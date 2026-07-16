PHASE 9a — Frontend shared infrastructure

Context:
- The entire backend (Phases 0–8) works and is tested.
- This phase builds the frontend foundation every surface reuses: the Vite + React
  + TypeScript project following docs/FRONTEND_STRUCTURE.md, the axios client with
  in-memory access token + cookie refresh (Decision D1), the Redux/RTK Query store,
  Zod schemas mirroring backend contracts, the router with role guards, and the
  WebSocket client. No user-facing screens yet beyond a login + a blank shell.
- Done = the app builds with strict TS, logs a staff user in, silently refreshes
  the access token, and connects an authenticated WS — with no JWT in localStorage.

Read first: CLAUDE.md (§4 Frontend layout, frontend security rules),
docs/FRONTEND_STRUCTURE.md. Confirm scope back in one line.

Threat model for this phase:
- The frontend is untrusted by the backend, but it must not WEAKEN security: no
  token in localStorage/sessionStorage, no dangerouslySetInnerHTML, validate API
  responses, and never use a UI guard as the only gate.

Scope — build these files and only these (TypeScript, .tsx/.ts only):
- frontend/ Vite + React + TS scaffold, tsconfig with "strict": true, ESLint.
- src/main.tsx, src/App.tsx, src/store/store.ts (RTK + RTK Query).
- src/services/api.ts: axios instance — base URL from env, attaches the in-memory
  access token, on 401 calls /auth/refresh (cookie) once and retries; clears state
  on refresh failure. Access token held in a module/store variable, NEVER persisted.
- src/features/auth/{authApi.ts, authSlice.ts, useAuth.ts}: login/logout/refresh;
  auth status in memory.
- src/features/session/{sessionApi.ts, sessionSlice.ts, useSession.ts}: customer
  table-session token handling (X-Session-Token), held in memory.
- src/features/realtime/{ws.ts, useRealtime.ts}: authenticated WS client that
  reconnects and dispatches events into RTK Query cache; auth via token, not a
  client-chosen channel.
- src/routes/{AppRoutes.tsx, RequireRole.tsx}: route table + a UX-only role guard.
- src/layouts/{CustomerLayout.tsx, StaffLayout.tsx, AdminLayout.tsx}: chrome only.
- src/components/common/{Button.tsx+Button.module.css, Input.tsx, Loader.tsx}.
- src/lib/zod schemas mirroring backend response/request shapes (auth, session;
  others added per later phase). src/types/ shared types.
- src/pages/staff/Login.tsx: minimal working staff login form (Zod-validated).

Specifications:
- Access token in memory only; refresh token is the HttpOnly cookie the backend
  set — the client never reads it. api.ts handles the refresh cycle.
- Every form uses Zod; cap inputs (e.g. instructions <=500) as UX.
- RequireRole hides/redirects in the UI only; the backend already enforces.

Dependencies to install (pinned): react, react-dom, react-router-dom, @reduxjs/
toolkit, react-redux, axios, zod, vite, typescript, @types/*. Confirm versions.

Out of scope — do NOT touch / add:
- No customer/kitchen/waiter/counter/admin screens beyond Login + blank layouts.
- No localStorage/sessionStorage for tokens. No UI component libraries unless you
  ask first. No backend changes.

Must not break (regression guard): backend unchanged; this is a new frontend/ dir.

ASK BEFORE: adding a UI/component library; persisting any token; changing the
refresh strategy from D1. (CLAUDE.md §6 applies.)

Functional acceptance — run these and paste the real output:
1. `npm run build` and `npx tsc --noEmit` -> both succeed with strict mode.
2. Run the dev server, log in as a seeded staff user -> lands on the staff shell;
   network tab shows access token in memory (Authorization header) and a refresh
   round-trip works after the access token expires.

Security acceptance — run these and paste the real output:
1. `grep -rn "localStorage\|sessionStorage" src/` -> no token storage (ideally no hits).
2. `grep -rn "dangerouslySetInnerHTML" src/` -> no hits.
3. Show that on a forced 401 the client calls /auth/refresh once and retries,
   then logs out cleanly if refresh fails.

Definition of done: see CLAUDE.md §8. Then stop — do not start Phase 9b.
Stop and ask before deviating from this spec.
