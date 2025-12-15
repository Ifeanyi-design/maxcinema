"""Add bytescale fields

Revision ID: c571406b8e66
Revises: b5c38cb9dd75
Create Date: 2025-12-08 19:21:52.074112

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c571406b8e66'
down_revision = 'b5c38cb9dd75'
branch_labels = None
depends_on = None


def upgrade():
    # all_video table
    with op.batch_alter_table('all_video', schema=None) as batch_op:
        batch_op.add_column(sa.Column('storage_server_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('created_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('updated_at', sa.DateTime(), nullable=True))
        batch_op.create_foreign_key(
            'fk_all_video_storage_server',   # <--- explicit name
            'storage_servers',
            ['storage_server_id'],
            ['id']
        )

    # episode table
    with op.batch_alter_table('episode', schema=None) as batch_op:
        batch_op.add_column(sa.Column('storage_server_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('created_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('updated_at', sa.DateTime(), nullable=True))
        batch_op.create_foreign_key(
            'fk_episode_storage_server',    # <--- explicit name
            'storage_servers',
            ['storage_server_id'],
            ['id']
        )


def downgrade():
    # episode table
    with op.batch_alter_table('episode', schema=None) as batch_op:
        batch_op.drop_constraint('fk_episode_storage_server', type_='foreignkey')
        batch_op.drop_column('updated_at')
        batch_op.drop_column('created_at')
        batch_op.drop_column('storage_server_id')

    # all_video table
    with op.batch_alter_table('all_video', schema=None) as batch_op:
        batch_op.drop_constraint('fk_all_video_storage_server', type_='foreignkey')
        batch_op.drop_column('updated_at')
        batch_op.drop_column('created_at')
        batch_op.drop_column('storage_server_id')

    # ### end Alembic commands ###
