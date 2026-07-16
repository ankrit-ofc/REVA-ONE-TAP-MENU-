PHASE 3 — QR codes & table sessions (customer)

Context:
- Phases 0–2 done: app runs, full schema with RLS exists, staff auth + tenant
  scoping + RBAC dependencies work and are tested.
- This phase builds CUSTOMER access: a signed QR per table, a /scan endpoint that
  exchanges a valid QR for a temporary TableSession, and a session dependency that
  later customer endpoints will use. No menu, no orders yet.
- Done = forged/expired QR rejected; sessions are non-guessable, expire, can be
  invalidated; table_id is always derived from the session, never the client.

Read first: CLAUDE.md (§3 Tenancy), docs/BUILD_PLAN.md (Phase 3, decision D5).
Confirm scope back to me in one line.

Threat model for this phase:
- Assume the attacker: edits the QR token to point at another table/restaurant,
  reuses an old/expired QR, replays a captured session token after expiry, and
  sends their own table_id/restaurant_id in the request body. All must fail.

Scope — build these files and only these:
- backend/app/core/qr.py: sign/verify a QR token. Payload {restaurant_id,
  table_id, v:1}, signed with a dedicated QR secret from config (NOT the JWT
  secret). Use itsdangerous (URLSafeSerializer/Signer) or HMAC. Verify rejects
  tampering and unknown versions.
- backend/app/services/session_service.py: create_or_reuse_session(table) ->
  returns the table's existing ACTIVE session if one exists, else creates a new
  one (token via secrets.token_urlsafe(32), expires_at = now + configurable TTL,
  status ACTIVE, bound to restaurant_id + table_id under a row lock on the table).
  invalidate_session(). A periodic/expiry check that treats past-expiry sessions
  as EXPIRED on access.
- backend/app/schemas/session.py: ScanRequest{qr_token:str} extra="forbid";
  SessionResponse{session_token, table_name, restaurant_name, expires_at}.
- backend/app/core/deps.py (extend): get_current_session — reads the session token
  from the `X-Session-Token` header, loads it, rejects if missing/expired/
  invalidated, sets the RLS GUC app.current_restaurant_id from the SESSION's
  restaurant_id. Exposes session.table_id to handlers.
- backend/app/api/scan.py: POST /scan -> validates QR signature, loads the table
  (must be is_active, tenant matches the QR's restaurant_id), calls
  create_or_reuse_session, returns SessionResponse.
- backend/app/api/session.py: POST /session/invalidate (staff ADMIN/WAITER/COUNTER
  or customer-with-session) -> invalidates the current table session.
- scripts/generate_qr.py: dev helper that, given restaurant_id + table_id, prints
  the signed QR token / a `/scan?...` payload. (No image rendering needed.)

Data contracts:
- QR token: signed string; verify() returns {restaurant_id, table_id} or raises.
- Session token: opaque, >= 256 bits entropy, stored hashed if feasible (or raw —
  ask if you want hashing). Returned once to the client.

Specifications:
- "One active session per table": if a table already has an ACTIVE, non-expired
  session, /scan returns THAT session (multiple diners at one table share it).
  This is intentional — it pairs with one-active-order-per-table later.
- Customer requests carry the session via header only; the body NEVER carries
  table_id or restaurant_id (extra="forbid" enforces it).
- Sessions expire automatically (TTL from config, e.g. 4 hours) and can be
  invalidated explicitly (e.g. on order close in a later phase).

Dependencies to install (pinned): itsdangerous (if used). Confirm version. If
you'd hash session tokens, you may need passlib/hashlib only — no new dep.

Out of scope — do NOT touch / add:
- No menu, products, orders, or invoices.
- No QR image generation (token only; image is a frontend/printing concern).
- No rate limiting (Phase 10).
- Do not modify the Phase 1 schema. If you think you must, STOP and ask.

Must not break (regression guard):
- Staff auth (/auth/*, /_probe/admin) still works; GET /health still 200;
  `alembic upgrade head` still clean.

ASK BEFORE: any schema change; whether to hash stored session tokens; changing
the session-token transport (header vs cookie). (CLAUDE.md §6 also applies.)

Functional acceptance — run these and paste the real output:
1. Generate a QR for a seeded table, then:
   `curl -s -X POST localhost:8000/scan -H 'Content-Type: application/json' -d '{"qr_token":"<valid>"}'`
   Expected: 200 with a session_token + expires_at + table/restaurant names.
2. Scan the SAME table again -> Expected: same active session returned, not a new one.

Security acceptance — run these and paste the real output:
1. Tampered QR (flip a char): Expected: 401/400, no session created.
2. QR signed for restaurant A used while the table belongs to restaurant B (craft
   via the script): Expected: rejected.
3. Use a session token after forcing expiry (set expires_at in the past via SQL):
   `curl ... -H 'X-Session-Token: <expired>'` to a get_current_session probe.
   Expected: 401.
4. Invalidate a session, then reuse it: Expected: 401.
5. Confirm a customer request body with `{"table_id":"..."}` is rejected (422,
   extra="forbid") and table is taken from the session.

Definition of done: see CLAUDE.md §8. Then stop — do not start Phase 4.
Stop and ask before deviating from this spec.
