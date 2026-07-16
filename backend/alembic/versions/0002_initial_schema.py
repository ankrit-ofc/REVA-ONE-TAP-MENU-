"""initial schema

Revision ID: 0002
Revises: 001
Create Date: 2026-06-13 00:00:00.000000

Creates all 16 tables with full integrity: ENUMs, CHECK constraints, UNIQUE
constraints, partial unique index (one active order per table), and Row-Level
Security policies on every tenant-owned table.
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "001"
branch_labels = None
depends_on = None

# All tenant-owned tables — used to apply / remove RLS in bulk.
TENANT_TABLES = [
    "users",
    "restaurant_settings",
    "categories",
    "products",
    "product_variants",
    "product_addons",
    "product_addon_mappings",
    "tables",
    "table_sessions",
    "orders",
    "order_items",
    "order_item_addons",
    "invoices",
    "audit_logs",
    "restaurant_counters",
]


def upgrade() -> None:
    # ── ENUM types ────────────────────────────────────────────────────────────
    op.execute(sa.text(
        "CREATE TYPE role AS ENUM ('SUPERADMIN','ADMIN','KITCHEN','WAITER','COUNTER')"
    ))
    op.execute(sa.text(
        "CREATE TYPE order_status AS ENUM ('OPEN','MEAL_FINISHED','CLOSED')"
    ))
    op.execute(sa.text(
        "CREATE TYPE order_item_status AS ENUM ('NEW','PREPARING','READY','SERVED','CANCELLED')"
    ))
    op.execute(sa.text(
        "CREATE TYPE invoice_status AS ENUM ('DRAFT','PENDING_PAYMENT','PAID','FAILED','VOID','REFUNDED')"
    ))
    op.execute(sa.text(
        "CREATE TYPE payment_method AS ENUM ('CASH','CARD','COUNTER_WALLET','QR_GATEWAY','MANUAL_OVERRIDE')"
    ))
    op.execute(sa.text(
        "CREATE TYPE session_status AS ENUM ('ACTIVE','EXPIRED','INVALIDATED')"
    ))

    # ── restaurants ───────────────────────────────────────────────────────────
    op.execute(sa.text("""
        CREATE TABLE restaurants (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name       VARCHAR(255) NOT NULL,
            slug       VARCHAR(100) NOT NULL,
            is_active  BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_restaurants_slug UNIQUE (slug)
        )
    """))

    # ── users ─────────────────────────────────────────────────────────────────
    op.execute(sa.text("""
        CREATE TABLE users (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            restaurant_id UUID NOT NULL REFERENCES restaurants(id),
            email         VARCHAR(255) NOT NULL,
            password_hash TEXT NOT NULL,
            role          role NOT NULL,
            is_active     BOOLEAN NOT NULL DEFAULT TRUE,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_users_email_restaurant UNIQUE (email, restaurant_id)
        )
    """))
    op.execute(sa.text("CREATE INDEX ix_users_restaurant_id ON users (restaurant_id)"))

    # ── restaurant_settings ───────────────────────────────────────────────────
    op.execute(sa.text("""
        CREATE TABLE restaurant_settings (
            id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            restaurant_id             UUID NOT NULL REFERENCES restaurants(id),
            enable_qr_payment         BOOLEAN NOT NULL DEFAULT FALSE,
            waiter_can_accept_payment BOOLEAN NOT NULL DEFAULT FALSE,
            allow_order_reopen        BOOLEAN NOT NULL DEFAULT FALSE,
            currency                  CHAR(3) NOT NULL DEFAULT 'NPR',
            timezone                  TEXT NOT NULL DEFAULT 'Asia/Kathmandu',
            created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_restaurant_settings_restaurant UNIQUE (restaurant_id)
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX ix_restaurant_settings_restaurant_id ON restaurant_settings (restaurant_id)"
    ))

    # ── categories ────────────────────────────────────────────────────────────
    op.execute(sa.text("""
        CREATE TABLE categories (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            restaurant_id UUID NOT NULL REFERENCES restaurants(id),
            name          VARCHAR(255) NOT NULL,
            display_order INTEGER NOT NULL DEFAULT 0,
            is_active     BOOLEAN NOT NULL DEFAULT TRUE,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    op.execute(sa.text("CREATE INDEX ix_categories_restaurant_id ON categories (restaurant_id)"))

    # ── products ──────────────────────────────────────────────────────────────
    op.execute(sa.text("""
        CREATE TABLE products (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            restaurant_id UUID NOT NULL REFERENCES restaurants(id),
            category_id   UUID NOT NULL REFERENCES categories(id),
            name          VARCHAR(255) NOT NULL,
            base_price    NUMERIC(12,2) NOT NULL,
            tax_rate      NUMERIC(5,2) NOT NULL DEFAULT 0,
            is_available  BOOLEAN NOT NULL DEFAULT TRUE,
            is_active     BOOLEAN NOT NULL DEFAULT TRUE,
            has_variants  BOOLEAN NOT NULL DEFAULT FALSE,
            allows_addons BOOLEAN NOT NULL DEFAULT FALSE,
            image_url     TEXT,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_products_base_price_non_negative CHECK (base_price >= 0),
            CONSTRAINT ck_products_tax_rate_non_negative   CHECK (tax_rate >= 0)
        )
    """))
    op.execute(sa.text("CREATE INDEX ix_products_restaurant_id ON products (restaurant_id)"))
    op.execute(sa.text("CREATE INDEX ix_products_category_id   ON products (category_id)"))

    # ── product_variants ──────────────────────────────────────────────────────
    op.execute(sa.text("""
        CREATE TABLE product_variants (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            restaurant_id UUID NOT NULL REFERENCES restaurants(id),
            product_id    UUID NOT NULL REFERENCES products(id),
            name          VARCHAR(255) NOT NULL,
            price         NUMERIC(12,2) NOT NULL,
            is_active     BOOLEAN NOT NULL DEFAULT TRUE,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_product_variants_price_non_negative CHECK (price >= 0)
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX ix_product_variants_restaurant_id ON product_variants (restaurant_id)"
    ))
    op.execute(sa.text("CREATE INDEX ix_product_variants_product_id ON product_variants (product_id)"))

    # ── product_addons ────────────────────────────────────────────────────────
    op.execute(sa.text("""
        CREATE TABLE product_addons (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            restaurant_id UUID NOT NULL REFERENCES restaurants(id),
            name          VARCHAR(255) NOT NULL,
            price         NUMERIC(12,2) NOT NULL,
            is_active     BOOLEAN NOT NULL DEFAULT TRUE,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_product_addons_price_non_negative CHECK (price >= 0)
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX ix_product_addons_restaurant_id ON product_addons (restaurant_id)"
    ))

    # ── product_addon_mappings ────────────────────────────────────────────────
    op.execute(sa.text("""
        CREATE TABLE product_addon_mappings (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            restaurant_id UUID NOT NULL REFERENCES restaurants(id),
            product_id    UUID NOT NULL REFERENCES products(id),
            addon_id      UUID NOT NULL REFERENCES product_addons(id),
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_product_addon_mappings_product_addon UNIQUE (product_id, addon_id)
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX ix_product_addon_mappings_restaurant_id ON product_addon_mappings (restaurant_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX ix_product_addon_mappings_product_id ON product_addon_mappings (product_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX ix_product_addon_mappings_addon_id ON product_addon_mappings (addon_id)"
    ))

    # ── tables ────────────────────────────────────────────────────────────────
    op.execute(sa.text("""
        CREATE TABLE tables (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            restaurant_id UUID NOT NULL REFERENCES restaurants(id),
            name          VARCHAR(100) NOT NULL,
            is_active     BOOLEAN NOT NULL DEFAULT TRUE,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_tables_name_restaurant UNIQUE (name, restaurant_id)
        )
    """))
    op.execute(sa.text("CREATE INDEX ix_tables_restaurant_id ON tables (restaurant_id)"))

    # ── table_sessions ────────────────────────────────────────────────────────
    op.execute(sa.text("""
        CREATE TABLE table_sessions (
            id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            restaurant_id  UUID NOT NULL REFERENCES restaurants(id),
            table_id       UUID NOT NULL REFERENCES tables(id),
            token          TEXT NOT NULL,
            status         session_status NOT NULL DEFAULT 'ACTIVE',
            expires_at     TIMESTAMPTZ NOT NULL,
            invalidated_at TIMESTAMPTZ,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_table_sessions_token UNIQUE (token)
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX ix_table_sessions_restaurant_id ON table_sessions (restaurant_id)"
    ))
    op.execute(sa.text("CREATE INDEX ix_table_sessions_table_id ON table_sessions (table_id)"))
    op.execute(sa.text("CREATE INDEX ix_table_sessions_token    ON table_sessions (token)"))

    # ── orders ────────────────────────────────────────────────────────────────
    op.execute(sa.text("""
        CREATE TABLE orders (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            restaurant_id UUID NOT NULL REFERENCES restaurants(id),
            table_id      UUID NOT NULL REFERENCES tables(id),
            order_number  INTEGER NOT NULL,
            status        order_status NOT NULL DEFAULT 'OPEN',
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_orders_restaurant_order_number UNIQUE (restaurant_id, order_number)
        )
    """))
    op.execute(sa.text("CREATE INDEX ix_orders_restaurant_id ON orders (restaurant_id)"))
    op.execute(sa.text("CREATE INDEX ix_orders_table_id      ON orders (table_id)"))
    # Partial unique index: at most one OPEN or MEAL_FINISHED order per table.
    op.execute(sa.text("""
        CREATE UNIQUE INDEX uq_orders_active_table
        ON orders (table_id)
        WHERE status IN ('OPEN', 'MEAL_FINISHED')
    """))

    # ── order_items ───────────────────────────────────────────────────────────
    op.execute(sa.text("""
        CREATE TABLE order_items (
            id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            restaurant_id        UUID NOT NULL REFERENCES restaurants(id),
            order_id             UUID NOT NULL REFERENCES orders(id),
            product_id           UUID NOT NULL REFERENCES products(id),
            status               order_item_status NOT NULL DEFAULT 'NEW',
            quantity             INTEGER NOT NULL,
            special_instructions VARCHAR(500),
            product_name         TEXT NOT NULL,
            variant_name         TEXT,
            unit_price           NUMERIC(12,2) NOT NULL,
            tax_rate             NUMERIC(5,2) NOT NULL,
            preparing_at         TIMESTAMPTZ,
            ready_at             TIMESTAMPTZ,
            served_at            TIMESTAMPTZ,
            created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_order_items_quantity_positive        CHECK (quantity > 0),
            CONSTRAINT ck_order_items_unit_price_non_negative  CHECK (unit_price >= 0),
            CONSTRAINT ck_order_items_tax_rate_non_negative    CHECK (tax_rate >= 0)
        )
    """))
    op.execute(sa.text("CREATE INDEX ix_order_items_restaurant_id ON order_items (restaurant_id)"))
    op.execute(sa.text("CREATE INDEX ix_order_items_order_id      ON order_items (order_id)"))
    op.execute(sa.text("CREATE INDEX ix_order_items_product_id    ON order_items (product_id)"))

    # ── order_item_addons ─────────────────────────────────────────────────────
    op.execute(sa.text("""
        CREATE TABLE order_item_addons (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            restaurant_id UUID NOT NULL REFERENCES restaurants(id),
            order_item_id UUID NOT NULL REFERENCES order_items(id),
            addon_name    TEXT NOT NULL,
            addon_price   NUMERIC(12,2) NOT NULL,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_order_item_addons_price_non_negative CHECK (addon_price >= 0)
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX ix_order_item_addons_restaurant_id ON order_item_addons (restaurant_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX ix_order_item_addons_order_item_id ON order_item_addons (order_item_id)"
    ))

    # ── invoices ──────────────────────────────────────────────────────────────
    op.execute(sa.text("""
        CREATE TABLE invoices (
            id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            restaurant_id          UUID NOT NULL REFERENCES restaurants(id),
            order_id               UUID NOT NULL REFERENCES orders(id),
            invoice_number         TEXT NOT NULL,
            status                 invoice_status NOT NULL DEFAULT 'DRAFT',
            payment_method         payment_method,
            subtotal               NUMERIC(12,2) NOT NULL,
            discount               NUMERIC(12,2) NOT NULL DEFAULT 0,
            tax_total              NUMERIC(12,2) NOT NULL DEFAULT 0,
            total                  NUMERIC(12,2) NOT NULL,
            gateway_transaction_id TEXT,
            created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_invoices_restaurant_invoice_number  UNIQUE (restaurant_id, invoice_number),
            CONSTRAINT uq_invoices_gateway_transaction_id     UNIQUE (gateway_transaction_id),
            CONSTRAINT ck_invoices_subtotal_non_negative      CHECK (subtotal >= 0),
            CONSTRAINT ck_invoices_discount_non_negative      CHECK (discount >= 0),
            CONSTRAINT ck_invoices_tax_total_non_negative     CHECK (tax_total >= 0),
            CONSTRAINT ck_invoices_total_non_negative         CHECK (total >= 0)
        )
    """))
    op.execute(sa.text("CREATE INDEX ix_invoices_restaurant_id ON invoices (restaurant_id)"))
    op.execute(sa.text("CREATE INDEX ix_invoices_order_id      ON invoices (order_id)"))

    # ── audit_logs (append-only; no updated_at) ───────────────────────────────
    op.execute(sa.text("""
        CREATE TABLE audit_logs (
            id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            restaurant_id  UUID NOT NULL REFERENCES restaurants(id),
            actor_user_id  UUID REFERENCES users(id) ON DELETE SET NULL,
            actor_type     TEXT NOT NULL,
            entity_type    TEXT NOT NULL,
            entity_id      UUID NOT NULL,
            action         TEXT NOT NULL,
            previous_value JSONB,
            new_value      JSONB,
            reason         TEXT,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    op.execute(sa.text("CREATE INDEX ix_audit_logs_restaurant_id  ON audit_logs (restaurant_id)"))
    op.execute(sa.text(
        "CREATE INDEX ix_audit_logs_entity ON audit_logs (entity_type, entity_id)"
    ))
    op.execute(sa.text("CREATE INDEX ix_audit_logs_actor_user_id ON audit_logs (actor_user_id)"))

    # ── restaurant_counters ───────────────────────────────────────────────────
    op.execute(sa.text("""
        CREATE TABLE restaurant_counters (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            restaurant_id UUID NOT NULL REFERENCES restaurants(id),
            counter_type  TEXT NOT NULL,
            current_value INTEGER NOT NULL DEFAULT 0,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_restaurant_counters_restaurant_type UNIQUE (restaurant_id, counter_type)
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX ix_restaurant_counters_restaurant_id ON restaurant_counters (restaurant_id)"
    ))

    # ── Row-Level Security ────────────────────────────────────────────────────
    # Table owners (tenant_app_user) bypass RLS by default; FORCE ROW LEVEL SECURITY
    # would apply it to the owner too. Phase 2 sets app.current_restaurant_id per
    # request. RLS is the second line of defense after mandatory app-layer filtering.
    for table in TENANT_TABLES:
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING (restaurant_id = "
            f"current_setting('app.current_restaurant_id', TRUE)::uuid)"
        ))


def downgrade() -> None:
    # Drop RLS policies first
    for table in reversed(TENANT_TABLES):
        op.execute(sa.text(f"DROP POLICY IF EXISTS tenant_isolation ON {table}"))
        op.execute(sa.text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))

    # Drop tables in reverse FK dependency order
    for table in [
        "restaurant_counters",
        "audit_logs",
        "invoices",
        "order_item_addons",
        "order_items",
        "orders",
        "table_sessions",
        "tables",
        "product_addon_mappings",
        "product_addons",
        "product_variants",
        "products",
        "categories",
        "restaurant_settings",
        "users",
        "restaurants",
    ]:
        op.execute(sa.text(f"DROP TABLE IF EXISTS {table} CASCADE"))

    # Drop ENUM types (reverse creation order)
    for enum_type in [
        "session_status",
        "payment_method",
        "invoice_status",
        "order_item_status",
        "order_status",
        "role",
    ]:
        op.execute(sa.text(f"DROP TYPE IF EXISTS {enum_type}"))
