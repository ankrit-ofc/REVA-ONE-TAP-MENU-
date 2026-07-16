# TAKEOVER_STEPS.md — Making this codebase fully yours

Starting point: code is on your machine, Docker + Postgres already run locally.
Work top to bottom. `you$` = PowerShell on your machine.

---

## Phase 1 — Replace all secrets (15 min)

The `.env` files shipped with the previous owner's values. Replace everything.

1. Generate two fresh random secrets:

   ```powershell
   you$ python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(64)); print('QR_SECRET=' + secrets.token_urlsafe(64))"
   ```

2. Edit `backend\.env` and replace:
   - `SECRET_KEY` and `QR_SECRET` → the values you just generated
   - `POSTGRES_PASSWORD` → a new strong password
   - `APP_DB_PASSWORD` → a different new strong password
   - `DATABASE_URL` → update its password part to match the **new
     `APP_DB_PASSWORD`** (the URL uses `tenant_app_user`, not `postgres`)
   - `ESEWA_SECRET_KEY`, `KHALTI_SECRET_KEY`, `FONEPAY_SECRET_KEY` → leave as-is
     for dev (sandbox); replace with YOUR merchant keys before production
   - `SMTP_*`, `FAL_KEY`, `ANTHROPIC_API_KEY` (if present) → clear or set to
     your own keys

3. The existing DB volume was initialized with the OLD passwords, so wipe it
   and let it rebuild with the new ones (dev data is disposable):

   ```powershell
   you$ docker compose down -v
   you$ docker compose up -d
   you$ docker compose logs backend --tail 20   # wait until uvicorn is up
   ```

   First boot re-runs `db/init/01_roles.sql` (creates `tenant_app_user` with
   your new `APP_DB_PASSWORD`) and you then apply migrations:

   ```powershell
   you$ docker compose exec backend alembic upgrade head
   ```

## Phase 2 — Create YOUR superadmin + smoke test (10 min)

1. Create your own platform superadmin (template in
   `docs/app_add_superadmin_setup.txt` — put your email and a strong password):

   ```powershell
   you$ docker compose exec backend python -c "
   from app.db.session import SessionLocal
   from app.models.user import User
   from app.models.restaurant import Restaurant, RestaurantSettings
   from app.core import security
   from app.models.enums import Role
   db = SessionLocal()
   r = Restaurant(name='Platform', slug='platform', is_active=True)
   db.add(r); db.flush()
   db.add(RestaurantSettings(restaurant_id=r.id))
   db.add(User(restaurant_id=r.id, email='ankritsapkota12345@gmail.com',
               password_hash=security.hash_password('CHANGE_ME_NOW'),
               role=Role.SUPERADMIN))
   db.commit(); print('Done.')
   "
   ```

2. Smoke test the core loop:
   - `GET http://localhost:8000/health` → `{"status": "ok"}`
   - Log in as superadmin → create a test restaurant + its ADMIN user
   - As ADMIN: add a category, a product, a table
   - Generate the table QR (`backend/scripts/generate_qr.py` or admin UI),
     scan/open it → menu loads → place an order
   - Check the kitchen queue shows the order

If all of that works, the stack is yours and functioning.

## Phase 3 — Push to your own GitHub repo (10 min)

1. On GitHub: create a new **empty private** repo (no README, no .gitignore).
2. From the project root:

   ```powershell
   you$ git init -b main
   you$ git add -A
   you$ git status
   ```

   **STOP and check the status list.** It must NOT contain: `backend/.env`,
   `frontend/.env`, `backend/.venv/`, `frontend/node_modules/`,
   `backend/media/`. (The `.gitignore` covers these — this is a double-check.)

3. Commit and push:

   ```powershell
   you$ git commit -m "initial commit"
   you$ git remote add origin https://github.com/<your-username>/<your-repo>.git
   you$ git push -u origin main
   ```

4. On GitHub → your repo → **Actions** tab → enable workflows. Push any small
   change (or re-run the workflow) and confirm CI goes green: backend migrate +
   pip-audit, frontend tsc + eslint + build + npm audit.

From here on, work as described in `HANDOVER.md` §2: feature branches, PRs
into `main`, merge on green CI.

## Phase 4 — Optional repo cleanup (first commit on a branch)

Safe deletions/fixes to make the repo yours (do as one `chore:` PR):

- Delete stale root `README.md` (write a real one) and root
  `package.json` + `package-lock.json` (orphaned; qrcode already lives in
  `frontend/`).
- Delete or move stray files: `DSA.txt`, `improvements.txt`,
  `SchemaCheckLogs.txt`, `resturants.png` (7.9 MB), `reva.jpeg`.
- `docs/DEPLOY.md` + `docs/app_add_superadmin_setup.txt` were already scrubbed
  of the previous owner's email/password/repo URL (done 2026-07-16).
- Fix docs drift when convenient: Postgres version (docs say 16, stack runs
  17), regenerate `docs/SCHEMA.md` from migrations.

## Phase 5 — Production, when you're ready (half a day + lead times)

Everything follows `docs/DEPLOY.md` (a full copy-paste runbook). Summary:

1. **Domain** (yours): buy one, add an A record → your server IP. If
   Cloudflare: "DNS only" (grey cloud) so Caddy can get certificates.
2. **Server** (yours): any 1 GB Ubuntu VPS — Vultr/Hetzner/DigitalOcean, the
   code doesn't care. Install Docker, clone YOUR repo.
3. **Env on the server**: `backend/.env` with production values (new secrets
   again — don't reuse dev ones; `ENVIRONMENT=production`), root `.env` from
   `.env.prod.example` with your `DOMAIN` and `ACME_EMAIL`.
4. **Deploy**: `./deploy.sh` — builds frontend, runs migrations, brings up
   Caddy (auto-HTTPS) + backend + Postgres. Only 80/443 are public.
5. **Backups**: set a nightly `pg_dump` cron to somewhere off the box (the
   previous owner relied on Vultr auto-backups; your provider may differ).

## Phase 6 — Payments + hardening (before real customers)

1. **Merchant accounts (longest lead time — start early)**: register YOUR
   eSewa / Khalti / Fonepay merchant accounts. Until they're approved, run
   CASH/CARD/manual only (supported). Before enabling Fonepay, confirm the
   signature field order against their merchant docs (`payments/fonepay.py`
   has a warning about this).
2. **Fix before prod** (details in `HANDOVER.md` §8):
   - eSewa sandbox key is the code default — make it fail fast in production
   - Rate limiting is per-proxy, not per-client, behind Caddy
   - Staff hard-delete violates the soft-delete invariant
3. **Add tests** — there are none. pytest + httpx for auth, cross-tenant
   isolation, payment idempotency. This is your safety net for every future
   feature.

---

*Generated 2026-07-16. Companion to `HANDOVER.md` (workflow + invariants).*
