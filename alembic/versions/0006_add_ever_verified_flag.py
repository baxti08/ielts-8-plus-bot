"""add ever_verified permanent flag to users (anti-abuse for referral freshness)

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-29

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("ever_verified", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    # Best-effort backfill: anyone currently verified has, by definition,
    # been verified at least once. We have no historical audit trail for
    # users who were verified in the past but have since left everything, so
    # this is a forward-looking fix -- it closes the loophole for all
    # landings from this point on, not a retroactive rewrite of history.
    op.execute("UPDATE users SET ever_verified = true WHERE is_verified_member = true")


def downgrade() -> None:
    op.drop_column("users", "ever_verified")
