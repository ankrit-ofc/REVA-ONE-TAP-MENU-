"""add kot-printer worker support (print mode/printer/token + kot_print_jobs queue)

Revision ID: 0015
Revises: 0014
Create Date: 2026-07-09 00:00:00.000000

The external kot-printer Windows service polls /printworker/kot/get and prints
kitchen tickets to an installed Windows printer, then acks. This adds:
- restaurant_settings.kot_print_mode ('browser' keeps the WebUSB behaviour,
  'worker' queues tickets server-side), kot_printer_name (Windows printer the
  ticket is routed to) and kot_worker_token (per-restaurant bearer token the
  worker authenticates with — this is how the poll is tenant-scoped).
- kot_print_jobs: the pending/printed ticket queue. queue_id is the numeric id
  the worker echoes back on ack. Rows are never deleted (print history).
"""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE restaurant_settings "
        "ADD COLUMN kot_print_mode VARCHAR(10) NOT NULL DEFAULT 'browser'"
    ))
    op.execute(sa.text(
        "ALTER TABLE restaurant_settings "
        "ADD CONSTRAINT ck_restaurant_settings_kot_print_mode "
        "CHECK (kot_print_mode IN ('browser', 'worker'))"
    ))
    op.execute(sa.text(
        "ALTER TABLE restaurant_settings ADD COLUMN kot_printer_name VARCHAR(120)"
    ))
    op.execute(sa.text(
        "ALTER TABLE restaurant_settings ADD COLUMN kot_worker_token VARCHAR(64)"
    ))
    op.execute(sa.text(
        "CREATE UNIQUE INDEX uq_restaurant_settings_kot_worker_token "
        "ON restaurant_settings (kot_worker_token) WHERE kot_worker_token IS NOT NULL"
    ))

    op.execute(sa.text(
        """
        CREATE TABLE kot_print_jobs (
            id UUID PRIMARY KEY,
            restaurant_id UUID NOT NULL REFERENCES restaurants(id) ON DELETE RESTRICT,
            queue_id BIGINT GENERATED ALWAYS AS IDENTITY,
            order_id UUID NOT NULL REFERENCES orders(id) ON DELETE RESTRICT,
            title VARCHAR(40) NOT NULL DEFAULT 'ORDER',
            ticket JSONB NOT NULL,
            printed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_kot_print_jobs_queue_id UNIQUE (queue_id)
        )
        """
    ))
    op.execute(sa.text(
        "CREATE INDEX ix_kot_print_jobs_restaurant_id ON kot_print_jobs (restaurant_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX ix_kot_print_jobs_order_id ON kot_print_jobs (order_id)"
    ))
    # The worker's poll: pending jobs for one restaurant, oldest first.
    op.execute(sa.text(
        "CREATE INDEX ix_kot_print_jobs_pending "
        "ON kot_print_jobs (restaurant_id, queue_id) WHERE printed_at IS NULL"
    ))

    # ── Row-Level Security (second line of defense; app-layer filter is first) ─
    op.execute(sa.text("ALTER TABLE kot_print_jobs ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text(
        "CREATE POLICY tenant_isolation ON kot_print_jobs "
        "USING (restaurant_id = current_setting('app.current_restaurant_id', TRUE)::uuid)"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP POLICY IF EXISTS tenant_isolation ON kot_print_jobs"))
    op.execute(sa.text("ALTER TABLE kot_print_jobs DISABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("DROP TABLE IF EXISTS kot_print_jobs CASCADE"))
    op.execute(sa.text(
        "DROP INDEX IF EXISTS uq_restaurant_settings_kot_worker_token"
    ))
    op.execute(sa.text("ALTER TABLE restaurant_settings DROP COLUMN IF EXISTS kot_worker_token"))
    op.execute(sa.text("ALTER TABLE restaurant_settings DROP COLUMN IF EXISTS kot_printer_name"))
    op.execute(sa.text(
        "ALTER TABLE restaurant_settings "
        "DROP CONSTRAINT IF EXISTS ck_restaurant_settings_kot_print_mode"
    ))
    op.execute(sa.text("ALTER TABLE restaurant_settings DROP COLUMN IF EXISTS kot_print_mode"))
