"""add completed column in season table

Revision ID: 96197427b479
Revises: b9f83de776b6
Create Date: 2025-12-01 23:54:01.019652
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '96197427b479'
down_revision = 'b9f83de776b6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('comment', schema=None) as batch_op:
        batch_op.add_column(sa.Column('trailer_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_comment_trailer_id',   # <-- NAME ADDED
            'trailer',
            ['trailer_id'],
            ['id']
        )


def downgrade():
    with op.batch_alter_table('comment', schema=None) as batch_op:
        batch_op.drop_constraint(
            'fk_comment_trailer_id',   # <-- SAME NAME HERE
            type_='foreignkey'
        )
        batch_op.drop_column('trailer_id')
