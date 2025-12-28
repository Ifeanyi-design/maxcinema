# listeners.py
from sqlalchemy import event, text
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
    # 1. Get the Series ID directly from the DB using the Season ID
    # We use a raw SQL query because 'target.season' might not be loaded yet
    sql = text("SELECT series_id FROM season WHERE id = :sid")
    result = connection.execute(sql, {"sid": target.season_id}).fetchone()
    
    # Extract the ID safely
    series_id = result[0] if result else None
    
    # 2. Delete old recent items for this series
    if series_id:
        delete_old_recent(connection, series_id=series_id)

    # 3. Insert the new recent item
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
    # Same logic as insert
    sql = text("SELECT series_id FROM season WHERE id = :sid")
    result = connection.execute(sql, {"sid": target.season_id}).fetchone()
    
    series_id = result[0] if result else None

    if series_id:
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
