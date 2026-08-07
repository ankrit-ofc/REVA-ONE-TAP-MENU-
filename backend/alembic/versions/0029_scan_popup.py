"""restaurant_settings: promotional scan popup

Revision ID: 0029
Revises: 0028
Create Date: 2026-08-07 00:00:00.000000

Twelve additive, non-destructive columns for the first-scan promotional popup:

- popup_enabled (BOOLEAN, NOT NULL, DEFAULT false): admin on/off switch.
  server_default backfills every existing row false, so no restaurant's
  customer menu changes on deploy until an admin opts in.
- popup_badge_text, popup_headline, popup_masthead_subline, popup_bubble_text,
  popup_kicker, popup_tagline, popup_section_label, popup_cta_text,
  popup_footer_text (all VARCHAR, nullable): every piece of popup copy.
  NULL/whitespace-only means the client hides that element (headline and CTA
  fall back to the restaurant name / "See the menu" instead of hiding).
- popup_illustration_url (TEXT, nullable): URL of the admin-uploaded popup
  illustration. Set only by the backend upload handler (never client-supplied,
  mirrors banner_image_url); NULL means the illustration slot is hidden.
- popup_product_ids (JSONB, NOT NULL, DEFAULT '[]'): ordered list of up to 5
  product-id strings featured in the popup. A plain JSON array rather than a
  join table — order matters and a array preserves it for free, the list is
  capped at 5, and products are never hard-deleted in this codebase (soft
  delete via is_active), so a stale id simply stops resolving via the
  customer menu tree instead of ever violating a real FK.

No data migration needed; downgrade drops all twelve columns (loses only
these presentation-layer values, no financial/order data).
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "restaurant_settings",
        sa.Column("popup_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("restaurant_settings", sa.Column("popup_badge_text", sa.String(length=30), nullable=True))
    op.add_column("restaurant_settings", sa.Column("popup_headline", sa.String(length=60), nullable=True))
    op.add_column("restaurant_settings", sa.Column("popup_masthead_subline", sa.String(length=80), nullable=True))
    op.add_column("restaurant_settings", sa.Column("popup_bubble_text", sa.String(length=100), nullable=True))
    op.add_column("restaurant_settings", sa.Column("popup_kicker", sa.String(length=60), nullable=True))
    op.add_column("restaurant_settings", sa.Column("popup_tagline", sa.String(length=100), nullable=True))
    op.add_column("restaurant_settings", sa.Column("popup_section_label", sa.String(length=40), nullable=True))
    op.add_column("restaurant_settings", sa.Column("popup_cta_text", sa.String(length=40), nullable=True))
    op.add_column("restaurant_settings", sa.Column("popup_footer_text", sa.String(length=80), nullable=True))
    op.add_column("restaurant_settings", sa.Column("popup_illustration_url", sa.Text(), nullable=True))
    op.add_column(
        "restaurant_settings",
        sa.Column(
            "popup_product_ids",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("restaurant_settings", "popup_product_ids")
    op.drop_column("restaurant_settings", "popup_illustration_url")
    op.drop_column("restaurant_settings", "popup_footer_text")
    op.drop_column("restaurant_settings", "popup_cta_text")
    op.drop_column("restaurant_settings", "popup_section_label")
    op.drop_column("restaurant_settings", "popup_tagline")
    op.drop_column("restaurant_settings", "popup_kicker")
    op.drop_column("restaurant_settings", "popup_bubble_text")
    op.drop_column("restaurant_settings", "popup_masthead_subline")
    op.drop_column("restaurant_settings", "popup_headline")
    op.drop_column("restaurant_settings", "popup_badge_text")
    op.drop_column("restaurant_settings", "popup_enabled")
