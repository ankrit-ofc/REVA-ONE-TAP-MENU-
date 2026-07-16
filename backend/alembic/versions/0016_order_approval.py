"""waiter order-approval gate (PENDING_APPROVAL item status + settings toggle)

Revision ID: 0016
Revises: 0015
Create Date: 2026-07-10 00:00:00.000000

When restaurant_settings.require_order_approval is true, each batch of
customer-ordered items is created as PENDING_APPROVAL: invisible to the
kitchen queue and unprinted until a waiter approves (-> NEW, KOT fires) or
rejects (-> CANCELLED) the batch. This adds:
- 'PENDING_APPROVAL' to the order_item_status enum (before 'NEW').
- restaurant_settings.require_order_approval boolean, default false.
"""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A value added to an enum cannot be used inside the same transaction that
    # added it; run the ALTER TYPE outside the migration transaction.
    with op.get_context().autocommit_block():
        op.execute(sa.text(
            "ALTER TYPE order_item_status ADD VALUE IF NOT EXISTS "
            "'PENDING_APPROVAL' BEFORE 'NEW'"
        ))
    op.execute(sa.text(
        "ALTER TABLE restaurant_settings "
        "ADD COLUMN require_order_approval BOOLEAN NOT NULL DEFAULT false"
    ))


def downgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE restaurant_settings DROP COLUMN IF EXISTS require_order_approval"
    ))
    # PostgreSQL cannot drop an enum value; rebuild the type without it.
    op.execute(sa.text(
        "UPDATE order_items SET status = 'NEW' WHERE status = 'PENDING_APPROVAL'"
    ))
    op.execute(sa.text("ALTER TYPE order_item_status RENAME TO order_item_status_old"))
    op.execute(sa.text(
        "CREATE TYPE order_item_status AS ENUM "
        "('NEW', 'PREPARING', 'READY', 'SERVED', 'CANCELLED')"
    ))
    op.execute(sa.text("ALTER TABLE order_items ALTER COLUMN status DROP DEFAULT"))
    op.execute(sa.text(
        "ALTER TABLE order_items ALTER COLUMN status "
        "TYPE order_item_status USING status::text::order_item_status"
    ))
    op.execute(sa.text(
        "ALTER TABLE order_items ALTER COLUMN status SET DEFAULT 'NEW'"
    ))
    op.execute(sa.text("DROP TYPE order_item_status_old"))
