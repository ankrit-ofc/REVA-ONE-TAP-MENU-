"""restaurant settings: payment QR image

Revision ID: 0021
Revises: 0020
Create Date: 2026-07-25 00:00:00.000000

One additive, non-destructive column:

- restaurant_settings.payment_qr_url (TEXT, nullable): URL of the
  admin-uploaded payment QR (eSewa / Khalti / Fonepay) that staff display to
  guests on the Billing screen. Set only by the backend upload handler (never
  client-supplied); NULL means no QR is configured for the restaurant.

No data migration needed; downgrade drops the column (loses only this
presentation-layer value, no financial/order data).
"""

import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "restaurant_settings",
        sa.Column("payment_qr_url", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("restaurant_settings", "payment_qr_url")
