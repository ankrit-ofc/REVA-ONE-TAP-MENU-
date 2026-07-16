# CLAUDE.md — Standing Instructions

> Claude Code reads this file at the start of **every** session and treats it as
> binding. It contains the rules that apply to all phases. Phase prompts add
> scope and contracts; they never relax anything below.

---

## 1. What we are building

A **multi-tenant restaurant QR-ordering + POS SaaS**.

- One application instance serves many restaurants ("tenants").
- Customers order by scanning a QR (no login). Staff log in with credentials.
- Roles: `SUPERADMIN`, `ADMIN`, `KITCHEN`, `WAITER`, `COUNTER`, plus `CUSTOMER` (sessionless-login).

**Stack (do not substitute without being asked):**

| Layer | Choice |
|---|---|
| Frontend | React + TypeScript (strict mode) |
| Backend | FastAPI (Python 3.12) |
| DB | PostgreSQL 17 |
| ORM / migrations | SQLAlchemy 2.x + Alembic |
| Realtime | WebSockets |
| Staff auth | JWT (access + rotating refresh) |
| Customer auth | Temporary signed table sessions |
| Validation | Pydantic v2 (backend), Zod (frontend) |
| Packaging | Docker + Docker Compose |

Read `docs/BUILD_PLAN.md` for the phase map and `docs/ARCHITECTURE.md` for the domain model.

---

## 2. Security philosophy (the prime directives)

1. **Never trust the frontend.** It is a UX convenience, not an authority.
2. **Backend is the source of truth.** All rules are enforced server-side.
3. **The database rejects impossible states.** Constraints are not optional.
4. **Every tenant-owned query is tenant-scoped.** No exceptions.
5. **Every critical action is auditable.**
6. **Preserve history.** Soft-delete, never hard-delete business records.
7. **Assume the attacker uses Postman/Burp.** Any field the client sends can be
   forged, replayed, reordered, or omitted. Validate accordingly.

These are tested, not trusted. See §9.

---

## 3. STANDING INVARIANTS (apply to every phase, never re-stated in prompts)

Treat a violation of any of these as a build failure, even if a phase prompt
doesn't mention it.

### Tenancy
- Every tenant-owned table has a `restaurant_id` column, `NOT NULL`, FK to `restaurants`.
- **Never fetch a tenant-owned record by primary key alone.** Always
  `WHERE id = :id AND restaurant_id = :current_restaurant_id`.
- The current `restaurant_id` is derived **server-side** from the JWT (staff) or
  the table session (customer). It is **never** read from a request body, query
  param, or header the client controls.
- Use the shared tenant-scoping dependency/helper — do not hand-roll the filter
  per endpoint.
- PostgreSQL Row-Level Security is enabled on tenant tables as a second line of
  defense (see Phase 1). App-layer filtering is still mandatory; RLS is the net.

### Authorization
- RBAC is enforced on **every** protected endpoint via the shared dependency.
- Hiding a button in the UI is never authorization.
- Permission is checked **before** any state change or write.

### Money
- All monetary values use `NUMERIC`/`Decimal`. **`FLOAT` for money is forbidden.**
- Currency is per-restaurant (from settings); never assume a default.

### History & deletes
- Soft delete via `is_active` (or `deleted_at`). **No `DELETE` on** users,
  categories, products, tables, orders, order items, invoices, audit logs.
- Historical financial/order data is immutable once written. Use the snapshot
  pattern (Phase 5): order items copy product name/price/tax/addon prices at
  order time; later product edits never alter past orders.

### Audit logging
- Every state transition and every privileged write emits an `audit_logs` row:
  `actor`, `entity_type`, `entity_id`, `action`, `previous_value`, `new_value`,
  `timestamp`, optional `reason`. Overrides/reopens **require** a reason.

### Concurrency
- Wrap multi-step critical operations (order append, invoice generation, payment
  completion, table closure, any state transition) in a DB transaction.
- Lock contended rows with `SELECT ... FOR UPDATE`. Commit only after all steps
  succeed; roll back on any failure.

### Identifiers
- Internal PKs are UUIDs (no sequential enumeration).
- User-facing identifiers are human-readable sequences (e.g. order `#102`,
  invoice `INV-2026-001`), generated under a row lock per restaurant. Never show
  UUIDs to end users.

### Input
- Validate **every** request body, query, and path param with Pydantic v2.
- Reject unexpected/extra fields (`model_config = ConfigDict(extra="forbid")`).
- Enforce min/max lengths and numeric bounds; restrict enums to allowed values.
- Cap free-text fields (special instructions, names) at a sane max length.

### File uploads (product images)
- Validate by **content (magic bytes), not extension**; allow only
  jpeg/png/webp. Enforce max file size and max dimensions; strip EXIF metadata.
- Store under a server-generated **UUID filename**, tenant-scoped path; never
  trust or reuse the client filename. Serve via a controlled URL, never a raw
  client path. `products.image_url` is set by the backend, never by the client.

### Money & currency
- Default market is **Nepal**; currency is **NPR**, stored per-restaurant in
  settings. Payment methods: CASH, CARD, COUNTER_WALLET (eSewa/Khalti),
  QR_GATEWAY (Fonepay/online), MANUAL_OVERRIDE. There is **no UPI** in Nepal.

### Database access
- The app connects as a **restricted** DB role, never `postgres`/superuser.
- Grant least privilege; no `DROP`/`CREATE`/`SUPERUSER` for the app role.

---

## 4. Conventions

- **Backend layout:** `app/api/` (routers), `app/services/` (business logic),
  `app/models/` (SQLAlchemy), `app/schemas/` (Pydantic), `app/core/`
  (config, security, deps), `app/db/`, `alembic/`.
- **Frontend layout:** follow `docs/FRONTEND_STRUCTURE.md` exactly — feature
  folders (`features/<x>/{xApi.ts, xSlice.ts, useX.ts}`), Redux Toolkit + RTK
  Query, axios client in `services/api.ts`. **TypeScript only** (`.tsx`/`.ts`,
  strict mode) — never `.jsx`/`.js`, even though the original sketch used them.
- Business logic lives in **services**, not in routers and not in models.
- Pydantic schemas are the API contract. SQLAlchemy models are the persistence
  contract. They are separate types — never return ORM models directly.
- All datetimes are timezone-aware UTC in storage; display tz is per-restaurant.
- Config and secrets come from environment variables only. **Never commit
  secrets.** No hardcoded keys, passwords, or signing secrets anywhere.
- Type hints everywhere (backend) and `strict: true` (frontend tsconfig).
- One concern per file; keep files focused.

---

## 5. What NOT to do (default exclusions — every phase)

- Do **not** add features not named in the current phase prompt.
- Do **not** scaffold auth, Docker, CI, READMEs, or logging frameworks unless the
  phase prompt asks for them.
- Do **not** refactor or touch files outside the phase's named scope.
- Do **not** add new dependencies without listing them and getting approval — see §6.
- Do **not** weaken any invariant in §3 for convenience.
- Do **not** write tests unless the phase asks (each phase specifies its tests).
- Do **not** hard-delete anything.
- Do **not** use `dangerouslySetInnerHTML`, `eval`, raw SQL string interpolation,
  or `FLOAT` money — ever.

## 6. ASK-BEFORE triggers (stop and ask; do not guess)

Stop and ask the human before proceeding if a task would require any of:
- Changing the database schema in a way not specified by the current phase.
- Adding, removing, or version-bumping a dependency.
- Changing anything about authentication, token handling, or the tenancy model.
- Changing a public API contract (route, request/response schema) defined in a
  previous phase.
- Introducing a destructive migration (drop/rename column or table, data loss).
- Anything that would touch how money or payments are calculated or recorded.

When unsure, prefer asking over assuming. State the ambiguity and the options.

---

## 7. Workflow per session

1. Read this file, `docs/BUILD_PLAN.md`, and any phase-referenced docs first.
2. Confirm the phase's scope and out-of-scope list back to the human in one line.
3. Build only what the phase names.
4. Run the phase's acceptance commands and **paste the real output**.
5. Stop. Do not start the next phase.

## 8. Definition of Done (every phase)

A phase is done only when **all** of these hold:
- [ ] All files in the phase scope exist and nothing outside scope changed.
- [ ] `alembic upgrade head` succeeds (if the phase touched the schema).
- [ ] The phase's functional acceptance commands pass with output shown.
- [ ] The phase's **security** acceptance commands pass with output shown (§9).
- [ ] No new unpinned dependency was added.
- [ ] Every new privileged write/transition emits an audit log (where applicable).
- [ ] A commit is ready with message `phase-N: <summary>`.

## 9. Security acceptance is mandatory, not optional

Functional tests prove it works for honest users. **Security tests prove it
holds against an attacker with curl/Burp.** Every phase that exposes an endpoint
must demonstrate, with real command output, at least the relevant subset of:

- A request with a **tampered/expired/missing** token is rejected (401/403).
- A request for **another tenant's resource** is rejected (404/403, never leaks).
- A request with **extra/unexpected fields** or out-of-range values is rejected (422).
- An **illegal state transition** is rejected.
- A **replayed** idempotent operation (payment/webhook) does not double-apply.

If a security check can't be demonstrated yet (dependency not built), say so
explicitly rather than skipping silently.
