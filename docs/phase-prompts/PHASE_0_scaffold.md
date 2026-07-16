PHASE 0 — Scaffold & foundations

Context:
- This is a brand-new repo. Nothing exists yet except CLAUDE.md and docs/.
- This phase builds a running, empty, secure shell: containers come up, the API
  answers a health check, and migrations can run. No business logic at all.
- Done = `docker compose up` works, GET /health returns 200, and the app connects
  to Postgres as a NON-superuser role.

Read first: CLAUDE.md and docs/BUILD_PLAN.md (Phase 0).
Confirm the scope and out-of-scope list back to me in one line before coding.

Threat model for this phase:
- Minimal, but: no secrets in the repo, and the app must NOT connect as the
  postgres superuser. Assume the compose file and env will be reviewed.

Scope — build these files and only these:
- docker-compose.yml: services for `db` (postgres:16), `backend` (FastAPI), and a
  placeholder `frontend` (node:20, no app yet — just a container that idles).
- backend/Dockerfile: Python 3.12-slim, installs from requirements.txt.
- backend/requirements.txt: pinned deps (see below).
- backend/app/main.py: FastAPI app, includes a health router.
- backend/app/api/health.py: GET /health -> {"status": "ok"}.
- backend/app/core/config.py: Pydantic-Settings config read from env (DB URL,
  secret key placeholder). No defaults for secrets.
- backend/app/db/session.py: SQLAlchemy 2.x engine + sessionmaker from config.
- backend/app/db/base.py: declarative Base.
- backend/alembic.ini + backend/alembic/ (env.py, versions/): Alembic wired to
  the SQLAlchemy Base and DB URL from env. One empty baseline revision.
- backend/.env.example: documents required env vars (no real values).
- db/init/01_roles.sql: creates a restricted role `app_user` (LOGIN, no
  SUPERUSER/CREATEDB/CREATEROLE) and grants it only what the app needs on the
  app database; run via the postgres image's docker-entrypoint-initdb.d.
- .gitignore: ignores .env, __pycache__, node_modules, etc.

Data contracts:
- Health response: exactly {"status": "ok"} with HTTP 200.
- Config fields: DATABASE_URL (str), SECRET_KEY (str, required, no default),
  ENVIRONMENT (str, default "development").

Dependencies to install (pinned — confirm latest compatible patch versions):
- fastapi, uvicorn[standard], sqlalchemy>=2, alembic, psycopg[binary],
  pydantic>=2, pydantic-settings
(Pin exact versions in requirements.txt.)

Out of scope for this phase — do NOT touch / add:
- No models, no tables, no business routers, no auth, no JWT, no tests.
- No frontend application code (the frontend container just idles for now).
- No CI, no logging framework, no rate limiting.

Must not break (regression guard):
- N/A (first phase).

ASK BEFORE doing any of these (stop and ask, do not guess):
- Choosing any dependency or version not listed above.
- Any deviation from "app connects as a non-superuser role."
- (CLAUDE.md §6 ask-before triggers also always apply.)

Functional acceptance — run these and paste the real output:
1. `docker compose up -d && sleep 5 && curl -s localhost:8000/health`
   Expected: {"status":"ok"}
2. `docker compose exec backend alembic upgrade head`
   Expected: runs without error against the empty baseline revision.

Security acceptance — run these and paste the real output:
1. `docker compose exec db psql -U app_user -d <appdb> -c "SELECT rolsuper FROM pg_roles WHERE rolname='app_user';"`
   Expected: rolsuper = f (false) — app role is NOT a superuser.
2. `git status --porcelain && grep -R "SECRET" backend/.env.example`
   Expected: no .env tracked by git; .env.example contains placeholders only.

Definition of done: see CLAUDE.md §8. Then stop — do not start Phase 1.
Stop and ask before deviating from this spec.
