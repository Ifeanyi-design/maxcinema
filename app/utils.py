from tmdbv3api import TMDb, Movie, TV, Season as TMDBSeason, Episode as TMDBEpisode
from slugify import slugify
from datetime import datetime
from .models import db, AllVideo, Movie as DbMovie, Series, Season, Episode, Genre, video_genre
import os
# Import your app context if needed, or run this inside a route

# CONFIGURATION
tmdb = TMDb()
tmdb.api_key = os.get('YOUR_TMDB_API_KEY')
tmdb.language = 'en'

class ContentImporter:
    def __init__(self):
        self.movie_api = Movie()
        self.tv_api = TV()
        self.season_api = TMDBSeason()
        self.episode_api = TMDBEpisode()

    def get_or_create_genres(self, tmdb_genres):
        """Helper to link Genres to the Video"""
        genre_list = []
        for g in tmdb_genres:
            # Check if genre exists, if not create it
            db_genre = Genre.query.filter_by(name=g['name']).first()
            if not db_genre:
                db_genre = Genre(name=g['name'])
                db.session.add(db_genre)
                db.session.commit() # Commit needed to get ID
            genre_list.append(db_genre)
        return genre_list

    def import_movie(self, tmdb_id):
        m = self.movie_api.details(tmdb_id)
        
        # 1. Create/Update AllVideo (Master)
        existing = AllVideo.query.filter_by(name=m.title).first()
        if existing: return f"Movie '{m.title}' already exists!"

        video = AllVideo(
            name=m.title,
            slug=slugify(m.title),
            type='movie',
            description=m.overview,
            image=f"https://image.tmdb.org/t/p/w500{m.poster_path}",
            year_produced=m.release_date.split('-')[0] if m.release_date else None,
            released_date=datetime.strptime(m.release_date, '%Y-%m-%d').date() if m.release_date else None,
            rating=m.vote_average,
            active=False # Kept hidden until you add links
        )
        
        # Handle Genres
        video.genres = self.get_or_create_genres(m.genres)
        
        # Handle Trailer (Find YouTube link)
        videos = self.movie_api.videos(tmdb_id)
        for v in videos:
            if v.site == "YouTube" and v.type == "Trailer":
                video.trailer_url = f"https://www.youtube.com/watch?v={v.key}"
                break
        
        db.session.add(video)
        db.session.commit()

        # 2. Create Movie Table Entry
        db_movie = DbMovie(all_video_id=video.id)
        db.session.add(db_movie)
        db.session.commit()
        
        return f"Success: Imported Movie '{m.title}'"

    def import_series(self, tmdb_id, season_range=None, episode_range=None):
        """
        tmdb_id: The ID of the show
        season_range: List of ints [1, 2, 3] or None (for all)
        episode_range: String "1-5" or "All"
        """
        s = self.tv_api.details(tmdb_id)
        
        # 1. Create/Update AllVideo (Master)
        video = AllVideo.query.filter_by(name=s.name).first()
        
        if not video:
            video = AllVideo(
                name=s.name,
                slug=slugify(s.name),
                type='series',
                description=s.overview,
                image=f"https://image.tmdb.org/t/p/w500{s.poster_path}",
                year_produced=s.first_air_date.split('-')[0] if s.first_air_date else None,
                rating=s.vote_average,
                active=True
            )
            video.genres = self.get_or_create_genres(s.genres)
            db.session.add(video)
            db.session.commit()
            
            # Create Series Table
            series_entry = Series(all_video_id=video.id, num_seasons=0, num_episodes=0)
            db.session.add(series_entry)
            db.session.commit()
        else:
            series_entry = video.series

        # 2. Process Seasons
        # If user didn't specify seasons, get ALL valid seasons
        if not season_range:
            season_range = [season.season_number for season in s.seasons if season.season_number > 0]

        total_episodes_count = 0

        for season_num in season_range:
            # Fetch Season Details from TMDB
            try:
                tmdb_season = self.season_api.details(tmdb_id, season_num)
            except:
                continue # Skip if season doesn't exist

            # Create/Get Season in DB
            db_season = Season.query.filter_by(series_id=series_entry.id, season_number=season_num).first()
            
            if not db_season:
                db_season = Season(
                    series_id=series_entry.id,
                    season_number=season_num,
                    description=tmdb_season.overview,
                    image=f"https://image.tmdb.org/t/p/w500{tmdb_season.poster_path}" if tmdb_season.poster_path else video.image,
                    release_date=datetime.strptime(tmdb_season.air_date, '%Y-%m-%d').date() if tmdb_season.air_date else None
                )
                
                # Try to find Season Trailer
                try:
                    # TMDB v3 requires a specific call for season videos, simplified here:
                    # You might need to check if your wrapper supports season_videos or skip
                    pass 
                except: pass

                db.session.add(db_season)
                db.session.commit()

            # 3. Process Episodes
            # Determine which episodes to fetch
            episodes_to_fetch = tmdb_season.episodes
            
            # Filter if user requested specific range (e.g., "1-8")
            if episode_range and episode_range != "All":
                try:
                    start, end = map(int, episode_range.split('-'))
                    episodes_to_fetch = [e for e in episodes_to_fetch if start <= e.episode_number <= end]
                except:
                    pass # Fallback to all if parse fails

            count_eps_added = 0
            for ep in episodes_to_fetch:
                # Check if exists
                if Episode.query.filter_by(season_id=db_season.id, episode_number=ep.episode_number).first():
                    continue

                new_ep = Episode(
                    season_id=db_season.id,
                    episode_number=ep.episode_number,
                    name=ep.name,
                    description=ep.overview,
                    released_date=datetime.strptime(ep.air_date, '%Y-%m-%d').date() if ep.air_date else None,
                    image=f"https://image.tmdb.org/t/p/w500{ep.still_path}" if ep.still_path else None
                )
                db.session.add(new_ep)
                count_eps_added += 1
            
            db.session.commit()
            
            # Update Season Count
            db_season.num_episodes = Episode.query.filter_by(season_id=db_season.id).count()
            db.session.commit()

        # Final Update: Series Counters
        series_entry.num_seasons = Season.query.filter_by(series_id=series_entry.id).count()
        series_entry.num_episodes = sum(s.num_episodes for s in series_entry.seasons)
        db.session.commit()

        return f"Success: Updated '{s.name}' with Seasons {season_range}"
