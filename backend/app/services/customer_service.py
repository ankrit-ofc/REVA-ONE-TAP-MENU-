"""
Customer contact capture.

The customer submits { email, name?, phone? } from the customer web app. This
module owns three things:

1. Normalisation — ONE place trims and lowercases an email (`normalize_email`).
   The unique index is `(restaurant_id, email)` on the raw column, not a
   functional index, so normalising before every read AND write is what makes
   "Ram@X.com" and "ram@x.com" the same row rather than two.
2. Upsert — same email again updates the existing row (filling in name/phone
   when newly provided) instead of creating a duplicate. It never blanks a
   value we already hold.
3. Linking the capture to the visit — see capture_contact below for the carrier
   (orders.customer_id) vs. analytics link (invoices.customer_id) split.

PII rule: email and phone are NEVER written to the log or to an audit_logs
value. Audit rows record THAT contact was captured, not what it was.
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.customer import Customer
from app.models.enums import InvoiceStatus, OrderStatus, SessionStatus
from app.models.invoice import Invoice
from app.models.order import Order
from app.models.table import TableSession
from app.schemas.customer import CustomerContactRequest

logger = logging.getLogger("app.customers")


class CustomerCaptureError(Exception):
    """Business-rule failure; carries the HTTP status the API should return."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def normalize_email(raw: str) -> str:
    """
    The single normalisation point. Trim, then lowercase.

    Every lookup and every insert goes through here — if a caller skips it, the
    unique index will happily store a second row for the same human.
    """
    return raw.strip().lower()


def redact_email(email: str) -> str:
    """`ram@example.com` -> `r***@example.com`, for logs. Phone is never logged."""
    local, _, domain = email.partition("@")
    if not domain:
        return "***"
    return f"{local[:1]}***@{domain}"


def upsert_customer(
    db: Session,
    restaurant_id: uuid.UUID,
    email: str,
    name: str | None,
    phone: str | None,
) -> Customer:
    """
    Find-or-create the customer for (restaurant_id, normalised email).

    On a repeat submission the existing row is updated: name/phone are filled in
    when a new non-empty value arrives, and left alone otherwise. A later
    submission that omits the name must not erase a name we already have.

    Does not commit — the caller owns the transaction.
    """
    normalized = normalize_email(email)

    customer = db.execute(
        select(Customer).where(
            Customer.restaurant_id == restaurant_id,
            Customer.email == normalized,
        )
    ).scalar_one_or_none()

    if customer is None:
        customer = Customer(
            id=uuid.uuid4(),
            restaurant_id=restaurant_id,
            email=normalized,
            name=name,
            phone=phone,
        )
        db.add(customer)
        try:
            db.flush()
        except IntegrityError:
            # A concurrent submission of the same address won the race; adopt it.
            db.rollback()
            customer = db.execute(
                select(Customer).where(
                    Customer.restaurant_id == restaurant_id,
                    Customer.email == normalized,
                )
            ).scalar_one_or_none()
            if customer is None:
                raise
            _fill_in(customer, name, phone)
        return customer

    _fill_in(customer, name, phone)
    customer.updated_at = datetime.now(timezone.utc)
    db.flush()
    return customer


def _fill_in(customer: Customer, name: str | None, phone: str | None) -> None:
    """Fill optional fields when newly provided; never overwrite with NULL."""
    if name is not None:
        customer.name = name
    if phone is not None:
        customer.phone = phone


def _live_order(db: Session, session: TableSession) -> Order | None:
    """The table's still-open order, locked. Tenant-scoped."""
    return db.execute(
        select(Order)
        .where(
            Order.table_id == session.table_id,
            Order.restaurant_id == session.restaurant_id,
            Order.status != OrderStatus.CLOSED,
        )
        .order_by(Order.created_at.desc())
        .limit(1)
        .with_for_update()
    ).scalars().first()


def _invoice_for_visit(db: Session, session: TableSession) -> Invoice | None:
    """
    The invoice belonging to THIS session's visit, locked. Tenant-scoped.

    For a grace-window (INVALIDATED) session the `created_at <= invalidated_at`
    filter is the load-bearing part: payment creates/settles the invoice and
    invalidates the session inside one transaction, so this session's own
    invoice always predates its invalidated_at, while a later party's invoice
    (new session, new order) is created strictly after it and is excluded. A
    stale-but-still-in-window token therefore cannot reach the next diner's bill.
    """
    order_ids = select(Order.id).where(
        Order.table_id == session.table_id,
        Order.restaurant_id == session.restaurant_id,
    )

    stmt = (
        select(Invoice)
        .where(
            Invoice.order_id.in_(order_ids),
            Invoice.restaurant_id == session.restaurant_id,
            Invoice.status != InvoiceStatus.VOID,
        )
        .order_by(Invoice.created_at.desc())
        .limit(1)
        .with_for_update()
    )

    if session.status == SessionStatus.INVALIDATED and session.invalidated_at is not None:
        stmt = stmt.where(Invoice.created_at <= session.invalidated_at)

    return db.execute(stmt).scalars().first()


def capture_contact(
    db: Session,
    session: TableSession,
    payload: CustomerContactRequest,
) -> None:
    """
    Record the diner's contact details and attach them to this visit.

    Idempotent: submitting twice for the same session updates the customer row
    and re-attaches the same link, rather than erroring.

    Attaches to whichever of the two links exists at the time:
      - orders.customer_id   while the order is still open (the "Request Bill"
                             entry point, before any invoice exists), and
      - invoices.customer_id as soon as there is an invoice — set here for the
        post-payment entry point, and copied from the order carrier by
        invoice_service.generate_invoice / payment_service.quick_bill_and_close
        for the pre-payment one.

    Raises CustomerCaptureError(409) rather than reassigning an invoice that is
    already attached to a DIFFERENT customer — a settled bill's payer is not
    something a second submission gets to rewrite.
    """
    customer = upsert_customer(
        db,
        restaurant_id=session.restaurant_id,
        email=payload.email,
        name=payload.name,
        phone=payload.phone,
    )

    invoice = _invoice_for_visit(db, session)
    if invoice is not None:
        if invoice.customer_id is not None and invoice.customer_id != customer.id:
            db.rollback()
            raise CustomerCaptureError(
                "This bill is already linked to a different customer",
                status_code=409,
            )
        invoice.customer_id = customer.id

    order = _live_order(db, session)
    if order is not None:
        order.customer_id = customer.id

    db.add(AuditLog(
        id=uuid.uuid4(),
        restaurant_id=session.restaurant_id,
        actor_type="CUSTOMER_SESSION",
        actor_user_id=None,
        entity_type="customer",
        entity_id=customer.id,
        action="CUSTOMER_CONTACT_CAPTURED",
        previous_value=None,
        # No email, name, or phone here — audit rows are widely readable and
        # this one only needs to record that a capture happened, and where.
        new_value={
            "table_id": str(session.table_id),
            "invoice_id": str(invoice.id) if invoice is not None else None,
            "has_name": payload.name is not None,
            "has_phone": payload.phone is not None,
        },
    ))

    db.commit()

    # Captured AFTER the bill was settled (the post-payment entry point) — the
    # receipt will not be triggered by any later payment event, so send it now.
    # Import here to keep the service import graph acyclic.
    if invoice is not None and invoice.status == InvoiceStatus.PAID:
        from app.services import receipt_email

        receipt_email.send_receipt_safely(db, session.restaurant_id, invoice.id)
