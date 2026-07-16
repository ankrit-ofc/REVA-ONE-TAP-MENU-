PHASES 9c–9g — Staff & admin frontend surfaces

Each section below is its own Claude Code session (one surface per session). They
all share the same rules, so those are stated once here, then each surface lists
only its scope, contracts, and acceptance.

============================================================
SHARED RULES (apply to every surface 9c–9g)
============================================================
Read first: CLAUDE.md (frontend security rules), docs/FRONTEND_STRUCTURE.md, and
the backend contracts for the relevant phase. Confirm scope back in one line.

- TypeScript strict only (.tsx/.ts). Follow FRONTEND_STRUCTURE.md folders.
- Reuse 9a infra: axios client (in-memory token + cookie refresh), RTK Query, Zod,
  RequireRole, the WS client. No localStorage tokens; no dangerouslySetInnerHTML.
- RequireRole is UX only — the backend already enforces every call. Hiding a
  button is not security.
- Every list/detail view has loading/empty/error states. Live views subscribe to
  the WS feed (Phase 8) and update the RTK Query cache.
- Each surface calls ONLY endpoints that already exist from the backend phases.
- Out of scope every time: backend changes, schema changes, other surfaces,
  adding a UI library or any dependency without asking.
- ASK BEFORE: adding any dependency; calling an endpoint that doesn't exist yet;
  changing the token/refresh strategy. (CLAUDE.md §6 applies.)
- Acceptance every time: `npx tsc --noEmit` + `npm run build` succeed; a security
  grep for `localStorage|sessionStorage|dangerouslySetInnerHTML` over the new
  files returns no hits; plus the surface-specific checks below.

============================================================
PHASE 9c — Kitchen display
============================================================
Scope: pages/staff/kitchen/Queue.tsx + components/ui/KitchenTicket.tsx +
features/orders hooks for the kitchen view.
Contracts (Phase 6/8): GET /kitchen/queue; POST /kitchen/items/{id}/preparing;
POST /kitchen/items/{id}/ready; WS order.created / order_item.status_changed.
Behavior: large, glanceable ticket board of NEW + PREPARING items, oldest first;
one tap advances NEW→PREPARING→READY; new orders appear live without refresh.
Surface acceptance: trigger a customer order on the backend → ticket appears live;
advancing a ticket calls the right endpoint and the card moves; a KITCHEN token is
required to load the route (UX guard) and is the only role the backend accepts.

============================================================
PHASE 9d — Waiter
============================================================
Scope: pages/staff/waiter/ReadyItems.tsx + relevant ui components + hooks.
Contracts (Phase 6/8): GET /waiter/ready; POST /waiter/items/{id}/served; POST
/waiter/orders/{id}/meal-finished; POST /waiter/orders/{id}/reopen (only shown if
allow_order_reopen); WS READY/served/meal-finished events.
Behavior: list of READY items grouped by table; serve with one tap; mark a table's
meal finished; reopen (with a required reason input) only when settings allow.
Surface acceptance: ready items appear live; serve moves the item; reopen UI is
hidden when allow_order_reopen=false; reason is required by the form before submit.

============================================================
PHASE 9e — Counter / billing
============================================================
Scope: pages/staff/counter/Billing.tsx + components/ui/PriceSummary (reuse) +
features/invoices hooks.
Contracts (Phase 7/8): POST /invoices (generate); GET /invoices/{id}; POST
/invoices/{id}/pay (CASH/CARD/COUNTER_WALLET, with an Idempotency-Key); POST
/invoices/{id}/override (ADMIN); customer gateway status via WS invoice.paid.
Behavior: pick a MEAL_FINISHED order → generate invoice → show server-computed
total (never client math) → take payment → on PAID, show order closed + table
freed; handle the fallback (failed gateway → new invoice → counter collects).
Surface acceptance: total displayed equals the server's invoice.total; a repeated
pay click reuses the same Idempotency-Key and never double-charges; override
requires a reason; the board reflects PAID/CLOSED live.

============================================================
PHASE 9f — Admin
============================================================
Scope: pages/admin/{Dashboard, Categories, Products, Tables, Staff, Settings}.tsx +
admin ui components + feature hooks.
Contracts (Phase 4): admin menu CRUD; image upload (multipart) to
/admin/products/{id}/image; restaurant settings get/update; staff/table CRUD.
Behavior: manage categories/products/variants/addons (with image upload +
preview), tables, staff, and settings (enable_qr_payment,
waiter_can_accept_payment, allow_order_reopen, currency NPR, timezone). Soft
delete via deactivate, not destructive delete.
Surface acceptance: image upload validates type/size client-side (backend
re-validates), shows a preview, sets image_url; a deactivated product disappears
from the customer menu but its past orders are unaffected; settings changes take
effect (e.g. toggling allow_order_reopen flips the waiter reopen UI).

============================================================
PHASE 9g — Superadmin
============================================================
Scope: pages/superadmin/{Restaurants, Subscriptions, Analytics}.tsx + hooks.
Contracts: SUPERADMIN platform endpoints (create/activate/deactivate restaurants,
subscriptions, platform analytics). NOTE: if these backend endpoints were not
built in an earlier phase, STOP and ask — do not invent them; we may need a small
backend addition first.
Behavior: list/create restaurants, toggle active status, manage subscriptions,
view cross-tenant platform analytics (SUPERADMIN only — this is the one role that
sees across tenants, and only via dedicated endpoints).
Surface acceptance: only a SUPERADMIN token loads these routes; cross-tenant
analytics come from explicit platform endpoints, never by bypassing tenant scope;
build + strict TS pass.

Definition of done (each surface): see CLAUDE.md §8. Build one surface per session,
commit, then stop.
