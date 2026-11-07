"""add agent access tables

Revision ID: e7c4a91b2d60
Revises: 9f1a2b3c4d5e
Create Date: 2026-11-07
"""
from alembic import op
import sqlalchemy as sa


revision = "e7c4a91b2d60"
down_revision = "9f1a2b3c4d5e"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agent_pairing_code",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("code_hash", name="uq_agent_pairing_code_hash"),
    )
    op.create_index("ix_agent_pairing_code_expires_at", "agent_pairing_code", ["expires_at"])

    op.create_table(
        "agent_access_token",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("token_hash", name="uq_agent_access_token_hash"),
    )
    op.create_index("ix_agent_access_token_expires_at", "agent_access_token", ["expires_at"])

    op.create_table(
        "agent_audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("agent_token_id", sa.Integer(), sa.ForeignKey("agent_access_token.id"), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("target_type", sa.String(length=40), nullable=True),
        sa.Column("target_id", sa.String(length=80), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_agent_audit_log_created_at", "agent_audit_log", ["created_at"])
    op.create_index("ix_agent_audit_log_action", "agent_audit_log", ["action"])


def downgrade():
    op.drop_index("ix_agent_audit_log_action", table_name="agent_audit_log")
    op.drop_index("ix_agent_audit_log_created_at", table_name="agent_audit_log")
    op.drop_table("agent_audit_log")
    op.drop_index("ix_agent_access_token_expires_at", table_name="agent_access_token")
    op.drop_table("agent_access_token")
    op.drop_index("ix_agent_pairing_code_expires_at", table_name="agent_pairing_code")
    op.drop_table("agent_pairing_code")
