"""Idempotent startup schema repair for the sports hub tables.

Adds columns that exist on the current SQLAlchemy models but are missing from
the live database (e.g. Heroku Postgres that was created before a model
change, or whose alembic state drifted from local). Only existing tables are
touched; brand-new tables are left to normal migrations. Safe on both
SQLite and Postgres, and safe to run on every boot.
"""

import logging

from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import (
    SportsCompetition,
    SportsMatch,
    SportsMatchEvent,
    SportsProviderCache,
    SportsProviderMapping,
    SportsSeason,
    SportsSport,
    SportsStanding,
    SportsStreamSource,
    SportsTeam,
)

logger = logging.getLogger(__name__)

SPORTS_MODELS = [
    SportsSport,
    SportsCompetition,
    SportsTeam,
    SportsSeason,
    SportsMatch,
    SportsMatchEvent,
    SportsStanding,
    SportsStreamSource,
    SportsProviderCache,
    SportsProviderMapping,
]


def ensure_sports_schema() -> list[str]:
    """Add missing model columns to existing sports tables.

    Returns a list of ``table.column`` names that were added.
    """
    added: list[str] = []
    inspector = inspect(db.engine)
    existing_tables = set(inspector.get_table_names())

    for model in SPORTS_MODELS:
        table = model.__table__.name
        if table not in existing_tables:
            continue
        db_columns = {col["name"] for col in inspector.get_columns(table)}
        for column in model.__table__.columns:
            if column.name in db_columns:
                continue
            # Adding a NOT NULL column without a default would fail on a
            # table with existing rows (on both SQLite and Postgres).
            if not column.nullable and column.default is None and column.server_default is None:
                continue
            column_ddl = column.type.compile(dialect=db.engine.dialect)
            ddl = f'ALTER TABLE "{table}" ADD COLUMN "{column.name}" {column_ddl}'
            try:
                with db.engine.begin() as conn:
                    conn.execute(text(ddl))
                added.append(f"{table}.{column.name}")
                logger.warning("Schema repair: added missing column %s.%s", table, column.name)
            except SQLAlchemyError as exc:
                logger.warning("Schema repair: could not add %s.%s: %s", table, column.name, exc)

    return added