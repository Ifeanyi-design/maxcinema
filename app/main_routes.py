from flask import Blueprint, make_response, render_template, abort, redirect, url_for, flash, request, jsonify, current_app, Response, stream_with_context, session
from flask_login import current_user, login_user, logout_user, login_required
from sqlalchemy.sql import func
from sqlalchemy.orm import joinedload, defer
from sqlalchemy import or_, text
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

import os
import time
import requests
from datetime import datetime
from functools import wraps
from slugify import slugify
from . import listeners
from .extensions import db, login_manager
from .models import (
    AllVideo, Movie, Series, StorageServer, User, Season, Episode,
    Genre, RecentItem, Rating, Comment, Trailer, MovieRequest
)

main_bp = Blueprint("main", __name__)



# # ---------------- Admin Required ----------------
# def admin_required(f):
#     @wraps(f)
#     def decorated_function(*args, **kwargs):
#         if not current_user.is_authenticated or not current_user.is_admin:
#             abort(403)
#         return f(*args, **kwargs)
#     return decorated_function

# @login_manager.user_loader
# def load_user(user_id):
#     return User.query.get(int(user_id))

def ping_search_engines():
    sitemap_url = "https://yourdomain.com/static/sitemap.xml"
    try:
        requests.get(f"http://www.google.com/ping?sitemap={sitemap_url}")
        requests.get(f"http://www.bing.com/ping?sitemap={sitemap_url}")
        print("Search engines notified!")
    except Exception as e:
        print("Ping failed:", e)

def get_up_next(trailer):
    # Same release year
    if trailer.release_year:
        up_next = Trailer.query.filter(
            Trailer.release_year == trailer.release_year,
            Trailer.id != trailer.id
        ).limit(6).all()

        if up_next:
            return up_next

    # Fallback: recent trailers
    up_next = Trailer.query.filter(
        Trailer.id != trailer.id
    ).order_by(Trailer.date_added.desc()).limit(6).all()

    if up_next:
        return up_next

    # Final fallback: random
    return Trailer.query.filter(
        Trailer.id != trailer.id
    ).order_by(func.random()).limit(6).all()

def populate_recent_items_bulk():
    """
    Efficiently populate RecentItem table with latest movies and latest episodes per series.
    """
    try:
        # Clear existing RecentItem table in one go
        db.session.query(RecentItem).delete(synchronize_session=False)

        # --- Latest movies ---
        movies = Movie.query.order_by(Movie.date_added.desc()).all()
        recent_movie_items = [
            RecentItem(
                video_id=m.id,
                episode_id=None,
                date_added=m.date_added,
                type="movie"
            )
            for m in movies
        ]
        if recent_movie_items:
            db.session.bulk_save_objects(recent_movie_items)

        # --- Latest episode per series ---
        latest_episodes = Episode.query.order_by(Episode.date_added.desc()).all()
        seen_series = set()
        recent_series_items = []

        for e in latest_episodes:
            if not e.season or not e.season.series:
                continue

            series_id = e.season.series.id
            if series_id in seen_series:
                continue

            recent_series_items.append(
                RecentItem(
                    video_id=None,
                    episode_id=e.id,
                    date_added=e.date_added,
                    type="series",
                    series_id=series_id
                )
            )
            seen_series.add(series_id)

        if recent_series_items:
            db.session.bulk_save_objects(recent_series_items)

        # Commit everything at once
        db.session.commit()
        print("RecentItem table populated successfully (bulk)!")

    except Exception as e:
        db.session.rollback()
        raise e

from sqlalchemy.exc import OperationalError, PendingRollbackError

def safe_populate_bulk(retries=5, delay=0.2):
    for attempt in range(1, retries + 1):
        try:
            populate_recent_items_bulk()
            break
        except (OperationalError, PendingRollbackError) as e:
            if 'database is locked' in str(e):
                print(f"Database locked, retrying {attempt}/{retries} after {delay}s...")
                db.session.rollback()
                time.sleep(delay)
            else:
                raise
    else:
        print("Failed to populate RecentItem after multiple retries (bulk).")
safe_populate = safe_populate_bulk

@main_bp.route('/')
@main_bp.route('/<int:page>')
def index(page=1):
    per_page = 24
    features = AllVideo.query.filter_by(featured=True).order_by(AllVideo.updated_at.desc()).limit(8).all()
    series_trend = AllVideo.query.filter_by(trending=True, type="series").order_by(AllVideo.date_added.desc()).limit(6).all()
    movie_trend = AllVideo.query.filter_by(trending=True, type="movie").order_by(AllVideo.date_added.desc()).limit(6).all()
    trending_trailers = Trailer.query.order_by(Trailer.views.desc()).limit(5).all()


    data = AllVideo.query.order_by(func.random()).limit(24).all()
    videos = AllVideo.query.order_by(AllVideo.date_added.desc()).all()
    # Paginate RecentItem directly
    recent_paginated = RecentItem.query.order_by(RecentItem.date_added.desc()) \
                                       .paginate(page=page, per_page=per_page, error_out=False)
    
    print(len(recent_paginated.items))
    # Collect IDs for this page
    video_ids = [r.video_id for r in recent_paginated.items if r.video_id]
    episode_ids = [r.episode_id for r in recent_paginated.items if r.episode_id]
    print(len(video_ids)) 


    # Load all Video/Episode objects in one query each
    if video_ids:
        videos = {v.all_video_id: v for v in Movie.query.filter(Movie.all_video_id.in_(video_ids)).all()}
    else:
        videos = {}
    episodes = {e.id: e for e in Episode.query.filter(Episode.id.in_(episode_ids)).all()} if episode_ids else {}
    print(len(videos))
    # Prepare items for display
    items = []
    series_name = []
    index=True

    for r in recent_paginated.items:
        if r.video_id:
            v = videos.get(r.video_id)
            if v:
                items.append(v)
        elif r.episode_id:
            e = episodes.get(r.episode_id)
            if e.season.series.all_video.name not in series_name:
                series_name.append(e.season.series.all_video.name)
                items.append(e)
    return render_template('index.html', features=features, data=data,
                            trending_series=series_trend,
                              trending_movie=movie_trend,
                                items=items, per_page=per_page,
                                  page=page, total_pages=recent_paginated.pages,
                                  videos=recent_paginated, index=index, trending_trailers=trending_trailers)

@main_bp.route("/featured/<int:page>")
@main_bp.route("/featured")
def featured(page=1):
    per_page = 24
    feature = True
    series_trend = AllVideo.query.filter_by(trending=True, type="series").order_by(AllVideo.date_added.desc()).limit(6).all()
    movie_trend = AllVideo.query.filter_by(trending=True, type="movie").order_by(AllVideo.date_added.desc()).limit(6).all()
    trending_trailers = Trailer.query.order_by(Trailer.views.desc()).limit(5).all()
    featured_videos = AllVideo.query.filter_by(featured=True).order_by(AllVideo.date_added.desc()).paginate(page=page, per_page=per_page)
    return render_template("featured.html", trending_series=series_trend, trending_movie=movie_trend, videos=featured_videos, feature=feature, trending_trailers=trending_trailers)

@main_bp.route("/search_result")
@main_bp.route("/search_result/<int:page>")
def search_result(page=1):
    per_page=24
    query = request.args.get("search", "").strip()

    if not query:
        flash("Please enter a search term", "warning")
        return redirect(url_for("main.index"))
    
    search_filter = or_(
        AllVideo.name.ilike(f"%{query}%"),
        AllVideo.country.ilike(f"%{query}%"),
        AllVideo.description.ilike(f"%{query}%"),
        AllVideo.genres.any(Genre.name.ilike(f"%{query}%")),
        AllVideo.star_cast.ilike(f"%{query}%")

    )
    videos = (
        AllVideo.query.options(joinedload(AllVideo.genres)).filter(search_filter, AllVideo.active.is_(True)).order_by(
            AllVideo.date_added.desc()
        ).paginate(page=page, per_page=per_page, error_out=False)
    )
    series_trend = AllVideo.query.filter_by(trending=True, type="series").order_by(AllVideo.date_added.desc()).limit(6).all()
    movie_trend = AllVideo.query.filter_by(trending=True, type="movie").order_by(AllVideo.date_added.desc()).limit(6).all()
    trending_trailers = Trailer.query.order_by(Trailer.views.desc()).limit(5).all()
    searches = True
    return render_template("search_results.html", trending_trailers=trending_trailers, videos=videos, query=query, searches=searches, trending_series=series_trend, trending_movie=movie_trend)

@main_bp.route("/contact_us")
def contact_us():
    series_trend = AllVideo.query.filter_by(trending=True, type="series").order_by(AllVideo.date_added.desc()).limit(6).all()
    movie_trend = AllVideo.query.filter_by(trending=True, type="movie").order_by(AllVideo.date_added.desc()).limit(6).all()
    trending_trailers = Trailer.query.order_by(Trailer.views.desc()).limit(5).all()
    return render_template("contact_us.html", trending_series=series_trend, trending_movie=movie_trend, trending_trailers=trending_trailers)

@main_bp.route("/privacy_policy")
def privacy():
    series_trend = AllVideo.query.filter_by(trending=True, type="series").order_by(AllVideo.date_added.desc()).limit(6).all()
    movie_trend = AllVideo.query.filter_by(trending=True, type="movie").order_by(AllVideo.date_added.desc()).limit(6).all()
    trending_trailers = Trailer.query.order_by(Trailer.views.desc()).limit(5).all()
    return render_template("privacy_policy.html", trending_series=series_trend, trending_movie=movie_trend, trending_trailers=trending_trailers)

@main_bp.route("/dcma")
def dcma():
    series_trend = AllVideo.query.filter_by(trending=True, type="series").order_by(AllVideo.date_added.desc()).limit(6).all()
    movie_trend = AllVideo.query.filter_by(trending=True, type="movie").order_by(AllVideo.date_added.desc()).limit(6).all()
    trending_trailers = Trailer.query.order_by(Trailer.views.desc()).limit(5).all()
    return render_template("dcma.html", trending_series=series_trend, trending_movie=movie_trend, trending_trailers=trending_trailers)

@main_bp.route("/genre/<string:genre_type>")
@main_bp.route("/genre/<string:genre_type>/page/<int:page>")
def genre(genre_type, page):
    per_page = 24
    genre = ""
    if genre_type == "Sci-Fi":
        genre = Genre.query.filter_by(name="Science Fiction").first_or_404()
        videos = (
            AllVideo.query.join(AllVideo.genres).filter(Genre.name == "Science Fiction").paginate(page=page, per_page=per_page)
        )
    else:
        genre = Genre.query.filter_by(name=genre_type).first_or_404()
        videos = (
            AllVideo.query.join(AllVideo.genres).filter(Genre.name == genre_type).paginate(page=page, per_page=per_page)
        )

    series_trend = AllVideo.query.filter_by(trending=True, type="series").order_by(AllVideo.date_added.desc()).limit(6).all()
    movie_trend = AllVideo.query.filter_by(trending=True, type="movie").order_by(AllVideo.date_added.desc()).limit(6).all()
    trending_trailers = Trailer.query.order_by(Trailer.views.desc()).limit(5).all()
    
    return render_template("genre.html", genre_type=genre_type, genre=genre, videos=videos, trending_series=series_trend, trending_movie=movie_trend, trending_trailers=trending_trailers)

@main_bp.route("/<det>/<name>/<int:id>")
@main_bp.route("/<det>/<name>/<int:id>/<int:season>/<int:episode>")
def detail(det, name, id, season=1, episode=1):
    
    if det == "movie":
        return redirect(url_for("main.movie_details", det=det, name=name, id=id))
        print("hello")
    elif det == "series":
        return redirect(url_for("main.series_details", det=det, name=name, season=season, episode=episode, id=id))
    elif det == "trailer_watch":
        return redirect(url_for("main.watch_trailer", det=det, name=name))

@main_bp.route("/download/<det>/<name>/<int:id>")
def movie_details(det, name, id):
    movie = AllVideo.query.get_or_404(id)
    num_comment = Comment.query.filter_by(
        video_id=movie.id,
        parent_id=None
    ).count()
    comments = Comment.query.filter_by(video_id=movie.id, parent_id=None).order_by(Comment.date_added.desc()).all()    
    series_trend = AllVideo.query.filter_by(trending=True, type="series").order_by(AllVideo.date_added.desc()).limit(6).all()
    movie_trend = AllVideo.query.filter_by(trending=True, type="movie").order_by(AllVideo.date_added.desc()).limit(6).all()
    trending_trailers = Trailer.query.order_by(Trailer.views.desc()).limit(5).all()
    genre_ids=[g.id for g in movie.genres]
    suggested = AllVideo.query.options(defer(AllVideo.video_qualities)).join(AllVideo.genres).filter(Genre.id.in_(genre_ids), AllVideo.id != id).distinct().limit(6).all()

    # Optional: prepare breakdown for template
    breakdown = {i: db.session.query(func.count(Rating.id))
                     .filter(Rating.video_id==movie.id, Rating.rating==i)
                     .scalar() for i in range(1,6)}

    more_needed=0
    if len(suggested) < 6:
        more_needed = 6 - len(suggested)

    extra = AllVideo.query.filter(AllVideo.id!=id, ~AllVideo.id.in_([m.id for m in suggested])).order_by(func.random()).limit(more_needed).all()
    suggested.extend(extra)
    return render_template("movie.html", num_comment=num_comment, comments=comments, id=id, det=det, breakdown=breakdown, suggested=suggested, video=movie, trending_series=series_trend, trending_movie=movie_trend, trending_trailers=trending_trailers)

@main_bp.route("/download/<det>/<name>/s<int:season>/e<int:episode>/<int:id>")
def series_details(det, name, season, episode, id):
    print(id)
    series = AllVideo.query.get_or_404(id)

    # 2. Ensure it is a series
    if not series.series:
        return "This is not a series", 404

    serie = series.series

    # 3. Get all seasons
    seasons = serie.seasons

    # 4. Get the requested season
    current_season = Season.query.filter_by(
        series_id=serie.id,
        season_number=season
    ).first_or_404()

    # 5. Get the requested episode
    current_episode = Episode.query.filter_by(
        season_id=current_season.id,
        episode_number=episode
    ).first_or_404()
    num_comment = Comment.query.filter_by(
        video_id=series.id,
        parent_id=None
    ).count()
    comments = Comment.query.filter_by(video_id=series.id, parent_id=None).order_by(Comment.date_added.desc()).all()    
    series_trend = AllVideo.query.filter_by(trending=True, type="series").order_by(AllVideo.date_added.desc()).limit(6).all()
    movie_trend = AllVideo.query.filter_by(trending=True, type="movie").order_by(AllVideo.date_added.desc()).limit(6).all()
    trending_trailers = Trailer.query.order_by(Trailer.views.desc()).limit(5).all()
    genre_ids=[g.id for g in series.genres]
    suggested = AllVideo.query.options(defer(AllVideo.video_qualities)).join(AllVideo.genres).filter(Genre.id.in_(genre_ids), AllVideo.id != id, AllVideo.type=="series").distinct().limit(6).all()

    # Optional: prepare breakdown for template
    breakdown = {i: db.session.query(func.count(Rating.id))
                     .filter(Rating.video_id==series.id, Rating.rating==i)
                     .scalar() for i in range(1,6)}

    more_needed=0
    if len(suggested) < 6:
        more_needed = 6 - len(suggested)

    extra = AllVideo.query.filter(AllVideo.id!=id, ~AllVideo.id.in_([m.id for m in suggested])).order_by(func.random()).limit(more_needed).all()
    suggested.extend(extra)
    return render_template("movie.html", num_comment=num_comment, current_season=current_season, current_episode=current_episode, comments=comments, season=int(season), seasons=seasons, breakdown=breakdown, episode=episode, det=det, suggested=suggested, video=series, trending_series=series_trend, trending_movie=movie_trend, trending_trailers=trending_trailers)

@main_bp.route("/download/<type>/<int:id>")
@main_bp.route("/download/<type>/<int:id>/<int:season>/<int:episode>")
def download_dispatcher(type, id, season=None, episode=None):
    """
    Dispatcher: Checks Server Type.
    - If Bytescale: Redirects to the special proxy route.
    - If Standard: Redirects directly to the file URL.
    """

    # --- 1. Fetch Video & Server ---
    if type == "movie":
        video = AllVideo.query.get_or_404(id)
        # Use the name from the DB for the user's saved file
        clean_name = video.name 
    elif type == "series":
        video = Episode.query.get_or_404(id)
        clean_name = f"{video.season.series.all_video.name}_S{season}E{episode}"
    else:
        return "Invalid type", 400

    storage_server = video.storage_server

    # Check if server exists
    if not storage_server or not storage_server.active:
        return "Storage server not found or inactive", 404
    
    # Check if filename exists
    if not video.download_link:
         return "File not linked in database", 404

    # --- 2. LOGIC BRANCH ---
    
    # BRANCH A: BYTESCALE (Needs Proxy/API work)
    if storage_server.server_type == "bytescale":
        if type == "movie":
            return redirect(url_for("main.movie_start_download", type="movie", name=clean_name, id=id))
        else:
            return redirect(url_for("main.movie_start_download", type="series", name=clean_name, id=id, season=season, episode=episode))

    # BRANCH B: STANDARD SERVERS (AWS S3, Local, FTP, etc.)
    # We just build the link and redirect the user directly.
    else:
        # Build the URL: Base + Filename
        base = storage_server.base_url.rstrip('/')
        path = video.download_link.lstrip('/')
        final_url = f"{base}/{path}"
        
        print(f"Direct Redirect to: {final_url}")
        return redirect(final_url)



CHUNK_SIZE = 1024 * 1024  # 1 MB

@main_bp.route("/<type>/<name>/<int:id>/start")
@main_bp.route("/<type>/<name>/<int:id>/<season>/<episode>/start")
def movie_start_download(type, name, id, season=None, episode=None):
    """
    Specific Route for Bytescale Proxying.
    We only come here if the Dispatcher sent us.
    """
    
    # --- 1. Fetch Video ---
    if type == "movie":
        video = AllVideo.query.get_or_404(id)
        clean_name = video.name
    else:
        video = Episode.query.get_or_404(id)
        clean_name = f"{video.season.series.all_video.name}_S{season}E{episode}"

    # --- 2. Construct Filename for User Download ---
    filename_in_db = video.download_link
    root, ext = os.path.splitext(filename_in_db)
    if not ext: ext = ".mp4"
    
    output_filename = secure_filename(f"{clean_name}{ext}")

    # --- 3. Build The Source Link ---
    base = video.storage_server.base_url.rstrip('/')
    path = filename_in_db.lstrip('/')
    source_url = f"{base}/{path}"
    direct_url = source_url # Default if API fails

    # --- 4. BYTESCALE API LOGIC ---
    try:
        api_key = video.storage_server.api_key
        # Fallback to app config if server key is missing
        if not api_key:
            api_key = current_app.config.get("BYTESCALE_API_KEY")

        if api_key:
            headers_api = {"Authorization": f"Bearer {api_key}"}
            # Generate a temporary download URL from Bytescale
            resp = requests.post(
                "https://api.bytescale.com/v1/files/generate_download_url",
                json={"url": source_url},
                headers=headers_api,
                timeout=10
            )
            if resp.status_code == 200:
                direct_url = resp.json().get("download_url", source_url)
                print("Using Bytescale Generated URL")
    except Exception as e:
        print(f"Bytescale API Error: {e}")

    # --- 5. PROXY STREAMING ---
    # We stream the data so we can force the filename header
    
    try:
        head = requests.head(direct_url, allow_redirects=True, timeout=10)
        total_size = int(head.headers.get("Content-Length", 0))
    except:
        total_size = 0

    range_header = request.headers.get("Range", None)
    start = 0
    end = total_size - 1 if total_size > 0 else 0
    status_code = 200

    if range_header and total_size > 0:
        try:
            range_val = range_header.strip().split("=")[1]
            start = int(range_val.split("-")[0])
            if "-" in range_val and range_val.split("-")[1]:
                 end_val = int(range_val.split("-")[1])
                 if end_val < total_size:
                     end = end_val
            status_code = 206
        except:
            start = 0

    headers = {
        "Content-Type": "application/octet-stream",
        "Content-Disposition": f'attachment; filename="{output_filename}"',
        "Accept-Ranges": "bytes",
        "Content-Length": str(end - start + 1)
    }
    if status_code == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{total_size}"

    def generate():
        try:
            with requests.get(
                direct_url,
                stream=True,
                headers={"Range": f"bytes={start}-{end}"},
                timeout=15
            ) as r:
                r.raise_for_status()
                for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                    yield chunk
        except Exception as e:
            print(f"Stream broken: {e}")

    return Response(stream_with_context(generate()), status=status_code, headers=headers)

@main_bp.route("/trailers/<string:det>/<string:name>")
def watch_trailer(det="trailer_watch", name=None):
    dark = True

    trailer = Trailer.query.filter_by(slug=name).first_or_404()
    up_next = get_up_next(trailer)
    trending_trailers = Trailer.query.order_by(Trailer.views.desc()).limit(5).all()

    # Count only top-level
    num_comment = Comment.query.filter_by(
        trailer_id=trailer.id,
        parent_id=None
    ).count()

    # Increase views
    trailer.views += 1
    db.session.commit()

    # Load only main comments (NO replies)
    comments = Comment.query.filter_by(
        trailer_id=trailer.id,
        parent_id=None
    ).order_by(Comment.date_added.desc()).all()

    return render_template(
        f"{det}.html",
        trailer=trailer,
        comments=comments,
        dark=dark,
        up_next=up_next,
        num_comment=num_comment,
        trending_trailers=trending_trailers
    )


@main_bp.route("/trending/<type>")
def trending(type):
    series_trend = AllVideo.query.filter_by(trending=True, type="series").limit(10).all()
    movie_trend = AllVideo.query.filter_by(trending=True, type="movie").limit(10).all()
    trending_action = AllVideo.query.join(AllVideo.genres).filter(AllVideo.type == "movie", AllVideo.trending==True, Genre.name=="Action").order_by(AllVideo.date_added.desc()).limit(10).all()
    trending_animation = AllVideo.query.join(AllVideo.genres).filter(AllVideo.trending == True, Genre.name=="Animation").order_by(AllVideo.date_added.desc()).limit(10).all()
    trending_sci_fi = AllVideo.query.join(AllVideo.genres).filter(AllVideo.trending == True, Genre.name=="Science Fiction").order_by(AllVideo.date_added.desc()).limit(10).all()
    old_but_gold = AllVideo.query.filter(
        AllVideo.type == "movie",
        AllVideo.year_produced <= 2020,
        AllVideo.rating >= 4  # or views >= 10000
    ).order_by(AllVideo.rating.desc()).limit(10).all()
        

    get_started_items = (
        AllVideo.query
            .filter(
                or_(
                    # Movies: short length
                    (AllVideo.type == "movie") & (AllVideo.length <= "1h 59m"),

                    # Series: few seasons (you could store num_seasons on AllVideo if you want)
                    (AllVideo.type == "series") & (AllVideo.series.has(Series.num_seasons <= 2))
                )
            )
            .order_by(AllVideo.views.desc())  # popular first
            .limit(10)
            .all()
    )
    return render_template(f"trending.html", old_but_gold=old_but_gold, get_started_items=get_started_items, trending_series=series_trend, trending_movie=movie_trend, trending_actions=trending_action, trending_animations=trending_animation, trending_sci_fic=trending_sci_fi)

@main_bp.route("/trailers")
@main_bp.route("/trailers/<int:page>")
def trailer(page=1):
    dark = True
    trending_trailers = Trailer.query.order_by(Trailer.views.desc()).limit(5).all()
    trailers = True
    per_page = 24
    videos = Trailer.query.order_by(Trailer.date_added.desc()).paginate(page=page, per_page=per_page)
    return render_template("trailers.html", dark=dark, videos=videos, per_page=per_page, page=page, trailers=trailers, trending_trailers=trending_trailers)


@main_bp.route("/watch_download/<type>/<name>/<int:id>")
@main_bp.route("/watch_download/<type>/<name>/<int:id>/<season>/<episode>")
def movie_stream_download(type, name, id, season=None, episode=None):
    

    if type == "movie":
        video = AllVideo.query.get_or_404(id)
    else:
        video = Episode.query.get_or_404(id)

    # Choose best default quality (prioritize 720p > 1080p > 480p > 360p)
    for q in ["720p", "1080p", "480p", "360p"]:
        if getattr(video, f"video_{q}", None):
            default_quality = q
            break
    else:
        default_quality = None  # No video available

    if not default_quality:
        return "No available video for streaming", 404
    
    if type == "movie":
        return redirect(url_for("main.movie_download", type=type, id=id, name=name, quality=default_quality))
    else:
        return redirect(url_for("main.series_download", type=type, name=name, id=id, season=season, episode=episode))

@main_bp.route("/watch_movie/<type>/<name>/<int:id>")
def movie_download(type, name, id):
    series_trend = AllVideo.query.filter_by(trending=True, type="series").order_by(AllVideo.date_added.desc()).limit(6).all()
    movie_trend = AllVideo.query.filter_by(trending=True, type="movie").order_by(AllVideo.date_added.desc()).limit(6).all()
    trending_trailers = Trailer.query.order_by(Trailer.views.desc()).limit(5).all()
    movie = AllVideo.query.get_or_404(id)

    # Get the best available quality

    
    genre_ids=[g.id for g in movie.genres]
    suggested = AllVideo.query.options(defer(AllVideo.video_qualities)).join(AllVideo.genres).filter(Genre.id.in_(genre_ids), AllVideo.id != id).distinct().limit(6).all()

    more_needed = max(0, 6 - len(suggested))
    if more_needed:
        extra = AllVideo.query.filter(AllVideo.id != id, ~AllVideo.id.in_([m.id for m in suggested]))\
            .order_by(func.random()).limit(more_needed).all()
        suggested.extend(extra)
    return render_template("stream.html", video=movie, suggested=suggested, id=id, type=type, trending_series=series_trend, trending_movie=movie_trend, trending_trailers=trending_trailers)


@main_bp.route("/watch_series/<type>/<name>/<int:id>/s<season>/e<int:episode>")
def series_download(type, name, id, season, episode):
    ep = Episode.query.get_or_404(id)
    

    # Trending lists
    series_trend = AllVideo.query.filter_by(trending=True, type="series").order_by(AllVideo.date_added.desc()).limit(6).all()
    movie_trend = AllVideo.query.filter_by(trending=True, type="movie").order_by(AllVideo.date_added.desc()).limit(6).all()
    trending_trailers = Trailer.query.order_by(Trailer.views.desc()).limit(5).all()
    qualities = ep.video_qualities or {}
    return render_template(
        "stream_download.html",
        video=ep,
        qualities=qualities,
        type=type,
        season=int(season),
        episode=int(episode),
        trending_series=series_trend,
        trending_movie=movie_trend,
        trending_trailers=trending_trailers
    )

@main_bp.route("/nav/<nav>")
@main_bp.route("/nav/<nav>/<int:page>")
def navbar(nav, page=1):
    dark = False
    videos = ""
    per_page = 24
    series_trend = AllVideo.query.filter_by(trending=True, type="series").order_by(AllVideo.date_added.desc()).limit(6).all()
    movie_trend = AllVideo.query.filter_by(trending=True, type="movie").order_by(AllVideo.date_added.desc()).limit(6).all()
    trending_trailers = Trailer.query.order_by(Trailer.views.desc()).limit(5).all()
    trending_action = ""
    trending_animation = ""
    trending_sci_fi = ""
    old_but_gold = ""
    get_started_items = ""
    trailers = False
    if nav=="trailers":
        dark = True
        trailers = True
        videos = Trailer.query.order_by(Trailer.date_added.desc()).paginate(page=page, per_page=per_page)
    if nav=="trending":
        series_trend = AllVideo.query.filter_by(trending=True, type="series").limit(10).all()
        movie_trend = AllVideo.query.filter_by(trending=True, type="movie").limit(10).all()
        trending_action = AllVideo.query.join(AllVideo.genres).filter(AllVideo.type == "movie", AllVideo.trending==True, Genre.name=="Action").order_by(AllVideo.date_added.desc()).limit(10).all()
        trending_animation = AllVideo.query.join(AllVideo.genres).filter(AllVideo.trending == True, Genre.name=="Animation").order_by(AllVideo.date_added.desc()).limit(10).all()
        trending_sci_fi = AllVideo.query.join(AllVideo.genres).filter(AllVideo.trending == True, Genre.name=="Science Fiction").order_by(AllVideo.date_added.desc()).limit(10).all()
        old_but_gold = AllVideo.query.filter(
            AllVideo.type == "movie",
            AllVideo.year_produced <= 2020,
            AllVideo.rating >= 4  # or views >= 10000
        ).order_by(AllVideo.rating.desc()).limit(10).all()
        

        get_started_items = (
            AllVideo.query
                .filter(
                    or_(
                        # Movies: short length
                        (AllVideo.type == "movie") & (AllVideo.length <= "1h 59m"),

                        # Series: few seasons (you could store num_seasons on AllVideo if you want)
                        (AllVideo.type == "series") & (AllVideo.series.has(Series.num_seasons <= 2))
                    )
                )
                .order_by(AllVideo.views.desc())  # popular first
                .limit(10)
                .all()
        )

    if nav == "all_movie":
        videos = AllVideo.query.filter_by(type="movie").order_by(AllVideo.date_added.desc()).paginate(page=page, per_page=per_page)
    if nav == "all_series":
        videos = AllVideo.query.filter_by(type="series").order_by(AllVideo.date_added.desc()).paginate(page=page, per_page=per_page)
    
    return render_template(f"{nav}.html", trailers=trailers, dark=dark, nav=nav, videos=videos, old_but_gold=old_but_gold, get_started_items=get_started_items, trending_series=series_trend, trending_movie=movie_trend, trending_actions=trending_action, trending_animations=trending_animation, trending_sci_fic=trending_sci_fi, trending_trailers=trending_trailers)


@main_bp.route('/rate/<int:video_id>', methods=['POST'])
def rate_video(video_id):
    video = AllVideo.query.get_or_404(video_id)
    ip_address = request.remote_addr
    data = request.get_json()
    new_rating = int(data.get('rating', 0))

    if new_rating < 1 or new_rating > 5:
        return jsonify({'error': 'Invalid rating'}), 400

    # Check if this IP already rated
    existing = Rating.query.filter_by(video_id=video.id, ip_address=ip_address).first()
    if existing:
        existing.rating = new_rating  # UPDATE rating if IP exists
    else:
        rating = Rating(video_id=video.id, ip_address=ip_address, rating=new_rating)
        db.session.add(rating)

    db.session.commit()

    # Recalculate average rating
    avg = db.session.query(func.avg(Rating.rating)).filter(Rating.video_id == video.id).scalar()
    count = db.session.query(func.count(Rating.id)).filter(Rating.video_id == video.id).scalar()

    video.rating = round(avg, 2)
    video.num_votes = count
    db.session.commit()

    # Rating breakdown
    breakdown = {}
    for i in range(1, 6):
        breakdown[i] = db.session.query(func.count(Rating.id)).filter(Rating.video_id == video.id, Rating.rating == i).scalar()

    return jsonify({
        'average_rating': video.rating,
        'num_votes': video.num_votes,
        'breakdown': breakdown
    })  

@main_bp.route('/comment/add/<int:video_id>', methods=['POST'])
@main_bp.route('/comment/add/<int:video_id>/<string:type>', methods=['POST'])
def add_comment(video_id, type="video"):
    name = request.form.get('name')
    email = request.form.get('email')
    text = request.form.get('text')

    # Basic Validation
    if not all([name, email, text]):
        return jsonify({'success': False, 'error': 'All fields required'}), 400

    video_obj = None
    comment = None

    if type == "trailer":
        # 1. Create Comment
        comment = Comment(
            trailer_id=video_id,
            name=name,
            email=email,
            text=text,
            parent_id=None
        )
        # 2. Get Video Object
        video_obj = Trailer.query.get_or_404(video_id)
        # 3. Update Count (Incrementing is faster than counting all rows every time)
        video_obj.total_comment = (video_obj.total_comment or 0) + 1

    else: # Default to "video" (Movie/Series)
        comment = Comment(
            video_id=video_id,
            name=name,
            email=email,
            text=text,
            parent_id=None
        )
        video_obj = AllVideo.query.get_or_404(video_id)
        video_obj.total_comment = (video_obj.total_comment or 0) + 1

    # 4. Single Commit for everything
    try:
        db.session.add(comment)
        db.session.add(video_obj) # Ensure video update is tracked
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

    if type == 'trailer':
        # dark_comments.html expects 'trailer', not 'video'
        html = render_template('dark_comments.html', comment=comment, trailer=video_obj)
    else:
        # comments.html expects 'video'
        html = render_template('comments.html', comment=comment, video=video_obj)
    return jsonify({'success': True, 'html': html})


@main_bp.route('/comment/reply/<int:video_id>', methods=['POST'])
@main_bp.route('/comment/reply/<int:video_id>/<string:type>', methods=['POST'])
def reply_comment(video_id, type="video"):
    name = request.form.get('name')
    email = request.form.get('email')
    text = request.form.get('text')
    parent_id = request.form.get('parent_id')

    if not all([name, email, text]):
        return jsonify({'success': False, 'error': 'All fields are required'})

    video_obj = None
    reply = None

    if type == "trailer":
        reply = Comment(
            trailer_id=video_id,
            name=name, email=email, text=text,
            parent_id=parent_id if parent_id else None
        )
        video_obj = Trailer.query.get_or_404(video_id)
    else:
        reply = Comment(
            video_id=video_id,
            name=name, email=email, text=text,
            parent_id=parent_id if parent_id else None
        )
        video_obj = AllVideo.query.get_or_404(video_id)

    db.session.add(reply)
    db.session.commit()

    # 👇 THIS IS THE FIX 👇
    if type == 'trailer':
        html = render_template('dark_comments.html', comment=reply, trailer=video_obj)
    else:
        html = render_template('comments.html', comment=reply, video=video_obj)
    
    return jsonify({'success': True, 'html': html})

@main_bp.route("/admin/uploads")
def admin_uploads():
    # # Only allow admins
    # if not current_user.is_admin:
    #     return redirect(url_for('index'))

    # Get all videos and episodes
    movies = AllVideo.query.order_by(AllVideo.id.desc()).all()
    episodes = Episode.query.order_by(Episode.id.desc()).all()

    return render_template("download.html", movies=movies, episodes=episodes)

@main_bp.route('/sitemap.xml')
def sitemap():
    """
    Dynamic Sitemap: Generates XML on the fly.
    Always up to date with DB. No file saving required.
    """
    host = "https://www.maxcinema.name.ng"

    # 1. Define Static Pages
    static_urls = [
        {'loc': f"{host}/"},
        {'loc': f"{host}/trending/movie"},
        {'loc': f"{host}/trending/series"},
        {'loc': f"{host}/request/movie"},
    ]

    # 2. Fetch Data (Limit to recent 2000 to keep it fast)
    # If you have < 2000 movies, .limit() does nothing, which is fine.
    movies = AllVideo.query.filter_by(type='movie').order_by(AllVideo.date_added.desc()).limit(2000).all()
    series_list = AllVideo.query.filter_by(type='series').order_by(AllVideo.date_added.desc()).limit(1000).all()
    trailers = Trailer.query.order_by(Trailer.date_added.desc()).limit(500).all()

    # 3. Render Template
    xml_content = render_template(
        'sitemap.xml',
        host=host, 
        static_urls=static_urls,
        movies=movies,
        series_list=series_list,
        trailers=trailers
    )
    
    # 4. Return as correct XML type
    response = make_response(xml_content)
    response.headers["Content-Type"] = "application/xml"
    return response

@main_bp.route("/sitemap")
def sitemap_page():
    # 1. Fetch Movies
    movies = AllVideo.query.filter_by(type="movie").order_by(AllVideo.date_added.desc()).all()

    # 2. Fetch Series (This returns a list of AllVideo objects)
    series_list = AllVideo.query.filter_by(type="series").order_by(AllVideo.date_added.desc()).all()

    # 3. Fetch Trailers
    trailers = Trailer.query.order_by(Trailer.date_added.desc()).all()

    return render_template("sitemap.html",
                           movies=movies,
                           series_list=series_list,
                           trailers=trailers)


@main_bp.route('/request/movie', methods=['POST'])
def request_movie():
    name = request.form.get('name')
    email = request.form.get('email')
    movie_name = request.form.get('movie_name')
    description = request.form.get('description')

    # Basic Validation
    if not all([name, email, movie_name]):
        return jsonify({'success': False, 'error': 'Name, Email, and Movie Name are required'}), 400

    new_request = MovieRequest(
        name=name,
        email=email,
        movie_name=movie_name,
        description=description,
        status='Pending'
    )

    try:
        db.session.add(new_request)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Request submitted successfully!'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500



@main_bp.route('/live_search')
def live_search():
    """
    Returns the top 5 matches as JSON for the dropdown.
    """
    query = request.args.get("q", "").strip()
    
    # If empty, return nothing
    if not query or len(query) < 2:
        return jsonify([])

    # Search Logic (Same as your main search, but simpler/faster)
    search_filter = or_(
        AllVideo.name.ilike(f"%{query}%"),
        AllVideo.star_cast.ilike(f"%{query}%")
    )
    
    # Only get Top 5, and only fetch columns we need (optimization)
    results = AllVideo.query.filter(search_filter, AllVideo.active.is_(True))\
              .order_by(AllVideo.views.desc())\
              .limit(5).all()

    # Convert database objects to a simple JSON list
    suggestions = []
    for video in results:
        suggestions.append({
            "name": video.name,
            "image": video.image, # Ensure you have this column or use a placeholder
            "year": video.date_added.year,
            "url": url_for('main.detail', det=video.type, name=video.slug, id=video.id, _external=True)
        })

    return jsonify(suggestions)


@main_bp.route('/ping')
def ping():
    try:
        # 1. Try to wake the DB with a tiny, zero-cost query
        db.session.execute(text("SELECT 1"))
        return "OK (DB Awake)", 200
    except Exception as e:
        # 2. If Neon is sleeping or erroring, CATCH the error.
        # Do not let the app crash.
        print(f"Ping managed a DB Error: {e}")
        
        # 3. CRITICAL: Rollback the session so the NEXT user doesn't get an error
        db.session.rollback()
        
        # 4. Return OK anyway so Cron Job doesn't get red alerts
        return "OK (DB Reset)", 200


# # ---------------- Dashboard ----------------
# @main_bp.route("/admin")
# @login_required
# @admin_required
# def admin_dashboard():
#     movies_count = AllVideo.query.filter_by(type="movie").count()
#     series_count = Series.query.count()
#     episodes_count = Episode.query.count()
#     genres_count = Genre.query.count()
#     servers_count = StorageServer.query.count()
#     return render_template("admin/dashboard.html",
#                            movies_count=movies_count,
#                            series_count=series_count,
#                            episodes_count=episodes_count,
#                            genres_count=genres_count,
#                            servers_count=servers_count)



# if __name__ == '__main__':
#     with app.app_context():
#         db.create_all()
        # video = Episode.query.all()
        # d = AllVideo.query.get_or_404(1).date_added
        # for v in video:
        #     v.date_added = d
        #     db.session.commit()
        
        # edit = Series.query.get(9)
        # edit.seasons[-1].completed = True
        # db.session.commit()
        # safe_populate()
        
        
        # for movie in AllVideo.query.limit(60).all():
        #     movie.download_link = "https://upcdn.io/W23MTTR/raw/Mr%20Beast%E2%80%99s%20insane%20%241%20million%20challenge.mp4"
        # db.session.commit()

        # # For Episode
        # for ep in Episode.query.all():
        #     ep.update_video_qualities()
        # db.session.commit()
        # videos = AllVideo.query.all()
        # for video in videos:
        #     if not video.slug:
        #         video.slug = slugify(video.name)
        # db.session.commit()
        # generate_sitemap()
        # existing = StorageServer.query.filter_by(name="Bytescale").first()
        # if not existing:
        #     bytescale_server = StorageServer(
        #         name="Bytescale",
        #         server_type="bytescale",
        #         active=True
        #     )
        #     db.session.add(bytescale_server)
        #     db.session.commit()
        #     print("Bytescale storage server added successfully.")
        # else:
        #     print("Bytescale storage server already exists.")

        # Get Bytescale server
        # bytescale_server = StorageServer.query.filter_by(name="Bytescale").first()
        # if not bytescale_server:
        #     raise ValueError("Bytescale server not found. Add it first.")

        # # Update all movies
        # AllVideo.query.update({AllVideo.storage_server_id: bytescale_server.id})

        # # Update all episodes
        # Episode.query.update({Episode.storage_server_id: bytescale_server.id})

        # # Commit changes
        # db.session.commit()

        # print("All videos and episodes assigned to Bytescale server.")

        # video = AllVideo.query.get(60)

        # if video:
        #     # Delete related Ratings
        #     Rating.query.filter_by(video_id=video.id).delete()

        #     # Delete related Comments
        #     Comment.query.filter_by(video_id=video.id).delete()

        #     # Remove from VideoGenre association table
        #     video.genres = []

        #     # Delete associated Movie or Series objects
        #     if video.movie:
        #         db.session.delete(video.movie)
        #     if video.series:
        #         # Delete all seasons and episodes via cascade
        #         db.session.delete(video.series)

        #     # Delete from RecentItem if it exists
        #     RecentItem.query.filter_by(video_id=video.id).delete()

        #     # Finally, delete the video
        #     db.session.delete(video)

        #     try:
        #         db.session.commit()
        #         print("AllVideo with id 60 deleted successfully!")
        #     except Exception as e:
        #         db.session.rollback()
        #         print("Error deleting video:", e)
        # else:
        #     print("Video not found.")
        

    # app.run(debug=True, host="0.0.0.0", port=5000)