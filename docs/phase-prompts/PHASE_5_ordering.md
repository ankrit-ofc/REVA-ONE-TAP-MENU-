PHASE 5 — Ordering core (the heart)

Context:
- Phases 0–4 done: schema, staff auth, customer sessions, and the tenant-scoped
  menu all work and are tested.
- This phase is the core: customers place and append items to ONE active order per
  table; order items capture price/tax/addon SNAPSHOTS; both state machines and
  their guards exist; concurrency is protected with row locks; transitions are
  audited; order numbers are gapless per restaurant.
- Done = illegal transitions rejected, no double active orders under concurrency,
  snapshots immune to later price edits, closed orders immutable.

Read first: CLAUDE.md (§3 all — esp. Concurrency, Audit, Identifiers, History),
docs/BUILD_PLAN.md (Phase 5, decisions D4, D6). Confirm scope back in one line.

Threat model for this phase:
- Assume the attacker (customer with a valid session): sends a fake unit_price,
  orders an unavailable or another tenant's product, appends to a CLOSED order,
  fires two concurrent appends to force two active orders, and attempts an
  illegal status jump (e.g. NEW -> SERVED). All must fail.

Scope — build these files and only these:
- backend/app/services/numbering_service.py: next_number(restaurant_id, type) ->
  increments restaurant_counters under SELECT ... FOR UPDATE; returns a gapless
  per-restaurant number (order #, later invoice #).
- backend/app/services/order_state.py: pure transition logic. ORDER:
  OPEN->MEAL_FINISHED->CLOSED, and MEAL_FINISHED->OPEN (reopen) requiring a
  permission flag + reason. ITEM: NEW->PREPARING->READY->SERVED, NEW->CANCELLED
  (only while NEW). Functions assert_valid_order_transition / assert_valid_item_
  transition raise a domain error on illegal moves. NO endpoints here.
- backend/app/services/order_service.py: place_or_append(session, items): under a
  transaction, lock the table row (FOR UPDATE), find/create the single active
  order (status OPEN), validate each item against the live product (tenant-owned,
  is_available, variant belongs to product, addons allowed), SNAPSHOT
  product_name/variant_name/unit_price/tax_rate and each addon name+price from the
  DB (NEVER from the client), insert order_items + order_item_addons, write an
  audit log. transition_order/transition_item wrappers that call order_state, set
  timestamps (preparing_at/ready_at/served_at), and audit.
- backend/app/schemas/order.py: OrderItemCreate{product_id:UUID,
  variant_id:UUID|None, addon_ids:list[UUID], quantity:int(1..99),
  special_instructions:str(0..500)|None} extra="forbid"; PlaceOrderRequest{items:
  list[OrderItemCreate](1..50)}; response models (order with items, snapshots,
  human-readable order_number — never expose UUIDs in user-facing fields).
- backend/app/api/orders.py: customer (session) endpoints only this phase:
  POST /orders/items (place or append; rejected unless order is OPEN),
  GET /orders/current (the table's active order with item statuses).

Data contracts:
- The client sends product_id/variant_id/addon_ids/quantity/instructions ONLY.
  Prices, names, taxes are looked up and snapshotted server-side. Any price-like
  field in the request is rejected (extra="forbid").

Specifications:
- One active order per table: rely on the Phase 1 partial unique index AND the
  in-transaction lock+check. A concurrent second append must attach to the same
  order, never create a second.
- Appends allowed only when order.status == OPEN. MEAL_FINISHED/CLOSED reject new
  items.
- Reopen (MEAL_FINISHED->OPEN) is NOT exposed to customers here; the service
  supports it (permission + reason) for Phase 6 staff endpoints to call.
- Every transition and every append writes an audit_logs row (actor =
  customer-session or staff user, entity, prev/new, reason where required).

Dependencies to install: none expected. If you think you need one, STOP and ask.

Out of scope — do NOT touch / add:
- No staff transition ENDPOINTS (that's Phase 6 — but build the service they'll
  call). No invoices/payments (Phase 7). No websockets (Phase 8).
- No schema changes. If you think you need one, STOP and ask.

Must not break (regression guard):
- /menu still hides unavailable items; auth, sessions, health all still work.

ASK BEFORE: any schema change; exposing reopen to customers; trusting any
client-supplied price/name/tax. (CLAUDE.md §6 applies.)

Functional acceptance — run these and paste the real output:
1. With a session: POST /orders/items (2 items) -> 200, order created with #N;
   POST again (1 item) -> 200, SAME order, 3 items total; GET /orders/current
   shows snapshots + order_number.

Security acceptance — run these and paste the real output:
1. POST with a fake price field, e.g. {"product_id":...,"unit_price":"0.01",...}.
   Expected: 422; if forced, stored unit_price = DB value, not client's.
2. Order an unavailable product. Expected: rejected.
3. Order another restaurant's product_id. Expected: rejected (not found in tenant).
4. Two near-simultaneous appends (run two curls in parallel). Expected: one active
   order with all items; no duplicate active order (partial index holds).
5. Force order to MEAL_FINISHED via SQL, then POST /orders/items. Expected: rejected.
6. Change the product's price via admin after ordering; GET /orders/current.
   Expected: snapshot price unchanged.
7. Attempt item transition NEW->SERVED through the service test. Expected: rejected.

Definition of done: see CLAUDE.md §8. Then stop — do not start Phase 6.
Stop and ask before deviating from this spec.
