"""Change social_video from single FK to many-to-many with all_video

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-08-21

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd2e3f4a5b6c7'
down_revision = 'c1d2e3f4a5b6'
branch_labels = None
depends_on = None


def upgrade():
    # Create junction table
    op.create_table('social_video_all_video',
        sa.Column('social_video_id', sa.Integer(), nullable=False),
        sa.Column('all_video_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['social_video_id'], ['social_video.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['all_video_id'], ['all_video.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('social_video_id', 'all_video_id')
    )

    # Migrate existing data from all_video_id to junction table
    op.execute("""
        INSERT INTO social_video_all_video (social_video_id, all_video_id)
        SELECT id, all_video_id FROM social_video WHERE all_video_id IS NOT NULL
    """)

    # Drop the old single FK column
    op.drop_constraint('social_video_all_video_id_fkey', 'social_video', type_='foreignkey')
    op.drop_index('ix_social_video_all_video_id', table_name='social_video')
    op.drop_column('social_video', 'all_video_id')


def downgrade():
    op.add_column('social_video', sa.Column('all_video_id', sa.Integer(), nullable=True))
    op.create_index('ix_social_video_all_video_id', 'social_video', ['all_video_id'], unique=False)
    op.create_foreign_key('social_video_all_video_id_fkey', 'social_video', 'all_video', ['all_video_id'], ['id'])

    # Migrate data back
    op.execute("""
        UPDATE social_video SET all_video_id = (
            SELECT all_video_id FROM social_video_all_video
            WHERE social_video_all_video.social_video_id = social_video.id
            LIMIT 1
        )
    """)

    op.drop_table('social_video_all_video')
