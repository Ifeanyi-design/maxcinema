from __future__ import annotations

import logging
import re
from datetime import datetime

import requests

from .providers import SportsProvider

_log = logging.getLogger("apifootball")

DEFAULT_HOST = "https://v3.football.api-sports.io"

# API-Football uses its own league IDs (different from TheSportsDB).
APIFOOTBALL_LEAGUES = [
    {"id": 39, "name": "English Premier League", "country": "England", "featured": True},
    {"id": 140, "name": "La Liga", "country": "Spain", "featured": True},
    {"id": 78, "name": "Bundesliga", "country": "Germany", "featured": True},
    {"id": 135, "name": "Serie A", "country": "Italy", "featured": True},
    {"id": 61, "name": "Ligue 1", "country": "France", "featured": True},
    {"id": 2, "name": "UEFA Champions League", "country": "Europe", "featured": True},
    {"id": 3, "name": "UEFA Europa League", "country": "Europe", "featured": False},
]

# API-Football fixture.status.short -> our normalized status
STATUS_MAP = {
    "NS": "scheduled",
    "TBD": "scheduled",
    "PST": "postponed",
    "CANC": "cancelled",
    "ABD": "cancelled",
    "WO": "finished",
    "AWD": "finished",
    "1H": "live",
    "HT": "live",
    "2H": "live",
    "ET": "live",
    "P": "live",
    "BT": "live",
    "INT": "live",
    "LIVE": "live",
    "FT": "finished",
    "AET": "finished",
    "PEN": "finished",
}


def _slug(value, fallback="item"):
    text = str(value or fallback).strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or fallback


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


class ApiFootballProvider(SportsProvider):
    name = "api-football"

    def __init__(self, api_key=None, host=None, leagues=None):
        self.api_key = api_key
        self.host = (host or DEFAULT_HOST).rstrip("/")
        self.leagues = leagues or APIFOOTBALL_LEAGUES
        if not self.api_key:
            _log.warning("ApiFootballProvider initialized without an API key")

    # ---- low-level HTTP ----
    def _request(self, path, params=None):
        if not self.api_key:
            _log.warning("apifootball: no API key set; skipping %s", path)
            return {}
        url = f"{self.host}/{path}"
        headers = {"x-apisports-key": self.api_key}
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=20)
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            _log.warning("apifootball request failed %s: %s", path, exc)
            return {}
        errors = data.get("errors")
        if errors:
            _log.warning("apifootball error for %s: %s", path, errors)
            return {}
        return data

    def _response(self, path, params=None):
        return self._request(path, params).get("response", [])

    def _season(self, prev=False):
        now = datetime.utcnow()
        start = now.year if now.month >= 7 else now.year - 1
        if prev:
            start -= 1
        return start

    def _resolve_leagues(self, competition_id):
        if competition_id is None:
            return self.leagues
        cid = str(competition_id)
        match = [lg for lg in self.leagues if str(lg["id"]) == cid]
        if match:
            return match
        match = [lg for lg in self.leagues if _slug(lg["name"]) == cid]
        if match:
            return match
        return [{"id": competition_id, "name": cid, "country": "", "featured": False}]

    # ---- mapping ----
    def _map_fixture(self, f, league_id, league_name, featured):
        fixture = f.get("fixture", {})
        goals = f.get("goals", {}) or {}
        teams = f.get("teams", {}) or {}
        home = teams.get("home", {}) or {}
        away = teams.get("away", {}) or {}
        status_short = (fixture.get("status", {}) or {}).get("short", "NS")
        status = STATUS_MAP.get(status_short, "scheduled")
        elapsed = (fixture.get("status", {}) or {}).get("elapsed")
        return {
            "provider_match_id": str(fixture.get("id")),
            "sport_slug": "football",
            "competition_slug": _slug(league_name),
            "competition_provider_id": str(league_id),
            "home_team_slug": _slug(home.get("name")),
            "home_team_provider_id": str(home.get("id")) if home.get("id") else None,
            "away_team_slug": _slug(away.get("name")),
            "away_team_provider_id": str(away.get("id")) if away.get("id") else None,
            "home_team": home.get("name"),
            "away_team": away.get("name"),
            "home_score": _int(goals.get("home")),
            "away_score": _int(goals.get("away")),
            "status": status,
            "provider_status": (fixture.get("status", {}) or {}).get("long"),
            "provider_clock": status_short if status == "live" else None,
            "minute": elapsed,
            "kickoff_at": fixture.get("date"),
            "featured": bool(featured),
        }

    # ---- provider interface ----
    def fetch_sports(self):
        return [
            {
                "provider_sport_id": "football",
                "name": "Football",
                "slug": "football",
                "enabled": True,
                "display_order": 1,
            }
        ]

    def fetch_competitions(self, sport_slug="football"):
        if sport_slug != "football":
            return []
        out = []
        season = self._season()
        for lg in self.leagues:
            detail = self._response("leagues", params={"id": lg["id"]})
            league = detail[0] if detail else {}
            name = league.get("name") or lg["name"]
            out.append(
                {
                    "provider_competition_id": str(lg["id"]),
                    "sport_slug": "football",
                    "name": name,
                    "slug": _slug(name),
                    "country": league.get("country") or lg.get("country"),
                    "logo_url": league.get("logo"),
                    "current_season": str(season),
                    "enabled": True,
                    "featured": lg.get("featured", False),
                }
            )
        return out

    def fetch_teams(self, sport_slug="football", competition_id=None):
        out = []
        season = self._season()
        for lg in self._resolve_leagues(competition_id):
            data = self._response(
                "teams", params={"league": lg["id"], "season": season}
            )
            for item in data:
                t = item.get("team", {})
                out.append(
                    {
                        "provider_team_id": str(t.get("id")),
                        "sport_slug": "football",
                        "name": t.get("name"),
                        "slug": _slug(t.get("name")),
                        "short_name": t.get("code"),
                        "country": t.get("country"),
                        "logo_url": t.get("logo"),
                    }
                )
        return out

    def fetch_fixtures(self, competition_id=None):
        out = []
        season = self._season()
        for lg in self._resolve_leagues(competition_id):
            data = self._response(
                "fixtures", params={"league": lg["id"], "season": season}
            )
            if not data:
                data = self._response(
                    "fixtures", params={"league": lg["id"], "season": season - 1}
                )
            for f in data:
                out.append(self._map_fixture(f, lg["id"], lg["name"], lg.get("featured", False)))
        return out

    def fetch_live_matches(self):
        data = self._response("fixtures/live", params={"live": "all"})
        out = []
        for f in data:
            lg = f.get("league", {}) or {}
            out.append(
                self._map_fixture(
                    f,
                    lg.get("id"),
                    lg.get("name") or "Live",
                    lg.get("id") in {l["id"] for l in self.leagues},
                )
            )
        return out

    def fetch_match_events(self, match):
        provider_match_id = getattr(match, "provider_match_id", None)
        if not provider_match_id:
            return []
        data = self._response("fixtures/events", params={"fixture": provider_match_id})
        out = []
        for ev in data:
            team = ev.get("team", {}) or {}
            player = ev.get("player", {}) or {}
            assist = ev.get("assist", {}) or {}
            elapsed = (ev.get("time", {}) or {}).get("elapsed")
            etype = (ev.get("type") or "update").lower()
            detail = ev.get("detail") or ""
            summary = detail
            if ev.get("comments"):
                summary = f"{detail} ({ev['comments']})" if detail else ev["comments"]
            provider_event_id = f"{provider_match_id}-{elapsed}-{ev.get('type')}-{team.get('id')}"
            out.append(
                {
                    "provider_event_id": provider_event_id,
                    "event_type": etype,
                    "minute": elapsed,
                    "clock": f"{elapsed}'" if elapsed is not None else None,
                    "team_slug": _slug(team.get("name")),
                    "player_name": player.get("name") if player else None,
                    "related_player_name": assist.get("name") if assist else None,
                    "summary": summary,
                    "sort_order": elapsed or 0,
                }
            )
        return out

    def fetch_standings(self, competition):
        league_id = competition.provider_competition_id or competition.slug
        try:
            league_id = int(league_id)
        except (TypeError, ValueError):
            league_id = self._resolve_leagues(competition.slug)[0]["id"]
        season = self._season()
        data = self._response(
            "standings", params={"league": league_id, "season": season}
        )
        out = []
        for league_block in data:
            groups = league_block.get("leagues", {}).get("standings") or league_block.get(
                "standings"
            )
            if not groups:
                groups = league_block.get("standings")
            for group in groups or []:
                for row in group:
                    team = row.get("team", {}) or {}
                    all_stats = row.get("all", {}) or {}
                    goals = all_stats.get("goals", {}) or {}
                    out.append(
                        {
                            "team_slug": _slug(team.get("name")),
                            "position": row.get("rank"),
                            "played": all_stats.get("played"),
                            "won": all_stats.get("won"),
                            "drawn": all_stats.get("draw"),
                            "lost": all_stats.get("lost"),
                            "goals_for": goals.get("for"),
                            "goals_against": goals.get("against"),
                            "goal_difference": row.get("goalsDiff"),
                            "points": row.get("points"),
                            "group_name": row.get("group"),
                        }
                    )
        return out

    # ---- extended capabilities (not yet surfaced by the API; ready for Phase 5/3) ----
    def fetch_lineups(self, fixture_id):
        return self._response("fixtures/lineups", params={"fixture": fixture_id})

    def fetch_match_statistics(self, fixture_id):
        return self._response("fixtures/statistics", params={"fixture": fixture_id})

    def fetch_top_scorers(self, competition_id=None, season=None):
        season = season or self._season()
        out = []
        for lg in self._resolve_leagues(competition_id):
            data = self._response(
                "players/topscorers", params={"league": lg["id"], "season": season}
            )
            for item in data:
                player = item.get("player", {}) or {}
                stats = item.get("statistics", [{}])[0] if item.get("statistics") else {}
                out.append(
                    {
                        "league_id": lg["id"],
                        "league_name": lg["name"],
                        "player_id": player.get("id"),
                        "player_name": player.get("name"),
                        "photo": player.get("photo"),
                        "goals": (stats.get("goals", {}) or {}).get("total"),
                        "assists": (stats.get("goals", {}) or {}).get("assists"),
                        "appearences": (stats.get("games", {}) or {}).get("appearances"),
                    }
                )
        return out
