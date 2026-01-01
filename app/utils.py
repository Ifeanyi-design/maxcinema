from tmdbv3api import TMDb, Movie, TV, Season as TMDBSeason, Episode as TMDBEpisode
from slugify import slugify
from datetime import datetime
from .models import db, AllVideo, Movie as DbMovie, Series, Season, Episode, Genre
from sqlalchemy.exc import IntegrityError

import os

# CONFIGURATION
tmdb = TMDb()
tmdb.api_key = os.environ.get('YOUR_TMDB_API_KEY')  # REPLACE THIS
tmdb.language = 'en'

class ContentImporter:
    def __init__(self):
        self.movie_api = Movie()
        self.tv_api = TV()
        self.season_api = TMDBSeason()
        self.episode_api = TMDBEpisode()

    def _get_cast_string(self, credits):
        """Helper to get top 5 actors as a comma-separated string"""
        if not credits or 'cast' not in credits:
            return ""
        # Get top 5 actors
        actors = [c['name'] for c in credits['cast'][:5]]
        return ", ".join(actors)

    def _format_runtime(self, runtime_mins):
        """Converts integer minutes (e.g. 130) to String '2h 10m'"""
        if not runtime_mins: return ""
        hours = runtime_mins // 60
        minutes = runtime_mins % 60
        return f"{hours}h {minutes}m"

    def _get_country_lang(self, obj):
        """Helper to extract Country and Language safely"""
        country = ""
        if hasattr(obj, 'production_countries') and obj.production_countries:
            country = obj.production_countries[0]['name']
        
        language = ""
        if hasattr(obj, 'spoken_languages') and obj.spoken_languages:
            language = obj.spoken_languages[0]['name']
        elif hasattr(obj, 'original_language'):
            language = obj.original_language
            
        return country, language

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
        # Fetch Details AND Credits (append_to_response is cleaner)
        try:
            m = self.movie_api.details(tmdb_id, append_to_response="credits")
        except:
            return f"Error: TMDB ID {tmdb_id} not found."

        # Check existing
        existing = AllVideo.query.filter_by(name=m.title).first()
        if existing: return f"Movie '{m.title}' already exists!"

        # Extract extra fields
        cast_str = self._get_cast_string(m.credits)
        runtime_str = self._format_runtime(getattr(m, 'runtime', 0))
        country_str, lang_str = self._get_country_lang(m)

        # 1. Create AllVideo
        video = AllVideo(
            name=m.title,
            slug=slugify(m.title),
            type='movie',
            description=m.overview,
            image=f"https://image.tmdb.org/t/p/w500{m.poster_path}" if m.poster_path else None,
            year_produced=m.release_date.split('-')[0] if m.release_date else None,
            released_date=datetime.strptime(m.release_date, '%Y-%m-%d').date() if m.release_date else None,
            rating=m.vote_average,
            active=False,
            # NEW FIELDS FIXED:
            star_cast=cast_str,
            length=runtime_str,
            country=country_str,
            language=lang_str
        )
        
        video.genres = self.get_or_create_genres(m.genres)
        
        # Add to DB to get ID
        db.session.add(video)
        db.session.commit() # Important: Commit to generate video.id

        # 2. Create Movie Table
        db_movie = DbMovie(all_video_id=video.id)
        db.session.add(db_movie)
        db.session.commit()
        
        return f"Success: Imported Movie '{m.title}'"

    def import_series(self, tmdb_id, season_range=None, episode_range=None):
        # Fetch Series Details with Credits
        try:
            s = self.tv_api.details(tmdb_id, append_to_response="credits")
        except:
            return f"Error: Series ID {tmdb_id} not found."

        # 1. Handle AllVideo & Series Master Table
        video = AllVideo.query.filter_by(name=s.name).first()
        series_entry = None

        if not video:
            # Create NEW Series
            cast_str = self._get_cast_string(s.credits)
            country_str, lang_str = self._get_country_lang(s)

            video = AllVideo(
                name=s.name,
                slug=slugify(s.name),
                type='series',
                description=s.overview,
                image=f"https://image.tmdb.org/t/p/w500{s.poster_path}" if s.poster_path else None,
                year_produced=s.first_air_date.split('-')[0] if s.first_air_date else None,
                rating=s.vote_average,
                active=True,
                # NEW FIELDS FIXED:
                star_cast=cast_str,
                country=country_str,
                language=lang_str,
                length=f"{s.episode_run_time[0]}m" if s.episode_run_time else "45m"
            )
            video.genres = self.get_or_create_genres(s.genres)
            db.session.add(video)
            db.session.commit() # Must commit to get ID

            # Create Series Entry
            series_entry = Series(all_video_id=video.id, num_seasons=0, num_episodes=0)
            db.session.add(series_entry)
            db.session.commit() # Must commit to get series.id
        else:
            # Series EXISTS - get the relationship
            series_entry = video.series
            if not series_entry:
                # Fallback if AllVideo exists but Series table is empty (Manual DB error fix)
                series_entry = Series(all_video_id=video.id, num_seasons=0, num_episodes=0)
                db.session.add(series_entry)
                db.session.commit()

        # 2. Determine Seasons to fetch
        if not season_range:
            # Get all valid seasons (ignoring Season 0/Specials if you want)
            season_range = [seas.season_number for seas in s.seasons if seas.season_number > 0]

        # 3. Process Seasons
        for season_num in season_range:
            # Fetch specific season details
            try:
                tmdb_season = self.season_api.details(tmdb_id, season_num)
            except:
                print(f"Skipping Season {season_num} (Not found in TMDB)")
                continue

            # Check if Season exists in DB
            db_season = Season.query.filter_by(series_id=series_entry.id, season_number=season_num).first()

            if not db_season:
                db_season = Season(
                    series_id=series_entry.id,
                    season_number=season_num,
                    description=tmdb_season.overview or f"Season {season_num} of {s.name}",
                    image=f"https://image.tmdb.org/t/p/w500{tmdb_season.poster_path}" if tmdb_season.poster_path else video.image,
                    release_date=datetime.strptime(tmdb_season.air_date, '%Y-%m-%d').date() if tmdb_season.air_date else None,
                    num_episodes=0
                )
                db.session.add(db_season)
                db.session.commit() # Commit to get db_season.id

            # 4. Process Episodes
            episodes_to_fetch = tmdb_season.episodes
            
            # Filter range (e.g. "1-8")
            if episode_range and episode_range != "All":
                try:
                    start, end = map(int, episode_range.split('-'))
                    episodes_to_fetch = [e for e in episodes_to_fetch if start <= e.episode_number <= end]
                except:
                    pass 

            for ep in episodes_to_fetch:
                # Check if episode exists
                existing_ep = Episode.query.filter_by(season_id=db_season.id, episode_number=ep.episode_number).first()
                if existing_ep:
                    continue

                # Get runtime for this specific episode if possible, else None
                # TMDB Episode object usually has 'runtime'
                ep_runtime = self._format_runtime(getattr(ep, 'runtime', 0))

                new_ep = Episode(
                    season_id=db_season.id,
                    episode_number=ep.episode_number,
                    name=ep.name,
                    description=ep.overview,
                    released_date=datetime.strptime(ep.air_date, '%Y-%m-%d').date() if ep.air_date else None,
                    image=f"https://image.tmdb.org/t/p/w500{ep.still_path}" if ep.still_path else None,
                    length=ep_runtime
                )
                db.session.add(new_ep)
            
            # Commit all episodes for this season
            db.session.commit()
            
            # Update Season Count
            db_season.num_episodes = Episode.query.filter_by(season_id=db_season.id).count()
            db.session.commit()

        # Final Update: Series Counters
        series_entry.num_seasons = Season.query.filter_by(series_id=series_entry.id).count()
        # Count all episodes across all seasons
        total_eps = 0
        all_seasons = Season.query.filter_by(series_id=series_entry.id).all()
        for seas in all_seasons:
            total_eps += seas.num_episodes
        series_entry.num_episodes = total_eps
        
        db.session.commit()

        return f"Success: Updated '{s.name}' | Seasons: {season_range}"
