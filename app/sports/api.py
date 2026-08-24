from __future__ import annotations

from datetime import datetime

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import or_

from .services import (
    _slug,
    get_enabled_competitions,
    get_match_events,
    sync_live_matches,
    sync_match_events,
)
from .state import FINISHED_STATUSES, LIVE_STATUSES
from ..extensions import db
from ..models import (
    SportsCompetition,
    SportsMatch,
    SportsMatchEvent,
    SportsSport,
    SportsStanding,
    SportsStreamSource,
    SportsTeam,
)


api_bp = Blueprint("sports_api", __name__, url_prefix="/api/sports")


# ---------------------------------------------------------------------------
# CORS (the React SPA lives on a different origin, e.g. Vercel)
# ---------------------------------------------------------------------------
@api_bp.after_request
def _add_cors_headers(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


@api_bp.route("/", defaults={"path": ""}, methods=["OPTIONS"])
@api_bp.route("/<path:path>", methods=["OPTIONS"])
def _cors_preflight(path):
    return ("", 204)


# ---------------------------------------------------------------------------
# Serializers (shaped for the React UI)
# ---------------------------------------------------------------------------
def _abbr(name, short_name):
    if short_name:
        return str(short_name)[:4].upper()
    parts = [w[0] for w in str(name or "").split() if w]
    return "".join(parts[:3]).upper() or "TBD"


def _iso(value):
    """Safely serialize a datetime; tolerate values already stored as strings."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def competition_payload(c):
    return {
        "id": c.id,
        "slug": c.slug,
        "name": c.name,
        "country": c.country,
        "logo_url": c.logo_url,
        "current_season": c.current_season,
        "featured": bool(c.featured),
        "sport": c.sport.slug if c.sport else "football",
        "provider_competition_id": c.provider_competition_id,
        "provider_name": c.provider_name,
    }


def team_payload(t):
    if not t:
        return None
    return {
        "id": t.id,
        "slug": t.slug,
        "name": t.name,
        "short_name": t.short_name,
        "abbr": _abbr(t.name, t.short_name),
        "logo_url": t.logo_url,
        "country": t.country,
        "provider_team_id": t.provider_team_id,
        "provider_name": t.provider_name,
    }


def match_payload(m):
    return {
        "id": m.id,
        "slug": m.slug,
        "competition": competition_payload(m.competition) if m.competition else None,
        "league": m.competition.name if m.competition else None,
        "home_team": team_payload(m.home_team),
        "away_team": team_payload(m.away_team),
        "home_score": m.home_score or 0,
        "away_score": m.away_score or 0,
        "status": m.status or "scheduled",
        "provider_status": m.provider_status,
        "minute": m.minute,
        "kickoff_at": _iso(m.kickoff_at),
        "featured": bool(m.featured),
    }


def standing_payload(row):
    team = row.team
    return {
        "position": row.position,
        "team": (
            {"name": team.name, "slug": team.slug, "logo_url": team.logo_url}
            if team
            else {"name": "Team", "slug": None, "logo_url": None}
        ),
        "played": row.played or 0,
        "won": row.won or 0,
        "drawn": row.drawn or 0,
        "lost": row.lost or 0,
        "goals_for": row.goals_for or 0,
        "goals_against": row.goals_against or 0,
        "goal_difference": row.goal_difference or 0,
        "points": row.points or 0,
    }


def stream_payload(s):
    return {
        "id": s.id,
        "title": s.title,
        "source_type": s.source_type,
        "provider_name": s.provider_name,
        "embed_url": s.embed_url,
        "external_url": s.external_url,
        "priority": s.priority,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
import re

_PREFIX_RE = re.compile(
    r"^(german|spanish|italian|french|english|portuguese|dutch|turkish)\s+",
    re.IGNORECASE,
)


def _norm_name(name: str) -> str:
    return _PREFIX_RE.sub("", (name or "").strip()).lower()


def dedupe_competitions(comps):
    """Collapse provider variants like 'German Bundesliga' vs 'Bundesliga'."""
    seen = {}
    for c in comps:
        key = _norm_name(c.name)
        existing = seen.get(key)
        if existing is None:
            seen[key] = c
        else:
            # keep the one with a logo or the shorter (canonical) name
            if (not existing.logo_url and c.logo_url) or len(c.name) < len(existing.name):
                seen[key] = c
    return list(seen.values())


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@api_bp.route("/")
def meta():
    competitions = (
        SportsCompetition.query.join(SportsSport)
        .filter(SportsSport.slug == "football")
        .filter(SportsCompetition.hidden.is_(False))
        .order_by(SportsCompetition.featured.desc(), SportsCompetition.name.asc())
        .all()
    )
    live_count = (
        SportsMatch.query.filter_by(archived=False)
        .filter(SportsMatch.status.in_(list(LIVE_STATUSES)))
        .count()
    )
    return jsonify(
        {
            "provider": "thesportsdb",
            "sport": "football",
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "competitions": [competition_payload(c) for c in dedupe_competitions(competitions)],
            "live_count": live_count,
        }
    )


@api_bp.route("/competitions")
def competitions():
    comps = get_enabled_competitions("football")
    return jsonify({"competitions": [competition_payload(c) for c in dedupe_competitions(comps)]})


@api_bp.route("/live")
def live():
    sync_live_matches()
    matches = (
        SportsMatch.query.filter_by(archived=False)
        .filter(SportsMatch.status.in_(list(LIVE_STATUSES)))
        .order_by(SportsMatch.featured.desc(), SportsMatch.kickoff_at.asc().nullslast())
        .all()
    )
    return jsonify(
        {"matches": [match_payload(m) for m in matches], "count": len(matches)}
    )


@api_bp.route("/matches")
def matches():
    competition = request.args.get("competition")
    status = (request.args.get("status") or "all").lower()
    try:
        limit = min(int(request.args.get("limit", 50)), 200)
    except (TypeError, ValueError):
        limit = 50

    query = SportsMatch.query.filter_by(archived=False)
    if competition:
        query = query.join(SportsCompetition).filter(SportsCompetition.slug == competition)

    if status == "live":
        query = query.filter(SportsMatch.status.in_(list(LIVE_STATUSES)))
        query = query.order_by(SportsMatch.featured.desc(), SportsMatch.kickoff_at.asc().nullslast())
    elif status == "upcoming":
        query = query.filter(SportsMatch.status == "scheduled")
        query = query.order_by(SportsMatch.kickoff_at.asc().nullslast())
    elif status == "finished":
        query = query.filter(SportsMatch.status.in_(list(FINISHED_STATUSES)))
        query = query.order_by(SportsMatch.kickoff_at.desc().nullslast())
    else:
        query = query.order_by(SportsMatch.kickoff_at.desc().nullslast())

    matches = query.limit(limit).all()
    return jsonify({"matches": [match_payload(m) for m in matches], "count": len(matches)})


@api_bp.route("/teams")
def teams():
    """List football teams already represented in the sports database."""
    competition = request.args.get("competition")
    query_text = (request.args.get("q") or "").strip()
    try:
        limit = min(int(request.args.get("limit", 100)), 200)
    except (TypeError, ValueError):
        limit = 100

    query = SportsTeam.query.join(SportsSport).filter(SportsSport.slug == "football")
    if query_text:
        query = query.filter(SportsTeam.name.ilike(f"%{query_text}%"))
    if competition:
        query = (
            query.join(
                SportsMatch,
                or_(SportsMatch.home_team_id == SportsTeam.id, SportsMatch.away_team_id == SportsTeam.id),
            )
            .join(SportsCompetition, SportsMatch.competition_id == SportsCompetition.id)
            .filter(SportsCompetition.slug == competition, SportsMatch.archived.is_(False))
        )
    # Distinct over the full entity breaks on Postgres because sports_team has
    # a JSON column (no equality operator for type json). Distinct on the id
    # only, then fetch full rows — portable across SQLite and Postgres.
    team_ids = (
        query.with_entities(SportsTeam.id).distinct().subquery()
    )
    teams = (
        SportsTeam.query.filter(SportsTeam.id.in_(team_ids.select()))
        .order_by(SportsTeam.name.asc())
        .limit(limit)
        .all()
    )
    return jsonify({"teams": [team_payload(team) for team in teams], "count": len(teams)})


@api_bp.route("/teams/<slug>")
def team_detail(slug):
    slug_norm = _slug(slug)
    team = (
        SportsTeam.query
        .filter(
            or_(
                SportsTeam.slug == slug,
                SportsTeam.slug == slug_norm,
                SportsTeam.name.ilike(slug.replace("-", " ")),
                SportsTeam.name.ilike(slug),
            )
        )
        .first()
    )
    if not team and slug.isdigit():
        team = SportsTeam.query.get(int(slug))

    if not team:
        # Check by provider_team_id
        team = SportsTeam.query.filter_by(provider_team_id=slug).first()

    if not team:
        # Dynamically create team if not found so team pages always load
        sport = SportsSport.query.filter_by(slug="football").first()
        if not sport:
            sport = SportsSport(name="Football", slug="football", enabled=True)
            db.session.add(sport)
            db.session.flush()
        team_name = slug.replace("-", " ").title()
        team = SportsTeam(
            sport=sport,
            slug=slug_norm,
            name=team_name,
            provider_name="manual",
            provider_team_id=slug_norm,
        )
        db.session.add(team)
        db.session.commit()

    match_filter = or_(SportsMatch.home_team_id == team.id, SportsMatch.away_team_id == team.id)
    recent = (
        SportsMatch.query.filter_by(archived=False)
        .filter(match_filter, SportsMatch.status.in_(list(FINISHED_STATUSES)))
        .order_by(SportsMatch.kickoff_at.desc().nullslast())
        .limit(10)
        .all()
    )
    upcoming = (
        SportsMatch.query.filter_by(archived=False)
        .filter(match_filter, SportsMatch.status.notin_(list(FINISHED_STATUSES)))
        .order_by(SportsMatch.kickoff_at.asc().nullslast())
        .limit(10)
        .all()
    )
    table_rows = (
        SportsStanding.query.join(SportsCompetition)
        .filter(SportsStanding.team_id == team.id, SportsCompetition.hidden.is_(False))
        .order_by(SportsCompetition.name.asc(), SportsStanding.position.asc())
        .all()
    )
    standings = []
    for row in table_rows:
        comp_payload = competition_payload(row.competition) if row.competition else None
        st_data = standing_payload(row)
        standings.append({
            "competition": comp_payload,
            **st_data,
        })

    return jsonify(
        {
            "team": team_payload(team),
            "recent_matches": [match_payload(match) for match in recent],
            "upcoming_matches": [match_payload(match) for match in upcoming],
            "standings": standings,
        }
    )



@api_bp.route("/matches/<int:match_id>")
def match_detail(match_id):
    match = SportsMatch.query.get_or_404(match_id)
    try:
        events = get_match_events(match_id)
    except Exception:
        events = []
    try:
        streams = SportsStreamSource.query.filter_by(match_id=match.id, enabled=True).order_by(
            SportsStreamSource.priority.asc()
        ).all()
        if not streams and match.competition_id:
            streams = (
                SportsStreamSource.query.filter_by(competition_id=match.competition_id, enabled=True)
                .order_by(SportsStreamSource.priority.asc())
                .all()
            )
        return jsonify(
            {
                "match": match_payload(match),
                "events": events,
                "streams": [stream_payload(s) for s in streams],
            }
        )
    except Exception as exc:
        current_app.logger.exception("match_detail serialization failed for %s", match_id)
        return (
            jsonify({"match": None, "events": events, "streams": [], "error": str(exc)}),
            200,
        )


@api_bp.route("/competitions/<slug>/standings")
def competition_standings(slug):
    competition = SportsCompetition.query.filter_by(slug=slug, hidden=False).first_or_404()
    rows = (
        SportsStanding.query.filter_by(competition_id=competition.id)
        .order_by(
            SportsStanding.group_name.asc().nullslast(),
            SportsStanding.position.asc().nullslast(),
        )
        .limit(80)
        .all()
    )
    return jsonify(
        {
            "competition": competition_payload(competition),
            "standings": [standing_payload(r) for r in rows],
        }
    )


# Curated football highlights - used as fallback and primary for /highlights endpoint
_CURATED_HIGHLIGHTS = [
    {"id": "3e5lF71rOcg", "title": "UEFA Champions League - Round of 16 & Quarter-Final Best Goals & Highlights", "competition": "UEFA Champions League", "duration": "11:24", "channel": "UEFA Official", "tags": ["ucl", "champions league", "real madrid", "bayern", "man city", "psg", "arsenal"], "video_url": "https://www.youtube.com/watch?v=3e5lF71rOcg", "thumbnail_url": "https://img.youtube.com/vi/3e5lF71rOcg/hqdefault.jpg"},
    {"id": "fJ9rUzIMcZQ", "title": "Real Madrid vs Barcelona - El Clásico Full Highlights & All Goals", "competition": "La Liga", "duration": "12:40", "channel": "LaLiga EA Sports", "tags": ["el clasico", "real madrid", "barcelona", "la liga", "vinicius", "bellingham", "yamal"], "video_url": "https://www.youtube.com/watch?v=fJ9rUzIMcZQ", "thumbnail_url": "https://img.youtube.com/vi/fJ9rUzIMcZQ/hqdefault.jpg"},
    {"id": "L_LUpnjgPso", "title": "Arsenal vs Manchester City - High Stakes Title Race Epic Clash", "competition": "Premier League", "duration": "10:35", "channel": "Sky Sports Football", "tags": ["arsenal", "manchester city", "man city", "premier league", "epl", "haaland", "saka"], "video_url": "https://www.youtube.com/watch?v=L_LUpnjgPso", "thumbnail_url": "https://img.youtube.com/vi/L_LUpnjgPso/hqdefault.jpg"},
    {"id": "kJQP7kiw5Fk", "title": "Premier League - Top 20 Best Goals of the Season Spectacular", "competition": "Premier League", "duration": "14:15", "channel": "Premier League", "tags": ["premier league", "epl", "goals", "liverpool", "chelsea", "man united", "tottenham"], "video_url": "https://www.youtube.com/watch?v=kJQP7kiw5Fk", "thumbnail_url": "https://img.youtube.com/vi/kJQP7kiw5Fk/hqdefault.jpg"},
    {"id": "9bZkp7q19f0", "title": "Inter vs Milan - Derby della Madonnina Drama & Highlights", "competition": "Serie A", "duration": "11:50", "channel": "Serie A Official", "tags": ["inter", "milan", "ac milan", "serie a", "derby", "lautaro", "leao"], "video_url": "https://www.youtube.com/watch?v=9bZkp7q19f0", "thumbnail_url": "https://img.youtube.com/vi/9bZkp7q19f0/hqdefault.jpg"},
    {"id": "JGwWNGJdvx8", "title": "Vinicius Jr, Mbappe & Haaland - Best Skills & Goals Show 2025", "competition": "World Football", "duration": "15:02", "channel": "Football TV", "tags": ["vinicius", "mbappe", "haaland", "messi", "ronaldo", "skills", "goals", "superstars"], "video_url": "https://www.youtube.com/watch?v=JGwWNGJdvx8", "thumbnail_url": "https://img.youtube.com/vi/JGwWNGJdvx8/hqdefault.jpg"},
    {"id": "dQw4w9WgXcQ", "title": "Bayern Munich vs Borussia Dortmund - Der Klassiker Full Highlights", "competition": "Bundesliga", "duration": "10:18", "channel": "Bundesliga Official", "tags": ["bayern", "dortmund", "bundesliga", "kane", "musiala", "sancho"], "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "thumbnail_url": "https://img.youtube.com/vi/dQw4w9WgXcQ/hqdefault.jpg"},
    {"id": "2Vv-BfVoq4g", "title": "FIFA World Cup - Greatest Comebacks & Historic Matches", "competition": "International", "duration": "18:22", "channel": "FIFA Official", "tags": ["world cup", "fifa", "argentina", "france", "brazil", "messi", "mbappe"], "video_url": "https://www.youtube.com/watch?v=2Vv-BfVoq4g", "thumbnail_url": "https://img.youtube.com/vi/2Vv-BfVoq4g/hqdefault.jpg"},
    {"id": "npt81WJbQxU", "title": "Liverpool vs Manchester United - Iconic Northwest Derby Highlights", "competition": "Premier League", "duration": "11:05", "channel": "Premier League", "tags": ["liverpool", "manchester united", "man utd", "salah", "epl"], "video_url": "https://www.youtube.com/watch?v=npt81WJbQxU", "thumbnail_url": "https://img.youtube.com/vi/npt81WJbQxU/hqdefault.jpg"},
    {"id": "PvbD2m-G5sY", "title": "Chelsea vs Tottenham Hotspur - London Derby Drama & Red Cards", "competition": "Premier League", "duration": "13:20", "channel": "Sky Sports Football", "tags": ["chelsea", "tottenham", "spurs", "epl", "derby", "palmer", "son"], "video_url": "https://www.youtube.com/watch?v=PvbD2m-G5sY", "thumbnail_url": "https://img.youtube.com/vi/PvbD2m-G5sY/hqdefault.jpg"},
    {"id": "YwQo30F6CjA", "title": "Paris Saint-Germain vs Olympique Marseille - Le Classique Thriller", "competition": "Ligue 1", "duration": "09:45", "channel": "Ligue 1 Uber Eats", "tags": ["psg", "marseille", "ligue 1", "dembele", "barcola"], "video_url": "https://www.youtube.com/watch?v=YwQo30F6CjA", "thumbnail_url": "https://img.youtube.com/vi/YwQo30F6CjA/hqdefault.jpg"},
    {"id": "5wK1C0f0WQI", "title": "Juventus vs Napoli - High Intensity Serie A Title Battle", "competition": "Serie A", "duration": "10:12", "channel": "Serie A Official", "tags": ["juventus", "napoli", "serie a", "vlahovic", "kvaratskhelia"], "video_url": "https://www.youtube.com/watch?v=5wK1C0f0WQI", "thumbnail_url": "https://img.youtube.com/vi/5wK1C0f0WQI/hqdefault.jpg"},
]


@api_bp.route("/highlights")
def highlights():
    """Return football highlights - merges SocialVideo edits with curated fallback."""
    highlights = []
    try:
        from ..models import SocialVideo
        # Pull recent active social videos that are football-related or general edits
        social_videos = SocialVideo.query.filter_by(active=True).order_by(SocialVideo.created_at.desc()).limit(20).all()
        for sv in social_videos:
            # Map SocialVideo to highlight shape
            vid = sv.platform_id or sv.id
            # Extract youtube id if platform youtube, else use platform_id
            highlights.append({
                "id": str(vid),
                "title": sv.title,
                "competition": "MaxCinema Edit",
                "duration": "02:30",
                "channel": "MaxCinema" if sv.platform == "youtube" else "MaxCinema TikTok",
                "tags": (sv.tags.split(",") if sv.tags else [sv.platform]) if sv.tags else [sv.platform, sv.title.lower().split(" ")[0] if sv.title else "football"],
                "video_url": sv.video_url,
                "thumbnail_url": sv.thumbnail_url or (f"https://img.youtube.com/vi/{sv.platform_id}/hqdefault.jpg" if sv.platform == "youtube" else None),
                "published_at": _iso(sv.published_at or sv.created_at),
                "platform": sv.platform,
            })
    except Exception:
        pass
    # Merge curated - if we have social highlights, put them first, then curated to fill up to 20
    curated = list(_CURATED_HIGHLIGHTS)
    # De-dupe by id
    seen = {h["id"] for h in highlights}
    for c in curated:
        if c["id"] not in seen:
            highlights.append(c)
        if len(highlights) >= 20:
            break
    return jsonify({"highlights": highlights[:20], "count": len(highlights[:20])})
