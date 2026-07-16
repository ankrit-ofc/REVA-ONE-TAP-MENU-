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

- Prod: `docker-compose.prod.yml` + `deploy.sh` on the Vultr box — see
  `docs/DEPLOY.md`. `deploy.sh` pulls, builds frontend, runs migrations, brings
  the stack up. There is **no CD pipeline** — deploys are manual SSH.
- Only Caddy's 80/443 are public; DB binds to host loopback only.

## 7. Secrets — rotate these now

This codebase circulated as a zip **with live `.env` files inside**. Treat all
of these as compromised and rotate before/at next deploy:

- `SECRET_KEY` (invalidates all staff JWTs), `QR_SECRET` (reprint table QRs)
- `POSTGRES_PASSWORD`, `APP_DB_PASSWORD`
- `KHALTI_SECRET_KEY`, `FONEPAY_SECRET_KEY`, `ESEWA_SECRET_KEY` (prod values)
- SMTP credentials, `FAL_KEY`, `ANTHROPIC_API_KEY` if set

Never commit `.env`. Update `.env.example` (names only) when adding new vars.

## 8. Known issues to fix (priority order)

From the July 2026 code review — verified against source:

1. **No automated tests** despite `CLAUDE.md` §9 mandating security acceptance.
   Add pytest + httpx suites (auth, cross-tenant 404, payment idempotency,
   illegal transitions) and wire into CI. Do this before feature work — it's
   your safety net for everything else.
2. **Rate limiting is broken behind the proxy**: `limiter.py` keys on direct
   remote address and uvicorn runs without `--proxy-headers`, so behind Caddy
   all clients share one bucket. Fix: uvicorn `--proxy-headers
   --forwarded-allow-ips` (backend network) or key off `X-Forwarded-For` from
   trusted proxy only.
3. **Staff hard-delete** (`staff_service.py:149`) violates the soft-delete
   invariant. Switch to `is_active=False`; free the email with a partial unique
   index on active rows.
4. **eSewa sandbox key is the code default** (`config.py:36`). Make it empty and
   fail fast at startup when `ENVIRONMENT=production` and gateway keys are unset.
5. **Fonepay signature field order unconfirmed** (`payments/fonepay.py`) —
   verify against merchant docs + golden-vector test before taking prod payments.
6. **Customer AR is still the pizza-model spike** (`features/ar/modelPrefetch.ts`)
   and the referenced `public/models/*` assets are missing.
7. **WS tokens ride in query strings** (`api/ws.py`) — move to first-message
   auth or short-lived tickets when convenient.
8. **`deps.py:62` loads users by PK alone** — add a `restaurant_id` cross-check
   after JWT decode.
9. **Docs drift**: `docs/SCHEMA.md` is behind migrations 0004–0018; docs say
   Postgres 16, stack runs 17; root `README.md` and root `package.json` are
   stale — regenerate/delete.
10. **Split the mega-services** (`order_service.py` 1056 lines,
    `menu_service.py` 1007, `payment_service.py` 972) before they grow further.

---

*Generated 2026-07-16 during codebase handover review.*
