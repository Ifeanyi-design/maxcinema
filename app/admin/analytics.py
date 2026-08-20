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

_stats_cache = {"context": {}, "timestamp": {}}
_STATS_CACHE_TTL = 600


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

    # Serve from cache if fresh (per-range)
    now = time.time()
    cache_ts = _stats_cache["timestamp"].get(range_param, 0)
    if now - cache_ts < _STATS_CACHE_TTL and range_param in _stats_cache["context"]:
        return render_template('admin/stats.html', **_stats_cache["context"][range_param])

    since = datetime.utcnow() - timedelta(days=days)
    since_7d = datetime.utcnow() - timedelta(days=7)
    since_30d = datetime.utcnow() - timedelta(days=30)

    total_movies = AllVideo.query.filter_by(type='movie').count()
    total_series = AllVideo.query.filter_by(type='series').count()
    total_content = total_movies + total_series
    total_trailers = Trailer.query.count()
    total_users = User.query.count()
    total_views = db.session.query(func.sum(AllVideo.views)).scalar() or 0
    total_downloads = db.session.query(func.sum(AllVideo.downloads)).scalar() or 0
    total_comments = Comment.query.count()
    total_ratings = Rating.query.count()

    pending_requests = MovieRequest.query.filter_by(status='Pending').count()
    filled_requests = MovieRequest.query.filter_by(status='Filled').count()
    rejected_requests = MovieRequest.query.filter_by(status='Rejected').count()
    req_total = pending_requests + filled_requests + rejected_requests
    fill_rate = round((filled_requests / req_total * 100), 1) if req_total > 0 else 0

    req_selected = MovieRequest.query.filter(MovieRequest.date_added >= since).count()
    req_7d = MovieRequest.query.filter(MovieRequest.date_added >= since_7d).count()
    req_30d = MovieRequest.query.filter(MovieRequest.date_added >= since_30d).count()
    stale_cutoff = datetime.utcnow() - timedelta(days=7)
    stale_pending = MovieRequest.query.filter(
        MovieRequest.status == 'Pending',
        MovieRequest.date_added < stale_cutoff
    ).count()

    range_labels = {'7d': 'Last 7 Days', '30d': 'Last 30 Days', '90d': 'Last 90 Days'}
    selected_range_label = range_labels.get(range_param, 'Last 30 Days')

    top_movies = (
        AllVideo.query
        .filter_by(type='movie', active=True)
        .order_by(AllVideo.views.desc())
        .limit(5)
        .all()
    )
    top_movie_names = [m.name for m in top_movies]
    top_movie_views = [m.views for m in top_movies]

    top_series = (
        AllVideo.query
        .filter_by(type='series', active=True)
        .order_by(AllVideo.views.desc())
        .limit(5)
        .all()
    )
    top_series_names = [s.name for s in top_series]
    top_series_downloads = [s.downloads for s in top_series]

    req_stats = [pending_requests, filled_requests, rejected_requests]

    # Single grouped query instead of one COUNT per day (30/90 round trips on
    # an unindexed column was timing out on the production Postgres).
    trend_rows = (
        db.session.query(func.date(MovieRequest.date_added), func.count())
        .filter(MovieRequest.date_added >= since)
        .group_by(func.date(MovieRequest.date_added))
        .all()
    )
    trend_by_day = {str(day_key): count for day_key, count in trend_rows}

    req_trend_labels = []
    req_trend_counts = []
    for i in range(days, -1, -1):
        day = datetime.utcnow() - timedelta(days=i)
        day_str = day.strftime('%m/%d')
        req_trend_labels.append(day_str)
        req_trend_counts.append(trend_by_day.get(str(day.date()), 0))

    top_searches = SearchTerm.query.order_by(SearchTerm.count.desc()).limit(10).all()
    recent_searches = SearchTerm.query.order_by(SearchTerm.last_searched.desc()).limit(10).all()
    likely_no_result_terms = SearchTerm.query.filter(SearchTerm.count <= 2).order_by(SearchTerm.count.desc()).limit(10).all()

    # Aggregate in Postgres instead of loading every ad event into Python.
    ad_rows = (
        db.session.query(AnalyticsEvent.event, AnalyticsEvent.target, func.count())
        .filter(AnalyticsEvent.date_added >= since)
        .group_by(AnalyticsEvent.event, AnalyticsEvent.target)
        .all()
    )
    ad_stats = defaultdict(lambda: {"views": 0, "clicks": 0, "mobile_views": 0, "desktop_views": 0})
    for event, target, count in ad_rows:
        if event == "ad_slot_view":
            ad_stats[target]["views"] += count
            # AnalyticsEvent has no device column; all views counted as desktop.
            ad_stats[target]["desktop_views"] += count
        elif event == "ad_slot_click":
            ad_stats[target]["clicks"] += count

    ad_labels = []
    ad_views_series = []
    ad_clicks_series = []
    ad_placement_rows = []
    ad_total_views = 0
    ad_total_clicks = 0
    ad_mobile_total = 0
    for placement, stats in sorted(ad_stats.items(), key=lambda x: x[1]["views"], reverse=True):
        ctr = (stats["clicks"] / stats["views"] * 100) if stats["views"] > 0 else 0
        ad_labels.append(placement)
        ad_views_series.append(stats["views"])
        ad_clicks_series.append(stats["clicks"])
        ad_total_views += stats["views"]
        ad_total_clicks += stats["clicks"]
        ad_mobile_total += stats["mobile_views"]
        ad_placement_rows.append({
            "placement": placement,
            "views": stats["views"],
            "clicks": stats["clicks"],
            "ctr": round(ctr, 2),
            "mobile_views": stats["mobile_views"],
            "desktop_views": stats["desktop_views"],
        })
    ad_overall_ctr = round((ad_total_clicks / ad_total_views * 100), 2) if ad_total_views > 0 else 0
    ad_mobile_share = round((ad_mobile_total / ad_total_views * 100), 1) if ad_total_views > 0 else 0

    storage_servers = StorageServer.query.all()
    server_stats = []
    for server in storage_servers:
        used = server.used_storage_gb or 0
        total = server.max_storage_gb or 1
        percent = round((used / total * 100), 1) if total > 0 else 0
        server_stats.append({
            "name": server.name,
            "used": used,
            "total": total,
            "percent": percent,
        })

    content_performance = []
    all_videos = AllVideo.query.filter_by(active=True).order_by(AllVideo.views.desc()).limit(12).all()
    for v in all_videos:
        score = (v.views * 1) + (v.downloads * 3) + ((v.rating or 0) * 100)
        content_performance.append({
            "name": v.name,
            "type": v.type,
            "views": v.views,
            "downloads": v.downloads,
            "comments": 0,
            "score": round(score, 1),
        })

    context = dict(
        total_movies=total_movies,
        total_series=total_series,
        total_content=total_content,
        total_trailers=total_trailers,
        total_users=total_users,
        total_views=total_views,
        total_downloads=total_downloads,
        total_comments=total_comments,
        total_ratings=total_ratings,
        pending_requests=pending_requests,
        filled_requests=filled_requests,
        rejected_requests=rejected_requests,
        fill_rate=fill_rate,
        req_filled=filled_requests,
        req_total=req_total,
        req_selected=req_selected,
        req_7d=req_7d,
        req_30d=req_30d,
        stale_pending=stale_pending,
        selected_range=range_param,
        selected_range_label=selected_range_label,
        top_movie_names=top_movie_names,
        top_movie_views=top_movie_views,
        top_series_names=top_series_names,
        top_series_downloads=top_series_downloads,
        req_stats=req_stats,
        req_trend_labels=req_trend_labels,
        req_trend_counts=req_trend_counts,
        top_searches=top_searches,
        recent_searches=recent_searches,
        likely_no_result_terms=likely_no_result_terms,
        ad_labels=ad_labels,
        ad_views_series=ad_views_series,
        ad_clicks_series=ad_clicks_series,
        ad_placement_rows=ad_placement_rows,
        ad_total_views=ad_total_views,
        ad_total_clicks=ad_total_clicks,
        ad_overall_ctr=ad_overall_ctr,
        ad_mobile_share=ad_mobile_share,
        server_stats=server_stats,
        top_content_rows=content_performance,
    )

    # Cache per range for 10 minutes
    _stats_cache["context"][range_param] = context
    _stats_cache["timestamp"][range_param] = time.time()

    return render_template('admin/stats.html', **context)


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
