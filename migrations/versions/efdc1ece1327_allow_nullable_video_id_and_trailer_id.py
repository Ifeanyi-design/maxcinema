"""Allow nullable video_id and trailer_id

Revision ID: efdc1ece1327
Revises: 152a7b4b36b1
Create Date: 2025-12-11 13:49:57.013828

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'efdc1ece1327'
down_revision = '152a7b4b36b1'
branch_labels = None
depends_on = None


def upgrade():
    # Episode -> Season
    with op.batch_alter_table('episode', schema=None) as batch_op:
        batch_op.create_foreign_key(
            'fk_episode_season_id',
            'season',
            ['season_id'],
            ['id'],
            ondelete='CASCADE'
        )

    # Movie -> AllVideo
    with op.batch_alter_table('movie', schema=None) as batch_op:
        batch_op.alter_column('all_video_id',
               existing_type=sa.INTEGER(),
               nullable=False)
        batch_op.create_foreign_key(
            'fk_movie_all_video_id',
            'all_video',
            ['all_video_id'],
            ['id'],
            ondelete='CASCADE'
        )

    # RecentItem -> Episode / Video
    with op.batch_alter_table('recent_item', schema=None) as batch_op:
        batch_op.create_foreign_key(
            'fk_recent_item_episode_id',
            'episode',
            ['episode_id'],
            ['id'],
            ondelete='CASCADE'
        )
        batch_op.create_foreign_key(
            'fk_recent_item_video_id',
            'all_video',
            ['video_id'],
            ['id'],
            ondelete='CASCADE'
        )

    # Season -> Series
    with op.batch_alter_table('season', schema=None) as batch_op:
        batch_op.create_foreign_key(
            'fk_season_series_id',
            'series',
            ['series_id'],
            ['id'],
            ondelete='CASCADE'
        )

    # Series -> AllVideo
    with op.batch_alter_table('series', schema=None) as batch_op:
        batch_op.create_foreign_key(
            'fk_series_all_video_id',
            'all_video',
            ['all_video_id'],
            ['id'],
            ondelete='CASCADE'
        )


def downgrade():
    # Remove foreign keys in reverse order
    with op.batch_alter_table('series', schema=None) as batch_op:
        batch_op.drop_constraint('fk_series_all_video_id', type_='foreignkey')

    with op.batch_alter_table('season', schema=None) as batch_op:
        batch_op.drop_constraint('fk_season_series_id', type_='foreignkey')

    with op.batch_alter_table('recent_item', schema=None) as batch_op:
        batch_op.drop_constraint('fk_recent_item_video_id', type_='foreignkey')
        batch_op.drop_constraint('fk_recent_item_episode_id', type_='foreignkey')

    with op.batch_alter_table('movie', schema=None) as batch_op:
        batch_op.drop_constraint('fk_movie_all_video_id', type_='foreignkey')
        batch_op.alter_column('all_video_id',
               existing_type=sa.INTEGER(),
               nullable=True)

    with op.batch_alter_table('episode', schema=None) as batch_op:
        batch_op.drop_constraint('fk_episode_season_id', type_='foreignkey')
