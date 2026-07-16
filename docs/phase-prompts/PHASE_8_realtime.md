PHASE 8 — Realtime (WebSockets)

Context:
- Phases 0–7 done: the full backend domain works and is tested.
- This phase adds live updates: authenticated WebSocket endpoints for staff (JWT)
  and customers (session token), strictly tenant-scoped channels, and broadcasts
  on the domain events that already happen in Phases 5–7. It adds NO new business
  rules — it only observes and pushes.
- Done = unauthenticated/expired connections are rejected; a connection for
  restaurant A never receives restaurant B's events; the right roles get the right
  events.

Read first: CLAUDE.md (§3 Tenancy, Authorization), docs/BUILD_PLAN.md (Phase 8),
docs/FRONTEND_STRUCTURE.md (realtime feature). Confirm scope back in one line.

Threat model for this phase:
- Assume the attacker: connects with no token / a forged or expired token, and
  tries to subscribe to another restaurant's channel by sending a chosen
  restaurant_id or channel name. Tenant scope MUST come from the verified token,
  never from a client-chosen channel string.

Scope — build these files and only these:
- backend/app/realtime/auth.py: authenticate a WS handshake — staff via JWT,
  customer via session token (query param or first message; pick one and document
  it). Reject (close with a policy code) on missing/invalid/expired credentials.
  Derive restaurant_id (+ role or session) from the verified credential ONLY.
- backend/app/realtime/manager.py: a connection manager keyed by restaurant_id,
  with role/session sub-grouping. broadcast(restaurant_id, event, audience) sends
  only to that tenant's connections matching the audience (e.g. kitchen, waiter,
  counter, or the specific customer session).
- backend/app/realtime/events.py: typed event payloads — order.created,
  order_item.status_changed, order.status_changed, invoice.paid, order.closed.
- backend/app/api/ws.py: WS routes — /ws/staff and /ws/customer. On connect,
  authenticate, register with the manager scoped to the token's restaurant_id;
  on disconnect, deregister.
- Wire emission: have the Phase 5–7 services emit these events AFTER their
  transaction commits (so clients never see uncommitted state). Add a thin hook
  call at the end of place_or_append, transition_item, transition_order,
  record_counter_payment, handle_webhook — without changing their business logic.

Specifications:
- Channel/tenant scope is server-derived. Ignore any client-sent restaurant_id or
  channel name for authorization; use it at most as a filter WITHIN the already
  scoped tenant.
- Audience routing: kitchen connections get item NEW/PREPARING/READY events;
  waiter gets READY/served + meal-finished; counter gets meal-finished/invoice;
  the customer session gets its own order's item/status/closed events.
- Emit only post-commit. No business rule lives in the WS layer.

Dependencies to install: none expected (FastAPI/Starlette WS is built in). If you
think you need one, STOP and ask.

Out of scope — do NOT touch / add:
- No new endpoints beyond the two WS routes. No schema changes. No frontend.
- Do not move/duplicate business logic into the realtime layer.

Must not break (regression guard):
- All Phase 0–7 HTTP endpoints behave exactly as before; the event hooks must not
  alter transaction outcomes or timing of the committed state.

ASK BEFORE: any schema change; the customer WS auth transport (query param vs
first-message); emitting before commit. (CLAUDE.md §6 applies.)

Functional acceptance — run these and paste the real output:
1. Connect a staff WS (KITCHEN) with a valid JWT; place a customer order via HTTP;
   show the kitchen socket received an order.created / order_item.status_changed
   event for that restaurant.
2. Transition an item ->ready; show a waiter socket receives it.

Security acceptance — run these and paste the real output:
1. Connect /ws/staff with no token and with a tampered token. Expected: connection
   closed/refused both times.
2. Connect with an expired JWT. Expected: refused.
3. Two staff sockets for restaurant A and restaurant B; trigger an event in A.
   Expected: only A's socket receives it; B receives nothing.
4. Customer socket for table T1 does not receive another table's order events.

Definition of done: see CLAUDE.md §8. Then stop — do not start Phase 9.
Stop and ask before deviating from this spec.
