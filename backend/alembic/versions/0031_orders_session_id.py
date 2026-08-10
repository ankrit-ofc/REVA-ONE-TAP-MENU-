"""orders: session_id — the visit key

Revision ID: 0031
Revises: 0030
Create Date: 2026-08-10 00:00:00.000000

One additive, nullable FK column: orders.session_id -> table_sessions.id.

Why it is needed at all: table_id is not a visit key. One table hosts many
parties a day, and session_service.create_or_reuse_session hands the same
session row to everyone who scans that table inside TABLE_SESSION_TTL_HOURS,
so "which party did this" is currently only answerable by heuristic. The
session is already in scope where an order is created (order_service
.place_or_append takes it as an argument), so recording it costs one field.

NOT BACKFILLED, deliberately. Existing rows stay NULL. Reconstructing them
would mean matching orders to sessions by table_id plus a time window — the
same guess this column exists to eliminate — and a guess stored in an
exact-looking column is worse than an honest NULL. Consumers must treat NULL
as "before instrumentation" and drop those rows from denominators.

ondelete="RESTRICT" matches every other FK in this schema and the standing
no-hard-delete rule: table_sessions rows are never deleted, so this can only
ever fire as a safety net.

The index serves the queries this column exists for (group a visit's orders by
session, count sessions that did/didn't order). Column is nullable with no
server_default, so the ALTER is metadata-only — no table rewrite, no lock held
while data is copied, safe on a live orders table.

Downgrade drops the index and the column. It loses only the visit linkage
captured since deploy; no financial or order data is touched.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("session_id", PGUUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_orders_session_id_table_sessions",
        "orders",
        "table_sessions",
        ["session_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_orders_session_id", "orders", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_orders_session_id", table_name="orders")
    op.drop_constraint("fk_orders_session_id_table_sessions", "orders", type_="foreignkey")
    op.drop_column("orders", "session_id")
