"""add customers + contact-capture links on orders and invoices

Revision ID: 0026
Revises: 0025
Create Date: 2026-08-03 00:00:00.000000

Captures diner contact details (email required, name/phone optional) so we can
email receipts and, later, recognise repeat customers.

Link design:
  invoices.customer_id  — the ANALYTICS link. One bill = one payer, so repeat
                          visits and lifetime spend are a plain GROUP BY over
                          invoices, with no table+time-window joins.
  orders.customer_id    — a CARRIER only. The customer submits their email when
                          they tap "Request Bill", which happens while the order
                          is still OPEN and long before staff generate an
                          invoice; the value is copied onto the invoice at
                          generation time.

Both FKs are nullable, so every existing order and invoice stays valid.
"""

import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text(
        """
        CREATE TABLE customers (
            id UUID PRIMARY KEY,
            restaurant_id UUID NOT NULL REFERENCES restaurants(id) ON DELETE RESTRICT,
            email TEXT NOT NULL,
            name VARCHAR(120),
            phone VARCHAR(32),
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    ))
    op.execute(sa.text(
        "CREATE INDEX ix_customers_restaurant_id ON customers (restaurant_id)"
    ))
    # One row per email per restaurant. The same address at a different tenant is
    # a separate customer. NOTE: a plain column index, not a functional one — the
    # application normalises (trim + lowercase) before every read and write, in
    # customer_service.normalize_email.
    op.execute(sa.text(
        "CREATE UNIQUE INDEX uq_customers_restaurant_email ON customers (restaurant_id, email)"
    ))

    # ── Row-Level Security (second line of defense; app-layer filter is first) ─
    # Same pattern as every other tenant table (see 0002/0017). The GUC is set
    # from the verified staff JWT (deps.tenant_scope) or from the customer's
    # table-session token (deps.get_current_session) — never from client input.
    op.execute(sa.text("ALTER TABLE customers ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text(
        "CREATE POLICY tenant_isolation ON customers "
        "USING (restaurant_id = current_setting('app.current_restaurant_id', TRUE)::uuid)"
    ))

    # ── Links ─────────────────────────────────────────────────────────────────
    op.execute(sa.text(
        "ALTER TABLE orders ADD COLUMN customer_id UUID "
        "REFERENCES customers(id) ON DELETE RESTRICT"
    ))
    op.execute(sa.text(
        "ALTER TABLE invoices ADD COLUMN customer_id UUID "
        "REFERENCES customers(id) ON DELETE RESTRICT"
    ))
    # Send-once guard for the emailed receipt.
    op.execute(sa.text(
        "ALTER TABLE invoices ADD COLUMN receipt_sent_at TIMESTAMPTZ"
    ))
    # The repeat-visit / lifetime-spend query: all invoices for one customer.
    op.execute(sa.text(
        "CREATE INDEX ix_invoices_customer_id ON invoices (customer_id) "
        "WHERE customer_id IS NOT NULL"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ix_invoices_customer_id"))
    op.execute(sa.text("ALTER TABLE invoices DROP COLUMN IF EXISTS receipt_sent_at"))
    op.execute(sa.text("ALTER TABLE invoices DROP COLUMN IF EXISTS customer_id"))
    op.execute(sa.text("ALTER TABLE orders DROP COLUMN IF EXISTS customer_id"))
    op.execute(sa.text("DROP POLICY IF EXISTS tenant_isolation ON customers"))
    op.execute(sa.text("ALTER TABLE customers DISABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("DROP TABLE IF EXISTS customers CASCADE"))
