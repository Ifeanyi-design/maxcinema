from tmdbv3api import TMDb, Movie, TV, Season as TMDBSeason, Episode as TMDBEpisode
from slugify import slugify
from datetime import datetime
import traceback

# ---------------------------------------------------------
# FIX: Use 'app.models' to find the DB no matter where this file is
# ---------------------------------------------------------
try:
    from app.models import db, AllVideo, Movie as DbMovie, Series, Season, Episode, Genre
except ImportError:
    from ..models import db, AllVideo, Movie as DbMovie, Series, Season, Episode, Genre

# ⚙️ CONFIGURATION
tmdb = TMDb()
tmdb.api_key = '3d6b99b6b66197eff0bbee7faab6cf5e'
tmdb.language = 'en'

class ContentImporter:
    def __init__(self):
        self.movie_api = Movie()
        self.tv_api = TV()
        self.season_api = TMDBSeason()

    # --- HELPERS ---
    def _val(self, obj, key, default=None):
        """Universal Helper: Gets value from Dict OR Object safely."""
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    def _get_date(self, date_str):
        if not date_str: return None
        try: return datetime.strptime(str(date_str), '%Y-%m-%d').date()
        except: return None

    def _get_runtime(self, mins):
        """Returns format: '100 min'"""
        if not mins: return "0 min"
        try:
            return f"{int(mins)} min"
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

    # --- MAIN FUNCTIONS ---
    def import_movie(self, tmdb_id):
        try:
            m = self.movie_api.details(tmdb_id, append_to_response="credits,videos")
        except:
            return "Error: TMDB ID invalid."

        if AllVideo.query.filter_by(name=m.title).first():
            return f"Movie '{m.title}' already exists."

        country_name = ""
        if hasattr(m, 'production_countries') and m.production_countries:
            country_name = self._val(m.production_countries[0], 'name')

        video = AllVideo(
            name=m.title,
            slug=slugify(m.title),
            type='movie',
            description=m.overview,
            image=f"https://image.tmdb.org/t/p/w500{m.poster_path}" if m.poster_path else None,
            year_produced=str(m.release_date)[:4] if m.release_date else None,
            released_date=self._get_date(m.release_date),
            rating=m.vote_average,
            active=False,
            star_cast=self._get_cast(m),
            length=self._get_runtime(getattr(m, 'runtime', 0)),
            country=country_name,
            language=getattr(m, 'original_language', 'en'),
            trailer_url=self._get_trailer(m)
        )
        video.genres = self.link_genres(m.genres)
        db.session.add(video)
        db.session.commit() 

        db_movie = DbMovie(all_video_id=video.id)
        db.session.add(db_movie)
        db.session.commit()
        return f"Imported Movie: {m.title}"

    def import_series(self, tmdb_id, season_input=None, episode_input=None):
        print(f"DEBUG: --- Starting Series Import for ID {tmdb_id} ---")
        try:
            s = self.tv_api.details(tmdb_id, append_to_response="credits,videos")
        except Exception as e:
            return "Error: Series ID invalid."

        video = AllVideo.query.filter_by(name=s.name).first()
        series_entry = None

        country_name = ""
        if hasattr(s, 'production_countries') and s.production_countries:
            country_name = self._val(s.production_countries[0], 'name')
        
        run_time = 45
        if hasattr(s, 'episode_run_time') and s.episode_run_time:
            run_time = s.episode_run_time[0]

        # Get Main Trailer (Backup)
        main_trailer = self._get_trailer(s)

        if not video:
            video = AllVideo(
                name=s.name,
                slug=slugify(s.name),
                type='series',
                description=s.overview,
                image=f"https://image.tmdb.org/t/p/w500{s.poster_path}" if s.poster_path else None,
                year_produced=str(s.first_air_date)[:4] if s.first_air_date else None,
                rating=s.vote_average,
                active=True,
                star_cast=self._get_cast(s),
                length=self._get_runtime(run_time),
                country=country_name,
                language=getattr(s, 'original_language', 'en'),
                trailer_url=main_trailer
            )
            video.genres = self.link_genres(s.genres)
            db.session.add(video)
            db.session.commit()

            series_entry = Series(all_video_id=video.id, num_seasons=0, num_episodes=0)
            db.session.add(series_entry)
            db.session.commit()
        else:
            series_entry = video.series
            if not series_entry:
                series_entry = Series(all_video_id=video.id, num_seasons=0, num_episodes=0)
                db.session.add(series_entry)
                db.session.commit()

        # Parse Inputs
        target_seasons = []
        if season_input:
            target_seasons = [int(x) for x in str(season_input).split(',') if x.strip().isdigit()]
        else:
            target_seasons = [seas.season_number for seas in s.seasons if seas.season_number > 0]

        # Parse Episode Range
        start_ep, end_ep = 0, 9999
        if episode_input and str(episode_input).strip().lower() not in ["all", "", "none"]:
            try:
                parts = str(episode_input).split('-')
                start_ep = int(parts[0])
                end_ep = int(parts[1])
            except: pass

        for seas_num in target_seasons:
            try:
                tmdb_season = self.season_api.details(tmdb_id, seas_num, append_to_response="credits,videos")
            except:
                continue 

            # Get Cast & Trailer
            s_cast = self._get_cast(tmdb_season)
            s_trailer = self._get_trailer(tmdb_season)
            if not s_trailer:
                s_trailer = main_trailer

            # Get Raw TMDB Overview
            tmdb_overview = getattr(tmdb_season, 'overview', '').strip()

            db_season = Season.query.filter_by(series_id=series_entry.id, season_number=seas_num).first()
            
            if not db_season:
                # ---------------------------------------------------
                # [CASE 1] NEW SEASON: Create it.
                # Only here do we use the "Season X" fallback if text is empty.
                # ---------------------------------------------------
                s_poster = getattr(tmdb_season, 'poster_path', None)
                img_url = f"https://image.tmdb.org/t/p/w500{s_poster}" if s_poster else video.image
                
                final_desc = tmdb_overview if tmdb_overview else f"Season {seas_num}"
                
                db_season = Season(
                    series_id=series_entry.id,
                    season_number=seas_num,
                    description=final_desc,
                    image=img_url,
                    release_date=self._get_date(getattr(tmdb_season, 'air_date', None)),
                    num_episodes=0,
                    cast=s_cast,
                    trailer_url=s_trailer
                )
                db.session.add(db_season)
                db.session.commit()
            
            else:
                # ---------------------------------------------------
                # [CASE 2] EXISTING SEASON: Safe Update.
                # We intentionally DO NOT update the description here.
                # This ensures your existing descriptions remain untouched.
                # ---------------------------------------------------
                if s_cast: db_season.cast = s_cast
                if s_trailer: db_season.trailer_url = s_trailer
                
                # OPTIONAL: Uncomment the lines below ONLY if you want to overwrite 
                # existing descriptions when TMDB has new, valid text.
                # if tmdb_overview and len(tmdb_overview) > 10:
                #    db_season.description = tmdb_overview
                
                db.session.commit()

            # --- EPISODES LOGIC ---
            all_eps = tmdb_season.episodes
            count_added = 0
            for ep in all_eps:
                ep_num = self._val(ep, 'episode_number')
                
                if ep_num is None: continue
                if not (start_ep <= int(ep_num) <= end_ep): continue
                if Episode.query.filter_by(season_id=db_season.id, episode_number=ep_num).first(): continue

                try:
                    ep_name = self._val(ep, 'name', f'Episode {ep_num}')
                    ep_still = self._val(ep, 'still_path')
                    img_url = f"https://image.tmdb.org/t/p/w500{ep_still}" if ep_still else None

                    new_ep = Episode(
                        season_id=db_season.id,
                        episode_number=ep_num,
                        name=ep_name,
                        description=self._val(ep, 'overview', ''),
                        released_date=self._get_date(self._val(ep, 'air_date')),
                        thumb_720p=img_url, 
                        length=self._get_runtime(self._val(ep, 'runtime', 0)),
                        cast=s_cast 
                    )
                    db.session.add(new_ep)
                    count_added += 1
                except Exception as e:
                    print(f"DEBUG: Error creating Ep {ep_num}: {e}")

            try:
                db.session.commit()
            except:
                db.session.rollback()

            # Recalculate counts
            db_season.num_episodes = Episode.query.filter_by(season_id=db_season.id).count()
            db.session.commit()

        series_entry.num_seasons = Season.query.filter_by(series_id=series_entry.id).count()
        total = 0
        for s_obj in series_entry.seasons:
            total += s_obj.num_episodes
        series_entry.num_episodes = total
        db.session.commit()

        return f"Updated Series: {s.name} (Seasons: {target_seasons})"
