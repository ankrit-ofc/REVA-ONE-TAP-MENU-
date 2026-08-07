"""restaurant_settings: customer-editable "Today's Special" section title

Revision ID: 0028
Revises: 0027
Create Date: 2026-08-07 00:00:00.000000

One additive, non-destructive column:

- restaurant_settings.specials_section_title (VARCHAR(80), nullable): admin-
  editable heading for the customer menu's "Today's Special" section. NULL
  (or, at the app layer, whitespace-only) means the client falls back to the
  default "Today's Special" text. No server_default / data rewrite — every
  existing row is simply NULL after this migration, which is exactly today's
  behaviour (the hardcoded default text renders unchanged).

Downgrade drops the column (loses only this presentation-layer value, no
financial/order data).
"""

import sqlalchemy as sa
from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "restaurant_settings",
        sa.Column("specials_section_title", sa.String(length=80), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("restaurant_settings", "specials_section_title")
