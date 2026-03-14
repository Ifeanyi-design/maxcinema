"""add analytics_event table

Revision ID: 190700991f79
Revises: 2ea138952338
Create Date: 2026-03-13 11:11:05.293256

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '190700991f79'
down_revision = '2ea138952338'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'analytics_event',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event', sa.String(length=50), nullable=False),
        sa.Column('target', sa.String(length=120), nullable=True),
        sa.Column('page', sa.String(length=240), nullable=True),
        sa.Column('ip_address', sa.String(length=64), nullable=True),
        sa.Column('user_agent', sa.String(length=180), nullable=True),
        sa.Column('date_added', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        schema='public'
    )

    with op.batch_alter_table('analytics_event', schema='public') as batch_op:
        batch_op.create_index(
            batch_op.f('ix_analytics_event_date_added'),
            ['date_added'],
            unique=False
        )
        batch_op.create_index(
            batch_op.f('ix_analytics_event_event'),
            ['event'],
            unique=False
        )


def downgrade():
    with op.batch_alter_table('analytics_event', schema='public') as batch_op:
        batch_op.drop_index(batch_op.f('ix_analytics_event_event'))
        batch_op.drop_index(batch_op.f('ix_analytics_event_date_added'))

    op.drop_table('analytics_event', schema='public')