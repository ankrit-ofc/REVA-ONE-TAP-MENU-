PHASE 10 — Hardening & cross-cutting

Context:
- The full stack (backend Phases 0–8 + frontend Phase 9) is built and tested.
- This final phase applies the cross-cutting protections the blueprint listed as
  "not fully solved by application design": rate limiting, security headers, strict
  CORS, structured non-leaky logging, dependency pinning/audit, and a basic CI
  pipeline. No new features.
- Done = abusive request rates are throttled (429), security headers are present,
  CORS is locked to known origins, logs carry no secrets/PII, and CI runs green.

Read first: CLAUDE.md (all), docs/BUILD_PLAN.md (Phase 10), and the original
security checklist's "threats not fully solved" list. Confirm scope back in one line.

Threat model for this phase:
- Assume: credential-stuffing on login, QR-scan flooding, order/session spam, and
  log-scraping for tokens. This phase blunts volume-based abuse and reduces blast
  radius; it does not replace the per-endpoint auth/tenant checks already in place.

Scope — build these (touch only what each item needs):
- Rate limiting (e.g. slowapi/Redis or an ASGI middleware): per-IP and where
  sensible per-session/per-user limits on: POST /auth/login (tight), POST /scan,
  POST /orders/items, session creation, and special-instruction submissions.
  Return 429 with a Retry-After. Make limits configurable via env.
- Security headers middleware: HSTS (prod), X-Content-Type-Options nosniff,
  X-Frame-Options/ frame-ancestors, a sane Content-Security-Policy for the API
  responses, Referrer-Policy. (Frontend CSP tuned to its asset origins.)
- CORS: allow only the known frontend origin(s) from env; no wildcard with
  credentials.
- Structured logging: JSON logs with request id, method, path, status, latency,
  actor (when known). NEVER log Authorization headers, tokens, passwords, cookies,
  or full request bodies for auth/payment routes. A redaction filter.
- Error handling: a global handler that returns safe messages (no stack traces /
  internal detail to clients) while logging detail server-side.
- Dependency hygiene: pin all backend (requirements) and frontend (package-lock)
  versions; run `pip-audit` / `npm audit` and record findings; document the
  restricted DB role + secret-management expectations in docs/SECURITY_OPS.md.
- CI (GitHub Actions or equivalent): on push/PR run lint, `tsc --noEmit`, backend
  tests (if any), `alembic upgrade head` against a throwaway Postgres, and the
  audits. Fail the build on a migration or type error.

Specifications:
- Rate limits must not break legitimate flows (e.g. multiple diners scanning one
  table). Tune scan limits per-IP, not per-table.
- Headers/CORS read origins and toggles from env so dev and prod differ safely.
- Logging redaction is mandatory on auth and payment paths.

Dependencies to install (pinned): slowapi (or chosen limiter), pip-audit; CI uses
runner-provided tooling. Confirm versions. STOP and ask before adding Redis if you
don't already run it.

Out of scope — do NOT touch / add:
- No new product features, endpoints, or schema. No business-logic changes.
- Do not loosen any existing auth/tenant/audit behavior to make a test pass.

Must not break (regression guard):
- Every Phase 0–9 acceptance still passes; legitimate flows are not rate-limited
  under normal use.

ASK BEFORE: adding Redis or any infra dependency; any schema change; changing an
existing endpoint's contract. (CLAUDE.md §6 applies.)

Functional acceptance — run these and paste the real output:
1. Exceed the login limit (loop curl) -> 429 with Retry-After; a normal login
   still works after the window.
2. `curl -sI <frontend-served-page or API>` -> shows the security headers.
3. CI run output: lint + tsc + migration + audit all green.

Security acceptance — run these and paste the real output:
1. Flood POST /scan from one IP -> throttled, but two different diners (different
   IPs) on the same table are NOT blocked.
2. Trigger an error on an auth route and show the client response contains no
   stack trace, and the server log line has the token/password REDACTED.
3. `npm audit` / `pip-audit` output recorded; no unpinned dependency remains.
4. A cross-origin request from an unknown origin is blocked by CORS.

Definition of done: see CLAUDE.md §8. This is the last planned phase — after this,
do a full regression pass across all phases before any deploy.
Stop and ask before deviating from this spec.
