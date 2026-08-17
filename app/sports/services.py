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
    competition.country = raw.get("country", competition.country)
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
    team.country = raw.get("country", team.country)
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
    if team:
        return team
    team = SportsTeam(
        sport=sport,
        slug=slug,
        name=raw.get(f"{side}_team") or slug.replace("-", " ").title(),
        provider_name=provider_name,
        provider_team_id=str(raw.get(f"{side}_team_provider_id") or slug),
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
