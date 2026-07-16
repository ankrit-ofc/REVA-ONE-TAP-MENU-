"""
Counter-staff endpoints (Phase 6).

All endpoints require COUNTER or ADMIN role.  restaurant_id is derived from
the verified JWT via tenant_scope — never from the request body or query params.

Transitions exposed:
  OPEN          -> MEAL_FINISHED  (POST /counter/orders/{id}/meal-finished)
  MEAL_FINISHED -> OPEN           (POST /counter/orders/{id}/reopen)
      — only when restaurant_settings.allow_order_reopen is True
      — requires a non-trivial reason (3–500 chars)

Invoice/payment endpoints are Phase 7 — not implemented here.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.deps import get_db, require_role, tenant_scope
from app.models.enums import OrderStatus, Role
from app.models.order import Order
from app.models.restaurant import RestaurantSettings
from app.models.user import User
from app.schemas.invoice import CounterPaymentRequest, InvoiceResponse
from app.schemas.menu import PrintConfigResponse
from app.schemas.order import CounterOrderSummary, OrderResponse
from app.schemas.workflow import ReopenRequest
from app.services import menu_service, order_service, payment_service
from app.services.order_state import OrderError
from app.services.payment_state import InvoiceError

router = APIRouter(prefix="/counter", tags=["counter"])

# Billing is shared by counter and (when enabled) waiter. Waiter money-ops are
# additionally gated by the waiter_can_accept_payment setting in the service layer.
_CounterDep = Annotated[User, Depends(require_role(Role.COUNTER, Role.ADMIN, Role.WAITER))]
_RidDep = Annotated[uuid.UUID, Depends(tenant_scope)]
_DbDep = Annotated[Session, Depends(get_db)]


# ── Internal helpers ──────────────────────────────────────────────────────────

def _check_reopen_allowed(db: Session, restaurant_id: uuid.UUID) -> None:
    """Raises 403 if the restaurant has not enabled order reopening."""
    settings = db.execute(
        select(RestaurantSettings).where(
            RestaurantSettings.restaurant_id == restaurant_id
        )
    ).scalar_one_or_none()
    if settings is None or not settings.allow_order_reopen:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Order reopening is not enabled for this restaurant",
        )


def _check_waiter_billing(db: Session, restaurant_id: uuid.UUID, user: User) -> None:
    """Waiters may only use billing actions when the restaurant has enabled it."""
    if user.role == Role.WAITER:
        settings = db.execute(
            select(RestaurantSettings).where(
                RestaurantSettings.restaurant_id == restaurant_id
            )
        ).scalar_one_or_none()
        if settings is None or not settings.waiter_can_accept_payment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Waiters are not permitted to handle billing at this restaurant",
            )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/print-config", response_model=PrintConfigResponse)
def get_print_config(
    restaurant_id: _RidDep,
    _user: _CounterDep,
    db: _DbDep,
) -> PrintConfigResponse:
    """Printer auto-print toggles + bill copy count (counter-readable; settings
    themselves remain ADMIN-only to edit)."""
    settings = menu_service.get_or_create_settings(db, restaurant_id)
    return PrintConfigResponse.model_validate(settings)

@router.get("/orders", response_model=list[CounterOrderSummary])
def list_meal_finished_orders(
    restaurant_id: _RidDep,
    _user: _CounterDep,
    db: _DbDep,
) -> list[CounterOrderSummary]:
    """List all MEAL_FINISHED orders awaiting payment, oldest-first."""
    orders = db.scalars(
        select(Order)
        .where(
            Order.restaurant_id == restaurant_id,
            Order.status == OrderStatus.MEAL_FINISHED,
        )
        .options(
            joinedload(Order.table),
            selectinload(Order.items),
        )
        .order_by(Order.updated_at.asc())
    ).all()

    return [CounterOrderSummary.from_order(o) for o in orders]


@router.get("/open-orders", response_model=list[CounterOrderSummary])
def list_open_orders(
    restaurant_id: _RidDep,
    _user: _CounterDep,
    db: _DbDep,
) -> list[CounterOrderSummary]:
    """
    List OPEN orders so the counter can send a table to billing directly
    (transition to MEAL_FINISHED), without waiting on the waiter.
    """
    orders = order_service.list_open_orders(db, restaurant_id)
    return [CounterOrderSummary.from_order(o) for o in orders]


@router.post("/orders/{order_id}/print-kot", status_code=status.HTTP_202_ACCEPTED)
def print_kot(
    order_id: uuid.UUID,
    user: _CounterDep,
    restaurant_id: _RidDep,
    db: _DbDep,
) -> dict[str, str]:
    """
    Relay a manual kitchen-ticket print for an order to the print station (COUNTER/
    ADMIN), so a roaming waiter with no local printer can print to the restaurant's
    printer. Emits a kot.print event; the station's PrintController does the printing.
    """
    try:
        order_service.request_kot_print(db, restaurant_id, order_id, actor=user)
    except OrderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    return {"status": "queued"}


@router.post("/orders/{order_id}/meal-finished", response_model=OrderResponse)
def meal_finished(
    order_id: uuid.UUID,
    user: _CounterDep,
    restaurant_id: _RidDep,
    db: _DbDep,
) -> OrderResponse:
    """Transition an OPEN order to MEAL_FINISHED (customer is ready to pay)."""
    try:
        order = order_service.transition_order(
            db, restaurant_id, order_id,
            OrderStatus.MEAL_FINISHED,
            actor_type=user.role.value,
            actor_id=user.id,
        )
    except OrderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    return OrderResponse.model_validate(order)


@router.post("/orders/{order_id}/reopen", response_model=OrderResponse)
def reopen_order(
    order_id: uuid.UUID,
    body: ReopenRequest,
    user: _CounterDep,
    restaurant_id: _RidDep,
    db: _DbDep,
) -> OrderResponse:
    """
    Reopen a MEAL_FINISHED order back to OPEN.

    Gated by restaurant_settings.allow_order_reopen; requires a reason (3–500 chars).
    Rejected with 403 if the setting is off, 422 if reason is absent or too short,
    409 if the order is not in MEAL_FINISHED state.
    """
    _check_reopen_allowed(db, restaurant_id)
    try:
        order = order_service.transition_order(
            db, restaurant_id, order_id,
            OrderStatus.OPEN,
            actor_type=user.role.value,
            actor_id=user.id,
            reason=body.reason,
            allow_reopen=True,
        )
    except OrderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    return OrderResponse.model_validate(order)


@router.post("/orders/{order_id}/start-billing", response_model=OrderResponse)
def start_billing(
    order_id: uuid.UUID,
    user: _CounterDep,
    restaurant_id: _RidDep,
    db: _DbDep,
) -> OrderResponse:
    """
    Staff override: mark an OPEN order as bill-requested so it can move to billing
    even though the customer never tapped Request Bill (dead phone / can't request).
    """
    _check_waiter_billing(db, restaurant_id, user)
    try:
        order = order_service.staff_start_billing(db, restaurant_id, order_id, user)
    except OrderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    return OrderResponse.model_validate(order)


@router.post("/orders/{order_id}/quick-bill", response_model=InvoiceResponse)
def quick_bill(
    order_id: uuid.UUID,
    body: CounterPaymentRequest,
    user: _CounterDep,
    restaurant_id: _RidDep,
    db: _DbDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> InvoiceResponse:
    """
    One-tap "bill & clear the table" for an OPEN, bill-requested order: generates
    the invoice, records payment with the chosen method, closes the order and clears
    the table — all atomically. WAITER is gated by waiter_can_accept_payment.
    Optional Idempotency-Key header makes the call safe to retry.
    """
    _check_waiter_billing(db, restaurant_id, user)
    try:
        invoice = payment_service.quick_bill_and_close(
            db, restaurant_id, order_id,
            method=body.method,
            actor=user,
            idempotency_key=idempotency_key,
        )
    except InvoiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    return InvoiceResponse.model_validate(invoice)


@router.post("/orders/{order_id}/close-unpaid", response_model=OrderResponse)
def close_unpaid(
    order_id: uuid.UUID,
    body: ReopenRequest,
    user: _CounterDep,
    restaurant_id: _RidDep,
    db: _DbDep,
) -> OrderResponse:
    """
    Close an order without payment (cancel / walkout / write-off). Voids any active
    invoice; requires a reason (3–500 chars); fully audited. The house absorbs the loss.
    """
    _check_waiter_billing(db, restaurant_id, user)
    try:
        order = payment_service.close_unpaid(db, restaurant_id, order_id, body.reason, user)
    except InvoiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    return OrderResponse.model_validate(order)
