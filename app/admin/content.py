import re
from urllib.parse import urlparse

from flask import render_template, redirect, url_for, request, flash
from flask_login import login_required

from . import admin_bp
from ..models import AllVideo, db, Trailer, MovieRequest, User, Series, Season, Episode, StorageServer
from ..indexnow import submit_for_video, submit_for_episode, urls_for_video, submit_indexnow_urls
from ..utils import ContentImporter
from .helpers import admin_required


def _extract_watch_code(text: str) -> str | None:
    m = re.search(r"/watch/([^/?#\s]+)", text)
    return m.group(1).strip() if m else None


def _normalize_bulk_link(raw_link: str) -> str:
    link = (raw_link or "").strip()
    if not link:
        return ""
    # If it's a full URL, try to extract the episode code from /watch/<code>
    code = _extract_watch_code(link)
    # Fallback: if the user pasted just the code (no /watch/ segment), keep it.
    return code if code else link


def normalize_bulk_links(links_text: str) -> list:
    """Split pasted text into individual episode codes/links.

    Handles normal newline-separated input, \\r\\n / lone \\r line endings,
    and the edge case where the paste collapses into a single line but still
    contains multiple /watch/<code> URLs jammed together.
    """
    text = (links_text or "").strip()
    if not text:
        return []

    lines = [l.strip() for l in re.split(r"[\r\n]+", text) if l.strip()]

    if len(lines) <= 1:
        codes = re.findall(r"/watch/([^/?#\s]+)", text)
        if len(codes) > 1:
            return [c.strip() for c in codes]

    return [_normalize_bulk_link(line) for line in lines]


@admin_bp.route('/import-tmdb', methods=['GET', 'POST'])
@login_required
@admin_required
def import_tmdb():
    if request.method == 'POST':
        try:
            importer = ContentImporter()
            tmdb_id = request.form.get('tmdb_id', '').strip()
            media_type = request.form.get('type', 'movie').strip()
            season_input = request.form.get('seasons', '').strip() or None
            episode_input = request.form.get('episodes', '').strip() or None

            if not tmdb_id:
                flash("Please enter a TMDB ID.", "error")
                return redirect(url_for('admin.import_tmdb'))

            if media_type == 'movie':
                result = importer.import_movie(int(tmdb_id))
            else:
                result = importer.import_series(int(tmdb_id), season_input, episode_input)

            flash(result, "success" if "Error" not in result else "error")
        except Exception as e:
            flash(f"Import failed: {str(e)}", "error")

        return redirect(url_for('admin.import_tmdb'))

    return render_template('admin/import.html')


@admin_bp.route('/series/<int:series_id>/season/<int:season_num>/bulk-links', methods=['GET', 'POST'])
@login_required
@admin_required
def bulk_link_season(series_id, season_num):
    series_obj = Series.query.get_or_404(series_id)
    season = Season.query.filter_by(series_id=series_obj.id, season_number=season_num).first_or_404()

    if request.method == 'POST':
        links_text = (request.form.get('link_list') or '').strip()
        links = [link for link in normalize_bulk_links(links_text) if link]

        # Which storage server these pasted links belong to (replaces the old
        # unused "distribute_telegram" checkbox with an explicit server pick).
        storage_server_id_raw = (request.form.get('storage_server_id') or '').strip()
        storage_server = None
        if storage_server_id_raw:
            try:
                storage_server = StorageServer.query.filter_by(
                    id=int(storage_server_id_raw), active=True
                ).first()
            except ValueError:
                storage_server = None

        if not storage_server:
            flash("Please select a valid, active storage server for these links.", "error")
            return redirect(url_for('admin.bulk_link_season', series_id=series_id, season_num=season_num))

        episodes = Episode.query.filter_by(season_id=season.id).order_by(Episode.episode_number).all()

        if not episodes:
            flash("No episodes found in this season.", "error")
            return redirect(url_for('admin.bulk_link_season', series_id=series_id, season_num=season_num))

        updated = 0
        for i, episode in enumerate(episodes):
            if i < len(links):
                episode.download_link = links[i]
                episode.storage_server_id = storage_server.id
                updated += 1

        db.session.commit()
        flash(f"Updated {updated} episode(s) with download links on {storage_server.name}.", "success")
        return redirect(url_for('admin.view_episodes', prev='serie', name=series_obj.all_video.slug, ns=season_num, season_id=season.id))

    episodes = Episode.query.filter_by(season_id=season.id).order_by(Episode.episode_number).all()
    storage_servers = StorageServer.query.filter_by(active=True).order_by(StorageServer.name).all()
    return render_template(
        'admin/bulk_links.html',
        series=series_obj,
        season=season,
        episodes=episodes,
        storage_servers=storage_servers,
    )


@admin_bp.route('/incomplete-content')
@login_required
@admin_required
def view_incomplete_content():
    total_movies = AllVideo.query.filter_by(type='movie').count()
    total_series = AllVideo.query.filter_by(type='series').count()
    total_trailers = Trailer.query.count()
    total_users = User.query.count()
    total_views = db.session.query(db.func.sum(AllVideo.views)).scalar() or 0
    total_requests = MovieRequest.query.filter_by(status='Pending').count()

    videos = AllVideo.query.filter_by(active=True).all()
    movies = []
    episodes = []
    for v in videos:
        has_link = bool((v.download_link or "").strip() or (v.dub_download_link or "").strip() or (v.backup_link or "").strip())
        if not has_link:
            if v.type == 'movie':
                movies.append(v)

    eps = Episode.query.all()
    for ep in eps:
        has_link = bool((ep.download_link or "").strip() or (ep.dub_download_link or "").strip() or (ep.backup_link or "").strip())
        if not has_link:
            episodes.append(ep)

    return render_template('admin/incomplete_content.html', movies=movies, episodes=episodes, total_movies=total_movies, total_series=total_series, total_trailers=total_trailers, total_users=total_users, total_views=total_views, total_requests=total_requests)


@admin_bp.route('/incomplete-series')
@login_required
@admin_required
def view_incomplete_series():
    total_movies = AllVideo.query.filter_by(type='movie').count()
    total_series = AllVideo.query.filter_by(type='series').count()
    total_trailers = Trailer.query.count()
    total_users = User.query.count()
    total_views = db.session.query(db.func.sum(AllVideo.views)).scalar() or 0
    total_requests = MovieRequest.query.filter_by(status='Pending').count()

    q = request.args.get('q', '').strip()
    sort = request.args.get('sort', 'updated').strip()
    direction = request.args.get('dir', 'desc').strip()

    all_series = AllVideo.query.filter_by(type='series', active=True).all()
    incomplete = []
    for s in all_series:
        if s.series and s.series.current_season_incomplete:
            current_season = None
            for season in s.series.seasons:
                if not season.completed:
                    current_season = season
                    break
            if current_season:
                incomplete.append({
                    'title': s.name,
                    'slug': s.slug,
                    'season_number': current_season.season_number,
                    'season_eps_count': len(current_season.episodes),
                    'season_num_episodes_field': current_season.num_episodes if hasattr(current_season, 'num_episodes') else None,
                    'updated_at': s.updated_at,
                    'series_id': s.id,
                    'season_id': current_season.id,
                })

    if sort == 'name':
        incomplete.sort(key=lambda x: x['title'] or '', reverse=(direction == 'desc'))
    elif sort == 'season':
        incomplete.sort(key=lambda x: x['season_number'], reverse=(direction == 'desc'))
    elif sort == 'eps':
        incomplete.sort(key=lambda x: x['season_eps_count'], reverse=(direction == 'desc'))
    else:
        incomplete.sort(key=lambda x: x['updated_at'] or '', reverse=(direction == 'desc'))

    if q:
        incomplete = [i for i in incomplete if q.lower() in (i['title'] or '').lower()]

    return render_template('admin/incomplete_series.html', incomplete=incomplete, q=q, sort=sort, direction=direction, total_movies=total_movies, total_series=total_series, total_trailers=total_trailers, total_users=total_users, total_views=total_views, total_requests=total_requests)


@admin_bp.route('/season/<int:season_id>/set-completed', methods=['POST'])
@login_required
@admin_required
def set_season_completed(season_id):
    season = Season.query.get_or_404(season_id)
    season.completed = True
    db.session.commit()
    flash(f"Season {season.season_number} marked as completed.", "success")
    return redirect(url_for('admin.view_episodes', prev='serie', name=season.series.all_video.slug, ns=season.season_number, season_id=season.id))


@admin_bp.route('/season/<int:season_id>/set-incomplete', methods=['POST'])
@login_required
@admin_required
def set_season_incomplete(season_id):
    season = Season.query.get_or_404(season_id)
    season.completed = False
    db.session.commit()
    flash(f"Season {season.season_number} marked as incomplete.", "success")
    return redirect(url_for('admin.view_episodes', prev='serie', name=season.series.all_video.slug, ns=season.season_number, season_id=season.id))


@admin_bp.route('/search')
@login_required
@admin_required
def search():
    total_movies = AllVideo.query.filter_by(type='movie').count()
    total_series = AllVideo.query.filter_by(type='series').count()
    total_trailers = Trailer.query.count()
    total_users = User.query.count()
    total_views = db.session.query(db.func.sum(AllVideo.views)).scalar() or 0
    total_requests = MovieRequest.query.filter_by(status='Pending').count()

    q = request.args.get('q', '').strip()
    movies = []
    series = []
    trailers = []
    users = []
    if q:
        results = AllVideo.query.filter(AllVideo.name.ilike(f'%{q}%')).all()
        for v in results:
            if v.type == 'movie':
                movies.append(v)
            elif v.type == 'series':
                series.append(v)
        trailers = Trailer.query.filter(Trailer.name.ilike(f'%{q}%')).all()
        users = User.query.filter(User.username.ilike(f'%{q}%')).all()

    return render_template('admin/search.html', movies=movies, series=series, trailers=trailers, users=users, q=q, total_movies=total_movies, total_series=total_series, total_trailers=total_trailers, total_users=total_users, total_views=total_views, total_requests=total_requests)


@admin_bp.route('/indexnow/resubmit', methods=['POST'])
@login_required
@admin_required
def resubmit_indexnow():
    from .helpers import _collect_manual_indexnow_urls
    try:
        urls = _collect_manual_indexnow_urls()
        from ..indexnow import submit_indexnow_urls
        result = submit_indexnow_urls(urls)
    except Exception as e:
        db.session.rollback()
        flash(f'IndexNow resubmit failed: {e}', 'error')
        return redirect(url_for('admin.dashboard'))

    if result.get('ok'):
        flash(f"IndexNow resubmitted {len(result.get('submitted', []))} URL(s).", 'success')
    else:
        reason = result.get('reason') or result.get('response_text') or 'unknown error'
        status = result.get('status_code')
        details = f" ({status})" if status else ""
        flash(f"IndexNow resubmit did not complete{details}: {reason}", 'warning')

    return redirect(url_for('admin.dashboard'))
