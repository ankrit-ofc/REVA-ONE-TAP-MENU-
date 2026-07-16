"""add COUNTER_DISPLAY to the role enum

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-17 00:00:00.000000

Adds a new staff role for the passive counter wall-display (a read-only food
status board). Extends the existing native `role` enum. Postgres cannot remove
an enum value, so downgrade is a no-op.
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # IF NOT EXISTS makes this idempotent; ADD VALUE is allowed in a tx on PG12+.
    op.execute(sa.text("ALTER TYPE role ADD VALUE IF NOT EXISTS 'COUNTER_DISPLAY'"))


def downgrade() -> None:
    # Postgres has no DROP VALUE for enums; intentionally a no-op.
    pass
