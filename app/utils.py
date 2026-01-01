from tmdbv3api import TMDb, Movie, TV, Season as TMDBSeason, Episode as TMDBEpisode
from slugify import slugify
from datetime import datetime

# ---------------------------------------------------------
# FIX: Use 'app.models' to find the DB no matter where this file is
# ---------------------------------------------------------
try:
    from app.models import db, AllVideo, Movie as DbMovie, Series, Season, Episode, Genre
except ImportError:
    # Fallback: Try going up one level (..models)
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
    def _get_date(self, date_str):
        if not date_str: return None
        try: return datetime.strptime(date_str, '%Y-%m-%d').date()
        except: return None

    def _get_runtime(self, mins):
        if not mins: return "0m"
        try:
            val = int(mins)
            return f"{val // 60}h {val % 60}m"
        except: return "0m"

    def _get_cast(self, obj):
        """Access raw JSON to avoid 'getattr' crash on slicing."""
        cast_list = []
        if hasattr(obj, '_json'):
            credits = obj._json.get('credits', {})
            if isinstance(credits, dict):
                cast_list = credits.get('cast', [])
        elif hasattr(obj, 'credits'):
            credits = obj.credits
            if hasattr(credits, 'cast'):
                cast_list = credits.cast

        if not isinstance(cast_list, list): return ""

        names = []
        for c in cast_list[:5]:
            name = c.get('name') if isinstance(c, dict) else getattr(c, 'name', None)
            if name: names.append(name)

        return ", ".join(names)

    def _get_trailer(self, obj):
        """
        NEW: Hunts for a YouTube Trailer in the 'videos' results.
        """
        # 1. Get the list of videos (safely)
        videos = []
        if hasattr(obj, 'videos'):
            v_data = obj.videos
            # If it's a dict (from _json)
            if isinstance(v_data, dict):
                videos = v_data.get('results', [])
            # If it's an object (from wrapper)
            elif hasattr(v_data, 'results'):
                videos = v_data.results
        
        # 2. Loop and find the first official Trailer on YouTube
        for v in videos:
            # Handle Dict vs Object
            site = v.get('site') if isinstance(v, dict) else getattr(v, 'site', '')
            type_ = v.get('type') if isinstance(v, dict) else getattr(v, 'type', '')
            key = v.get('key') if isinstance(v, dict) else getattr(v, 'key', '')

            if site == "YouTube" and type_ == "Trailer" and key:
                return f"https://www.youtube.com/watch?v={key}"
        
        return None # No trailer found

    def link_genres(self, tmdb_genres):
        """Fixed: Uses raw access for genres to prevent crashes"""
        genre_objs = []
        if not isinstance(tmdb_genres, list):
             if hasattr(tmdb_genres, '_json'): tmdb_genres = tmdb_genres._json
             else: return []

        for g in tmdb_genres:
            g_name = g.get('name') if isinstance(g, dict) else getattr(g, 'name', None)
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
        # 1. Fetch Data (Request credits AND videos)
        try:
            m = self.movie_api.details(tmdb_id, append_to_response="credits,videos")
        except:
            return "Error: TMDB ID invalid."

        if AllVideo.query.filter_by(name=m.title).first():
            return f"Movie '{m.title}' already exists."

        country_name = ""
        if hasattr(m, 'production_countries') and m.production_countries:
            c_obj = m.production_countries[0]
            country_name = getattr(c_obj, 'name', None) or c_obj.get('name')

        # 3. Create Master Video
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
            trailer_url=self._get_trailer(m)  # <--- NEW TRAILER FETCH
        )
        
        video.genres = self.link_genres(m.genres)
        
        db.session.add(video)
        db.session.commit() 

        db_movie = DbMovie(all_video_id=video.id)
        db.session.add(db_movie)
        db.session.commit()

        return f"Imported Movie: {m.title}"

    def import_series(self, tmdb_id, season_input=None, episode_input=None):
        try:
            s = self.tv_api.details(tmdb_id, append_to_response="credits,videos")
        except:
            return "Error: Series ID invalid."

        video = AllVideo.query.filter_by(name=s.name).first()
        series_entry = None

        country_name = ""
        if hasattr(s, 'production_countries') and s.production_countries:
            c_obj = s.production_countries[0]
            country_name = getattr(c_obj, 'name', None) or c_obj.get('name')

        run_time = 45
        if hasattr(s, 'episode_run_time') and s.episode_run_time:
            run_time = s.episode_run_time[0]

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
                trailer_url=self._get_trailer(s) # <--- NEW TRAILER FETCH
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

        # Seasons/Episodes Logic
        target_seasons = []
        if season_input:
            target_seasons = [int(x) for x in str(season_input).split(',') if x.strip().isdigit()]
        else:
            target_seasons = [seas.season_number for seas in s.seasons if seas.season_number > 0]

        for seas_num in target_seasons:
            try:
                tmdb_season = self.season_api.details(tmdb_id, seas_num)
            except:
                continue 

            db_season = Season.query.filter_by(series_id=series_entry.id, season_number=seas_num).first()
            if not db_season:
                db_season = Season(
                    series_id=series_entry.id,
                    season_number=seas_num,
                    description=tmdb_season.overview or f"Season {seas_num}",
                    image=f"https://image.tmdb.org/t/p/w500{tmdb_season.poster_path}" if tmdb_season.poster_path else video.image,
                    release_date=self._get_date(tmdb_season.air_date),
                    num_episodes=0
                )
                db.session.add(db_season)
                db.session.commit() 

            all_eps = tmdb_season.episodes
            start_ep, end_ep = 0, 9999
            if episode_input and episode_input.lower() != "all":
                try:
                    parts = episode_input.split('-')
                    start_ep = int(parts[0])
                    end_ep = int(parts[1])
                except:
                    pass 

            for ep in all_eps:
                if not (start_ep <= ep.episode_number <= end_ep): continue
                if Episode.query.filter_by(season_id=db_season.id, episode_number=ep.episode_number).first(): continue

                new_ep = Episode(
                    season_id=db_season.id,
                    episode_number=ep.episode_number,
                    name=ep.name,
                    description=ep.overview,
                    released_date=self._get_date(ep.air_date),
                    image=f"https://image.tmdb.org/t/p/w500{ep.still_path}" if ep.still_path else None,
                    length=self._get_runtime(getattr(ep, 'runtime', 0))
                )
                db.session.add(new_ep)
            
            db.session.commit()
            db_season.num_episodes = Episode.query.filter_by(season_id=db_season.id).count()
            db.session.commit()

        series_entry.num_seasons = Season.query.filter_by(series_id=series_entry.id).count()
        total = 0
        for s_obj in series_entry.seasons:
            total += s_obj.num_episodes
        series_entry.num_episodes = total
        db.session.commit()

        return f"Updated Series: {s.name} (Seasons: {target_seasons})"
