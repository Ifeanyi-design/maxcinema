# import requests
# import json

# API_KEY = "3d6b99b6b66197eff0bbee7faab6cf5e"
# BASE_URL = "https://api.themoviedb.org/3"

# def fetch_popular(media_type, page=1):
#     """Fetch popular movies or TV shows from TMDB."""
#     url = f"{BASE_URL}/{media_type}/popular"
#     params = {"api_key": API_KEY, "language": "en-US", "page": page}
#     resp = requests.get(url, params=params)
#     resp.raise_for_status()
#     return resp.json().get("results", [])

# def fetch_details(media_type, tmdb_id):
#     """Fetch detailed info including videos and credits."""
#     url = f"{BASE_URL}/{media_type}/{tmdb_id}"
#     params = {"api_key": API_KEY, "language": "en-US", "append_to_response": "videos,credits"}
#     resp = requests.get(url, params=params)
#     resp.raise_for_status()
#     return resp.json()

# def fetch_season_details(series_id, season_number):
#     """Fetch data for a specific season including its episodes."""
#     url = f"{BASE_URL}/tv/{series_id}/season/{season_number}"
#     params = {"api_key": API_KEY, "language": "en-US"}
#     resp = requests.get(url, params=params)
#     resp.raise_for_status()
#     return resp.json()

# def build_episode(entry):
#     """Build a dictionary for one episode in a season."""
#     return {
#         "episode_number": entry.get("episode_number"),
#         "name": entry.get("name"),
#         "length": f"{entry.get('runtime', None)} min" if entry.get("runtime", None) else None,
#         "description": entry.get("overview"),
#         "cast": [],  # TMDB season details don't always give full cast per episode
#         "released_date": entry.get("air_date"),
#         "source": None
#     }

# def build_season(series_id, season_number):
#     """Build a dictionary for one season and all its episodes."""
#     data = fetch_season_details(series_id, season_number)
#     episodes = data.get("episodes", [])
#     ep_list = [build_episode(ep) for ep in episodes]

#     # Try to guess length_per_episode: average runtime
#     runtimes = [ep.get("runtime") for ep in episodes if ep.get("runtime")]
#     avg_runtime = None
#     if runtimes:
#         avg_runtime = sum(runtimes) / len(runtimes)

#     return {
#         "season_number": data.get("season_number"),
#         "num_episodes": len(episodes),
#         "length_per_episode": f"{int(avg_runtime)} min" if avg_runtime else None,
#         "description": data.get("overview"),
#         "cast": [],  # optionally fill: you might fetch credits separately
#         "episodes": ep_list
#     }

# def build_entry(item, media_type):
#     """Build a dictionary for a movie or TV show."""
#     details = fetch_details(media_type, item["id"])

#     # Get trailer
#     trailer_url = None
#     for video in details.get("videos", {}).get("results", []):
#         if video.get("type") == "Trailer" and video.get("site") == "YouTube":
#             trailer_url = f"https://www.youtube.com/embed/{video.get('key')}"
#             break

#     # Cast
#     cast = []
#     for member in details.get("credits", {}).get("cast", [])[:6]:  # top 6 cast
#         cast.append(member.get("name"))

#     base = {
#         "name": details.get("name") or details.get("title"),
#         "year": int((details.get("first_air_date") or details.get("release_date") or "0")[:4]) or None,
#         "description": details.get("overview"),
#         "cast": cast,
#         "image": f"https://image.tmdb.org/t/p/w500{details.get('poster_path')}" if details.get("poster_path") else None,
#         "trailer": trailer_url,
#         "genres": [g["name"] for g in details.get("genres", [])],
#         "country": details.get("origin_country")[0] if media_type == "tv" and details.get("origin_country") else None,
#         "rating": details.get("vote_average"),
#         "download_link": None,
#         "type": "series" if media_type == "tv" else "movie"
#     }

#     if media_type == "movie":
#         base["length"] = f"{details.get('runtime')} min" if details.get("runtime") else None
#     else:
#         # series-specific
#         base["num_seasons"] = details.get("number_of_seasons")
#         base["num_episodes"] = details.get("number_of_episodes")

#         # build seasons
#         seasons = []
#         for sn in range(1, details.get("number_of_seasons", 0) + 1):
#             seasons.append(build_season(item["id"], sn))
#         base["seasons"] = seasons

#     return base

# def build_seed_list(num_movies=50, num_series=50):
#     seed = []
#     # Movies
#     page = 1
#     while len([s for s in seed if s["type"] == "movie"]) < num_movies:
#         results = fetch_popular("movie", page)
#         if not results:
#             break
#         for item in results:
#             if len([s for s in seed if s["type"] == "movie"]) >= num_movies:
#                 break
#             seed.append(build_entry(item, "movie"))
#         page += 1

#     # Series (TV)
#     page = 1
#     while len([s for s in seed if s["type"] == "series"]) < num_series:
#         results = fetch_popular("tv", page)
#         if not results:
#             break
#         for item in results:
#             if len([s for s in seed if s["type"] == "series"]) >= num_series:
#                 break
#             seed.append(build_entry(item, "tv"))
#         page += 1

#     return seed

# def save_to_json(data, filename="seed_data.json"):
#     with open(filename, "w", encoding="utf-8") as f:
#         json.dump(data, f, indent=2, ensure_ascii=False)

# if __name__ == "__main__":
#     data = build_seed_list(num_movies=60, num_series=40)  # total ~100 entries
#     save_to_json(data)
#     print(f"Saved {len(data)} entries to seed_data.json")

TMDB_API_KEY = "3d6b99b6b66197eff0bbee7faab6cf5e"
import requests
from slugify import slugify
from datetime import datetime
from app import app
from models import db, Trailer

# -----------------------------------------
# 1. SET YOUR TMDB API KEY HERE
# -----------------------------------------
   # <-- Replace with your actual TMDB API key
BASE_URL = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p/w500"  # Poster image base URL

# -----------------------------------------
# 2. FUNCTION TO GET POPULAR MOVIES
# -----------------------------------------
def get_popular_movies(page=1):
    url = f"{BASE_URL}/movie/popular?api_key={TMDB_API_KEY}&page={page}"
    return requests.get(url).json().get("results", [])

# -----------------------------------------
# 3. FUNCTION TO GET TRAILER FOR A MOVIE
# -----------------------------------------
def get_movie_trailer(movie_id):
    url = f"{BASE_URL}/movie/{movie_id}/videos?api_key={TMDB_API_KEY}"
    videos = requests.get(url).json().get("results", [])

    # Find a YouTube trailer
    for v in videos:
        if v["site"] == "YouTube" and v["type"] == "Trailer":
            return v["key"]  # YouTube video ID

    return None

# -----------------------------------------
# 4. POPULATE THE DATABASE
# -----------------------------------------
def populate_trailers(max_pages=3):
    with app.app_context():

        for page in range(1, max_pages + 1):
            print(f"Fetching page {page}...")
            movies = get_popular_movies(page)

            for movie in movies:
                name = movie.get("title")
                overview = movie.get("overview")
                release_date_str = movie.get("release_date")
                poster_path = movie.get("poster_path")

                # Handle release date + year
                try:
                    release_date = datetime.strptime(release_date_str, "%Y-%m-%d")
                    release_year = release_date.year
                except:
                    release_date = None
                    release_year = None

                movie_id = movie.get("id")

                # Get trailer key
                yt_key = get_movie_trailer(movie_id)
                if not yt_key:
                    print(f"No trailer for {name}, skipping...")
                    continue

                # Embed YouTube URL
                youtube_link = f"https://www.youtube.com/embed/{yt_key}"
                slug = slugify(name)

                # Compose image URL
                image_url = IMAGE_BASE + poster_path if poster_path else None

                # Check if trailer already exists
                existing = Trailer.query.filter_by(slug=slug).first()
                if existing:
                    print(f"Trailer already exists: {name}")
                    continue

                # Insert into DB
                t = Trailer(
                    name=name,
                    slug=slug,
                    trailer_link=youtube_link,
                    description=overview,
                    release_date=release_date,
                    release_year=release_year,
                    views=0,
                    image=image_url
                )

                db.session.add(t)
                print(f"Added trailer: {name}")

        db.session.commit()
        print("DONE ✓ All trailers added.")

# -----------------------------------------
# RUN
# -----------------------------------------
if __name__ == "__main__":
    populate_trailers(max_pages=5)
