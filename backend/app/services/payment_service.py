"""
Payment processing service.

Three public entry points:

record_counter_payment  — CASH / CARD / COUNTER_WALLET collected at the counter.
                          Respects waiter_can_accept_payment setting for WAITER role.
                          Idempotent via optional Idempotency-Key header (stored as
                          gateway_transaction_id).

create_payment_intent   — Initiate a QR gateway payment (customer endpoint).
                          Validates enable_qr_payment, transitions DRAFT →
                          PENDING_PAYMENT, then calls gateway.create_intent().

handle_webhook          — Called from the webhook endpoints after signature
                          verification by the gateway adapter.  Maps to invoice,
                          checks amount == invoice.total (never trusts gateway amount
                          blindly), transitions state, closes order, resets table.
                          Idempotent: a replay with the same gateway_transaction_id
                          returns the existing paid invoice without a second credit.
                          Last-resort guard: UNIQUE(gateway_transaction_id) in the DB
                          catches any race that slips through the row lock.

manual_override         — ADMIN only. Marks any non-PAID invoice PAID with a reason.
                          Audited; requires reason.

All multi-step operations run in ONE transaction with SELECT ... FOR UPDATE on the
invoice and order rows.  Commit happens only after all steps succeed.
"""

import uuid
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models.audit_log import AuditLog
from app.models.enums import (
    InvoiceStatus,
    OrderItemStatus,
    OrderStatus,
    PaymentMethod,
    Role,
    SessionStatus,
)
from app.models.invoice import Invoice
from app.models.order import Order, OrderItem
from app.models.restaurant import RestaurantSettings
from app.models.table import TableSession
from app.models.user import User
from app.payments.base import PaymentGateway
from app.realtime.events import InvoicePaidEvent, OrderClosedEvent
from app.realtime.manager import _fire, manager as rt_manager
from app.services import numbering_service
from app.services.order_state import assert_valid_order_transition
from app.services.payment_state import InvoiceError, assert_valid_invoice_transition

_TWO_PLACES = Decimal("0.01")


def _q(value: Decimal) -> Decimal:
    return value.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _close_order_and_reset_table(
    db: Session,
    order: Order,
    restaurant_id: uuid.UUID,
) -> None:
    """
    Marks the order CLOSED and invalidates all active table sessions.
    Called inside an existing transaction — does NOT commit.
    """
    order.status = OrderStatus.CLOSED
    now = datetime.now(timezone.utc)
    sessions = db.execute(
        select(TableSession).where(
            TableSession.table_id == order.table_id,
            TableSession.restaurant_id == restaurant_id,
            TableSession.status == SessionStatus.ACTIVE,
        )
    ).scalars().all()
    for session in sessions:
        session.status = SessionStatus.INVALIDATED
        session.invalidated_at = now


def _load_settings(db: Session, restaurant_id: uuid.UUID) -> RestaurantSettings | None:
    return db.execute(
        select(RestaurantSettings).where(
            RestaurantSettings.restaurant_id == restaurant_id
        )
    ).scalar_one_or_none()


# ── Public entry points ───────────────────────────────────────────────────────

def record_counter_payment(
    db: Session,
    restaurant_id: uuid.UUID,
    invoice_id: uuid.UUID,
    method: PaymentMethod,
    actor: User,
    idempotency_key: str | None = None,
) -> Invoice:
    """
    Accept a counter payment (CASH / CARD / COUNTER_WALLET).
    Raises InvoiceError on any business rule violation.
    """
    # WAITER permission check (before acquiring any locks)
    if actor.role == Role.WAITER:
        settings = _load_settings(db, restaurant_id)
        if settings is None or not settings.waiter_can_accept_payment:
            raise InvoiceError(
                "Waiters are not permitted to accept payments at this restaurant",
                status_code=403,
            )

    # Lock invoice row — serialises concurrent payment attempts
    invoice = db.execute(
        select(Invoice)
        .where(Invoice.id == invoice_id, Invoice.restaurant_id == restaurant_id)
        .with_for_update()
    ).scalar_one_or_none()
    if invoice is None:
        raise InvoiceError("Invoice not found", status_code=404)

    # Idempotency: if already PAID with the same key, return without re-processing
    if invoice.status == InvoiceStatus.PAID:
        if idempotency_key and invoice.gateway_transaction_id == idempotency_key:
            return invoice
        raise InvoiceError("Invoice is already paid", status_code=409)

    assert_valid_invoice_transition(invoice.status, InvoiceStatus.PAID)

    # Lock order row
    order = db.execute(
        select(Order)
        .where(Order.id == invoice.order_id, Order.restaurant_id == restaurant_id)
        .with_for_update()
    ).scalar_one_or_none()
    if order is None:
        raise InvoiceError("Associated order not found", status_code=404)

    if order.status != OrderStatus.MEAL_FINISHED:
        raise InvoiceError(
            f"Cannot accept payment: order is {order.status.value}, "
            "expected MEAL_FINISHED",
            status_code=409,
        )

    prev_status = invoice.status
    invoice.status = InvoiceStatus.PAID
    invoice.payment_method = method
    # Store idempotency key (reuses gateway_transaction_id column; UNIQUE guards replay)
    if idempotency_key:
        invoice.gateway_transaction_id = idempotency_key

    _close_order_and_reset_table(db, order, restaurant_id)

    db.add(AuditLog(
        id=uuid.uuid4(),
        restaurant_id=restaurant_id,
        actor_type=actor.role.value,
        actor_user_id=actor.id,
        entity_type="invoice",
        entity_id=invoice.id,
        action="INVOICE_PAID",
        previous_value={"status": prev_status.value},
        new_value={"status": InvoiceStatus.PAID.value, "method": method.value},
    ))
    db.add(AuditLog(
        id=uuid.uuid4(),
        restaurant_id=restaurant_id,
        actor_type=actor.role.value,
        actor_user_id=actor.id,
        entity_type="order",
        entity_id=order.id,
        action="ORDER_CLOSED",
        previous_value={"status": OrderStatus.MEAL_FINISHED.value},
        new_value={"status": OrderStatus.CLOSED.value},
    ))

    # Save values needed for events before commit (attrs expire on commit).
    _rid_str = str(restaurant_id)
    _inv_id_str = str(invoice.id)
    _inv_num = invoice.invoice_number
    _ord_id_str = str(order.id)
    _ord_num = order.order_number
    _tid_str = str(order.table_id)
    _total_str = str(invoice.total)
    _method_str = method.value

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # UNIQUE violation on gateway_transaction_id = concurrent idempotent duplicate
        existing = db.execute(
            select(Invoice).where(Invoice.id == invoice_id)
        ).scalar_one_or_none()
        if existing and existing.status == InvoiceStatus.PAID:
            return existing
        raise InvoiceError(
            "Payment conflict: another request processed this invoice simultaneously",
            status_code=409,
        )

    db.refresh(invoice)

    # Post-commit events — counter AND the customer's table get invoice.paid so the
    # bill page can show "Paid" instantly (the session is invalidated on close, so the
    # client must render from the event, not a refetch).
    _paid_ev = InvoicePaidEvent(
        invoice_id=_inv_id_str,
        invoice_number=_inv_num,
        order_id=_ord_id_str,
        restaurant_id=_rid_str,
        total=_total_str,
        payment_method=_method_str,
    )
    _fire(rt_manager.broadcast_to_roles(_rid_str, _paid_ev, [Role.COUNTER, Role.ADMIN]))
    _fire(rt_manager.broadcast_to_table(_rid_str, _tid_str, _paid_ev))
    _closed_ev = OrderClosedEvent(
        order_id=_ord_id_str,
        order_number=_ord_num,
        table_id=_tid_str,
        restaurant_id=_rid_str,
    )
    _fire(rt_manager.broadcast_to_roles(_rid_str, _closed_ev, [Role.COUNTER]))
    _fire(rt_manager.broadcast_to_table(_rid_str, _tid_str, _closed_ev))

    return invoice


def close_unpaid(
    db: Session,
    restaurant_id: uuid.UUID,
    order_id: uuid.UUID,
    reason: str,
    actor: User,
) -> Order:
    """
    Close an order WITHOUT payment — cancel / walkout / write-off. Voids any active
    invoice (DRAFT/PENDING_PAYMENT → VOID), closes the order, resets the table.
    A reason is required; everything is audited. The house absorbs the loss; nothing
    is marked PAID.
    """
    order = db.execute(
        select(Order)
        .where(Order.id == order_id, Order.restaurant_id == restaurant_id)
        .with_for_update()
    ).scalar_one_or_none()
    if order is None:
        raise InvoiceError("Order not found", status_code=404)
    if order.status == OrderStatus.CLOSED:
        raise InvoiceError("Order is already closed", status_code=409)

    # Void any active (non-terminal, unpaid) invoices on this order.
    active_invoices = db.execute(
        select(Invoice)
        .where(
            Invoice.order_id == order_id,
            Invoice.status.in_([InvoiceStatus.DRAFT, InvoiceStatus.PENDING_PAYMENT]),
        )
        .with_for_update()
    ).scalars().all()
    for inv in active_invoices:
        prev = inv.status
        inv.status = InvoiceStatus.VOID
        db.add(AuditLog(
            id=uuid.uuid4(),
            restaurant_id=restaurant_id,
            actor_type=actor.role.value,
            actor_user_id=actor.id,
            entity_type="invoice",
            entity_id=inv.id,
            action="INVOICE_VOID",
            previous_value={"status": prev.value},
            new_value={"status": InvoiceStatus.VOID.value},
            reason=reason,
        ))

    prev_status = order.status
    _close_order_and_reset_table(db, order, restaurant_id)  # sets CLOSED + invalidates sessions

    db.add(AuditLog(
        id=uuid.uuid4(),
        restaurant_id=restaurant_id,
        actor_type=actor.role.value,
        actor_user_id=actor.id,
        entity_type="order",
        entity_id=order.id,
        action="ORDER_CLOSED_UNPAID",
        previous_value={"status": prev_status.value},
        new_value={"status": OrderStatus.CLOSED.value},
        reason=reason,
    ))

    _oid_str = str(order.id)
    _onum = order.order_number
    _tid_str = str(order.table_id)
    _rid_str = str(restaurant_id)

    db.commit()

    # Tell the customer's table + staff the order is closed (no payment).
    ev = OrderClosedEvent(
        order_id=_oid_str, order_number=_onum, table_id=_tid_str, restaurant_id=_rid_str,
    )
    _fire(rt_manager.broadcast_to_roles(_rid_str, ev, [Role.COUNTER, Role.WAITER]))
    _fire(rt_manager.broadcast_to_table(_rid_str, _tid_str, ev))

    db.refresh(order)
    return order


def quick_bill_and_close(
    db: Session,
    restaurant_id: uuid.UUID,
    order_id: uuid.UUID,
    method: PaymentMethod,
    actor: User,
    idempotency_key: str | None = None,
) -> Invoice:
    """
    One-tap "bill & clear the table": for an OPEN order whose customer has already
    requested the bill, generate the invoice, mark it PAID with the chosen counter
    method, close the order, and reset the table — all in ONE transaction.

    This is the collapsed equivalent of Move-to-Billing → Generate Invoice →
    Collect Payment. It records revenue exactly like record_counter_payment (a PAID
    invoice + invoice.paid/order.closed events); it never skips the money.

    Guards:
    - WAITER may only use this when waiter_can_accept_payment is enabled (403).
    - The customer must have requested the bill (bill_requested_at set) — 409 if not.
    - No item may still be awaiting waiter approval — 409 if any is.
    Idempotent: an optional Idempotency-Key is stored on the invoice
    (gateway_transaction_id, UNIQUE); a replay returns the same PAID invoice.
    """
    # WAITER permission check (before acquiring any locks) — mirrors record_counter_payment.
    if actor.role == Role.WAITER:
        settings = _load_settings(db, restaurant_id)
        if settings is None or not settings.waiter_can_accept_payment:
            raise InvoiceError(
                "Waiters are not permitted to accept payments at this restaurant",
                status_code=403,
            )

    # Lock the order row — serialises concurrent bill/clear + payment attempts.
    order = db.execute(
        select(Order)
        .where(Order.id == order_id, Order.restaurant_id == restaurant_id)
        .with_for_update()
    ).scalar_one_or_none()
    if order is None:
        raise InvoiceError("Order not found", status_code=404)

    # Replay: the table was already billed & cleared. If the same idempotency key
    # produced the existing PAID invoice, return it; otherwise this is a genuine
    # "already closed" conflict.
    if order.status == OrderStatus.CLOSED:
        paid = db.execute(
            select(Invoice)
            .where(
                Invoice.order_id == order_id,
                Invoice.restaurant_id == restaurant_id,
                Invoice.status == InvoiceStatus.PAID,
            )
            .order_by(Invoice.created_at.desc())
        ).scalars().first()
        if paid is not None and idempotency_key and paid.gateway_transaction_id == idempotency_key:
            return paid
        raise InvoiceError("Order is already closed", status_code=409)

    if order.status != OrderStatus.OPEN:
        raise InvoiceError(
            f"Quick bill needs an OPEN order (current status: {order.status.value}). "
            "Use the billing screen to complete an order already in billing.",
            status_code=409,
        )

    # Gate: a table can only be billed after the customer requested the bill.
    if order.bill_requested_at is None:
        raise InvoiceError(
            "Cannot bill: the customer has not requested the bill yet",
            status_code=409,
        )

    # Gate: a batch awaiting waiter approval must be resolved before billing.
    pending = db.scalar(
        select(OrderItem.id).where(
            OrderItem.order_id == order_id,
            OrderItem.restaurant_id == restaurant_id,
            OrderItem.status == OrderItemStatus.PENDING_APPROVAL,
        ).limit(1)
    )
    if pending is not None:
        raise InvoiceError(
            "Order has items awaiting approval — approve or reject them first",
            status_code=409,
        )

    # Defensive: no active invoice should exist on an OPEN order, but never bill twice.
    existing = db.execute(
        select(Invoice).where(
            Invoice.order_id == order_id,
            Invoice.status.in_(
                [InvoiceStatus.DRAFT, InvoiceStatus.PENDING_PAYMENT, InvoiceStatus.PAID]
            ),
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise InvoiceError(
            f"Order already has an active invoice (status: {existing.status.value}).",
            status_code=409,
        )

    # Billable items (not cancelled, not awaiting approval) + their addons.
    items = db.execute(
        select(OrderItem)
        .where(
            OrderItem.order_id == order_id,
            OrderItem.status.notin_(
                [OrderItemStatus.CANCELLED, OrderItemStatus.PENDING_APPROVAL]
            ),
        )
        .options(selectinload(OrderItem.addons))
    ).scalars().all()
    if not items:
        raise InvoiceError("No billable items on this order", status_code=400)

    # Compute subtotal + tax from item snapshots — never from any client value.
    # Mirrors invoice_service.generate_invoice; no discount on the one-tap path.
    subtotal = Decimal("0")
    tax_total = Decimal("0")
    for item in items:
        addon_sum = sum((a.addon_price for a in item.addons), Decimal("0"))
        line_sub = item.quantity * (item.unit_price + addon_sum)
        subtotal += line_sub
        tax_total += line_sub * item.tax_rate / Decimal("100")
    subtotal = _q(subtotal)
    tax_total = _q(tax_total)
    total = _q(subtotal + tax_total)

    # OPEN -> MEAL_FINISHED (validated) — the resting state we pass through.
    assert_valid_order_transition(order.status, OrderStatus.MEAL_FINISHED)
    order.status = OrderStatus.MEAL_FINISHED
    db.add(AuditLog(
        id=uuid.uuid4(),
        restaurant_id=restaurant_id,
        actor_type=actor.role.value,
        actor_user_id=actor.id,
        entity_type="order",
        entity_id=order.id,
        action="ORDER_MEAL_FINISHED",
        previous_value={"status": OrderStatus.OPEN.value},
        new_value={"status": OrderStatus.MEAL_FINISHED.value, "via": "quick_bill"},
    ))

    # Gapless invoice number: INV-YYYY-NNNN.
    seq = numbering_service.next_number(db, restaurant_id, "invoice")
    year = datetime.now(timezone.utc).year
    invoice_number = f"INV-{year}-{seq:04d}"

    invoice = Invoice(
        id=uuid.uuid4(),
        restaurant_id=restaurant_id,
        order_id=order_id,
        invoice_number=invoice_number,
        status=InvoiceStatus.DRAFT,
        subtotal=subtotal,
        discount=Decimal("0.00"),
        tax_total=tax_total,
        total=total,
    )
    db.add(invoice)
    db.add(AuditLog(
        id=uuid.uuid4(),
        restaurant_id=restaurant_id,
        actor_type=actor.role.value,
        actor_user_id=actor.id,
        entity_type="invoice",
        entity_id=invoice.id,
        action="INVOICE_GENERATED",
        previous_value=None,
        new_value={
            "invoice_number": invoice_number,
            "subtotal": str(subtotal),
            "discount": "0.00",
            "tax_total": str(tax_total),
            "total": str(total),
            "via": "quick_bill",
        },
    ))

    # DRAFT -> PAID (validated) with the chosen counter method.
    assert_valid_invoice_transition(invoice.status, InvoiceStatus.PAID)
    invoice.status = InvoiceStatus.PAID
    invoice.payment_method = method
    if idempotency_key:
        invoice.gateway_transaction_id = idempotency_key
    db.add(AuditLog(
        id=uuid.uuid4(),
        restaurant_id=restaurant_id,
        actor_type=actor.role.value,
        actor_user_id=actor.id,
        entity_type="invoice",
        entity_id=invoice.id,
        action="INVOICE_PAID",
        previous_value={"status": InvoiceStatus.DRAFT.value},
        new_value={"status": InvoiceStatus.PAID.value, "method": method.value},
    ))

    # MEAL_FINISHED -> CLOSED + invalidate the table's active sessions (clears the table).
    _close_order_and_reset_table(db, order, restaurant_id)
    db.add(AuditLog(
        id=uuid.uuid4(),
        restaurant_id=restaurant_id,
        actor_type=actor.role.value,
        actor_user_id=actor.id,
        entity_type="order",
        entity_id=order.id,
        action="ORDER_CLOSED",
        previous_value={"status": OrderStatus.MEAL_FINISHED.value},
        new_value={"status": OrderStatus.CLOSED.value},
    ))

    # Save values needed for events before commit (attrs expire on commit).
    _rid_str = str(restaurant_id)
    _inv_id_str = str(invoice.id)
    _inv_num = invoice.invoice_number
    _ord_id_str = str(order.id)
    _ord_num = order.order_number
    _tid_str = str(order.table_id)
    _total_str = str(invoice.total)
    _method_str = method.value

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # UNIQUE violation on gateway_transaction_id = concurrent idempotent duplicate.
        existing_paid = db.execute(
            select(Invoice).where(
                Invoice.order_id == order_id,
                Invoice.restaurant_id == restaurant_id,
                Invoice.status == InvoiceStatus.PAID,
            )
        ).scalars().first()
        if existing_paid is not None:
            return existing_paid
        raise InvoiceError(
            "Payment conflict: another request billed this table simultaneously",
            status_code=409,
        )

    db.refresh(invoice)

    # Post-commit events — identical to record_counter_payment: the counter/admin and
    # the customer's table both learn the invoice is paid and the order is closed.
    _paid_ev = InvoicePaidEvent(
        invoice_id=_inv_id_str,
        invoice_number=_inv_num,
        order_id=_ord_id_str,
        restaurant_id=_rid_str,
        total=_total_str,
        payment_method=_method_str,
    )
    _fire(rt_manager.broadcast_to_roles(_rid_str, _paid_ev, [Role.COUNTER, Role.ADMIN]))
    _fire(rt_manager.broadcast_to_table(_rid_str, _tid_str, _paid_ev))
    _closed_ev = OrderClosedEvent(
        order_id=_ord_id_str,
        order_number=_ord_num,
        table_id=_tid_str,
        restaurant_id=_rid_str,
    )
    _fire(rt_manager.broadcast_to_roles(_rid_str, _closed_ev, [Role.COUNTER, Role.WAITER]))
    _fire(rt_manager.broadcast_to_table(_rid_str, _tid_str, _closed_ev))

    return invoice


def create_payment_intent(
    db: Session,
    restaurant_id: uuid.UUID,
    invoice_id: uuid.UUID,
    gateway: PaymentGateway,
    session: TableSession,
) -> dict:
    """
    Initiate a gateway payment for an invoice (customer-facing).
    Validates QR payment is enabled, verifies the invoice belongs to the
    session's table, transitions to PENDING_PAYMENT, then calls the gateway.
    """
    settings = _load_settings(db, restaurant_id)
    if settings is None or not settings.enable_qr_payment:
        raise InvoiceError(
            "QR gateway payment is not enabled for this restaurant",
            status_code=403,
        )

    # Lock invoice
    invoice = db.execute(
        select(Invoice)
        .where(Invoice.id == invoice_id, Invoice.restaurant_id == restaurant_id)
        .with_for_update()
    ).scalar_one_or_none()
    if invoice is None:
        raise InvoiceError("Invoice not found", status_code=404)

    # Verify the invoice's order belongs to the caller's table
    order = db.execute(
        select(Order).where(
            Order.id == invoice.order_id,
            Order.table_id == session.table_id,
            Order.restaurant_id == restaurant_id,
        )
    ).scalar_one_or_none()
    if order is None:
        raise InvoiceError("Invoice not found or not associated with your table", status_code=404)

    # Idempotent: already in PENDING_PAYMENT — re-generate intent params (no state change)
    if invoice.status == InvoiceStatus.PENDING_PAYMENT:
        try:
            return gateway.create_intent(invoice)
        except ValueError as exc:
            raise InvoiceError(str(exc), status_code=502)

    assert_valid_invoice_transition(invoice.status, InvoiceStatus.PENDING_PAYMENT)

    # Call gateway BEFORE committing — if it fails, invoice stays DRAFT
    try:
        intent_data = gateway.create_intent(invoice)
    except ValueError as exc:
        raise InvoiceError(f"Payment gateway error: {exc}", status_code=502)

    invoice.status = InvoiceStatus.PENDING_PAYMENT
    db.add(AuditLog(
        id=uuid.uuid4(),
        restaurant_id=restaurant_id,
        actor_type="CUSTOMER_SESSION",
        actor_user_id=None,
        entity_type="invoice",
        entity_id=invoice.id,
        action="INVOICE_PAYMENT_INITIATED",
        previous_value={"status": InvoiceStatus.DRAFT.value},
        new_value={"status": InvoiceStatus.PENDING_PAYMENT.value},
    ))
    db.commit()
    return intent_data


def handle_webhook(
    db: Session,
    gateway: PaymentGateway,
    gateway_name: str,
    headers: dict,
    raw_body: bytes,
) -> Invoice:
    """
    Process a gateway callback (called by webhook endpoints after receiving raw bytes).

    Security contract:
    - Signature verification happens INSIDE gateway.verify_webhook(); ValueError → 400.
    - Amount from gateway is compared server-side with invoice.total; mismatch → reject.
    - gateway_transaction_id uniqueness is the last-resort replay guard.
    - All state changes are in ONE transaction with FOR UPDATE.
    """
    # 1. Verify signature — ValueError on any failure
    try:
        payload = gateway.verify_webhook(headers, raw_body)
    except ValueError as exc:
        raise InvoiceError(str(exc), status_code=400)

    # 2. Map invoice reference
    try:
        invoice_id = uuid.UUID(payload.invoice_ref)
    except ValueError:
        raise InvoiceError("Webhook contains invalid invoice reference", status_code=400)

    # 3. Lock invoice (no restaurant_id filter — webhook has no tenant ctx)
    invoice = db.execute(
        select(Invoice)
        .where(Invoice.id == invoice_id)
        .with_for_update()
    ).scalar_one_or_none()
    if invoice is None:
        raise InvoiceError("Invoice not found", status_code=404)

    restaurant_id = invoice.restaurant_id

    # 4. Idempotency: same transaction already processed
    if invoice.gateway_transaction_id == payload.transaction_id:
        if invoice.status in (InvoiceStatus.PAID, InvoiceStatus.FAILED):
            return invoice  # Replay — no-op, return existing state
        # Same transaction ID but different status — unusual; surface as conflict
        raise InvoiceError(
            f"Transaction {payload.transaction_id} already recorded "
            f"with status {invoice.status.value}",
            status_code=409,
        )

    # 5. Reject if already in a terminal state via a different path
    if invoice.status in (InvoiceStatus.PAID, InvoiceStatus.FAILED, InvoiceStatus.VOID):
        raise InvoiceError(
            f"Invoice is already in terminal state: {invoice.status.value}",
            status_code=409,
        )

    # 6. Amount integrity check — never auto-trust gateway-supplied amount
    if payload.amount != invoice.total:
        db.add(AuditLog(
            id=uuid.uuid4(),
            restaurant_id=restaurant_id,
            actor_type=gateway_name.upper(),
            actor_user_id=None,
            entity_type="invoice",
            entity_id=invoice.id,
            action="WEBHOOK_AMOUNT_MISMATCH",
            previous_value={"invoice_total": str(invoice.total)},
            new_value={
                "gateway_amount": str(payload.amount),
                "transaction_id": payload.transaction_id,
                "gateway": gateway_name,
            },
        ))
        db.commit()
        raise InvoiceError(
            f"Payment amount mismatch: gateway sent {payload.amount}, "
            f"invoice total is {invoice.total}. Payment not credited.",
            status_code=400,
        )

    prev_status = invoice.status

    # 7a. FAILED path
    if payload.status == "FAILED":
        assert_valid_invoice_transition(invoice.status, InvoiceStatus.FAILED)
        invoice.status = InvoiceStatus.FAILED
        invoice.gateway_transaction_id = payload.transaction_id
        db.add(AuditLog(
            id=uuid.uuid4(),
            restaurant_id=restaurant_id,
            actor_type=gateway_name.upper(),
            actor_user_id=None,
            entity_type="invoice",
            entity_id=invoice.id,
            action="INVOICE_PAYMENT_FAILED",
            previous_value={"status": prev_status.value},
            new_value={"status": InvoiceStatus.FAILED.value, "gateway": gateway_name},
        ))
        db.commit()
        db.refresh(invoice)
        return invoice

    # 7b. PAID path
    if payload.status == "PAID":
        assert_valid_invoice_transition(invoice.status, InvoiceStatus.PAID)

        order = db.execute(
            select(Order)
            .where(Order.id == invoice.order_id)
            .with_for_update()
        ).scalar_one_or_none()
        if order is None:
            raise InvoiceError("Associated order not found", status_code=500)

        if order.status != OrderStatus.MEAL_FINISHED:
            raise InvoiceError(
                f"Order in unexpected state: {order.status.value}",
                status_code=409,
            )

        invoice.status = InvoiceStatus.PAID
        invoice.payment_method = PaymentMethod.QR_GATEWAY
        invoice.gateway_transaction_id = payload.transaction_id

        _close_order_and_reset_table(db, order, restaurant_id)

        db.add(AuditLog(
            id=uuid.uuid4(),
            restaurant_id=restaurant_id,
            actor_type=gateway_name.upper(),
            actor_user_id=None,
            entity_type="invoice",
            entity_id=invoice.id,
            action="INVOICE_PAID_VIA_GATEWAY",
            previous_value={"status": prev_status.value},
            new_value={
                "status": InvoiceStatus.PAID.value,
                "gateway": gateway_name,
                "transaction_id": payload.transaction_id,
            },
        ))
        db.add(AuditLog(
            id=uuid.uuid4(),
            restaurant_id=restaurant_id,
            actor_type=gateway_name.upper(),
            actor_user_id=None,
            entity_type="order",
            entity_id=order.id,
            action="ORDER_CLOSED",
            previous_value={"status": OrderStatus.MEAL_FINISHED.value},
            new_value={"status": OrderStatus.CLOSED.value},
        ))

        # Save before commit.
        _rid_str = str(restaurant_id)
        _inv_id_str = str(invoice.id)
        _inv_num = invoice.invoice_number
        _ord_id_str = str(order.id)
        _ord_num = order.order_number
        _tid_str = str(order.table_id)
        _total_str = str(invoice.total)

        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            # UNIQUE violation on gateway_transaction_id — concurrent replay guard
            existing = db.execute(
                select(Invoice).where(Invoice.id == invoice_id)
            ).scalar_one_or_none()
            if existing and existing.status == InvoiceStatus.PAID:
                return existing
            raise InvoiceError(
                "Payment conflict: duplicate transaction detected",
                status_code=409,
            )

        db.refresh(invoice)

        # Post-commit events — staff + the customer's table see invoice.paid.
        _paid_ev = InvoicePaidEvent(
            invoice_id=_inv_id_str,
            invoice_number=_inv_num,
            order_id=_ord_id_str,
            restaurant_id=_rid_str,
            total=_total_str,
            payment_method=PaymentMethod.QR_GATEWAY.value,
        )
        _fire(rt_manager.broadcast_to_roles(_rid_str, _paid_ev, [Role.COUNTER, Role.ADMIN]))
        _fire(rt_manager.broadcast_to_table(_rid_str, _tid_str, _paid_ev))
        _closed_ev = OrderClosedEvent(
            order_id=_ord_id_str,
            order_number=_ord_num,
            table_id=_tid_str,
            restaurant_id=_rid_str,
        )
        _fire(rt_manager.broadcast_to_roles(_rid_str, _closed_ev, [Role.COUNTER]))
        _fire(rt_manager.broadcast_to_table(_rid_str, _tid_str, _closed_ev))

        return invoice

    raise InvoiceError(
        f"Unrecognised payment status from gateway: {payload.status}",
        status_code=400,
    )


def manual_override(
    db: Session,
    restaurant_id: uuid.UUID,
    invoice_id: uuid.UUID,
    reason: str,
    actor: User,
) -> Invoice:
    """
    ADMIN-only: mark any non-PAID invoice as PAID with a required reason.
    Audited. Closes the order and resets the table.
    """
    invoice = db.execute(
        select(Invoice)
        .where(Invoice.id == invoice_id, Invoice.restaurant_id == restaurant_id)
        .with_for_update()
    ).scalar_one_or_none()
    if invoice is None:
        raise InvoiceError("Invoice not found", status_code=404)

    if invoice.status == InvoiceStatus.PAID:
        raise InvoiceError("Invoice is already paid", status_code=409)

    prev_status = invoice.status
    assert_valid_invoice_transition(invoice.status, InvoiceStatus.PAID)

    order = db.execute(
        select(Order)
        .where(Order.id == invoice.order_id, Order.restaurant_id == restaurant_id)
        .with_for_update()
    ).scalar_one_or_none()
    if order is None:
        raise InvoiceError("Associated order not found", status_code=404)

    if order.status != OrderStatus.MEAL_FINISHED:
        raise InvoiceError(
            f"Cannot override payment: order is {order.status.value}, "
            "expected MEAL_FINISHED",
            status_code=409,
        )

    invoice.status = InvoiceStatus.PAID
    invoice.payment_method = PaymentMethod.MANUAL_OVERRIDE

    _close_order_and_reset_table(db, order, restaurant_id)

    db.add(AuditLog(
        id=uuid.uuid4(),
        restaurant_id=restaurant_id,
        actor_type=actor.role.value,
        actor_user_id=actor.id,
        entity_type="invoice",
        entity_id=invoice.id,
        action="INVOICE_MANUAL_OVERRIDE",
        previous_value={"status": prev_status.value},
        new_value={
            "status": InvoiceStatus.PAID.value,
            "method": PaymentMethod.MANUAL_OVERRIDE.value,
        },
        reason=reason,
    ))
    db.add(AuditLog(
        id=uuid.uuid4(),
        restaurant_id=restaurant_id,
        actor_type=actor.role.value,
        actor_user_id=actor.id,
        entity_type="order",
        entity_id=order.id,
        action="ORDER_CLOSED",
        previous_value={"status": OrderStatus.MEAL_FINISHED.value},
        new_value={"status": OrderStatus.CLOSED.value},
        reason=reason,
    ))

    # Save before commit.
    _rid_str = str(restaurant_id)
    _inv_id_str = str(invoice.id)
    _inv_num = invoice.invoice_number
    _ord_id_str = str(order.id)
    _ord_num = order.order_number
    _tid_str = str(order.table_id)
    _total_str = str(invoice.total)

    db.commit()
    db.refresh(invoice)

    # Post-commit events — staff + the customer's table see invoice.paid.
    _paid_ev = InvoicePaidEvent(
        invoice_id=_inv_id_str,
        invoice_number=_inv_num,
        order_id=_ord_id_str,
        restaurant_id=_rid_str,
        total=_total_str,
        payment_method=PaymentMethod.MANUAL_OVERRIDE.value,
    )
    _fire(rt_manager.broadcast_to_roles(_rid_str, _paid_ev, [Role.COUNTER, Role.ADMIN]))
    _fire(rt_manager.broadcast_to_table(_rid_str, _tid_str, _paid_ev))
    _closed_ev = OrderClosedEvent(
        order_id=_ord_id_str,
        order_number=_ord_num,
        table_id=_tid_str,
        restaurant_id=_rid_str,
    )
    _fire(rt_manager.broadcast_to_roles(_rid_str, _closed_ev, [Role.COUNTER]))
    _fire(rt_manager.broadcast_to_table(_rid_str, _tid_str, _closed_ev))

    return invoice
