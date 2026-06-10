from datetime import datetime, timedelta

from ..extensions import db
from ..models import SportsMatch, SportsMatchEvent, SportsProviderCache


def cleanup_old_sports_data(match_retention_days=30, cache_retention_days=7):
    now = datetime.utcnow()
    match_cutoff = now - timedelta(days=match_retention_days)
    cache_cutoff = now - timedelta(days=cache_retention_days)

    old_matches = (
        SportsMatch.query
        .filter(SportsMatch.archived.is_(False))
        .filter(SportsMatch.pinned.is_(False))
        .filter(SportsMatch.status.in_(["fulltime", "finished", "ft", "cancelled"]))
        .filter(SportsMatch.kickoff_at < match_cutoff)
        .all()
    )
    for match in old_matches:
        SportsMatchEvent.query.filter_by(match_id=match.id).delete()
        match.archived = True

    SportsProviderCache.query.filter(SportsProviderCache.updated_at < cache_cutoff).delete()
    db.session.commit()
    return {"archived_matches": len(old_matches)}

