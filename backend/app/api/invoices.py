"""
Invoice and payment endpoints (Phase 7).

Staff (COUNTER / ADMIN / WAITER):
  POST   /invoices              — generate invoice for a MEAL_FINISHED order
  GET    /invoices/{id}         — fetch invoice by ID (tenant-scoped)
  POST   /invoices/{id}/pay     — accept counter payment (CASH/CARD/COUNTER_WALLET)
                                  WAITER allowed only if waiter_can_accept_payment=true
  POST   /invoices/{id}/override — ADMIN only; manual override with required reason

Customer (session):
  POST   /invoices/{id}/intent  — initiate a QR gateway payment
  GET    /invoices/my-order     — fetch the invoice for the caller's current order

Idempotency-Key header on /pay is optional; when provided it is stored as
gateway_transaction_id and a duplicate with the same key returns 200 (no-op).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_session, get_db, require_role, tenant_scope
from app.models.enums import InvoiceStatus, OrderStatus, Role
from app.models.invoice import Invoice
from app.models.order import Order
from app.models.table import TableSession
from app.models.user import User
from app.payments.esewa import ESewaGateway
from app.payments.fonepay import FonepayGateway
from app.payments.khalti import KhaltiGateway
from app.core.config import settings
from app.schemas.invoice import (
    CounterPaymentRequest,
    GatewayIntentRequest,
    GenerateInvoiceRequest,
    InvoiceResponse,
    ManualOverrideRequest,
    ReceiptResponse,
)
from app.services import invoice_service, payment_service
from app.services.payment_state import InvoiceError

router = APIRouter(prefix="/invoices", tags=["invoices"])

# WAITER included for generate/get/pay; the waiter_can_accept_payment setting is
# enforced in the service layer for the money operations (generate + pay).
_CounterDep = Annotated[User, Depends(require_role(Role.COUNTER, Role.ADMIN, Role.WAITER))]
_AdminDep   = Annotated[User, Depends(require_role(Role.ADMIN))]
_PayerDep   = Annotated[User, Depends(require_role(Role.COUNTER, Role.ADMIN, Role.WAITER))]
_RidDep     = Annotated[uuid.UUID, Depends(tenant_scope)]
_DbDep      = Annotated[Session, Depends(get_db)]
_SessionDep = Annotated[TableSession, Depends(get_current_session)]


def _gateway_for(name: str):
    if name == "esewa":
        return ESewaGateway(settings)
    if name == "khalti":
        return KhaltiGateway(settings)
    if name == "fonepay":
        return FonepayGateway(settings)
    raise HTTPException(status_code=400, detail=f"Unknown gateway: {name}")


# ── Customer endpoint must be declared BEFORE /{invoice_id} to avoid shadowing ──

@router.get("/my-order", response_model=InvoiceResponse | None)
def get_my_order_invoice(
    session: _SessionDep,
    db: _DbDep,
) -> InvoiceResponse | None:
    """
    Customer: returns the most-recent non-VOID invoice for the current table's order.
    Returns null if no invoice has been generated yet.
    """
    order = db.execute(
        select(Order).where(
            Order.table_id == session.table_id,
            Order.restaurant_id == session.restaurant_id,
            Order.status.in_([OrderStatus.MEAL_FINISHED, OrderStatus.CLOSED]),
        )
    ).scalar_one_or_none()
    if order is None:
        return None

    invoice = db.execute(
        select(Invoice)
        .where(
            Invoice.order_id == order.id,
            Invoice.status != InvoiceStatus.VOID,
        )
        .order_by(Invoice.created_at.desc())
    ).scalar_one_or_none()
    if invoice is None:
        return None
    return InvoiceResponse.model_validate(invoice)


# ── Staff endpoints ────────────────────────────────────────────────────────────

@router.post("", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
def generate_invoice(
    body: GenerateInvoiceRequest,
    user: _CounterDep,
    restaurant_id: _RidDep,
    db: _DbDep,
) -> InvoiceResponse:
    """Generate a DRAFT invoice for a MEAL_FINISHED order."""
    try:
        inv = invoice_service.generate_invoice(
            db, restaurant_id, body.order_id,
            discount_type=body.discount_type,
            discount_value=body.discount_value,
            actor_type=user.role.value,
            actor_id=user.id,
        )
    except InvoiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    return InvoiceResponse.model_validate(inv)


@router.get("/{invoice_id}", response_model=InvoiceResponse)
def get_invoice(
    invoice_id: uuid.UUID,
    user: _CounterDep,
    restaurant_id: _RidDep,
    db: _DbDep,
) -> InvoiceResponse:
    """Fetch an invoice by ID (tenant-scoped)."""
    invoice = db.execute(
        select(Invoice).where(
            Invoice.id == invoice_id,
            Invoice.restaurant_id == restaurant_id,
        )
    ).scalar_one_or_none()
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return InvoiceResponse.model_validate(invoice)


@router.get("/{invoice_id}/receipt", response_model=ReceiptResponse)
def get_receipt(
    invoice_id: uuid.UUID,
    user: _CounterDep,
    restaurant_id: _RidDep,
    db: _DbDep,
) -> ReceiptResponse:
    """Itemized receipt for thermal printing (invoice totals + order-item snapshots)."""
    try:
        data = invoice_service.build_receipt(db, restaurant_id, invoice_id)
    except InvoiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    return ReceiptResponse.model_validate(data)


@router.post("/{invoice_id}/pay", response_model=InvoiceResponse)
def pay_counter(
    invoice_id: uuid.UUID,
    body: CounterPaymentRequest,
    user: _PayerDep,
    restaurant_id: _RidDep,
    db: _DbDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> InvoiceResponse:
    """
    Accept a counter payment (CASH / CARD / COUNTER_WALLET).
    Optional Idempotency-Key header makes this call safe to retry.
    WAITER role is subject to the waiter_can_accept_payment restaurant setting.
    """
    try:
        inv = payment_service.record_counter_payment(
            db, restaurant_id, invoice_id,
            method=body.method,
            actor=user,
            idempotency_key=idempotency_key,
        )
    except InvoiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    return InvoiceResponse.model_validate(inv)


@router.post("/{invoice_id}/override", response_model=InvoiceResponse)
def manual_override(
    invoice_id: uuid.UUID,
    body: ManualOverrideRequest,
    user: _AdminDep,
    restaurant_id: _RidDep,
    db: _DbDep,
) -> InvoiceResponse:
    """ADMIN only: mark an invoice PAID with a required reason. Fully audited."""
    try:
        inv = payment_service.manual_override(
            db, restaurant_id, invoice_id,
            reason=body.reason,
            actor=user,
        )
    except InvoiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    return InvoiceResponse.model_validate(inv)


# ── Customer gateway intent ────────────────────────────────────────────────────

@router.post("/{invoice_id}/intent", response_model=dict)
def create_payment_intent(
    invoice_id: uuid.UUID,
    body: GatewayIntentRequest,
    session: _SessionDep,
    db: _DbDep,
) -> dict:
    """
    Customer: start a QR gateway payment for an invoice.
    Returns gateway-specific parameters (signed form fields / payment URL / QR params).
    Requires restaurant setting enable_qr_payment=true.
    """
    gateway = _gateway_for(body.gateway)
    try:
        return payment_service.create_payment_intent(
            db, session.restaurant_id, invoice_id, gateway, session,
        )
    except InvoiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
