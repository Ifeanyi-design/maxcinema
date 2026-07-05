from datetime import datetime
from itertools import cycle

from flask import render_template, redirect, url_for, request, flash
from flask_login import login_required
from sqlalchemy import func
from slugify import slugify

from . import admin_bp
from .forms import AllVideoForm, SeasonForm, EpisodeForm
from ..models import AllVideo, Genre, StorageServer, Series, Season, Episode, db, Trailer, MovieRequest, User, Movie
from ..indexnow import (
    submit_for_video, submit_for_episode, urls_for_video,
    submit_indexnow_urls, build_episode_url,
)
from .helpers import admin_required


@admin_bp.route('/series/add/<prev>', methods=['GET', 'POST'])
@login_required
@admin_required
def add_series(prev):
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
            download_link=form.download_link.data,
            dub_download_link=form.dub_download_link.data,
            backup_link=form.backup_link.data,
            trailer_url=form.trailer_url.data,
            released_date=form.released_date.data,
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
        video = AllVideo.query.filter_by(slug=slug).first()
        return redirect(url_for("admin.view_series_specific", prev="series", name=video.slug, id=video.id))

    return render_template("admin/add_series.html", form=form, prev=prev)


@admin_bp.route('/series')
@login_required
@admin_required
def view_series():
    total_movies = AllVideo.query.filter_by(type='movie').count()
    total_series = AllVideo.query.filter_by(type='series').count()
    total_trailers = Trailer.query.count()
    total_users = User.query.count()
    total_views = db.session.query(db.func.sum(AllVideo.views)).scalar() or 0
    total_requests = MovieRequest.query.filter_by(status='Pending').count()
    series = True
    page = request.args.get('page', 1, type=int)
    per_page = 24

    series_list = (
        AllVideo.query
        .filter_by(type="series")
        .order_by(AllVideo.created_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )
    return render_template('admin/view_series.html', series_list=series_list, series=series, total_movies=total_movies, total_series=total_series, total_trailers=total_trailers, total_users=total_users, total_views=total_views, total_requests=total_requests)


@admin_bp.route("/series/viewspec/<prev>/<name>/<id>")
@login_required
@admin_required
def view_series_specific(prev, name, id):
    total_movies = AllVideo.query.filter_by(type='movie').count()
    total_series = AllVideo.query.filter_by(type='series').count()
    total_trailers = Trailer.query.count()
    total_users = User.query.count()
    total_views = db.session.query(db.func.sum(AllVideo.views)).scalar() or 0
    total_requests = MovieRequest.query.filter_by(status='Pending').count()
    series = AllVideo.query.get_or_404(id)
    return render_template("admin/series.html", series=series, prev=prev, total_requests=total_requests, total_movies=total_movies, total_series=total_series, total_trailers=total_trailers, total_users=total_users, total_views=total_views)


@admin_bp.route('/series/<int:series_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_series(series_id):
    series = Series.query.get_or_404(series_id)
    video = AllVideo.query.get(series.all_video_id)
    deleted_urls = urls_for_video(video)

    db.session.delete(series)
    if video:
        db.session.delete(video)
    db.session.commit()
    submit_indexnow_urls(deleted_urls)
    flash('Series and associated videos deleted.', 'success')
    return redirect(url_for('admin.view_series'))


@admin_bp.route('/series/<prev>/<int:series_id>/seasons/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_season(series_id, prev):
    series = AllVideo.query.get_or_404(series_id)
    form = SeasonForm()

    if form.validate_on_submit():
        season = Season(
            series_id=series.series.id,
            season_number=form.season_number.data,
            description=form.description.data,
            cast=form.cast.data,
            completed=form.completed.data,
            release_date=form.release_date.data,
            image=form.image.data,
            trailer_url=form.trailer_url.data,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.session.add(season)
        db.session.commit()
        serie = Series.query.filter_by(all_video_id=series.id).first()
        ep = Season.query.filter_by(series_id=serie.id).count()
        serie.num_seasons = int(ep)
        db.session.commit()
        submit_for_video(series)
        flash(f"Season {season.season_number} added to {series.name}.", "success")
        return redirect(url_for('admin.view_series_specific', prev=prev, name=series.slug, id=series.id))

    return render_template('admin/add_season.html', prev=prev, form=form, series=series, action="Create")


@admin_bp.route('/seasons/<prev>/<name>/<int:id>/<int:season_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_season(prev, name, id, season_id):
    season = Season.query.get_or_404(season_id)
    serie = AllVideo.query.get_or_404(id)
    deleted_urls = urls_for_video(serie) + [build_episode_url(episode) for episode in season.episodes]

    db.session.delete(season)
    db.session.commit()
    season_count = len(serie.series.seasons)
    serie.series.num_seasons = season_count
    db.session.commit()
    submit_indexnow_urls(deleted_urls + urls_for_video(serie))
    flash('Season deleted.', 'success')
    return redirect(url_for('admin.view_series_specific', prev=prev, name=name, id=id))


@admin_bp.route('/serie/<prev>/<name>/<int:series_id>/season/<int:season_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_season(prev, name, series_id, season_id):
    series = AllVideo.query.get_or_404(series_id)
    season = Season.query.get_or_404(season_id)
    form = SeasonForm(obj=season)

    if form.validate_on_submit():
        form.populate_obj(season)
        season.updated_at = datetime.utcnow()
        db.session.commit()
        submit_for_video(series)
        flash(f"Season {season.season_number} updated.", "success")
        return redirect(url_for('admin.view_series_specific', prev=prev, name=series.slug, id=series.id))

    return render_template('admin/season_form.html', form=form, season=season, series=series, prev=prev, action="Edit")


@admin_bp.route("/series/<name>/season-<int:ns>/episodes/<prev>/<int:season_id>")
@login_required
@admin_required
def view_episodes(name, ns, prev, season_id):
    season = Season.query.get_or_404(season_id)
    return render_template("admin/episodes.html", prev=prev, season=season)


@admin_bp.route('/seasons/<prev>/<int:season_id>/episodes/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_episode(season_id, prev):
    season = Season.query.get_or_404(season_id)
    form = EpisodeForm()

    form.storage_server_id.choices = [(s.id, s.name) for s in StorageServer.query.filter_by(active=True).all()]

    if form.validate_on_submit():
        existing_episode = Episode.query.filter_by(
            season_id=season.id,
            episode_number=form.episode_number.data
        ).first()

        if not existing_episode:
            new_episode = Episode()
            form.populate_obj(new_episode)
            new_episode.season_id = season.id

            db.session.add(new_episode)
            db.session.commit()

            season.num_episodes = Episode.query.filter_by(season_id=season.id).count()

            video = Series.query.get_or_404(season.series.id)

            total_eps = 0
            for s in video.seasons:
                total_eps += len(s.episodes)
            video.num_episodes = total_eps

            db.session.commit()
            submit_for_episode(new_episode)

            flash(f"Episode {new_episode.episode_number} created successfully!", "success")
            return redirect(url_for('admin.view_series_specific', prev=prev, name=video.all_video.slug, id=video.all_video.id))
        else:
            flash(f"Episode {form.episode_number.data} already exists in this season!", "error")
            video = Series.query.get_or_404(season.series.id)
            return redirect(url_for('admin.view_series_specific', prev=prev, name=video.all_video.slug, id=video.all_video.id))

    return render_template('admin/add_episode.html', prev=prev, form=form, season=season, action="Create")


@admin_bp.route('/episodes/<name>/<prev>/<int:series_id>/<int:season_id>/<int:episode_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_episode(name, prev, series_id, season_id, episode_id):
    episode = Episode.query.get_or_404(episode_id)
    series = AllVideo.query.get_or_404(series_id)
    season = Season.query.get_or_404(season_id)

    form = EpisodeForm(obj=episode)
    form.storage_server_id.choices = [
        (s.id, s.name) for s in StorageServer.query.filter_by(active=True).all()
    ]

    if form.validate_on_submit():
        original_season_id = episode.season_id

        form.populate_obj(episode)

        if form.season_id.data:
            if Season.query.get(form.season_id.data):
                episode.season_id = form.season_id.data
            else:
                db.session.rollback()
                flash(f"Error: Season ID {form.season_id.data} does not exist!", "error")
                return render_template('admin/add_episode.html', form=form, season=season, series=series, prev="serie", action="Edit")
        else:
            episode.season_id = original_season_id

        episode.updated_at = datetime.utcnow()
        db.session.commit()
        submit_for_episode(episode)

        flash(f"Episode updated successfully.", "success")
        return redirect(url_for('admin.view_episodes', prev=prev, name=series.slug, ns=season.season_number, season_id=season.id))

    return render_template('admin/add_episode.html', form=form, season=season, series=series, prev="serie" if prev == "serie" or prev == "series" else "incomplete", action="Edit")


@admin_bp.route('/episodes/<name>/<int:id>/<int:season_id>/<prev>/<int:episode_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_episode(name, id, prev, season_id, episode_id):
    episode = Episode.query.get_or_404(episode_id)
    deleted_urls = [build_episode_url(episode)]

    db.session.delete(episode)
    db.session.commit()
    season = Season.query.get_or_404(season_id)
    serie = AllVideo.query.get_or_404(id)
    season.num_episodes = Episode.query.filter_by(season_id=season.id).count()

    total_eps = 0
    for s in serie.series.seasons:
        total_eps += len(s.episodes)
    serie.series.num_episodes = total_eps

    db.session.commit()
    submit_indexnow_urls(deleted_urls + urls_for_video(serie))
    flash('Episode deleted.', 'success')
    return redirect(url_for('admin.view_episodes', prev=prev, name=name, season_id=season_id, ns=season.season_number))
