"""add source_chat_id/source_message_id to broadcast_logs (media broadcast support)

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-29

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("broadcast_logs", sa.Column("source_chat_id", sa.BigInteger(), nullable=True))
    op.add_column("broadcast_logs", sa.Column("source_message_id", sa.BigInteger(), nullable=True))
    op.alter_column("broadcast_logs", "message_text", existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    op.alter_column("broadcast_logs", "message_text", existing_type=sa.Text(), nullable=False)
    op.drop_column("broadcast_logs", "source_message_id")
    op.drop_column("broadcast_logs", "source_chat_id")
