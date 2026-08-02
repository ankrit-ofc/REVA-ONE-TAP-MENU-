# CLAUDE.md — read before any work in this repo

## What this repo is
WEB ADMIN + BACKEND (FastAPI, React web, Caddy). Ships via: merge to main → server `git pull --ff-only` → `bash deploy.sh` → live at revatap.com.
The STAFF MOBILE APP is a separate repo (reva-tap-analysis) shipping via eas build. Staff-phone features do NOT go here.

## Settled decisions — do not reverse without explicit instruction from Ankrit
- Caddy @always_api MUST include /push/* — removing it breaks all staff push registration (405 at the edge).
- _ANDROID_CHANNEL = "staff-v2" MUST match the mobile app's CHANNEL_ID. Changing either alone breaks lock-screen alerts.
- Push messages must send priority: "high" + channelId (push_service.py) — required for screen-off delivery.
- device_tokens must contain only @ank.ofc-project tokens. Mixed-project batches fail entirely (PUSH_TOO_MANY_EXPERIENCE_IDS). Backend still needs a per-project batching fix (pending task).

## Known traps
- NEW TOP-LEVEL BACKEND ROUTE → must be added to Caddy's @always_api path list or @api regex, or it 405s at the edge. This has caused a multi-day outage once already.
- The server (/opt/app) cannot push to GitHub (403). NEVER rely on server-side git push. All changes flow PC → PR → merge → server pulls.
- NEVER git reset --hard on the server unless origin verifiably contains every server commit.
- Backend is a BAKED Docker image: server code changes require `docker compose -f docker-compose.prod.yml up -d --build backend`, not just restart.
- Caddy config is a bind mount (./caddy/prod:/etc/caddy): edit host file, then caddy reload.
- TESTS SHARE A SESSION-SCOPED DATABASE WITH NO ROLLBACK (conftest.py fixtures
  `database` and `seed` are scope="session"; the `client` fixture does not wrap
  a transaction). Every row a test writes persists for the whole run, visible to
  every later test, and files run in alphabetical order. Never assert on
  full-list results for a seeded tenant — filter to the ID you created, or
  create a fresh restaurant inside the test. Neither seed["a"] nor seed["b"] is
  clean by the time later files run. This has already turned CI red once.

## Session rules
- One task per session. Pending items listed at END, never acted on.
- Raw command output as evidence for every claim.
- Diffs before commit. No push/merge/deploy without explicit go.

## Git hygiene — non-negotiable

- **Identity must be configured before committing.** Every machine sets
  `user.name`, `user.email`, and `user.useConfigOnly true` globally. Without
  the last one git silently invents an address from username@hostname, which
  maps to no GitHub account and renders as an unlinked commit. This has already
  cost one cleanup session.
- **Never `git init` on a copy of this repo.** Always `git clone`. An init
  produces unrelated history and squashes real work into one opaque commit;
  recovering requires reconstructing commits by tree.
- **Never commit to local `main`.** Branch first:
  `git switch -c <name> origin/main`. Always `git fetch origin` before branching.
- **`main` is PR-only.** No direct push, no force-push, no deletion. The server
  pulls `--ff-only`, so a rewritten `main` breaks deploys outright.
- **One concern per PR.** A PR bundling migrations, services, and UI is not
  reviewable and will be split.
- **Before pushing, verify the author** with
  `git log --format='%an <%ae>' origin/main..HEAD`. Wrong identity is cheap to
  fix before a PR exists and irritating afterwards.

---

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
- **Widening an endpoint's RBAC requires auditing its response body.** Adding
  roles to `require_role(...)` is not sufficient — every field the endpoint
  returns must be checked against what the newly-admitted roles should see.
  A WAITER-widened GET /admin/tables was caught returning signed
  `qr_token`/`scan_url` in review, before it merged. Trim per-role, and add a
  test asserting the field is absent for
  the lower role, not merely that the status code is 200.

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
