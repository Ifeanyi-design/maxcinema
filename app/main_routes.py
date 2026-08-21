from flask import Blueprint, make_response, render_template, abort, redirect, url_for, flash, request, jsonify, current_app, Response, stream_with_context, session
from flask_login import current_user, login_user, logout_user, login_required
from sqlalchemy.sql import func
from sqlalchemy.orm import joinedload, defer
from sqlalchemy import or_, text, desc
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import random

import os
import time
import requests
from datetime import datetime, timedelta
from functools import wraps
from slugify import slugify
import hashlib
from . import listeners
from .extensions import db, login_manager
from .indexnow import get_indexnow_key_record, get_site_base_url
from .models import (
    AllVideo, Movie, Series, StorageServer, User, Season, Episode,
    Genre, RecentItem, Rating, Comment, Trailer, MovieRequest, SearchTerm, AnalyticsEvent,
    WatchlistNotify, WeeklyPoll, WeeklyPollOption, WeeklyPollVote, CourseLead, SocialVideo
)

main_bp = Blueprint("main", __name__)

# Simple in-memory cache for sidebar data (5 minute TTL)
_sidebar_cache = {"data": None, "timestamp": 0}
_SIDEBAR_CACHE_TTL = 300  # 5 minutes


# # ---------------- Admin Required ----------------
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

# @login_manager.user_loader
# def load_user(user_id):
#     return User.query.get(int(user_id))

def get_sidebar_data_safe():
    now = time.time()
    if _sidebar_cache["data"] and (now - _sidebar_cache["timestamp"]) < _SIDEBAR_CACHE_TTL:
        return _sidebar_cache["data"]
    try:
        series_trend = AllVideo.query.filter_by(
            trending=True, type="series", active=True
        ).order_by(AllVideo.views.desc()).limit(6).all()

        movie_trend = AllVideo.query.filter_by(
            trending=True, type="movie", active=True
        ).order_by(AllVideo.views.desc()).limit(6).all()

        trending_trailers = Trailer.query.order_by(
            Trailer.views.desc()
        ).limit(5).all()

        result = series_trend, movie_trend, trending_trailers
        _sidebar_cache["data"] = result
        _sidebar_cache["timestamp"] = now
        return result
    except Exception as e:
        db.session.rollback()
        print(f"Sidebar load failed: {e}")
        return [], [], []

@main_bp.app_errorhandler(404)
def page_not_found(e):
    series_trend, movie_trend, trending_trailers = get_sidebar_data_safe()
    return render_template(
        "404.html",
        trending_series=series_trend,
        trending_movie=movie_trend,
        trending_trailers=trending_trailers
    ), 404


@main_bp.app_errorhandler(500)
def internal_server_error(e):
    series_trend, movie_trend, trending_trailers = get_sidebar_data_safe()
    return render_template(
        "500.html",
        trending_series=series_trend,
        trending_movie=movie_trend,
        trending_trailers=trending_trailers
    ), 500


@main_bp.app_errorhandler(403)
def access_forbidden(e):
    series_trend, movie_trend, trending_trailers = get_sidebar_data_safe()
    return render_template(
        "403.html",
        trending_series=series_trend,
        trending_movie=movie_trend,
        trending_trailers=trending_trailers
    ), 403

@main_bp.context_processor
def inject_now():
    # Nigeria is UTC + 1
    nigeria_time = datetime.utcnow() + timedelta(hours=1) 
    return {'now': nigeria_time}

    
def ping_search_engines():
    sitemap_url = f"{get_site_base_url()}/sitemap.xml"
    try:
        requests.get(f"http://www.google.com/ping?sitemap={sitemap_url}")
        requests.get(f"http://www.bing.com/ping?sitemap={sitemap_url}")
        print("Search engines notified!")
    except Exception as e:
        print("Ping failed:", e)


@main_bp.route("/robots.txt")
def robots_txt():
    body = "\n".join([
        "User-agent: *",
        "Allow: /",
        f"Sitemap: {get_site_base_url()}/sitemap.xml",
    ])
    response = make_response(body)
    response.headers["Content-Type"] = "text/plain; charset=utf-8"
    return response


@main_bp.route("/<string:key>.txt")
def indexnow_key_file(key):
    record = get_indexnow_key_record()
    if not record or record["key"] != key:
        abort(404)

    response = make_response(record["content"])
    response.headers["Content-Type"] = "text/plain; charset=utf-8"
    return response

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


def _comment_badge_for_score(score: int):
    if score >= 80:
        return "Legend"
    if score >= 35:
        return "Top Fan"
    if score >= 12:
        return "Contributor"
    if score >= 4:
        return "Rising Voice"
    return None


def build_comment_badges():
    """
    Build badge map keyed by normalized identity (email first, fallback to name).
    Uses both volume and recency to rank active commenters.
    Single query with CASE for recent count to avoid N+1.
    """
    three_months_ago = datetime.utcnow() - timedelta(days=90)
    rows = (
        db.session.query(
            Comment.email,
            func.min(Comment.name),
            func.count(Comment.id),
            func.sum(
                func.cast(
                    (Comment.date_added >= three_months_ago),
                    db.Integer
                )
            )
        )
        .group_by(Comment.email)
        .all()
    )

    badge_map = {}
    for email, any_name, total_count, recent_count in rows:
        identity = (email or any_name or "").strip().lower()
        if not identity:
            continue
        score = int(total_count or 0) + (int(recent_count or 0) * 2)
        badge = _comment_badge_for_score(score)
        if badge:
            badge_map[identity] = badge
    return badge_map


def get_active_poll():
    now_ts = datetime.utcnow()
    try:
        return (
            WeeklyPoll.query
            .filter(
                WeeklyPoll.is_active.is_(True),
                or_(WeeklyPoll.ends_at.is_(None), WeeklyPoll.ends_at >= now_ts)
            )
            .order_by(WeeklyPoll.date_added.desc())
            .first()
        )
    except Exception:
        db.session.rollback()
        return None

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
    today = datetime.utcnow().date()
    features = AllVideo.query.filter_by(featured=True, active=True).order_by(AllVideo.date_added.desc()).limit(8).all()
    series_trend = AllVideo.query.filter_by(trending=True, type="series", active=True).order_by(AllVideo.views.desc()).limit(6).all()
    movie_trend = AllVideo.query.filter_by(trending=True, type="movie", active=True).order_by(AllVideo.views.desc()).limit(6).all()
    trending_trailers = Trailer.query.order_by(Trailer.views.desc()).limit(5).all()
    top_rated_movies = AllVideo.query.filter(AllVideo.num_votes > 0, AllVideo.active == True)\
                                  .order_by(desc(AllVideo.rating))\
                                  .limit(10).all()

    data = AllVideo.query.filter_by(active=True).order_by(func.random()).limit(24).all()
    upcoming_video_rows = (
        AllVideo.query
        .filter(
            AllVideo.active.is_(True),
            AllVideo.coming_soon.is_(True),
            AllVideo.released_date.isnot(None),
            AllVideo.released_date >= today
        )
        .order_by(AllVideo.released_date.asc())
        .limit(20)
        .all()
    )
    upcoming_episode_rows = (
        Episode.query
        .join(Season, Episode.season_id == Season.id)
        .join(Series, Season.series_id == Series.id)
        .join(AllVideo, Series.all_video_id == AllVideo.id)
        .filter(
            AllVideo.active.is_(True),
            Episode.coming_soon.is_(True),
            Episode.released_date.isnot(None),
            Episode.released_date >= today
        )
        .order_by(Episode.released_date.asc())
        .limit(20)
        .all()
    )

    upcoming_titles = []
    for v in upcoming_video_rows:
        upcoming_titles.append({
            "id": v.id,
            "name": v.slug or v.name,
            "title": v.name,
            "type": v.type,
            "badge": v.type,
            "image": v.image,
            "released_date": v.released_date,
            "season": None,
            "episode": None,
        })

    nearest_episode_by_series = {}
    for ep in upcoming_episode_rows:
        season_obj = ep.season
        if not season_obj or not season_obj.series or not season_obj.series.all_video:
            continue
        parent_video = season_obj.series.all_video
        parent_id = parent_video.id
        prev = nearest_episode_by_series.get(parent_id)
        if prev and prev.released_date and ep.released_date and prev.released_date <= ep.released_date:
            continue
        nearest_episode_by_series[parent_id] = ep

    for ep in nearest_episode_by_series.values():
        season_obj = ep.season
        parent_video = season_obj.series.all_video
        season_no = season_obj.season_number
        episode_no = ep.episode_number
        upcoming_titles.append({
            "id": parent_video.id,
            "name": parent_video.slug or parent_video.name,
            "title": f"{parent_video.name} S{season_no}E{episode_no}",
            "type": "series",
            "badge": "Episode",
            "image": season_obj.image or parent_video.image,
            "released_date": ep.released_date,
            "season": season_no,
            "episode": episode_no,
        })

    upcoming_titles = sorted(upcoming_titles, key=lambda x: x["released_date"])[:8]
    active_poll = get_active_poll()
    poll_total_votes = 0
    if active_poll:
        poll_total_votes = sum((opt.votes or 0) for opt in active_poll.options)
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
        videos = {
            v.all_video_id: v for v in Movie.query
            .join(AllVideo)
            .filter(Movie.all_video_id.in_(video_ids), AllVideo.active == True)
            .all()
        }
    else:
        videos = {}
    if episode_ids:
        episodes = {
            e.id: e for e in Episode.query
            .join(Season).join(Series).join(AllVideo)
            .filter(Episode.id.in_(episode_ids), AllVideo.active == True)
            .all()
        }
    else:
        episodes = {}
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
            if e and e.season.series.all_video.name not in series_name:
                series_name.append(e.season.series.all_video.name)
                items.append(e)
    return render_template('index.html', features=features, data=data,
                            trending_series=series_trend,
                              trending_movie=movie_trend,
                                items=items, per_page=per_page,
                                  page=page, total_pages=recent_paginated.pages,
                                  top_rated_movies=top_rated_movies,
                                  videos=recent_paginated, index=index, trending_trailers=trending_trailers,
                                  upcoming_titles=upcoming_titles,
                                  active_poll=active_poll,
                                  poll_total_votes=poll_total_votes)


@main_bp.route("/release-calendar")
def release_calendar():
    today = datetime.utcnow().date()
    start_month = today.replace(day=1)
    next_month = (start_month + timedelta(days=32)).replace(day=1)
    after_next_month = (next_month + timedelta(days=32)).replace(day=1)

    def _calendar_items_between(date_from, date_to, limit=120):
        video_rows = (
            AllVideo.query
            .filter(
                AllVideo.active.is_(True),
                AllVideo.coming_soon.is_(True),
                AllVideo.released_date.isnot(None),
                AllVideo.released_date >= date_from,
                AllVideo.released_date < date_to
            )
            .order_by(AllVideo.released_date.asc())
            .limit(limit)
            .all()
        )
        episode_rows = (
            Episode.query
            .join(Season, Episode.season_id == Season.id)
            .join(Series, Season.series_id == Series.id)
            .join(AllVideo, Series.all_video_id == AllVideo.id)
            .filter(
                AllVideo.active.is_(True),
                Episode.coming_soon.is_(True),
                Episode.released_date.isnot(None),
                Episode.released_date >= date_from,
                Episode.released_date < date_to
            )
            .order_by(Episode.released_date.asc())
            .limit(limit)
            .all()
        )

        merged = []
        for v in video_rows:
            merged.append({
                "id": v.id,
                "name": v.slug or v.name,
                "title": v.name,
                "type": v.type,
                "display_type": (v.type or "").upper(),
                "image": v.image,
                "released_date": v.released_date,
                "season": None,
                "episode": None,
            })

        for ep in episode_rows:
            season_obj = ep.season
            if not season_obj or not season_obj.series or not season_obj.series.all_video:
                continue
            parent_video = season_obj.series.all_video
            season_no = season_obj.season_number
            episode_no = ep.episode_number
            merged.append({
                "id": parent_video.id,
                "name": parent_video.slug or parent_video.name,
                "title": f"{parent_video.name} S{season_no}E{episode_no}",
                "type": "series",
                "display_type": "EPISODE",
                "image": season_obj.image or parent_video.image,
                "released_date": ep.released_date,
                "season": season_no,
                "episode": episode_no,
            })

        merged.sort(key=lambda x: (x["released_date"], x["title"]))
        return merged[:limit]

    current_month_items = _calendar_items_between(start_month, next_month)
    next_month_items = _calendar_items_between(next_month, after_next_month)

    series_trend = AllVideo.query.filter_by(trending=True, type="series", active=True).order_by(AllVideo.views.desc()).limit(6).all()
    movie_trend = AllVideo.query.filter_by(trending=True, type="movie", active=True).order_by(AllVideo.views.desc()).limit(6).all()
    trending_trailers = Trailer.query.order_by(Trailer.views.desc()).limit(5).all()

    return render_template(
        "release_calendar.html",
        current_month_items=current_month_items,
        next_month_items=next_month_items,
        month_label=start_month.strftime("%B %Y"),
        next_month_label=next_month.strftime("%B %Y"),
        trending_series=series_trend,
        trending_movie=movie_trend,
        trending_trailers=trending_trailers
    )

@main_bp.route("/featured/<int:page>")
@main_bp.route("/featured")
def featured(page=1):
    per_page = 24
    feature = True
    series_trend = AllVideo.query.filter_by(trending=True, type="series", active=True).order_by(AllVideo.views.desc()).limit(6).all()
    movie_trend = AllVideo.query.filter_by(trending=True, type="movie", active=True).order_by(AllVideo.views.desc()).limit(6).all()
    trending_trailers = Trailer.query.order_by(Trailer.views.desc()).limit(5).all()
    featured_videos = AllVideo.query.filter_by(featured=True, active=True).order_by(AllVideo.date_added.desc()).paginate(page=page, per_page=per_page)
    return render_template("featured.html", trending_series=series_trend, trending_movie=movie_trend, videos=featured_videos, feature=feature, trending_trailers=trending_trailers)

@main_bp.route("/search_result")
@main_bp.route("/search_result/<int:page>")
def search_result(page=1):
    per_page=24
    query = request.args.get("search", "").strip()

    if not query:
        flash("Please enter a search term", "warning")
        return redirect(url_for("main.index"))
    
    try:
        # 1. Normalize query (convert to lowercase so "Batman" == "batman")
        clean_term = query.lower()[:100] # Limit to 100 chars to match DB column size

        # 2. Check if term exists in DB
        existing_search = SearchTerm.query.filter_by(term=clean_term).first()
        
        if existing_search:
            # If exists, just add +1 to count and update time
            existing_search.count += 1
            existing_search.last_searched = datetime.utcnow()
        else:
            # If new, create it
            new_search = SearchTerm(term=clean_term, count=1)
            db.session.add(new_search)
        
        db.session.commit()
    except Exception as e:
        # 3. Safety Net: If logging fails, ROLLBACK so the user still sees their results
        db.session.rollback()
        print(f"Error logging search term: {e}")

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
    series_trend = AllVideo.query.filter_by(trending=True, type="series", active=True).order_by(AllVideo.views.desc()).limit(6).all()
    movie_trend = AllVideo.query.filter_by(trending=True, type="movie", active=True).order_by(AllVideo.views.desc()).limit(6).all()
    trending_trailers = Trailer.query.order_by(Trailer.views.desc()).limit(5).all()
    return render_template("contact_us.html", trending_series=series_trend, trending_movie=movie_trend, trending_trailers=trending_trailers)

@main_bp.route("/privacy_policy")
def privacy():
    series_trend = AllVideo.query.filter_by(trending=True, type="series", active=True).order_by(AllVideo.views.desc()).limit(6).all()
    movie_trend = AllVideo.query.filter_by(trending=True, type="movie", active=True).order_by(AllVideo.views.desc()).limit(6).all()
    trending_trailers = Trailer.query.order_by(Trailer.views.desc()).limit(5).all()
    return render_template("privacy_policy.html", trending_series=series_trend, trending_movie=movie_trend, trending_trailers=trending_trailers)

@main_bp.route("/dcma")
def dcma():
    series_trend = AllVideo.query.filter_by(trending=True, type="series", active=True).order_by(AllVideo.views.desc()).limit(6).all()
    movie_trend = AllVideo.query.filter_by(trending=True, type="movie", active=True).order_by(AllVideo.views.desc()).limit(6).all()
    trending_trailers = Trailer.query.order_by(Trailer.views.desc()).limit(5).all()
    return render_template("dcma.html", trending_series=series_trend, trending_movie=movie_trend, trending_trailers=trending_trailers)

@main_bp.route("/genre/<string:contain>/<string:genre_type>")
@main_bp.route("/genre/<string:contain>/<string:genre_type>/page/<int:page>")
def genre(genre_type, contain="movie", page=1):
    per_page = 24
    
    # 1. Define Region Mapping
    # Maps the Button Name -> The keyword to search in your 'country' column
    region_map = {
        'Hollywood': 'United States',      # Searches for 'USA' or 'United States'
        'Nollywood': 'Nigeria',
        'Korean': 'Korea',       # Searches for 'South Korea' or 'Korea'
        'Indian': 'India',
        'Chinese': 'China'
    }

    if genre_type == 'Hollywood':
        # Special check for Hollywood to catch BOTH "USA" and "United States"
        if contain == 'movie':
            videos = AllVideo.query.filter(
                or_(AllVideo.country.ilike('%USA%'), AllVideo.country.ilike('%United States%')),
                AllVideo.active == True, AllVideo.type == "movie"
            ).order_by(AllVideo.date_added.desc()).paginate(page=page, per_page=per_page)
        else:
            videos = AllVideo.query.filter(
                or_(AllVideo.country.ilike('%USA%'), AllVideo.country.ilike('%United States%')),
                AllVideo.active == True
            ).order_by(AllVideo.date_added.desc()).paginate(page=page, per_page=per_page)
        
        # Create the mock genre for the title
        class MockGenre:
             def __init__(self, name): self.name = name
        genre = MockGenre(name=genre_type)
    
    # 2. Check if the user clicked a Region
    elif genre_type in region_map:
        search_country = region_map[genre_type]
        
        # Filter by COUNTRY, not Genre
        if contain != 'movie':
            videos = AllVideo.query.filter(
                AllVideo.country.ilike(f'%{search_country}%'), 
                AllVideo.active == True
            ).order_by(AllVideo.date_added.desc()).paginate(page=page, per_page=per_page)
        else:
            videos = AllVideo.query.filter(
                AllVideo.country.ilike(f'%{search_country}%'), 
                AllVideo.active == True, AllVideo.type == "movie"
            ).order_by(AllVideo.date_added.desc()).paginate(page=page, per_page=per_page)
        # Create a fake genre object so your template doesn't crash if it uses {{ genre.name }}
        class MockGenre:
            def __init__(self, name):
                self.name = name
        genre = MockGenre(name=genre_type)

    elif genre_type == "Old":
        # Adjust the year (2000, 2010) to whatever you consider "Old"
        if contain != 'movie':
            videos = AllVideo.query.filter(
                AllVideo.year_produced < 2010, 
                AllVideo.active == True
            ).order_by(AllVideo.date_added.desc()).paginate(page=page, per_page=per_page)
        else:
            videos = AllVideo.query.filter(
                AllVideo.year_produced < 2010, 
                AllVideo.active == True, AllVideo.type == "movie"
            ).order_by(AllVideo.date_added.desc()).paginate(page=page, per_page=per_page)
        class MockGenre:
            def __init__(self, name): self.name = name
        genre = MockGenre(name="Classic Movies")

    # 3. Handle Special "Sci-Fi" case
    elif genre_type == "Anime":
        # USE MOCK GENRE (Safer)
        # This prevents a 404 error if "Anime" isn't strictly in your genres table
        class MockGenre:
            def __init__(self, name): self.name = name
        genre = MockGenre(name="Anime")

        if contain != 'movie':
            videos = (
                AllVideo.query.join(AllVideo.genres)
                .filter(
                    Genre.name == "Animation",   # Looks for 'Animation'
                    AllVideo.country == "Japan", # AND 'Japan'
                    AllVideo.active == True
                )
                .order_by(AllVideo.date_added.desc()).paginate(page=page, per_page=per_page)
            )
        else:
            videos = (
                AllVideo.query.join(AllVideo.genres)
                .filter(
                    Genre.name == "Animation",   # Looks for 'Animation'
                    AllVideo.country == "Japan", # AND 'Japan'
                    AllVideo.active == True, 
                    AllVideo.type == "movie"
                )
                .order_by(AllVideo.date_added.desc()).paginate(page=page, per_page=per_page)
            )

    elif genre_type == "Sci-Fi":
        genre = Genre.query.filter_by(name="Science Fiction").first_or_404()
        if contain != 'movie':
            videos = (
                AllVideo.query.join(AllVideo.genres)
                .filter(Genre.name == "Science Fiction", AllVideo.active == True)
                .paginate(page=page, per_page=per_page)
            )
        else:
            videos = (
                AllVideo.query.join(AllVideo.genres)
                .filter(Genre.name == "Science Fiction", AllVideo.active == True, AllVideo.type == "movie")
                .paginate(page=page, per_page=per_page)
            )

    # 4. Standard Genres (Action, Comedy, etc.)
    else:
        genre = Genre.query.filter_by(name=genre_type).first_or_404()
        
        if contain != 'movie':
            videos = (
                AllVideo.query.join(AllVideo.genres)
                .filter(Genre.name == genre_type, AllVideo.active == True)
                .paginate(page=page, per_page=per_page)
            )
        else:
            videos = (
                AllVideo.query.join(AllVideo.genres)
                .filter(Genre.name == genre_type, AllVideo.active == True, AllVideo.type == "movie")
                .paginate(page=page, per_page=per_page)
            )

    # --- Sidebar Data (Unchanged) ---
    series_trend = AllVideo.query.filter_by(trending=True, type="series", active=True).order_by(AllVideo.views.desc()).limit(6).all()
    movie_trend = AllVideo.query.filter_by(trending=True, type="movie", active=True).order_by(AllVideo.views.desc()).limit(6).all()
    trending_trailers = Trailer.query.order_by(Trailer.views.desc()).limit(5).all()
    
    return render_template("genre.html", 
                           genre_type=genre_type, 
                           genre=genre, 
                           videos=videos, 
                           trending_series=series_trend, 
                           trending_movie=movie_trend, 
                           trending_trailers=trending_trailers, 
                           is_genre=True, context=contain)


@main_bp.route("/<det>/<name>/<int:id>")
@main_bp.route("/<det>/<name>/<int:id>/<int:season>/<int:episode>")
def detail(det, name, id, season=1, episode=1):
    video = AllVideo.query.get(id)
    if video and video.slug and det != "trailer_watch":
        name = video.slug
    
    if det == "movie":
        return redirect(url_for("main.movie_details", det=det, name=name, id=id))
        print("hello")
    elif det == "series":
        return redirect(url_for("main.series_details", det=det, name=name, season=season, episode=episode, id=id))
    elif det == "trailer_watch":
        return redirect(url_for("main.watch_trailer", det=det, name=name))

@main_bp.route("/download/<det>/<name>/<int:id>")
def movie_details(det, name, id):
    movie = AllVideo.query.filter_by(id=id, active=True).first_or_404()
    num_comment = Comment.query.filter_by(
        video_id=movie.id,
        parent_id=None
    ).count()
    comments = Comment.query.filter_by(video_id=movie.id, parent_id=None).order_by(Comment.date_added.desc()).all()    
    pinned_admin_comment = (Comment.query
        .filter_by(video_id=movie.id, parent_id=None)
        .filter(Comment.name.like('[ADMIN] %'))
        .order_by(Comment.date_added.desc())
        .first())
    comment_badges = build_comment_badges()
    series_trend = AllVideo.query.filter_by(trending=True, type="series", active=True).order_by(AllVideo.views.desc()).limit(6).all()
    movie_trend = AllVideo.query.filter_by(trending=True, type="movie", active=True).order_by(AllVideo.views.desc()).limit(6).all()
    trending_trailers = Trailer.query.order_by(Trailer.views.desc()).limit(5).all()
    genre_ids=[g.id for g in movie.genres]
    suggested = AllVideo.query.options(defer(AllVideo.video_qualities)).join(AllVideo.genres).filter(Genre.id.in_(genre_ids), AllVideo.id != id, AllVideo.active == True).distinct().limit(6).all()

    # Optional: prepare breakdown for template
    breakdown = {i: db.session.query(func.count(Rating.id))
                     .filter(Rating.video_id==movie.id, Rating.rating==i)
                     .scalar() for i in range(1,6)}

    more_needed=0
    if len(suggested) < 6:
        more_needed = 6 - len(suggested)

    extra = AllVideo.query.filter(AllVideo.id!=id, ~AllVideo.id.in_([m.id for m in suggested]), AllVideo.active == True).order_by(func.random()).limit(more_needed).all()
    suggested.extend(extra)

    # Social videos linked to this movie
    social_videos = SocialVideo.query.filter(
        SocialVideo.active == True,
        SocialVideo.all_videos.any(AllVideo.id == id)
    ).order_by(SocialVideo.sort_order.asc()).all()

    try:
        # 1. Safety Valve: Clear any pending/accidental changes so we don't save garbage
        db.session.rollback()

        # 2. Atomic Update: Increase view count directly in DB
        # This is fast and DOES NOT trigger the 'updated_at' timestamp change
        AllVideo.query.filter_by(id=id).update({'views': AllVideo.views + 1})

        # 3. Save only this specific change
        db.session.commit()
        
    except Exception as e:
        # If the view count fails for some reason, just ignore it.
        # Don't crash the whole page just because a counter failed.
        db.session.rollback()
        print(f"Error updating view count: {e}")

    return render_template("movie.html", num_comment=num_comment, comments=comments, pinned_admin_comment=pinned_admin_comment, id=id, det=det, breakdown=breakdown, suggested=suggested, video=movie, trending_series=series_trend, trending_movie=movie_trend, trending_trailers=trending_trailers, comment_badges=comment_badges, social_videos=social_videos)

@main_bp.route("/download/<det>/<name>/s<int:season>/e<int:episode>/<int:id>")
def series_details(det, name, season, episode, id):
    print(id)
    series = AllVideo.query.filter_by(id=id, active=True).first_or_404()

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
    ).first()


    if not current_episode:
        current_episode = (Episode.query
            .filter_by(season_id=current_season.id)
            .order_by(Episode.episode_number.asc())
            .first_or_404()
        )
        episode = current_episode.episode_number
    else:
        episode = current_episode.episode_number

    try:
        if current_episode:
            current_episode.views = (current_episode.views or 0) + 1
            db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Error updating episode views: {e}")

    num_comment = Comment.query.filter_by(
        video_id=series.id,
        parent_id=None
    ).count()
    comments = Comment.query.filter_by(video_id=series.id, parent_id=None).order_by(Comment.date_added.desc()).all()    
    pinned_admin_comment = (Comment.query
        .filter_by(video_id=series.id, parent_id=None)
        .filter(Comment.name.like('[ADMIN] %'))
        .order_by(Comment.date_added.desc())
        .first())
    comment_badges = build_comment_badges()
    series_trend = AllVideo.query.filter_by(trending=True, type="series", active=True).order_by(AllVideo.views.desc()).limit(6).all()
    movie_trend = AllVideo.query.filter_by(trending=True, type="movie", active=True).order_by(AllVideo.views.desc()).limit(6).all()
    trending_trailers = Trailer.query.order_by(Trailer.views.desc()).limit(5).all()
    genre_ids=[g.id for g in series.genres]
    suggested = AllVideo.query.options(defer(AllVideo.video_qualities)).join(AllVideo.genres).filter(Genre.id.in_(genre_ids), AllVideo.id != id, AllVideo.type=="series", AllVideo.active == True).distinct().limit(6).all()
    # Optional: prepare breakdown for template
    breakdown = {i: db.session.query(func.count(Rating.id))
                     .filter(Rating.video_id==series.id, Rating.rating==i)
                     .scalar() for i in range(1,6)}

    more_needed=0
    if len(suggested) < 6:
        more_needed = 6 - len(suggested)

    extra = AllVideo.query.filter(AllVideo.id!=id, ~AllVideo.id.in_([m.id for m in suggested]), AllVideo.active == True).order_by(func.random()).limit(more_needed).all()
    suggested.extend(extra)
    
    try:
        # 1. Safety Valve: Clear any pending/accidental changes so we don't save garbage
        db.session.rollback()

        # 2. Atomic Update: Increase view count directly in DB
        # This is fast and DOES NOT trigger the 'updated_at' timestamp change
        AllVideo.query.filter_by(id=id).update({'views': AllVideo.views + 1})

        # 3. Save only this specific change
        db.session.commit()
        
    except Exception as e:
        # If the view count fails for some reason, just ignore it.
        # Don't crash the whole page just because a counter failed.
        db.session.rollback()
        print(f"Error updating view count: {e}")

    return render_template("movie.html", num_comment=num_comment, current_season=current_season, current_episode=current_episode, comments=comments, pinned_admin_comment=pinned_admin_comment, season=int(season), seasons=seasons, breakdown=breakdown, episode=episode, det=det, suggested=suggested, video=series, trending_series=series_trend, trending_movie=movie_trend, trending_trailers=trending_trailers, comment_badges=comment_badges)


@main_bp.route("/download/<string:slug>")
def movie_download_page(slug):
    """
    Public download hub page.
    Route: /download/<slug>
    Supports both movies and series (season/episode via query args).
    """
    # Try slug first, then name as fallback
    video = AllVideo.query.filter_by(slug=slug, active=True).first()
    if not video:
        video = AllVideo.query.filter_by(name=slug, active=True).first_or_404()

    # Series support — season/episode from query args
    season  = request.args.get('season',  1, type=int)
    episode = request.args.get('episode', 1, type=int)
    det     = video.type  # 'movie' or 'series'

    current_season  = None
    current_episode = None

    if video.type == 'series' and video.series:
        current_season = Season.query.filter_by(
            series_id=video.series.id,
            season_number=season
        ).first()
        if current_season:
            current_episode = Episode.query.filter_by(
                season_id=current_season.id,
                episode_number=episode
            ).first()
            if not current_episode:
                current_episode = (
                    Episode.query
                    .filter_by(season_id=current_season.id)
                    .order_by(Episode.episode_number.asc())
                    .first()
                )
            if current_episode:
                episode = current_episode.episode_number

    # Sidebar data
    series_trend     = AllVideo.query.filter_by(trending=True, type="series", active=True).order_by(AllVideo.views.desc()).limit(6).all()
    movie_trend      = AllVideo.query.filter_by(trending=True, type="movie",  active=True).order_by(AllVideo.views.desc()).limit(6).all()
    trending_trailers = Trailer.query.order_by(Trailer.views.desc()).limit(5).all()

    # Related content
    genre_ids = [g.id for g in video.genres]
    suggested = (
        AllVideo.query
        .options(defer(AllVideo.video_qualities))
        .join(AllVideo.genres)
        .filter(Genre.id.in_(genre_ids), AllVideo.id != video.id, AllVideo.active == True)
        .distinct().limit(8).all()
    )
    if len(suggested) < 8:
        extra = AllVideo.query.filter(
            AllVideo.id != video.id,
            ~AllVideo.id.in_([s.id for s in suggested]),
            AllVideo.active == True
        ).order_by(func.random()).limit(8 - len(suggested)).all()
        suggested.extend(extra)

    return render_template(
        "movie_download.html",
        video=video,
        det=det,
        season=season,
        episode=episode,
        current_season=current_season,
        current_episode=current_episode,
        suggested=suggested,
        trending_series=series_trend,
        trending_movie=movie_trend,
        trending_trailers=trending_trailers,
        dark=True,
    )


@main_bp.route("/download/<type>/<int:id>")
@main_bp.route("/download/<type>/<int:id>/<int:season>/<int:episode>")
def download_dispatcher(type, id, season=None, episode=None):
    BRAND_TAG = "[MaxCinema.name.ng]"
    
    # --- 1. Fetch Media Object ---
    if type == "movie":
        video = AllVideo.query.filter_by(id=id, active=True).first_or_404()
        base_name = slugify(video.name)
    
    elif type == "series":
        video = Episode.query.get_or_404(id)
        # Hierarchy: Episode -> Season -> Series
        series_title = video.season.series.all_video.name
        base_name = f"{slugify(series_title)}_S{video.season.season_number:02d}E{video.episode_number:02d}"
    else:
        return "Invalid type", 400

    # --- 2. Determine Audio Type (Sub vs Dub) 🟢 ---
    audio_type = request.args.get('audio') # Get ?audio=dub from URL
    is_dub = (audio_type == 'dub')

    if is_dub:
        # Use the NEW column
        target_link = video.dub_download_link
        filename_suffix = "-ENG-DUB"
    else:
        # Use the STANDARD column
        target_link = video.download_link
        filename_suffix = ""

    # --- 3. Validate Link Exists ---
    if not target_link:
        flash("This audio version is not available yet.", "error")
        # Send user back to the movie page
        if type == 'movie':
            return redirect(url_for('main.detail', det='movie', name=video.name, id=video.id))
        else:
            return redirect(url_for('main.detail', det='series', name=video.season.series.all_video.name, id=video.season.series.all_video.id, season=season, episode=episode))

    # --- 4. Generate Clean Filename ---
    # Result: "[MaxCinema.name.ng]_Jujutsu-Kaisen-ENG-DUB.mp4"
    full_clean_name = f"{BRAND_TAG}_{base_name}{filename_suffix}"

    # --- 5. Increment Download Counters (Only once per click) ---
    try:
        video.downloads = (video.downloads or 0) + 1
    
        if type == "series":
            parent_video = video.season.series.all_video
            parent_video.downloads = (parent_video.downloads or 0) + 1
    
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Error tracking download: {e}")

    # --- 6. Select Server ---
    # Get the assigned server (just to check the type)
    assigned_server = video.storage_server
    if not assigned_server or not assigned_server.active:
        return "Storage server not found or inactive", 404

    server_type = assigned_server.server_type.lower()

    # =====================================================
    # 🚀 TELEGRAM LOAD BALANCER
    # =====================================================
    if server_type == "telegram":
        telegram_pool = StorageServer.query.filter_by(server_type="telegram", active=True).all()

        if not telegram_pool:
            return "No active Telegram servers available", 503

        # Pick random worker
        selected_server = telegram_pool[0]

        base = selected_server.base_url.rstrip("/")
        file_hash = target_link.strip() # 👈 Uses the selected link (Dub or Sub)
        
        # Pass the smart filename to the bot
        final_url = f"{base}/watch/{file_hash}?name={full_clean_name}"
        
        return redirect(final_url)

    # =====================================================
    # BYTESCALE
    # =====================================================
    elif server_type == "bytescale":
        # Redirect to your bytescale handler
        if type == "movie":
            return redirect(url_for("main.movie_start_download", type="movie", name=video.name, id=id))
        else:
            # Note: You might need to update movie_start_download to handle Dubs if you use Bytescale
            clean_name = f"{video.season.series.all_video.name}_S{season}E{episode}"
            return redirect(url_for("main.movie_start_download", type="series", name=clean_name, id=id, season=season, episode=episode))

    # =====================================================
    # OTHER SERVERS (Direct Redirects)
    # =====================================================
    elif server_type in ["gofile", "terabox", "streamwish", "doodstream"]:
        link = target_link.strip()
        
        if link.startswith("http"):
            return redirect(link)

        base = assigned_server.base_url.rstrip("/")
        path = link.lstrip("/")
        final_url = f"{base}/{path}"

        return redirect(final_url)

    # =====================================================
    # DEFAULT FALLBACK
    # =====================================================
    else:
        base = assigned_server.base_url.rstrip("/")
        path = target_link.lstrip("/")
        final_url = f"{base}/{path}"

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
        video = AllVideo.query.filter_by(id=id, active=True).first_or_404()
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
    pinned_admin_comment = (Comment.query
        .filter_by(trailer_id=trailer.id, parent_id=None)
        .filter(Comment.name.like('[ADMIN] %'))
        .order_by(Comment.date_added.desc())
        .first())
    comment_badges = build_comment_badges()

    return render_template(
        f"{det}.html",
        trailer=trailer,
        comments=comments,
        pinned_admin_comment=pinned_admin_comment,
        dark=dark,
        up_next=up_next,
        num_comment=num_comment,
        trending_trailers=trending_trailers,
        comment_badges=comment_badges
    )


@main_bp.route("/trending/<type>")
def trending(type):
    series_trend = AllVideo.query.filter_by(trending=True, type="series", active=True).limit(10).all()
    movie_trend = AllVideo.query.filter_by(trending=True, type="movie", active=True).limit(10).all()
    trending_action = AllVideo.query.join(AllVideo.genres).filter(AllVideo.type == "movie", AllVideo.trending==True, Genre.name=="Action", AllVideo.active == True).order_by(AllVideo.date_added.desc()).limit(10).all()
    trending_animation = AllVideo.query.join(AllVideo.genres).filter(AllVideo.trending == True, Genre.name=="Animation", AllVideo.active == True).order_by(AllVideo.date_added.desc()).limit(10).all()
    trending_sci_fi = AllVideo.query.join(AllVideo.genres).filter(AllVideo.trending == True, Genre.name=="Science Fiction", AllVideo.active == True).order_by(AllVideo.date_added.desc()).limit(10).all()
    old_but_gold = AllVideo.query.filter(
        AllVideo.type == "movie",
        AllVideo.year_produced <= 2020,
        AllVideo.rating >= 4,
        AllVideo.active == True
    ).order_by(AllVideo.rating.desc()).limit(10).all()
        

    get_started_items = (
        AllVideo.query
            .filter(
                or_(
                    # Movies: short length
                    (AllVideo.type == "movie") & (AllVideo.length <= "1h 59m"),

                    # Series: few seasons (you could store num_seasons on AllVideo if you want)
                    (AllVideo.type == "series") & (AllVideo.series.has(Series.num_seasons <= 2))
                ),
                AllVideo.active == True
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
        video = AllVideo.query.filter_by(id=id, active=True).first_or_404()
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
    series_trend = AllVideo.query.filter_by(trending=True, type="series", active=True).order_by(AllVideo.views.desc()).limit(6).all()
    movie_trend = AllVideo.query.filter_by(trending=True, type="movie", active=True).order_by(AllVideo.views.desc()).limit(6).all()
    trending_trailers = Trailer.query.order_by(Trailer.views.desc()).limit(5).all()
    movie = AllVideo.query.filter_by(id=id, active=True).first_or_404()

    # Get the best available quality

    
    genre_ids=[g.id for g in movie.genres]
    suggested = AllVideo.query.options(defer(AllVideo.video_qualities)).join(AllVideo.genres).filter(Genre.id.in_(genre_ids), AllVideo.id != id).distinct().limit(6).all()

    more_needed = max(0, 6 - len(suggested))
    if more_needed:
        extra = AllVideo.query.filter(AllVideo.id != id, ~AllVideo.id.in_([m.id for m in suggested]), AllVideo.active == True)\
            .order_by(func.random()).limit(more_needed).all()
        suggested.extend(extra)
    return render_template("stream.html", video=movie, suggested=suggested, id=id, type=type, trending_series=series_trend, trending_movie=movie_trend, trending_trailers=trending_trailers)


@main_bp.route("/watch_series/<type>/<name>/<int:id>/s<season>/e<int:episode>")
def series_download(type, name, id, season, episode):
    ep = Episode.query.get_or_404(id)
    

    # Trending lists
    series_trend = AllVideo.query.filter_by(trending=True, type="series", active=True).order_by(AllVideo.views.desc()).limit(6).all()
    movie_trend = AllVideo.query.filter_by(trending=True, type="movie", active=True).order_by(AllVideo.views.desc()).limit(6).all()
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
    recent_requests = MovieRequest.query.order_by(MovieRequest.date_added.desc()).limit(10).all()
    series_trend = AllVideo.query.filter_by(trending=True, type="series", active=True).order_by(AllVideo.views.desc()).limit(6).all()
    movie_trend = AllVideo.query.filter_by(trending=True, type="movie", active=True).order_by(AllVideo.views.desc()).limit(6).all()
    trending_trailers = Trailer.query.order_by(Trailer.views.desc()).limit(5).all()
    trending_action = ""
    trending_animation = ""
    trending_sci_fi = ""
    old_but_gold = ""
    get_started_items = ""
    trailers = False
    if nav=="trailers" or nav=="all_trailers":
        nav="trailers"
        dark = True
        trailers = True
        videos = Trailer.query.order_by(Trailer.date_added.desc()).paginate(page=page, per_page=per_page)
    if nav=="trending":
        series_trend = AllVideo.query.filter_by(trending=True, type="series", active=True).limit(10).all()
        movie_trend = AllVideo.query.filter_by(trending=True, type="movie", active=True).limit(10).all()
        trending_action = AllVideo.query.join(AllVideo.genres).filter(AllVideo.type == "movie", AllVideo.trending==True, Genre.name=="Action", AllVideo.active == True).order_by(AllVideo.date_added.desc()).limit(10).all()
        trending_animation = AllVideo.query.join(AllVideo.genres).filter(AllVideo.trending == True, Genre.name=="Animation", AllVideo.active == True).order_by(AllVideo.date_added.desc()).limit(10).all()
        trending_sci_fi = AllVideo.query.join(AllVideo.genres).filter(AllVideo.trending == True, Genre.name=="Science Fiction", AllVideo.active == True).order_by(AllVideo.date_added.desc()).limit(10).all()
        old_but_gold = AllVideo.query.filter(
            AllVideo.type == "movie",
            AllVideo.year_produced <= 2020,
            AllVideo.rating >= 4,
            AllVideo.active == True
        ).order_by(AllVideo.rating.desc()).limit(10).all()
        

        get_started_items = (
            AllVideo.query
                .filter(
                    or_(
                        # Movies: short length
                        (AllVideo.type == "movie") & (AllVideo.length <= "1h 59m"),

                        # Series: few seasons (you could store num_seasons on AllVideo if you want)
                        (AllVideo.type == "series") & (AllVideo.series.has(Series.num_seasons <= 2))
                    ),
                    AllVideo.active == True
                )
                .order_by(AllVideo.views.desc())  # popular first
                .limit(10)
                .all()
        )

    if nav == "all_movie":
        videos = AllVideo.query.filter_by(type="movie", active=True).order_by(AllVideo.date_added.desc()).paginate(page=page, per_page=per_page)
    if nav == "all_series":
        videos = AllVideo.query.filter_by(type="series", active=True).order_by(AllVideo.date_added.desc()).paginate(page=page, per_page=per_page)

    return render_template(f"{nav}.html", trailers=trailers, dark=dark, nav=nav, videos=videos, old_but_gold=old_but_gold, get_started_items=get_started_items, trending_series=series_trend, trending_movie=movie_trend, trending_actions=trending_action, trending_animations=trending_animation, trending_sci_fic=trending_sci_fi, trending_trailers=trending_trailers,
recent_requests=recent_requests)


@main_bp.route('/rate/<int:video_id>', methods=['GET', 'POST'])
def rate_video(video_id):
    video = AllVideo.query.get_or_404(video_id)
    ip_address = request.remote_addr or "0.0.0.0"

    if request.method == 'GET':
        avg = db.session.query(func.avg(Rating.rating)).filter(Rating.video_id == video.id).scalar() or 0
        count = db.session.query(func.count(Rating.id)).filter(Rating.video_id == video.id).scalar() or 0
        breakdown = {}
        for i in range(1, 6):
            breakdown[i] = db.session.query(func.count(Rating.id)).filter(
                Rating.video_id == video.id, Rating.rating == i
            ).scalar()
        return jsonify({
            'average_rating': round(float(avg), 2),
            'num_votes': count,
            'breakdown': breakdown
        })

    data = request.get_json(silent=True) or {}
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


def _comment_spam_guard(scope: str, text: str):
    """
    Lightweight session-based anti-spam:
    - 12s cooldown between submissions in same scope.
    - duplicate message blocked for 10 minutes in same scope.
    """
    now_ts = int(time.time())
    min_interval = 12
    duplicate_window = 600
    clean_text = (text or "").strip().lower()
    text_hash = hashlib.sha256(clean_text.encode("utf-8")).hexdigest()

    last_ts_key = f"{scope}_last_ts"
    last_hash_key = f"{scope}_last_hash"
    last_hash_ts_key = f"{scope}_last_hash_ts"

    last_ts = session.get(last_ts_key, 0)
    last_hash = session.get(last_hash_key)
    last_hash_ts = session.get(last_hash_ts_key, 0)

    if now_ts - last_ts < min_interval:
        wait_for = min_interval - (now_ts - last_ts)
        return f"Please wait {wait_for}s before posting again."

    if last_hash == text_hash and (now_ts - last_hash_ts) < duplicate_window:
        return "Duplicate message detected. Please post a different message."

    session[last_ts_key] = now_ts
    session[last_hash_key] = text_hash
    session[last_hash_ts_key] = now_ts
    session.modified = True
    return None

@main_bp.route('/comment/add/<int:video_id>', methods=['POST'])
@main_bp.route('/comment/add/<int:video_id>/<string:type>', methods=['POST'])
def add_comment(video_id, type="video"):
    name = (request.form.get('name') or '').strip()
    email = (request.form.get('email') or '').strip()
    text = (request.form.get('text') or '').strip()
    is_admin_user = current_user.is_authenticated and getattr(current_user, "is_admin", False)

    # Basic Validation
    if not is_admin_user and not all([name, text]):
        return jsonify({'success': False, 'error': 'Name and comment are required'}), 400

    if is_admin_user:
        admin_name = (current_user.username or 'Admin').strip()
        name = f"[ADMIN] {admin_name}"
        email = (current_user.email or email).strip()
    elif name.upper().startswith('[ADMIN]'):
        # Prevent non-admin impersonation via name prefix.
        name = name[7:].strip() or "Guest"

    # Keep DB compatibility (Comment.email is non-nullable) while making email optional in UI.
    if not email:
        email = f"anonymous+{int(time.time() * 1000)}-{random.randint(1000, 9999)}@maxcinema.local"

    spam_error = _comment_spam_guard(f"comment_add_{type}_{video_id}", text)
    if spam_error:
        return jsonify({'success': False, 'error': spam_error}), 429

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
        html = render_template('dark_comments.html', comment=comment, trailer=video_obj, comment_badges=build_comment_badges())
    else:
        # comments.html expects 'video'
        html = render_template('comments.html', comment=comment, video=video_obj, comment_badges=build_comment_badges())
    return jsonify({'success': True, 'html': html})


@main_bp.route('/comment/reply/<int:video_id>', methods=['POST'])
@main_bp.route('/comment/reply/<int:video_id>/<string:type>', methods=['POST'])
def reply_comment(video_id, type="video"):
    name = (request.form.get('name') or '').strip()
    email = (request.form.get('email') or '').strip()
    text = (request.form.get('text') or '').strip()
    parent_id = request.form.get('parent_id', type=int)
    is_admin_user = current_user.is_authenticated and getattr(current_user, "is_admin", False)

    if not is_admin_user and not all([name, text]):
        return jsonify({'success': False, 'error': 'Name and reply are required'}), 400

    if not parent_id:
        return jsonify({'success': False, 'error': 'Invalid parent comment'}), 400

    if is_admin_user:
        admin_name = (current_user.username or 'Admin').strip()
        name = f"[ADMIN] {admin_name}"
        email = (current_user.email or email).strip()
    elif name.upper().startswith('[ADMIN]'):
        name = name[7:].strip() or "Guest"

    if not email:
        email = f"anonymous+{int(time.time() * 1000)}-{random.randint(1000, 9999)}@maxcinema.local"

    spam_error = _comment_spam_guard(f"comment_reply_{type}_{video_id}_{parent_id}", text)
    if spam_error:
        return jsonify({'success': False, 'error': spam_error}), 429

    video_obj = None
    reply = None

    if type == "trailer":
        reply = Comment(
            trailer_id=video_id,
            name=name, email=email, text=text,
            parent_id=parent_id
        )
        video_obj = Trailer.query.get_or_404(video_id)
    else:
        reply = Comment(
            video_id=video_id,
            name=name, email=email, text=text,
            parent_id=parent_id
        )
        video_obj = AllVideo.query.get_or_404(video_id)

    try:
        db.session.add(reply)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

    # 👇 THIS IS THE FIX 👇
    if type == 'trailer':
        html = render_template('dark_comments.html', comment=reply, trailer=video_obj, comment_badges=build_comment_badges())
    else:
        html = render_template('comments.html', comment=reply, video=video_obj, comment_badges=build_comment_badges())
    
    return jsonify({'success': True, 'html': html})


@main_bp.route('/watchlist/notify/<int:video_id>', methods=['POST'])
def watchlist_notify(video_id):
    video = AllVideo.query.filter_by(id=video_id, active=True).first_or_404()
    name = (request.form.get('name') or '').strip()
    email = (request.form.get('email') or '').strip().lower()
    telegram = (request.form.get('telegram') or '').strip()

    if not email and not telegram:
        return jsonify({'success': False, 'error': 'Provide email or Telegram username.'}), 400

    existing = WatchlistNotify.query.filter_by(
        video_id=video.id,
        email=email or None,
        telegram=telegram or None
    ).first()
    if existing:
        return jsonify({'success': True, 'message': 'You are already on this notify list.'})

    try:
        db.session.add(WatchlistNotify(
            video_id=video.id,
            name=name or None,
            email=email or None,
            telegram=telegram or None,
            source="web"
        ))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

    return jsonify({'success': True, 'message': 'Added. We will notify you when it drops.'})


@main_bp.route('/poll/vote/<int:poll_id>', methods=['POST'])
def vote_poll(poll_id):
    poll = WeeklyPoll.query.get_or_404(poll_id)
    option_id = request.form.get('option_id', type=int)
    if not option_id:
        return jsonify({'success': False, 'error': 'Option is required'}), 400

    option = WeeklyPollOption.query.filter_by(id=option_id, poll_id=poll.id).first()
    if not option:
        return jsonify({'success': False, 'error': 'Invalid option'}), 400

    if not session.get('poll_voter_token'):
        session['poll_voter_token'] = hashlib.sha256(
            f"{request.remote_addr}-{time.time()}-{random.randint(1000, 9999)}".encode("utf-8")
        ).hexdigest()[:40]
        session.modified = True

    voter_token = session.get('poll_voter_token')
    already_voted = WeeklyPollVote.query.filter_by(poll_id=poll.id, voter_token=voter_token).first()
    if already_voted:
        return jsonify({'success': False, 'error': 'You already voted in this poll.'}), 409

    try:
        option.votes = (option.votes or 0) + 1
        db.session.add(WeeklyPollVote(
            poll_id=poll.id,
            option_id=option.id,
            voter_token=voter_token,
            ip_address=request.remote_addr
        ))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

    totals = {opt.id: (opt.votes or 0) for opt in poll.options}
    total_votes = sum(totals.values())
    return jsonify({'success': True, 'totals': totals, 'total_votes': total_votes})

@main_bp.route("/admin/uploads")
@login_required
@admin_required
def admin_uploads():

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
    host = get_site_base_url()

    # 1. Define Static Pages (Manually add the host)
    static_urls = [
        {'loc': f"{host}/", 'priority': '1.0'},
        {'loc': f"{host}/trending/movie", 'priority': '0.9'},
        {'loc': f"{host}/trending/series", 'priority': '0.9'},
        {'loc': f"{host}/request/movie", 'priority': '0.5'},
    ]

    # 2. Fetch Data (Limit to recent 2000 to keep it fast)
    # If you have < 2000 movies, .limit() does nothing, which is fine.
    movies = AllVideo.query.filter_by(type='movie', active=True).order_by(AllVideo.date_added.desc()).limit(2000).all()
    series_list = AllVideo.query.filter_by(type='series', active=True).order_by(AllVideo.date_added.desc()).limit(1000).all()
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
    movies = AllVideo.query.filter_by(type="movie", active=True).order_by(AllVideo.date_added.desc()).all()

    # 2. Fetch Series (This returns a list of AllVideo objects)
    series_list = AllVideo.query.filter_by(type="series", active=True).order_by(AllVideo.date_added.desc()).all()

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


from sqlalchemy import text  # Ensure this is imported at the top

@main_bp.route('/learn-tech')
def learn_tech():
    series_trend = AllVideo.query.filter_by(trending=True, type="series", active=True).order_by(AllVideo.views.desc()).limit(6).all()
    movie_trend = AllVideo.query.filter_by(trending=True, type="movie", active=True).order_by(AllVideo.views.desc()).limit(6).all()
    trending_trailers = Trailer.query.order_by(Trailer.views.desc()).limit(5).all()
    return render_template("learn_tech.html", trending_series=series_trend, trending_movie=movie_trend, trending_trailers=trending_trailers)

@main_bp.route('/api/leads/submit', methods=['POST'])
def submit_course_lead():
    data = request.get_json(silent=True) or {}
    name = data.get('name', '').strip()
    email = data.get('email', '').strip()
    phone = data.get('phone', '').strip()
    course_interest = data.get('course_interest', '').strip()

    if not name or not email or not course_interest:
        return jsonify({'success': False, 'error': 'Name, email, and course interest are required'}), 400

    try:
        new_lead = CourseLead(
            name=name,
            email=email,
            phone=phone,
            course_interest=course_interest
        )
        db.session.add(new_lead)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Lead saved successfully'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error saving lead: {e}")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500

@main_bp.route('/ping')
def ping():
    # =========================================================
    # ✅ OPTION 1: LIGHTWEIGHT PING (ACTIVE)
    # This keeps your Flask App awake, but lets Neon DB sleep.
    # This is CRITICAL for the Free Tier (saves your 100 hours).
    # =========================================================
    return "App is awake (DB Sleeping)", 200


@main_bp.route('/track/event', methods=['POST'])
def track_event():
    payload = request.get_json(silent=True) or {}
    event = (payload.get('event') or '').strip().lower()
    target = (payload.get('target') or '').strip()[:120]
    page = (payload.get('page') or '').strip()[:240]

    allowed = {
        'download_click',
        'search_submit',
        'request_submit',
        'share_click',
    }
    if event not in allowed:
        return jsonify({'success': False, 'error': 'Invalid event'}), 400

    current_app.logger.info(
        "analytics_event event=%s target=%s page=%s ip=%s ua=%s",
        event,
        target,
        page,
        request.remote_addr,
        request.headers.get('User-Agent', '')[:180]
    )

    # Persist when table exists; keep endpoint resilient if migration is pending.
    try:
        db.session.add(AnalyticsEvent(
            event=event,
            target=target,
            page=page,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent', '')[:180]
        ))
        db.session.commit()
    except Exception:
        db.session.rollback()

    return jsonify({'success': True}), 200


    # =========================================================
    # ❌ OPTION 2: HEAVY PING (OLD CODE - COMMENTED OUT)
    # This wakes up the Database every time. 
    # WARNING: This will use up your 100 hours in 4 days.
    # Only uncomment this if you start paying for a Database.
    # =========================================================
    # try:
    #     # 1. Try to wake the DB with a tiny, zero-cost query
    #     db.session.execute(text("SELECT 1"))
    #     return "OK (DB Awake)", 200
    # except Exception as e:
    #     # 2. If Neon is sleeping or erroring, CATCH the error.
    #     # Do not let the app crash.
    #     print(f"Ping managed a DB Error: {e}")
    #
    #     # 3. CRITICAL: Rollback the session so the NEXT user doesn't get an error
    #     db.session.rollback()
    #
    #     # 4. Return OK anyway so Cron Job doesn't get red alerts
    #     return "OK (DB Reset)", 200


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
