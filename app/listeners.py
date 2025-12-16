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
    conn_type = str(type(dbapi_connection))
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
# 🔥 MOVIES (AllVideo) INSERT - FIXED
# =======================================================
@event.listens_for(AllVideo, "after_insert")
def recent_video_insert(mapper, connection, target):
    if target.type == "movie":
        # FIX: Use target.id (AllVideo ID), not target.movie.id
        video_id = target.id 
        
        # Remove old entry (safety)
        if video_id:
            delete_old_recent(connection, video_id=video_id)
        
        # Insert new movie item
        insert_recent(
            connection,
            video_id=video_id,  # <--- Using the correct ID now
            episode_id=None,
            type="movie",
            series_id=None
        )

# =======================================================
# 🔥 MOVIES (AllVideo) UPDATE - FIXED
# =======================================================
@event.listens_for(AllVideo, "after_update")
def recent_video_update(mapper, connection, target):
    if target.type == "movie":
        # FIX: Use target.id (AllVideo ID)
        video_id = target.id
        
        if video_id:
            # Always remove old record
            delete_old_recent(connection, video_id=video_id)

            # Insert refresh record
            insert_recent(
                connection,
                video_id=video_id,
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
    # Note: For Episodes, we must rely on relationships being populated. 
    # If this fails, we might need a separate query, but usually OK for Child->Parent access
    series_id = target.season.series.id if target.season and target.season.series else None
    
    delete_old_recent(connection, series_id=series_id)

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
    series_id = target.season.series.id if target.season and target.season.series else None

    delete_old_recent(connection, series_id=series_id)

    insert_recent(
        connection,
        video_id=None,
        episode_id=target.id,
        type="series",
        series_id=series_id
    )

@event.listens_for(AllVideo, "before_insert")
def generate_slug(mapper, connection, target):
    if not target.slug:
        target.slug = slugify(target.name)
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


# @event.listens_for(AllVideo, "before_insert")
# @event.listens_for(AllVideo, "before_update")
# def update_movie_video_qualities(mapper, connection, target):
#     target.update_video_qualities()


# @event.listens_for(Episode, "before_insert")
# @event.listens_for(Episode, "before_update")
# def update_episode_video_qualities(mapper, connection, target):
#     target.update_video_qualities()
