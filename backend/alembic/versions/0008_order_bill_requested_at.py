"""add bill_requested_at to orders

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-17 00:00:00.000000

Records when the customer asked for the bill. Staff can move an order to billing
(MEAL_FINISHED) only after this is set — see order_service.transition_order.
Nullable; legacy rows are NULL (no request on record).
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE orders ADD COLUMN bill_requested_at TIMESTAMPTZ"
    ))


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE orders DROP COLUMN IF EXISTS bill_requested_at"))
