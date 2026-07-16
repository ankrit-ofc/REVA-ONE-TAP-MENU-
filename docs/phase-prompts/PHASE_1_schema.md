PHASE 1 — Database schema & migrations

Context:
- After Phase 0 the app runs and Alembic works against an empty baseline.
- This phase defines the ENTIRE data model with full integrity constraints, so
  the database itself rejects impossible states. SQLAlchemy models + one Alembic
  migration. No endpoints, no business logic.
- Done = migration applies and the DB rejects bad inserts (qty 0, duplicate
  active order, cross-tenant references, etc.), demonstrated with SQL.

Read first: CLAUDE.md (esp. §3 invariants), docs/BUILD_PLAN.md (Phase 1),
docs/ARCHITECTURE.md (domain model). Confirm scope back to me in one line.

Threat model for this phase:
- Assume application code will eventually have bugs that forget a tenant filter
  or attempt an illegal state. The schema is the last line of defense and must
  make those states physically impossible (constraints + RLS).

Scope — build these files and only these:
- backend/app/models/*.py: one module per aggregate, all importing the shared Base.
- backend/app/models/enums.py: Python enums mirrored to PG ENUM types.
- backend/alembic/versions/<rev>_initial_schema.py: the migration creating all
  tables, constraints, indexes, ENUM types, and RLS policies.
- docs/SCHEMA.md: a short table-by-table reference (columns, constraints) kept in
  sync with the models.

Data contracts — create these tables (UUID PK `id` on all; `created_at`,
`updated_at` timestamptz on all unless noted). Tenant tables marked [T] carry
`restaurant_id UUID NOT NULL REFERENCES restaurants(id)`:

- restaurants: name, slug UNIQUE, is_active bool default true.
- users [T]: email, password_hash, role (ENUM role), is_active;
  UNIQUE(email, restaurant_id).
- restaurant_settings [T]: enable_qr_payment bool, waiter_can_accept_payment bool,
  allow_order_reopen bool, currency char(3), timezone text; UNIQUE(restaurant_id).
- categories [T]: name, display_order int, is_active.
- products [T]: category_id FK, name, base_price NUMERIC(12,2) CHECK(>=0),
  tax_rate NUMERIC(5,2) CHECK(>=0), is_available bool, is_active, has_variants
  bool, allows_addons bool, image_url text NULL (controlled URL set by Phase 4
  upload; never a client-supplied raw path).
- product_variants [T]: product_id FK, name, price NUMERIC(12,2) CHECK(>=0),
  is_active.
- product_addons [T]: name, price NUMERIC(12,2) CHECK(>=0), is_active.
- product_addon_mappings [T]: product_id FK, addon_id FK;
  UNIQUE(product_id, addon_id).
- tables [T]: name, is_active; UNIQUE(name, restaurant_id).
- table_sessions [T]: table_id FK, token (unique, indexed), status (ENUM
  session_status), expires_at timestamptz, invalidated_at timestamptz NULL.
- orders [T]: table_id FK, order_number int (human-readable, per restaurant),
  status (ENUM order_status), UNIQUE(restaurant_id, order_number).
- order_items [T]: order_id FK, product_id FK (reference only), status (ENUM
  order_item_status), quantity int CHECK(>0), special_instructions varchar(500)
  NULL; SNAPSHOT cols: product_name, variant_name NULL, unit_price NUMERIC(12,2),
  tax_rate NUMERIC(5,2); timestamps: created_at, preparing_at, ready_at, served_at.
- order_item_addons [T]: order_item_id FK; SNAPSHOT cols: addon_name,
  addon_price NUMERIC(12,2).
- invoices [T]: order_id FK, invoice_number text (per restaurant),
  status (ENUM invoice_status), payment_method (ENUM payment_method) NULL,
  subtotal/discount/tax_total/total NUMERIC(12,2) CHECK(>=0),
  gateway_transaction_id text NULL UNIQUE; UNIQUE(restaurant_id, invoice_number).
- audit_logs [T]: actor_user_id NULL, actor_type text, entity_type text,
  entity_id UUID, action text, previous_value jsonb NULL, new_value jsonb NULL,
  reason text NULL, created_at timestamptz. (Append-only; no updates/deletes.)
- restaurant_counters [T]: counter_type text, current_value int;
  UNIQUE(restaurant_id, counter_type). (Used later for gapless numbering.)

ENUMs:
- role: SUPERADMIN, ADMIN, KITCHEN, WAITER, COUNTER
- order_status: OPEN, MEAL_FINISHED, CLOSED
- order_item_status: NEW, PREPARING, READY, SERVED, CANCELLED
- invoice_status: DRAFT, PENDING_PAYMENT, PAID, FAILED, VOID, REFUNDED
- payment_method: CASH, CARD, COUNTER_WALLET, QR_GATEWAY, MANUAL_OVERRIDE
  (Nepal fix per D9: blueprint's COUNTER_UPI is renamed COUNTER_WALLET —
  eSewa/Khalti at the counter. UPI does not exist in Nepal.)
- session_status: ACTIVE, EXPIRED, INVALIDATED

Critical constraints / indexes:
- Partial unique index enforcing ONE active order per table:
  `CREATE UNIQUE INDEX ... ON orders (table_id) WHERE status IN ('OPEN','MEAL_FINISHED');`
- All money columns NUMERIC (never FLOAT/DOUBLE).
- RLS: enable row-level security on all [T] tables with a policy that filters by
  `restaurant_id = current_setting('app.current_restaurant_id')::uuid`. (Phase 2
  will set that GUC per request; for now just define the policies + enable RLS.)

Specifications:
- Models in SQLAlchemy 2.x typed style (Mapped[...] / mapped_column).
- Soft-delete columns (`is_active` or `deleted_at`) present per CLAUDE.md §3.
- No business logic, no relationships beyond FK + ORM relationship() definitions.

Dependencies to install: none (Phase 0 covers them). If you think you need one,
STOP and ask.

Out of scope for this phase — do NOT touch / add:
- No routers, services, auth, or endpoints.
- No seed data beyond what a migration needs.
- No tests (we verify via SQL in acceptance).

Must not break (regression guard):
- `GET /health` must still return 200; the app must still start.

ASK BEFORE doing any of these (stop and ask, do not guess):
- Adding, renaming, or removing any table/column not listed above.
- Any FLOAT/DOUBLE money column (forbidden — must be NUMERIC).
- (CLAUDE.md §6 ask-before triggers also always apply.)

Functional acceptance — run these and paste the real output:
1. `docker compose exec backend alembic upgrade head`
   Expected: all tables + ENUMs + RLS policies created, no errors.
2. `docker compose exec db psql -U app_user -d <appdb> -c "\dt"`
   Expected: all 16 tables listed.

Security acceptance — run these and paste the real output:
1. Insert with quantity 0:
   `... INSERT INTO order_items (..., quantity) VALUES (..., 0);`
   Expected: rejected by CHECK(quantity > 0).
2. Create a second active order for the same table:
   Expected: rejected by the partial unique index.
3. `... \d+ orders` (or query information_schema)
   Expected: money columns are numeric, NOT float/double.

Definition of done: see CLAUDE.md §8. Then stop — do not start Phase 2.
Stop and ask before deviating from this spec.
