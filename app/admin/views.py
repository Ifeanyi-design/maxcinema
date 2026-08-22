from datetime import datetime
from sqlalchemy.orm import aliased
from sqlalchemy import func

from flask import render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user, login_user, logout_user
from werkzeug.security import check_password_hash

from ..models import (
    AllVideo, Series, Trailer, StorageServer, User, db, MovieRequest,
    Season, Episode, AnalyticsEvent
)
from ..extensions import login_manager
from . import admin_bp
from .helpers import admin_required

import os


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@admin_bp.context_processor
def inject_ads():
    iframe_domain = os.getenv("AD_IFRAME_DOMAIN", "highperformanceformat.com")

    def iframe_ad(key_env, width, height, fmt="iframe"):
        key = os.getenv(key_env)
        if not key:
            return None
        return {
            "key": key,
            "domain": iframe_domain,
            "format": fmt,
            "width": width,
            "height": height,
        }

    banner = iframe_ad("AD_BANNER_KEY", 728, 90)
    banner_mobile = iframe_ad("AD_BANNER_MOBILE_KEY", 320, 50)
    sidebar = iframe_ad("AD_SIDEBAR_KEY", 300, 250)
    sticky_desktop = iframe_ad("AD_STICKY_DESKTOP_KEY", 728, 90)
    sticky_mobile = iframe_ad("AD_STICKY_MOBILE_KEY", 320, 50)

    pop_domain = os.getenv("AD_POP_DOMAIN", "effectivegatecpm.com")
    pop_path = os.getenv("AD_POP_PATH")
    pop_key = os.getenv("AD_POP_KEY")

    pop_url = None
    if pop_path and pop_key:
        pop_url = f"https://www.{pop_domain}/{pop_path}?key={pop_key}"

    return dict(
        ads={
            "banner": banner,
            "banner_mobile": banner_mobile,
            "sidebar": sidebar,
            "sticky_desktop": sticky_desktop,
            "sticky_mobile": sticky_mobile,
            "pop_url": pop_url,
        }
    )


@admin_bp.app_context_processor
def inject_admin_sidebar_counts():
    total_movies = AllVideo.query.filter_by(type="movie").count()
    total_series = AllVideo.query.filter_by(type="series").count()
    total_trailers = Trailer.query.count()
    total_users = User.query.count()
    total_requests = MovieRequest.query.filter_by(status="Pending").count()

    LatestSeason = aliased(Season)
    latest_season_subq = (
        db.session.query(
            Season.series_id.label("series_id"),
            func.max(Season.season_number).label("max_season_number")
        )
        .group_by(Season.series_id)
        .subquery()
    )

    incomplete_series_count = (
        db.session.query(func.count(Series.id))
        .join(AllVideo, AllVideo.id == Series.all_video_id)
        .join(latest_season_subq, latest_season_subq.c.series_id == Series.id)
        .join(
            LatestSeason,
            (LatestSeason.series_id == Series.id) &
            (LatestSeason.season_number == latest_season_subq.c.max_season_number)
        )
        .filter(AllVideo.type == "series")
        .filter(LatestSeason.completed == False)
        .scalar()
    ) or 0

    return dict(
        total_movies=total_movies,
        total_series=total_series,
        total_trailers=total_trailers,
        total_users=total_users,
        total_requests=total_requests,
        incomplete_series_count=incomplete_series_count,
    )


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("admin.dashboard"))

    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            try:
                user.last_login = datetime.utcnow()
                db.session.commit()
            except Exception:
                db.session.rollback()
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
    page = request.args.get('page', 1, type=int)
    per_page = 24
    kind_filter = (request.args.get('kind') or 'all').strip().lower()
    state_filter = (request.args.get('state') or 'all').strip().lower()
    today = datetime.utcnow().date()

    total_movies = AllVideo.query.filter_by(type='movie').count()
    total_series = AllVideo.query.filter_by(type='series').count()
    total_trailers = Trailer.query.count()
    total_users = User.query.count()
    total_views = db.session.query(db.func.sum(AllVideo.views)).scalar() or 0
    total_requests = MovieRequest.query.filter_by(status='Pending').count()

    storage_servers = StorageServer.query.all()
    storage_info = []
    for server in storage_servers:
        storage_info.append({
            'name': server.name,
            'used': server.used_storage_gb,
            'available': server.available_storage()
        })

    video_query = AllVideo.query
    if kind_filter in {'movie', 'series'}:
        video_query = video_query.filter(AllVideo.type == kind_filter)

    video_missing_links_expr = (
        (func.length(func.trim(func.coalesce(AllVideo.download_link, ''))) == 0) &
        (func.length(func.trim(func.coalesce(AllVideo.dub_download_link, ''))) == 0) &
        (func.length(func.trim(func.coalesce(AllVideo.backup_link, ''))) == 0)
    )
    series_missing_episode_expr = (
        db.session.query(Episode.id)
        .join(Season, Episode.season_id == Season.id)
        .join(Series, Season.series_id == Series.id)
        .filter(
            Series.all_video_id == AllVideo.id,
            func.length(func.trim(func.coalesce(Episode.download_link, ''))) == 0
        )
        .exists()
    )
    missing_links_expr = video_missing_links_expr | series_missing_episode_expr
    if state_filter == 'coming_soon':
        video_query = video_query.filter(AllVideo.coming_soon.is_(True))
    elif state_filter == 'missing_links':
        video_query = video_query.filter(missing_links_expr)
    elif state_filter == 'inactive':
        video_query = video_query.filter(AllVideo.active.is_(False))

    videos_page = (
        video_query
        .order_by(AllVideo.created_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    all_videos_dict = []
    for v in videos_page.items:
        all_videos_dict.append({
            'id': v.id,
            'name': v.name,
            'type': v.type,
            'description': v.description,
            'poster_url': v.image,
            'views': v.views,
            'downloads': v.downloads,
            'slug': v.slug
        })

    recent_analytics = []
    analytics_available = True
    try:
    recent_analytics = (
        AnalyticsEvent.query
        .order_by(AnalyticsEvent.date_added.desc())
        .limit(20)
        .all()
    )

    social_cta_top = []
    social_cta_total = 0
    try:
        social_cta_total = AnalyticsEvent.query.filter_by(event='social_cta_click').count()
        social_cta_top = (
            db.session.query(
                AnalyticsEvent.target,
                func.count(AnalyticsEvent.id).label('cnt')
            )
            .filter(
                AnalyticsEvent.event == 'social_cta_click',
                AnalyticsEvent.target.isnot(None),
                AnalyticsEvent.target != ''
            )
            .group_by(AnalyticsEvent.target)
            .order_by(func.count(AnalyticsEvent.id).desc())
            .limit(8)
            .all()
        )
    except Exception:
        pass
    except Exception:
        analytics_available = False
        recent_analytics = []

    needs_poster = (
        AllVideo.query
        .filter(func.length(func.trim(func.coalesce(AllVideo.image, ''))) == 0)
        .count()
    )
    needs_missing_links = AllVideo.query.filter(missing_links_expr).count()
    needs_past_due = (
        AllVideo.query
        .filter(
            AllVideo.coming_soon.is_(True),
            AllVideo.released_date.isnot(None),
            AllVideo.released_date < today
        )
        .count()
    )
    needs_inactive = AllVideo.query.filter(AllVideo.active.is_(False)).count()

    return render_template(
        'admin/dashboard.html',
        total_movies=total_movies,
        total_series=total_series,
        total_trailers=total_trailers,
        total_users=total_users,
        total_views=total_views,
        storage_info=storage_info,
        all_videos=all_videos_dict,
        videos_page=videos_page,
        total_requests=total_requests,
        recent_analytics=recent_analytics,
        analytics_available=analytics_available,
        social_cta_top=social_cta_top,
        social_cta_total=social_cta_total,
        kind_filter=kind_filter,
        state_filter=state_filter,
        needs_poster=needs_poster,
        needs_missing_links=needs_missing_links,
        needs_past_due=needs_past_due,
        needs_inactive=needs_inactive
    )


@admin_bp.route('/requests')
@admin_bp.route('/requests/<int:page>')
@login_required
@admin_required
def view_requests(page=1):
    per_page = 30
    requests = MovieRequest.query.order_by(MovieRequest.date_added.desc()).paginate(page=page, per_page=per_page, error_out=False)
    total_movies = AllVideo.query.filter_by(type='movie').count()
    total_series = AllVideo.query.filter_by(type='series').count()
    total_trailers = Trailer.query.count()
    total_users = User.query.count()
    total_views = db.session.query(db.func.sum(AllVideo.views)).scalar() or 0
    total_requests = MovieRequest.query.filter_by(status='Pending').count()
    return render_template(
        'admin/requests.html',
        requests=requests,
        total_movies=total_movies,
        total_series=total_series,
        total_trailers=total_trailers,
        total_users=total_users,
        total_views=total_views,
        total_requests=total_requests,
    )


@admin_bp.route('/requests/update/<int:id>/<status>')
@login_required
@admin_required
def update_request_status(id, status):
    req = MovieRequest.query.get_or_404(id)
    if status in ('Filled', 'Rejected', 'Pending'):
        req.status = status
        db.session.commit()
        flash(f'Request marked as {status}.', 'success')
    return redirect(url_for('admin.view_requests'))


@admin_bp.route('/requests/delete/<int:id>')
@login_required
@admin_required
def delete_request(id):
    req = MovieRequest.query.get_or_404(id)
    db.session.delete(req)
    db.session.commit()
    flash('Request deleted.', 'success')
    return redirect(url_for('admin.view_requests'))
