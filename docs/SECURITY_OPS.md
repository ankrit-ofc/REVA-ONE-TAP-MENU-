# SECURITY_OPS.md — Operational Security Reference

This document covers the restricted DB role, secret management expectations,
and operational security runbook for the Restaurant QR Ordering SaaS. It is
intended for DevOps and on-call engineers, not end users.

---

## 1. Database access — restricted role

The application connects to PostgreSQL as `tenant_app_user`, a role with **minimum
required privileges only**. It cannot DROP, CREATE, or SUPERUSER.

### Granted privileges

| Scope | Granted |
|---|---|
| Database | CONNECT only |
| Schema `public` | USAGE, CREATE (CREATE required for Alembic in dev/CI; revoke in prod after migrations) |
| Tables | SELECT, INSERT, UPDATE, DELETE via DEFAULT PRIVILEGES |
| Sequences | USAGE, SELECT via DEFAULT PRIVILEGES |

### How to create the role

Run `db/init/01_roles.sql` at DB init time (the Docker `postgres:17` image
runs scripts in `docker-entrypoint-initdb.d/` automatically on first boot):

```bash
# Manual equivalent (set APP_DB_PASSWORD and POSTGRES_DB first):
psql -U postgres -d $POSTGRES_DB \
  -v app_db_password="$APP_DB_PASSWORD" \
  -f db/init/01_roles.sql
```

### Production hardening

After running `alembic upgrade head` in production, revoke CREATE from the app
role to prevent the app from creating new objects:

```sql
REVOKE CREATE ON SCHEMA public FROM tenant_app_user;
```

Re-grant before the next migration run, then revoke again after.

### Row-Level Security

RLS policies are enabled on all tenant-owned tables (Phase 1). The app sets the
GUC `app.current_restaurant_id` at the start of every request via the
`tenant_scope` dependency. The RLS policy is:

```sql
USING (restaurant_id = current_setting('app.current_restaurant_id', TRUE)::uuid)
```

The app also enforces tenant scoping at the application layer (defense in depth).
RLS is the safety net — not the primary enforcement.

---

## 2. Secret management

| Secret | Purpose | Rotation |
|---|---|---|
| `SECRET_KEY` | JWT signing (HS256) | Rotate → all active sessions invalidated |
| `QR_SECRET` | QR token signing (HMAC) | Rotate → all printed QRs must be regenerated |
| `APP_DB_PASSWORD` | PostgreSQL `tenant_app_user` login | Rotate → update `DATABASE_URL` + restart app |
| `ESEWA_SECRET_KEY` | eSewa ePay v2 HMAC signing | Set by eSewa merchant dashboard |
| `KHALTI_SECRET_KEY` | Khalti payment lookup | Set by Khalti merchant dashboard |
| `FONEPAY_SECRET_KEY` | Fonepay HMAC signing | Set by Fonepay merchant dashboard |

### Rules
- **No secrets in source control.** All secrets come from environment variables.
  The `.env` file is git-ignored. Only `.env.example` (with placeholder values)
  is committed.
- **Separate secrets per environment.** Dev, staging, and production use
  different values for every secret.
- **Minimum length.** `SECRET_KEY` and `QR_SECRET` must be at least 32 random
  bytes (`python -c "import secrets; print(secrets.token_hex(32))"`).
- **Never log secrets.** The structured logging middleware explicitly avoids
  logging Authorization headers, cookies, passwords, or token values.

---

## 3. CORS

Allowed origins are set via the `ALLOWED_ORIGINS` environment variable
(comma-separated). In production:

```bash
ALLOWED_ORIGINS=https://order.yourrestaurant.com
```

`allow_credentials=True` is set in the CORS middleware. This combination is
safe because `allow_origins` is an explicit whitelist (never `*`). Browsers
will not attach cookies or Authorization headers to cross-origin requests from
unlisted origins.

---

## 4. Rate limiting

Rate limits are per-IP (X-Forwarded-For is not trusted by default — configure
a reverse proxy to set it correctly if deploying behind nginx/ALB).

| Endpoint | Default limit | Purpose |
|---|---|---|
| `POST /auth/login` | 5/minute | Credential-stuffing mitigation |
| `POST /scan` | 20/minute | QR-scan flooding mitigation |
| `POST /orders/items` | 30/minute | Order spam mitigation |

All limits return HTTP 429 with a `Retry-After` header. Limits are configurable
via env vars (`RATE_LIMIT_LOGIN`, `RATE_LIMIT_SCAN`, `RATE_LIMIT_ORDERS`).

Storage: in-memory (per process). For multi-process deployments, configure
a shared Redis backend by updating `limiter.py` to use `slowapi`'s Redis
storage adapter. Ask the team before adding Redis as an infrastructure dependency.

---

## 5. Security headers

Applied to every response by `app/middleware/security_headers.py`:

| Header | Value |
|---|---|
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Content-Security-Policy` | `default-src 'none'; frame-ancestors 'none'` |
| `X-Permitted-Cross-Domain-Policies` | `none` |
| `Strict-Transport-Security` | `max-age=63072000; includeSubDomains; preload` (production only) |

---

## 6. Dependency auditing

Run before every deployment:

```bash
# Backend
cd backend
pip-audit -r requirements.txt

# Frontend
cd frontend
npm audit --audit-level=high
```

CI runs these automatically on every push/PR (see `.github/workflows/ci.yml`).
Fix or document any `high`/`critical` findings before merging to main.

---

## 7. Incident response (brief)

| Scenario | Action |
|---|---|
| JWT `SECRET_KEY` leaked | Rotate key immediately — all tokens invalidated |
| QR `QR_SECRET` leaked | Rotate key + reprint/redistribute all table QR codes |
| DB password leaked | Reset `tenant_app_user` password, update `DATABASE_URL`, restart app |
| Gateway webhook secret leaked | Rotate at gateway dashboard, update env var |
| Suspected data breach | Revoke all tokens (rotate `SECRET_KEY`), notify DPO, review audit_logs |

All privileged actions are recorded in the `audit_logs` table. Investigate
there first.
