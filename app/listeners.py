# listeners.py
from sqlalchemy import event
from datetime import datetime
from slugify import slugify
from .models import Trailer, db, RecentItem, AllVideo, Episode, Series, Movie


# -------------------------------------------------------
# Helper function: Insert a new recent-item entry
# -------------------------------------------------------
def insert_recent(connection, *, video_id=None, episode_id=None, type=None, series_id=None):
    connection.execute(
        RecentItem.__table__.insert(),
        {
            "video_id": video_id,
            "episode_id": episode_id,
            "type": type,
            "series_id": series_id,
            "date_added": datetime.utcnow(),
        }
    )

from sqlalchemy.engine import Engine

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    # Get the class name of the connection
    conn_type = str(type(dbapi_connection))
    
    # Only run PRAGMA if the connection object explicitly mentions 'sqlite'
    if "sqlite" in conn_type.lower():
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()




# -------------------------------------------------------
# Helper function: Delete all previous entries for this item
# -------------------------------------------------------
def delete_old_recent(connection, *, video_id=None, series_id=None):
    if video_id:
        connection.execute(
            RecentItem.__table__.delete().where(RecentItem.video_id == video_id)
        )
    if series_id:
        connection.execute(
            RecentItem.__table__.delete().where(RecentItem.series_id == series_id)
        )


# =======================================================
# 🔥 MOVIES (AllVideo) INSERT
# =======================================================
@event.listens_for(AllVideo, "after_insert")
def recent_video_insert(mapper, connection, target):
    if target.type == "movie":
        # Remove old entry (safety)
        movie_id = target.movie.id if target.movie else None
        if movie_id:
            delete_old_recent(connection, video_id=movie_id)
        # Insert new movie item
        insert_recent(
            connection,
            video_id=movie_id,
            episode_id=None,
            type="movie",
            series_id=None
        )


# =======================================================
# 🔥 MOVIES (AllVideo) UPDATE
# =======================================================
@event.listens_for(AllVideo, "after_update")
def recent_video_update(mapper, connection, target):
    if target.type == "movie":
        # Always remove old record
        movie_id = target.movie.id if target.movie else None
        if movie_id:
        
            delete_old_recent(connection, video_id=movie_id)

            # Insert refresh record
            insert_recent(
                connection,
                video_id=movie_id,
                episode_id=None,
                type="movie",
                series_id=None
            )


# =======================================================
# 🔥 EPISODES INSERT
# =======================================================
@event.listens_for(Episode, "after_insert")
def recent_episode_insert(mapper, connection, target):

    

    # Use ORM relationships to get series_id
    series_id = target.season.series.id if target.season and target.season.series else None
    # Remove old entry
    delete_old_recent(connection, series_id=series_id)

    # Insert recent item
    insert_recent(
        connection,
        video_id=None,
        episode_id=target.id,
        type="series",
        series_id=series_id
    )


# =======================================================
# 🔥 EPISODES UPDATE
# =======================================================
@event.listens_for(Episode, "after_update")
def recent_episode_update(mapper, connection, target):
    # Retrieve parent series
    series_id = target.season.series.id if target.season and target.season.series else None

    # Remove old entry
    delete_old_recent(connection, series_id=series_id)

    

    # Insert refreshed item
    insert_recent(
        connection,
        video_id=None,
        episode_id=target.id,
        type="series",
        series_id=series_id
    )

# # Trigger after insert, update, delete for AllVideo
# @event.listens_for(AllVideo, 'after_insert')
# @event.listens_for(AllVideo, 'after_update')
# @event.listens_for(AllVideo, 'after_delete')
# def update_sitemap_allvideo(mapper, connection, target):
#     from app import create_app
#     app = create_app()
#     from app.main_routes import generate_sitemap
#     with app.app_context():
#         generate_sitemap()

# # Trigger after insert, update, delete for Trailer
# @event.listens_for(Trailer, 'after_insert')
# @event.listens_for(Trailer, 'after_update')
# @event.listens_for(Trailer, 'after_delete')
# def update_sitemap_trailer(mapper, connection, target):
#     from app import create_app
#     app = create_app()
#     from app.main_routes import generate_sitemap
#     with app.app_context():
#         generate_sitemap()


@event.listens_for(AllVideo, "before_insert")
def generate_slug(mapper, connection, target):
    if not target.slug:
        target.slug = slugify(target.name)

# @event.listens_for(AllVideo, "before_insert")
# @event.listens_for(AllVideo, "before_update")
# def update_movie_video_qualities(mapper, connection, target):
#     target.update_video_qualities()


# @event.listens_for(Episode, "before_insert")
# @event.listens_for(Episode, "before_update")
# def update_episode_video_qualities(mapper, connection, target):
#     target.update_video_qualities()
