# REVA — One Tap Menu

Multi-tenant restaurant QR-ordering + POS SaaS. One instance serves many
restaurants: customers scan a table QR and order with no login or app install;
staff (kitchen, waiter, counter, admin) run the floor from role-scoped web
dashboards in real time.

## What it does

- **Customers** — scan the table QR → browse the menu (photos, 3D/AR previews)
  → order → track status live → request the bill. No account needed.
- **Kitchen** — live ticket queue (NEW → PREPARING → READY) over WebSockets,
  with optional thermal KOT printing.
- **Waiters** — ready-item board, serve per item, order approval gate,
  "Call Waiter" alerts.
- **Counter** — invoicing, payments (cash / card / eSewa / Khalti / Fonepay),
  idempotent payment capture, customer-facing display.
- **Admin (per restaurant)** — menu, categories, add-ons, tables + QR PDFs,
  staff, settings; product image → AI-generated 3D model pipeline.
- **Superadmin (platform)** — restaurant onboarding and management.

## Stack

| Layer | Choice |
|---|---|
| Frontend | React + TypeScript (strict), Redux Toolkit + RTK Query, Vite |
| Backend | FastAPI (Python 3.12) |
| Database | PostgreSQL 17 (row-level security as tenancy backstop) |
| ORM / migrations | SQLAlchemy 2.x + Alembic |
| Realtime | WebSockets |
| Auth | JWT access + rotating refresh (staff); signed table sessions (customers) |
| Validation | Pydantic v2 (backend), Zod (frontend) |
| Packaging | Docker Compose (Postgres, backend, frontend, Caddy, model-converter) |

## Local development

Prerequisites: Docker Desktop. Copy the env templates and fill them in
(never commit real `.env` files):

```powershell
copy backend\.env.example backend\.env      # secrets, DB, gateways
copy frontend\.env.example frontend\.env    # VITE_API_BASE_URL
```

Then:

```powershell
docker compose up -d                            # full stack
docker compose exec backend alembic upgrade head  # apply migrations
```

- Frontend: http://localhost:3000 (Vite) or https://localhost (Caddy, for PWA/QR testing)
- Backend API: http://localhost:8000 (health check at `/health`)
- First platform SUPERADMIN is created manually — see
  [docs/app_add_superadmin_setup.txt](docs/app_add_superadmin_setup.txt).

CI (GitHub Actions) runs on every push/PR to `main`: Alembic migrate +
pip-audit (backend), tsc + eslint + build + npm audit (frontend).

## Documentation

| Doc | Purpose |
|---|---|
| [CLAUDE.md](CLAUDE.md) | Binding engineering rules: tenancy, RBAC, money, audit, soft-delete invariants |
| [docs/HANDOVER.md](docs/HANDOVER.md) | Day-to-day operation: workflow, migrations, deploys, known issues |
| [docs/TAKEOVER_STEPS.md](docs/TAKEOVER_STEPS.md) | Ownership playbook: secrets rotation → smoke test → production |
| [docs/DEPLOY.md](docs/DEPLOY.md) | Production deploy runbook (Caddy auto-HTTPS, `deploy.sh`) |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) / [docs/BUILD_PLAN.md](docs/BUILD_PLAN.md) | Domain model and phase map |

## Security posture (short version)

The backend is the source of truth; the frontend is UX only. Every
tenant-owned query is scoped by `restaurant_id` derived server-side from the
JWT or table session — never from client input. RBAC on every protected
endpoint, Pydantic `extra="forbid"` on every request body, soft-deletes and
immutable order/invoice snapshots, audit log rows on every privileged write,
and `SELECT ... FOR UPDATE` around money-touching transactions. Details and
the full invariant list live in [CLAUDE.md](CLAUDE.md).
