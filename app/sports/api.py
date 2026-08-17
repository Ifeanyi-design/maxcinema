from __future__ import annotations

from datetime import datetime

from flask import Blueprint, jsonify, request

from .services import (
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
    SportsSport,
    SportsStreamSource,
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
        "kickoff_at": m.kickoff_at.isoformat() if m.kickoff_at else None,
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
            "competitions": [competition_payload(c) for c in competitions],
            "live_count": live_count,
        }
    )


@api_bp.route("/competitions")
def competitions():
    comps = get_enabled_competitions("football")
    return jsonify({"competitions": [competition_payload(c) for c in comps]})


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


@api_bp.route("/matches/<int:match_id>")
def match_detail(match_id):
    match = SportsMatch.query.get_or_404(match_id)
    sync_match_events(match)
    events = get_match_events(match_id)
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
