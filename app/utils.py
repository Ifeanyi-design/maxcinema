from tmdbv3api import TMDb, Movie, TV, Season as TMDBSeason, Episode as TMDBEpisode
from slugify import slugify
from datetime import datetime
from .models import db, AllVideo, Movie as DbMovie, Series, Season, Episode, Genre

# ==========================================
# ⚙️ CONFIGURATION (PASTE KEY HERE)
# ==========================================
tmdb = TMDb()
# 👇 DELETE THE OLD LINE AND PASTE YOUR ACTUAL KEY INSIDE THE QUOTES 👇
tmdb.api_key = '3d6b99b6b66197eff0bbee7faab6cf5e'  
tmdb.language = 'en'
# ==========================================

class ContentImporter:
    def __init__(self):
        self.movie_api = Movie()
        self.tv_api = TV()
        self.season_api = TMDBSeason()
        self.episode_api = TMDBEpisode()

    def _safe_date(self, date_str):
        """Prevents crash if API returns None or empty date"""
        if not date_str: return None
        try:
            return datetime.strptime(date_str, '%Y-%m-%d').date()
        except:
            return None

    def _get_cast_string(self, credits):
        """Helper to get top 5 actors"""
        if not credits or 'cast' not in credits: return ""
        return ", ".join([c['name'] for c in credits['cast'][:5]])

    def _format_runtime(self, runtime_mins):
        """Converts 130 -> 2h 10m"""
        if not runtime_mins: return ""
        try:
            val = int(runtime_mins)
            return f"{val // 60}h {val % 60}m"
        except: return ""

    def _get_country_lang(self, obj):
        """Helper to extract Country and Language safely"""
        c = obj.production_countries[0]['name'] if hasattr(obj, 'production_countries') and obj.production_countries else ""
        l = obj.original_language if hasattr(obj, 'original_language') else ""
        return c, l

    def get_or_create_genres(self, tmdb_genres):
        """Helper to link Genres"""
        genre_list = []
        for g in tmdb_genres:
            db_genre = Genre.query.filter_by(name=g['name']).first()
            if not db_genre:
                db_genre = Genre(name=g['name'])
                db.session.add(db_genre)
                db.session.commit()
            genre_list.append(db_genre)
        return genre_list

    def import_movie(self, tmdb_id):
        print(f"DEBUG: Starting Movie Import for ID: {tmdb_id}")
        try:
            m = self.movie_api.details(tmdb_id, append_to_response="credits")
        except Exception as e:
            print(f"DEBUG: API Error: {e}")
            return f"Error: TMDB ID {tmdb_id} not found."

        existing = AllVideo.query.filter_by(name=m.title).first()
        if existing: 
            print(f"DEBUG: Movie {m.title} already exists.")
            return f"Movie '{m.title}' already exists!"

        # Extract Fields
        print("DEBUG: Extracting details...")
        cast_str = self._get_cast_string(m.credits)
        runtime_str = self._format_runtime(getattr(m, 'runtime', 0))
        country_str, lang_str = self._get_country_lang(m)
        rel_date = self._safe_date(m.release_date)

        # Create AllVideo
        video = AllVideo(
            name=m.title,
            slug=slugify(m.title),
            type='movie',
            description=m.overview,
            image=f"https://image.tmdb.org/t/p/w500{m.poster_path}" if m.poster_path else None,
            year_produced=str(rel_date.year) if rel_date else None,
            released_date=rel_date,
            rating=m.vote_average,
            active=False,
            star_cast=cast_str,
            length=runtime_str,
            country=country_str,
            language=lang_str
        )
        
        video.genres = self.get_or_create_genres(m.genres)
        
        db.session.add(video)
        db.session.commit()
        print(f"DEBUG: Created AllVideo ID: {video.id}")

        # Create Movie Table
        db_movie = DbMovie(all_video_id=video.id)
        db.session.add(db_movie)
        db.session.commit()
        
        return f"Success: Imported Movie '{m.title}'"

    def import_series(self, tmdb_id, season_range=None, episode_range=None):
        print(f"DEBUG: Starting Series Import for ID: {tmdb_id}")
        
        try:
            s = self.tv_api.details(tmdb_id, append_to_response="credits")
        except Exception as e:
            print(f"DEBUG: API Error: {e}")
            return f"Error: Series ID {tmdb_id} not found."

        # 1. Check / Create Master Record
        video = AllVideo.query.filter_by(name=s.name).first()
        series_entry = None

        if not video:
            print(f"DEBUG: Creating NEW Series: {s.name}")
            cast_str = self._get_cast_string(s.credits)
            country_str, lang_str = self._get_country_lang(s)
            rel_date = self._safe_date(s.first_air_date)
            run_time = s.episode_run_time[0] if s.episode_run_time else 0

            video = AllVideo(
                name=s.name,
                slug=slugify(s.name),
                type='series',
                description=s.overview,
                image=f"https://image.tmdb.org/t/p/w500{s.poster_path}" if s.poster_path else None,
                year_produced=str(rel_date.year) if rel_date else None,
                rating=s.vote_average,
                active=True,
                star_cast=cast_str,
                country=country_str,
                language=lang_str,
                length=self._format_runtime(run_time)
            )
            video.genres = self.get_or_create_genres(s.genres)
            db.session.add(video)
            db.session.commit()

            series_entry = Series(all_video_id=video.id, num_seasons=0, num_episodes=0)
            db.session.add(series_entry)
            db.session.commit()
        else:
            print(f"DEBUG: Series {s.name} exists. Updating...")
            series_entry = video.series
            if not series_entry:
                series_entry = Series(all_video_id=video.id, num_seasons=0, num_episodes=0)
                db.session.add(series_entry)
                db.session.commit()

        # 2. Determine Seasons
        if not season_range:
            season_range = [seas.season_number for seas in s.seasons if seas.season_number > 0]
        
        print(f"DEBUG: Processing Seasons: {season_range}")

        # 3. Process Seasons
        for season_num in season_range:
            print(f"DEBUG: Fetching Season {season_num}...")
            try:
                tmdb_season = self.season_api.details(tmdb_id, season_num)
            except:
                print(f"DEBUG: Skipped Season {season_num} (API Fail)")
                continue

            db_season = Season.query.filter_by(series_id=series_entry.id, season_number=season_num).first()

            if not db_season:
                rel_date = self._safe_date(tmdb_season.air_date)
                db_season = Season(
                    series_id=series_entry.id,
                    season_number=season_num,
                    description=tmdb_season.overview or f"Season {season_num}",
                    image=f"https://image.tmdb.org/t/p/w500{tmdb_season.poster_path}" if tmdb_season.poster_path else video.image,
                    release_date=rel_date,
                    num_episodes=0
                )
                db.session.add(db_season)
                db.session.commit()
                print(f"DEBUG: Added Season {season_num}")

            # 4. Process Episodes
            episodes_to_fetch = tmdb_season.episodes
            
            # Filter Range
            if episode_range and episode_range != "All":
                try:
                    start, end = map(int, episode_range.split('-'))
                    episodes_to_fetch = [e for e in episodes_to_fetch if start <= e.episode_number <= end]
                except: pass

            count_new = 0
            for ep in episodes_to_fetch:
                if Episode.query.filter_by(season_id=db_season.id, episode_number=ep.episode_number).first():
                    continue

                rel_date = self._safe_date(ep.air_date)
                new_ep = Episode(
                    season_id=db_season.id,
                    episode_number=ep.episode_number,
                    name=ep.name,
                    description=ep.overview,
                    released_date=rel_date,
                    image=f"https://image.tmdb.org/t/p/w500{ep.still_path}" if ep.still_path else None,
                    length=self._format_runtime(getattr(ep, 'runtime', 0))
                )
                db.session.add(new_ep)
                count_new += 1
            
            db.session.commit()
            print(f"DEBUG: Added {count_new} episodes to Season {season_num}")

            # Update Counts
            db_season.num_episodes = Episode.query.filter_by(season_id=db_season.id).count()
            db.session.commit()

        # Update Series Totals
        series_entry.num_seasons = Season.query.filter_by(series_id=series_entry.id).count()
        
        total_eps = 0
        all_seasons = Season.query.filter_by(series_id=series_entry.id).all()
        for seas in all_seasons:
            total_eps += seas.num_episodes
        series_entry.num_episodes = total_eps
        db.session.commit()

        return f"Success: Updated '{s.name}' | Seasons: {season_range}"
