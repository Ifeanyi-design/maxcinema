"""Small, database-driven helpers for public search metadata.

Keeping this logic out of templates gives every title the same canonical URL,
clean descriptions, and structured data while still using the fields editors
already manage in ``AllVideo``, ``Genre``, ``Season``, and ``Episode``.
"""

from __future__ import annotations

import re
from html import unescape
from typing import Any, Iterable
from urllib.parse import urljoin

from flask import current_app, url_for
from slugify import slugify


DEFAULT_SOCIAL_IMAGE = "https://i.imgur.com/Ch4SMwG.png"


def _site_url() -> str:
    return current_app.config["SITE_BASE_URL"].rstrip("/")


def absolute_url(value: str | None, fallback: str | None = None) -> str:
    """Return an absolute, public URL without trusting the request host."""
    value = (value or fallback or "").strip()
    if value.startswith("//"):
        return f"https:{value}"
    if value.startswith(("http://", "https://")):
        return value
    return urljoin(f"{_site_url()}/", value.lstrip("/"))


def clean_text(value: Any, limit: int = 160) -> str:
    """Strip markup and trim text at a word boundary for meta descriptions."""
    text = unescape(str(value or ""))
    text = re.sub(r"<[^>]*>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    shortened = text[: limit + 1].rsplit(" ", 1)[0].strip()
    return f"{shortened}..."


def video_slug(video: Any) -> str:
    return video.slug or slugify(video.name)


def video_url(video: Any, season: int | None = None, episode: int | None = None) -> str:
    """The one public, indexable URL for a movie or series episode."""
    name = video_slug(video)
    if video.type == "series":
        return absolute_url(
            url_for(
                "main.series_details",
                det="series",
                name=name,
                id=video.id,
                season=season or 1,
                episode=episode or 1,
            )
        )
    return absolute_url(
        url_for("main.movie_details", det="movie", name=name, id=video.id)
    )


def _keywords(values: Iterable[Any]) -> str:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value:
            continue
        value = clean_text(value, 80)
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return ", ".join(result[:14])


def _breadcrumb(items: list[tuple[str, str]]) -> dict[str, Any]:
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": position,
                "name": name,
                "item": url,
            }
            for position, (name, url) in enumerate(items, start=1)
        ],
    }


def _page(
    *,
    title: str,
    description: str,
    canonical: str,
    image: str | None = None,
    page_type: str = "website",
    keywords: Iterable[Any] = (),
    schemas: Iterable[dict[str, Any]] = (),
    robots: str = "index,follow,max-image-preview:large",
) -> dict[str, Any]:
    return {
        "title": clean_text(title, 70),
        "description": clean_text(description, 160),
        "canonical": canonical,
        "image": absolute_url(image, DEFAULT_SOCIAL_IMAGE),
        "type": page_type,
        "keywords": _keywords(keywords),
        "schemas": list(schemas),
        "robots": robots,
    }


def build_video_seo(video: Any, *, season: Any = None, episode: Any = None) -> dict[str, Any]:
    """Build metadata and schema from a movie or a specific series episode."""
    genres = [genre.name for genre in (video.genres or [])]
    image = getattr(season, "image", None) or video.image
    year = video.year_produced
    year_label = f" ({year})" if year else ""

    if video.type == "series":
        season_number = getattr(season, "season_number", None) or 1
        episode_number = getattr(episode, "episode_number", None) or 1
        title = f"{video.name} Season {season_number} Episode {episode_number} | MaxCinema"
        source_description = getattr(episode, "description", None) or getattr(season, "description", None) or video.description
        description = (
            f"Watch {video.name} Season {season_number}, Episode {episode_number}"
            f" on MaxCinema. {clean_text(source_description, 100)}"
        )
        canonical = video_url(video, season_number, episode_number)
        series_url = video_url(video, 1, 1)
        series_schema: dict[str, Any] = {
            "@context": "https://schema.org",
            "@type": "TVSeries",
            "@id": f"{series_url}#series",
            "name": video.name,
            "description": clean_text(video.description, 300),
            "image": absolute_url(image, DEFAULT_SOCIAL_IMAGE),
            "genre": genres,
        }
        if video.series and video.series.num_seasons:
            series_schema["numberOfSeasons"] = video.series.num_seasons
        if video.series and video.series.num_episodes:
            series_schema["numberOfEpisodes"] = video.series.num_episodes
        episode_schema: dict[str, Any] = {
            "@type": "TVEpisode",
            "name": getattr(episode, "name", None) or f"{video.name} Season {season_number} Episode {episode_number}",
            "episodeNumber": episode_number,
            "partOfSeason": {"@type": "TVSeason", "seasonNumber": season_number},
            "partOfSeries": {"@id": f"{series_url}#series"},
        }
        if getattr(episode, "description", None):
            episode_schema["description"] = clean_text(episode.description, 300)
        if getattr(episode, "released_date", None):
            episode_schema["datePublished"] = episode.released_date.isoformat()
        series_schema["episode"] = episode_schema
        schemas = [
            series_schema,
            _breadcrumb([
                ("Home", absolute_url("/")),
                ("Series", absolute_url("/nav/all_series")),
                (video.name, canonical),
            ]),
        ]
        keywords = ["MaxCinema", video.name, "TV series", "Season", f"Season {season_number}", f"Episode {episode_number}", *genres, video.country, video.language]
    else:
        title = f"{video.name}{year_label} | MaxCinema"
        description = f"Watch {video.name}{year_label} on MaxCinema. {clean_text(video.description, 105)}"
        canonical = video_url(video)
        movie_schema: dict[str, Any] = {
            "@context": "https://schema.org",
            "@type": "Movie",
            "@id": f"{canonical}#movie",
            "name": video.name,
            "description": clean_text(video.description, 300),
            "image": absolute_url(image, DEFAULT_SOCIAL_IMAGE),
            "genre": genres,
        }
        if year:
            movie_schema["dateCreated"] = str(year)
        if video.released_date:
            movie_schema["datePublished"] = video.released_date.isoformat()
        if video.country:
            movie_schema["countryOfOrigin"] = {"@type": "Country", "name": video.country}
        if video.num_votes and video.num_votes > 0 and video.rating:
            movie_schema["aggregateRating"] = {
                "@type": "AggregateRating",
                "ratingValue": round(video.rating, 1),
                "ratingCount": video.num_votes,
                "bestRating": 5,
                "worstRating": 1,
            }
        schemas = [
            movie_schema,
            _breadcrumb([
                ("Home", absolute_url("/")),
                ("Movies", absolute_url("/nav/all_movie")),
                (video.name, canonical),
            ]),
        ]
        keywords = ["MaxCinema", video.name, "movie", year, *genres, video.country, video.language]

    return _page(
        title=title,
        description=description,
        canonical=canonical,
        image=image,
        page_type="video.movie",
        keywords=keywords,
        schemas=schemas,
    )


def build_collection_seo(
    *,
    title: str,
    description: str,
    canonical_path: str,
    items: Iterable[Any] = (),
    keywords: Iterable[Any] = (),
    page: int = 1,
    robots: str | None = None,
) -> dict[str, Any]:
    """Metadata for a DB-backed listing page, including an ItemList schema."""
    canonical = absolute_url(canonical_path)
    page_suffix = f" - Page {page}" if page > 1 else ""
    list_entries = []
    for position, item in enumerate(list(items)[:20], start=1):
        if not getattr(item, "id", None) or not getattr(item, "name", None):
            continue
        list_entries.append({
            "@type": "ListItem",
            "position": position,
            "url": video_url(item),
            "name": item.name,
        })
    schemas: list[dict[str, Any]] = [_breadcrumb([("Home", absolute_url("/")), (title, canonical)])]
    if list_entries:
        schemas.append({
            "@context": "https://schema.org",
            "@type": "ItemList",
            "name": title,
            "itemListElement": list_entries,
        })
    return _page(
        title=f"{title}{page_suffix} | MaxCinema",
        description=description,
        canonical=canonical,
        keywords=["MaxCinema", *keywords],
        schemas=schemas,
        robots=robots or ("noindex,follow" if page > 1 else "index,follow,max-image-preview:large"),
    )


def build_homepage_seo(items: Iterable[Any]) -> dict[str, Any]:
    canonical = absolute_url("/")
    homepage_schema = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "@id": f"{canonical}#website",
        "url": canonical,
        "name": "MaxCinema",
        "description": "Discover movies, TV series, anime, and trailers on MaxCinema.",
    }
    seo = build_collection_seo(
        title="Latest Movies, TV Series & Anime",
        description="Discover the latest movies, TV series, anime, and trailers added to MaxCinema.",
        canonical_path="/",
        items=items,
        keywords=["latest movies", "TV series", "anime", "Nollywood", "Hollywood"],
    )
    seo["schemas"].insert(0, homepage_schema)
    return seo


def build_page_seo(
    *,
    title: str,
    description: str,
    canonical_path: str,
    keywords: Iterable[Any] = (),
    image: str | None = None,
    robots: str = "index,follow,max-image-preview:large",
) -> dict[str, Any]:
    """Metadata for a public informational page without a title collection."""
    canonical = absolute_url(canonical_path)
    return _page(
        title=title,
        description=description,
        canonical=canonical,
        image=image,
        keywords=["MaxCinema", *keywords],
        schemas=[_breadcrumb([("Home", absolute_url("/")), (title, canonical)])],
        robots=robots,
    )


def build_trailer_seo(trailer: Any) -> dict[str, Any]:
    """Metadata for a trailer page that contains an embedded playable video."""
    canonical = absolute_url(
        url_for("main.watch_trailer", det="trailer_watch", name=trailer.slug)
    )
    title = f"{trailer.name} Trailer | MaxCinema"
    video_schema: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "VideoObject",
        "name": f"{trailer.name} Trailer",
        "description": clean_text(trailer.description, 300),
        "thumbnailUrl": absolute_url(trailer.image, DEFAULT_SOCIAL_IMAGE),
        "uploadDate": (trailer.date_added.isoformat() if trailer.date_added else None),
        "embedUrl": trailer.trailer_link,
    }
    if trailer.release_date:
        video_schema["datePublished"] = trailer.release_date.isoformat()
    # Schema properties with a null value are less useful and can trigger
    # validation warnings in search tools.
    video_schema = {key: value for key, value in video_schema.items() if value}
    return _page(
        title=title,
        description=f"Watch the official trailer for {trailer.name}. {clean_text(trailer.description, 105)}",
        canonical=canonical,
        image=trailer.image,
        page_type="video.other",
        keywords=["trailer", trailer.name, trailer.release_year, "movie trailer", "TV trailer"],
        schemas=[
            video_schema,
            _breadcrumb([
                ("Home", absolute_url("/")),
                ("Trailers", absolute_url("/trailers")),
                (trailer.name, canonical),
            ]),
        ],
    )
