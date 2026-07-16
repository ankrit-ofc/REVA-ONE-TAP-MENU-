PHASE 9b — Customer ordering surface (highest design priority)

Context:
- Phase 9a done: frontend infra, auth/session handling, store, router, WS client,
  and Zod schemas exist; the backend is fully built.
- This phase builds the customer flow — the product's first impression. A diner
  scans a QR, browses the menu (with images), customizes and orders, watches live
  status, and requests the bill. Mobile-first, no login, non-technical user.
- Done = a phone user can scan → order → append → see live status → request bill,
  entirely against real backend contracts, validated and accessible.

Read first: CLAUDE.md (frontend security rules), docs/FRONTEND_STRUCTURE.md
(customer pages), and the Phase 3/4/5/7/8 contracts. Confirm scope back in one line.

Threat model for this phase:
- The client is untrusted: never send table_id (it's in the session), never trust
  client-side price math (display only; backend snapshots authoritative prices),
  Zod-validate every response, escape all text (no dangerouslySetInnerHTML).

Design direction (this surface gets real care, not a default template):
- Mobile-first, one-handed, large tap targets, sticky cart bar, clear category
  nav, prominent product images, obvious "Add", unmistakable "Request bill".
- A deliberate visual identity: choose a restrained palette + type scale and apply
  it consistently via CSS modules / tokens; avoid the generic Bootstrap look.
- Loading/empty/error states for every async view. Optimistic add-to-cart is fine,
  but order placement reflects the server's real response.

Scope — build these files and only these (TS, under src/pages/customer + features):
- pages/customer/Scan.tsx: takes the QR token (from the scanned URL), calls /scan,
  stores the session, routes to Menu. Handles invalid/expired QR gracefully.
- pages/customer/Menu.tsx: GET /menu via menu feature; category nav; ProductCard
  grid with images, price, availability.
- pages/customer/ProductDetail.tsx: variant select, addon multiselect, quantity,
  special instructions (<=500, Zod). Adds to cart (client draft).
- pages/customer/Cart.tsx: review draft (PriceSummary shows an ESTIMATE, labeled
  as such), place/append via POST /orders/items.
- pages/customer/OrderStatus.tsx: GET /orders/current + live updates via the WS
  client; shows each item NEW→PREPARING→READY→SERVED.
- pages/customer/BillRequest.tsx: trigger meal-finished/bill, and (if
  enable_qr_payment) start a gateway intent; show payment status.
- features/menu/{menuApi.ts, useMenu.ts}, features/cart/{cartSlice.ts, useCart.ts},
  features/orders/{ordersApi.ts, useOrders.ts}, features/invoices/{invoicesApi.ts,
  useInvoices.ts} — typed via Zod, wired to RTK Query + the WS cache updates.
- components/ui/{ProductCard.tsx, CartItem.tsx, PriceSummary.tsx,
  OrderItemStatus.tsx} + CSS modules.

Specifications:
- The cart is a client-side draft; prices shown are estimates. The order
  response/`GET /orders/current` (server snapshots) is the source of truth shown
  after placing.
- Never render the bill total from client math as authoritative — show the
  server's invoice total.
- All text rendered normally (React escaping); never dangerouslySetInnerHTML.

Dependencies to install: none beyond 9a unless you justify and ask.

Out of scope — do NOT touch / add:
- No staff/admin surfaces (later sub-phases). No backend changes. No new schema.
- No payment SDK embed unless the gateway requires it AND you ask first.

Must not break (regression guard): 9a infra, staff login, the build, strict TS.

ASK BEFORE: adding any dependency; embedding a gateway SDK; sending table_id from
the client; treating client price math as authoritative. (CLAUDE.md §6 applies.)

Functional acceptance — run these and paste the real output:
1. `npx tsc --noEmit` and `npm run build` succeed.
2. End-to-end on a mobile viewport (describe + screenshot or recording): scan →
   menu with images → customize → add → cart → place → status updates live as you
   transition items on the backend → request bill shows the server total.

Security acceptance — run these and paste the real output:
1. `grep -rn "dangerouslySetInnerHTML\|localStorage\|sessionStorage" src/pages/customer src/features` -> no hits.
2. Show the order request body contains NO table_id/price fields (only
   product_id/variant_id/addon_ids/quantity/instructions).
3. Show special_instructions is capped at 500 chars client-side (and the backend
   would reject longer anyway).

Definition of done: see CLAUDE.md §8. Then stop — do not start the next surface.
Stop and ask before deviating from this spec.
