from dataclasses import dataclass, field
from datetime import datetime


LIVE_STATUSES = {"live", "1h", "2h", "halftime", "extra_time", "penalties"}
FINISHED_STATUSES = {"fulltime", "finished", "ft", "after_extra_time", "after_penalties"}


def _iso(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return None


@dataclass(frozen=True)
class MatchState:
    id: int | None
    name: str
    sport: str
    competition: str | None
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    status: str
    provider_status: str | None = None
    provider_clock: str | None = None
    minute: int | None = None
    kickoff_at: datetime | None = None
    last_synced_at: datetime | None = None
    stale: bool = False
    events: list[dict] = field(default_factory=list)

    @property
    def is_live(self):
        return (self.status or "").lower() in LIVE_STATUSES

    @property
    def is_finished(self):
        return (self.status or "").lower() in FINISHED_STATUSES

    @classmethod
    def from_match(cls, match, events=None, stale=False):
        return cls(
            id=match.id,
            name=match.name,
            sport=match.sport.name if match.sport else "Football",
            competition=match.competition.name if match.competition else None,
            home_team=match.home_team.name if match.home_team else "Home",
            away_team=match.away_team.name if match.away_team else "Away",
            home_score=match.home_score or 0,
            away_score=match.away_score or 0,
            status=match.status or "scheduled",
            provider_status=match.provider_status,
            provider_clock=match.provider_clock,
            minute=match.minute,
            kickoff_at=match.kickoff_at,
            last_synced_at=match.last_synced_at,
            stale=stale,
            events=events or [],
        )

    @classmethod
    def demo(cls):
        return cls(
            id=None,
            name="World Cup Live Center",
            sport="Football",
            competition="Featured Football",
            home_team="Home Team",
            away_team="Away Team",
            home_score=0,
            away_score=0,
            status="scheduled",
            provider_status="Awaiting data provider",
            provider_clock=None,
            stale=True,
            events=[],
        )

    def to_dict(self, include_events=False):
        payload = {
            "id": self.id,
            "name": self.name,
            "sport": self.sport,
            "competition": self.competition,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "home_score": self.home_score,
            "away_score": self.away_score,
            "status": self.status,
            "provider_status": self.provider_status,
            "provider_clock": self.provider_clock,
            "minute": self.minute,
            "kickoff_at": _iso(self.kickoff_at),
            "last_synced_at": _iso(self.last_synced_at),
            "is_live": self.is_live,
            "is_finished": self.is_finished,
            "stale": self.stale,
        }
        if include_events:
            payload["events"] = self.events
        return payload

