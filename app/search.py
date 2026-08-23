"""Shared video search matching for live search and the results page."""

from sqlalchemy import case, func, or_

from .models import AllVideo, Genre, SocialVideo

# Hyphens (including unicode dashes) plus common title punctuation.
_STRIP_CHARS = [
    "-",
    ":",
    "'",
    ".",
    ",",
    "!",
    "?",
    "&",
    "/",
    "(",
    ")",
    "[",
    "]",
    '"',
    "\u2010",
    "\u2011",
    "\u2012",
    "\u2013",
    "\u2014",
    "\u2212",
]


def compact_text(value):
    """Lowercase and strip punctuation/spaces: 'Spider-Man' -> 'spiderman'."""
    if not value:
        return ""
    text = value.lower()
    for ch in _STRIP_CHARS:
        text = text.replace(ch, "")
    return text.replace(" ", "")


def like_escape(value):
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def compact_sql(column):
    """SQL equivalent of compact_text(). Works on Postgres and SQLite."""
    expr = func.lower(column)
    for ch in _STRIP_CHARS:
        expr = func.replace(expr, ch, "")
    return func.replace(expr, " ", "")


def _compact_pattern(query):
    compact = compact_text(query)
    if not compact:
        return None
    return f"%{like_escape(compact)}%"


def _raw_pattern(query):
    raw = (query or "").strip()
    if not raw:
        return None
    return f"%{like_escape(raw)}%"


def title_match_filter(query):
    """True when the title or slug matches, ignoring hyphens/punctuation/spaces."""
    parts = []
    compact_pattern = _compact_pattern(query)
    raw_pattern = _raw_pattern(query)

    if compact_pattern:
        parts.append(compact_sql(AllVideo.name).like(compact_pattern, escape="\\"))
        parts.append(compact_sql(AllVideo.slug).like(compact_pattern, escape="\\"))
    if raw_pattern:
        # Keep original substring behavior so existing exact hits never regress.
        parts.append(AllVideo.name.ilike(raw_pattern, escape="\\"))

    if not parts:
        return None
    return or_(*parts)


def discovery_filter(query):
    """Broader matches from country, description, genre, and cast."""
    raw_pattern = _raw_pattern(query)
    compact_pattern = _compact_pattern(query)
    parts = []

    if raw_pattern:
        parts.extend(
            [
                AllVideo.country.ilike(raw_pattern, escape="\\"),
                AllVideo.description.ilike(raw_pattern, escape="\\"),
                AllVideo.genres.any(Genre.name.ilike(raw_pattern, escape="\\")),
                AllVideo.star_cast.ilike(raw_pattern, escape="\\"),
            ]
        )
    if compact_pattern:
        parts.append(compact_sql(AllVideo.star_cast).like(compact_pattern, escape="\\"))

    if not parts:
        return None
    return or_(*parts)


def video_search_filter(query):
    """Results-page filter: title hits OR discovery hits."""
    parts = [p for p in (title_match_filter(query), discovery_filter(query)) if p is not None]
    if not parts:
        return None
    return or_(*parts)


def live_search_filter(query):
    """Dropdown filter: title/slug compact match plus cast. No genre/description dump."""
    parts = []
    title = title_match_filter(query)
    if title is not None:
        parts.append(title)

    raw_pattern = _raw_pattern(query)
    compact_pattern = _compact_pattern(query)
    if raw_pattern:
        parts.append(AllVideo.star_cast.ilike(raw_pattern, escape="\\"))
    if compact_pattern:
        parts.append(compact_sql(AllVideo.star_cast).like(compact_pattern, escape="\\"))

    if not parts:
        return None
    return or_(*parts)


def title_hit_first(query):
    """Order expression: 0 for title/slug matches, 1 for discovery-only rows."""
    title = title_match_filter(query)
    if title is None:
        return None
    return case((title, 0), else_=1)


def social_search_filter(query):
    compact_pattern = _compact_pattern(query)
    raw_pattern = _raw_pattern(query)
    parts = []

    if compact_pattern:
        parts.extend(
            [
                compact_sql(SocialVideo.title).like(compact_pattern, escape="\\"),
                compact_sql(SocialVideo.tags).like(compact_pattern, escape="\\"),
                compact_sql(SocialVideo.description).like(compact_pattern, escape="\\"),
            ]
        )
    if raw_pattern:
        parts.extend(
            [
                SocialVideo.title.ilike(raw_pattern, escape="\\"),
                SocialVideo.tags.ilike(raw_pattern, escape="\\"),
                SocialVideo.description.ilike(raw_pattern, escape="\\"),
            ]
        )

    if not parts:
        return None
    return or_(*parts)
