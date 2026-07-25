"""invoices: composite index for the order-history list

Revision ID: 0022
Revises: 0021
Create Date: 2026-07-25 00:00:00.000000

GET /counter/order-history filters on (restaurant_id, status) and orders by
created_at DESC. invoices previously carried only the single-column
restaurant_id index from TenantMixin, so that query degrades into a sort over
every invoice a restaurant has ever issued — and billing history grows without
bound.

Index only: no column added, dropped, or rewritten, and no data touched.
created_at is indexed DESC to match the query's ORDER BY, so the planner can
walk the index instead of sorting.

Downgrade drops the index; the query still returns identical results, just
more slowly.
"""

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_invoices_restaurant_status_created",
        "invoices",
        ["restaurant_id", "status", "created_at"],
        postgresql_ops={"created_at": "DESC"},
    )


def downgrade() -> None:
    op.drop_index("ix_invoices_restaurant_status_created", table_name="invoices")
