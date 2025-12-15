# import json
# from app import db, app
# from app.models import AllVideo, Movie, Series, Season, Episode, Genre
# with app.app_context():
#     # Helper to get or create a genre
#     def get_or_create_genre(name):
#         genre = Genre.query.filter_by(name=name).first()
#         if not genre:
#             genre = Genre(name=name)
#             db.session.add(genre)
#             db.session.commit()
#         return genre

#     # Load the JSON
#     with open("seed_data.json", "r", encoding="utf-8") as f:
#         data = json.load(f)

#     # Iterate through all entries
#     for item in data:
#         # Create AllVideo
#         all_video = AllVideo(
#             name=item.get("name"),
#             image=item.get("image"),
#             download_link=item.get("download_link"),
#             type=item.get("type"),
#             featured=item.get("featured", False),
#             trending=item.get("trending", False),
#             description=item.get("description"),
#             rating=item.get("rating", 0.0),
#             num_votes=item.get("num_votes", 0),
#             length=item.get("length"),
#             year_produced=item.get("year"),
#             star_cast=", ".join(item.get("cast", [])) if item.get("cast") else None,
#             released_date=None,
#             country=item.get("country"),
#             language=item.get("language"),
#             subtitles=item.get("subtitles", "none"),
#             source=item.get("source", 'none'),
#             trailer_url=item.get("trailer")
#         )

#         db.session.add(all_video)
#         db.session.flush()

#         # Add genres
#         for g in item.get("genres", []):
#             genre = get_or_create_genre(g)
#             all_video.genres.append(genre)

#         db.session.commit()

#         # Movies
#         if item.get("type") == "movie":
#             mv = Movie(all_video_id=all_video.id)
#             db.session.add(mv)
#             db.session.commit()

#         # Series
#         elif item.get("type") == "series":
#             ser = Series(
#                 all_video_id=all_video.id,
#                 num_seasons=item.get("num_seasons"),
#                 num_episodes=item.get("num_episodes")
#             )
#             db.session.add(ser)
#             db.session.commit()

#             # Add seasons
#             for s in item.get("seasons", []):
#                 season = Season(
#                     series_id=ser.id,
#                     season_number=s.get("season_number"),
#                     num_episodes=s.get("num_episodes"),
#                     length_per_episode=s.get("length_per_episode"),
#                     description=s.get("description"),
#                     cast=", ".join(s.get("cast", [])) if s.get("cast") else None
#                 )
#                 db.session.add(season)
#                 db.session.commit()

#                 # Add episodes
#                 for e in s.get("episodes", []):
#                     ep = Episode(
#                         season_id=season.id,
#                         episode_number=e.get("episode_number"),
#                         name=e.get("name"),
#                         length=e.get("length"),
#                         description=e.get("description"),
#                         cast=", ".join(e.get("cast", [])) if e.get("cast") else None,
#                         released_date=None,
#                         source=e.get("source")
#                     )
#                     db.session.add(ep)
#             db.session.commit()

#     print("Database populated successfully!")




import json
from app import db, app
from app.models import Series, Season, Episode

with app.app_context():

    with open("seed_data.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    for item in data:
        if item.get("type") != "series":
            continue

        # Find the series via AllVideo name
        series = (
            Series.query
            .join(Series.all_video)
            .filter_by(name=item.get("name"))
            .first()
        )

        if not series:
            print(f"Series not found: {item.get('name')}")
            continue

        for s in item.get("seasons", []):
            season = Season.query.filter_by(
                series_id=series.id,
                season_number=s.get("season_number")
            ).first()

            if not season:
                print(f"Season not found: {item.get('name')} S{s.get('season_number')}")
                continue

            for e in s.get("episodes", []):
                # Skip if episode already exists
                exists = Episode.query.filter_by(
                    season_id=season.id,
                    episode_number=e.get("episode_number")
                ).first()

                if exists:
                    continue

                ep = Episode(
                    season_id=season.id,
                    episode_number=e.get("episode_number"),
                    name=e.get("name"),
                    length=e.get("length"),
                    description=e.get("description"),
                    cast=", ".join(e.get("cast", [])) if e.get("cast") else None,
                    source=e.get("source")
                )
                db.session.add(ep)

    db.session.commit()

    print("Episodes repopulated successfully.")
