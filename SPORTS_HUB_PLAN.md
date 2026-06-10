# MaxCinema Sports Hub Plan

Status: Frozen architecture specification
Last updated: 2026-05-31

This document is the authoritative design for the MaxCinema Sports Hub. Do not overwrite or materially change it unless explicitly instructed.

## 1. Summary

Sports Hub is a modular second product area inside the existing MaxCinema Flask monolith. It lives under `app/sports/`, uses its own blueprint, services, templates, provider adapters, and public JSON APIs, and must not disturb the existing Movies, Series, Download, Trailer, Ads, or Admin systems.

V1 is football-first for World Cup readiness. The architecture supports rugby, wrestling, and future sports, but public activation should be phased.

Sports Hub V1 is public and anonymous. User accounts are not required for fixtures, scores, results, standings, match pages, timelines, or Watch Live.

## 2. Module Structure

Use a modular Flask subpackage:

```text
app/sports/
  __init__.py
  routes.py
  services.py
  providers.py
  stream_resolver.py
  retention.py
  serializers.py
```

Public routes should be registered through `sports_bp` at `/sports`.

Recommended route surface:

```text
/sports
/sports/football
/sports/<sport_slug>
/sports/<sport_slug>/competitions/<competition_slug>
/sports/match/<int:match_id>
/sports/match/<int:match_id>/watch
/sports/api/live-matches
/sports/api/match/<int:match_id>
/sports/api/match/<int:match_id>/events
/sports/api/competition/<int:competition_id>/standings
```

Admin routes stay in the existing admin blueprint:

```text
/admin/sports
/admin/sports/sync
/admin/sports/competitions
/admin/sports/competitions/<int:id>/toggle
/admin/sports/competitions/<int:id>/feature
/admin/sports/matches/<int:id>/streams
/admin/sports/matches/<int:id>/refresh
/admin/sports/retention
```

## 3. Data Strategy

Use SQLAlchemy models in the existing app model system and Alembic migrations.

Permanent metadata:

- sports
- competitions/leagues
- teams
- seasons
- provider mappings
- stream sources
- provider configuration

Lifecycle-retained operational data:

- matches
- match events/timelines
- standings snapshots
- provider response cache rows

Recommended core tables:

- `sports_sport`: sport identity, slug, enabled state, display order.
- `sports_competition`: sport-linked competition, provider IDs, enabled/featured/hidden flags.
- `sports_team`: team metadata, sport, country, logo, provider IDs.
- `sports_season`: competition season/year metadata when provider supports it.
- `sports_match`: home/away teams, competition, kickoff time, status, score, provider status, provider clock/minute, last synced.
- `sports_match_event`: normalized timeline entries such as goal, card, substitution, kickoff, halftime, fulltime.
- `sports_standing`: standings rows or snapshots for a competition/season.
- `sports_stream_source`: manual and provider-derived stream sources for Watch Live.
- `sports_provider_cache`: provider response cache with cache key, payload JSON, expiry, stale metadata.
- `sports_provider_mapping`: generic external ID mapping for sport, competition, team, season, match, and stream providers.

Indexes should prioritize high-read paths:

- sport slug
- competition slug
- match status
- kickoff time
- competition + kickoff
- provider name + provider entity ID
- match events by match ID + provider event ID + minute

## 4. Provider System

Provider APIs must be hidden behind adapters. Do not hardcode one API into routes or templates.

Adapter capabilities should be optional and discoverable:

- fetch sports
- fetch competitions/leagues
- fetch teams
- fetch seasons
- fetch fixtures
- fetch live matches
- fetch match detail
- fetch match events
- fetch standings
- lookup streams

V1 is free-first. Initial adapters may support football-data.org and/or TheSportsDB style APIs, but they must be replaceable by paid providers later.

Provider sync flow:

```text
provider API -> adapter normalization -> DB metadata/cache -> admin filtering -> public pages/API
```

Admin should not manually create every sport, competition, league, or team. API sync should populate available records, then admin enables, hides, or features selected competitions.

Provider failures must degrade gracefully:

- serve stale cached data when available
- show last updated timestamp
- never call provider APIs directly for every user request
- never block page rendering if provider is unavailable

## 5. Caching Strategy

V1 cache stack:

- Flask SimpleCache for fast local runtime cache.
- DB cache fallback via `sports_provider_cache`.
- Redis optional later through configuration only; do not require Redis for initial launch.

Cache rules:

- Public JSON endpoints serve normalized cached data.
- Provider APIs are called only by service refresh logic.
- Request-triggered refresh is allowed only when TTL has expired.
- Important match days can use a secret-protected cron/prewarm endpoint.
- Stale cached responses should be served during provider failure.

Suggested TTLs:

- Sports/competitions/teams: 12-24 hours.
- Upcoming matches: 15-60 minutes.
- Live matches: 15-60 seconds.
- Recently finished matches: 5-15 minutes for a short post-match window.
- Old finished matches: no refresh; retention job handles archive/purge.

## 6. Live Update System

### Provider to Backend

V1 uses provider API polling, not provider WebSockets.

Backend periodically or lazily fetches:

- fixtures
- live match status
- score updates
- match clock/minute
- standings
- timeline events

Match status and clock are provider-authoritative. Examples:

- scheduled
- live
- halftime
- fulltime
- postponed
- cancelled

Do not calculate official match time locally. Store provider status, provider minute/clock, provider timestamps, and `last_synced_at`.

### Backend to Browser

V1 uses cached browser polling.

Frontend polls lightweight JSON endpoints:

```text
/sports/api/live-matches
/sports/api/match/<id>
/sports/api/match/<id>/events
```

Polling intervals:

- live matches: 5-30 seconds
- upcoming matches: 1-5 minutes
- finished matches: slow polling or no polling

Frontend compares previous state with new state and only animates genuinely new updates:

- goals
- cards
- substitutions
- kickoff
- halftime
- fulltime
- score changes
- provider clock changes

### Future Upgrade Path

Do not hard-bind the architecture to polling. Keep the normalized event layer independent so future flow can become:

```text
provider API -> backend event layer -> SSE/WebSocket push -> browser
```

Future SSE/WebSockets should reuse serializers and event normalization rather than rewriting match pages.

## 7. Streaming Resolver Design

V1 Watch Live is an external resolver/gateway. MaxCinema must not host or proxy live video.

Resolver priority:

1. Manual admin override
2. Provider API stream lookup
3. Default URL / provider pattern generation
4. Sport default fallback source
5. No stream available state

Manual admin override supports:

- match-specific embed URL
- match-specific external link
- enable/disable source
- provider name
- priority
- notes/status

Provider lookup supports match metadata search:

- home team
- away team
- competition
- kickoff datetime
- sport type

Pattern generation supports predictable providers:

```text
provider.com/watch/{match_id}
provider.com/embed/{event_id}
provider.com/live/{sport}/{match_slug}
```

Allowed template variables:

- match ID
- external match ID
- provider match ID
- sport slug
- match slug/name
- competition slug/name
- kickoff date/time

If no stream is found, show a clean no-stream state and keep scores/timeline usable.

## 8. Retention Strategy

Do not permanently store every match/event forever.

Keep permanently:

- sports
- competitions
- teams
- seasons
- provider mappings
- stream sources
- provider configuration

Lifecycle retention:

- upcoming matches: cache until completion.
- live matches: aggressive refresh and short TTL.
- recently finished matches: retain for configurable period, default 7-30 days.
- old matches/events: archive or purge automatically.

Retention job behavior:

- purge old provider cache rows after expiry/stale grace.
- delete old match events after retention window unless match is pinned/featured.
- keep match summary longer than full event timeline.
- never delete permanent metadata during retention cleanup.

## 9. Admin System Design

Admin V1 should support:

- sports dashboard summary
- provider sync trigger
- enabled/hidden/featured competitions
- featured matches
- manual stream override per match
- forced match refresh
- provider cache status
- retention cleanup trigger

Admin is control/filtering, not manual data entry by default. Manual creation/editing is fallback only.

## 10. UI/UX Design

Public Sports Hub should feel like a strong secondary product while staying inside MaxCinema.

Shared navigation:

- persistent Sports entry in header/mobile nav.
- live pulse/badge when live matches exist.
- avoid intrusive forced animation interruptions.

Inside Sports Hub:

- clear Movie return action.
- football-first landing page.
- live match cards.
- today fixtures.
- results.
- standings tabs.
- match detail with score, status, timeline, and Watch Live.
- mobile-first layout for low bandwidth users.

Event animations:

- goal: score glow/toast.
- card: yellow/red flash.
- kickoff/halftime/fulltime: status banner.

Animations must not replay old events after refresh.

## 11. Phase Breakdown

### Phase 1: Core Sports Module Setup

- Add sports blueprint.
- Add DB models and migration.
- Add base public routes/pages.
- Add seed/demo fallback data path.
- Register blueprint in app factory.

### Phase 2: Provider Integration & Data Sync

- Add provider adapter interface.
- Add free-first provider adapter(s).
- Add provider response cache.
- Add sync service for sports, competitions, teams, fixtures, standings.
- Add admin sync controls.

### Phase 3: Live Match System

- Add live match refresh service.
- Add normalized event timeline service.
- Add cached JSON endpoints.
- Add browser polling script.
- Add event-diff animation behavior.

### Phase 4: Watch Live Resolver System

- Add stream source models/services.
- Add manual override admin UI.
- Add provider lookup hook.
- Add URL pattern generation.
- Add watch page/player/embed handling.

### Phase 5: UI/UX Integration

- Add Sports Hub templates.
- Add header/mobile nav entry.
- Add Sports return-to-movies transition.
- Add live badges and match cards.
- Rebuild Tailwind output.

### Phase 6: Admin Panel Tools

- Add sports dashboard.
- Add competition filters.
- Add featured competition/match controls.
- Add provider/cache/retention controls.

### Phase 7: Optimization & World Cup Readiness

- Add retention cleanup.
- Tune TTLs.
- Add stale fallback status messages.
- Add endpoint payload limits.
- Validate high-read routes.
- Confirm existing movie/download system unchanged.

## 12. Safety Rules

- Do not modify Movies module unless explicitly required.
- Do not introduce WebSockets in V1.
- Do not require Redis in V1.
- Do not self-host or proxy live video in V1.
- Do not redesign auth.
- Do not migrate to microservices.
- Keep Flask monolith with modular blueprints.
- Prioritize stability and World Cup readiness over complexity.

## 13. Phase 1 Implementation Constraints

- Define a unified `MatchState` service object and use it for both server-rendered pages and JSON APIs.
- Enforce cache coalescing so only one provider refresh can happen for a given cache key inside a TTL window.
- Provider failure must return fresh or stale cached data when any exists; it must not force empty UI states.
- Live endpoints must be read-optimized: compact payloads, limited rows, indexed queries, and cache-first service calls.
- Phase 1 must not modify Movies, Series, Download, or external Telegram download behavior.
