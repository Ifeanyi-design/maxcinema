import os
from datetime import datetime

from flask import render_template, redirect, url_for, request, flash
from flask_login import login_required
from sqlalchemy import func

from . import admin_bp
from ..models import AllVideo, db, Trailer, MovieRequest, User, Series, WatchlistNotify
from .helpers import (
    admin_required, _get_email_provider_config, _email_transport_status,
    _send_email_notification, _send_telegram_notification, _send_release_notifications,
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
                    test_result = {"ok": False, "message": "Enter a numeric chat ID, or set TELEGRAM_NOTIFY_CHAT_ID for username mentions."}
                else:
                    ok, err = _send_telegram_notification(
                        target_chat,
                        f"MaxCinema Telegram test notification ({now_tag}).",
                        bot_token=tg_bot_token,
                        default_chat_id=tg_default_chat
                    )
                    if ok:
                        test_result = {"ok": True, "message": f"Telegram test sent using {target_chat}."}
                    else:
                        test_result = {"ok": False, "message": f"Telegram test failed: {err}"}
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


@admin_bp.route('/admin/release-notify/<int:video_id>')
@login_required
@admin_required
def release_notify(video_id):
    video = AllVideo.query.get_or_404(video_id)
    summary = _send_release_notifications(video)
    if summary["queued"] == 0:
        flash("No pending notifications for this video.", "info")
    elif summary["errors"]:
        flash(
            f"Notifications: email {summary['emailed']}, telegram {summary['telegram']}, "
            f"marked {summary['marked']}/{summary['queued']}. Errors: {'; '.join(summary['errors'][:3])}",
            "warning"
        )
    else:
        flash(
            f"Notifications sent: email {summary['emailed']}, telegram {summary['telegram']}, "
            f"marked {summary['marked']}/{summary['queued']}.",
            "success"
        )
    return redirect(url_for('admin.dashboard'))
