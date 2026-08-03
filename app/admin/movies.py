from flask import render_template, redirect, url_for, request, flash
from flask_login import login_required
from slugify import slugify

from . import admin_bp
from .forms import AllVideoForm
from ..models import AllVideo, Genre, StorageServer, Movie, Series, db, Trailer, MovieRequest, User, RecentItem, Comment
from ..indexnow import submit_for_video, urls_for_video, submit_indexnow_urls
from .helpers import admin_required, _has_download_payload, _send_release_notifications, _normalize_download_link


@admin_bp.route('/edit_video/<prev>/<int:video_id>', methods=["GET", "POST"])
@login_required
@admin_required
def edit_video(video_id, prev):
    video = AllVideo.query.get_or_404(video_id)
    was_coming_soon = bool(video.coming_soon)

    form = AllVideoForm(obj=video)

    form.genres.choices = [(g.id, g.name) for g in Genre.query.order_by(Genre.name).all()]
    form.storage_server_id.choices = [
        (s.id, s.name) for s in StorageServer.query.filter_by(active=True).all()
    ]

    if request.method == "GET":
        form.genres.data = [g.id for g in video.genres]

    if form.validate_on_submit():
        selected_server = None
        if form.storage_server_id.data:
            selected_server = StorageServer.query.get(form.storage_server_id.data)

        video.name = form.name.data
        video.slug = form.slug.data
        video.description = form.description.data
        video.year_produced = form.year_produced.data
        video.length = form.length.data
        video.rating = form.rating.data
        video.country = form.country.data
        video.language = form.language.data
        video.subtitles = form.subtitles.data
        video.released_date = form.released_date.data
        video.star_cast = form.star_cast.data
        video.source = form.source.data
        video.download_link = _normalize_download_link(form.download_link.data, selected_server)
        video.dub_download_link = _normalize_download_link(form.dub_download_link.data, selected_server)
        video.image = form.image.data
        video.type = form.type.data
        video.trailer_url = form.trailer_url.data
        video.backup_link = form.backup_link.data
        video.coming_soon = form.coming_soon.data
        video.featured = form.featured.data
        video.trending = form.trending.data
        video.active = form.active.data

        selected_genre_ids = form.genres.data
        video.genres = Genre.query.filter(Genre.id.in_(selected_genre_ids)).all()

        video.storage_server_id = form.storage_server_id.data
        db.session.commit()
        if was_coming_soon and (not video.coming_soon) and _has_download_payload(video):
            summary = _send_release_notifications(video)
            if summary["queued"] > 0:
                flash(
                    f"Release notifications sent: email {summary['emailed']}, telegram {summary['telegram']}, marked {summary['marked']}/{summary['queued']}.",
                    "info"
                )
        submit_for_video(video)
        flash("Video updated successfully!", "success")
        return redirect(url_for("admin.dashboard"))

    return render_template("admin/video_edit.html", form=form, video=video, prev=prev)


@admin_bp.route('/delete_video/<prev>/<int:video_id>', methods=['POST', 'GET'])
@login_required
@admin_required
def delete_video(video_id, prev):
    video = AllVideo.query.get_or_404(video_id)
    deleted_urls = urls_for_video(video)

    try:
        RecentItem.query.filter_by(video_id=video.id).delete()

        if video.series:
            for season in video.series.seasons:
                for episode in season.episodes:
                    RecentItem.query.filter_by(episode_id=episode.id).delete()
            RecentItem.query.filter_by(series_id=video.series.id).delete()

        Comment.query.filter_by(video_id=video.id).delete()

        if video.movie:
            db.session.delete(video.movie)

        if video.series:
            for season in video.series.seasons:
                for episode in season.episodes:
                    db.session.delete(episode)
                db.session.delete(season)
            db.session.delete(video.series)

        db.session.delete(video)
        db.session.commit()
        submit_indexnow_urls(deleted_urls)
        flash("Video and all related content deleted successfully!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting video: {str(e)}", "error")
    if prev == "dashboard":
        return redirect(url_for('admin.dashboard'))
    elif prev == "movie":
        return redirect(url_for('admin.view_movies'))
    elif prev == "serie":
        return redirect(url_for('admin.view_series'))
    elif prev == "search":
        return redirect(url_for('admin.search'))
    elif prev == "incomplete":
        return redirect(url_for('admin.view_incomplete_content'))
    else:
        return redirect(url_for('admin.dashboard'))


@admin_bp.route('/movies/add/<prev>', methods=['GET', 'POST'])
@login_required
@admin_required
def add_movie(prev):
    form = AllVideoForm()

    form.genres.choices = [(g.id, g.name) for g in Genre.query.order_by(Genre.name).all()]
    form.storage_server_id.choices = [(s.id, s.name) for s in StorageServer.query.filter_by(active=True).all()]

    if form.validate_on_submit():
        base_slug = slugify(form.name.data)
        slug = base_slug
        counter = 1
        while AllVideo.query.filter_by(slug=slug).first():
            slug = f"{base_slug}-{counter}"
            counter += 1
        video = AllVideo(
            name=form.name.data,
            slug=slug,
            description=form.description.data,
            year_produced=form.year_produced.data,
            length=form.length.data,
            rating=form.rating.data,
            country=form.country.data,
            language=form.language.data,
            subtitles=form.subtitles.data,
            star_cast=form.star_cast.data,
            source=form.source.data,
            released_date=form.released_date.data,
            backup_link=form.backup_link.data,
            trailer_url=form.trailer_url.data,
            download_link=_normalize_download_link(form.download_link.data, StorageServer.query.get(form.storage_server_id.data) if form.storage_server_id.data else None),
            dub_download_link=_normalize_download_link(form.dub_download_link.data, StorageServer.query.get(form.storage_server_id.data) if form.storage_server_id.data else None),
            image=form.image.data,
            type=form.type.data,
            featured=form.featured.data,
            trending=form.trending.data,
            active=form.active.data,
            coming_soon=form.coming_soon.data,
            storage_server_id=form.storage_server_id.data or None
        )

        db.session.add(video)
        db.session.commit()

        selected_genres = Genre.query.filter(Genre.id.in_(form.genres.data)).all()
        video.genres = selected_genres

        if video.type == "movie":
            movie = Movie(all_video_id=video.id)
            db.session.add(movie)
        elif video.type == "series":
            series = Series(all_video_id=video.id)
            db.session.add(series)

        db.session.commit()
        submit_for_video(video)
        flash(f"{video.type.capitalize()} '{video.name}' added successfully!", "success")
        return redirect(url_for("admin.add_movie", prev=prev))

    return render_template("admin/add_movie.html", form=form, prev=prev)


@admin_bp.route('/movies')
@login_required
@admin_required
def view_movies():
    movie = True
    page = request.args.get('page', 1, type=int)
    per_page = 24

    total_movies = AllVideo.query.filter_by(type='movie').count()
    total_series = AllVideo.query.filter_by(type='series').count()
    total_trailers = Trailer.query.count()
    total_users = User.query.count()
    total_views = db.session.query(db.func.sum(AllVideo.views)).scalar() or 0
    total_requests = MovieRequest.query.filter_by(status='Pending').count()

    movies = (
        AllVideo.query
        .filter_by(type='movie')
        .order_by(AllVideo.created_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    return render_template(
        'admin/view_movies.html',
        movies=movies,
        movie=movie,
        total_movies=total_movies,
        total_series=total_series,
        total_trailers=total_trailers,
        total_users=total_users,
        total_views=total_views,
        total_requests=total_requests
    )
