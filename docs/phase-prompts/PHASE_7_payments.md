PHASE 7 — Invoices & payments (HIGHEST RISK)

Context:
- Phases 0–6 done: full ordering + role workflows work and are tested.
- This phase handles money: generate invoices (separate from orders, multiple per
  order), run the invoice state machine, accept counter payments, process gateway
  webhooks with signature verification + idempotency, prevent double payments,
  handle the fallback flow, and close the order + reset the table on success.
- Done = forged webhooks rejected, replays idempotent, no double payment, failed
  payments spawn a new invoice without corrupting the order, manual overrides audited.

Read first: CLAUDE.md (§2, §3 Money/Concurrency/Audit), docs/BUILD_PLAN.md
(Phase 7, decisions D2, D6, D7, D9). Confirm scope back in one line.

!! Before coding the gateway adapters, FETCH THE CURRENT eSewa / Khalti / Fonepay
   integration docs and confirm the exact signature scheme and verification call.
   My spec below is the shape, not authoritative API detail — STOP and confirm
   the live signing/verification method before implementing it.

Threat model for this phase:
- Assume the attacker: POSTs a forged webhook with no/invalid signature, replays a
  real webhook to double-credit, races two payments on one invoice, tampers the
  amount in the callback, and tries to close an order that was never paid. All
  must fail. Money is computed server-side from snapshots, never from the client
  or the gateway's claimed amount alone.

Scope — build these files and only these:
- backend/app/services/invoice_service.py: generate_invoice(order) — only when
  order is MEAL_FINISHED; computes subtotal from order_item snapshots (qty *
  unit_price + addons), tax_total, applies invoice-level discount (flat/percent,
  validated >=0 and not exceeding subtotal), total — all Decimal; assigns
  invoice_number via numbering_service; status DRAFT. Multiple invoices per order
  allowed (a FAILED/VOID invoice does not block a new one).
- backend/app/services/payment_state.py: invoice transitions DRAFT->
  PENDING_PAYMENT->PAID|FAILED|VOID, PAID->REFUNDED. Guard function.
- backend/app/payments/base.py: PaymentGateway interface — create_intent(invoice)
  and verify_webhook(headers, raw_body) -> {transaction_id, status, amount,
  invoice_ref}. raw_body is the EXACT bytes (needed for signature checks).
- backend/app/payments/esewa.py, khalti.py, fonepay.py: reference adapters
  implementing the interface (after you confirm live docs). Secrets from config.
- backend/app/services/payment_service.py:
  - record_counter_payment(invoice, method, idempotency_key): CASH/CARD/
    COUNTER_WALLET; under a transaction with FOR UPDATE on the invoice + order,
    marks PAID, closes order (CLOSED), resets table (free for a new session),
    audits. Honors restaurant_settings.waiter_can_accept_payment for WAITER.
  - handle_webhook(gateway, headers, raw_body): verify signature -> map to invoice
    -> idempotency via UNIQUE gateway_transaction_id AND an idempotency key store
    -> confirm gateway amount == invoice.total -> mark PAID -> close + reset ->
    audit. A replay (same transaction_id) is a no-op success, never a second credit.
  - fallback: on gateway FAILED, mark that invoice FAILED and allow a new invoice;
    counter then collects via record_counter_payment.
  - manual_override(invoice, reason): ADMIN only, requires reason, audited.
- backend/app/schemas/invoice.py: request/response models, extra="forbid";
  Idempotency-Key handled via header for counter payment endpoints.
- backend/app/api/invoices.py: COUNTER/ADMIN — POST /invoices (generate),
  GET /invoices/{id}, POST /invoices/{id}/pay (counter), POST
  /invoices/{id}/override (ADMIN). Customer (session) — POST /invoices/{id}/intent
  to start a gateway payment, GET own invoice for the active order.
- backend/app/api/webhooks.py: POST /webhooks/{gateway} — raw body, signature
  verified, NO auth dependency (it's the gateway), strictly idempotent.

Specifications:
- Amount is the server's invoice.total. A webhook/callback whose amount disagrees
  is rejected (logged), never auto-trusted.
- Everything that changes invoice/order/table state runs in ONE transaction with
  row locks; commit only after all succeed.
- gateway_transaction_id is UNIQUE (Phase 1) — rely on it as the last-resort
  idempotency guard; handle the unique-violation as "already processed".
- Close + reset table happens ONLY on a real PAID transition.

Dependencies to install (pinned): an HTTP client if a gateway needs server-side
verification lookups (httpx). Confirm versions. STOP and ask before adding a
vendor SDK.

Out of scope — do NOT touch / add:
- No websockets (Phase 8). No refunds UI flow beyond the PAID->REFUNDED guard +
  an ADMIN endpoint if trivial (else defer; ask). No schema changes (the Phase 1
  invoice table + unique tx id already cover this) — if you think you need one,
  STOP and ask.

Must not break (regression guard):
- Order/append, role workflows, menu, sessions, auth, health all still work.

ASK BEFORE: any schema change; the exact gateway signature/verification method
(confirm against live docs); refund scope; trusting any client/gateway-supplied
amount. (CLAUDE.md §6 applies.)

Functional acceptance — run these and paste the real output:
1. Take an order to MEAL_FINISHED, POST /invoices -> DRAFT with computed total
   matching the snapshot math. As COUNTER: /pay (CASH) -> invoice PAID, order
   CLOSED, table reset, audit row present.
2. Simulate a valid gateway webhook (use the adapter's own signer in a test) ->
   invoice PAID, order CLOSED.

Security acceptance — run these and paste the real output:
1. POST /webhooks/esewa with no/invalid signature. Expected: rejected, no state change.
2. Replay the SAME valid webhook twice. Expected: first PAID, second a no-op;
   exactly ONE payment, no double close.
3. Webhook with amount != invoice.total. Expected: rejected/flagged, not auto-PAID.
4. Two parallel /pay calls on one invoice. Expected: one PAID, the other a no-op
   or conflict; never two payments (FOR UPDATE holds).
5. Try to /pay or close an invoice whose order is still OPEN. Expected: rejected.
6. manual override with no reason. Expected: 422. With reason -> audited.
7. WAITER /pay while waiter_can_accept_payment=false. Expected: 403.

Definition of done: see CLAUDE.md §8. Then stop — do not start Phase 8.
Stop and ask before deviating from this spec.
