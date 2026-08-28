"""add content_deliveries table

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

section_enum_col = postgresql.ENUM(
    "reading", "multilevel", "listening", "speaking", "writing", name="section_enum", create_type=False
)


def upgrade() -> None:
    op.create_table(
        "content_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.telegram_id"), nullable=False),
        sa.Column("section", section_enum_col, nullable=False),
        sa.Column("day_number", sa.Integer(), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_content_deliveries_user_id", "content_deliveries", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_content_deliveries_user_id", table_name="content_deliveries")
    op.drop_table("content_deliveries")
