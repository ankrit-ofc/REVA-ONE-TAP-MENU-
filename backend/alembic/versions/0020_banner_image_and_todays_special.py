"""menu customization: settings banner image + products todays-special flag

Revision ID: 0020
Revises: 0019
Create Date: 2026-07-16 00:00:00.000000

Two additive, non-destructive columns:

- restaurant_settings.banner_image_url (TEXT, nullable): URL of the
  admin-uploaded customer-menu hero image. Set only by the backend upload
  handler (never client-supplied); NULL means the customer page falls back
  to the built-in stock hero.

- products.is_todays_special (BOOLEAN, NOT NULL, DEFAULT false): admin
  toggle that features the product in the customer menu's "Today's Special"
  section. server_default false backfills every existing row.

No data migration needed; downgrade drops both columns (loses only these
two presentation-layer values, no financial/order data).
"""

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "restaurant_settings",
        sa.Column("banner_image_url", sa.Text(), nullable=True),
    )
    op.add_column(
        "products",
        sa.Column(
            "is_todays_special",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("products", "is_todays_special")
    op.drop_column("restaurant_settings", "banner_image_url")
