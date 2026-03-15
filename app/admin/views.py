from datetime import datetime, timedelta
from collections import defaultdict
from sqlalchemy import or_, func
from sqlalchemy.orm import aliased
from os import name
from flask import render_template, abort, redirect, url_for, request, flash
from ..models import (
    AllVideo, Series, Trailer, StorageServer, User, db, RecentItem, Genre, Movie,
    Season, Episode, Rating, Comment, MovieRequest, SearchTerm, AnalyticsEvent,
    WatchlistNotify, WeeklyPoll, WeeklyPollOption
)
from slugify import slugify
from ..extensions import login_manager
from . import admin_bp
from .forms import AllVideoForm, StorageServerForm, SeasonForm, TrailerForm, EpisodeForm, UserForm
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps
from flask_login import login_required, current_user, login_user, logout_user
import os
import smtplib
import requests
from email.message import EmailMessage

from ..utils import ContentImporter # Import the class we just made

from itertools import cycle  # <--- ADD THIS AT THE TOP


def _has_download_payload(video):
    return bool((video.download_link or "").strip() or (video.dub_download_link or "").strip() or (video.backup_link or "").strip())


def _get_email_provider_config():
    provider = (os.getenv("EMAIL_PROVIDER", "smtp") or "smtp").strip().lower()

    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587") or 587)
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_pass = os.getenv("SMTP_PASS", "").strip()
    smtp_from = os.getenv("SMTP_FROM", smtp_user or "noreply@maxcinema.local").strip()
    smtp_use_ssl = os.getenv("SMTP_USE_SSL", "0").strip().lower() in {"1", "true", "yes", "on"}
    smtp_use_tls = os.getenv("SMTP_USE_TLS", "1").strip().lower() in {"1", "true", "yes", "on"}
    smtp_enabled = bool(smtp_host and smtp_user and smtp_pass)

    resend_api_key = os.getenv("RESEND_API_KEY", "").strip()
    resend_from = os.getenv("RESEND_FROM", "").strip()
    resend_api_url = os.getenv("RESEND_API_URL", "https://api.resend.com/emails").strip()
    resend_enabled = bool(resend_api_key and resend_from)

    return {
        "provider": provider,
        "smtp": {
            "enabled": smtp_enabled,
            "host": smtp_host,
            "port": smtp_port,
            "user": smtp_user,
            "password": smtp_pass,
            "from": smtp_from,
            "use_ssl": smtp_use_ssl,
            "use_tls": smtp_use_tls,
        },
        "resend": {
            "enabled": resend_enabled,
            "api_key": resend_api_key,
            "from": resend_from,
            "api_url": resend_api_url,
        },
    }


def _email_transport_status(cfg):
    provider = cfg["provider"]
    if provider == "resend":
        return cfg["resend"]["enabled"], "resend"
    return cfg["smtp"]["enabled"], "smtp"


def _send_email_notification(to_email, subject, plain_text, html_body=None):
    cfg = _get_email_provider_config()
    enabled, provider = _email_transport_status(cfg)
    if not enabled:
        return False, f"email provider '{provider}' is not configured"

    if provider == "resend":
        resend_cfg = cfg["resend"]
        payload = {
            "from": resend_cfg["from"],
            "to": [to_email],
            "subject": subject,
            "html": html_body or f"<p>{plain_text.replace(chr(10), '<br>')}</p>"
        }
        try:
            resp = requests.post(
                resend_cfg["api_url"],
                headers={
                    "Authorization": f"Bearer {resend_cfg['api_key']}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=20,
            )
            if resp.ok:
                return True, ""
            return False, f"resend:{resp.status_code}:{resp.text[:180]}"
        except Exception as e:
            return False, f"resend:{e}"

    smtp_cfg = cfg["smtp"]
    smtp_server = None
    try:
        if smtp_cfg["use_ssl"]:
            smtp_server = smtplib.SMTP_SSL(smtp_cfg["host"], smtp_cfg["port"], timeout=20)
        else:
            smtp_server = smtplib.SMTP(smtp_cfg["host"], smtp_cfg["port"], timeout=20)
            if smtp_cfg["use_tls"]:
                smtp_server.starttls()

        smtp_server.login(smtp_cfg["user"], smtp_cfg["password"])
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = smtp_cfg["from"]
        msg["To"] = to_email
        msg.set_content(plain_text)
        if html_body:
            msg.add_alternative(html_body, subtype="html")
        smtp_server.send_message(msg)
        return True, ""
    except Exception as e:
        return False, f"smtp:{e}"
    finally:
        if smtp_server:
            try:
                smtp_server.quit()
            except Exception:
                pass


def _send_release_notifications(video):
    """
    Send notifications to watchers for a released title.
    Supports:
    - Resend API email (EMAIL_PROVIDER=resend)
    - SMTP email (EMAIL_PROVIDER=smtp)
    - Telegram Bot API (if TELEGRAM_BOT_TOKEN set)
    """
    rows = WatchlistNotify.query.filter_by(video_id=video.id, notified=False).all()
    if not rows:
        return {"queued": 0, "emailed": 0, "telegram": 0, "marked": 0, "errors": []}

    site_url = os.getenv("SITE_BASE_URL", "https://maxcinema.name.ng")
    release_url = f"{site_url.rstrip('/')}/download/{video.type}/{video.slug or video.name}/{video.id}"
    plain_text = (
        f"Good news! '{video.name}' is now available on MaxCinema.\n\n"
        f"Open: {release_url}\n\n"
        "You requested this notification."
    )

    email_cfg = _get_email_provider_config()
    email_enabled, _ = _email_transport_status(email_cfg)

    # Telegram config (optional)
    tg_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    tg_default_chat = os.getenv("TELEGRAM_NOTIFY_CHAT_ID", "").strip()
    tg_enabled = bool(tg_bot_token)

    emailed = 0
    telegram = 0
    marked = 0
    errors = []

    try:
        for row in rows:
            sent_any = False

            if email_enabled and row.email:
                try:
                    html_text = (
                        f"<p>Good news! '<strong>{video.name}</strong>' is now available on MaxCinema.</p>"
                        f"<p><a href=\"{release_url}\">Open release page</a></p>"
                        "<p>You requested this notification.</p>"
                    )
                    ok, err = _send_email_notification(
                        to_email=row.email,
                        subject=f"Now Available: {video.name}",
                        plain_text=plain_text,
                        html_body=html_text
                    )
                    if not ok:
                        raise RuntimeError(err or "email send failed")
                    emailed += 1
                    sent_any = True
                except Exception as e:
                    errors.append(f"email:{row.email}:{e}")

            if tg_enabled:
                try:
                    tg_target = (row.telegram or "").strip()
                    # If user provided direct chat id, use it. Else fallback to configured channel/chat.
                    if tg_target and tg_target.lstrip("-").isdigit():
                        chat_id = tg_target
                    elif tg_default_chat:
                        mention = f"@{tg_target.lstrip('@')}" if tg_target and not tg_target.lstrip("-").isdigit() else ""
                        chat_id = tg_default_chat
                        plain_with_mention = f"{mention} {plain_text}".strip()
                        payload = {"chat_id": chat_id, "text": plain_with_mention, "disable_web_page_preview": False}
                        resp = requests.post(
                            f"https://api.telegram.org/bot{tg_bot_token}/sendMessage",
                            json=payload,
                            timeout=15
                        )
                        if resp.ok:
                            telegram += 1
                            sent_any = True
                        else:
                            errors.append(f"telegram:{tg_target or 'default'}:{resp.text[:120]}")
                        if sent_any:
                            row.notified = True
                            marked += 1
                        continue
                    else:
                        chat_id = None

                    if chat_id:
                        payload = {"chat_id": chat_id, "text": plain_text, "disable_web_page_preview": False}
                        resp = requests.post(
                            f"https://api.telegram.org/bot{tg_bot_token}/sendMessage",
                            json=payload,
                            timeout=15
                        )
                        if resp.ok:
                            telegram += 1
                            sent_any = True
                        else:
                            errors.append(f"telegram:{chat_id}:{resp.text[:120]}")
                except Exception as e:
                    errors.append(f"telegram:{row.telegram}:{e}")

            if sent_any:
                row.notified = True
                marked += 1

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        errors.append(f"fatal:{e}")

    return {
        "queued": len(rows),
        "emailed": emailed,
        "telegram": telegram,
        "marked": marked,
        "errors": errors[:8]
    }

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

    # IFRAME ADS
    banner = iframe_ad("AD_BANNER_KEY", 728, 90)
    banner_mobile = iframe_ad("AD_BANNER_MOBILE_KEY", 320, 50)
    sidebar = iframe_ad("AD_SIDEBAR_KEY", 300, 250)
    sticky_desktop = iframe_ad("AD_STICKY_DESKTOP_KEY", 728, 90)
    sticky_mobile = iframe_ad("AD_STICKY_MOBILE_KEY", 320, 50)

    # POPUNDER URL (built server-side from secrets)
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
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            try:
                user.last_login = datetime.utcnow()
                db.session.commit()
            except Exception as e:
                db.session.rollback() # Safety first
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


# admin/__init__.py or admin/views.py (once)

@admin_bp.app_context_processor
def inject_admin_sidebar_counts():
    # Totals
    total_movies = AllVideo.query.filter_by(type="movie").count()
    total_series = AllVideo.query.filter_by(type="series").count()
    total_trailers = Trailer.query.count()
    total_users = User.query.count()
    total_requests = MovieRequest.query.filter_by(status="Pending").count()

    # Incomplete series count (your existing logic)
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

    missing_links_expr = (
        (func.length(func.trim(func.coalesce(AllVideo.download_link, ''))) == 0) &
        (func.length(func.trim(func.coalesce(AllVideo.dub_download_link, ''))) == 0) &
        (func.length(func.trim(func.coalesce(AllVideo.backup_link, ''))) == 0)
    )
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
        kind_filter=kind_filter,
        state_filter=state_filter,
        needs_poster=needs_poster,
        needs_missing_links=needs_missing_links,
        needs_past_due=needs_past_due,
        needs_inactive=needs_inactive
    )

import json


@admin_bp.route('/edit_video/<prev>/<int:video_id>', methods=["GET", "POST"])
@login_required
def edit_video(video_id, prev):
    video = AllVideo.query.get_or_404(video_id)
    was_coming_soon = bool(video.coming_soon)

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
        video.dub_download_link = form.dub_download_link.data
        video.image = form.image.data
        video.type = form.type.data
        video.trailer_url = form.trailer_url.data
        video.backup_link = form.backup_link.data
        video.coming_soon=form.coming_soon.data
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
        if was_coming_soon and (not video.coming_soon) and _has_download_payload(video):
            summary = _send_release_notifications(video)
            if summary["queued"] > 0:
                flash(
                    f"Release notifications sent: email {summary['emailed']}, telegram {summary['telegram']}, marked {summary['marked']}/{summary['queued']}.",
                    "info"
                )
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
            backup_link=form.backup_link.data,
            trailer_url=form.trailer_url.data,
            download_link=form.download_link.data,
            dub_download_link=form.dub_download_link.data,
            image=form.image.data,
            type=form.type.data,
            featured=form.featured.data,
            trending=form.trending.data,
            active=form.active.data,
            coming_soon=form.coming_soon.data,
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
    page = request.args.get('page', 1, type=int)
    per_page = 24
    
    series_list = (
        AllVideo.query
        .filter_by(type="series")
        .order_by(AllVideo.created_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )
    return render_template('admin/view_series.html', series_list=series_list, series=series, total_movies=total_movies, total_series=total_series, total_trailers=total_trailers, total_users=total_users, total_views=total_views, total_requests=total_requests)



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
        # ⚠️ CRITICAL FIX: Save the old ID before populate_obj wipes it
        original_season_id = episode.season_id
        
        form.populate_obj(episode)
        
        # Logic: If the Admin typed a new ID, check if valid. 
        # If they left it empty (None), restore the original ID.
        if form.season_id.data:
            # Check if this new Season ID exists
            if Season.query.get(form.season_id.data):
                episode.season_id = form.season_id.data
            else:
                db.session.rollback() # Undo changes
                flash(f"Error: Season ID {form.season_id.data} does not exist!", "error")
                return render_template('admin/add_episode.html', form=form, season=season, series=series, prev="serie", action="Edit")
        else:
            # Restore the original ID so it doesn't become None/Null
            episode.season_id = original_season_id

        episode.updated_at = datetime.utcnow()
        db.session.commit()
        
        flash(f"Episode updated successfully.", "success")
        return redirect(url_for('admin.view_episodes', prev=prev, name=series.slug, ns=season.season_number, season_id=season.id))

    return render_template('admin/add_episode.html', form=form, season=season, series=series, prev="serie" if prev == "serie" or prev == "series" else "incomplete", action="Edit")

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
    season.num_episodes = Episode.query.filter_by(season_id=season.id).count()

    # total across all seasons:
    total_eps = 0
    for s in serie.series.seasons:
        total_eps += len(s.episodes)
    serie.series.num_episodes = total_eps

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
        print("DEBUG: Form Submitted! Processing...") 

        try:
            # 1. Import inside the function to prevent circular errors
            # Note: Ensure the dot (.) matches where the file actually is. 
            # If utils.py is next to views.py, use .utils
            from ..utils import ContentImporter 
            
            importer = ContentImporter()
            
            # 2. Get Data
            tmdb_id = request.form.get('tmdb_id')
            ctype = request.form.get('type')
            
            msg = ""
            if ctype == 'movie':
                msg = importer.import_movie(tmdb_id)
            
            elif ctype == 'series':
                # Get the raw text (e.g., "1-8")
                seasons_in = request.form.get('seasons')
                ep_range = request.form.get('episodes')
                
                print(f"DEBUG: Processing Series {tmdb_id} | Seasons: {seasons_in} | Eps: {ep_range}")
                
                # Pass the raw text directly. The new utils.py handles the splitting.
                msg = importer.import_series(tmdb_id, seasons_in, ep_range)
            
            print(f"DEBUG: Success! {msg}")
            flash(msg, 'success')

        except Exception as e:
            import traceback
            traceback.print_exc()
            flash(f"Error: {str(e)}", 'error')

        return redirect(url_for('admin.import_tmdb'))

    return render_template('admin/import.html')


@admin_bp.route('/admin/incomplete-content')
@login_required
@admin_required
def view_incomplete_content():
    if not current_user.is_admin:
        abort(403)

    # 1. Fetch Movies with NO links (Download AND Backup are empty/None)
    incomplete_movies = AllVideo.query.filter_by(type='movie').filter(
        (AllVideo.download_link == None) | (AllVideo.download_link == ""),
        (AllVideo.backup_link == None) | (AllVideo.backup_link == "")
    ).all()

    # 2. Fetch Episodes with NO links
    incomplete_episodes = Episode.query.filter(
        (Episode.download_link == None) | (Episode.download_link == ""),
        (Episode.backup_link == None) | (Episode.backup_link == "")
    ).all()

    return render_template('admin/incomplete_content.html', 
                           movies=incomplete_movies, 
                           episodes=incomplete_episodes)


@admin_bp.route('/admin/stats')
@login_required
@admin_required
def stats_dashboard():
    if not current_user.is_admin:
        abort(403)

    range_key = (request.args.get('range') or '30d').strip().lower()
    range_days_map = {'7d': 7, '30d': 30, '90d': 90}
    selected_days = range_days_map.get(range_key, 30)
    selected_range_label = f"{selected_days}d"
    range_start = datetime.utcnow() - timedelta(days=selected_days)

    # --- 1. BIG NUMBER CARDS ---
    total_users = User.query.count()
    total_views = db.session.query(func.sum(AllVideo.views)).scalar() or 0
    
    # Calculate Total Downloads (Movies + All Episodes)
    movie_downloads = db.session.query(func.sum(AllVideo.downloads)).filter(AllVideo.type == 'movie').scalar() or 0
    episode_downloads = db.session.query(func.sum(Episode.downloads)).scalar() or 0
    grand_total_downloads = movie_downloads + episode_downloads
    
    pending_requests = MovieRequest.query.filter_by(status='Pending').count()
    req_filled = MovieRequest.query.filter_by(status='Filled').count()
    req_rejected = MovieRequest.query.filter_by(status='Rejected').count()
    req_total = pending_requests + req_filled + req_rejected
    fill_rate = round((req_filled / req_total) * 100, 1) if req_total else 0
    total_content = (AllVideo.query.filter_by(type='movie').count() +
                     AllVideo.query.filter_by(type='series').count() +
                     Trailer.query.count())

    # --- 2. CHART DATA: Top 5 Movies by Views ---
    top_movies_query = AllVideo.query.filter_by(type='movie').order_by(AllVideo.views.desc()).limit(5).all()
    
    top_movie_names = []
    for m in top_movies_query:
        name = m.name
        if len(name) > 20:
            name = name[:20] + "..."
        top_movie_names.append(name)
        
    top_movie_views = [m.views for m in top_movies_query]

    # --- 3. CHART DATA: Top 5 Series by POPULARITY (VIEWS) ---
    # 👇 FIXED: We now sort by VIEWS so JJK appears immediately. 
    # (Previously it sorted by downloads, which were likely 0 due to broken links).
    top_series_query = AllVideo.query.filter_by(type='series').order_by(AllVideo.views.desc()).limit(5).all()

    top_series_names = []
    top_series_downloads = [] # We keep this variable name so the HTML doesn't break
    
    for s in top_series_query:
        name = s.name
        if len(name) > 20:
            name = name[:20] + "..."
        top_series_names.append(name)
        # Using views here ensures the chart is populated
        top_series_downloads.append(s.views)

    # --- 4. PIE CHART: Requests ---
    req_pending = pending_requests

    # --- 5. SEARCH TERMS ---
    scoped_search_query = SearchTerm.query.filter(SearchTerm.last_searched >= range_start)
    top_searches = scoped_search_query.order_by(SearchTerm.count.desc()).limit(10).all()
    recent_searches = scoped_search_query.order_by(SearchTerm.last_searched.desc()).limit(8).all()
    if not top_searches:
        top_searches = SearchTerm.query.order_by(SearchTerm.count.desc()).limit(10).all()
    if not recent_searches:
        recent_searches = SearchTerm.query.order_by(SearchTerm.last_searched.desc()).limit(8).all()

    # Heuristic: "no result" opportunities based on no active title match.
    likely_no_result_terms = []
    search_candidates = scoped_search_query.order_by(SearchTerm.count.desc()).limit(40).all()
    if not search_candidates:
        search_candidates = SearchTerm.query.order_by(SearchTerm.count.desc()).limit(40).all()
    for st in search_candidates:
        has_match = AllVideo.query.filter(
            AllVideo.active.is_(True),
            AllVideo.name.ilike(f"%{st.term}%")
        ).first()
        if not has_match:
            likely_no_result_terms.append(st)
        if len(likely_no_result_terms) >= 8:
            break

    # --- 5b. AD PERFORMANCE (SELECTED RANGE) ---
    ad_events = AnalyticsEvent.query.filter(
        AnalyticsEvent.date_added >= range_start,
        AnalyticsEvent.event.in_(["ad_slot_view", "ad_slot_click"])
    ).all()

    placement_stats_map = defaultdict(lambda: {
        "views": 0,
        "clicks": 0,
        "mobile_views": 0,
        "desktop_views": 0
    })

    for ev in ad_events:
        raw_target = (ev.target or "").strip().lower()
        parts = raw_target.split("|")
        placement = parts[0] if parts and parts[0] else "unknown"
        device = parts[1] if len(parts) > 1 and parts[1] else "unknown"

        if ev.event == "ad_slot_view":
            placement_stats_map[placement]["views"] += 1
            if device == "mobile":
                placement_stats_map[placement]["mobile_views"] += 1
            elif device == "desktop":
                placement_stats_map[placement]["desktop_views"] += 1
        elif ev.event == "ad_slot_click":
            placement_stats_map[placement]["clicks"] += 1

    ad_placement_rows = []
    for placement, stat in placement_stats_map.items():
        views = stat["views"]
        clicks = stat["clicks"]
        ctr = round((clicks / views) * 100, 2) if views else 0.0
        ad_placement_rows.append({
            "placement": placement,
            "views": views,
            "clicks": clicks,
            "ctr": ctr,
            "mobile_views": stat["mobile_views"],
            "desktop_views": stat["desktop_views"]
        })

    ad_placement_rows.sort(key=lambda x: x["views"], reverse=True)
    ad_placement_rows = ad_placement_rows[:8]

    ad_total_views = sum(r["views"] for r in ad_placement_rows)
    ad_total_clicks = sum(r["clicks"] for r in ad_placement_rows)
    ad_overall_ctr = round((ad_total_clicks / ad_total_views) * 100, 2) if ad_total_views else 0.0
    ad_mobile_share = round(
        (sum(r["mobile_views"] for r in ad_placement_rows) / ad_total_views) * 100, 1
    ) if ad_total_views else 0

    ad_labels = [r["placement"].replace("_", " ").title() for r in ad_placement_rows]
    ad_views_series = [r["views"] for r in ad_placement_rows]
    ad_clicks_series = [r["clicks"] for r in ad_placement_rows]

    # --- 6. NEW: STORAGE HEALTH ---
    servers = StorageServer.query.all()
    server_stats = []
    for s in servers:
        # Avoid division by zero
        percent = (s.used_storage_gb / s.max_storage_gb * 100) if s.max_storage_gb > 0 else 0
        server_stats.append({
            'name': s.name,
            'percent': round(percent, 1),
            'used': round(s.used_storage_gb, 1),
            'total': s.max_storage_gb
        })

    # --- 7. REQUEST FUNNEL + TREND ---
    now_utc = datetime.utcnow()
    req_selected = MovieRequest.query.filter(MovieRequest.date_added >= range_start).count()
    req_7d = MovieRequest.query.filter(MovieRequest.date_added >= (now_utc - timedelta(days=7))).count()
    req_30d = MovieRequest.query.filter(MovieRequest.date_added >= (now_utc - timedelta(days=30))).count()
    stale_pending = MovieRequest.query.filter(
        MovieRequest.status == 'Pending',
        MovieRequest.date_added < (now_utc - timedelta(days=7))
    ).count()

    # Trend: new requests per day (selected range)
    trend_span = selected_days
    trend_days = [now_utc.date() - timedelta(days=i) for i in range(trend_span - 1, -1, -1)]
    trend_index = {d.isoformat(): 0 for d in trend_days}
    req_trend_rows = MovieRequest.query.filter(
        MovieRequest.date_added >= range_start
    ).all()

    for row in req_trend_rows:
        dkey = row.date_added.date().isoformat()
        if dkey in trend_index:
            trend_index[dkey] += 1

    req_trend_labels = [d.strftime('%b %d') for d in trend_days]
    req_trend_counts = [trend_index[d.isoformat()] for d in trend_days]

    # --- 8. EXTRA: TOP CONTENT PERFORMANCE ---
    content_rows = AllVideo.query.filter(AllVideo.active.is_(True)).order_by(AllVideo.views.desc()).limit(12).all()
    top_content_rows = []
    for video in content_rows:
        comments = video.total_comment or 0
        downloads = video.downloads or 0
        views = video.views or 0
        perf_score = (views * 1.0) + (downloads * 2.0) + (comments * 4.0)
        top_content_rows.append({
            "name": video.name,
            "type": video.type,
            "views": views,
            "downloads": downloads,
            "comments": comments,
            "score": int(perf_score)
        })

    return render_template('admin/stats.html',
                           total_users=total_users,
                           total_views=total_views,
                           total_downloads=grand_total_downloads,
                           pending_requests=pending_requests,
                           req_total=req_total,
                           req_filled=req_filled,
                           req_rejected=req_rejected,
                           fill_rate=fill_rate,
                           total_content=total_content,
                           # Charts
                           top_movie_names=top_movie_names,
                           top_movie_views=top_movie_views,
                           top_series_names=top_series_names,
                           top_series_downloads=top_series_downloads,
                           req_stats=[req_pending, req_filled, req_rejected],
                           top_searches=top_searches,
                           recent_searches=recent_searches,
                           likely_no_result_terms=likely_no_result_terms,
                           server_stats=server_stats,
                           ad_total_views=ad_total_views,
                           ad_total_clicks=ad_total_clicks,
                           ad_overall_ctr=ad_overall_ctr,
                           ad_mobile_share=ad_mobile_share,
                           ad_labels=ad_labels,
                           ad_views_series=ad_views_series,
                           ad_clicks_series=ad_clicks_series,
                           ad_placement_rows=ad_placement_rows,
                           selected_range=range_key,
                           selected_range_label=selected_range_label,
                           selected_days=selected_days,
                           req_selected=req_selected,
                           req_7d=req_7d,
                           req_30d=req_30d,
                           stale_pending=stale_pending,
                           req_trend_labels=req_trend_labels,
                           req_trend_counts=req_trend_counts,
                           top_content_rows=top_content_rows
                           )


@admin_bp.route('/admin/watchlist-notify')
@login_required
@admin_required
def watchlist_notify_page():
    try:
        rows = WatchlistNotify.query.order_by(WatchlistNotify.date_added.desc()).limit(300).all()
    except Exception:
        db.session.rollback()
        rows = []

    total_movies = AllVideo.query.filter_by(type='movie').count()
    total_series = Series.query.count()
    total_trailers = Trailer.query.count()
    total_users = User.query.count()
    total_views = db.session.query(func.sum(AllVideo.views)).scalar() or 0
    total_requests = MovieRequest.query.filter_by(status='Pending').count()

    return render_template(
        'admin/watchlist_notify.html',
        rows=rows,
        total_movies=total_movies,
        total_series=total_series,
        total_trailers=total_trailers,
        total_users=total_users,
        total_views=total_views,
        total_requests=total_requests
    )


@admin_bp.route('/admin/watchlist-notify/mark/<int:row_id>')
@login_required
@admin_required
def mark_watchlist_notified(row_id):
    row = WatchlistNotify.query.get_or_404(row_id)
    try:
        row.notified = True
        db.session.commit()
        flash('Entry marked as notified.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Failed to update entry: {e}', 'error')
    return redirect(url_for('admin.watchlist_notify_page'))


@admin_bp.route('/admin/notification-settings', methods=['GET', 'POST'])
@login_required
@admin_required
def notification_settings():
    email_cfg = _get_email_provider_config()
    email_enabled, email_provider = _email_transport_status(email_cfg)
    smtp_cfg = email_cfg["smtp"]
    resend_cfg = email_cfg["resend"]

    tg_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    tg_default_chat = os.getenv("TELEGRAM_NOTIFY_CHAT_ID", "").strip()
    tg_enabled = bool(tg_bot_token)

    test_result = None

    if request.method == 'POST':
        action = (request.form.get('action') or '').strip()
        now_tag = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')

        if action == 'test_email':
            target_email = (request.form.get('test_email') or '').strip()
            if not target_email:
                test_result = {"ok": False, "message": "Enter an email address for test send."}
            elif not email_enabled:
                test_result = {"ok": False, "message": f"Email provider '{email_provider}' is not configured."}
            else:
                try:
                    plain_text = (
                        "This is a test notification from MaxCinema admin settings.\n\n"
                        f"Time: {now_tag}\n\n"
                        f"If you got this, {email_provider.upper()} works."
                    )
                    html_text = (
                        "<p>This is a test notification from MaxCinema admin settings.</p>"
                        f"<p>Time: {now_tag}</p>"
                        f"<p>If you got this, <strong>{email_provider.upper()}</strong> works.</p>"
                    )
                    ok, err = _send_email_notification(
                        to_email=target_email,
                        subject="MaxCinema Notification Test",
                        plain_text=plain_text,
                        html_body=html_text
                    )
                    if not ok:
                        raise RuntimeError(err or "email send failed")
                    test_result = {"ok": True, "message": f"Test email sent to {target_email}."}
                except Exception as e:
                    test_result = {"ok": False, "message": f"Email test failed: {e}"}

        elif action == 'test_telegram':
            if not tg_enabled:
                test_result = {"ok": False, "message": "Telegram bot is not configured. Set TELEGRAM_BOT_TOKEN first."}
            else:
                target_chat = (request.form.get('test_telegram_chat') or '').strip() or tg_default_chat
                if not target_chat:
                    test_result = {"ok": False, "message": "Enter a Telegram chat id/username or set TELEGRAM_NOTIFY_CHAT_ID."}
                else:
                    try:
                        payload = {
                            "chat_id": target_chat,
                            "text": f"MaxCinema Telegram test notification ({now_tag}).",
                            "disable_web_page_preview": True
                        }
                        resp = requests.post(
                            f"https://api.telegram.org/bot{tg_bot_token}/sendMessage",
                            json=payload,
                            timeout=15
                        )
                        if resp.ok:
                            test_result = {"ok": True, "message": f"Telegram test sent to {target_chat}."}
                        else:
                            test_result = {"ok": False, "message": f"Telegram test failed: {resp.text[:180]}"}
                    except Exception as e:
                        test_result = {"ok": False, "message": f"Telegram test failed: {e}"}
        else:
            test_result = {"ok": False, "message": "Unknown action."}

    return render_template(
        'admin/notification_settings.html',
        email_provider=email_provider,
        email_enabled=email_enabled,
        smtp_enabled=smtp_cfg["enabled"],
        smtp_host=smtp_cfg["host"],
        smtp_port=smtp_cfg["port"],
        smtp_user=smtp_cfg["user"],
        smtp_from=smtp_cfg["from"],
        smtp_use_ssl=smtp_cfg["use_ssl"],
        smtp_use_tls=smtp_cfg["use_tls"],
        resend_enabled=resend_cfg["enabled"],
        resend_from=resend_cfg["from"],
        resend_api_url=resend_cfg["api_url"],
        tg_enabled=tg_enabled,
        tg_default_chat=tg_default_chat,
        test_result=test_result
    )


@admin_bp.route('/admin/polls', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_polls():
    if request.method == 'POST':
        question = (request.form.get('question') or '').strip()
        options_raw = (request.form.get('options') or '').strip()
        make_active = request.form.get('is_active') == 'on'

        options = [x.strip() for x in options_raw.splitlines() if x.strip()]
        if not question or len(options) < 2:
            flash('Provide a question and at least 2 options.', 'error')
            return redirect(url_for('admin.manage_polls'))

        try:
            if make_active:
                WeeklyPoll.query.update({'is_active': False})

            poll = WeeklyPoll(question=question, is_active=make_active)
            db.session.add(poll)
            db.session.flush()
            for option_text in options[:8]:
                db.session.add(WeeklyPollOption(poll_id=poll.id, option_text=option_text))
            db.session.commit()
            flash('Poll created successfully.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating poll: {e}', 'error')
        return redirect(url_for('admin.manage_polls'))

    try:
        polls = WeeklyPoll.query.order_by(WeeklyPoll.date_added.desc()).limit(20).all()
    except Exception:
        db.session.rollback()
        polls = []

    total_movies = AllVideo.query.filter_by(type='movie').count()
    total_series = Series.query.count()
    total_trailers = Trailer.query.count()
    total_users = User.query.count()
    total_views = db.session.query(func.sum(AllVideo.views)).scalar() or 0
    total_requests = MovieRequest.query.filter_by(status='Pending').count()

    return render_template(
        'admin/polls.html',
        polls=polls,
        total_movies=total_movies,
        total_series=total_series,
        total_trailers=total_trailers,
        total_users=total_users,
        total_views=total_views,
        total_requests=total_requests
    )


@admin_bp.route('/admin/polls/activate/<int:poll_id>')
@login_required
@admin_required
def activate_poll(poll_id):
    poll = WeeklyPoll.query.get_or_404(poll_id)
    try:
        WeeklyPoll.query.update({'is_active': False})
        poll.is_active = True
        db.session.commit()
        flash('Poll activated.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Failed to activate poll: {e}', 'error')
    return redirect(url_for('admin.manage_polls'))


@admin_bp.route('/admin/polls/delete/<int:poll_id>')
@login_required
@admin_required
def delete_poll(poll_id):
    poll = WeeklyPoll.query.get_or_404(poll_id)
    try:
        db.session.delete(poll)
        db.session.commit()
        flash('Poll deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Failed to delete poll: {e}', 'error')
    return redirect(url_for('admin.manage_polls'))


@admin_bp.route('/admin/release-notify/<int:video_id>')
@login_required
@admin_required
def release_notify(video_id):
    video = AllVideo.query.get_or_404(video_id)
    summary = _send_release_notifications(video)
    if summary["queued"] == 0:
        flash("No pending subscribers to notify for this title.", "warning")
    else:
        flash(
            f"Notification run complete: email {summary['emailed']}, telegram {summary['telegram']}, marked {summary['marked']}/{summary['queued']}.",
            "success"
        )
        if summary["errors"]:
            flash(f"Some notifications failed ({len(summary['errors'])}). Check SMTP/Telegram config.", "warning")
    return redirect(request.referrer or url_for('admin.view_movies'))




@admin_bp.route('/admin/series/<int:series_id>/season/<int:season_num>/bulk-links', methods=['GET', 'POST'])
@login_required
def bulk_link_season(series_id, season_num):
    if not current_user.is_admin:
        abort(403)

    series = Series.query.get_or_404(series_id)
    season = Season.query.filter_by(series_id=series.id, season_number=season_num).first_or_404()
    episodes = Episode.query.filter_by(season_id=season.id).order_by(Episode.episode_number).all()

    if request.method == 'POST':
        raw_text = request.form.get('link_list', '').strip()
        links = [line.strip() for line in raw_text.split('\n') if line.strip()]

        # 👇 1. Check if user wants to use Telegram Load Balancing
        use_balancing = 'distribute_telegram' in request.form
        server_pool = None
        
        if use_balancing:
            # Fetch all active Telegram servers
            telegram_servers = StorageServer.query.filter_by(server_type='telegram', active=True).all()
            
            if telegram_servers:
                # Create a never-ending cycle: [Server A, Server B, Server A, Server B...]
                server_pool = cycle(telegram_servers)
            else:
                flash("⚠️ You checked 'Distribute' but no active 'telegram' servers were found!", "warning")

        if not links:
            flash("No links provided!", "error")
            return redirect(request.url)

        updated_count = 0

        for episode, link in zip(episodes, links):
            # --- CLEANING LOGIC (Extract Hash) ---
            clean_str = link.strip()
            extracted_hash = clean_str
            
            if "/watch/" in clean_str:
                extracted_hash = clean_str.rstrip('/').split('/')[-1]
            elif "start=" in clean_str:
                extracted_hash = clean_str.split('start=')[-1]
            else:
                extracted_hash = clean_str.rstrip('/').split('/')[-1]

            # Save the Hash
            episode.download_link = extracted_hash

            # 👇 2. Assign the Storage Server (Round-Robin)
            if server_pool:
                current_server = next(server_pool)
                episode.storage_server_id = current_server.id
            
            updated_count += 1

        try:
            db.session.commit()
            if server_pool:
                flash(f"✅ Success! Balanced {updated_count} episodes across {len(telegram_servers)} bots.", "success")
            else:
                flash(f"✅ Success! Updated {updated_count} episodes (No server assigned).", "success")
            
            return redirect(url_for('admin.view_series_specific', id=series_id, name=series.all_video.slug))
        except Exception as e:
            db.session.rollback()
            flash(f"Error saving links: {str(e)}", "error")

    return render_template('admin/bulk_links.html', series=series, season=season, episodes=episodes)





@admin_bp.route('/admin/incomplete-series')
@login_required
@admin_required
def view_incomplete_series():
    # Sidebar counters you already pass everywhere
    total_movies = AllVideo.query.filter_by(type='movie').count()
    total_series = AllVideo.query.filter_by(type='series').count()
    total_trailers = Trailer.query.count()
    total_users = User.query.count()
    total_views = db.session.query(func.sum(AllVideo.views)).scalar() or 0
    total_requests = MovieRequest.query.filter_by(status='Pending').count()

    q = (request.args.get("q") or "").strip()
    sort = (request.args.get("sort") or "updated").strip()     # updated, name, season, eps
    direction = (request.args.get("dir") or "desc").strip()    # asc/desc

    # --- latest season per series ---
    latest_season_subq = (
        db.session.query(
            Season.series_id.label("series_id"),
            func.max(Season.season_number).label("max_season_number")
        )
        .group_by(Season.series_id)
        .subquery()
    )
    LatestSeason = aliased(Season)

    base = (
        db.session.query(Series, AllVideo, LatestSeason)
        .join(AllVideo, AllVideo.id == Series.all_video_id)
        .join(latest_season_subq, latest_season_subq.c.series_id == Series.id)
        .join(
            LatestSeason,
            (LatestSeason.series_id == Series.id) &
            (LatestSeason.season_number == latest_season_subq.c.max_season_number)
        )
        .filter(AllVideo.type == 'series')
        .filter(LatestSeason.completed == False)
    )

    if q:
        base = base.filter(AllVideo.name.ilike(f"%{q}%"))

    # Sorting
    if sort == "name":
        col = AllVideo.name
    elif sort == "season":
        col = LatestSeason.season_number
    elif sort == "eps":
        col = LatestSeason.num_episodes
    else:
        col = LatestSeason.updated_at  # default

    if direction == "asc":
        base = base.order_by(col.asc().nullslast(), AllVideo.name.asc())
    else:
        base = base.order_by(col.desc().nullslast(), AllVideo.name.asc())

    rows = base.all()

    incomplete = []
    for series_obj, video_obj, season_obj in rows:
        incomplete.append({
            "series_id": video_obj.id,
            "slug": video_obj.slug,
            "title": video_obj.name,
            "season_id": season_obj.id,
            "season_number": season_obj.season_number,
            "season_num_episodes_field": season_obj.num_episodes or 0,
            "season_eps_count": len(season_obj.episodes),
            "updated_at": season_obj.updated_at,
        })

    return render_template(
        "admin/incomplete_series.html",
        incomplete=incomplete,
        q=q,
        sort=sort,
        direction=direction,
        total_movies=total_movies,
        total_series=total_series,
        total_trailers=total_trailers,
        total_users=total_users,
        total_views=total_views,
        total_requests=total_requests
    )


@admin_bp.route('/admin/season/<int:season_id>/set-completed', methods=['POST'])
@login_required
@admin_required
def set_season_completed(season_id):
    season = Season.query.get_or_404(season_id)
    season.completed = True
    season.updated_at = datetime.utcnow()
    db.session.commit()
    flash(f"Season {season.season_number} marked as completed.", "success")

    # keep user on same filtered list
    return redirect(request.referrer or url_for("admin.view_incomplete_series"))


@admin_bp.route('/admin/season/<int:season_id>/set-incomplete', methods=['POST'])
@login_required
@admin_required
def set_season_incomplete(season_id):
    season = Season.query.get_or_404(season_id)
    season.completed = False
    season.updated_at = datetime.utcnow()
    db.session.commit()
    flash(f"Season {season.season_number} marked as incomplete.", "success")
    return redirect(request.referrer or url_for("admin.view_incomplete_series"))


@admin_bp.route("/search")
@login_required
@admin_required
def search():
    q = (request.args.get("q") or "").strip()

    # Always return a page (even empty) so template doesn't crash
    if not q:
        return render_template("admin/search.html", q=q, movies=[], series=[], trailers=[], users=[])

    like = f"%{q}%"

    movies = (AllVideo.query
              .filter(AllVideo.type == "movie", AllVideo.name.ilike(like))
              .order_by(AllVideo.created_at.desc())
              .limit(20)
              .all())

    series = (AllVideo.query
              .filter(AllVideo.type == "series", AllVideo.name.ilike(like))
              .order_by(AllVideo.created_at.desc())
              .limit(20)
              .all())

    trailers = (Trailer.query
                .filter(Trailer.name.ilike(like))
                .order_by(Trailer.date_added.desc())
                .limit(20)
                .all())

    users = (User.query
             .filter(User.username.ilike(like))
             .order_by(User.date_created.desc())
             .limit(20)
             .all())

    return render_template(
        "admin/search.html",
        q=q,
        movies=movies,
        series=series,
        trailers=trailers,
        users=users,
    )

@admin_bp.route('/search-terms')
@admin_required
@login_required
def search_terms_page():
    if not current_user.is_admin:
        abort(403)

    page = request.args.get('page', 1, type=int)

    search_terms = SearchTerm.query.order_by(
        SearchTerm.count.desc(),
        SearchTerm.last_searched.desc()
    ).paginate(page=page, per_page=20, error_out=False)

    return render_template(
        'admin/search_terms.html',
        search_terms=search_terms
    )
