"""restaurants: AR + online QR-pay plan toggles

Revision ID: 0024
Revises: 0023
Create Date: 2026-07-30 00:00:00.000000

Adds ar_enabled and qr_payment_enabled starter toggles (default true).
Consulted only when plan == starter; basic forces both off, custom forces both
on via plan_features. Existing restaurants (default plan custom) keep full
capability. Customer QR pay still also requires settings.enable_qr_payment.
"""

import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "restaurants",
        sa.Column(
            "ar_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "restaurants",
        sa.Column(
            "qr_payment_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    op.drop_column("restaurants", "qr_payment_enabled")
    op.drop_column("restaurants", "ar_enabled")
