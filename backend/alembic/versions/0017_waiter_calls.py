"""add waiter_calls (persisted, attend-able 'Call Waiter' log)

Revision ID: 0017
Revises: 0016
Create Date: 2026-07-14 00:00:00.000000

'Call Waiter' used to be a transient broadcast. This persists each call so the
waiter dashboard shows a live list of open calls and a waiter can confirm
attendance (who + when), keeping an auditable record. Rows are never deleted;
status moves PENDING -> ATTENDED. A partial unique index enforces at most one
PENDING call per table (repeated taps refresh the existing call, not pile up).
"""

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text(
        """
        CREATE TABLE waiter_calls (
            id UUID PRIMARY KEY,
            restaurant_id UUID NOT NULL REFERENCES restaurants(id) ON DELETE RESTRICT,
            table_id UUID NOT NULL REFERENCES tables(id) ON DELETE RESTRICT,
            status VARCHAR(10) NOT NULL DEFAULT 'PENDING',
            attended_at TIMESTAMPTZ,
            attended_by_user_id UUID REFERENCES users(id) ON DELETE RESTRICT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_waiter_calls_status CHECK (status IN ('PENDING', 'ATTENDED'))
        )
        """
    ))
    op.execute(sa.text(
        "CREATE INDEX ix_waiter_calls_restaurant_id ON waiter_calls (restaurant_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX ix_waiter_calls_table_id ON waiter_calls (table_id)"
    ))
    # At most one open call per table (a customer tapping twice refreshes it).
    op.execute(sa.text(
        "CREATE UNIQUE INDEX uq_waiter_calls_one_pending_per_table "
        "ON waiter_calls (table_id) WHERE status = 'PENDING'"
    ))
    # The waiter's poll: open calls for one restaurant, oldest first.
    op.execute(sa.text(
        "CREATE INDEX ix_waiter_calls_pending "
        "ON waiter_calls (restaurant_id, created_at) WHERE status = 'PENDING'"
    ))

    # ── Row-Level Security (second line of defense; app-layer filter is first) ─
    op.execute(sa.text("ALTER TABLE waiter_calls ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text(
        "CREATE POLICY tenant_isolation ON waiter_calls "
        "USING (restaurant_id = current_setting('app.current_restaurant_id', TRUE)::uuid)"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP POLICY IF EXISTS tenant_isolation ON waiter_calls"))
    op.execute(sa.text("ALTER TABLE waiter_calls DISABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("DROP TABLE IF EXISTS waiter_calls CASCADE"))
