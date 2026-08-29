"""add speaking_recent and writing_ai_check to section_enum

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-29

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Postgres requires new enum values to be added to the native type before
    # any row can use them. Safe to run standalone (this migration does
    # nothing else) -- Postgres 12+ allows ADD VALUE inside a transaction as
    # long as the new value isn't also used within that same transaction.
    op.execute("ALTER TYPE section_enum ADD VALUE IF NOT EXISTS 'speaking_recent'")
    op.execute("ALTER TYPE section_enum ADD VALUE IF NOT EXISTS 'writing_ai_check'")


def downgrade() -> None:
    # Postgres has no native "DROP VALUE" for enum types. Removing a value
    # that may already be referenced by rows would require rebuilding the
    # type and every column that uses it, which isn't safe to automate here.
    raise NotImplementedError(
        "Cannot automatically downgrade: Postgres does not support removing enum values. "
        "If truly needed, this requires a manual data migration."
    )
