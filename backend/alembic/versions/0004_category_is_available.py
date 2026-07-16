"""add is_available to categories

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-15 00:00:00.000000

Adds a per-category availability flag, mirroring products.is_available.
is_active stays the soft-delete flag; is_available is the show/hide toggle that
gates the customer menu (and cascades to a category's products when turned off).
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE categories ADD COLUMN is_available BOOLEAN NOT NULL DEFAULT true"
    ))


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE categories DROP COLUMN IF EXISTS is_available"))
