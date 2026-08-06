"""restaurant_settings: menu theming (template + accent colour)

Revision ID: 0027
Revises: 0026
Create Date: 2026-08-06 00:00:00.000000

Two additive, non-destructive columns:

- restaurant_settings.menu_template (VARCHAR(20), NOT NULL,
  DEFAULT 'classic'): which of the six customer-menu layouts to render.
  'classic' is today's existing thumbnail-left list — server_default
  backfills every existing row, so every restaurant renders byte-identically
  to before this migration until an admin actively opts into one of the
  five new templates.

- restaurant_settings.menu_accent_color (VARCHAR(7), nullable): hex accent
  colour (e.g. #1D9E75) applied to buttons/headings/chips/price/cart badge
  on the customer menu. NULL means the client falls back to the built-in
  default accent.

No data migration needed; downgrade drops both columns (loses only these
two presentation-layer values, no financial/order data).
"""

import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "restaurant_settings",
        sa.Column(
            "menu_template",
            sa.String(length=20),
            nullable=False,
            server_default="classic",
        ),
    )
    op.add_column(
        "restaurant_settings",
        sa.Column("menu_accent_color", sa.String(length=7), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("restaurant_settings", "menu_accent_color")
    op.drop_column("restaurant_settings", "menu_template")
