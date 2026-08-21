"""Add social_video table

Revision ID: a1b2c3d4e5f6
Revises: 8dc4ee555fff
Create Date: 2026-08-21

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '8dc4ee555fff'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('social_video',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('platform', sa.String(length=20), nullable=False),
        sa.Column('video_url', sa.String(length=500), nullable=False),
        sa.Column('platform_id', sa.String(length=100), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('thumbnail_url', sa.String(length=500), nullable=True),
        sa.Column('tags', sa.String(length=500), nullable=True),
        sa.Column('all_video_id', sa.Integer(), nullable=True),
        sa.Column('featured', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('published_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['all_video_id'], ['all_video.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('platform', 'platform_id', name='uq_social_video_platform_id')
    )
    op.create_index('ix_social_video_all_video_id', 'social_video', ['all_video_id'], unique=False)


def downgrade():
    op.drop_index('ix_social_video_all_video_id', table_name='social_video')
    op.drop_table('social_video')
