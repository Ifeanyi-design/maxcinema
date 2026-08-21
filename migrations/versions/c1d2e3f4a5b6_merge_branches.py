"""Merge email_history and social_video branches

Revision ID: c1d2e3f4a5b6
Revises: b70603f1f8d5, a1b2c3d4e5f6
Create Date: 2026-08-21

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c1d2e3f4a5b6'
down_revision = ('b70603f1f8d5', 'a1b2c3d4e5f6')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
