"""restaurants: rename qr flag + copy from settings; plan = preset-only semantics

Revision ID: 0025
Revises: 0024
Create Date: 2026-07-30 00:00:00.000000

1. Rename restaurants.qr_payment_enabled -> qr_pay_enabled.
2. OVERWRITE qr_pay_enabled from restaurant_settings.enable_qr_payment so venues
   that had QR off in settings stay off (sole truth moves to restaurants).
3. Soft-deprecate restaurant_settings.enable_qr_payment: column KEPT for now
   (staff mobile still sends it on SettingsUpdate). A LATER migration drops it
   once mobile stops sending the field. Runtime truth is restaurants.qr_pay_enabled.
"""

import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "restaurants",
        "qr_payment_enabled",
        new_column_name="qr_pay_enabled",
    )
    # Copy settings → restaurants so nobody currently using QR-off loses that state.
    op.execute(
        sa.text(
            """
            UPDATE restaurants r
            SET qr_pay_enabled = COALESCE(s.enable_qr_payment, FALSE)
            FROM restaurant_settings s
            WHERE s.restaurant_id = r.id
            """
        )
    )
    # Restaurants with no settings row: leave whatever was already on the column
    # (defaults true from 0024 / custom plan). No-op for those.


def downgrade() -> None:
    op.alter_column(
        "restaurants",
        "qr_pay_enabled",
        new_column_name="qr_payment_enabled",
    )
