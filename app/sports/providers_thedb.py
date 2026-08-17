from __future__ import annotations

import logging
import re
from datetime import datetime

import requests

from .providers import SportsProvider

_log = logging.getLogger("thesportsdb")

BASE_URL = "https://www.thesportsdb.com/api/v1/json"


def _slug(value, fallback="item"):
    text = str(value or fallback).strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or fallback


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _normalize_status(raw):
    s = (raw or "").strip().lower()
    if s in ("", "tbd"):
        return "scheduled"
    if s in ("not started", "ns"):
        return "scheduled"
    if s == "postponed":
        return "postponed"
    if s == "cancelled":
        return "cancelled"
    if s in (
        "ft",
        "match finished",
        "finished",
        "fulltime",
        "aet",
        "after extra time",
        "after_extra_time",
        "pen",
        "pens",
        "after penalties",
        "after_penalties",
    ):
        return "finished"
    if s in (
        "in play",
        "live",
        "1h",
        "2h",
        "halftime",
        "ht",
        "et",
        "extra time",
        "penalties",
        "break",
        "suspended",
    ):
        return "live"
    return "scheduled"


def _kickoff(ev):
    ts = ev.get("strTimestamp")
    if ts:
        return ts
    d = ev.get("dateEvent")
    t = ev.get("strTime")
    if d and t:
        return f"{d}T{t}"
    return None


DEFAULT_LEAGUES = [
    {"id": "4328", "name": "English Premier League", "country": "England", "featured": True},
    {"id": "4335", "name": "La Liga", "country": "Spain", "featured": True},
    {"id": "4331", "name": "Bundesliga", "country": "Germany", "featured": True},
    {"id": "4332", "name": "Serie A", "country": "Italy", "featured": True},
    {"id": "4334", "name": "Ligue 1", "country": "France", "featured": True},
    {"id": "4480", "name": "UEFA Champions League", "country": "Europe", "featured": True},
    {"id": "4391", "name": "UEFA Europa League", "country": "Europe", "featured": False},
]


class TheSportsDBProvider(SportsProvider):
    name = "thesportsdb"

    def __init__(self, api_key=None, leagues=None):
        self.api_key = api_key or "3"
        self.leagues = leagues or DEFAULT_LEAGUES

    # ---- low-level HTTP ----
    def _get(self, path, params=None):
        url = f"{BASE_URL}/{self.api_key}/{path}"
        try:
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            _log.warning("thesportsdb request failed %s: %s", path, exc)
            return {}

    def _season(self, prev=False):
        now = datetime.utcnow()
        start = now.year if now.month >= 7 else now.year - 1
        if prev:
            start -= 1
        return f"{start}-{start + 1}"

    def _resolve_leagues(self, competition_id):
        if competition_id is None:
            return self.leagues
        cid = str(competition_id)
        match = [lg for lg in self.leagues if str(lg["id"]) == cid]
        if match:
            return match
        # try slug match
        match = [lg for lg in self.leagues if _slug(lg["name"]) == cid]
        if match:
            return match
        # assume a raw league id was passed
        return [{"id": competition_id, "name": cid, "country": "", "featured": False}]

    # ---- mapping ----
    def _map_match(self, ev, lg):
        lg_id = ev.get("idLeague") or (lg or {}).get("id")
        lg_name = ev.get("strLeague") or (lg or {}).get("name") or "Featured Football"
        progress = ev.get("strProgress")
        return {
            "provider_match_id": str(ev.get("idEvent")),
            "sport_slug": "football",
            "competition_slug": _slug(lg_name),
            "competition_provider_id": str(lg_id) if lg_id else None,
            "home_team_slug": _slug(ev.get("strHomeTeam")),
            "home_team_provider_id": str(ev.get("idHomeTeam")) if ev.get("idHomeTeam") else None,
            "away_team_slug": _slug(ev.get("strAwayTeam")),
            "away_team_provider_id": str(ev.get("idAwayTeam")) if ev.get("idAwayTeam") else None,
            "home_team": ev.get("strHomeTeam"),
            "away_team": ev.get("strAwayTeam"),
            "home_score": _int(ev.get("intHomeScore")),
            "away_score": _int(ev.get("intAwayScore")),
            "status": _normalize_status(ev.get("strStatus")),
            "provider_status": ev.get("strStatus"),
            "provider_clock": progress,
            "minute": _int(progress) if str(progress or "").isdigit() else None,
            "kickoff_at": _kickoff(ev),
            "featured": (lg or {}).get("featured", False),
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
        for lg in self.leagues:
            logo_url = None
            data = self._get("lookupleague.php", params={"id": lg["id"]})
            league = (data.get("leagues") or [{}])[0]
            if league:
                logo_url = league.get("strBadge") or league.get("strLogo")
            out.append(
                {
                    "provider_competition_id": lg["id"],
                    "sport_slug": "football",
                    "name": lg["name"],
                    "slug": _slug(lg["name"]),
                    "country": lg.get("country"),
                    "logo_url": logo_url,
                    "current_season": self._season(),
                    "enabled": True,
                    "featured": lg.get("featured", False),
                }
            )
        return out

    def fetch_teams(self, sport_slug="football", competition_id=None):
        out = []
        for lg in self._resolve_leagues(competition_id):
            data = self._get("lookup_all_teams.php", params={"id": lg["id"]})
            for t in data.get("teams") or []:
                out.append(
                    {
                        "provider_team_id": t.get("idTeam"),
                        "sport_slug": "football",
                        "name": t.get("strTeam"),
                        "slug": _slug(t.get("strTeam")),
                        "short_name": t.get("strTeamShort"),
                        "country": t.get("strCountry"),
                        "logo_url": t.get("strTeamBadge") or t.get("strBadge"),
                    }
                )
        return out

    def fetch_fixtures(self, competition_id=None):
        out = []
        for lg in self._resolve_leagues(competition_id):
            data = self._get("eventsseason.php", params={"id": lg["id"], "s": self._season()})
            events = data.get("events") or []
            if not events:
                data = self._get(
                    "eventsseason.php", params={"id": lg["id"], "s": self._season(prev=True)}
                )
                events = data.get("events") or []
            for ev in events:
                out.append(self._map_match(ev, lg))
        return out

    def fetch_live_matches(self):
        data = self._get("livescore.php")
        items = data.get("livescore") or []
        out = []
        for it in items:
            if (it.get("strSport") or "").lower() != "soccer":
                continue
            out.append(self._map_match(it, {"id": it.get("idLeague"), "name": it.get("strLeague")}))
        return out

    def fetch_match_events(self, match):
        # TheSportsDB free tier does not expose minute-by-minute timelines.
        return []

    def fetch_standings(self, competition):
        lg_id = competition.provider_competition_id or competition.slug
        data = self._get("lookuptable.php", params={"l": lg_id, "s": self._season()})
        rows = data.get("table") or []
        if not rows:
            data = self._get(
                "lookuptable.php", params={"l": lg_id, "s": self._season(prev=True)}
            )
            rows = data.get("table") or []
        out = []
        for r in rows:
            out.append(
                {
                    "team_slug": _slug(r.get("strTeam")),
                    "position": _int(r.get("intRank")),
                    "played": _int(r.get("intPlayed")),
                    "won": _int(r.get("intWin")),
                    "drawn": _int(r.get("intDraw")),
                    "lost": _int(r.get("intLoss")),
                    "goals_for": _int(r.get("intGoalsFor")),
                    "goals_against": _int(r.get("intGoalsAgainst")),
                    "goal_difference": _int(r.get("intGoalDifference")),
                    "points": _int(r.get("intPoints")),
                    "group_name": r.get("strGroup"),
                }
            )
        return out
