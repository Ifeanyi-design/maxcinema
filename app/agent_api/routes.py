import re
from datetime import date, datetime, timedelta

from flask import current_app, jsonify, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from ..extensions import db
from ..models import AllVideo, Episode, Genre, Season, StorageServer
from ..utils import ContentImporter
from . import agent_api_bp
from .auth import agent_required, exchange_pairing_code, write_audit


LINK_FIELDS = {
    "primary": "download_link",
    "dub": "dub_download_link",
    "backup": "backup_link",
}


def _value(obj, name, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _iso(value):
    return value.isoformat() if value else None


def _today_lagos():
    return (datetime.utcnow() + timedelta(hours=1)).date()


def _video_payload(video):
    return {
        "id": video.id,
        "name": video.name,
        "slug": video.slug,
        "type": video.type,
        "tmdb_id": video.tmdb_id,
        "description": video.description,
        "poster": video.image,
        "release_date": _iso(video.released_date),
        "year": video.year_produced,
        "country": video.country,
        "language": video.language,
        "rating": video.rating,
        "genres": [genre.name for genre in video.genres],
        "active": bool(video.active),
        "coming_soon": bool(video.coming_soon),
        "featured": bool(video.featured),
        "trending": bool(video.trending),
        "has_primary_link": bool((video.download_link or "").strip()),
        "has_dub_link": bool((video.dub_download_link or "").strip()),
        "has_backup_link": bool((video.backup_link or "").strip()),
    }


def _normalize_code(raw):
    value = (raw or "").strip()
    if not value:
        return ""
    match = re.search(r"/watch/([^/?#\s]+)", value)
    if match:
        return match.group(1).strip()
    match = re.search(r"t\.me/[^/?#\s]+\?start=([^/?#&\s]+)", value)
    if match:
        return match.group(1).strip()
    return value


def _current_link(target, track):
    return (getattr(target, LINK_FIELDS[track], None) or "").strip()


def _plan_serializer():
    return URLSafeTimedSerializer(
        current_app.config["SECRET_KEY"],
        salt="maxcinema-agent-link-plan-v1",
    )


def _json_error(error, message, status=400, **extra):
    payload = {"error": error, "message": message}
    payload.update(extra)
    return jsonify(payload), status


@agent_api_bp.post("/pair")
def pair_agent():
    body = request.get_json(silent=True) or {}
    result, error = exchange_pairing_code(
        body.get("code"),
        label=body.get("label") or "Content management agent",
    )
    if error:
        return _json_error("pairing_failed", error, 401)
    return jsonify(result), 201


@agent_api_bp.get("/capabilities")
@agent_required("content:read")
def capabilities():
    return jsonify({
        "api": "MaxCinema Content Agent API",
        "version": "1",
        "base_path": "/api/agent/v1",
        "default_link_policy": "fill_missing",
        "replacement_policy": "preview_then_confirm",
        "episode_import_policy": (
            "Only episodes with a confirmed air_date on or before the current "
            "UTC date are imported. Future or undated episodes are skipped."
        ),
        "capabilities": [
            "tmdb.search",
            "library.search",
            "library.update",
            "movie.import",
            "series.import",
            "series.sync",
            "series.status",
            "storage.list",
            "links.preview",
            "links.apply",
        ],
        "agent_responsibilities": [
            "Read Telegram TXT exports and preserve each filename/code pair.",
            "Interpret filenames and determine season/episode numbers.",
            "Ask the user when TMDB results or filename mappings are ambiguous.",
            "Only change featured/trending when the user explicitly requests it.",
            "Obtain user approval before applying any link replacement.",
        ],
    })


@agent_api_bp.get("/openapi.json")
@agent_required("content:read")
def openapi_document():
    return jsonify({
        "openapi": "3.1.0",
        "info": {
            "title": "MaxCinema Content Agent API",
            "version": "1.0.0",
            "description": (
                "Controlled content operations for an external AI agent. "
                "The agent performs filename reasoning; the API validates and applies structured assignments."
            ),
        },
        "servers": [{"url": "/api/agent/v1"}],
        "security": [{"BearerAuth": []}],
        "components": {
            "securitySchemes": {
                "BearerAuth": {"type": "http", "scheme": "bearer"}
            }
        },
        "paths": {
            "/tmdb/search": {"get": {"summary": "Search TMDB movie and TV candidates"}},
            "/library/search": {"get": {"summary": "Search existing MaxCinema content"}},
            "/series/{video_id}/status": {"get": {"summary": "Read seasons, released episodes, and link status"}},
            "/series/{video_id}/sync": {"post": {"summary": "Manually sync a series from TMDB"}},
            "/movies/import": {"post": {"summary": "Import a movie by TMDB ID"}},
            "/series/import": {"post": {"summary": "Import a series by TMDB ID"}},
            "/library/{video_id}": {"patch": {"summary": "Update allowlisted movie/series metadata"}},
            "/seasons/{season_id}": {"patch": {"summary": "Update season metadata"}},
            "/episodes/{episode_id}": {"patch": {"summary": "Update episode metadata"}},
            "/storage-servers": {"get": {"summary": "List active storage servers"}},
            "/links/preview": {"post": {"summary": "Validate a movie or episode link assignment"}},
            "/links/apply": {"post": {"summary": "Apply a previously previewed link plan"}},
        },
    })


@agent_api_bp.get("/tmdb/search")
@agent_required("content:read")
def tmdb_search():
    query = (request.args.get("q") or "").strip()
    media_type = (request.args.get("type") or "all").strip().lower()
    if len(query) < 2:
        return _json_error("invalid_query", "Search query must contain at least two characters.")
    if media_type not in {"all", "movie", "series"}:
        return _json_error("invalid_type", "type must be all, movie, or series.")

    try:
        from tmdbv3api import Movie as TMDBMovie, TV as TMDBTV
        candidates = []
        if media_type in {"all", "movie"}:
            for item in (TMDBMovie().search(query) or [])[:10]:
                candidates.append({
                    "tmdb_id": _value(item, "id"),
                    "type": "movie",
                    "title": _value(item, "title") or _value(item, "original_title"),
                    "release_date": _value(item, "release_date"),
                    "overview": _value(item, "overview"),
                    "poster_path": _value(item, "poster_path"),
                    "rating": _value(item, "vote_average"),
                })
        if media_type in {"all", "series"}:
            for item in (TMDBTV().search(query) or [])[:10]:
                candidates.append({
                    "tmdb_id": _value(item, "id"),
                    "type": "series",
                    "title": _value(item, "name") or _value(item, "original_name"),
                    "release_date": _value(item, "first_air_date"),
                    "overview": _value(item, "overview"),
                    "poster_path": _value(item, "poster_path"),
                    "rating": _value(item, "vote_average"),
                })
        return jsonify({"query": query, "results": candidates})
    except Exception:
        current_app.logger.exception("TMDB search failed")
        return _json_error("tmdb_search_failed", "TMDB search failed. Check the TMDB configuration.", 502)


@agent_api_bp.get("/library/search")
@agent_required("content:read")
def library_search():
    query = (request.args.get("q") or "").strip()
    kind = (request.args.get("type") or "").strip().lower()
    tmdb_id = request.args.get("tmdb_id", type=int)
    limit = min(max(request.args.get("limit", 20, type=int), 1), 50)

    if not query and not tmdb_id:
        return _json_error("missing_search_term", "Supply q or tmdb_id.")
    statement = AllVideo.query
    if query:
        statement = statement.filter(AllVideo.name.ilike(f"%{query}%"))
    if tmdb_id:
        statement = statement.filter(AllVideo.tmdb_id == tmdb_id)
    if kind in {"movie", "series"}:
        statement = statement.filter(AllVideo.type == kind)
    items = statement.order_by(AllVideo.updated_at.desc()).limit(limit).all()
    return jsonify({"count": len(items), "results": [_video_payload(item) for item in items]})


@agent_api_bp.get("/storage-servers")
@agent_required("content:read")
def list_storage_servers():
    servers = StorageServer.query.filter_by(active=True).order_by(StorageServer.name).all()
    return jsonify({
        "results": [
            {"id": server.id, "name": server.name, "type": server.server_type}
            for server in servers
        ]
    })


@agent_api_bp.get("/series/<int:video_id>/status")
@agent_required("content:read")
def series_status(video_id):
    video = AllVideo.query.filter_by(id=video_id, type="series").first()
    if not video or not video.series:
        return _json_error("not_found", "Series was not found.", 404)

    seasons = []
    for season in video.series.seasons:
        episodes = []
        for episode in season.episodes:
            has_primary = bool((episode.download_link or "").strip())
            air_date = episode.released_date
            released = bool(air_date and air_date <= _today_lagos())
            episodes.append({
                "id": episode.id,
                "episode_number": episode.episode_number,
                "name": episode.name,
                "release_date": _iso(air_date),
                "release_state": "released" if released else ("upcoming" if air_date else "unknown"),
                "coming_soon": bool(episode.coming_soon and not released and not has_primary),
                "has_primary_link": has_primary,
                "has_dub_link": bool((episode.dub_download_link or "").strip()),
                "has_backup_link": bool((episode.backup_link or "").strip()),
                "storage_server_id": episode.storage_server_id,
            })
        seasons.append({
            "id": season.id,
            "season_number": season.season_number,
            "release_date": _iso(season.release_date),
            "completed": bool(season.completed),
            "episodes_total": len(episodes),
            "episodes_released": sum(1 for item in episodes if item["release_state"] == "released"),
            "episodes_missing_primary_link": sum(
                1 for item in episodes
                if item["release_state"] == "released" and not item["has_primary_link"]
            ),
            "episodes": episodes,
        })
    return jsonify({
        "series": _video_payload(video),
        "series_id": video.series.id,
        "seasons": seasons,
    })


def _import_response(result, video):
    status = getattr(result, "status", "error")
    return {
        "status": status,
        "message": str(result),
        "content": _video_payload(video) if video else None,
        "created": getattr(result, "created", {}) or {},
        "updated": getattr(result, "updated", 0),
        "skipped": getattr(result, "skipped", []) or [],
    }


@agent_api_bp.post("/movies/import")
@agent_required("content:write")
def import_movie():
    body = request.get_json(silent=True) or {}
    tmdb_id = body.get("tmdb_id")
    if not str(tmdb_id or "").isdigit():
        return _json_error("invalid_tmdb_id", "tmdb_id must be a numeric TMDB movie ID.")
    result = ContentImporter().import_movie(int(tmdb_id))
    video = AllVideo.query.filter_by(tmdb_id=int(tmdb_id), type="movie").first()
    if getattr(result, "status", None) == "error":
        return jsonify(_import_response(result, video)), 422
    if video:
        write_audit("movie.import", "movie", video.id, {"tmdb_id": int(tmdb_id), "status": result.status})
        db.session.commit()
    return jsonify(_import_response(result, video)), 200


@agent_api_bp.post("/series/import")
@agent_required("content:write")
def import_series():
    body = request.get_json(silent=True) or {}
    tmdb_id = body.get("tmdb_id")
    if not str(tmdb_id or "").isdigit():
        return _json_error("invalid_tmdb_id", "tmdb_id must be a numeric TMDB TV ID.")
    seasons = body.get("seasons")
    season_input = ",".join(str(value) for value in seasons) if isinstance(seasons, list) else seasons
    result = ContentImporter().import_series(int(tmdb_id), season_input, body.get("episodes"))
    video = AllVideo.query.filter_by(tmdb_id=int(tmdb_id), type="series").first()
    if getattr(result, "status", None) == "error":
        return jsonify(_import_response(result, video)), 422
    if video:
        write_audit("series.import", "series", video.id, {"tmdb_id": int(tmdb_id), "status": result.status})
        db.session.commit()
    return jsonify(_import_response(result, video)), 200


@agent_api_bp.post("/series/<int:video_id>/sync")
@agent_required("content:write")
def sync_series(video_id):
    video = AllVideo.query.filter_by(id=video_id, type="series").first()
    if not video or not video.tmdb_id:
        return _json_error("tmdb_link_missing", "Series does not have a saved TMDB ID.", 404)
    body = request.get_json(silent=True) or {}
    seasons = body.get("seasons")
    season_input = ",".join(str(value) for value in seasons) if isinstance(seasons, list) else seasons
    result = ContentImporter().import_series(video.tmdb_id, season_input, body.get("episodes"))
    db.session.refresh(video)
    write_audit("series.sync", "series", video.id, {
        "tmdb_id": video.tmdb_id,
        "status": getattr(result, "status", "unknown"),
    })
    db.session.commit()
    if getattr(result, "status", None) == "error":
        return jsonify(_import_response(result, video)), 422
    return jsonify(_import_response(result, video))


def _parse_date(value, field_name):
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise ValueError(f"{field_name} must use YYYY-MM-DD.")


@agent_api_bp.patch("/library/<int:video_id>")
@agent_required("content:write")
def update_library_item(video_id):
    video = AllVideo.query.get_or_404(video_id)
    body = request.get_json(silent=True) or {}
    allowed = {
        "name", "description", "image", "released_date", "year_produced",
        "country", "language", "trailer_url", "active", "coming_soon",
    }
    editorial = {"featured", "trending"}
    unknown = set(body) - allowed - editorial - {"editorial_reason"}
    if unknown:
        return _json_error("unsupported_fields", "One or more fields are not editable through this endpoint.", 400,
                           fields=sorted(unknown))
    if editorial.intersection(body):
        reason = (body.get("editorial_reason") or "").strip()
        if len(reason) < 8:
            return _json_error(
                "editorial_reason_required",
                "Changing featured/trending requires an explicit editorial_reason describing the user's instruction.",
            )
    try:
        for field in ("name", "description", "image", "country", "language", "trailer_url"):
            if field in body:
                value = body[field]
                if value is not None and not isinstance(value, str):
                    return _json_error("invalid_field", f"{field} must be a string or null.")
                setattr(video, field, value.strip() if isinstance(value, str) else None)
        if "released_date" in body:
            video.released_date = _parse_date(body["released_date"], "released_date")
        if "genres" in body:
            names = body["genres"]
            if not isinstance(names, list) or any(not isinstance(name, str) or not name.strip() for name in names):
                return _json_error("invalid_field", "genres must be a list of non-empty genre names.")
            if len(names) > 20:
                return _json_error("invalid_field", "A maximum of 20 genres may be assigned.")
            genre_objects = []
            for name in dict.fromkeys(name.strip() for name in names):
                genre = Genre.query.filter_by(name=name).first()
                if not genre:
                    genre = Genre(name=name[:50])
                    db.session.add(genre)
                genre_objects.append(genre)
            video.genres = genre_objects
        if "year_produced" in body:
            value = body["year_produced"]
            if value is not None and (not isinstance(value, int) or value < 1870 or value > 2200):
                return _json_error("invalid_field", "year_produced must be a plausible year or null.")
            video.year_produced = value
        for field in ("active", "coming_soon", "featured", "trending"):
            if field in body:
                if not isinstance(body[field], bool):
                    return _json_error("invalid_field", f"{field} must be a boolean.")
                setattr(video, field, body[field])
        if "released_date" in body:
            release_date = video.released_date
            video.coming_soon = bool(release_date and release_date > _today_lagos())
        if "name" in body and video.name:
            from slugify import slugify
            base = slugify(video.name) or f"content-{video.id}"
            candidate = base
            suffix = 2
            while AllVideo.query.filter(AllVideo.slug == candidate, AllVideo.id != video.id).first():
                candidate = f"{base}-{suffix}"
                suffix += 1
            video.slug = candidate
        write_audit("library.update", video.type, video.id, {
            "fields": sorted(set(body) - {"editorial_reason"}),
            "editorial_reason": body.get("editorial_reason"),
        })
        db.session.commit()
        return jsonify({"status": "success", "content": _video_payload(video)})
    except ValueError as exc:
        db.session.rollback()
        return _json_error("invalid_field", str(exc))


@agent_api_bp.patch("/seasons/<int:season_id>")
@agent_required("content:write")
def update_season(season_id):
    season = Season.query.get_or_404(season_id)
    body = request.get_json(silent=True) or {}
    allowed = {"description", "cast", "release_date", "completed", "image", "trailer_url"}
    unknown = set(body) - allowed
    if unknown:
        return _json_error("unsupported_fields", "One or more season fields are not editable.", 400,
                           fields=sorted(unknown))
    for field in ("description", "cast", "image", "trailer_url"):
        if field in body:
            value = body[field]
            if value is not None and not isinstance(value, str):
                return _json_error("invalid_field", f"{field} must be a string or null.")
            setattr(season, field, value.strip() if isinstance(value, str) else None)
    if "release_date" in body:
        try:
            season.release_date = _parse_date(body["release_date"], "release_date")
        except ValueError as exc:
            return _json_error("invalid_field", str(exc))
    if "completed" in body:
        if not isinstance(body["completed"], bool):
            return _json_error("invalid_field", "completed must be a boolean.")
        season.completed = body["completed"]
    write_audit("season.update", "season", season.id, {"fields": sorted(body)})
    db.session.commit()
    return jsonify({
        "status": "success",
        "season": {
            "id": season.id,
            "season_number": season.season_number,
            "release_date": _iso(season.release_date),
            "completed": bool(season.completed),
        },
    })


@agent_api_bp.patch("/episodes/<int:episode_id>")
@agent_required("content:write")
def update_episode(episode_id):
    episode = Episode.query.get_or_404(episode_id)
    body = request.get_json(silent=True) or {}
    allowed = {"name", "description", "released_date", "coming_soon"}
    unknown = set(body) - allowed
    if unknown:
        return _json_error("unsupported_fields", "One or more fields are not editable.", 400,
                           fields=sorted(unknown))
    try:
        for field in ("name", "description"):
            if field in body:
                value = body[field]
                if value is not None and not isinstance(value, str):
                    return _json_error("invalid_field", f"{field} must be a string or null.")
                setattr(episode, field, value.strip() if isinstance(value, str) else None)
        if "released_date" in body:
            episode.released_date = _parse_date(body["released_date"], "released_date")
        if "coming_soon" in body:
            if not isinstance(body["coming_soon"], bool):
                return _json_error("invalid_field", "coming_soon must be a boolean.")
            episode.coming_soon = body["coming_soon"]
        if "released_date" in body:
            episode.coming_soon = bool(
                episode.released_date and episode.released_date > _today_lagos()
            )
        write_audit("episode.update", "episode", episode.id, {"fields": sorted(body)})
        db.session.commit()
        return jsonify({
            "status": "success",
            "episode": {
                "id": episode.id,
                "episode_number": episode.episode_number,
                "name": episode.name,
                "released_date": _iso(episode.released_date),
                "coming_soon": bool(episode.coming_soon),
            },
        })
    except ValueError as exc:
        db.session.rollback()
        return _json_error("invalid_field", str(exc))


@agent_api_bp.post("/links/preview")
@agent_required("links:write")
def preview_links():
    body = request.get_json(silent=True) or {}
    track = (body.get("track") or "primary").strip().lower()
    mode = (body.get("mode") or "fill_missing").strip().lower()
    requested_replace = body.get("replace_existing") is True
    replace_existing = mode == "replace" and requested_replace
    if track not in LINK_FIELDS:
        return _json_error("invalid_track", "track must be primary, dub, or backup.")
    if mode not in {"fill_missing", "replace"}:
        return _json_error("invalid_mode", "mode must be fill_missing or replace.")
    if mode == "replace" and not requested_replace:
        return _json_error("replacement_flag_required", "mode=replace also requires replace_existing=true.")
    if mode == "fill_missing" and requested_replace:
        return _json_error("invalid_replacement_policy", "Use mode=replace to request replacement; fill_missing never replaces.")

    server_id = body.get("storage_server_id")
    server = StorageServer.query.filter_by(id=server_id, active=True).first() if server_id else None
    if not server:
        return _json_error("invalid_storage_server", "Choose an active storage_server_id.")

    operations = []
    skipped = []
    warnings = []
    is_movie = body.get("movie_id") is not None

    if is_movie:
        video = AllVideo.query.filter_by(id=body.get("movie_id"), type="movie").first()
        if not video:
            return _json_error("movie_not_found", "Movie was not found.", 404)
        code = _normalize_code(body.get("code"))
        if not code or len(code) > 500:
            return _json_error("invalid_code", "A valid non-empty download code is required.")
        existing = _current_link(video, track)
        if existing == code:
            skipped.append({"target": "movie", "reason": "already_has_this_code"})
        elif existing and not replace_existing:
            skipped.append({"target": "movie", "reason": "existing_link_preserved"})
        else:
            operations.append({
                "target_type": "movie",
                "target_id": video.id,
                "track": track,
                "code": code,
                "existing_code": existing,
            })
    else:
        series_id = body.get("series_id")
        season_number = body.get("season_number")
        series_video = AllVideo.query.filter_by(id=series_id, type="series").first()
        if not series_video or not series_video.series:
            return _json_error("series_not_found", "Series was not found.", 404)
        try:
            season_number = int(season_number)
        except (TypeError, ValueError):
            return _json_error("invalid_season", "season_number must be an integer.")
        season = Season.query.filter_by(
            series_id=series_video.series.id,
            season_number=season_number,
        ).first()
        if not season:
            return _json_error("season_not_found", "Season was not found.", 404)
        episodes = Episode.query.filter_by(season_id=season.id).order_by(Episode.episode_number).all()
        by_number = {episode.episode_number: episode for episode in episodes}

        assignments = body.get("assignments")
        if not isinstance(assignments, list):
            assignments = None
        if assignments is None:
            ordered_codes = body.get("ordered_codes")
            if not isinstance(ordered_codes, list):
                return _json_error(
                    "assignments_required",
                    "Supply explicit assignments or ordered_codes. Explicit episode assignments are recommended.",
                )
            targets = [
                episode for episode in episodes
                if episode.released_date
                and episode.released_date <= _today_lagos()
                and (replace_existing or not _current_link(episode, track))
            ]
            assignments = [
                {"episode_number": episode.episode_number, "code": code}
                for episode, code in zip(targets, ordered_codes)
            ]
            if len(ordered_codes) > len(targets):
                warnings.append({
                    "type": "unused_codes",
                    "count": len(ordered_codes) - len(targets),
                })

        seen_numbers = set()
        seen_codes = set()
        for item in assignments:
            if not isinstance(item, dict):
                return _json_error("invalid_assignment", "Each assignment must be an object.")
            try:
                episode_number = int(item.get("episode_number"))
            except (TypeError, ValueError):
                return _json_error("invalid_assignment", "Each assignment needs an integer episode_number.")
            if episode_number in seen_numbers:
                return _json_error("duplicate_episode", f"Episode {episode_number} appears more than once.")
            seen_numbers.add(episode_number)
            episode = by_number.get(episode_number)
            if not episode:
                skipped.append({"episode_number": episode_number, "reason": "episode_not_in_library"})
                continue
            if not episode.released_date or episode.released_date > _today_lagos():
                skipped.append({
                    "episode_number": episode_number,
                    "reason": "episode_not_released_or_release_date_unknown",
                })
                continue
            code = _normalize_code(item.get("code"))
            if not code or len(code) > 500:
                return _json_error("invalid_code", f"Episode {episode_number} has an empty or invalid code.")
            if code in seen_codes:
                return _json_error("duplicate_code", "The same download code cannot be assigned to multiple episodes.")
            seen_codes.add(code)
            existing = _current_link(episode, track)
            if existing == code:
                skipped.append({"episode_number": episode_number, "reason": "already_has_this_code"})
            elif existing and not replace_existing:
                skipped.append({"episode_number": episode_number, "reason": "existing_link_preserved"})
            else:
                operations.append({
                    "target_type": "episode",
                    "target_id": episode.id,
                    "episode_number": episode_number,
                    "track": track,
                    "code": code,
                    "existing_code": existing,
                    "source_filename": item.get("source_filename"),
                })

    requires_confirmation = any(
        bool(operation.get("existing_code")) and operation["existing_code"] != operation["code"]
        for operation in operations
    )
    plan = {
        "agent_token_id": g.agent_token.id,
        "operations": operations,
        "storage_server_id": server.id,
        "replace_existing": replace_existing,
        "created_at": datetime.utcnow().isoformat(),
    }
    signed_plan = _plan_serializer().dumps(plan) if operations else None
    return jsonify({
        "status": "preview",
        "operation_count": len(operations),
        "requires_confirmation": requires_confirmation,
        "confirmation_instruction": (
            "Show the proposed replacements to the user and obtain explicit approval before calling links/apply with confirm_replacements=true."
            if requires_confirmation else None
        ),
        "assignments": [
            {
                "target_type": operation["target_type"],
                "target_id": operation["target_id"],
                "episode_number": operation.get("episode_number"),
                "track": operation["track"],
                "will_replace": bool(operation.get("existing_code")),
                "source_filename": operation.get("source_filename"),
            }
            for operation in operations
        ],
        "skipped": skipped,
        "warnings": warnings,
        "preview_token": signed_plan,
        "can_apply": bool(operations),
    })


@agent_api_bp.post("/links/apply")
@agent_required("links:write")
def apply_links():
    body = request.get_json(silent=True) or {}
    signed_plan = body.get("preview_token")
    if not signed_plan:
        return _json_error("preview_required", "Call links/preview first and submit its preview_token.")
    try:
        plan = _plan_serializer().loads(signed_plan, max_age=15 * 60)
    except SignatureExpired:
        return _json_error("preview_expired", "The preview expired. Create a new preview.", 409)
    except BadSignature:
        return _json_error("invalid_preview", "The preview token is invalid.", 400)

    if plan.get("agent_token_id") != g.agent_token.id:
        return _json_error("preview_session_mismatch", "This preview was created by a different agent session.", 403)
    operations = plan.get("operations") or []
    if not operations:
        return _json_error("empty_plan", "The preview contains no changes.")
    has_replacements = any(
        bool(operation.get("existing_code")) and operation["existing_code"] != operation["code"]
        for operation in operations
    )
    if has_replacements and body.get("confirm_replacements") is not True:
        return _json_error(
            "replacement_confirmation_required",
            "This plan replaces existing download codes. User approval is required before applying.",
            409,
        )

    server = StorageServer.query.filter_by(
        id=plan.get("storage_server_id"), active=True
    ).first()
    if not server:
        return _json_error("storage_server_unavailable", "The selected storage server is no longer active.", 409)

    applied, unchanged = [], []
    for operation in operations:
        if operation["target_type"] == "movie":
            target = AllVideo.query.filter_by(id=operation["target_id"], type="movie").first()
        else:
            target = Episode.query.get(operation["target_id"])
        if not target:
            db.session.rollback()
            return _json_error("target_changed", "A target disappeared after preview. Create a new preview.", 409)

        current = _current_link(target, operation["track"])
        if current == operation["code"]:
            unchanged.append(operation["target_id"])
            continue
        expected = operation.get("existing_code") or ""
        if current != expected:
            db.session.rollback()
            return _json_error(
                "target_changed",
                "A link changed after preview. Nothing was applied; create a fresh preview.",
                409,
                target_id=operation["target_id"],
            )
        if current and not plan.get("replace_existing"):
            continue

        setattr(target, LINK_FIELDS[operation["track"]], operation["code"])
        target.storage_server_id = server.id
        target_release_date = target.released_date
        if operation["track"] == "primary":
            target.coming_soon = bool(
                target_release_date and target_release_date > _today_lagos()
            )
        applied.append(operation["target_id"])

    write_audit(
        "links.apply",
        "batch",
        None,
        {
            "applied_count": len(applied),
            "already_applied_count": len(unchanged),
            "track": operations[0]["track"],
            "storage_server_id": server.id,
        },
    )
    db.session.commit()
    return jsonify({
        "status": "success",
        "applied_count": len(applied),
        "already_applied_count": len(unchanged),
        "applied_target_ids": applied,
        "already_applied_target_ids": unchanged,
    })
