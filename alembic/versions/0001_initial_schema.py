"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-08-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

section_enum = postgresql.ENUM(
    "reading", "multilevel", "listening", "speaking", "writing", name="section_enum"
)
# Reused for column definitions below. create_type=False is required here:
# without it, SQLAlchemy tries to CREATE TYPE again for every table that uses
# this enum, even though we've already created it explicitly in upgrade()
# below -- which fails with "type already exists" on the 2nd+ table.
section_enum_col = postgresql.ENUM(
    "reading", "multilevel", "listening", "speaking", "writing", name="section_enum", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    section_enum.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("telegram_id", sa.BigInteger(), primary_key=True),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("full_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("referred_by", sa.BigInteger(), sa.ForeignKey("users.telegram_id"), nullable=True),
        sa.Column("is_verified_member", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_membership_check", sa.DateTime(timezone=True), nullable=True),
        sa.Column("landed_via_referrer_id", sa.BigInteger(), nullable=True),
    )

    op.create_table(
        "referrals",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("referrer_id", sa.BigInteger(), sa.ForeignKey("users.telegram_id"), nullable=False),
        sa.Column("referred_id", sa.BigInteger(), sa.ForeignKey("users.telegram_id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("was_fresh_at_landing", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_valid", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("section_assigned", section_enum_col, nullable=True),
        sa.Column("batch_number", sa.Integer(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("referred_id", name="uq_referral_referred_once"),
    )
    op.create_index("ix_referrals_referrer_id", "referrals", ["referrer_id"])
    op.create_index("ix_referrals_is_valid", "referrals", ["is_valid"])

    op.create_table(
        "section_unlocks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.telegram_id"), nullable=False),
        sa.Column("section", section_enum_col, nullable=False),
        sa.Column("unlocked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("relocked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("user_id", "section", name="uq_user_section"),
    )
    op.create_index("ix_section_unlocks_user_id", "section_unlocks", ["user_id"])

    op.create_table(
        "content",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("section", section_enum_col, nullable=False),
        sa.Column("day_number", sa.Integer(), nullable=False),
        sa.Column("source_channel_id", sa.BigInteger(), nullable=False),
        sa.Column("message_ids", postgresql.JSONB(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("section", "day_number", name="uq_section_day"),
    )

    op.create_table(
        "admin_actions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("admin_username", sa.String(length=64), nullable=False),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("target_user_id", sa.BigInteger(), nullable=True),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "broadcast_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("segment", sa.String(length=64), nullable=False),
        sa.Column("message_text", sa.Text(), nullable=False),
        sa.Column("total_targets", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sent_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("broadcast_logs")
    op.drop_table("admin_actions")
    op.drop_table("content")
    op.drop_table("section_unlocks")
    op.drop_index("ix_referrals_is_valid", table_name="referrals")
    op.drop_index("ix_referrals_referrer_id", table_name="referrals")
    op.drop_table("referrals")
    op.drop_table("users")
    section_enum.drop(op.get_bind(), checkfirst=True)
