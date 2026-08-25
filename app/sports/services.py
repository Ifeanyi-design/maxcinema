from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import Lock

from flask import current_app

from ..extensions import db
from ..models import (
    SportsCompetition,
    SportsMatch,
    SportsMatchEvent,
    SportsProviderCache,
    SportsSport,
    SportsStanding,
    SportsTeam,
)
from .providers import get_provider
from .state import FINISHED_STATUSES, LIVE_STATUSES, MatchState


LIVE_REFRESH_SECONDS = 30
UPCOMING_REFRESH_SECONDS = 1800
FINISHED_REFRESH_SECONDS = 3600
STALE_FALLBACK_SECONDS = 86400

_cache_locks = defaultdict(Lock)
_memory_cache = {}


@dataclass(frozen=True)
class CacheResult:
    payload: object
    stale: bool = False
    error: str | None = None


def _utcnow():
    return datetime.utcnow()


def _slug(value, fallback="item"):
    text = str(value or fallback).strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or fallback


def _parse_datetime(value):
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _status_ttl(status):
    normalized = (status or "").lower()
    if normalized in LIVE_STATUSES:
        return LIVE_REFRESH_SECONDS
    if normalized in FINISHED_STATUSES:
        return FINISHED_REFRESH_SECONDS
    return UPCOMING_REFRESH_SECONDS


def get_or_refresh_cache(provider_name, cache_key, ttl_seconds, stale_seconds, fetcher, fallback=None):
    now = _utcnow()
    memory_key = f"{provider_name}:{cache_key}"
    memory_hit = _memory_cache.get(memory_key)
    if memory_hit and memory_hit["expires_at"] > now:
        return CacheResult(memory_hit["payload"], stale=False)

    cache_row = SportsProviderCache.query.filter_by(
        provider_name=provider_name,
        cache_key=cache_key,
    ).first()
    if cache_row and cache_row.expires_at > now:
        _memory_cache[memory_key] = {"payload": cache_row.payload, "expires_at": cache_row.expires_at}
        return CacheResult(cache_row.payload, stale=False)

    lock = _cache_locks[memory_key]
    if not lock.acquire(blocking=False):
        if cache_row and cache_row.payload is not None:
            return CacheResult(cache_row.payload, stale=True, error="refresh in progress")
        if memory_hit:
            return CacheResult(memory_hit["payload"], stale=True, error="refresh in progress")
        return CacheResult(fallback, stale=True, error="refresh in progress")

    try:
        cache_row = SportsProviderCache.query.filter_by(
            provider_name=provider_name,
            cache_key=cache_key,
        ).first()
        if cache_row and cache_row.expires_at > now:
            return CacheResult(cache_row.payload, stale=False)

        payload = fetcher()
        expires_at = now + timedelta(seconds=ttl_seconds)
        stale_until = expires_at + timedelta(seconds=stale_seconds)

        if not cache_row:
            cache_row = SportsProviderCache(provider_name=provider_name, cache_key=cache_key)
            db.session.add(cache_row)

        cache_row.payload = payload
        cache_row.status = "fresh"
        cache_row.expires_at = expires_at
        cache_row.stale_until = stale_until
        cache_row.last_error = None
        cache_row.last_fetched_at = now
        db.session.commit()
        _memory_cache[memory_key] = {"payload": payload, "expires_at": expires_at}
        return CacheResult(payload, stale=False)
    except Exception as exc:
        db.session.rollback()
        current_app.logger.warning("sports cache refresh failed for %s: %s", memory_key, exc)
        if cache_row and cache_row.payload is not None:
            cache_row.status = "stale"
            cache_row.last_error = str(exc)
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
            return CacheResult(cache_row.payload, stale=True, error=str(exc))
        return CacheResult(fallback, stale=True, error=str(exc))
    finally:
        lock.release()


def serialize_event(event):
    return {
        "id": event.id,
        "event_type": event.event_type,
        "minute": event.minute,
        "clock": event.clock,
        "team": event.team.name if event.team else None,
        "player_name": event.player_name,
        "related_player_name": event.related_player_name,
        "summary": event.summary,
        "occurred_at": event.occurred_at.isoformat() if event.occurred_at else None,
    }


def sync_provider_catalog(provider=None):
    provider = provider or get_provider()

    sports_result = get_or_refresh_cache(
        provider.name,
        "catalog:sports",
        ttl_seconds=UPCOMING_REFRESH_SECONDS,
        stale_seconds=STALE_FALLBACK_SECONDS,
        fetcher=provider.fetch_sports,
        fallback=[],
    )
    for raw_sport in sports_result.payload or []:
        _upsert_sport(raw_sport)

    competitions_result = get_or_refresh_cache(
        provider.name,
        "catalog:competitions:football",
        ttl_seconds=UPCOMING_REFRESH_SECONDS,
        stale_seconds=STALE_FALLBACK_SECONDS,
        fetcher=lambda: provider.fetch_competitions("football"),
        fallback=[],
    )
    for raw_competition in competitions_result.payload or []:
        _upsert_competition(raw_competition, provider.name)

    teams_result = get_or_refresh_cache(
        provider.name,
        "catalog:teams:football",
        ttl_seconds=UPCOMING_REFRESH_SECONDS,
        stale_seconds=STALE_FALLBACK_SECONDS,
        fetcher=lambda: provider.fetch_teams("football"),
        fallback=[],
    )
    for raw_team in teams_result.payload or []:
        _upsert_team(raw_team, provider.name)

    db.session.commit()
    return {
        "sports_stale": sports_result.stale,
        "competitions_stale": competitions_result.stale,
        "teams_stale": teams_result.stale,
    }


def sync_provider_fixtures(provider=None, competition_id=None):
    provider = provider or get_provider()
    sync_provider_catalog(provider)
    cache_key = f"fixtures:{competition_id or 'all'}"
    result = get_or_refresh_cache(
        provider.name,
        cache_key,
        ttl_seconds=UPCOMING_REFRESH_SECONDS,
        stale_seconds=STALE_FALLBACK_SECONDS,
        fetcher=lambda: provider.fetch_fixtures(competition_id=competition_id),
        fallback=[],
    )
    for raw_match in result.payload or []:
        _upsert_match(raw_match, provider.name)
    db.session.commit()
    return result


def sync_live_matches(provider=None):
    provider = provider or get_provider()
    sync_provider_catalog(provider)
    result = get_or_refresh_cache(
        provider.name,
        "live-matches",
        ttl_seconds=LIVE_REFRESH_SECONDS,
        stale_seconds=STALE_FALLBACK_SECONDS,
        fetcher=provider.fetch_live_matches,
        fallback=[],
    )
    for raw_match in result.payload or []:
        _upsert_match(raw_match, provider.name, stale=result.stale)
    db.session.commit()
    return result


def sync_match_events(match, provider=None):
    if not match or not match.provider_match_id:
        return CacheResult([], stale=True, error="missing provider match id")
    provider = provider or get_provider(match.provider_name)
    existing_events = [serialize_event(event) for event in match.events[:80]]
    result = get_or_refresh_cache(
        provider.name,
        f"events:{match.provider_match_id}",
        ttl_seconds=_status_ttl(match.status),
        stale_seconds=STALE_FALLBACK_SECONDS,
        fetcher=lambda: provider.fetch_match_events(match),
        fallback=existing_events,
    )
    for raw_event in result.payload or []:
        _upsert_event(match, raw_event, provider.name)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
    return result


def sync_competition_standings(competition, provider=None):
    if not competition:
        return CacheResult([], stale=True, error="missing competition")
    provider = provider or get_provider(competition.provider_name)
    fallback = [_standing_payload(row) for row in competition.standings[:80]]
    provider_competition_id = competition.provider_competition_id or competition.slug or competition.id
    result = get_or_refresh_cache(
        provider.name,
        f"standings:{provider_competition_id}",
        ttl_seconds=UPCOMING_REFRESH_SECONDS,
        stale_seconds=STALE_FALLBACK_SECONDS,
        fetcher=lambda: provider.fetch_standings(competition),
        fallback=fallback,
    )
    for raw_row in result.payload or []:
        _upsert_standing(competition, raw_row)
    db.session.commit()
    return result


def get_live_match_states(limit=24):
    sync_live_matches()

    def fetcher():
        matches = (
            SportsMatch.query
            .filter(SportsMatch.archived.is_(False))
            .filter(SportsMatch.status.in_(list(LIVE_STATUSES)))
            .order_by(SportsMatch.featured.desc(), SportsMatch.kickoff_at.asc())
            .limit(limit)
            .all()
        )
        return [MatchState.from_match(match).to_dict() for match in matches]

    result = get_or_refresh_cache(
        "local",
        "live-match-states",
        ttl_seconds=10,
        stale_seconds=300,
        fetcher=fetcher,
        fallback=[MatchState.demo().to_dict()],
    )
    payload = result.payload or [MatchState.demo().to_dict()]
    return [MatchState(**_match_state_kwargs(item, result.stale)) for item in payload]


def get_featured_matches(limit=12):
    sync_provider_fixtures()
    matches = (
        SportsMatch.query
        .filter(SportsMatch.archived.is_(False))
        .order_by(SportsMatch.featured.desc(), SportsMatch.kickoff_at.asc().nullslast())
        .limit(limit)
        .all()
    )
    if not matches:
        return [MatchState.demo()]
    return [MatchState.from_match(match) for match in matches]


def get_match_state(match_id):
    match = SportsMatch.query.get_or_404(match_id)
    sync_match_events(match)
    events = _query_match_events(match_id)
    return MatchState.from_match(match, events=events)


def get_match_events(match_id, limit=80):
    match = SportsMatch.query.get_or_404(match_id)
    sync_match_events(match)
    return _query_match_events(match_id, limit=limit)


def _query_match_events(match_id, limit=80):
    events = (
        SportsMatchEvent.query
        .filter_by(match_id=match_id)
        .order_by(SportsMatchEvent.sort_order.asc(), SportsMatchEvent.id.asc())
        .limit(limit)
        .all()
    )
    return [serialize_event(event) for event in events]


def get_competition_standings(competition_id, limit=80):
    competition = SportsCompetition.query.get_or_404(competition_id)
    sync_competition_standings(competition)
    rows = (
        SportsStanding.query
        .filter_by(competition_id=competition_id)
        .order_by(SportsStanding.group_name.asc().nullslast(), SportsStanding.position.asc().nullslast())
        .limit(limit)
        .all()
    )
    return [_standing_payload(row) for row in rows]


def get_enabled_competitions(sport_slug="football", limit=20):
    sync_provider_catalog()
    query = (
        SportsCompetition.query
        .join(SportsSport)
        .filter(SportsSport.slug == sport_slug)
        .filter(SportsCompetition.hidden.is_(False))
        .order_by(SportsCompetition.featured.desc(), SportsCompetition.name.asc())
        .limit(limit)
    )
    return query.all()


def get_or_create_default_sport():
    sport = SportsSport.query.filter_by(slug="football").first()
    if sport:
        return sport
    sport = SportsSport(name="Football", slug="football", enabled=True, display_order=1)
    db.session.add(sport)
    db.session.commit()
    return sport


def _upsert_sport(raw):
    slug = _slug(raw.get("slug") or raw.get("name"), "sport")
    sport = SportsSport.query.filter_by(slug=slug).first()
    if not sport:
        sport = SportsSport(slug=slug, name=raw.get("name") or slug.title())
        db.session.add(sport)
    sport.name = raw.get("name") or sport.name
    sport.enabled = raw.get("enabled", sport.enabled)
    sport.display_order = raw.get("display_order", sport.display_order or 0)
    sport.provider_payload = raw
    return sport


def _upsert_competition(raw, provider_name):
    sport_slug = _slug(raw.get("sport_slug") or "football", "football")
    sport = SportsSport.query.filter_by(slug=sport_slug).first() or get_or_create_default_sport()

    # 1) Prefer matching by provider_competition_id (stable across slug changes)
    provider_id = str(raw.get("provider_competition_id") or raw.get("id") or "")
    if provider_id:
        existing = SportsCompetition.query.filter_by(provider_competition_id=provider_id).first()
        if existing:
            existing.name = raw.get("name") or existing.name
            _c = raw.get("country", existing.country)
            if isinstance(_c, dict):
                _c = _c.get("name")
            existing.country = _c
            existing.logo_url = raw.get("logo_url", existing.logo_url)
            existing.current_season = raw.get("current_season", existing.current_season)
            existing.provider_name = provider_name
            existing.provider_payload = raw
            return existing
        # 2) Cross-provider migration: same league under different provider IDs
        # e.g. thesportsdb "German Bundesliga" (4331) vs api-football "Bundesliga" (78)
        _prefix_re = re.compile(r"^(german|spanish|italian|french|english|portuguese|dutch|turkish)\s+", re.IGNORECASE)
        norm = _prefix_re.sub("", (raw.get("name") or "").strip()).lower()
        if norm:
            for c in SportsCompetition.query.filter_by(sport_id=sport.id).all():
                existing_norm = _prefix_re.sub("", (c.name or "").strip()).lower()
                if existing_norm == norm:
                    c.name = raw.get("name") or c.name
                    _c2 = raw.get("country", c.country)
                    if isinstance(_c2, dict):
                        _c2 = _c2.get("name")
                    c.country = _c2
                    c.logo_url = raw.get("logo_url", c.logo_url)
                    c.current_season = raw.get("current_season", c.current_season)
                    c.provider_name = provider_name
                    c.provider_competition_id = provider_id
                    c.provider_payload = raw
                    return c

    slug = _slug(raw.get("slug") or raw.get("name"), "competition")
    competition = SportsCompetition.query.filter_by(sport_id=sport.id, slug=slug).first()
    if not competition:
        competition = SportsCompetition(
            sport=sport,
            slug=slug,
            name=raw.get("name") or slug.title(),
            enabled=bool(raw.get("enabled", False)),
            featured=bool(raw.get("featured", False)),
            hidden=bool(raw.get("hidden", False)),
        )
        db.session.add(competition)
    competition.name = raw.get("name") or competition.name
    # API-Football returns country as a dict {name, code, flag} — normalize to string
    _country = raw.get("country", competition.country)
    if isinstance(_country, dict):
        _country = _country.get("name")
    competition.country = _country
    competition.logo_url = raw.get("logo_url", competition.logo_url)
    competition.current_season = raw.get("current_season", competition.current_season)
    competition.provider_name = provider_name
    competition.provider_competition_id = str(raw.get("provider_competition_id") or raw.get("id") or slug)
    competition.provider_payload = raw
    return competition


def _upsert_team(raw, provider_name):
    sport_slug = _slug(raw.get("sport_slug") or "football", "football")
    sport = SportsSport.query.filter_by(slug=sport_slug).first() or get_or_create_default_sport()
    slug = _slug(raw.get("slug") or raw.get("name"), "team")
    team = SportsTeam.query.filter_by(sport_id=sport.id, slug=slug).first()
    if not team:
        team = SportsTeam(sport=sport, slug=slug, name=raw.get("name") or slug.title())
        db.session.add(team)
    team.name = raw.get("name") or team.name
    team.short_name = raw.get("short_name", team.short_name)
    _t_country = raw.get("country", team.country)
    if isinstance(_t_country, dict):
        _t_country = _t_country.get("name")
    team.country = _t_country
    team.logo_url = raw.get("logo_url", team.logo_url)
    team.provider_name = provider_name
    team.provider_team_id = str(raw.get("provider_team_id") or raw.get("id") or slug)
    team.provider_payload = raw
    return team


def _upsert_match(raw, provider_name, stale=False):
    sport_slug = _slug(raw.get("sport_slug") or "football", "football")
    sport = SportsSport.query.filter_by(slug=sport_slug).first() or get_or_create_default_sport()
    competition = _find_or_create_match_competition(raw, sport, provider_name)
    home_team = _find_or_create_match_team(raw, "home", sport, provider_name)
    away_team = _find_or_create_match_team(raw, "away", sport, provider_name)
    provider_match_id = str(raw.get("provider_match_id") or raw.get("id") or "")
    name = raw.get("name") or f"{home_team.name if home_team else 'Home'} vs {away_team.name if away_team else 'Away'}"
    slug = _slug(raw.get("slug") or f"{provider_match_id}-{name}", "match")
    match = None
    if provider_match_id:
        match = SportsMatch.query.filter_by(provider_name=provider_name, provider_match_id=provider_match_id).first()
    if not match:
        match = SportsMatch.query.filter_by(slug=slug).first()
    if not match:
        match = SportsMatch(sport=sport, slug=slug, name=name, provider_name=provider_name, provider_match_id=provider_match_id)
        db.session.add(match)

    status = (raw.get("status") or "scheduled").lower()
    now = _utcnow()
    match.sport = sport
    match.competition = competition
    match.home_team = home_team
    match.away_team = away_team
    match.name = name
    match.kickoff_at = _parse_datetime(raw.get("kickoff_at"))
    match.status = status
    match.provider_status = raw.get("provider_status")
    match.provider_clock = raw.get("provider_clock")
    match.minute = raw.get("minute")
    match.home_score = int(raw.get("home_score") or 0)
    match.away_score = int(raw.get("away_score") or 0)
    match.provider_name = provider_name
    match.provider_match_id = provider_match_id
    match.external_match_id = str(raw.get("external_match_id") or provider_match_id or slug)
    match.featured = bool(raw.get("featured", match.featured))
    match.last_synced_at = now
    match.stale_after = now + timedelta(seconds=_status_ttl(status))
    match.provider_payload = {**raw, "stale": stale}
    return match


def _find_or_create_match_competition(raw, sport, provider_name):
    slug = _slug(raw.get("competition_slug") or raw.get("competition") or "featured-football", "competition")
    competition = SportsCompetition.query.filter_by(sport_id=sport.id, slug=slug).first()
    if competition:
        return competition
    competition = SportsCompetition(
        sport=sport,
        slug=slug,
        name=raw.get("competition") or slug.replace("-", " ").title(),
        provider_name=provider_name,
        provider_competition_id=str(raw.get("competition_provider_id") or slug),
        enabled=True,
        featured=bool(raw.get("featured", False)),
    )
    db.session.add(competition)
    return competition


def _find_or_create_match_team(raw, side, sport, provider_name):
    slug = _slug(raw.get(f"{side}_team_slug") or raw.get(f"{side}_team"), f"{side}-team")
    team = SportsTeam.query.filter_by(sport_id=sport.id, slug=slug).first()
    logo = raw.get(f"{side}_team_logo") or raw.get(f"{side}_logo")
    provider_id = str(raw.get(f"{side}_team_provider_id") or raw.get(f"{side}_id") or slug)
    if team:
        if not team.logo_url and logo:
            team.logo_url = logo
        if not team.provider_team_id and provider_id:
            team.provider_team_id = provider_id
        return team
    team = SportsTeam(
        sport=sport,
        slug=slug,
        name=raw.get(f"{side}_team") or slug.replace("-", " ").title(),
        provider_name=provider_name,
        provider_team_id=provider_id,
        logo_url=logo,
    )
    db.session.add(team)
    return team


def _upsert_event(match, raw, provider_name):
    provider_event_id = str(raw.get("provider_event_id") or raw.get("id") or "")

    team = None
    team_slug = raw.get("team_slug")
    if team_slug:
        team = SportsTeam.query.filter_by(sport_id=match.sport_id, slug=_slug(team_slug, "team")).first()

    event_type = raw.get("event_type") or "update"
    minute = raw.get("minute")
    clock = raw.get("clock")
    player_name = raw.get("player_name")
    related_player_name = raw.get("related_player_name")
    summary = raw.get("summary")
    sort_order = int(raw.get("sort_order") or minute or 0)
    occurred_at = _parse_datetime(raw.get("occurred_at"))

    event = None
    if provider_event_id:
        event = SportsMatchEvent.query.filter_by(
            match_id=match.id,
            provider_name=provider_name,
            provider_event_id=provider_event_id,
        ).first()
    if not event:
        event = SportsMatchEvent(
            match=match,
            provider_name=provider_name,
            provider_event_id=provider_event_id,
            event_type=event_type,
            minute=minute,
            clock=clock,
            team=team,
            player_name=player_name,
            related_player_name=related_player_name,
            summary=summary,
            sort_order=sort_order,
            provider_payload=raw,
            occurred_at=occurred_at,
        )
        db.session.add(event)
        return event

    event.event_type = event_type
    event.minute = minute
    event.clock = clock
    event.team = team
    event.player_name = player_name
    event.related_player_name = related_player_name
    event.summary = summary
    event.sort_order = sort_order
    event.provider_payload = raw
    event.occurred_at = occurred_at
    return event


def _upsert_standing(competition, raw):
    team = None
    if raw.get("team_slug") and competition.sport_id:
        team = SportsTeam.query.filter_by(
            sport_id=competition.sport_id,
            slug=_slug(raw.get("team_slug"), "team"),
        ).first()
    row = None
    if team:
        row = SportsStanding.query.filter_by(
            competition_id=competition.id,
            team_id=team.id,
            group_name=raw.get("group_name"),
        ).first()
    if not row:
        row = SportsStanding(competition=competition, team=team, group_name=raw.get("group_name"))
        db.session.add(row)

    row.position = raw.get("position")
    row.played = raw.get("played") or 0
    row.won = raw.get("won") or 0
    row.drawn = raw.get("drawn") or 0
    row.lost = raw.get("lost") or 0
    row.goals_for = raw.get("goals_for") or 0
    row.goals_against = raw.get("goals_against") or 0
    row.goal_difference = raw.get("goal_difference") or 0
    row.points = raw.get("points") or 0
    row.provider_payload = raw
    row.last_synced_at = _utcnow()
    return row


def _standing_payload(row):
    return {
        "team": row.team.name if row.team else "Team",
        "position": row.position,
        "played": row.played,
        "won": row.won,
        "drawn": row.drawn,
        "lost": row.lost,
        "goals_for": row.goals_for,
        "goals_against": row.goals_against,
        "goal_difference": row.goal_difference,
        "points": row.points,
        "group_name": row.group_name,
    }


def _match_state_kwargs(item, stale):
    return {
        "id": item.get("id"),
        "name": item.get("name") or "Match",
        "sport": item.get("sport") or "Football",
        "competition": item.get("competition"),
        "home_team": item.get("home_team") or "Home",
        "away_team": item.get("away_team") or "Away",
        "home_score": item.get("home_score") or 0,
        "away_score": item.get("away_score") or 0,
        "status": item.get("status") or "scheduled",
        "provider_status": item.get("provider_status"),
        "provider_clock": item.get("provider_clock"),
        "minute": item.get("minute"),
        "kickoff_at": _parse_datetime(item.get("kickoff_at")),
        "last_synced_at": _parse_datetime(item.get("last_synced_at")),
        "stale": bool(item.get("stale") or stale),
        "events": item.get("events") or [],
    }


# ---------------------------------------------------------------------------
# Optional depth endpoints: match statistics & lineups.
# These are provider-dependent (API-Football). When the active provider does
# not support them the endpoints return {"available": false} and the UI shows
# an honest empty state instead of fabricated numbers.
# ---------------------------------------------------------------------------

_STAT_LABELS = {
    "shots on goal": ("Shots on target", "attack"),
    "total shots": ("Total shots", "attack"),
    "blocked shots": ("Blocked shots", "attack"),
    "shots insidebox": ("Shots inside box", "attack"),
    "shots outsidebox": ("Shots outside box", "attack"),
    "fouls": ("Fouls", "discipline"),
    "corner kicks": ("Corners", "attack"),
    "offsides": ("Offsides", "discipline"),
    "ball possession": ("Possession %", "possession"),
    "yellow cards": ("Yellow cards", "discipline"),
    "red cards": ("Red cards", "discipline"),
    "goalkeeper saves": ("Goalkeeper saves", "defence"),
    "total passes": ("Passes", "possession"),
    "passes accurate": ("Passes accurate", "possession"),
    "passes %": ("Pass accuracy %", "possession"),
}


def _parse_stat_value(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip().replace("%", "")
    try:
        num = float(text)
    except ValueError:
        return None
    return int(num) if float(num).is_integer() else num


def _normalize_api_football_statistics(raw, match=None):
    """raw: API-Football fixtures/statistics response (list of team blocks).

    Blocks are ordered home-first when the match model allows id matching.
    xG is intentionally absent: this endpoint does not provide it and we
    never fabricate advanced numbers.
    """
    if not isinstance(raw, list) or not raw:
        return {"available": False}

    # Order sides home-first when possible.
    if match is not None:
        home_pid = str(getattr(match.home_team, "provider_team_id", "") or "")
        away_pid = str(getattr(match.away_team, "provider_team_id", "") or "")

        def block_id(block):
            return str((block.get("team") or {}).get("id") or "")

        if home_pid or away_pid:
            home_idx = next((i for i, b in enumerate(raw) if home_pid and block_id(b) == home_pid), None)
            away_idx = next((i for i, b in enumerate(raw) if away_pid and block_id(b) == away_pid), None)
            if home_idx is not None and away_idx is not None and away_idx < home_idx:
                raw = [raw[away_idx], raw[home_idx]]
            elif home_idx is None and away_idx == 0 and len(raw) > 1:
                raw = [raw[1], raw[0]]

    def side(team_block):
        stats_out = []
        for item in team_block.get("statistics", []) or []:
            label_raw = str(item.get("type") or "").strip()
            mapped = _STAT_LABELS.get(label_raw.lower())
            if not mapped:
                continue
            value = _parse_stat_value(item.get("value"))
            if value is None:
                continue
            stats_out.append({"label": mapped[0], "group": mapped[1], "value": value})
        return stats_out

    sides = [side(block) for block in raw]
    if not any(sides):
        return {"available": False}

    # Pair values by label so the UI gets home/away columns.
    by_label: dict[str, dict] = {}
    for idx, rows in enumerate(sides):
        for row in rows:
            slot = by_label.setdefault(row["label"], {"label": row["label"], "group": row["group"], "home": None, "away": None})
            slot["home" if idx == 0 else "away"] = row["value"]

    return {
        "available": True,
        "period": "full",
        "stats": [
            {k: s[k] for k in ("label", "group", "home", "away")}
            for s in by_label.values()
        ],
    }


def get_match_statistics(match):
    if not match or not match.provider_match_id:
        return {"available": False}
    provider_name = (match.provider_name or "").lower()
    if provider_name != "api-football":
        return {"available": False}
    provider = get_provider(match.provider_name)
    fetch_stats = getattr(provider, "fetch_match_statistics", None)
    if fetch_stats is None:
        return {"available": False}

    result = get_or_refresh_cache(
        "api-football",
        f"stats:{match.provider_match_id}",
        ttl_seconds=max(_status_ttl(match.status), 60),
        stale_seconds=STALE_FALLBACK_SECONDS,
        fetcher=lambda: _normalize_api_football_statistics(fetch_stats(match.provider_match_id), match),
        fallback={"available": False},
    )
    payload = result.payload if isinstance(result.payload, dict) else {"available": False}
    return payload


def _lineup_side_payload(block):
    if not isinstance(block, dict):
        return None

    def player_row(entry):
        player = entry.get("player", {}) or {}
        return {
            "name": player.get("name") or "",
            "number": player.get("number"),
            "position": player.get("pos"),
            "grid": player.get("grid"),
        }

    startXI = [player_row(e) for e in (block.get("startXI") or [])]
    startXI = [p for p in startXI if p["name"]]
    subs = [player_row(e) for e in (block.get("substitutes") or [])]
    subs = [p for p in subs if p["name"]]
    return {
        "formation": block.get("formation"),
        "startingXI": startXI,
        "substitutes": subs,
    }


def _normalize_api_football_lineups(raw, match):
    if not isinstance(raw, list) or not raw:
        return {"available": False}

    def pick(team_model):
        # Prefer provider id matching, fall back to slug comparison.
        pid = str(getattr(team_model, "provider_team_id", "") or "")
        for block in raw:
            block_id = str((block.get("team") or {}).get("id") or "")
            if pid and block_id == pid:
                return block
        want = getattr(team_model, "slug", "") or ""
        want_name = str(getattr(team_model, "name", "") or "")
        for block in raw:
            name = str((block.get("team") or {}).get("name") or "")
            if want and name.lower().replace("-", " ") == want.replace("-", " "):
                return block
            if want_name and name.lower() == want_name.lower():
                return block
        return None

    home_block = pick(match.home_team)
    away_block = next(
        (b for b in raw if b is not home_block), None
    ) if home_block else (raw[1] if len(raw) > 1 else None)

    home = _lineup_side_payload(home_block) if home_block else None
    away = _lineup_side_payload(away_block) if away_block else None
    if not (home and home["startingXI"]) and not (away and away["startingXI"]):
        return {"available": False}
    return {"available": True, "home": home, "away": away}


def get_match_lineups(match):
    if not match or not match.provider_match_id:
        return {"available": False}
    provider_name = (match.provider_name or "").lower()
    if provider_name != "api-football":
        return {"available": False}
    provider = get_provider(match.provider_name)
    fetch_lineups = getattr(provider, "fetch_lineups", None)
    if fetch_lineups is None:
        return {"available": False}

    result = get_or_refresh_cache(
        "api-football",
        f"lineups:{match.provider_match_id}",
        ttl_seconds=max(_status_ttl(match.status), 60),
        stale_seconds=STALE_FALLBACK_SECONDS,
        fetcher=lambda: _normalize_api_football_lineups(fetch_lineups(match.provider_match_id), match),
        fallback={"available": False},
    )
    payload = result.payload if isinstance(result.payload, dict) else {"available": False}
    return payload


# ---------------------------------------------------------------------------
# Competition & player depth: top scorers, player profiles, squads.
# Provider-dependent (API-Football). Endpoints degrade to {"available": false}.
# ---------------------------------------------------------------------------

TOP_SCORERS_TTL = 12 * 3600
PLAYER_TTL = 24 * 3600
SQUAD_TTL = 24 * 3600
TRANSFER_TTL = 6 * 3600
NEWS_TTL = 600


def _api_football_provider():
    """Return the API-Football provider instance or None when not configured."""
    try:
        provider = get_provider("api-football")
    except Exception:  # noqa: BLE001
        return None
    if provider is None or not getattr(provider, "api_key", None):
        return None
    return provider


def get_competition_topscorers(competition):
    if not competition:
        return {"available": False, "scorers": []}
    provider = _api_football_provider()
    if provider is None:
        return {"available": False, "scorers": []}
    fetch = getattr(provider, "fetch_top_scorers", None)
    if fetch is None:
        return {"available": False, "scorers": []}
    comp_id = competition.provider_competition_id or competition.slug

    result = get_or_refresh_cache(
        "api-football",
        f"topscorers:{comp_id}",
        ttl_seconds=TOP_SCORERS_TTL,
        stale_seconds=STALE_FALLBACK_SECONDS,
        fetcher=lambda: fetch(comp_id),
        fallback=[],
    )
    rows = result.payload if isinstance(result.payload, list) else []
    return {
        "available": bool(rows),
        "competition": competition.slug,
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "stale": result.stale,
        "scorers": rows[:25],
    }


def _normalize_api_football_player(raw):
    """raw: API-Football `players` response for a single player+season."""
    if not isinstance(raw, list) or not raw:
        return {"available": False}
    block = raw[0]
    player = block.get("player") or {}
    stats = block.get("statistics") or []

    def stat_row(s):
        games = s.get("games") or {}
        goals = s.get("goals") or {}
        cards = s.get("cards") or {}
        shots = s.get("shots") or {}
        passes = s.get("passes") or {}
        tackles = s.get("tackles") or {}
        dribbles = s.get("dribbles") or {}
        duels = s.get("duels") or {}
        penalty = s.get("penalty") or {}
        league = s.get("league") or {}
        team = s.get("team") or {}
        return {
            "season": str(s.get("season") or ""),
            "league": league.get("name"),
            "team": team.get("name"),
            "position": (games.get("position") or ""),
            "appearances": games.get("appeareances"),
            "minutes": games.get("minutes"),
            "rating": games.get("rating"),
            "goals": goals.get("total"),
            "assists": goals.get("assists"),
            "shots": shots.get("total"),
            "shots_on_target": shots.get("on"),
            "pass_accuracy": passes.get("accuracy"),
            "tackles": tackles.get("total"),
            "blocks": tackles.get("blocks"),
            "interceptions": tackles.get("interceptions"),
            "duels_won_pct": duels.get("won"),
            "dribbles_success": dribbles.get("success"),
            "yellow": cards.get("yellow"),
            "red": cards.get("red"),
            "penalties_scored": penalty.get("scored"),
            "captain": games.get("captain"),
        }

    birth = player.get("birth") or {}
    height_m = None
    if player.get("height"):
        try:
            height_m = float(str(player["height"]).replace("cm", "").strip())
        except (TypeError, ValueError):
            height_m = None
    return {
        "available": True,
        "player": {
            "id": player.get("id"),
            "name": player.get("name"),
            "first_name": player.get("firstname"),
            "last_name": player.get("lastname"),
            "photo": player.get("photo"),
            "nationality": player.get("nationality"),
            "age": player.get("age"),
            "birth_date": birth.get("date"),
            "birth_place": birth.get("place"),
            "birth_country": birth.get("country"),
            "height_cm": height_m,
            "weight_kg": (str(player.get("weight")).replace("kg", "").strip() if player.get("weight") else None),
            "injured": player.get("injured"),
        },
        # newest season first when multiple blocks exist
        "statistics": [stat_row(s) for s in stats],
    }


def get_player_profile(player_id, season=None):
    provider = _api_football_provider()
    if provider is None:
        return {"available": False}
    fetch = getattr(provider, "fetch_player_profile", None)
    if fetch is None:
        return {"available": False}
    cache_season = season or "current"
    result = get_or_refresh_cache(
        "api-football",
        f"player:{player_id}:{cache_season}",
        ttl_seconds=PLAYER_TTL,
        stale_seconds=STALE_FALLBACK_SECONDS,
        fetcher=lambda: _normalize_api_football_player(fetch(player_id, season)),
        fallback={"available": False},
    )
    return result.payload if isinstance(result.payload, dict) else {"available": False}


def _normalize_api_football_squad(raw):
    if not isinstance(raw, list) or not raw:
        return {"available": False}
    block = raw[0] or {}
    players_out = []
    for p in block.get("players") or []:
        name = p.get("name")
        if not name:
            continue
        players_out.append(
            {
                "id": p.get("id"),
                "name": name,
                "number": p.get("number"),
                "position": p.get("position"),
                "age": p.get("age"),
            }
        )
    if not players_out:
        return {"available": False}
    return {
        "available": True,
        "team": (block.get("team") or {}).get("name"),
        "members": players_out,
    }


def get_team_squad(team):
    if not team:
        return {"available": False}
    provider = _api_football_provider()
    if provider is None:
        return {"available": False}
    fetch = getattr(provider, "fetch_team_squad", None)
    if fetch is None:
        return {"available": False}
    team_id = team.provider_team_id
    if not team_id:
        return {"available": False}

    result = get_or_refresh_cache(
        "api-football",
        f"squad:{team_id}",
        ttl_seconds=SQUAD_TTL,
        stale_seconds=STALE_FALLBACK_SECONDS,
        fetcher=lambda: _normalize_api_football_squad(fetch(team_id)),
        fallback={"available": False},
    )
    return result.payload if isinstance(result.payload, dict) else {"available": False}


# ---------------------------------------------------------------------------
# Transfers (API-Football transfers endpoint, per configured popular teams).
# ---------------------------------------------------------------------------

DEFAULT_TRANSFER_TEAM_IDS = "50,33,42,49,40,47,541,529,530,505,496,157,165,211,212"


def _normalize_api_football_transfers(raw, team_name_hint=""):
    """raw: API-Football transfers response for one team.

    Returns a flat list of moves involving that team.
    """
    out = []
    for entry in raw or []:
        player = entry.get("player") or {}
        for t in entry.get("transfers") or []:
            teams = t.get("teams") or {}
            tin = (teams.get("in") or {}).get("name")
            tout = (teams.get("out") or {}).get("name")
            if not tin or not tout or tin == tout:
                continue
            out.append(
                {
                    "player_id": player.get("id"),
                    "player": player.get("name"),
                    "date": t.get("date"),
                    "type": t.get("type"),  # "Free", "Loan", "N/A" or fee string like "€ 50M"
                    "from_team": tout,
                    "to_team": tin,
                    "team_hint": team_name_hint,
                }
            )
    return out


def get_recent_transfers(limit=40):
    provider = _api_football_provider()
    if provider is None:
        return {"available": False, "transfers": []}
    fetch = getattr(provider, "fetch_transfers", None)
    if fetch is None:
        return {"available": False, "transfers": []}

    import json as _json

    raw_ids = current_app.config.get("SPORTS_TRANSFER_TEAM_IDS") or DEFAULT_TRANSFER_TEAM_IDS
    if isinstance(raw_ids, str):
        try:
            ids = [int(x) for x in _json.loads(raw_ids)] if raw_ids.strip().startswith("[") else [
                int(x) for x in raw_ids.split(",") if x.strip().isdigit()
            ]
        except Exception:  # noqa: BLE001
            ids = []
    else:
        ids = list(raw_ids)

    merged = {}
    for tid in ids[:20]:
        result = get_or_refresh_cache(
            "api-football",
            f"transfers:{tid}",
            ttl_seconds=TRANSFER_TTL,
            stale_seconds=STALE_FALLBACK_SECONDS,
            fetcher=lambda tid=tid: _normalize_api_football_transfers(fetch(tid)),
            fallback=None,
        )
        payload = result.payload if isinstance(result.payload, list) else None
        if not payload and result.stale and result.error:
            continue
        for row in payload or []:
            key = f"{row.get('player')}-{row.get('date')}-{row.get('to_team')}"
            merged[key] = row

    rows = sorted(
        merged.values(),
        key=lambda r: r.get("date") or "",
        reverse=True,
    )[:limit]
    return {"available": bool(rows), "transfers": rows}


# ---------------------------------------------------------------------------
# Football news — free sources, no API key required.
# Primary: ESPN public site JSON per competition. Fallback/merge: BBC Sport RSS.
# ---------------------------------------------------------------------------

ESPN_LEAGUE_CODES = {
    "english-premier-league": "eng.1",
    "uefa-champions-league": "uefa.champions",
    "la-liga": "esp.1",
    "serie-a": "ita.1",
    "bundesliga": "ger.1",
    "ligue-1": "fra.1",
    "uefa-europa-league": "uefa.europa",
}


def _parse_iso_loose(value):
    if not value:
        return None
    try:
        from email.utils import parsedate_to_datetime

        return parsedate_to_datetime(value).isoformat()
    except Exception:  # noqa: BLE001
        pass
    return str(value)


def _fetch_espn_news(league_code, limit=10):
    import requests as _requests

    url = f"https://site.web.api.espn.com/apis/v2/sports/soccer/{league_code}/news"
    resp = _requests.get(url, params={"lang": "en", "limit": limit}, timeout=8)
    resp.raise_for_status()
    data = resp.json() or {}
    out = []
    for article in data.get("articles", []) or []:
        link = (article.get("links") or {}).get("web") or (article.get("links") or {}).get("mobile")
        images = article.get("images") or []
        image = images[0].get("url") if images else None
        out.append(
            {
                "id": f"espn-{article.get('id') or article.get('published')}-{hash(article.get('headline', '')) % 99999}",
                "title": article.get("headline") or "",
                "description": article.get("description") or "",
                "link": link,
                "image": image,
                "source": "ESPN",
                "published_at": _iso_local(article.get("published")),
                "category": league_code,
            }
        )
    return [a for a in out if a["title"]]


def _iso_local(value):
    if not value:
        return None
    return str(value)


def _fetch_bbc_rss(limit=12):
    import xml.etree.ElementTree as ET

    import requests as _requests

    resp = _requests.get("https://feeds.bbci.co.uk/sport/football/rss.xml", timeout=8)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    out = []
    for item in root.iter("item"):
        title = item.findtext("title") or ""
        if not title:
            continue
        link = item.findtext("link") or ""
        description = item.findtext("description") or ""
        pub = _parse_iso_loose(item.findtext("pubDate"))
        image = None
        for el in item.iter():
            tag = el.tag.split("}")[-1]
            if tag == "thumbnail":
                image = el.attrib.get("url")
                break
        if not image:
            for el in item.iter():
                if el.tag.endswith("enclosure") and str(el.attrib.get("type", "")).startswith("image"):
                    image = el.attrib.get("url")
                    break
        out.append(
            {
                "id": f"bbc-{abs(hash(link)) % 999999999}",
                "title": title,
                "description": description,
                "link": link,
                "image": image,
                "source": "BBC Sport",
                "published_at": pub,
                "category": "football",
            }
        )
        if len(out) >= limit:
            break
    return out


def get_football_news(competition_slug=None, limit=18):
    """Merge ESPN competition news (when mapped) with BBC football RSS."""
    cache_key = f"news:{competition_slug or 'all'}"
    result = get_or_refresh_cache(
        "news",
        cache_key,
        ttl_seconds=NEWS_TTL,
        stale_seconds=STALE_FALLBACK_SECONDS,
        fetcher=lambda: _collect_news(competition_slug),
        fallback=[],
    )
    items = result.payload if isinstance(result.payload, list) else []
    return {
        "available": bool(items),
        "stale": result.stale,
        "articles": items[:limit],
    }


def _collect_news(competition_slug=None):
    articles = []
    codes = []
    if competition_slug and competition_slug in ESPN_LEAGUE_CODES:
        codes.append(ESPN_LEAGUE_CODES[competition_slug])
    else:
        codes.extend(ESPN_LEAGUE_CODES[c] for c in ("english-premier-league", "uefa-champions-league"))
    for code in codes:
        try:
            articles.extend(_fetch_espn_news(code))
        except Exception:  # noqa: BLE001
            continue
    if len(articles) < 6:
        try:
            articles.extend(_fetch_bbc_rss())
        except Exception:  # noqa: BLE001
            pass
    # dedupe by title, sort by published desc where parseable
    seen = set()
    unique = []
    for a in articles:
        k = (a.get("title") or "").lower()
        if k and k not in seen:
            seen.add(k)
            unique.append(a)
    unique.sort(key=lambda a: a.get("published_at") or "", reverse=True)
    return unique
