"""add short description to products

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-15 00:00:00.000000

Optional one-line product description shown on the menu card and admin form.
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("ALTER TABLE products ADD COLUMN description VARCHAR(255)"))


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE products DROP COLUMN IF EXISTS description"))
