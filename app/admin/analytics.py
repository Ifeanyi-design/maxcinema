from datetime import datetime, timedelta
from collections import defaultdict
import time

from flask import render_template, redirect, url_for, request, flash
from flask_login import login_required
from sqlalchemy import or_, func
from sqlalchemy.orm import aliased

from . import admin_bp
from ..models import (
    AllVideo, Series, Trailer, StorageServer, User, db, RecentItem, Genre, Movie,
    Season, Episode, Rating, Comment, MovieRequest, SearchTerm, AnalyticsEvent,
    WatchlistNotify
)
from .helpers import admin_required

# Simple in-memory cache for stats (10 minute TTL)
_stats_cache = {"data": {}, "timestamp": 0}
_STATS_CACHE_TTL = 600  # 10 minutes


@admin_bp.route('/stats')
@login_required
@admin_required
def stats_dashboard():
    range_param = request.args.get('range', '30d')
    days = 30
    if range_param == '7d':
        days = 7
    elif range_param == '90d':
        days = 90
    elif range_param == '30d':
        days = 30

    since = datetime.utcnow() - timedelta(days=days)

    now = time.time()
    use_cache = (now - _stats_cache["timestamp"]) < _STATS_CACHE_TTL

    if use_cache and "totals" in _stats_cache["data"]:
        totals = _stats_cache["data"]["totals"]
        total_movies = totals["total_movies"]
        total_series = totals["total_series"]
        total_trailers = totals["total_trailers"]
        total_users = totals["total_users"]
        total_views = totals["total_views"]
        total_downloads = totals["total_downloads"]
        total_comments = totals["total_comments"]
        total_ratings = totals["total_ratings"]
        pending_requests = totals["pending_requests"]
        filled_requests = totals["filled_requests"]
        rejected_requests = totals["rejected_requests"]
    else:
        total_movies = AllVideo.query.filter_by(type='movie').count()
        total_series = AllVideo.query.filter_by(type='series').count()
        total_trailers = Trailer.query.count()
        total_users = User.query.count()
        total_views = db.session.query(func.sum(AllVideo.views)).scalar() or 0
        total_downloads = db.session.query(func.sum(AllVideo.downloads)).scalar() or 0
        total_comments = Comment.query.count()
        total_ratings = Rating.query.count()
        pending_requests = MovieRequest.query.filter_by(status='Pending').count()
        filled_requests = MovieRequest.query.filter_by(status='Filled').count()
        rejected_requests = MovieRequest.query.filter_by(status='Rejected').count()

        _stats_cache["data"]["totals"] = {
            "total_movies": total_movies,
            "total_series": total_series,
            "total_trailers": total_trailers,
            "total_users": total_users,
            "total_views": total_views,
            "total_downloads": total_downloads,
            "total_comments": total_comments,
            "total_ratings": total_ratings,
            "pending_requests": pending_requests,
            "filled_requests": filled_requests,
            "rejected_requests": rejected_requests,
        }
        _stats_cache["timestamp"] = now

    top_movies = (
        AllVideo.query
        .filter_by(type='movie', active=True)
        .order_by(AllVideo.views.desc())
        .limit(5)
        .all()
    )
    top_series = (
        AllVideo.query
        .filter_by(type='series', active=True)
        .order_by(AllVideo.views.desc())
        .limit(5)
        .all()
    )

    top_searches = (
        SearchTerm.query
        .order_by(SearchTerm.count.desc())
        .limit(10)
        .all()
    )

    recent_searches = (
        SearchTerm.query
        .order_by(SearchTerm.last_searched.desc())
        .limit(10)
        .all()
    )

    no_result_searches = (
        SearchTerm.query
        .filter(SearchTerm.count <= 2)
        .order_by(SearchTerm.count.desc())
        .limit(10)
        .all()
    )

    ad_events = (
        AnalyticsEvent.query
        .filter(AnalyticsEvent.date_added >= since)
        .all()
    )

    ad_stats = defaultdict(lambda: {"views": 0, "clicks": 0})
    for event in ad_events:
        if event.event == "ad_slot_view":
            ad_stats[event.target]["views"] += 1
        elif event.event == "ad_slot_click":
            ad_stats[event.target]["clicks"] += 1

    ad_performance = []
    for placement, stats in sorted(ad_stats.items(), key=lambda x: x[1]["views"], reverse=True):
        ctr = (stats["clicks"] / stats["views"] * 100) if stats["views"] > 0 else 0
        ad_performance.append({
            "placement": placement,
            "views": stats["views"],
            "clicks": stats["clicks"],
            "ctr": round(ctr, 2)
        })

    storage_servers = StorageServer.query.all()
    storage_health = []
    for server in storage_servers:
        storage_health.append({
            "name": server.name,
            "type": server.server_type,
            "used": server.used_storage_gb,
            "max": server.max_storage_gb,
            "available": server.available_storage(),
            "active": server.active
        })

    content_performance = []
    all_videos = AllVideo.query.filter_by(active=True).order_by(AllVideo.views.desc()).limit(12).all()
    for v in all_videos:
        score = (v.views * 1) + (v.downloads * 3) + ((v.rating or 0) * 100)
        content_performance.append({
            "id": v.id,
            "name": v.name,
            "type": v.type,
            "views": v.views,
            "downloads": v.downloads,
            "rating": v.rating or 0,
            "score": round(score, 1)
        })
    content_performance.sort(key=lambda x: x["score"], reverse=True)

    return render_template(
        'admin/stats.html',
        total_movies=total_movies,
        total_series=total_series,
        total_trailers=total_trailers,
        total_users=total_users,
        total_views=total_views,
        total_downloads=total_downloads,
        total_comments=total_comments,
        total_ratings=total_ratings,
        top_movies=top_movies,
        top_series=top_series,
        pending_requests=pending_requests,
        filled_requests=filled_requests,
        rejected_requests=rejected_requests,
        top_searches=top_searches,
        recent_searches=recent_searches,
        no_result_searches=no_result_searches,
        ad_performance=ad_performance,
        storage_health=storage_health,
        content_performance=content_performance,
        range_param=range_param
    )


@admin_bp.route('/search-terms')
@login_required
@admin_required
def search_terms_page():
    total_movies = AllVideo.query.filter_by(type='movie').count()
    total_series = AllVideo.query.filter_by(type='series').count()
    total_trailers = Trailer.query.count()
    total_users = User.query.count()
    total_views = db.session.query(db.func.sum(AllVideo.views)).scalar() or 0
    total_requests = MovieRequest.query.filter_by(status='Pending').count()

    page = request.args.get('page', 1, type=int)
    per_page = 30
    pagination = SearchTerm.query.order_by(SearchTerm.count.desc()).paginate(page=page, per_page=per_page, error_out=False)

    return render_template('admin/search_terms.html', search_terms=pagination, total_movies=total_movies, total_series=total_series, total_trailers=total_trailers, total_users=total_users, total_views=total_views, total_requests=total_requests)
