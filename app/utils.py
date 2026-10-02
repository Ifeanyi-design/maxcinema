import os
import re
import traceback
from datetime import datetime

from tmdbv3api import TMDb, Movie, TV, Season as TMDBSeason
from slugify import slugify

# ---------------------------------------------------------
# DATABASE IMPORT
# ---------------------------------------------------------
try:
    from app.models import db, AllVideo, Movie as DbMovie, Series, Season, Episode, Genre
except ImportError:
    from ..models import db, AllVideo, Movie as DbMovie, Series, Season, Episode, Genre

# ⚙️ CONFIGURATION
tmdb = TMDb()
tmdb.api_key = os.environ.get("TMDB_API_KEY", "")
tmdb.language = 'en'
tmdb.debug = False


class ImportResult:
    """Outcome of an import.

    The old code returned a bare string and the route flashed "success" for
    anything that did not literally contain the word "Error" — so an import
    that changed nothing still looked like it worked. This carries an explicit
    status plus a human summary of what actually happened.
    """

    __slots__ = ("status", "message", "created", "updated", "skipped")

    def __init__(self, status, message, created=None, updated=0, skipped=None):
        self.status = status  # 'success' | 'warning' | 'error'
        self.message = message
        self.created = created or {}
        self.updated = updated
        self.skipped = skipped or []

    def __str__(self):
        return self.message


# ---------------------------------------------------------------------------
# Input parsing
#
# The admin form is filled in by a human, so "Season 3", "14 to 17" and
# "ep 14-17" all have to work. Previously anything the old parser could not
# understand was swallowed by a bare `except: pass`, which silently reset the
# range to "everything" — one typo and the importer pulled down an entire show.
# ---------------------------------------------------------------------------

_SEASON_PREFIX = r"(?:s(?:eason)?s?\.?\s*)?"
_EPISODE_PREFIX = r"(?:ep(?:isode)?s?\.?\s*)?"

_EPISODE_RANGE_RE = re.compile(
    r"^\s*" + _EPISODE_PREFIX + r"(\d+)\s*(?:-|\u2013|\u2014|to|through|thru)\s*"
    + _EPISODE_PREFIX + r"(\d+)\s*$",
    re.IGNORECASE,
)
_EPISODE_SINGLE_RE = re.compile(r"^\s*" + _EPISODE_PREFIX + r"(\d+)\s*$", re.IGNORECASE)
_ALL_WORDS = {"all", "none", "any", ""}


def parse_season_selection(raw):
    """Return (seasons, invalid_chunks). `seasons is None` means "every season"."""
    if raw is None:
        return None, []

    text = str(raw).strip()
    if text.lower() in _ALL_WORDS:
        return None, []

    seasons, invalid = [], []
    for chunk in re.split(r"[,;/]+|\s+and\s+|\s*&\s*", text, flags=re.IGNORECASE):
        chunk = chunk.strip()
        if not chunk:
            continue
        cleaned = re.sub(r"^\s*" + _SEASON_PREFIX, "", chunk, flags=re.IGNORECASE).strip()
        if not cleaned or not re.fullmatch(r"\d+(?:\s+\d+)*", cleaned):
            invalid.append(chunk)
            continue
        seasons.extend(int(n) for n in cleaned.split())

    ordered, seen = [], set()
    for n in seasons:
        if n not in seen:
            seen.add(n)
            ordered.append(n)

    return ordered, invalid


def parse_episode_selection(raw):
    """Return (start, end), or None meaning "every episode".

    Raises ValueError with a message the admin can act on rather than
    silently falling back to the whole season.
    """
    if raw is None:
        return None

    text = str(raw).strip()
    if text.lower() in _ALL_WORDS:
        return None

    match = _EPISODE_RANGE_RE.match(text)
    if match:
        start, end = int(match.group(1)), int(match.group(2))
    else:
        match = _EPISODE_SINGLE_RE.match(text)
        if not match:
            raise ValueError(
                f"Could not understand the episode range {raw!r}. "
                "Use a range like 14-17, a single episode like 5, "
                "or leave it blank / type All for every episode."
            )
        start = end = int(match.group(1))

    if start < 1 or end < 1:
        raise ValueError("Episode numbers start at 1.")
    if start > end:
        raise ValueError(
            f"Episode range {raw!r} is reversed — put the lower number first (e.g. 14-17)."
        )

    return start, end


class ContentImporter:
    def __init__(self):
        self.movie_api = Movie()
        self.tv_api = TV()
        self.season_api = TMDBSeason()
        self._tmdb_id_ok = None

    # --- HELPERS ---
    def _val(self, obj, key, default=None):
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    def _get_date(self, date_str):
        if not date_str: return None
        try: return datetime.strptime(str(date_str), '%Y-%m-%d').date()
        except: return None

    def _get_year(self, date_str):
        if not date_str: return None
        try: return int(str(date_str)[:4])
        except: return None

    def _get_runtime(self, mins):
        if not mins: return "0 min"
        try: return f"{int(mins)} min"
        except: return "0 min"

    def _get_cast(self, obj):
        cast_list = []
        if hasattr(obj, '_json'):
            credits = obj._json.get('credits', {})
            if isinstance(credits, dict): cast_list = credits.get('cast', [])
        elif hasattr(obj, 'credits'):
            credits = obj.credits
            if hasattr(credits, 'cast'): cast_list = credits.cast

        if not isinstance(cast_list, list): return ""
        names = []
        for c in cast_list[:5]:
            name = self._val(c, 'name')
            if name: names.append(name)
        return ", ".join(names)

    def _get_trailer(self, obj):
        videos = []
        if hasattr(obj, 'videos'):
            v_data = obj.videos
            if isinstance(v_data, dict): videos = v_data.get('results', [])
            elif hasattr(v_data, 'results'): videos = v_data.results

        for v in videos:
            if self._val(v, 'site') == "YouTube" and self._val(v, 'type') == "Trailer":
                key = self._val(v, 'key')
                if key: return f"https://www.youtube.com/watch?v={key}"
        return None

    def _generate_unique_slug(self, name, current_type):
        """Always returns a slug that is free to use.

        The previous version returned the *taken* slug whenever an existing row
        had the same type, which blew up the INSERT with a UNIQUE constraint
        error as soon as a series was matched by name but not by slug.
        """
        base_slug = slugify(name) or current_type
        candidate = base_slug
        counter = 0
        while AllVideo.query.filter_by(slug=candidate).first():
            counter += 1
            candidate = (
                f"{base_slug}-{current_type}"
                if counter == 1
                else f"{base_slug}-{current_type}-{counter}"
            )
        return candidate

    # --- TMDB ID SUPPORT ---
    # `tmdb_id` lets a re-import find the right row even after the admin has
    # renamed the title. The column may not exist yet on a database that has
    # not been migrated, so every use degrades gracefully to name matching.
    def _tmdb_id_available(self):
        """True when the all_video.tmdb_id column exists on this database."""
        if self._tmdb_id_ok is None:
            try:
                AllVideo.query.filter_by(tmdb_id=0).first()
                self._tmdb_id_ok = True
            except Exception:
                db.session.rollback()
                self._tmdb_id_ok = False
        return self._tmdb_id_ok

    def _lookup_by_tmdb_id(self, tmdb_id, media_type):
        if not self._tmdb_id_available():
            return None
        return AllVideo.query.filter_by(tmdb_id=int(tmdb_id), type=media_type).first()

    def _remember_tmdb_id(self, video, tmdb_id):
        """Backfill tmdb_id on a row we matched by title. Never fatal."""
        if video is None or not self._tmdb_id_available():
            return
        try:
            if not video.tmdb_id:
                video.tmdb_id = int(tmdb_id)
                db.session.commit()
        except Exception:
            db.session.rollback()

    def _set_tmdb_id(self, video, tmdb_id):
        """Stamp tmdb_id on a row that has not been committed yet."""
        if video is not None and self._tmdb_id_available():
            video.tmdb_id = int(tmdb_id)
        return video

    def _find_existing_video(self, tmdb_id, name, media_type):
        video = self._lookup_by_tmdb_id(tmdb_id, media_type)
        if video:
            return video, "tmdb id"

        video = AllVideo.query.filter_by(name=name, type=media_type).first()
        if video:
            self._remember_tmdb_id(video, tmdb_id)
            return video, "title"
        return None, None

    def link_genres(self, tmdb_genres):
        genre_objs = []
        if not isinstance(tmdb_genres, list):
             if hasattr(tmdb_genres, '_json'): tmdb_genres = tmdb_genres._json
             else: return []

        for g in tmdb_genres:
            g_name = self._val(g, 'name')
            if g_name:
                db_genre = Genre.query.filter_by(name=g_name).first()
                if not db_genre:
                    db_genre = Genre(name=g_name)
                    db.session.add(db_genre)
                    db.session.commit()
                genre_objs.append(db_genre)
        return genre_objs

    # --- IMPORT MOVIE ---
    def import_movie(self, tmdb_id):
        print(f"🔍 SEARCHING MOVIE ID: {tmdb_id}")
        if not tmdb.api_key:
            return ImportResult("error", "TMDB_API_KEY is not set in the environment variables.")

        try:
            m = self.movie_api.details(tmdb_id, append_to_response="credits,videos")
        except Exception as e:
            print(f"❌ TMDB FETCH ERROR: {e}")
            return ImportResult(
                "error",
                f"Could not find Movie ID {tmdb_id}. Check that TMDB_API_KEY is set and the ID is valid.",
            )

        try:
            existing_video, matched_by = self._find_existing_video(tmdb_id, m.title, 'movie')
            if existing_video:
                self._remember_tmdb_id(existing_video, tmdb_id)
                return ImportResult(
                    "warning",
                    f"Movie '{m.title}' is already in the library (matched by {matched_by}) — nothing imported.",
                )

            country_name = ""
            if hasattr(m, 'production_countries') and m.production_countries:
                country_name = self._val(m.production_countries[0], 'name')

            final_slug = self._generate_unique_slug(m.title, 'movie')

            video = AllVideo(
                name=m.title,
                slug=final_slug,
                type='movie',
                description=m.overview,
                image=f"https://image.tmdb.org/t/p/w500{m.poster_path}" if m.poster_path else None,
                year_produced=self._get_year(m.release_date),
                released_date=self._get_date(m.release_date),
                rating=m.vote_average,
                active=False,
                star_cast=self._get_cast(m),
                length=self._get_runtime(getattr(m, 'runtime', 0)),
                country=country_name,
                language=getattr(m, 'original_language', 'en'),
                trailer_url=self._get_trailer(m)
            )
            self._set_tmdb_id(video, tmdb_id)
            video.genres = self.link_genres(m.genres)
            db.session.add(video)
            db.session.commit()

            db_movie = DbMovie(all_video_id=video.id)
            db.session.add(db_movie)
            db.session.commit()

            self._submit_indexnow([video])

            print(f"✅ SUCCESS: Imported {m.title}")
            return ImportResult(
                "success",
                f"Imported movie '{m.title}' (TMDB {tmdb_id}) as an inactive draft — "
                "review it and set it live when you are ready.",
            )
        except Exception as e:
            db.session.rollback()
            print("❌ DATABASE ERROR (Movie):")
            traceback.print_exc()
            return ImportResult("error", f"Database error while importing movie: {e}")

    # --- IMPORT SERIES ---
    def import_series(self, tmdb_id, season_input=None, episode_input=None):
        print(f"🔍 SEARCHING SERIES ID: {tmdb_id}")
        if not tmdb.api_key:
            return ImportResult("error", "TMDB_API_KEY is not set in the environment variables.")

        # --- validate the admin's input BEFORE hitting TMDB ---
        try:
            target_seasons, invalid_seasons = parse_season_selection(season_input)
        except Exception as e:
            return ImportResult("error", f"Could not read the seasons field: {e}")

        if invalid_seasons:
            return ImportResult(
                "error",
                "Could not read these season values: "
                + ", ".join(repr(c) for c in invalid_seasons)
                + ". Use numbers such as 3 or 1, 2 — or leave the field blank for every season.",
            )

        try:
            episode_range = parse_episode_selection(episode_input)
        except ValueError as e:
            return ImportResult("error", str(e))

        try:
            s = self.tv_api.details(tmdb_id, append_to_response="credits,videos")
        except Exception as e:
            print(f"❌ TMDB FETCH ERROR: {e}")
            return ImportResult(
                "error",
                f"Could not find Series ID {tmdb_id}. Check that TMDB_API_KEY is set and the ID is valid.",
            )

        try:
            video, matched_by = self._find_existing_video(tmdb_id, s.name, 'series')
            created_series = False

            country_name = ""
            if hasattr(s, 'production_countries') and s.production_countries:
                country_name = self._val(s.production_countries[0], 'name')

            run_time = 45
            if hasattr(s, 'episode_run_time') and s.episode_run_time:
                run_time = s.episode_run_time[0]

            main_trailer = self._get_trailer(s)

            if not video:
                print(f"📝 Creating new Series entry for: {s.name}")
                final_slug = self._generate_unique_slug(s.name, 'series')

                video = AllVideo(
                    name=s.name,
                    slug=final_slug,
                    type='series',
                    description=s.overview,
                    image=f"https://image.tmdb.org/t/p/w500{s.poster_path}" if s.poster_path else None,
                    year_produced=self._get_year(s.first_air_date),
                    rating=s.vote_average,
                    active=True,
                    star_cast=self._get_cast(s),
                    length=self._get_runtime(run_time),
                    country=country_name,
                    language=getattr(s, 'original_language', 'en'),
                    trailer_url=main_trailer
                )
                self._set_tmdb_id(video, tmdb_id)
                video.genres = self.link_genres(s.genres)
                db.session.add(video)
                db.session.commit()

                series_entry = Series(all_video_id=video.id, num_seasons=0, num_episodes=0)
                db.session.add(series_entry)
                db.session.commit()
                created_series = True
            else:
                print(f"🔄 Series {s.name} exists (matched by {matched_by}), updating...")
                self._remember_tmdb_id(video, tmdb_id)
                series_entry = video.series
                if not series_entry:
                    series_entry = Series(all_video_id=video.id, num_seasons=0, num_episodes=0)
                    db.session.add(series_entry)
                    db.session.commit()

            # --- work out which seasons to touch ---
            available_seasons = {
                seas.season_number
                for seas in s.seasons
                if self._val(seas, 'season_number') is not None
            }

            if target_seasons is None:
                target_seasons = sorted(n for n in available_seasons if n > 0)

            not_on_tmdb = [n for n in target_seasons if n not in available_seasons]
            target_seasons = [n for n in target_seasons if n in available_seasons]

            print(f"📂 Processing Seasons: {target_seasons}")

            seasons_created = 0
            seasons_updated = 0
            episodes_created = 0
            episodes_refreshed = 0
            in_range_total = 0
            skipped = []

            for seas_num in target_seasons:
                print(f"  👉 Fetching Season {seas_num}...")
                try:
                    tmdb_season = self.season_api.details(tmdb_id, seas_num, append_to_response="credits,videos")
                except Exception as e:
                    print(f"  ⚠️ Skipped Season {seas_num} (TMDB Error: {e})")
                    skipped.append(f"season {seas_num} (TMDB error: {e})")
                    continue

                s_cast = self._get_cast(tmdb_season)
                s_trailer = self._get_trailer(tmdb_season) or main_trailer
                tmdb_overview = (self._val(tmdb_season, 'overview') or '').strip()

                db_season = Season.query.filter_by(
                    series_id=series_entry.id, season_number=seas_num
                ).first()

                if not db_season:
                    s_poster = self._val(tmdb_season, 'poster_path')
                    img_url = f"https://image.tmdb.org/t/p/w500{s_poster}" if s_poster else video.image
                    final_desc = tmdb_overview if tmdb_overview else (video.description or f"Season {seas_num}")

                    db_season = Season(
                        series_id=series_entry.id,
                        season_number=seas_num,
                        description=final_desc,
                        image=img_url,
                        release_date=self._get_date(self._val(tmdb_season, 'air_date')),
                        num_episodes=0,
                        cast=s_cast,
                        trailer_url=s_trailer
                    )
                    db.session.add(db_season)
                    db.session.commit()
                    seasons_created += 1
                else:
                    changed = False
                    if s_cast and db_season.cast != s_cast:
                        db_season.cast = s_cast
                        changed = True
                    if s_trailer and db_season.trailer_url != s_trailer:
                        db_season.trailer_url = s_trailer
                        changed = True
                    if tmdb_overview and not (db_season.description or '').strip():
                        db_season.description = tmdb_overview
                        changed = True
                    if changed:
                        seasons_updated += 1
                    db.session.commit()

                # --- Episodes ---
                for ep in tmdb_season.episodes:
                    ep_num = self._val(ep, 'episode_number')
                    if ep_num is None:
                        continue
                    ep_num = int(ep_num)
                    if episode_range and not (episode_range[0] <= ep_num <= episode_range[1]):
                        continue
                    in_range_total += 1

                    ep_name = self._val(ep, 'name') or f'Episode {ep_num}'
                    ep_still = self._val(ep, 'still_path')
                    ep_image = f"https://image.tmdb.org/t/p/w500{ep_still}" if ep_still else None
                    ep_overview = self._val(ep, 'overview') or ''
                    ep_air = self._get_date(self._val(ep, 'air_date'))
                    ep_runtime = self._get_runtime(self._val(ep, 'runtime', 0))

                    existing_ep = Episode.query.filter_by(
                        season_id=db_season.id, episode_number=ep_num
                    ).first()

                    if not existing_ep:
                        try:
                            new_ep = Episode(
                                season_id=db_season.id,
                                episode_number=ep_num,
                                name=ep_name,
                                description=ep_overview,
                                released_date=ep_air,
                                thumb_720p=ep_image,
                                length=ep_runtime,
                                cast=s_cast
                            )
                            db.session.add(new_ep)
                            db.session.commit()
                            episodes_created += 1
                        except Exception as e:
                            db.session.rollback()
                            print(f"    ❌ Ep {ep_num} Fail: {e}")
                            skipped.append(f"S{seas_num}E{ep_num} (database error)")
                        continue

                    # The old importer only ever INSERTED. An episode that was
                    # already there was left untouched forever, so re-running an
                    # import looked like it did nothing at all.
                    # Metadata is refreshed, but only where TMDB actually has a
                    # value — hand-written copy, links and view counts are kept.
                    touched = False
                    if ep_name and existing_ep.name != ep_name:
                        existing_ep.name = ep_name
                        touched = True
                    if ep_runtime and existing_ep.length != ep_runtime and ep_runtime != "0 min":
                        existing_ep.length = ep_runtime
                        touched = True
                    if ep_air and existing_ep.released_date != ep_air:
                        existing_ep.released_date = ep_air
                        touched = True
                    if ep_overview and not (existing_ep.description or '').strip():
                        existing_ep.description = ep_overview
                        touched = True
                    if ep_image and not (existing_ep.thumb_720p or '').strip():
                        existing_ep.thumb_720p = ep_image
                        touched = True
                    if s_cast and not (existing_ep.cast or '').strip():
                        existing_ep.cast = s_cast
                        touched = True

                    if touched:
                        episodes_refreshed += 1

                db.session.commit()
                db_season.num_episodes = Episode.query.filter_by(season_id=db_season.id).count()
                db.session.commit()

            # --- series totals ---
            series_entry.num_seasons = Season.query.filter_by(series_id=series_entry.id).count()
            series_entry.num_episodes = sum(
                Episode.query.filter_by(season_id=season.id).count()
                for season in series_entry.seasons
            )
            db.session.commit()

            # The old importer never pinged IndexNow at all, unlike the manual
            # add-episode route. Submitting the series detail URL once covers
            # the new content without firing hundreds of requests.
            self._submit_indexnow([video])

            print(f"✅ SUCCESS: Imported Series {s.name}")
            return self._build_series_result(
                s=s,
                tmdb_id=tmdb_id,
                created_series=created_series,
                matched_by=matched_by,
                seasons_created=seasons_created,
                seasons_updated=seasons_updated,
                episodes_created=episodes_created,
                episodes_refreshed=episodes_refreshed,
                in_range_total=in_range_total,
                not_on_tmdb=not_on_tmdb,
                skipped=skipped,
                episode_range=episode_range,
            )

        except Exception as e:
            db.session.rollback()
            print("❌ DATABASE ERROR (Series):")
            traceback.print_exc()
            return ImportResult("error", f"Database error while importing series: {e}")

    # --- RESULT SUMMARY ---
    def _build_series_result(
        self, s, tmdb_id, created_series, matched_by, seasons_created, seasons_updated,
        episodes_created, episodes_refreshed, in_range_total, not_on_tmdb, skipped,
        episode_range,
    ):
        """Tell the admin exactly what happened — including when nothing did."""
        parts = []
        header = f"{'Imported' if created_series else 'Updated'} series '{s.name}' (TMDB {tmdb_id})"
        if not created_series:
            header += f" — matched the existing entry by {matched_by}"
        parts.append(header)

        changes = []
        if seasons_created:
            changes.append(f"{seasons_created} new season(s)")
        if episodes_created:
            changes.append(f"{episodes_created} new episode(s)")
        if episodes_refreshed:
            changes.append(f"{episodes_refreshed} episode(s) refreshed from TMDB")
        if seasons_updated and not changes:
            changes.append(f"{seasons_updated} season(s) metadata updated")

        notes = []
        if not_on_tmdb:
            notes.append(
                "these seasons do not exist on TMDB: "
                + ", ".join(str(n) for n in not_on_tmdb)
            )
        if skipped:
            notes.append("skipped — " + "; ".join(skipped))
        if episode_range and in_range_total == 0 and not not_on_tmdb:
            notes.append(
                f"no episodes matched the range "
                f"{episode_range[0]}-{episode_range[1]} in the selected season(s)"
            )

        if changes:
            message = f"{'; '.join(parts)} — {', '.join(changes)}."
            if notes:
                message += " Note: " + " | ".join(notes) + "."
            return ImportResult(
                "success",
                message,
                created={"seasons": seasons_created, "episodes": episodes_created},
                updated=episodes_refreshed,
                skipped=not_on_tmdb + skipped,
            )

        # Nothing changed. Say so plainly instead of claiming success.
        message = (
            f"{'; '.join(parts)} — nothing to do. "
            "Everything you asked for is already in the library, so no rows were changed."
        )
        if notes:
            message += " Note: " + " | ".join(notes) + "."
        return ImportResult("warning", message, skipped=not_on_tmdb + skipped)

    # --- SEO ---
    def _submit_indexnow(self, videos):
        """Best-effort IndexNow ping for content that is actually live.

        Never breaks an import, and skips inactive drafts — pinging a search
        engine about a page that is not published yet does more harm than good.
        """
        live = [v for v in videos if v is not None and getattr(v, "active", False)]
        if not live:
            return

        try:
            from ..indexnow import submit_indexnow_urls, urls_for_video
        except ImportError:
            try:
                from app.indexnow import submit_indexnow_urls, urls_for_video
            except ImportError:
                return

        try:
            urls = []
            for video in live:
                urls.extend(urls_for_video(video))
            if urls:
                submit_indexnow_urls(urls)
        except Exception as e:
            print(f"ℹ️ IndexNow submit skipped: {e}")
