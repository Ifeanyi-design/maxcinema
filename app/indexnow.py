import re
from pathlib import Path
from urllib.parse import urlparse

import requests
from flask import current_app, has_request_context, request, url_for


INDEXNOW_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,128}$")


def get_site_base_url():
    configured = (current_app.config.get("SITE_BASE_URL") or "").strip()
    if configured:
        return configured.rstrip("/")

    if has_request_context():
        scheme = request.headers.get("X-Forwarded-Proto", request.scheme)
        host = request.headers.get("X-Forwarded-Host") or request.host
        return f"{scheme}://{host}".rstrip("/")

    return "https://maxcinema.name.ng"


def _project_root():
    return Path(current_app.root_path).parent


def _candidate_key_paths():
    root = _project_root()
    explicit_filename = (current_app.config.get("INDEXNOW_KEY_FILENAME") or "").strip()
    explicit_key = (current_app.config.get("INDEXNOW_KEY") or "").strip()

    if explicit_filename:
        yield root / explicit_filename

    if explicit_key:
        yield root / f"{explicit_key}.txt"

    yield from root.glob("*.txt")


def get_indexnow_key_record():
    seen = set()

    for candidate in _candidate_key_paths():
        try:
            resolved = candidate.resolve()
        except OSError:
            continue

        if resolved in seen or not candidate.is_file():
            continue
        seen.add(resolved)

        stem = candidate.stem.strip()
        if not INDEXNOW_KEY_PATTERN.fullmatch(stem):
            continue

        try:
            content = candidate.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeDecodeError):
            continue

        if content != stem:
            continue

        return {
            "key": stem,
            "content": content,
            "path": candidate,
            "location": f"{get_site_base_url()}/{candidate.name}",
        }

    return None


def _external_url(endpoint, **values):
    if has_request_context():
        return url_for(endpoint, _external=True, **values)

    with current_app.test_request_context(base_url=get_site_base_url()):
        return url_for(endpoint, _external=True, **values)


def _supporting_urls():
    return [
        _external_url("main.index"),
        _external_url("main.sitemap"),
    ]


def _dedupe_urls(urls):
    expected_host = urlparse(get_site_base_url()).netloc.lower()
    unique = []
    seen = set()

    for raw_url in urls:
        url = (raw_url or "").strip()
        if not url or url in seen:
            continue

        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            continue
        if parsed.netloc.lower() != expected_host:
            continue

        seen.add(url)
        unique.append(url)

    return unique


def _series_entry_episode(video):
    if not video or not getattr(video, "series", None):
        return None

    ordered_seasons = sorted(
        list(video.series.seasons or []),
        key=lambda item: (item.season_number or 0, item.id or 0),
    )

    for season in ordered_seasons:
        ordered_episodes = sorted(
            list(season.episodes or []),
            key=lambda item: (item.episode_number or 0, item.id or 0),
        )
        if ordered_episodes:
            return ordered_episodes[0]

    return None


def build_video_detail_url(video):
    if not video:
        return None

    slug = video.slug or video.name

    if video.type == "movie":
        return _external_url("main.movie_details", det="movie", name=slug, id=video.id)

    if video.type == "series":
        episode = _series_entry_episode(video)
        if not episode or not episode.season:
            return None
        return _external_url(
            "main.series_details",
            det="series",
            name=slug,
            season=episode.season.season_number,
            episode=episode.episode_number,
            id=video.id,
        )

    return None


def build_episode_url(episode):
    if not episode or not episode.season or not episode.season.series or not episode.season.series.all_video:
        return None

    series_video = episode.season.series.all_video
    return _external_url(
        "main.series_details",
        det="series",
        name=series_video.slug or series_video.name,
        season=episode.season.season_number,
        episode=episode.episode_number,
        id=series_video.id,
    )


def build_trailer_url(trailer):
    if not trailer:
        return None

    return _external_url(
        "main.watch_trailer",
        det="trailer_watch",
        name=trailer.slug or trailer.name,
    )


def urls_for_video(video):
    return _dedupe_urls(_supporting_urls() + [build_video_detail_url(video)])


def urls_for_episode(episode):
    series_video = None
    if episode and episode.season and episode.season.series:
        series_video = episode.season.series.all_video

    urls = _supporting_urls()
    if series_video:
        urls.append(build_video_detail_url(series_video))
    urls.append(build_episode_url(episode))
    return _dedupe_urls(urls)


def urls_for_trailer(trailer):
    return _dedupe_urls(
        _supporting_urls()
        + [
            _external_url("main.trailer"),
            build_trailer_url(trailer),
        ]
    )


def submit_indexnow_urls(urls):
    if not current_app.config.get("INDEXNOW_ENABLED", True):
        return {"ok": False, "reason": "disabled", "submitted": []}

    record = get_indexnow_key_record()
    if not record:
        current_app.logger.warning("IndexNow skipped: no valid key file found at project root.")
        return {"ok": False, "reason": "missing_key", "submitted": []}

    normalized_urls = _dedupe_urls(urls)
    if not normalized_urls:
        return {"ok": False, "reason": "no_urls", "submitted": []}

    host = urlparse(get_site_base_url()).netloc
    payload = {
        "host": host,
        "key": record["key"],
        "keyLocation": record["location"],
        "urlList": normalized_urls,
    }

    try:
        response = requests.post(
            current_app.config.get("INDEXNOW_ENDPOINT"),
            json=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=10,
        )
    except requests.RequestException as exc:
        current_app.logger.warning("IndexNow request failed: %s", exc)
        return {
            "ok": False,
            "reason": "request_failed",
            "error": str(exc),
            "submitted": normalized_urls,
        }

    if response.ok:
        current_app.logger.info("IndexNow submitted %s URL(s).", len(normalized_urls))
    else:
        current_app.logger.warning(
            "IndexNow rejected submission with status %s: %s",
            response.status_code,
            response.text[:250],
        )

    return {
        "ok": response.ok,
        "status_code": response.status_code,
        "response_text": response.text[:250],
        "submitted": normalized_urls,
    }


def submit_for_video(video):
    return submit_indexnow_urls(urls_for_video(video))


def submit_for_episode(episode):
    return submit_indexnow_urls(urls_for_episode(episode))


def submit_for_trailer(trailer):
    return submit_indexnow_urls(urls_for_trailer(trailer))
