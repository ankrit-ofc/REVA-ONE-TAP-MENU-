"""add printer settings to restaurant_settings

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-26 00:00:00.000000

Thermal printing config. print_kot_enabled / print_bill_enabled gate the
counter computer's auto-print of kitchen tickets and bills; bill_copies is how
many bill copies to print (e.g. 2 = Merchant + Customer). All default to a safe
"off"/sane state so existing tenants are unaffected.
"""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE restaurant_settings "
        "ADD COLUMN print_kot_enabled BOOLEAN NOT NULL DEFAULT false"
    ))
    op.execute(sa.text(
        "ALTER TABLE restaurant_settings "
        "ADD COLUMN print_bill_enabled BOOLEAN NOT NULL DEFAULT false"
    ))
    op.execute(sa.text(
        "ALTER TABLE restaurant_settings "
        "ADD COLUMN bill_copies INTEGER NOT NULL DEFAULT 2"
    ))


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE restaurant_settings DROP COLUMN IF EXISTS bill_copies"))
    op.execute(sa.text("ALTER TABLE restaurant_settings DROP COLUMN IF EXISTS print_bill_enabled"))
    op.execute(sa.text("ALTER TABLE restaurant_settings DROP COLUMN IF EXISTS print_kot_enabled"))
