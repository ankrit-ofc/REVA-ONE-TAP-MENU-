PHASE 2 — Auth & tenancy core (staff)

Context:
- After Phase 1 the full schema exists with constraints + RLS policies (RLS not
  yet enforced per-request — this phase wires that).
- This phase builds the security spine every later phase reuses: password
  hashing, JWT issue/verify, refresh rotation, and the dependencies for current
  user, role enforcement, and tenant scoping. Plus one role-guarded probe
  endpoint to prove the spine works. No business domain.
- Done = login issues tokens; the probe rejects tampered/expired/missing JWT and
  wrong role; the tenant scope is derived from the JWT and ignores client input.

Read first: CLAUDE.md (§3 Tenancy + Authorization), docs/BUILD_PLAN.md (Phase 2,
decision D1). Confirm scope back to me in one line.

Threat model for this phase:
- Assume the attacker uses curl/Burp: forges JWTs, edits the role/restaurant_id
  claim, replays old tokens, omits the Authorization header, and sends a
  restaurant_id in the body hoping it's trusted. The spine must defeat all of these.

Scope — build these files and only these:
- backend/app/core/security.py: Argon2 hashing (verify/hash); JWT encode/decode
  (HS256 or RS256 — pick HS256 with SECRET_KEY for V1); access token (short TTL,
  e.g. 15 min) + refresh token (longer TTL, rotation).
- backend/app/core/deps.py: get_db; get_current_user (decodes access token from
  Authorization: Bearer, loads active user, 401 on any failure);
  require_role(*roles) (403 if user role not allowed); tenant_scope (returns the
  restaurant_id FROM THE TOKEN and sets the Postgres GUC
  `app.current_restaurant_id` on the session so RLS engages).
- backend/app/schemas/auth.py: Pydantic models (LoginRequest extra="forbid",
  TokenResponse, etc.).
- backend/app/services/auth_service.py: authenticate, issue tokens, rotate
  refresh, revoke on logout.
- backend/app/api/auth.py: POST /auth/login, POST /auth/refresh, POST /auth/logout.
- backend/app/api/_probe.py: GET /_probe/admin guarded by require_role(ADMIN);
  returns the resolved restaurant_id from tenant_scope. (Temporary; removed later.)
- Wire refresh token into HttpOnly; Secure; SameSite=Strict cookie per D1; access
  token returned in the JSON body for the client to hold in memory.

Data contracts:
- LoginRequest: { email: EmailStr, password: str (min 8) }  extra="forbid".
- TokenResponse: { access_token: str, token_type: "bearer" }  (refresh set as cookie).
- JWT access claims: { sub: user_id, restaurant_id, role, exp, iat, type:"access" }.
- Refresh claims: { sub, restaurant_id, exp, iat, type:"refresh", jti }.

Specifications:
- Passwords hashed with Argon2 (argon2-cffi). Never store or log plaintext.
- Login: look up user by email WITHIN no tenant assumption? — users are unique by
  (email, restaurant_id); for staff login require email + (restaurant slug or
  derive single match). For V1 assume email is unique per restaurant and the
  login payload includes restaurant_slug; STOP and ask if you think a global
  email login is intended.
- refresh rotation: each /auth/refresh issues a new refresh token and invalidates
  the old jti (store revoked/last-valid jti per user, or a refresh-token table —
  propose which and ask if unsure).
- tenant_scope MUST take restaurant_id from the verified token only. If a request
  body/query contains restaurant_id, ignore it (and it's already extra="forbid").
- On every authenticated DB-touching request, set the RLS GUC so Phase 1 policies
  apply.

Dependencies to install (pinned): python-jose[cryptography] (or pyjwt),
argon2-cffi, email-validator. Confirm versions. If you'd choose differently, ask.

Out of scope for this phase — do NOT touch / add:
- No business endpoints (menu, orders, etc.). The probe is the only protected route.
- No rate limiting yet (Phase 10). No MFA.
- No frontend.
- Do not modify the Phase 1 schema except (if needed) adding a refresh-token /
  revoked-jti table — and if you need that, STOP and ask first.

Must not break (regression guard):
- GET /health still 200. `alembic upgrade head` still clean.

ASK BEFORE doing any of these (stop and ask, do not guess):
- Any schema change (incl. a refresh-token table).
- Global-vs-per-restaurant email login semantics.
- Switching JWT algorithm or token storage away from D1.
- (CLAUDE.md §6 ask-before triggers also always apply.)

Functional acceptance — run these and paste the real output:
1. Create a test ADMIN user (via a one-off script/SQL), then:
   `curl -s -X POST localhost:8000/auth/login -d '{"email":"a@x.com","password":"...","restaurant_slug":"x"}' -H 'Content-Type: application/json'`
   Expected: 200 with access_token + Set-Cookie refresh.
2. `curl -s localhost:8000/_probe/admin -H "Authorization: Bearer <token>"`
   Expected: 200, returns the restaurant_id from the token.

Security acceptance — run these and paste the real output:
1. Tampered token (flip a character):
   `curl -s -o /dev/null -w "%{http_code}" localhost:8000/_probe/admin -H "Authorization: Bearer <bad>"`
   Expected: 401.
2. No Authorization header:
   Expected: 401.
3. Valid token but wrong role (make a WAITER user, hit /_probe/admin):
   Expected: 403.
4. Login with extra field `{"email":...,"password":...,"is_admin":true}`:
   Expected: 422 (extra="forbid").
5. Authenticated request where the body also sends a different restaurant_id:
   Expected: server uses the token's restaurant_id, never the body's.

Definition of done: see CLAUDE.md §8. Then stop — do not start Phase 3.
Stop and ask before deviating from this spec.
