# ARCHITECTURE — Ordering / Kitchen / Waiter / Counter flow

> Traced from source. Every non-obvious claim cites `path:line`. Anything not
> found in code is marked **not found** rather than guessed. This describes the
> system as the code actually behaves, not as any single screen implies.

Stack: FastAPI + SQLAlchemy 2 + PostgreSQL (backend), React + TypeScript + Redux
Toolkit / RTK Query (frontend), WebSockets + Expo push (realtime/notifications).

---

## 1. Order lifecycle / state machine

There are **two independent state machines**: one for the **order** and one for
each **order item**. They are enforced in pure functions with no DB/HTTP concern
(`backend/app/services/order_state.py`) and applied under a row lock by
`order_service.transition_order` / `transition_item`.

### Order status

Enum values — `backend/app/models/enums.py:14`:

```
OPEN · MEAL_FINISHED · CLOSED
```

Allowed transitions — `order_state.py:24`:

```
OPEN            → MEAL_FINISHED
MEAL_FINISHED   → CLOSED
MEAL_FINISHED   → OPEN        (reopen; needs allow_reopen + reason)
CLOSED          → (terminal)
```

Text diagram (order):

```
                  customer taps "Request Bill"  (sets bill_requested_at; NO status change)
                                 │  orders.py:73 → order_service.request_bill (order_service.py:391)
                                 ▼
   ┌────────┐  waiter/counter move-to-billing   ┌───────────────┐   payment / quick-bill   ┌────────┐
   │  OPEN  │ ────────────────────────────────▶ │ MEAL_FINISHED │ ───────────────────────▶ │ CLOSED │
   └────────┘   counter.py:145 / waiter.py:277   └───────────────┘  payment_service /        └────────┘
        ▲        → transition_order (…:877)             │            _close_order_and_reset_table   (terminal)
        │                                               │                (payment_service.py:69,78)
        └───────────────── reopen (reason req.) ────────┘
             counter.py:165 / waiter.py:297 → transition_order(allow_reopen=True)
```

Gates enforced inside `transition_order` (`order_service.py:877`):
- `OPEN → MEAL_FINISHED` is **rejected** unless `bill_requested_at` is set
  (`order_service.py:904`) — staff cannot bill a table the customer hasn't asked
  to bill, *unless* they explicitly stamp it via `staff_start_billing`
  (`order_service.py:442`, exposed at `counter.py:195` `/counter/orders/{id}/start-billing`).
- `OPEN → MEAL_FINISHED` is **rejected** if any item is still `PENDING_APPROVAL`
  (`order_service.py:912`).
- Reopen (`→ OPEN`) requires `allow_reopen=True` **and** a non-empty reason
  (`order_state.py:50`), and the endpoints additionally gate it on the
  `allow_order_reopen` restaurant setting (`counter.py:47`, `waiter.py:85`).

### Order-item status

Enum values — `enums.py:20`:

```
PENDING_APPROVAL · NEW · PREPARING · READY · SERVED · CANCELLED
```

Allowed transitions — `order_state.py:72`:

```
PENDING_APPROVAL → NEW          (waiter approves batch)
PENDING_APPROVAL → CANCELLED    (waiter rejects batch)
NEW              → PREPARING | SERVED | CANCELLED
PREPARING        → READY | SERVED
READY            → SERVED
SERVED           → (terminal)
CANCELLED        → (terminal)
```

Text diagram (item):

```
 (require_order_approval ON)          kitchen              kitchen            waiter
   ┌──────────────────┐  approve   ┌─────┐  preparing   ┌───────────┐  ready  ┌───────┐  serve  ┌────────┐
   │ PENDING_APPROVAL │ ─────────▶ │ NEW │ ───────────▶ │ PREPARING │ ──────▶ │ READY │ ──────▶ │ SERVED │
   └──────────────────┘            └─────┘              └───────────┘         └───────┘         └────────┘
        │ reject                      │  │  cancel (NEW only)   │  serve directly  ▲   waiter can serve from
        ▼                            ▼  └──────────────────────┴──────────────────┘   NEW/PREPARING/READY
   ┌───────────┐                ┌───────────┐                       waiter.py:254 → transition_item(SERVED)
   │ CANCELLED │ ◀──────────────│ CANCELLED │  (kitchen.py:133)
   └───────────┘                └───────────┘
```

Who triggers what (item):
- **Kitchen**: `NEW→PREPARING` (`kitchen.py:93`), `PREPARING→READY`
  (`kitchen.py:113`), `NEW→CANCELLED` (`kitchen.py:133`).
- **Waiter**: `…→SERVED` from NEW/PREPARING/READY (`waiter.py:254`); batch
  approve `PENDING_APPROVAL→NEW` (`waiter.py:156`) and reject
  `PENDING_APPROVAL→CANCELLED` (`waiter.py:178`).
- **Customer**: never drives item/order status directly; only creates items and
  requests the bill.

> Note the **order** machine (`OPEN/MEAL_FINISHED/CLOSED`) is *separate* from the
> **item** machine. `SERVED` is an *item* state; `MEAL_FINISHED`/`CLOSED` are
> *order* states. An order does not auto-advance when its items are served — a
> staff member explicitly moves it to billing.

---

## 2. Customer / table side (order creation)

**Entry — scan:** `POST /scan` (`scan.py:21`). The QR token is a **signed**
payload; `restaurant_id` and `table_id` come from the verified signature, never
the request body (`scan.py:36`, `scan.py:41`). Optional geofence check
(`scan.py:59`, `428` if location needed). It returns a `TableSession` token via
`session_service.create_or_reuse_session` (`scan.py:98`).

**Session model:** `TableSession` (`backend/app/models/table.py:33`) with `token`,
`status` (`ACTIVE/EXPIRED/INVALIDATED`, `enums.py:49`), `expires_at`. The token
is sent by the customer app as the `X-Session-Token` header and validated by
`get_current_session` (`backend/app/core/deps.py`), which also sets the RLS GUC.

**Create / append items:** `POST /orders/items` (`orders.py:31`) →
`order_service.place_or_append` (`order_service.py:64`):
1. Locks the table row `FOR UPDATE` to serialise concurrent appends
   (`order_service.py:87`).
2. Finds the table's non-`CLOSED` order (`order_service.py:96`):
   - none → create a new `OPEN` order with a gapless `order_number`
     (`order_service.py:106`);
   - `OPEN` → append to it;
   - `MEAL_FINISHED` → **reject** 409 (`order_service.py:117`) — customer can't
     add to a checking-out table.
3. For each item: tenant-scoped product lookup (`order_service.py:149`),
   availability + variant + addon-mapping validation, then **snapshots**
   `product_name / variant_name / unit_price / tax_rate` and each addon's
   name+price (`order_service.py:195`, `:246`). Client-sent prices/names are never
   trusted (`OrderItemCreate` forbids extras — `schemas/order.py:30`).
4. Item status is `PENDING_APPROVAL` when `require_order_approval` is on, else
   `NEW` (`order_service.py:207`).

**Running total (customer view):** computed per line as
`(unit_price + Σ addon_price) × qty`, tax `= line × tax_rate / 100`
(`order_service.py:257`). This same math is mirrored authoritatively at invoice
time (`invoice_service.py:205`) and for the dashboard running tab
(`dashboard_service.py`). Money is `Decimal`/`NUMERIC`, never float.

**Request bill:** `POST /orders/request-bill` (`orders.py:73`) →
`request_bill` (`order_service.py:391`). **Notify-only**: it stamps
`bill_requested_at` and emits `bill.requested`; it performs **no** status change
(`orders.py:81`, `order_service.py:408`).

**Read current order:** `GET /orders/current` (`orders.py:55`) →
`get_current_order`, which returns the table's `OPEN` order only
(`order_service.py:377`, filter `status == OPEN` at `:383`).

---

## 3. Kitchen flow

**Queue query:** `GET /kitchen/queue` (`kitchen.py:71`) returns items with status
**`NEW` or `PREPARING`**, oldest first (`kitchen.py:82`). `READY`, `SERVED`,
`CANCELLED`, and `PENDING_APPROVAL` items are **not** in the kitchen queue.

**Frontend screen:** `frontend/src/pages/staff/kitchen/Queue.tsx`. Uses
`useGetKitchenQueueQuery` with `pollingInterval: 30_000` (`Queue.tsx:22`) and a
staff WebSocket that invalidates the `KitchenQueue` cache tag on `order.created`
/ `order_item.status_changed` (`Queue.tsx:26`). Items are grouped by order number
(`Queue.tsx:10`).

**Actions:** `KitchenTicket` (`components/ui/KitchenTicket.tsx`) shows a "Start
Preparing" button for `NEW` and "Mark Ready" for `PREPARING`
(`KitchenTicket.tsx:40`, `:49`). Both call mutations that hit
`/kitchen/items/{id}/preparing|ready`.

**"Optimistic-remove vs status-flip" behavior (the earlier fix):** the mutations
in `features/kitchen/kitchenApi.ts` do **not** manually mutate the cache — they
declare `invalidatesTags: ['KitchenQueue']` (`kitchenApi.ts:22`, `:27`), so after
each action the queue is **refetched from the server**. Because the queue filter
is `NEW ∪ PREPARING` (`kitchen.py:82`):
- `NEW → PREPARING`: the item **remains** in the queue and the ticket re-renders
  in its `PREPARING` style (the status flip — `KitchenTicket.tsx:18` keys the CSS
  class off `item.status`).
- `PREPARING → READY`: the item **falls out** of the queue (READY isn't in the
  filter) and disappears on refetch.

So "remove" happens only when an item genuinely leaves the `NEW/PREPARING` set;
there is no optimistic client-side removal that could desync from server truth.

---

## 4. Waiter flow

**Two queues:**
- To-serve: `GET /waiter/ready` (`waiter.py:101`) → items in `NEW ∪ PREPARING ∪
  READY`, oldest first (`waiter.py:116`). Broader than the kitchen queue: a
  waiter can serve at any pre-served stage (kitchens driven by the printed KOT
  never touch the queue screen).
- Pending approvals: `GET /waiter/pending-approvals` (`waiter.py:131`) → items in
  `PENDING_APPROVAL` (`waiter.py:145`).
- Also `GET /waiter/open-orders` (`waiter.py:199`) → `list_open_orders` so a
  waiter can move a served table to billing after the ready queue empties.

**Serve path:** `POST /waiter/items/{id}/served` (`waiter.py:254`) →
`transition_item(SERVED)`. Valid from NEW/PREPARING/READY (`order_state.py:74‑80`);
sets `served_at`.

**Pending-approval path** (only when `require_order_approval` is on):
- Approve: `POST /waiter/orders/{id}/approve` (`waiter.py:156`) →
  `approve_pending_items` (`order_service.py:711`). Locks the order + its pending
  items (`_lock_pending_batch`, `order_service.py:673`), flips each
  `PENDING_APPROVAL→NEW` (`order_service.py:722`), writes one batch audit row,
  and fires the **deferred KOT** (the kitchen ticket that was withheld at
  placement). Replays are a safe 409 — the row lock guarantees a single KOT
  (`waiter.py:166`).
- Reject: `POST /waiter/orders/{id}/reject` (`waiter.py:178`) →
  `reject_pending_items` (`order_service.py:813`); items `→ CANCELLED`, optional
  audited reason.

**Frontend screens:** `WaiterOrders.tsx` (open orders + pending approvals) and
`ReadyItems.tsx`. Both poll at `30_000` (`WaiterOrders.tsx:194`, `:197`;
`ReadyItems.tsx:97`, `:162`) and invalidate `WaiterOpenOrders` / `WaiterPending`
tags on the matching WS events (`WaiterOrders.tsx:201`).

**Rollback on failure:** state changes go through `transition_item` /
`approve_pending_items`, which mutate under a `FOR UPDATE` lock and `db.commit()`
only after all steps succeed; the domain error path raises `OrderError` before
commit, so a failed transition leaves the DB unchanged (see `transition_item`
`order_service.py:970` onward, and the batch lock at `order_service.py:673`). On
the client, mutations use `invalidatesTags` (server-truth refetch) rather than
optimistic writes, so a rejected request simply leaves the last server state on
screen. **Note:** the exact frontend catch/toast handling was not exhaustively
read for every button — **not fully verified per-button**; the server-side
atomicity is the authoritative guarantee.

---

## 5. Counter / billing / invoice flow

**Invoice model:** `Invoice` (`backend/app/models/invoice.py:17`) with `status`
(`InvoiceStatus`, `enums.py:32`: `DRAFT/PENDING_PAYMENT/PAID/FAILED/VOID/REFUNDED`),
`subtotal/discount/tax_total/total` (all `NUMERIC(12,2)`), `payment_method`, and
`gateway_transaction_id` (also reused as an idempotency key).

**Invoice total source:** computed server-side in
`invoice_service.generate_invoice` (`invoice_service.py:116`) from item snapshots:
`subtotal = Σ qty×(unit_price+addons)`, per-line tax, then discount, then
`total = subtotal − discount + tax` (`invoice_service.py:205‑229`). The client
never supplies money. Generation is only allowed for `MEAL_FINISHED` orders
(`invoice_service.py:150`) and is serialised by a `FOR UPDATE` lock on the order.

**Invoice state machine:** `payment_state.py:28` — `DRAFT→PAID` directly for
counter cash/card (skips `PENDING_PAYMENT`); gateway path goes
`DRAFT→PENDING_PAYMENT→PAID/FAILED`.

**Two ways to bill:**

1. **Two-step** (generate, then pay):
   - `POST /invoices` (`invoices.py:105`) → DRAFT invoice.
   - `POST /invoices/{id}/pay` (`invoices.py:160`) →
     `payment_service.record_counter_payment` (`payment_service.py:102`): locks
     the invoice + order (`payment_service.py:124`, `:141`), asserts order is
     `MEAL_FINISHED` (`payment_service.py:149`), sets invoice `PAID`, then
     `_close_order_and_reset_table` closes the order and invalidates the table's
     sessions (`payment_service.py:69`, `:78`). `Idempotency-Key` reuses
     `gateway_transaction_id` so a replay returns the same PAID invoice rather
     than double-applying (`payment_service.py:132`).

2. **Quick-bill** (create + pay + close in one atomic call):
   - `POST /counter/orders/{id}/quick-bill` (`counter.py:214`) →
     `payment_service.quick_bill_and_close`. For an `OPEN`, bill-requested order
     it generates the invoice, records payment, moves the order
     `→ MEAL_FINISHED → CLOSED`, and clears the table — all in one transaction
     (`payment_service.py` around `:442‑453`). Also `Idempotency-Key`-safe.

`WAITER` may use billing actions only when `waiter_can_accept_payment` is set
(`counter.py:61`, `payment_service.py:114`). Walkouts: `POST
/counter/orders/{id}/close-unpaid` (`counter.py:242`) voids any invoice and
closes the order with an audited reason.

**Frontend:** counter billing screen `pages/staff/counter/Billing.tsx` polls at
10–15 s (`Billing.tsx:193`, `:371`, `:549`); counter queues via `counterApi`.

---

## 6. Notifications (push)

**Purpose:** deliver staff alerts even when the app is backgrounded/killed, which
a WebSocket cannot (`push_service.py:1`).

**Trigger:** `push_service.notify(db, event)` is called right after each WS
broadcast (e.g. inside the order-creation path). It maps the event type to target
roles via `_EVENT_ROLES` (`push_service.py:45`) — `order.created`,
`order.approval_requested`, `waiter.called`, `bill.requested` — builds a message,
looks up **active, tenant-scoped device tokens** for users in those roles
(`push_service.py:153`), and fires a best-effort send on the event loop
(`push_service.py:167`) — never blocking or failing the originating request.

**Send path:** `_send_expo` (`push_service.py:170`) POSTs to Expo's push API
(`settings.EXPO_PUSH_URL`) in ≤100-token chunks, with
`channelId = _ANDROID_CHANNEL = "staff-v2"` (`push_service.py:40`, `:187`),
`priority: "high"`, `sound: "default"`. Tokens Expo reports as
`DeviceNotRegistered` are retired on a fresh RLS-scoped session
(`push_service.py:200`, `_deactivate_tokens` `:212`).

**Token model:** `DeviceToken` (tenant-scoped, per physical device). Registered
at login / deactivated at logout via `POST /push/register` and `/push/unregister`
(`push.py:31`, `:43`); `restaurant_id`/user come from the JWT, never the body
(`push.py:5`). Upsert reassigns a re-registered token to the current
user/restaurant (`push_service.py:55`).

**Routing (infra):** `/push/*` must reach the backend, not the SPA. This is
gated by the reverse-proxy allowlists — dev `frontend/vite.config.ts` and prod
`caddy/prod/Caddyfile:35` (the `@api` `path_regexp`, which includes `push`).
**Live-server verification of `/push` routing is still pending** (see Open
questions).

---

## 7. Realtime

**Transport:** WebSockets — `GET /ws/staff` and `/ws/customer` (`ws.py:38`, `:62`).
Auth uses a **single-use 60-second ticket** (`?ticket=`), minted by
`POST /auth/ws-ticket` (staff) or `POST /session/ws-ticket` (customer); raw
long-lived tokens in the query string are rejected (`ws.py:9`). The connection is
registered to a role/restaurant bucket (staff) or table bucket (customer) derived
from the ticket — never a client-chosen channel (`ws.py:52`, `:77`). It is
**server→client only** in this phase (`ws.py:54`).

**Broadcast fan-out** (`realtime/manager.py`, called from services): e.g.
`transition_order` routes `MEAL_FINISHED` to WAITER+COUNTER, `OPEN` (reopen) to
KITCHEN+WAITER, and always notifies the customer's table
(`order_service.py:960‑965`).

**Client:** `useStaffRealtime` / `useCustomerRealtime`
(`features/realtime/useRealtime.ts:13`, `:47`) open a reconnecting socket and
dispatch RTK Query cache invalidations on relevant events. **WS invalidation is
the primary update path; polling is the fallback.**

**Polling intervals by screen** (fallback cadence):

| Screen | Interval | Source |
|---|---|---|
| Kitchen queue | 30 s | `Queue.tsx:23` |
| Waiter orders / pending | 30 s | `WaiterOrders.tsx:194,197` |
| Waiter ready | 30 s | `ReadyItems.tsx:97,162` |
| Customer current order | 30 s | `features/orders/useOrders.ts:14` |
| Customer order status | 30 s | `pages/customer/OrderStatus.tsx:25` |
| Customer bill request | 10–30 s | `pages/customer/BillRequest.tsx:44,52` |
| Counter display board | 20 s | `pages/staff/counter/CounterDisplay.tsx:26` |
| Counter billing | 10–15 s | `pages/staff/counter/Billing.tsx:193,371,549` |
| Invoices | 15 s | `features/invoices/useInvoices.ts:13` |
| **Admin dashboard (new)** | 30 s | `pages/admin/Dashboard.tsx` (`POLL_MS`) |

---

## 8. Dashboard (newly built)

Routes (ADMIN-only, tenant-scoped) — `backend/app/api/dashboard.py`, mounted at
prefix `/dashboard` (`main.py:21`, `:116`). Frontend queries live in the admin
slice `frontend/src/features/admin/adminApi.ts:373‑385`, wired into
`pages/admin/Dashboard.tsx`, each polled at 30 s.

- **Active Tables** — `GET /dashboard/active-tables` →
  `dashboard_service.active_tables`. **Reuses** `order_service.list_open_orders`
  (does not re-derive the filter) and groups its orders by table, returning
  `table_label`, `order_count`, `earliest_placed_at`, a running `total_amount`,
  and nested orders→items. Sorted longest-waiting first.
- **Revenue Today** — `GET /dashboard/revenue-today` → sum of `invoices.total`
  where `status == PAID` and `created_at` is today in the restaurant timezone
  (default `Asia/Kathmandu`). There is **no `paid_at` column**; `created_at` is
  used as the payment instant (exact for quick-bill).
- **Orders This Week** — `GET /dashboard/orders-this-week` → count of orders
  placed since **Sunday 00:00** in the restaurant timezone.
- **Top-Selling Products** — `GET /dashboard/top-products` → GROUP BY product
  over line items from orders placed in the **last 7 days**, `SUM(quantity)`,
  top 5, returning the snapshot **product name** (not just id).

**Definition of "active":** an occupied table is one with an `OPEN` order — the
exact predicate of `order_service.list_open_orders` (`order_service.py:489`,
`status == OPEN` at `:530`, with the approval nuance `has_approved_item OR
¬has_pending_item` at `:531`). A separate table-session notion is deliberately
**not** used for occupancy.

**Open definitional question (by design, flagged):** `MEAL_FINISHED` orders
(done eating, awaiting payment) are **excluded** from Active Tables, because
they're no longer `OPEN`. Whether "awaiting-payment" tables should also surface
on the dashboard is an open product decision — see §10.

---

## 9. Multi-tenancy

**Column:** every tenant-owned table carries `restaurant_id` (NOT NULL, FK,
indexed) via `TenantMixin` (`backend/app/models/mixins.py:18`).

**Scope derivation:** `tenant_scope` (`core/deps.py:95`) reads `restaurant_id`
from the **verified JWT** (staff) — never from body/query/header — and sets the
Postgres GUC `app.current_restaurant_id` so RLS policies engage; it returns the
`restaurant_id` handlers use. `get_current_user` (`deps.py:33`) and `require_role`
(`deps.py:79`) provide identity + RBAC. The customer side uses
`get_current_session`, which sets the same GUC from the validated table session.

**App-layer filtering:** every tenant query additionally filters
`… .restaurant_id == restaurant_id` (e.g. order lookups `order_service.py:97`,
product lookups `:150`, dashboard queries throughout `dashboard_service.py`).
Per the project invariants, RLS is the *net*; app-layer scoping is mandatory.

**Human-facing ids:** internal PKs are UUIDs; users see `order_number` (per-
restaurant gapless sequence via `numbering_service`) and `INV-YYYY-NNNN`
(`invoice_service.py:231`), generated under a row lock.

---

## 10. Open questions / risks

> Flags only — nothing fixed here.

1. **Awaiting-payment tables invisible on the dashboard.** Active Tables is
   `OPEN`-only (§8). A table in `MEAL_FINISHED` (customer done, bill not yet
   paid) shows on neither "active tables" nor as revenue — a real occupied table
   that no dashboard panel surfaces. Decide whether it deserves its own count.

2. **Revenue Today has no true payment timestamp.** With no `paid_at`/`closed_at`
   column, revenue is dated by `invoice.created_at` (`dashboard_service.py`).
   Exact for quick-bill; for the two-step flow an invoice generated just before
   midnight but paid after it is attributed to the earlier day. Consider a
   dedicated `paid_at` if cross-midnight accuracy matters.

3. **`updated_at` is not auto-bumped.** `TimestampMixin.updated_at`
   (`mixins.py:13`) has only an insert default — no `onupdate`, no DB trigger
   (confirmed across `alembic/versions/*`). Any code ordering/among rows by
   `updated_at` (e.g. the counter MEAL_FINISHED queue `counter.py:106`) is really
   ordering by creation time, not last change. Latent surprise, not a crash.

4. **`/push` live routing unverified.** The prod Caddy `@api` regex now lists
   `push` (`caddy/prod/Caddyfile:35`), but this was replicated from an assumption
   about server commit `68c0498`, not confirmed against the running server. A
   `curl` to a real `/push/*` route on the live host is still owed before push
   notifications can be trusted end-to-end.

5. **Item vs order machine coupling is manual.** Serving the last item does not
   move the order to `MEAL_FINISHED`; a staff action must. Correct by design, but
   a table can sit with all items `SERVED` and the order still `OPEN`
   indefinitely — worth a "served but not billed" nudge somewhere.

6. **Kitchen queue relies on refetch, not optimistic UI.** Correct and simple
   (§3), but every kitchen action costs a full `/kitchen/queue` refetch; under a
   busy board that is more requests than an optimistic status-patch would be.
   Performance note, not a bug.
```
