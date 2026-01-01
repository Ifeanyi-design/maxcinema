from tmdbv3api import TMDb, Movie, TV, Season as TMDBSeason, Episode as TMDBEpisode
from slugify import slugify
from datetime import datetime
from .models import db, AllVideo, Movie as DbMovie, Series, Season, Episode, Genre

# ⚙️ CONFIGURATION
tmdb = TMDb()
tmdb.api_key = '3d6b99b6b66197eff0bbee7faab6cf5e'  # Your Key
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
        # Safely tries to find cast in different API locations
        credits = getattr(obj, 'credits', None)
        if not credits: return ""
        # Credits is usually a dict, accessed via ['cast']
        cast_list = credits.get('cast', []) if isinstance(credits, dict) else getattr(credits, 'cast', [])
        names = [c['name'] for c in cast_list[:5]]
        return ", ".join(names)

    def link_genres(self, tmdb_genres):
        genre_objs = []
        for g in tmdb_genres:
            # TMDB returns genres as dicts {'id': 1, 'name': 'Action'}
            g_name = g['name'] if isinstance(g, dict) else g.name
            
            db_genre = Genre.query.filter_by(name=g_name).first()
            if not db_genre:
                db_genre = Genre(name=g_name)
                db.session.add(db_genre)
                db.session.commit()
            genre_objs.append(db_genre)
        return genre_objs

    # --- MAIN FUNCTIONS ---
    def import_movie(self, tmdb_id):
        # 1. Fetch Data
        try:
            m = self.movie_api.details(tmdb_id, append_to_response="credits")
        except:
            return "Error: TMDB ID invalid."

        # 2. Check Exists
        if AllVideo.query.filter_by(name=m.title).first():
            return f"Movie '{m.title}' already exists."

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
            # Extra Fields
            star_cast=self._get_cast(m),
            length=self._get_runtime(getattr(m, 'runtime', 0)),
            country=m.production_countries[0]['name'] if m.production_countries else "",
            language=m.original_language
        )
        
        # Add Genres
        video.genres = self.link_genres(m.genres)
        
        db.session.add(video)
        db.session.commit() # Save to generate ID

        # 4. Create Movie Entry
        db_movie = DbMovie(all_video_id=video.id)
        db.session.add(db_movie)
        db.session.commit()

        return f"Imported Movie: {m.title}"

    def import_series(self, tmdb_id, season_input=None, episode_input=None):
        # 1. Fetch Series
        try:
            s = self.tv_api.details(tmdb_id, append_to_response="credits")
        except:
            return "Error: Series ID invalid."

        # 2. Handle Master Video (Create or Get)
        video = AllVideo.query.filter_by(name=s.name).first()
        series_entry = None

        if not video:
            # Create NEW Series
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
                length=self._get_runtime(s.episode_run_time[0] if s.episode_run_time else 45),
                country=s.production_countries[0]['name'] if s.production_countries else "",
                language=s.original_language
            )
            video.genres = self.link_genres(s.genres)
            db.session.add(video)
            db.session.commit()

            series_entry = Series(all_video_id=video.id, num_seasons=0, num_episodes=0)
            db.session.add(series_entry)
            db.session.commit()
        else:
            # Get Existing
            series_entry = video.series
            if not series_entry:
                series_entry = Series(all_video_id=video.id, num_seasons=0, num_episodes=0)
                db.session.add(series_entry)
                db.session.commit()

        # 3. Determine Seasons to Add
        # If user entered "5", we make a list [5]. If empty, we get all seasons > 0.
        target_seasons = []
        if season_input:
            # User input: "1, 2" or "5"
            target_seasons = [int(x) for x in str(season_input).split(',') if x.strip().isdigit()]
        else:
            # Auto-detect all seasons
            target_seasons = [seas.season_number for seas in s.seasons if seas.season_number > 0]

        # 4. Loop Seasons
        for seas_num in target_seasons:
            # Fetch Season Details
            try:
                tmdb_season = self.season_api.details(tmdb_id, seas_num)
            except:
                continue # Skip if not found

            # Check DB
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
                db.session.commit() # Save immediately

            # 5. Handle Episodes (THE FIX YOU REQUESTED)
            all_eps = tmdb_season.episodes
            
            # Parse Range: "1-8"
            start_ep, end_ep = 0, 9999
            if episode_input and episode_input.lower() != "all":
                try:
                    parts = episode_input.split('-')
                    start_ep = int(parts[0])
                    end_ep = int(parts[1])
                except:
                    pass # If fail, default to all

            for ep in all_eps:
                # Check Range
                if not (start_ep <= ep.episode_number <= end_ep):
                    continue

                # Check Exists
                if Episode.query.filter_by(season_id=db_season.id, episode_number=ep.episode_number).first():
                    continue

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
            
            # Update Count for Season
            db_season.num_episodes = Episode.query.filter_by(season_id=db_season.id).count()
            db.session.commit()

        # 6. Final Series Update
        series_entry.num_seasons = Season.query.filter_by(series_id=series_entry.id).count()
        # Sum all episodes
        total = 0
        for s_obj in series_entry.seasons:
            total += s_obj.num_episodes
        series_entry.num_episodes = total
        db.session.commit()

        return f"Updated Series: {s.name} (Seasons: {target_seasons})"
