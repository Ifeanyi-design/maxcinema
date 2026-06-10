from .state import MatchState
from ..models import SportsStreamSource


def resolve_stream(match):
    manual = (
        SportsStreamSource.query
        .filter_by(match_id=match.id, enabled=True)
        .order_by(SportsStreamSource.priority.asc())
        .first()
    )
    if manual:
        return {
            "available": True,
            "source_type": manual.source_type,
            "title": manual.title,
            "embed_url": manual.embed_url,
            "external_url": manual.external_url,
            "provider_name": manual.provider_name,
        }

    fallback = (
        SportsStreamSource.query
        .filter(SportsStreamSource.match_id.is_(None))
        .filter_by(enabled=True)
        .order_by(SportsStreamSource.priority.asc())
        .first()
    )
    if fallback:
        return {
            "available": True,
            "source_type": fallback.source_type,
            "title": fallback.title,
            "embed_url": fallback.embed_url,
            "external_url": fallback.external_url,
            "provider_name": fallback.provider_name,
        }

    return {
        "available": False,
        "source_type": "none",
        "title": "No stream available",
        "embed_url": None,
        "external_url": None,
        "provider_name": None,
    }


def resolve_demo_stream():
    return {
        "available": False,
        "source_type": "none",
        "title": "No stream available yet",
        "embed_url": None,
        "external_url": None,
        "provider_name": None,
        "match": MatchState.demo().to_dict(),
    }

