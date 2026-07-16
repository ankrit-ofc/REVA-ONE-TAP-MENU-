PHASE 6 — Role workflow endpoints

Context:
- Phases 0–5 done: ordering core, both state machines (as a service), snapshots,
  concurrency, audit, and gapless numbering all work and are tested.
- This phase exposes the staff-facing transition endpoints on top of Phase 5's
  order_state/order_service: kitchen prep flow, waiter serve/finish/reopen,
  counter actions — all RBAC-gated and tenant-scoped, honoring restaurant settings.
- Done = each role can perform only its own transitions; reopen obeys settings +
  requires a reason; every transition is audited.

Read first: CLAUDE.md (§3 Authorization, Audit), docs/BUILD_PLAN.md (Phase 6).
Confirm scope back in one line.

Threat model for this phase:
- Assume the attacker is a logged-in staff member of the WRONG role (or right
  role, wrong restaurant): kitchen trying to mark SERVED, waiter reopening when
  settings forbid it, anyone transitioning another restaurant's item, reopen
  with no reason. All must fail.

Scope — build these files and only these:
- backend/app/schemas/workflow.py: request models — ItemTransitionRequest (target
  status), MealFinishRequest, ReopenRequest{reason:str(3..500)} extra="forbid".
- backend/app/api/kitchen.py: require_role(KITCHEN, ADMIN). GET /kitchen/queue
  (NEW + PREPARING items for the tenant, oldest first). POST
  /kitchen/items/{id}/preparing (NEW->PREPARING). POST /kitchen/items/{id}/ready
  (PREPARING->READY). Sets preparing_at/ready_at.
- backend/app/api/waiter.py: require_role(WAITER, ADMIN). GET /waiter/ready
  (READY items). POST /waiter/items/{id}/served (READY->SERVED, sets served_at).
  POST /waiter/orders/{id}/meal-finished (OPEN->MEAL_FINISHED). POST
  /waiter/orders/{id}/reopen (MEAL_FINISHED->OPEN) — ONLY if
  restaurant_settings.allow_order_reopen, requires reason.
- backend/app/api/counter.py: require_role(COUNTER, ADMIN). POST
  /counter/orders/{id}/meal-finished and /reopen (same rules as waiter; reopen
  gated by settings). (Invoice/payment endpoints are Phase 7 — not here.)
- All endpoints call Phase 5 services inside a transaction with row locks; all
  write audit_logs with actor + entity + prev/new + reason (reopen).

Specifications:
- Reuse Phase 5 order_state guards — do NOT re-implement transition logic.
- Cancellation (NEW->CANCELLED) endpoint: allow KITCHEN/ADMIN, only while NEW.
- Every endpoint is tenant-scoped; never act on an item/order by id alone.
- Honor restaurant_settings (allow_order_reopen; waiter_can_accept_payment is a
  Phase 7 concern — ignore here).

Dependencies to install: none expected. If you think you need one, STOP and ask.

Out of scope — do NOT touch / add:
- No invoices/payments (Phase 7), no websockets (Phase 8), no schema changes.
- Do not add new transition logic; call the existing service.

Must not break (regression guard):
- Customer order/append (Phase 5), menu, sessions, auth, health all still work.

ASK BEFORE: any schema change; adding a transition not in the state machines;
changing who may reopen. (CLAUDE.md §6 applies.)

Functional acceptance — run these and paste the real output:
1. Seed an OPEN order with a NEW item. As KITCHEN: ->preparing, ->ready (200 each;
   timestamps set). As WAITER: ->served (200). As WAITER: order ->meal-finished (200).
2. GET /kitchen/queue and /waiter/ready reflect the correct items per status.

Security acceptance — run these and paste the real output:
1. KITCHEN calls the waiter ->served endpoint. Expected: 403.
2. WAITER calls reopen while allow_order_reopen=false. Expected: 403/409.
3. Reopen with no reason / 1-char reason. Expected: 422.
4. Any role transitions an item belonging to another restaurant. Expected: 404/403.
5. Illegal jump (e.g. ready an item that is still NEW). Expected: rejected by the
   state machine.
6. After a reopen, confirm an audit_logs row exists with actor, prev=MEAL_FINISHED,
   new=OPEN, and the reason.

Definition of done: see CLAUDE.md §8. Then stop — do not start Phase 7.
Stop and ask before deviating from this spec.
