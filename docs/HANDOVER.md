# HANDOVER.md — Owning and operating this codebase

You are taking over a multi-tenant restaurant QR-ordering + POS SaaS.
Read `CLAUDE.md` (binding engineering rules) and `docs/BUILD_PLAN.md` first.
This file covers day-to-day operation: version control, running the stack,
adding features, migrations, and deploying.

---

## 1. Push this folder to your own repo (do this first, once)

This is an independent repo under your account — no link to the original.

1. On GitHub: create a new **empty** repo (no README, no .gitignore).
2. In PowerShell from the project root:

```powershell
git init -b main
git add -A
git status                  # verify backend/.env and frontend/.env are NOT listed
git commit -m "initial commit"
git remote add origin https://github.com/<your-username>/<your-repo>.git
git push -u origin main
```

Sanity checks before that first push:

- `git status` must NOT list `backend/.env`, `frontend/.env`, `backend/.venv/`,
  `frontend/node_modules/`, or `backend/media/`. The `.gitignore` already
  covers these — if any appear, stop and check.
- Don't commit `resturants.png` (7.9 MB) unless it's actually used.

## 2. Daily push workflow

1. `git checkout -b feat/<short-name>` — never work directly on `main`.
2. Make changes, commit in small logical units. Message style: `phase-N: <summary>`
   for phase work, or `feat:/fix:/docs: <summary>` otherwise.
3. `git push -u origin feat/<short-name>` and open a PR into `main`.
4. CI (`.github/workflows/ci.yml`) runs on `main`: Alembic migrate + pip-audit
   (backend), tsc + eslint + build + npm audit (frontend). npm audit **fails on
   high/critical** — run `npm audit` locally before pushing frontend changes.
5. Merge only when CI is green.

## 3. Running the stack locally

```powershell
docker compose up            # Postgres 17, backend (reload), Vite frontend, Caddy, model-converter
```

- Backend needs `backend/.env` (exists; template in `backend/.env.example`).
- Frontend needs `frontend/.env` (`VITE_API_BASE_URL`).
- App via Caddy (HTTPS, for PWA/QR testing) or Vite directly on :3000.
- First-boot DB creates the restricted role from `db/init/01_roles.sql`.
- First SUPERADMIN is created manually — see `docs/app_add_superadmin_setup.txt`.

## 4. Adding a feature safely (checklist)

The invariants in `CLAUDE.md` §3 are non-negotiable. Per feature:

1. **Scope**: business logic in `app/services/`, HTTP in `app/api/`, contracts
   in `app/schemas/`. Frontend: feature folder per `docs/FRONTEND_STRUCTURE.md`.
2. **Tenancy**: every tenant-owned query filters by `restaurant_id` via the
   shared `tenant_scope` dependency. Never trust client-sent restaurant IDs.
3. **Auth**: `require_role(...)` on every protected endpoint. Frontend route
   guards are UX only.
4. **Money**: `NUMERIC`/`Decimal` only. Never float.
5. **Validation**: Pydantic v2 with `extra="forbid"`, bounds, max lengths.
6. **History**: soft-delete only; snapshot prices/names into order items.
7. **Audit**: privileged writes and state transitions emit `audit_logs` rows.
8. **Concurrency**: multi-step ops in a transaction with `SELECT ... FOR UPDATE`.
9. **Schema change?** Add an Alembic migration (next number, current head as
   `down_revision`), then `alembic upgrade head` against a scratch DB.
10. **Prove security, not just function** (`CLAUDE.md` §9): tampered token → 401,
    other tenant's resource → 404, extra fields → 422, illegal transition
    rejected, replayed payment not double-applied.

## 5. Migrations

- Files: `backend/alembic/versions/`, linear chain `001` → `0018`.
- New migration: `alembic revision -m "<what>"` inside the backend container,
  set `down_revision` to the current head.
- Never edit an applied migration; add a new one.
- Destructive changes (drop/rename column) require explicit sign-off — see
  `CLAUDE.md` §6.

## 6. Deploying

- Prod: `docker-compose.prod.yml` + `deploy.sh` on the server — see
  `docs/DEPLOY.md`. `deploy.sh` now takes an automatic `pg_dump` backup
  (step 0, keeps the 7 most recent in `backups/`), then pulls, builds,
  migrates, and brings the stack up. There is **no CD pipeline** — deploys
  are manual SSH.
- Only Caddy's 80/443 are public; DB binds to host loopback only.

### Safe-deploy checklist (production data protection)

Data lives in named volumes (`postgres_data`, `media_data`) and survives every
rebuild/restart. Per deploy:

1. Confirm you are SSHed into **your** server (`hostname` / prompt check).
2. CI is green on `main` — migrations already passed against a fresh DB.
3. Run `./deploy.sh` — it backs up the DB automatically before anything else.
4. After: `docker compose -f docker-compose.prod.yml ps` (all up) + hit
   `/health` + one real page load.

**Never run on production:** `docker compose down -v` (deletes the data
volumes — the ONLY compose command that destroys data), or any destructive
migration without a rehearsal against a restored backup copy first.

**Restore procedure** (worst case):
`gunzip -c backups/pre_deploy_<ts>.sql.gz | docker compose -f docker-compose.prod.yml exec -T db psql -U postgres -d multi_tenant_qr_resturant`

## 7. Secrets — rotate these now

This codebase circulated as a zip **with live `.env` files inside**. Treat all
of these as compromised and rotate before/at next deploy:

- `SECRET_KEY` (invalidates all staff JWTs), `QR_SECRET` (reprint table QRs)
- `POSTGRES_PASSWORD`, `APP_DB_PASSWORD`
- `KHALTI_SECRET_KEY`, `FONEPAY_SECRET_KEY`, `ESEWA_SECRET_KEY` (prod values)
- SMTP credentials, `FAL_KEY`, `ANTHROPIC_API_KEY` if set

Never commit `.env`. Update `.env.example` (names only) when adding new vars.

## 8. Known issues (July 2026 code review) — status

Hardening pass completed 2026-07-16. FIXED items name the branch and commit
that resolved them.

1. **No automated tests** — ✅ FIXED (`chore/tests` @ `917ef5b` baseline;
   `test/payments-and-transitions` @ `8435d43` payments). pytest + httpx suite
   against a dedicated `<dbname>_test` database, wired into CI (`tests` job,
   postgres:17 service). See "Current test suite" below.
2. **Rate limiting broken behind the proxy** — ✅ FIXED
   (`fix/rate-limit-proxy` @ `8ccbfce`). uvicorn runs `--proxy-headers
   --forwarded-allow-ips 172.16.0.0/12` (dev compose + prod Dockerfile), and
   `limiter.py` keys on the real client IP: X-Forwarded-For is honoured only
   from trusted proxy peers (`TRUSTED_PROXY_IPS`), rightmost entry; spoofed
   headers on direct connections are ignored.
3. **Staff hard-delete** — ✅ FIXED (`fix/staff-soft-delete` @ `6847fac`).
   Deletion is now `is_active=False` for every role, audited
   (`STAFF_DEACTIVATED`); migration `0019` replaces the users unique
   constraint with a partial unique index on active rows so the email frees up.
4. **eSewa sandbox key as code default** — ✅ FIXED (`fix/prod-config-guard`
   @ `022ad81`). Gateway defaults are empty (empty = disabled); with
   `ENVIRONMENT=production` the app refuses to boot on partial gateway config,
   the known eSewa sandbox credentials, missing SECRET_KEY/QR_SECRET, or
   localhost in ALLOWED_ORIGINS.
5. **Fonepay signature field order unconfirmed** (`payments/fonepay.py`) —
   ⚠️ STILL OPEN: verify against merchant docs + golden-vector test before
   taking prod payments.
6. **Customer AR is still the pizza-model spike** (`features/ar/modelPrefetch.ts`)
   — ⚠️ STILL OPEN.
7. **WS tokens in query strings** — ✅ FIXED (`fix/auth-hardening` @
   `dd1a72d`). WebSockets accept only 60-second single-use tickets
   (`POST /auth/ws-ticket` / `POST /session/ws-ticket`); raw
   `?token=`/`?session_token=` params are rejected with close code 1008.
8. **`deps.py` loads users by PK alone** — ✅ FIXED (`fix/auth-hardening` @
   `dd1a72d`). `get_current_user` cross-checks the JWT's `restaurant_id`
   claim against the loaded user's tenant; mismatch or missing claim → 401.
9. **Docs drift**: `docs/SCHEMA.md` is behind migrations 0004–0019 (stale
   banner added; still needs regeneration). Postgres-16 references, root
   `README.md`, and root `package.json` were fixed/removed in the repo
   cleanup (2026-07-16). ⚠️ SCHEMA.md regeneration still open.
10. **Split the mega-services** (`order_service.py` 1056 lines,
    `menu_service.py` 1007, `payment_service.py` 972) — ⚠️ STILL OPEN.

### Current test suite (38 tests, `backend/tests/`)

Runs via `python -m pytest tests` in the backend container (deps in
`requirements-dev.txt`) and in CI against a postgres:17 service. Fixtures
rebuild a dedicated `<dbname>_test` database from the full migration chain —
the dev database is never touched. Coverage:

- `test_security_baseline.py` (7) — missing/tampered/expired JWT → 401,
  cross-tenant fetch → 404 without leaking, extra fields → 422, login rate
  limit → 429, customer endpoints demand X-Session-Token.
- `test_rate_limit_proxy.py` (2) — independent buckets per X-Forwarded-For
  client behind a trusted proxy; spoofed headers on direct connections don't
  mint fresh buckets.
- `test_staff_soft_delete.py` (2) — deactivate → login + old JWT fail → email
  reusable → audit row; self-deletion blocked.
- `test_prod_config_guard.py` (9) — production boot refusals (missing/partial/
  sandbox gateway config, localhost origins, blank secrets); dev unaffected.
- `test_ws_tickets.py` (8) — ticket connect + tenant bucket isolation;
  expired/reused/garbage/legacy-token connections rejected; JWT tenant-claim
  checks.
- `test_payments_and_transitions.py` (10) — payment idempotency, illegal
  state transitions (with audit rows verified for every legal transition),
  eSewa/Fonepay/Khalti webhook replay without double-credit, Decimal-only
  money end-to-end, order-item snapshot immutability.

---

*Generated 2026-07-16 during codebase handover review.*
