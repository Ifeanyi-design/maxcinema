import os
import smtplib
import time
from email.message import EmailMessage
from functools import wraps
from urllib.parse import parse_qs, unquote, urlparse

import requests
from flask import render_template, abort, url_for
from flask_login import current_user
from slugify import slugify

from . import admin_bp
from ..models import AllVideo, WatchlistNotify, EmailHistory, db, Trailer


def _has_download_payload(video):
    return bool((video.download_link or "").strip() or (video.dub_download_link or "").strip() or (video.backup_link or "").strip())


def _normalize_download_link(value, storage_server=None):
    if value is None:
        return None

    raw = str(value).strip()
    if not raw:
        return None

    parsed = urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        return raw

    if storage_server and getattr(storage_server, "base_url", None):
        base_parsed = urlparse((storage_server.base_url or "").strip())
        if base_parsed.netloc and parsed.netloc.lower() == base_parsed.netloc.lower():
            source_path = parsed.path or ""
            base_path = (base_parsed.path or "").rstrip("/")
            if base_path and source_path.startswith(f"{base_path}/"):
                source_path = source_path[len(base_path) + 1 :]
            else:
                source_path = source_path.lstrip("/")
            if source_path:
                return unquote(source_path)

    path_segments = [segment for segment in (parsed.path or "").split("/") if segment]
    if "watch" in path_segments:
        watch_index = path_segments.index("watch")
        if watch_index + 1 < len(path_segments):
            token = (path_segments[watch_index + 1] or "").strip()
            if token:
                return unquote(token)

    query = parse_qs(parsed.query or "")
    for key in ("code", "file", "id", "hash", "token"):
        values = query.get(key) or []
        if values and (values[0] or "").strip():
            return values[0].strip()

    return raw


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


def _send_telegram_notification(target, text, bot_token=None, default_chat_id=None):
    bot_token = (bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
    default_chat_id = (default_chat_id or os.getenv("TELEGRAM_NOTIFY_CHAT_ID", "")).strip()
    relay_url = os.getenv("TELEGRAM_RELAY_URL", "").strip()
    relay_secret = os.getenv("TELEGRAM_RELAY_SECRET", "").strip()
    target = (target or "").strip()

    if not bot_token and not relay_url:
        return False, "Telegram bot is not configured. Set TELEGRAM_BOT_TOKEN."

    chat_id = None
    message_text = text

    if target and target.lstrip("-").isdigit():
        chat_id = target
    elif target and default_chat_id:
        chat_id = default_chat_id
        mention = f"@{target.lstrip('@')}"
        message_text = f"{mention} {text}".strip()
    elif default_chat_id:
        chat_id = default_chat_id
    elif target:
        return False, "Telegram usernames cannot receive direct bot DMs. Set TELEGRAM_NOTIFY_CHAT_ID to a group/channel for username mentions, or collect numeric chat IDs."
    else:
        return False, "Set TELEGRAM_NOTIFY_CHAT_ID or provide a numeric Telegram chat ID."

    if relay_url:
        headers = {"Content-Type": "application/json"}
        if relay_secret:
            headers["Authorization"] = f"Bearer {relay_secret}"

        try:
            resp = requests.post(
                relay_url,
                headers=headers,
                json={
                    "chat_id": chat_id,
                    "text": message_text,
                    "disable_web_page_preview": False,
                },
                timeout=(10, 45)
            )
            if resp.ok:
                return True, ""
            return False, f"relay:{resp.status_code}:{resp.text[:180]}"
        except requests.exceptions.RequestException as e:
            return False, f"relay:{e}"

    last_error = ""
    for attempt in range(1, 4):
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": message_text, "disable_web_page_preview": False},
                timeout=(10, 45)
            )
            if resp.ok:
                return True, ""
            return False, resp.text[:180]
        except requests.exceptions.Timeout:
            last_error = f"Telegram API timed out on attempt {attempt}/3"
        except requests.exceptions.RequestException as e:
            last_error = str(e)
            break

        if attempt < 3:
            time.sleep(2)

    return False, last_error or "Telegram request failed"


def _send_release_notifications(video):
    pending_query = WatchlistNotify.query.filter_by(video_id=video.id, notified=False)
    queued = pending_query.count()
    if queued == 0:
        return {"queued": 0, "emailed": 0, "telegram": 0, "marked": 0, "errors": []}

    site_url = os.getenv("SITE_BASE_URL", "https://www.maxcinema.name.ng")
    if video.type == "movie":
        release_url = f"{site_url.rstrip('/')}/download/movie/{video.slug or slugify(video.name)}/{video.id}"
    else:
        release_url = f"{site_url.rstrip('/')}/download/series/{video.slug or slugify(video.name)}/s1/e1/{video.id}"

    plain_text = (
        f"Good news! '{video.name}' is now available on MaxCinema.\n\n"
        f"Open: {release_url}\n\n"
        "You requested this notification."
    )

    email_cfg = _get_email_provider_config()
    email_enabled, _ = _email_transport_status(email_cfg)

    tg_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    tg_default_chat = os.getenv("TELEGRAM_NOTIFY_CHAT_ID", "").strip()
    tg_enabled = bool(tg_bot_token)

    emailed = 0
    telegram = 0
    marked = 0
    errors = []
    batch_size = 20

    sender = "system"
    try:
        if getattr(current_user, "is_authenticated", False):
            sender = getattr(current_user, "email", "") or "admin"
    except Exception:
        sender = "system"

    while True:
        rows = (
            WatchlistNotify.query
            .filter_by(video_id=video.id, notified=False)
            .order_by(WatchlistNotify.id.asc())
            .limit(batch_size)
            .all()
        )
        if not rows:
            break

        for row in rows:
            sent_any = False

            if email_enabled and row.email:
                email_success = False
                email_error = None
                try:
                    html_text = render_template(
                        "emails/release_notification.html",
                        video=video,
                        release_url=release_url
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
                    email_success = True
                except Exception as e:
                    email_error = str(e)
                    errors.append(f"email:{row.email}:{email_error}")
                finally:
                    db.session.add(EmailHistory(
                        to_email=row.email,
                        subject=f"Now Available: {video.name}",
                        body=plain_text,
                        status="sent" if email_success else "failed",
                        error_message=None if email_success else email_error,
                        sent_by=sender,
                    ))

            if tg_enabled:
                try:
                    tg_target = (row.telegram or "").strip()
                    if tg_target:
                        ok, err = _send_telegram_notification(
                            tg_target,
                            plain_text,
                            bot_token=tg_bot_token,
                            default_chat_id=tg_default_chat
                        )
                        if ok:
                            telegram += 1
                            sent_any = True
                        else:
                            errors.append(f"telegram:{tg_target}:{err}")
                except Exception as e:
                    errors.append(f"telegram:{row.telegram}:{e}")

            if sent_any:
                row.notified = True
                marked += 1

            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                errors.append(f"commit:row:{row.id}:{e}")

    return {
        "queued": queued,
        "emailed": emailed,
        "telegram": telegram,
        "marked": marked,
        "errors": errors[:8]
    }


def _collect_manual_indexnow_urls(limit_per_type=25):
    urls = [
        url_for('main.index', _external=True),
        url_for('main.sitemap', _external=True),
        url_for('main.robots_txt', _external=True),
        url_for('main.trailer', _external=True),
        url_for('main.trending', type='movie', _external=True),
        url_for('main.trending', type='series', _external=True),
        url_for('main.release_calendar', _external=True),
        url_for('main.navbar', nav='all_movie', _external=True),
        url_for('main.navbar', nav='all_series', _external=True),
    ]

    latest_movies = (
        AllVideo.query
        .filter_by(type='movie', active=True)
        .order_by(AllVideo.date_added.desc())
        .limit(limit_per_type)
        .all()
    )
    latest_series = (
        AllVideo.query
        .filter_by(type='series', active=True)
        .order_by(AllVideo.date_added.desc())
        .limit(limit_per_type)
        .all()
    )
    latest_trailers = (
        Trailer.query
        .order_by(Trailer.date_added.desc())
        .limit(limit_per_type)
        .all()
    )

    for video in latest_movies + latest_series:
        from ..indexnow import urls_for_video
        urls.extend(urls_for_video(video))

    for trailer in latest_trailers:
        from ..indexnow import build_trailer_url
        trailer_url = build_trailer_url(trailer)
        if trailer_url:
            urls.append(trailer_url)

    return urls


def admin_required(func):
    @wraps(func)
    def decorated_view(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            return abort(403)
        return func(*args, **kwargs)
    return decorated_view
