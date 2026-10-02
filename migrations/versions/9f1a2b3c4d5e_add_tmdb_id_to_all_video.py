"""add tmdb_id to all_video

Revision ID: 9f1a2b3c4d5e
Revises: d2e3f4a5b6c7
Create Date: 2026-10-02 01:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9f1a2b3c4d5e'
down_revision = 'd2e3f4a5b6c7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('all_video', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tmdb_id', sa.Integer(), nullable=True))
        batch_op.create_index('ix_all_video_tmdb_id', ['tmdb_id'], unique=False)


def downgrade():
    with op.batch_alter_table('all_video', schema=None) as batch_op:
        batch_op.drop_index('ix_all_video_tmdb_id')
        batch_op.drop_column('tmdb_id')
