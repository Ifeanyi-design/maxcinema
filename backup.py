# import json
# from datetime import datetime
# from slugify import slugify
# from app import create_app, db
# from app.models import AllVideo, Movie, Series, Season, Episode, Genre

# # Initialize the Flask App Context
# app = create_app()

# def parse_date(date_str):
#     """Convert YYYY-MM-DD string to Python Date object."""
#     if not date_str:
#         return None
#     try:
#         return datetime.strptime(date_str, "%Y-%m-%d").date()
#     except ValueError:
#         return None

# def get_or_create_genre(name, genre_cache):
#     """
#     Fetch genre from cache or DB. If not found, create new one.
#     genre_cache is a dict {name: GenreObject} to avoid repeated DB queries.
#     """
#     if name in genre_cache:
#         return genre_cache[name]
    
#     # Check DB
#     genre = Genre.query.filter_by(name=name).first()
#     if not genre:
#         genre = Genre(name=name)
#         db.session.add(genre)
#         # We don't commit yet, but we add to session so it has an ID upon flush if needed
    
#     genre_cache[name] = genre
#     return genre

# def seed():
#     with app.app_context():
#         print("Loading seed data...")
#         with open('seed_data.json', 'r', encoding='utf-8') as f:
#             data = json.load(f)

#         print(f"Found {len(data)} items. Beginning insertion...")
        
#         # Cache genres to prevent duplicates
#         existing_genres = Genre.query.all()
#         genre_cache = {g.name: g for g in existing_genres}

#         count = 0
#         for item in data:
#             # 1. Create the AllVideo (Master Record)
#             video = AllVideo()
#             video.name = item.get('name')
#             video.slug = slugify(item.get('name'))
            
#             # Handle potential duplicate slugs
#             if AllVideo.query.filter_by(slug=video.slug).first():
#                 video.slug = f"{video.slug}-{datetime.now().microsecond}"

#             video.description = item.get('description')
#             video.image = item.get('image')
#             video.trailer_url = item.get('trailer')
#             video.rating = float(item.get('rating', 0))
#             video.download_link = item.get('download_link')
#             video.type = item.get('type')
#             video.length = item.get('length')
#             video.year_produced = item.get('year')
#             video.country = item.get('country')
            
#             # Convert list of cast members to a single string
#             if isinstance(item.get('cast'), list):
#                 video.star_cast = ", ".join(item.get('cast'))
#             else:
#                 video.star_cast = item.get('cast')

#             # 2. Handle Genres
#             item_genres = item.get('genres', [])
#             for g_name in item_genres:
#                 genre_obj = get_or_create_genre(g_name, genre_cache)
#                 video.genres.append(genre_obj)

#             db.session.add(video)
#             db.session.flush() # Flush to generate video.id for relationships

#             # 3. Handle specific types (Movie vs Series)
#             if video.type == 'movie':
#                 movie = Movie(all_video_id=video.id)
#                 db.session.add(movie)

#             elif video.type == 'series':
#                 series = Series(all_video_id=video.id)
#                 series.num_seasons = item.get('num_seasons')
#                 series.num_episodes = item.get('num_episodes')
#                 db.session.add(series)
#                 db.session.flush() # Flush to get series.id

#                 # Process Seasons
#                 seasons_data = item.get('seasons', [])
#                 for s_data in seasons_data:
#                     season = Season(series_id=series.id)
#                     season.season_number = s_data.get('season_number')
#                     season.num_episodes = s_data.get('num_episodes')
#                     season.length_per_episode = s_data.get('length_per_episode')
#                     season.description = s_data.get('description')
                    
#                     if isinstance(s_data.get('cast'), list):
#                         season.cast = ", ".join(s_data.get('cast'))
                    
#                     db.session.add(season)
#                     db.session.flush() # Flush to get season.id

#                     # Process Episodes
#                     episodes_data = s_data.get('episodes', [])
#                     for e_data in episodes_data:
#                         episode = Episode(season_id=season.id)
#                         episode.episode_number = e_data.get('episode_number')
#                         episode.name = e_data.get('name')
#                         episode.length = e_data.get('length')
#                         episode.description = e_data.get('description')
#                         episode.source = e_data.get('source')
#                         episode.released_date = parse_date(e_data.get('released_date'))
                        
#                         if isinstance(e_data.get('cast'), list):
#                             episode.cast = ", ".join(e_data.get('cast'))

#                         db.session.add(episode)

#             count += 1
#             if count % 10 == 0:
#                 print(f"Processed {count} videos...")
        
#         db.session.commit()
#         print("Success! Database populated.")

# if __name__ == "__main__":
#     seed()


import requests
from slugify import slugify
from datetime import datetime
from sqlalchemy import event

# Import your app and models
from app import create_app, db
from app.models import Trailer

# Import listeners to disable them temporarily (just like we did for seed_db)
from app import listeners 

# -----------------------------------------
# CONFIGURATION
# -----------------------------------------
TMDB_API_KEY = "3d6b99b6b66197eff0bbee7faab6cf5e"
BASE_URL = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p/w500"

app = create_app()

def get_popular_movies(page=1):
    """Fetch popular movies from TMDB."""
    url = f"{BASE_URL}/movie/popular?api_key={TMDB_API_KEY}&page={page}&language=en-US"
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json().get("results", [])
    except Exception as e:
        print(f"   [Error] Fetching page {page}: {e}")
        return []

def get_movie_trailer(movie_id):
    """Fetch the first YouTube trailer key for a specific movie."""
    url = f"{BASE_URL}/movie/{movie_id}/videos?api_key={TMDB_API_KEY}&language=en-US"
    try:
        response = requests.get(url)
        videos = response.json().get("results", [])
        
        # Priority: 'Trailer' type on 'YouTube'
        for v in videos:
            if v.get("site") == "YouTube" and v.get("type") == "Trailer":
                return v.get("key")
        
        # Fallback: 'Teaser' if no trailer found
        for v in videos:
            if v.get("site") == "YouTube" and v.get("type") == "Teaser":
                return v.get("key")
                
    except Exception:
        pass
    return None

def remove_trailer_listeners():
    """Disable listeners to prevent locks during bulk insert."""
    print("--> Disabling Trailer listeners...")
    if event.contains(Trailer, 'after_insert', listeners.update_sitemap_trailer):
        event.remove(Trailer, 'after_insert', listeners.update_sitemap_trailer)
    if event.contains(Trailer, 'after_update', listeners.update_sitemap_trailer):
        event.remove(Trailer, 'after_update', listeners.update_sitemap_trailer)

def populate_trailers(max_pages=3):
    # 1. Disable listeners to avoid "Database Locked" errors
    remove_trailer_listeners()

    with app.app_context():
        print(f"--> Starting Trailer Import (Pages 1 to {max_pages})...")
        
        added_count = 0
        skipped_count = 0

        for page in range(1, max_pages + 1):
            print(f"--> Fetching Page {page}...")
            movies = get_popular_movies(page)

            for movie in movies:
                title = movie.get("title")
                
                # Check for duplicate by slug
                slug = slugify(title)
                existing = Trailer.query.filter_by(slug=slug).first()
                if existing:
                    print(f"   [Skip] '{title}' already exists.")
                    skipped_count += 1
                    continue

                # Get trailer link
                yt_key = get_movie_trailer(movie.get("id"))
                if not yt_key:
                    # Skip movies that don't have a YouTube trailer
                    continue

                # Parse dates
                release_date_str = movie.get("release_date")
                release_date = None
                release_year = None
                if release_date_str:
                    try:
                        release_date = datetime.strptime(release_date_str, "%Y-%m-%d")
                        release_year = release_date.year
                    except ValueError:
                        pass

                # Create Trailer Object
                new_trailer = Trailer(
                    name=title,
                    slug=slug,
                    trailer_link=f"https://www.youtube.com/embed/{yt_key}",
                    description=movie.get("overview"),
                    image=IMAGE_BASE + movie.get("poster_path") if movie.get("poster_path") else None,
                    release_date=release_date,
                    release_year=release_year,
                    views=0
                )

                db.session.add(new_trailer)
                added_count += 1
                print(f"   [+] Added: {title}")

            # Commit after every page to save progress
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                print(f"   [Error] Commit failed for page {page}: {e}")

        print("\n---------------------------------------------------")
        print(f"DONE! Added {added_count} new trailers. Skipped {skipped_count} duplicates.")
        print("---------------------------------------------------")

        # Optional: Re-enable sitemap generation manually at the end
        print("--> Updating Sitemap...")
        try:
            from app.main_routes import generate_sitemap
            generate_sitemap()
            print("--> Sitemap updated.")
        except Exception as e:
            print(f"--> Could not update sitemap: {e}")

if __name__ == "__main__":
    # You can change max_pages to fetch more (e.g., 5 or 10)
    populate_trailers(max_pages=5)