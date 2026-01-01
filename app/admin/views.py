from datetime import datetime
from os import name
from flask import render_template, abort, redirect, url_for, request, flash
from ..models import AllVideo, Series, Trailer, StorageServer, User, db, RecentItem, Genre, Movie, Season, Episode, Rating, Comment, MovieRequest
from slugify import slugify
from ..extensions import login_manager
from . import admin_bp
from .forms import AllVideoForm, StorageServerForm, SeasonForm, TrailerForm, EpisodeForm, UserForm
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps
from flask_login import login_required, current_user, login_user, logout_user

from ..utils import ContentImporter # Import the class we just made




def admin_required(func):
    @wraps(func)
    def decorated_view(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            return abort(403)
        return func(*args, **kwargs)
    return decorated_view

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("admin.dashboard"))

    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        user = User.query.filter_by(email=email).first()
        print(user)
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            flash("Logged in successfully!", "success")
            return redirect(url_for("admin.dashboard"))
        flash("Invalid credentials", "danger")

    return render_template("login.html")

@admin_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out successfully!", "success")
    return redirect(url_for("admin.login"))


@admin_bp.route('/')
@login_required
@admin_required
def dashboard():
    # Basic stats
    total_movies = AllVideo.query.filter_by(type='movie').count()
    total_series = AllVideo.query.filter_by(type='series').count()
    total_trailers = Trailer.query.count()
    total_users = User.query.count()
    total_views = db.session.query(db.func.sum(AllVideo.views)).scalar() or 0
    total_requests = MovieRequest.query.filter_by(status='Pending').count()

    # Storage info
    storage_servers = StorageServer.query.all()
    storage_info = []
    for server in storage_servers:
        storage_info.append({
            'name': server.name,
            'used': server.used_storage_gb,
            'available': server.available_storage()
        })

    # Fetch all videos for Netflix-style grid
    all_videos = AllVideo.query.order_by(AllVideo.created_at.desc()).all()
    all_videos_dict = []
    for v in all_videos:
        all_videos_dict.append({
            'id': v.id,
            'name': v.name,
            'type': v.type,
            'description': v.description,
            'poster_url': v.image,
            'views': v.views,
            'slug': v.slug
        })

    return render_template(
        'admin/dashboard.html',
        total_movies=total_movies,
        total_series=total_series,
        total_trailers=total_trailers,
        total_users=total_users,
        total_views=total_views,
        storage_info=storage_info,
        all_videos=all_videos_dict,
        total_requests=total_requests
    )


import json


@admin_bp.route('/edit_video/<prev>/<int:video_id>', methods=["GET", "POST"])
@login_required
def edit_video(video_id, prev):
    video = AllVideo.query.get_or_404(video_id)

    form = AllVideoForm(obj=video)   # preload current video data

    # Load genre choices
    form.genres.choices = [(g.id, g.name) for g in Genre.query.order_by(Genre.name).all()]

    # Load storage server dropdown
    form.storage_server_id.choices = [
        (s.id, s.name) for s in StorageServer.query.filter_by(active=True).all()
    ]

    # Pre-select genres (only on GET)
    if request.method == "GET":
        form.genres.data = [g.id for g in video.genres]

    if form.validate_on_submit():
        # Update simple fields
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
        video.download_link = form.download_link.data
        video.image = form.image.data
        video.type = form.type.data
        video.trailer_url = form.trailer_url.data

        # Update booleans
        video.featured = form.featured.data
        video.trending = form.trending.data
        video.active = form.active.data

        # Update genres (many-to-many)
        selected_genre_ids = form.genres.data
        video.genres = Genre.query.filter(Genre.id.in_(selected_genre_ids)).all()

        # Update storage server
        video.storage_server_id = form.storage_server_id.data
        print("Hello")
        db.session.commit()
        flash("Video updated successfully!", "success")
        return redirect(url_for("admin.dashboard"))

    return render_template("admin/video_edit.html", form=form, video=video, prev=prev)




@admin_bp.route('/delete_video/<prev>/<int:video_id>', methods=['POST', 'GET'])
@login_required
@admin_required
def delete_video(video_id, prev):
    video = AllVideo.query.get_or_404(video_id)

    try:
        # ---------------- Delete RecentItems ----------------
        # Delete video-level recent items
        RecentItem.query.filter_by(video_id=video.id).delete()

        # If it's a series, delete recent items for all episodes
        if video.series:
            for season in video.series.seasons:
                for episode in season.episodes:
                    RecentItem.query.filter_by(episode_id=episode.id).delete()
            # Delete series-level recent items
            RecentItem.query.filter_by(series_id=video.series.id).delete()

        # ---------------- Delete Comments ----------------
        Comment.query.filter_by(video_id=video.id).delete()

        # ---------------- Delete Movie or Series ----------------
        if video.movie:
            db.session.delete(video.movie)

        if video.series:
            for season in video.series.seasons:
                for episode in season.episodes:
                    db.session.delete(episode)
                db.session.delete(season)
            db.session.delete(video.series)

        # ---------------- Finally delete the AllVideo ----------------
        db.session.delete(video)
        db.session.commit()
        flash("Video and all related content deleted successfully!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting video: {str(e)}", "error")
    if prev == "dashboard":
        return redirect(url_for('admin.dashboard'))
    elif prev == "movie":
        return redirect(url_for('admin.view_movies'))
    if prev == "serie":
        return redirect(url_for('admin.view_series'))



@admin_bp.route('/movies/add/<prev>', methods=['GET', 'POST'])
@login_required
@admin_required
def add_movie(prev):
    form = AllVideoForm()

    # Populate genre choices dynamically
    form.genres.choices = [(g.id, g.name) for g in Genre.query.order_by(Genre.name).all()]
    # Populate storage server choices dynamically
    form.storage_server_id.choices = [(s.id, s.name) for s in StorageServer.query.filter_by(active=True).all()]

    if form.validate_on_submit():
        # Create new AllVideo instance
        
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
            download_link=form.download_link.data,
            trailer_url=form.trailer_url.data,
            image=form.image.data,
            type=form.type.data,
            featured=form.featured.data,
            trending=form.trending.data,
            active=form.active.data,
            storage_server_id=form.storage_server_id.data or None
        )

        # Add video to session
        db.session.add(video)
        db.session.commit()  # Commit first to generate video.id

        # Assign genres (helper table)
        selected_genres = Genre.query.filter(Genre.id.in_(form.genres.data)).all()
        video.genres = selected_genres

        # Create Movie or Series record
        if video.type == "movie":
            movie = Movie(all_video_id=video.id)
            db.session.add(movie)
        elif video.type == "series":
            series = Series(all_video_id=video.id)
            db.session.add(series)

        db.session.commit()
        flash(f"{video.type.capitalize()} '{video.name}' added successfully!", "success")
        return redirect(url_for("admin.add_movie", prev=prev))

    return render_template("admin/add_movie.html", form=form, prev=prev)

@admin_bp.route('/series/add/<prev>', methods=['GET', 'POST'])
@login_required
@admin_required
def add_series(prev):
    form = AllVideoForm()

    # Populate genre choices dynamically
    form.genres.choices = [(g.id, g.name) for g in Genre.query.order_by(Genre.name).all()]
    # Populate storage server choices dynamically
    form.storage_server_id.choices = [(s.id, s.name) for s in StorageServer.query.filter_by(active=True).all()]

    if form.validate_on_submit():
        # Create new AllVideo instance
        
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
            trailer_url=form.trailer_url.data,
            released_date=form.released_date.data,
            image=form.image.data,
            type=form.type.data,
            featured=form.featured.data,
            trending=form.trending.data,
            active=form.active.data,
            storage_server_id=form.storage_server_id.data or None
        )

        # Add video to session
        db.session.add(video)
        db.session.commit()  # Commit first to generate video.id

        # Assign genres (helper table)
        selected_genres = Genre.query.filter(Genre.id.in_(form.genres.data)).all()
        video.genres = selected_genres

        # Create Movie or Series record
        if video.type == "movie":
            movie = Movie(all_video_id=video.id)
            db.session.add(movie)
        elif video.type == "series":
            series = Series(all_video_id=video.id)
            db.session.add(series)

        db.session.commit()
        flash(f"{video.type.capitalize()} '{video.name}' added successfully!", "success")
        video = AllVideo.query.filter_by(slug=slug).first()
        return redirect(url_for("admin.view_series_specific", prev="series", name=video.slug, id=video.id))

    return render_template("admin/add_series.html", form=form, prev=prev)

# ---------------- View Movies ----------------
@admin_bp.route('/movies')
@login_required
@admin_required
def view_movies():
    movie=True
    total_movies = AllVideo.query.filter_by(type='movie').count()
    total_series = AllVideo.query.filter_by(type='series').count()
    total_trailers = Trailer.query.count()
    total_users = User.query.count()
    total_views = db.session.query(db.func.sum(AllVideo.views)).scalar() or 0
    total_requests = MovieRequest.query.filter_by(status='Pending').count()
    movies = AllVideo.query.filter_by(type='movie').order_by(AllVideo.created_at.desc()).all()
    return render_template('admin/view_movies.html', movies=movies, movie=movie, total_movies=total_movies, total_series=total_series, total_trailers=total_trailers, total_users=total_users, total_views=total_views, total_requests=total_requests)


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



# ---------------- View Series ----------------
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
    # show series entries (joining with AllVideo)
    series=True
    series_list = AllVideo.query.filter_by(type="series").order_by(AllVideo.created_at.desc()).all()
    return render_template('admin/view_series.html', series_list=series_list, series=series, total_movies=total_movies, total_series=total_series, total_trailers=total_trailers, total_users=total_users, total_views=total_views, total_requests=total_requests)


@admin_bp.route('/series/<int:series_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_series(series_id):
    series = Series.query.get_or_404(series_id)
    video = AllVideo.query.get_or_404(series.all_video_id)
    genres = Genre.query.order_by(Genre.name).all()
    storage_servers = StorageServer.query.filter_by(active=True).all()

    if request.method == 'POST':
        data = request.form

        # Helper: only set if non-empty (ignores empty inputs)
        def set_if_present(obj, attr, value, cast=None):
            if value is not None and value != '':
                setattr(obj, attr, cast(value) if cast else value)

        set_if_present(video, 'name', data.get('name'))
        # slug: if empty, keep existing; else slugify if requested or use provided
        slug_val = data.get('slug')
        if slug_val:
            video.slug = slugify(slug_val)
        # other fields
        set_if_present(video, 'image', data.get('image'))
        set_if_present(video, 'description', data.get('description'))
        set_if_present(video, 'length', data.get('length'))
        set_if_present(video, 'year_produced', data.get('year_produced'), cast=int)
        set_if_present(video, 'star_cast', data.get('star_cast'))
        set_if_present(video, 'country', data.get('country'))
        set_if_present(video, 'language', data.get('language'))
        set_if_present(video, 'subtitles', data.get('subtitles'))
        set_if_present(video, 'source', data.get('source'))
        set_if_present(video, 'trailer_url', data.get('trailer_url'))
        if data.get('rating') != '':
            video.rating = float(data.get('rating')) if data.get('rating') else None
        if data.get('num_votes') != '':
            video.num_votes = int(data.get('num_votes')) if data.get('num_votes') else None

        # boolean toggles: checkboxes submit 'on' or value; use presence to toggle
        video.featured = bool(data.get('featured'))
        video.trending = bool(data.get('trending'))
        video.active = bool(data.get('active'))

        # storage server
        if data.get('storage_server_id'):
            video.storage_server_id = int(data.get('storage_server_id'))

        # video qualities (JSON)
        vq = data.get('video_qualities')
        if vq:
            try:
                parsed = json.loads(vq)
                video.video_qualities = parsed
            except Exception:
                flash('Invalid JSON for video_qualities', 'error')
                return redirect(url_for('admin.edit_series', series_id=series.id))

        # genres
        selected_genres = data.getlist('genres')
        if selected_genres:
            video.genres = Genre.query.filter(Genre.id.in_(selected_genres)).all()

        # update Series-specific fields (num_seasons, num_episodes)
        if data.get('num_seasons') != '':
            series.num_seasons = int(data.get('num_seasons'))
        if data.get('num_episodes') != '':
            series.num_episodes = int(data.get('num_episodes'))

        db.session.commit()
        flash('Series updated.', 'success')
        return redirect(url_for('admin.view_series'))

    # GET: prefill form
    return render_template('admin/edit_series.html',
                           series=series, video=video,
                           genres=genres, storage_servers=storage_servers)

@admin_bp.route('/series/<int:series_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_series(series_id):
    series = Series.query.get_or_404(series_id)
    video = AllVideo.query.get(series.all_video_id)

    # Optional: remove RecentItem rows referencing this series or its videos/episodes
    # try:
    #     RecentItem.query.filter(
    #         (RecentItem.series_id == series.id) |
    #         (RecentItem.video_id == video.id)
    #     ).delete(synchronize_session=False)
    # except Exception:
    #     # Not critical — continue
    #     pass

    # deleting series will cascade-delete seasons -> episodes (because of cascade on seasons->episodes)
    # but AllVideo should be removed explicitly
    # Remove Series entry and AllVideo entry (and related ratings/comments via cascade)
    db.session.delete(series)
    if video:
        db.session.delete(video)
    db.session.commit()
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
        flash(f"Season {season.season_number} added to {series.name}.", "success")
        return redirect(url_for('admin.view_series_specific',prev=prev, name=series.slug, id=series.id))

    return render_template('admin/add_season.html',prev=prev, form=form, series=series, action="Create")


@admin_bp.route('/seasons/<prev>/<name>/<int:id>/<int:season_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_season(prev, name, id, season_id):
    season = Season.query.get_or_404(season_id)
    # optional: remove RecentItem referencing episodes in this season
    # try:
    #     episode_ids = [e.id for e in season.episodes]
    #     RecentItem.query.filter(RecentItem.episode_id.in_(episode_ids)).delete(synchronize_session=False)
    # except Exception:
    #     pass

    db.session.delete(season)
    db.session.commit()
    serie = AllVideo.query.get_or_404(id)
    season_count = len(serie.series.seasons)
    serie.series.num_seasons = season_count
    db.session.commit()
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
        flash(f"Season {season.season_number} updated.", "success")
        return redirect(url_for('admin.view_series_specific',prev=prev, name=series.slug, id=series.id))

    return render_template('admin/season_form.html', form=form, season=season, series=series, prev=prev, action="Edit")


@admin_bp.route("/series/<name>/season-<int:ns>/episodes/<prev>/<int:season_id>")
@login_required
@admin_required
def view_episodes(name, ns, prev, season_id):

    season = Season.query.get_or_404(season_id)

    return render_template("admin/episodes.html", prev=prev, season=season)

# ----------------- Episode: Add / Edit / Delete / View -----------------

@admin_bp.route('/seasons/<prev>/<int:season_id>/episodes/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_episode(season_id, prev):
    season = Season.query.get_or_404(season_id)
    form = EpisodeForm()
    
    # Load storage servers
    form.storage_server_id.choices = [(s.id, s.name) for s in StorageServer.query.filter_by(active=True).all()]

    if form.validate_on_submit():
        # --- FIX IS HERE: Added .first() ---
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
            
            # Update Season Episode Count
            season.num_episodes = Episode.query.filter_by(season_id=season.id).count()
            
            # Update Series Total Episode Count (Sum of all seasons)
            video = Series.query.get_or_404(season.series.id)
            
            # Note: You were setting series total to equal this specific season's count. 
            # Ideally, it should be the total of all episodes in the series:
            total_eps = 0
            for s in video.seasons:
                total_eps += len(s.episodes)
            video.num_episodes = total_eps
            
            db.session.commit()
            
            flash(f"Episode {new_episode.episode_number} created successfully!", "success")
            return redirect(url_for('admin.view_series_specific', prev=prev, name=video.all_video.slug, id=video.all_video.id))
        else:
            # Add a message so you know why it failed
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
        form.populate_obj(episode)
        episode.updated_at = datetime.utcnow()
        db.session.commit()
        flash(f"Season {season.season_number} updated.", "success")
        return redirect(url_for('admin.view_episodes',prev=prev, name=series.slug, ns=season.season_number, season_id=season.id))

    return render_template('admin/add_episode.html', form=form, season=season, series=series, prev="serie", action="Edit")


@admin_bp.route('/episodes/<name>/<int:id>/<int:season_id>/<prev>/<int:episode_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_episode(name, id, prev, season_id, episode_id):

    episode = Episode.query.get_or_404(episode_id)
    # optional: remove RecentItem referencing episodes in this season
    # try:
    #     episode_ids = [e.id for e in season.episodes]
    #     RecentItem.query.filter(RecentItem.episode_id.in_(episode_ids)).delete(synchronize_session=False)
    # except Exception:
    #     pass

    db.session.delete(episode)
    db.session.commit()
    season = Season.query.get_or_404(season_id)
    serie = AllVideo.query.get_or_404(id)
    episode_count = len(season.episodes)
    serie.series.num_episodes = episode_count
    season.num_episodes = episode_count
    db.session.commit()
    flash('Season deleted.', 'success')
    return redirect(url_for('admin.view_episodes', prev=prev, name=name, season_id=season_id, ns=season.season_number))



@admin_bp.route("/trailers")
def view_trailers():
    total_movies = AllVideo.query.filter_by(type='movie').count()
    total_series = AllVideo.query.filter_by(type='series').count()
    total_trailers = Trailer.query.count()
    total_users = User.query.count()
    total_views = db.session.query(db.func.sum(AllVideo.views)).scalar() or 0
    total_requests = MovieRequest.query.filter_by(status='Pending').count()
    trailers = Trailer.query.all()
    return render_template("admin/trailers.html", trailers=trailers, total_movies=total_movies, total_series=total_series, total_trailers=total_trailers, total_users=total_users, total_views=total_views, total_requests=total_requests)

@admin_bp.route("/delete-trailer/<int:trailer_id>", methods=["GET", "POST"])
@login_required
@admin_required
def delete_trailer(trailer_id):
    trailer = Trailer.query.get_or_404(trailer_id)
    db.session.delete(trailer)
    db.session.commit()
    return redirect(url_for("admin.view_trailers"))

@admin_bp.route("/edit-trailer/<prev>/<slug>/<int:trailer_id>", methods=["GET", "POST"])
@login_required
@admin_required
def edit_trailer(prev, slug, trailer_id):
    trailer = Trailer.query.get_or_404(trailer_id)
    form = TrailerForm(obj=trailer)
    if form.validate_on_submit():
        form.populate_obj(trailer)
        db.session.commit()
        flash(f"Season {trailer.name} updated.", "success")
        return redirect(url_for("admin.view_trailers"))
    return render_template("admin/trailer_form.html", form=form)

@admin_bp.route("/add-trailer/<prev>", methods=["GET", "POST"])
@login_required
@admin_required
def add_trailer(prev):
    new_trailer = Trailer()
    form = TrailerForm()
    if form.validate_on_submit():
        form.populate_obj(new_trailer)
        db.session.add(new_trailer)
        db.session.commit()
        return redirect(url_for("admin.view_trailers"))
    return render_template("admin/trailer_form.html", form=form)


@admin_bp.route("/users")
def view_users():
    total_movies = AllVideo.query.filter_by(type='movie').count()
    total_series = AllVideo.query.filter_by(type='series').count()
    total_trailers = Trailer.query.count()
    total_users = User.query.count()
    total_views = db.session.query(db.func.sum(AllVideo.views)).scalar() or 0
    total_requests = MovieRequest.query.filter_by(status='Pending').count()
    users = User.query.all()
    len_users = len(users)
    user=True
    return render_template("admin/users.html", user=user, len_users=len_users, users=users, total_movies=total_movies, total_series=total_series, total_trailers=total_trailers, total_users=total_users, total_views=total_views, total_requests=total_requests)

@admin_bp.route("/add-user", methods=["GET", "POST"])
@login_required
@admin_required
def add_user():
    form = UserForm()
    if form.validate_on_submit():
        if User.query.filter_by(email=form.email.data).first():
            flash("Email already exists.", "danger")
            return render_template("admin/user_form.html", form=form)
        password = generate_password_hash(form.password_hash.data)
        user = User(
            username=form.username.data,
            email=form.email.data,
            is_admin=form.is_admin.data,
            password_hash=password
        )
        db.session.add(user)
        db.session.commit()
        flash("User added successfully.", "success")
        return redirect(url_for("admin.view_users"))
    return render_template("admin/user_form.html", form=form)

@admin_bp.route("/edit-user/<int:user_id>", methods=["GET", "POST"])
@login_required
@admin_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    form = UserForm(obj=user)
    if form.validate_on_submit():
        if user.email != form.email.data and User.query.filter_by(email=form.email.data).first():
            flash("Email already exists.", "danger")
            return render_template("admin/user_form.html", form=form, user=user)
        form.populate_obj(user)
        if form.password_hash.data:
            user.password_hash = generate_password_hash(form.password_hash.data)
        db.session.commit()
        flash("User updated successfully.", "success")
        return redirect(url_for("admin.view_users"))
    return render_template("admin/user_form.html", form=form, user=user)

@admin_bp.route("/delete-user/<int:user_id>", methods=["POST"])
@login_required
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    flash("User deleted successfully.", "success")
    return redirect(url_for("admin.view_users"))

@admin_bp.route("/storage-servers")
def view_storage():
    server = True
    total_movies = AllVideo.query.filter_by(type='movie').count()
    total_series = AllVideo.query.filter_by(type='series').count()
    total_trailers = Trailer.query.count()
    total_users = User.query.count()
    total_views = db.session.query(db.func.sum(AllVideo.views)).scalar() or 0
    total_requests = MovieRequest.query.filter_by(status='Pending').count()
    servers = StorageServer.query.order_by(StorageServer.created_at.desc()).all()
    return render_template("admin/view_storage.html", server=server, servers=servers, total_movies=total_movies, total_series=total_series, total_trailers=total_trailers, total_users=total_users, total_views=total_views, total_requests=total_requests)

@admin_bp.route("/storage-servers/add", methods=["GET", "POST"])
@login_required
@admin_required
def add_storage_server():
    # TODO: Add form logic here later
    form = StorageServerForm()
    if form.validate_on_submit():
        new_server = StorageServer()
        
        # 2. Magic: Auto-fill the model with form data
        form.populate_obj(new_server)
        
        # 3. Handle any fields NOT in the form (optional defaults)
        new_server.used_storage_gb = 0.0 
        
        try:
            db.session.add(new_server)
            db.session.commit()
            flash(f"Storage Server '{new_server.name}' added successfully!", "success")
            return redirect(url_for('admin.list_storage_servers'))
            
        except Exception as e:
            db.session.rollback()
            # Check if it's a duplicate name error
            if "UNIQUE constraint" in str(e) or "unique constraint" in str(e).lower():
                flash("Error: A server with that name already exists.", "error")
            else:
                flash(f"Database error: {str(e)}", "error")
        
    return render_template("admin/add_storage_server.html", form=form, title="Add New Server")


# 3. EDIT an existing server (Placeholder)
@admin_bp.route("/storage-servers/edit/<int:server_id>", methods=["GET", "POST"])
@login_required
@admin_required
def edit_storage_server(server_id):
    edit = True
    server = StorageServer.query.get_or_404(server_id)
    
    # 2. Pre-fill the form with the server's current data using 'obj='
    form = StorageServerForm(obj=server)
    
    if form.validate_on_submit():
        # 3. Magic: Update the EXISTING server object with new form data
        form.populate_obj(server)
        
        try:
            db.session.commit()
            flash(f"Server '{server.name}' updated successfully.", "success")
            return redirect(url_for('admin.list_storage_servers'))
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating server: {str(e)}", "error")

    # Pass 'server' to template so the title can say "Edit Server: AWS_S3"
    return render_template("admin/add_storage_server.html", edit=edit, form=form, title=f"Edit {server.name}")

# 4. DELETE a server (Fully Functional)
@admin_bp.route("/storage-servers/delete/<int:server_id>", methods=["POST"])
# @login_required
# @admin_required
def delete_storage_server(server_id):
    server = StorageServer.query.get_or_404(server_id)
    
    # Optional: Check if videos are using this server before deleting
    # if server.videos.count() > 0:
    #     flash("Cannot delete: This server contains videos.", "error")
    #     return redirect(url_for('admin.list_storage_servers'))

    try:
        db.session.delete(server)
        db.session.commit()
        flash(f"Server '{server.name}' deleted successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash("Error deleting server.", "error")
        
    return redirect(url_for("admin.list_storage_servers"))


@admin_bp.route('/requests')
@login_required
def view_requests():
    total_movies = AllVideo.query.filter_by(type='movie').count()
    total_series = AllVideo.query.filter_by(type='series').count()
    total_trailers = Trailer.query.count()
    total_users = User.query.count()
    total_views = db.session.query(db.func.sum(AllVideo.views)).scalar() or 0
    total_requests = MovieRequest.query.filter_by(status='Pending').count()
    # Get all requests, newest first
    requests_list = MovieRequest.query.order_by(MovieRequest.date_added.desc()).all()
    return render_template('admin/requests.html', requests=requests_list, total_requests=total_requests, total_movies=total_movies, total_series=total_series, total_trailers=total_trailers, total_users=total_users, total_views=total_views)


# 2. UPDATE STATUS (Filled/Rejected/Pending)
@admin_bp.route('/request/status/<int:id>/<string:status>')
@login_required
def update_request_status(id, status):
    req = MovieRequest.query.get_or_404(id)
    
    # Valid statuses only
    if status in ['Pending', 'Filled', 'Rejected']:
        req.status = status
        db.session.commit()
        flash(f'Request marked as {status}', 'success')
    
    return redirect(url_for('admin.view_requests'))

# 3. DELETE REQUEST
@admin_bp.route('/request/delete/<int:id>')
@login_required
def delete_request(id):
    req = MovieRequest.query.get_or_404(id)
    db.session.delete(req)
    db.session.commit()
    flash('Request deleted', 'success')
    return redirect(url_for('admin.view_requests'))


# In admin.py

@admin_bp.route('/admin/import-tmdb', methods=['GET', 'POST'])
@login_required
@admin_required
def import_tmdb():
    if request.method == 'POST':
        print("DEBUG: Form Submitted! Processing...") # <--- LOOK FOR THIS IN TERMINAL
        
        try:
            # 1. Check Imports
            print("DEBUG: Initializing Importer...")
            from .utils import ContentImporter # Import here to catch errors instantly
            importer = ContentImporter()
            print("DEBUG: Importer Initialized.")

            # 2. Get Data
            tmdb_id = request.form.get('tmdb_id')
            ctype = request.form.get('type')
            print(f"DEBUG: Type={ctype}, ID={tmdb_id}")

            msg = ""
            if ctype == 'movie':
                msg = importer.import_movie(tmdb_id)
            
            elif ctype == 'series':
                seasons_in = request.form.get('seasons')
                ep_range = request.form.get('episodes')
                print(f"DEBUG: Seasons={seasons_in}, Episodes={ep_range}")
                
                msg = importer.import_series(tmdb_id, seasons_in, ep_range)
            
            print(f"DEBUG: Success! Message: {msg}")
            flash(msg, 'success')

        except ImportError as e:
            err = f"CRASH: Missing Library! Run 'pip install tmdbv3api'. Error: {e}"
            print(err)
            flash(err, 'error')
            
        except Exception as e:
            # This prints the EXACT line number that failed
            import traceback
            traceback.print_exc() 
            err = f"CRASH: {str(e)}"
            print(err)
            flash(err, 'error')

        return redirect(url_for('admin.import_tmdb'))

    return render_template('admin/import.html')
