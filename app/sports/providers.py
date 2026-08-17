from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from flask import current_app


@dataclass(frozen=True)
class ProviderResult:
    payload: dict | list
    stale: bool = False
    error: str | None = None


class SportsProvider:
    name = "base"

    def fetch_sports(self):
        raise NotImplementedError

    def fetch_competitions(self, sport_slug="football"):
        raise NotImplementedError

    def fetch_teams(self, sport_slug="football", competition_id=None):
        raise NotImplementedError

    def fetch_fixtures(self, competition_id=None):
        raise NotImplementedError

    def fetch_live_matches(self):
        raise NotImplementedError

    def fetch_match_events(self, match):
        raise NotImplementedError

    def fetch_standings(self, competition):
        raise NotImplementedError

    def lookup_stream(self, match):
        return None


class MockFootballProvider(SportsProvider):
    name = "mock-football"

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
        return [
            {
                "provider_competition_id": "world-cup-2026",
                "sport_slug": "football",
                "name": "World Cup 2026",
                "slug": "world-cup-2026",
                "country": "International",
                "current_season": "2026",
                "enabled": True,
                "featured": True,
            },
            {
                "provider_competition_id": "featured-football",
                "sport_slug": "football",
                "name": "Featured Football",
                "slug": "featured-football",
                "country": "Global",
                "current_season": "2026",
                "enabled": True,
                "featured": False,
            },
        ]

    def fetch_teams(self, sport_slug="football", competition_id=None):
        if sport_slug != "football":
            return []
        return [
            {"provider_team_id": "nga", "sport_slug": "football", "name": "Nigeria", "slug": "nigeria", "short_name": "NGA", "country": "Nigeria"},
            {"provider_team_id": "gha", "sport_slug": "football", "name": "Ghana", "slug": "ghana", "short_name": "GHA", "country": "Ghana"},
            {"provider_team_id": "eng", "sport_slug": "football", "name": "England", "slug": "england", "short_name": "ENG", "country": "England"},
            {"provider_team_id": "bra", "sport_slug": "football", "name": "Brazil", "slug": "brazil", "short_name": "BRA", "country": "Brazil"},
            {"provider_team_id": "arg", "sport_slug": "football", "name": "Argentina", "slug": "argentina", "short_name": "ARG", "country": "Argentina"},
            {"provider_team_id": "fra", "sport_slug": "football", "name": "France", "slug": "france", "short_name": "FRA", "country": "France"},
        ]

    def fetch_fixtures(self, competition_id=None):
        now = datetime.utcnow().replace(microsecond=0)
        fixtures = [
            {
                "provider_match_id": "mock-live-nga-gha",
                "sport_slug": "football",
                "competition_slug": "world-cup-2026",
                "competition_provider_id": "world-cup-2026",
                "home_team_slug": "nigeria",
                "home_team_provider_id": "nga",
                "away_team_slug": "ghana",
                "away_team_provider_id": "gha",
                "home_team": "Nigeria",
                "away_team": "Ghana",
                "home_score": 1,
                "away_score": 1,
                "status": "live",
                "provider_status": "Second Half",
                "provider_clock": "63'",
                "minute": 63,
                "kickoff_at": (now - timedelta(minutes=63)).isoformat(),
                "featured": True,
            },
            {
                "provider_match_id": "mock-upcoming-eng-bra",
                "sport_slug": "football",
                "competition_slug": "world-cup-2026",
                "competition_provider_id": "world-cup-2026",
                "home_team_slug": "england",
                "home_team_provider_id": "eng",
                "away_team_slug": "brazil",
                "away_team_provider_id": "bra",
                "home_team": "England",
                "away_team": "Brazil",
                "home_score": 0,
                "away_score": 0,
                "status": "scheduled",
                "provider_status": "Scheduled",
                "provider_clock": None,
                "minute": None,
                "kickoff_at": (now + timedelta(hours=4)).isoformat(),
                "featured": True,
            },
            {
                "provider_match_id": "mock-finished-arg-fra",
                "sport_slug": "football",
                "competition_slug": "world-cup-2026",
                "competition_provider_id": "world-cup-2026",
                "home_team_slug": "argentina",
                "home_team_provider_id": "arg",
                "away_team_slug": "france",
                "away_team_provider_id": "fra",
                "home_team": "Argentina",
                "away_team": "France",
                "home_score": 2,
                "away_score": 1,
                "status": "finished",
                "provider_status": "Full Time",
                "provider_clock": "FT",
                "minute": 90,
                "kickoff_at": (now - timedelta(days=1, hours=2)).isoformat(),
                "featured": False,
            },
        ]
        if competition_id:
            return [
                fixture for fixture in fixtures
                if fixture["competition_provider_id"] == str(competition_id)
                or fixture["competition_slug"] == str(competition_id)
            ]
        return fixtures

    def fetch_live_matches(self):
        return [
            fixture for fixture in self.fetch_fixtures()
            if fixture.get("status") in {"live", "1h", "2h", "halftime", "extra_time", "penalties"}
        ]

    def fetch_match_events(self, match):
        provider_match_id = getattr(match, "provider_match_id", None)
        if provider_match_id == "mock-live-nga-gha":
            return [
                {
                    "provider_event_id": "mock-live-nga-gha-kickoff",
                    "event_type": "kickoff",
                    "minute": 0,
                    "clock": "0'",
                    "team_slug": None,
                    "player_name": None,
                    "related_player_name": None,
                    "summary": "Kickoff",
                    "sort_order": 1,
                },
                {
                    "provider_event_id": "mock-live-nga-gha-goal-nga",
                    "event_type": "goal",
                    "minute": 24,
                    "clock": "24'",
                    "team_slug": "nigeria",
                    "player_name": "Victor Osimhen",
                    "related_player_name": None,
                    "summary": "Nigeria goal",
                    "sort_order": 24,
                },
                {
                    "provider_event_id": "mock-live-nga-gha-goal-gha",
                    "event_type": "goal",
                    "minute": 55,
                    "clock": "55'",
                    "team_slug": "ghana",
                    "player_name": "Mohammed Kudus",
                    "related_player_name": None,
                    "summary": "Ghana equalizer",
                    "sort_order": 55,
                },
            ]
        return []

    def fetch_standings(self, competition):
        if getattr(competition, "slug", None) != "world-cup-2026":
            return []
        return [
            {"team_slug": "nigeria", "position": 1, "played": 1, "won": 0, "drawn": 1, "lost": 0, "goals_for": 1, "goals_against": 1, "goal_difference": 0, "points": 1, "group_name": "Group A"},
            {"team_slug": "ghana", "position": 2, "played": 1, "won": 0, "drawn": 1, "lost": 0, "goals_for": 1, "goals_against": 1, "goal_difference": 0, "points": 1, "group_name": "Group A"},
            {"team_slug": "england", "position": 3, "played": 0, "won": 0, "drawn": 0, "lost": 0, "goals_for": 0, "goals_against": 0, "goal_difference": 0, "points": 0, "group_name": "Group B"},
            {"team_slug": "brazil", "position": 4, "played": 0, "won": 0, "drawn": 0, "lost": 0, "goals_for": 0, "goals_against": 0, "goal_difference": 0, "points": 0, "group_name": "Group B"},
        ]


class DemoSportsProvider(MockFootballProvider):
    name = "demo"


PROVIDERS = {
    "mock": MockFootballProvider,
    "mock-football": MockFootballProvider,
    "demo": DemoSportsProvider,
}


def get_provider(provider_name=None):
    configured_name = provider_name or current_app.config.get("SPORTS_PROVIDER") or "thesportsdb"
    name = str(configured_name).lower()
    if name == "thesportsdb":
        # Lazy import to avoid a circular import with providers_thedb at boot.
        from .providers_thedb import TheSportsDBProvider

        key = current_app.config.get("SPORTS_TSDB_KEY")
        leagues = current_app.config.get("SPORTS_TSDB_LEAGUES")
        if isinstance(leagues, str) and leagues.strip().startswith("["):
            import json

            try:
                leagues = json.loads(leagues)
            except Exception:  # noqa: BLE001
                leagues = None
        return TheSportsDBProvider(api_key=key, leagues=leagues)
    if name == "api-football":
        # Lazy import to avoid a circular import with providers_apifootball at boot.
        from .providers_apifootball import ApiFootballProvider

        key = current_app.config.get("SPORTS_APIFOOTBALL_KEY")
        host = current_app.config.get("SPORTS_APIFOOTBALL_HOST")
        rapidapi_host = current_app.config.get("SPORTS_APIFOOTBALL_RAPIDAPI_HOST")
        return ApiFootballProvider(api_key=key, host=host, rapidapi_host=rapidapi_host)
    provider_class = PROVIDERS.get(name, MockFootballProvider)
    return provider_class()
