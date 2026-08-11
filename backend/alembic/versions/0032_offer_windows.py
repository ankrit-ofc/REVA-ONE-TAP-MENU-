"""offer_windows + offer_window_products; order_items offer provenance

Revision ID: 0032
Revises: 0031
Create Date: 2026-08-11 00:00:00.000000

The Dead Hours Engine's pricing half. Two new tables plus two additive columns
on order_items.

WHY A TABLE AND NOT JSON ON restaurant_settings
popup_product_ids is JSONB because it is ONE ordered list on a singleton row,
never queried by, never independently enabled. Offers invert every one of those:
plural per restaurant, each independently enabled, each soft-deleted, each
looked up by "which offers are live right now", and each carrying a value that
decides what a customer is CHARGED. A JSONB blob cannot hold a CHECK
constraint, and money that the database cannot reject impossible states for is
money the application is guessing at.

THE CONSTRAINTS ARE THE DESIGN RULES
- ck_offer_windows_percent_max is the never-surge rule in the database. A
  PERCENT offer above 100 would produce a negative price; it cannot be stored.
- ck_offer_windows_fixed_needs_floor makes min_resulting_price mandatory for a
  FIXED discount. The owner states the floor; there is deliberately no default,
  because a hidden default on the money path is exactly the kind of wrong
  nobody notices.
- ck_offer_windows_time_order forbids a window that wraps past midnight. Dead
  hours are a daytime phenomenon and a wrapping window makes every "is this
  live" comparison a special case.
- ck_offer_windows_target ties applies_to to the column it needs, so a
  CATEGORY offer cannot exist without a category and a PRODUCTS offer cannot
  carry a stray one.

weekday_mask is a 7-bit SMALLINT (bit 0 = Monday, matching Python's
date.weekday()) rather than an array or seven booleans: one column, one CHECK,
and `weekday_mask & (1 << n)` is a plain indexable predicate. 0 is excluded
because an offer that runs on no day is configuration nobody meant to write.

start_time/end_time are TIME, not TIMESTAMPTZ, for the reason
daily_report_closing_time is: "2pm" is a recurring LOCAL fact, and storing an
instant would drift across DST for any tenant outside Nepal. They are read
against the restaurant's own timezone, never UTC.

ORDER_ITEMS PROVENANCE (financial table — change explicitly approved)
order_items.unit_price already snapshots what was charged, so a discounted bill
already reprints correctly. What it cannot do is say WHY. offer_name and
list_unit_price record the offer that applied and the anchor price it applied
to, so a receipt reprinted months later can show "Momo Rs 150 (Afternoon
Special, was Rs 200)" instead of a bare number that looks like a mispriced
item. Both are nullable and NEVER backfilled: rows written before this
migration had no offer, and inventing an anchor equal to the charged price
would put a fabricated value in a provenance column.

ck_order_items_offer_provenance keeps the pair honest — either both are set or
neither is, so `offer_name IS NOT NULL` is a reliable "this line was
discounted" test for every consumer.

Additive and non-destructive: no existing row is rewritten and no column is
dropped or retyped. Downgrade removes the offer tables and the two provenance
columns; it destroys offer configuration and the record of WHICH offer applied
to past orders, but never a charged amount — unit_price is untouched.
"""

import sqlalchemy as sa
from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("CREATE TYPE offer_discount_type AS ENUM ('PERCENT','FIXED')"))
    op.execute(sa.text("CREATE TYPE offer_applies_to AS ENUM ('CATEGORY','PRODUCTS')"))

    op.execute(sa.text(
        """
        CREATE TABLE offer_windows (
            id                  UUID PRIMARY KEY,
            restaurant_id       UUID NOT NULL REFERENCES restaurants(id) ON DELETE RESTRICT,
            name                VARCHAR(60) NOT NULL,
            discount_type       offer_discount_type NOT NULL,
            discount_value      NUMERIC(12,2) NOT NULL,
            min_resulting_price NUMERIC(12,2),
            start_time          TIME NOT NULL,
            end_time            TIME NOT NULL,
            weekday_mask        SMALLINT NOT NULL,
            applies_to          offer_applies_to NOT NULL,
            category_id         UUID REFERENCES categories(id) ON DELETE RESTRICT,
            is_enabled          BOOLEAN NOT NULL DEFAULT false,
            is_active           BOOLEAN NOT NULL DEFAULT true,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

            -- A discount of zero is not an offer.
            CONSTRAINT ck_offer_windows_discount_positive
                CHECK (discount_value > 0),
            -- RULE 1, in the database: the engine can only price BELOW normal.
            CONSTRAINT ck_offer_windows_percent_max
                CHECK (discount_type <> 'PERCENT' OR discount_value <= 100),
            -- A floor, when present, must be a real price.
            CONSTRAINT ck_offer_windows_floor_positive
                CHECK (min_resulting_price IS NULL OR min_resulting_price > 0),
            -- FIXED must state its floor; PERCENT may, and it is honoured if set.
            CONSTRAINT ck_offer_windows_fixed_needs_floor
                CHECK (discount_type <> 'FIXED' OR min_resulting_price IS NOT NULL),
            -- No wrap past midnight.
            CONSTRAINT ck_offer_windows_time_order
                CHECK (end_time > start_time),
            -- Runs on at least one weekday; bit 0 = Monday.
            CONSTRAINT ck_offer_windows_weekday_mask
                CHECK (weekday_mask BETWEEN 1 AND 127),
            CONSTRAINT ck_offer_windows_target
                CHECK ((applies_to = 'CATEGORY') = (category_id IS NOT NULL))
        )
        """
    ))
    op.execute(sa.text(
        "CREATE INDEX ix_offer_windows_restaurant_id ON offer_windows (restaurant_id)"
    ))
    # The hot read: every live offer for one tenant on every customer menu load.
    op.execute(sa.text(
        "CREATE INDEX ix_offer_windows_live ON offer_windows (restaurant_id) "
        "WHERE is_active AND is_enabled"
    ))

    op.execute(sa.text(
        """
        CREATE TABLE offer_window_products (
            id              UUID PRIMARY KEY,
            restaurant_id   UUID NOT NULL REFERENCES restaurants(id) ON DELETE RESTRICT,
            offer_window_id UUID NOT NULL REFERENCES offer_windows(id) ON DELETE RESTRICT,
            product_id      UUID NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_offer_window_products_offer_product
                UNIQUE (offer_window_id, product_id)
        )
        """
    ))
    op.execute(sa.text(
        "CREATE INDEX ix_offer_window_products_restaurant_id "
        "ON offer_window_products (restaurant_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX ix_offer_window_products_offer "
        "ON offer_window_products (offer_window_id)"
    ))

    # ── order_items provenance ────────────────────────────────────────────────
    op.add_column("order_items", sa.Column("offer_name", sa.String(length=60), nullable=True))
    op.add_column(
        "order_items", sa.Column("list_unit_price", sa.Numeric(12, 2), nullable=True)
    )
    op.execute(sa.text(
        "ALTER TABLE order_items ADD CONSTRAINT ck_order_items_list_price_non_negative "
        "CHECK (list_unit_price IS NULL OR list_unit_price >= 0)"
    ))
    op.execute(sa.text(
        "ALTER TABLE order_items ADD CONSTRAINT ck_order_items_offer_provenance "
        "CHECK ((offer_name IS NULL) = (list_unit_price IS NULL))"
    ))

    # ── Row-Level Security (second line of defense; app-layer filter is first) ─
    for table in ("offer_windows", "offer_window_products"):
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(
            f"CREATE POLICY tenant_isolation ON {table} "
            "USING (restaurant_id = current_setting('app.current_restaurant_id', TRUE)::uuid)"
        ))


def downgrade() -> None:
    for table in ("offer_window_products", "offer_windows"):
        op.execute(sa.text(f"DROP POLICY IF EXISTS tenant_isolation ON {table}"))
        op.execute(sa.text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))

    op.execute(sa.text(
        "ALTER TABLE order_items DROP CONSTRAINT IF EXISTS ck_order_items_offer_provenance"
    ))
    op.execute(sa.text(
        "ALTER TABLE order_items DROP CONSTRAINT IF EXISTS ck_order_items_list_price_non_negative"
    ))
    op.drop_column("order_items", "list_unit_price")
    op.drop_column("order_items", "offer_name")

    op.execute(sa.text("DROP TABLE IF EXISTS offer_window_products CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS offer_windows CASCADE"))
    op.execute(sa.text("DROP TYPE IF EXISTS offer_applies_to"))
    op.execute(sa.text("DROP TYPE IF EXISTS offer_discount_type"))
