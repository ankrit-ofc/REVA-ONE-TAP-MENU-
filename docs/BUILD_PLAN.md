# Build Plan — Restaurant QR Ordering SaaS

This is the authoritative sequence for building the system with Claude Code, one
phase per session. Each phase is independently buildable and testable, and builds
only on what came before. Read alongside `CLAUDE.md`.

## Sequencing principle

Build **bottom-up**: the database enforces truth first, then the security spine,
then domains, then the risky money/realtime layers, then the UI, then hardening.
A bug in a lower layer is cheap to fix early and expensive to fix after six
layers sit on top of it.

```
0 Scaffold ─► 1 Schema ─► 2 Auth+Tenancy ─► 3 QR/Sessions ─► 4 Menu
                                                                │
        10 Hardening ◄─ 9 Frontend ◄─ 8 Realtime ◄─ 7 Payments ◄─ 6 Roles ◄─ 5 Ordering
```

---

## Decision points (defaults chosen — override if you disagree)

| # | Decision | Default | Rationale |
|---|---|---|---|
| D1 | Staff token storage | Access token in memory + refresh token in `HttpOnly; Secure; SameSite=Strict` cookie; CSRF via custom header / double-submit | Survives page refresh without `localStorage` XSS exposure; better than pure in-memory for an all-shift POS. |
| D2 | Payment gateway (**Nepal**) | Adapter interface; **eSewa + Khalti** reference impls, **Fonepay** (NepalPay QR) for the scan-to-pay flow; currency **NPR** | Nepal market. eSewa ePay v2 uses HMAC-SHA256 signing; Khalti uses key + server-side payment lookup/verification; Fonepay covers interoperable QR. Adapter keeps each swappable. |
| D3 | Tenant isolation | App-layer scoping **+ PostgreSQL RLS** | RLS is the safety net for the day a developer forgets the `.filter()`. |
| D4 | One active order/table | DB **partial unique index** + app check | Makes the impossible state impossible at the storage layer. |
| D5 | QR token | Signed token (restaurant_id + table_id), exchanged at `/scan` for a session | QR is static/printable; it grants only a session, not order rights directly. |
| D6 | Per-restaurant sequence numbers | `restaurant_counters` table incremented under `FOR UPDATE` | Gapless, tenant-scoped, race-safe order/invoice numbers. |
| D7 | Money type | `NUMERIC(12,2)` (NPR has 2 decimal paisa) | Per the blueprint; exact decimal arithmetic. |
| D8 | Product images | Upload validated (type, magic bytes, size, dimensions), EXIF stripped, stored under a UUID filename in **object storage** (Azure Blob / S3 / Cloudinary), served via a controlled URL; tenant-scoped path | Untrusted file uploads are a top web risk; this satisfies the checklist's "sanitize uploaded filenames and metadata." Local volume is an acceptable V1 fallback if you don't want a bucket yet. |
| D9 | `payment_method` enum (**Nepal fix**) | Replace blueprint's `COUNTER_UPI` with `COUNTER_WALLET` (eSewa/Khalti at counter); keep `CASH`, `CARD`, `QR_GATEWAY` (Fonepay/online), `MANUAL_OVERRIDE` | UPI is India-only and doesn't exist in Nepal; wallet/QR are the local equivalents. |

If you want different choices, tell me and I'll adjust the affected phase prompts.

---

## Phase 0 — Scaffold & foundations

**Adds:** a running, empty, secure shell. Docker Compose (Postgres + backend +
frontend placeholders), FastAPI app with `/health`, SQLAlchemy engine + session,
Alembic initialized, env-based config, a restricted DB role created in init SQL,
`CLAUDE.md` + `docs/` committed.
**No** models, no auth, no business logic.
**Done when:** `docker compose up` works, `GET /health` → 200, `alembic upgrade
head` runs against an empty revision, app connects as the non-superuser role.

## Phase 1 — Database schema & migrations

**Adds:** every table from the conceptual model with full integrity:
- `restaurants`, `users`, `restaurant_settings`, `categories`, `products`,
  `product_variants`, `product_addons`, `product_addon_mappings`, `tables`,
  `table_sessions`, `orders`, `order_items`, `order_item_addons`, `invoices`,
  `audit_logs`, `restaurant_counters`.
- UUID PKs; `restaurant_id` FK + `NOT NULL` on all tenant tables.
- ENUMs for every state machine (order, order item, invoice, payment method, role).
- CHECK constraints (`quantity > 0`, `discount >= 0`, prices `>= 0`).
- UNIQUE / composite UNIQUE (`UNIQUE(email, restaurant_id)`,
  `UNIQUE(gateway_transaction_id)`), partial unique index for one-active-order.
- `NUMERIC` money columns; timestamps; `is_active`/`deleted_at` soft-delete cols;
  snapshot columns on `order_items`.
- RLS policies enabled on tenant tables.
- SQLAlchemy models + first real Alembic migration.
**No** endpoints, no business logic.
**Done when:** migration applies; inserting a bad row (qty 0, FLOAT-ish money,
duplicate active order, cross-tenant FK) is rejected by the DB — shown with SQL.

## Phase 2 — Auth + tenancy core (staff)

**Adds:** Argon2 hashing; JWT access tokens (short-lived) + rotating refresh
tokens (cookie per D1); `get_current_user`, `require_role(...)`, and
`tenant_scope` dependencies; `POST /auth/login`, `/auth/refresh`, `/auth/logout`;
one trivial role-guarded probe endpoint to test the spine.
**Out of scope:** any business domain.
**Done when:** login issues tokens; the probe endpoint rejects missing/expired/
tampered JWT (401) and wrong role (403); tenant dependency yields the
JWT-derived `restaurant_id`, ignoring any client-sent value.

## Phase 3 — QR codes & table sessions (customer)

**Adds:** signed QR token format + generator; `POST /scan` (validates QR sig →
creates `TableSession` with non-guessable token, expiry, single-active-per-table);
`get_current_session` dependency; session invalidation; "table_id derived from
session, never from client."
**Done when:** forged/expired QR rejected; expired/invalidated session rejected;
a customer request that tries to pass its own `table_id` is ignored in favor of
the session binding.

## Phase 4 — Menu domain (admin CRUD)

**Adds:** tenant-scoped CRUD for categories, products, variants, addons, mappings,
availability toggle, tax rate, restaurant settings. **Secure product-image upload**
(per D8): validate MIME + magic bytes + size + dimensions, strip EXIF, store under
a UUID filename in object storage, serve via a controlled URL, tenant-scoped path.
Customer-facing read that hides unavailable/inactive items. Soft delete. Full
Pydantic validation.
**Done when:** CRUD works tenant-scoped; cross-tenant read/write denied;
unavailable products absent from the customer menu but still referenceable by
historical orders; uploading a disguised non-image (e.g. a script renamed `.jpg`)
is rejected, and an over-size/over-dimension image is rejected.

## Phase 5 — Ordering core (the heart)

**Adds:** create/append order; `OrderItem` creation that **snapshots** product
name/variant/unit price/tax/addon prices; one-active-order-per-table enforced;
order state machine (`OPEN → MEAL_FINISHED → CLOSED`, guarded `MEAL_FINISHED →
OPEN` reopen requiring permission + reason); order-item state machine
(`NEW → PREPARING → READY → SERVED`, `NEW → CANCELLED` only pre-prep);
`SELECT ... FOR UPDATE` on append/transitions; audit logs on every transition.
**Done when:** illegal transitions rejected; two concurrent appends don't create
two active orders; a product price change after ordering does not alter the
order's snapshot; closed orders reject modification.

## Phase 6 — Role workflow endpoints

**Adds:** kitchen queue + `NEW→PREPARING→READY`; waiter `READY→SERVED` + mark
meal finished + optional reopen; counter actions. All RBAC-gated transitions over
Phase 5's machine, each emitting audit logs with actor/prev/new.
**Done when:** each role can perform only its own transitions; others get 403;
audit trail complete.

## Phase 7 — Invoices & payments (highest risk)

**Adds:** invoice generation separate from order (multiple per order); invoice
state machine (`DRAFT → PENDING_PAYMENT → PAID|FAILED|VOID`, `PAID → REFUNDED`);
payment methods (CASH/CARD/COUNTER_UPI/QR_GATEWAY/MANUAL_OVERRIDE); gateway
webhook with **signature verification + idempotency keys + duplicate-payment
prevention**; fallback flow (gateway fail → counter collects → new invoice);
close order + reset table on paid — all under transaction + row locks.
**Done when:** forged webhook signature rejected; replayed webhook is idempotent
(no double payment); a failed payment creates a new invoice without corrupting
the order; manual override is audited with a reason.

## Phase 8 — Realtime (WebSockets)

**Adds:** authenticated WS endpoints (staff via JWT, customer via session token);
tenant-scoped channels; broadcast on new order, item state changes, order
close. No new business rules — it observes Phase 5–7 events.
**Done when:** unauthenticated WS connection rejected; events scoped to the
correct restaurant only; kitchen receives a new-order event on order create.

## Phase 9 — Frontend (sub-sessions)

Follows **`docs/FRONTEND_STRUCTURE.md`** (your `react_layout`, adapted to
TypeScript + the real surfaces). Each surface is its own Claude Code session,
sharing infra built in 9a:

- **9a Shared infra:** `services/api.ts` (axios, in-memory access token, refresh
  interceptor per D1), router + `RequireRole`, Redux store, RTK Query base, Zod
  schemas mirroring backend contracts, shared types, WS client. No `localStorage`
  JWTs; no `dangerouslySetInnerHTML`.
- **9b Customer (highest design priority):** scan → menu (with product images) →
  product detail (variants/addons/special instructions) → cart → place/append →
  live order status → request bill. Mobile-first, non-technical user, fast.
- **9c Kitchen display:** live queue, NEW→PREPARING→READY.
- **9d Waiter:** ready items, serve, finish, reopen.
- **9e Counter:** invoice, payment (eSewa/Khalti/Fonepay/cash), fallback, close.
- **9f Admin:** menu/staff/tables/settings management, image upload UI.
- **9g Superadmin:** restaurant + subscription management, analytics.

**Done per surface when:** UI calls only real backend contracts; role guards are
UX-only (backend already enforces); inputs are Zod-validated and length-capped;
the customer flow is usable one-handed on a phone. Build with the
`frontend-design` skill for visual quality, not default-template look.

## Phase 10 — Hardening & cross-cutting

**Adds:** rate limiting (login attempts, QR scans, orders/session, session
creation, special-instruction submissions); security headers; strict CORS;
structured request logging (no secrets/PII leakage); dependency pinning + audit;
basic CI (lint, type-check, tests, migration check).
**Done when:** rate limits return 429 when exceeded; headers present; CI runs
green on a clean checkout.

---

## Out of scope for V1 (do not let Claude Code add these)

Inventory, ingredients, suppliers, reservations, nested categories, coupon
engines, loyalty, push notifications, advanced accounting, ERP features.
