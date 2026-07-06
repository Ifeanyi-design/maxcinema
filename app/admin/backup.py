"""Admin backup dashboard — UI to interact with the backup service API."""

import os
import threading

import requests
from flask import render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required

from . import admin_bp
from .helpers import admin_required
from ..models import AllVideo, Trailer, User, db


def _backup_api_url(endpoint=""):
    """Build backup service API URL."""
    base = os.environ.get("BACKUP_SERVICE_URL", "http://localhost:8080").rstrip("/")
    return f"{base}/{endpoint.lstrip('/')}"


def _backup_api_key():
    """Get backup service API key."""
    return os.environ.get("BACKUP_API_KEY", "")


def _call_backup_api(endpoint, method="GET", json_data=None, files=None, timeout=300):
    """Call the backup service API and return (success, data_or_error)."""
    url = _backup_api_url(endpoint)
    api_key = _backup_api_key()

    if not api_key:
        return False, "BACKUP_API_KEY not configured"

    headers = {"X-API-Key": api_key}
    if not files:
        headers["Content-Type"] = "application/json"

    try:
        if method == "POST":
            resp = requests.post(url, headers=headers, json=json_data, files=files, timeout=timeout)
        else:
            resp = requests.get(url, headers=headers, timeout=timeout)

        if resp.status_code == 200:
            return True, resp.json()
        return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
    except requests.ConnectionError:
        return False, "Backup service not reachable. Is it running?"
    except requests.Timeout:
        return False, "Backup service timed out"
    except Exception as e:
        return False, str(e)


def _run_backup_async(include_telegram):
    """Run backup in background thread."""
    try:
        _call_backup_api("backup", method="POST", json_data={"include_telegram": include_telegram}, timeout=600)
    except Exception:
        pass


@admin_bp.route('/backup')
@login_required
@admin_required
def backup_dashboard():
    """Backup service dashboard."""
    total_movies = AllVideo.query.filter_by(type='movie').count()
    total_series = AllVideo.query.filter_by(type='series').count()
    total_trailers = Trailer.query.count()
    total_users = User.query.count()
    total_views = db.session.query(db.func.sum(AllVideo.views)).scalar() or 0
    total_requests = 0

    status_ok, status_data = _call_backup_api("health")
    list_ok, list_data = _call_backup_api("list")
    detail_ok, detail_data = _call_backup_api("status")

    backups = []
    service_reachable = False
    latest_backup = None
    telegram_configured = False

    if status_ok:
        service_reachable = True

    if list_ok and isinstance(list_data, dict):
        backups = list_data.get("backups", [])

    if detail_ok and isinstance(detail_data, dict):
        latest_backup = detail_data.get("latest_backup")
        telegram_configured = detail_data.get("telegram_configured", False)

    return render_template(
        "admin/backup.html",
        service_reachable=service_reachable,
        backups=backups,
        latest_backup=latest_backup,
        telegram_configured=telegram_configured,
        backup_service_url=os.environ.get("BACKUP_SERVICE_URL", "http://localhost:8080"),
        total_movies=total_movies,
        total_series=total_series,
        total_trailers=total_trailers,
        total_users=total_users,
        total_views=total_views,
        total_requests=total_requests,
    )


@admin_bp.route('/backup/trigger', methods=['POST'])
@login_required
@admin_required
def backup_trigger():
    """Trigger a new backup (async, returns JSON)."""
    include_telegram = request.form.get("include_telegram", "on") == "on"

    thread = threading.Thread(target=_run_backup_async, args=(include_telegram,), daemon=True)
    thread.start()

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"success": True, "message": "Backup started"})

    flash("Backup started in background. It may take a few minutes.", "info")
    return redirect(url_for("admin.backup_dashboard"))


@admin_bp.route('/backup/restore', methods=['POST'])
@login_required
@admin_required
def backup_restore():
    """Trigger a restore from a backup file or Telegram."""
    source = request.form.get("source", "local").strip()
    filepath = request.form.get("filepath", "").strip()
    telegram_file_id = request.form.get("telegram_file_id", "").strip()

    json_data = {}
    if source == "telegram":
        if telegram_file_id:
            json_data["telegram_file_id"] = telegram_file_id
        else:
            json_data["use_latest_telegram"] = True
    else:
        if not filepath:
            flash("No backup file selected.", "danger")
            return redirect(url_for("admin.backup_dashboard"))
        json_data["filepath"] = filepath

    ok, data = _call_backup_api("restore", method="POST", json_data=json_data, timeout=600)

    if ok:
        duration = data.get("duration", "?")
        flash(f"Restore completed in {duration}s", "success")
    else:
        flash(f"Restore failed: {data}", "danger")

    return redirect(url_for("admin.backup_dashboard"))


@admin_bp.route('/backup/upload', methods=['POST'])
@login_required
@admin_required
def backup_upload():
    """Upload a backup file to the backup service."""
    backup_file = request.files.get("backup_file")
    if not backup_file or not backup_file.filename:
        flash("No file selected.", "danger")
        return redirect(url_for("admin.backup_dashboard"))

    filename = backup_file.filename
    files = {"file": (filename, backup_file.stream, backup_file.content_type)}

    ok, data = _call_backup_api("upload", method="POST", files=files, timeout=300)

    if ok:
        flash(f"Backup file '{filename}' uploaded successfully.", "success")
    else:
        flash(f"Upload failed: {data}", "danger")

    return redirect(url_for("admin.backup_dashboard"))
