"""
Waiter-staff endpoints (Phase 6).

All endpoints require WAITER or ADMIN role.  restaurant_id is derived from
the verified JWT via tenant_scope — never from the request body or query params.

Transitions exposed:
  NEW/PREPARING/READY -> SERVED    (POST /waiter/items/{id}/served)
  OPEN          -> MEAL_FINISHED   (POST /waiter/orders/{id}/meal-finished)
  MEAL_FINISHED -> OPEN            (POST /waiter/orders/{id}/reopen)
      — only when restaurant_settings.allow_order_reopen is True
      — requires a non-trivial reason (3–500 chars)
  PENDING_APPROVAL -> NEW / CANCELLED  (POST /waiter/orders/{id}/approve|reject)
      — batch approval gate when restaurant_settings.require_order_approval

Queues:
  GET /waiter/ready              — to-serve queue (NEW/PREPARING/READY), oldest first.
  GET /waiter/pending-approvals  — items awaiting approval, oldest first.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import get_db, require_role, tenant_scope
from app.models.enums import OrderItemStatus, OrderStatus, Role
from app.models.order import Order, OrderItem
from app.models.restaurant import RestaurantSettings
from app.models.user import User
from app.schemas.order import (
    CounterOrderSummary,
    OrderItemAddonResponse,
    OrderItemResponse,
    OrderResponse,
)
from app.schemas.workflow import (
    QueueItemResponse,
    RejectItemsRequest,
    ReopenRequest,
    WaiterCallResponse,
)
from app.services import order_service, waiter_call_service
from app.services.order_state import OrderError

router = APIRouter(prefix="/waiter", tags=["waiter"])

_WaiterDep = Annotated[User, Depends(require_role(Role.WAITER, Role.ADMIN))]
_RidDep = Annotated[uuid.UUID, Depends(tenant_scope)]
_DbDep = Annotated[Session, Depends(get_db)]


# ── Internal helpers ──────────────────────────────────────────────────────────

def _to_queue_item(item: OrderItem) -> QueueItemResponse:
    return QueueItemResponse(
        id=item.id,
        order_id=item.order_id,
        order_number=item.order.order_number,
        table_name=item.order.table.name if item.order.table else None,
        product_name=item.product_name,
        variant_name=item.variant_name,
        unit_price=item.unit_price,
        tax_rate=item.tax_rate,
        quantity=item.quantity,
        special_instructions=item.special_instructions,
        status=item.status,
        preparing_at=item.preparing_at,
        ready_at=item.ready_at,
        served_at=item.served_at,
        addons=[OrderItemAddonResponse.model_validate(a) for a in item.addons],
    )


def _reload_item(db: Session, item_id: uuid.UUID) -> OrderItem:
    return db.execute(
        select(OrderItem)
        .where(OrderItem.id == item_id)
        .options(selectinload(OrderItem.addons))
    ).scalar_one()


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


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/ready", response_model=list[QueueItemResponse])
def get_ready_items(
    _user: _WaiterDep,
    restaurant_id: _RidDep,
    db: _DbDep,
) -> list[QueueItemResponse]:
    """
    The waiter's to-serve queue: every approved, unserved item (NEW / PREPARING /
    READY), oldest first. Kitchens that work off the printed KOT never touch the
    queue screen, so a waiter can serve an item at any of these stages.
    """
    items = db.execute(
        select(OrderItem)
        .where(
            OrderItem.restaurant_id == restaurant_id,
            OrderItem.status.in_([
                OrderItemStatus.NEW,
                OrderItemStatus.PREPARING,
                OrderItemStatus.READY,
            ]),
        )
        .options(
            selectinload(OrderItem.order).selectinload(Order.table),
            selectinload(OrderItem.addons),
        )
        .order_by(OrderItem.created_at.asc())
    ).scalars().all()
    return [_to_queue_item(item) for item in items]


@router.get("/pending-approvals", response_model=list[QueueItemResponse])
def get_pending_approvals(
    _user: _WaiterDep,
    restaurant_id: _RidDep,
    db: _DbDep,
) -> list[QueueItemResponse]:
    """
    Items awaiting waiter approval (require_order_approval gate), oldest first —
    the waiter reviews these before approving/rejecting an order's batch.
    """
    items = db.execute(
        select(OrderItem)
        .where(
            OrderItem.restaurant_id == restaurant_id,
            OrderItem.status == OrderItemStatus.PENDING_APPROVAL,
        )
        .options(
            selectinload(OrderItem.order).selectinload(Order.table),
            selectinload(OrderItem.addons),
        )
        .order_by(OrderItem.created_at.asc())
    ).scalars().all()
    return [_to_queue_item(item) for item in items]


@router.post("/orders/{order_id}/approve", response_model=OrderResponse)
def approve_order_items(
    order_id: uuid.UUID,
    user: _WaiterDep,
    restaurant_id: _RidDep,
    db: _DbDep,
) -> OrderResponse:
    """
    Approve the order's batch of PENDING_APPROVAL items: items become NEW, the
    kitchen ticket prints (deferred from placement), and the kitchen queue sees
    them. 409 if nothing is awaiting approval (replays are safe no-ops at the
    HTTP level; the row lock guarantees a single KOT).
    """
    try:
        order = order_service.approve_pending_items(
            db, restaurant_id, order_id, actor=user,
        )
    except OrderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    return OrderResponse.model_validate(order)


@router.post("/orders/{order_id}/reject", response_model=OrderResponse)
def reject_order_items(
    order_id: uuid.UUID,
    body: RejectItemsRequest,
    user: _WaiterDep,
    restaurant_id: _RidDep,
    db: _DbDep,
) -> OrderResponse:
    """
    Reject the order's batch of PENDING_APPROVAL items: items become CANCELLED
    and the customer is notified. Optional reason (3–500 chars) is audited.
    """
    try:
        order = order_service.reject_pending_items(
            db, restaurant_id, order_id, actor=user, reason=body.reason,
        )
    except OrderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    return OrderResponse.model_validate(order)


@router.get("/open-orders", response_model=list[CounterOrderSummary])
def get_open_orders(
    _user: _WaiterDep,
    restaurant_id: _RidDep,
    db: _DbDep,
) -> list[CounterOrderSummary]:
    """
    List OPEN orders (oldest first) so the waiter can move a table to billing.
    This stays reachable after every item is served, unlike the READY queue.
    """
    orders = order_service.list_open_orders(db, restaurant_id)
    return [CounterOrderSummary.from_order(o) for o in orders]


@router.get("/billing-enabled")
def billing_enabled(
    _user: _WaiterDep,
    restaurant_id: _RidDep,
    db: _DbDep,
) -> dict[str, bool]:
    """Whether this restaurant lets waiters handle billing/payment."""
    settings = db.execute(
        select(RestaurantSettings).where(
            RestaurantSettings.restaurant_id == restaurant_id
        )
    ).scalar_one_or_none()
    return {"enabled": bool(settings and settings.waiter_can_accept_payment)}


@router.get("/calls", response_model=list[WaiterCallResponse])
def get_waiter_calls(
    _user: _WaiterDep,
    restaurant_id: _RidDep,
    db: _DbDep,
) -> list[WaiterCallResponse]:
    """Open 'Call Waiter' requests awaiting attendance, oldest first."""
    calls = waiter_call_service.list_pending_calls(db, restaurant_id)
    return [WaiterCallResponse.from_call(c) for c in calls]


@router.post("/calls/{call_id}/attend", response_model=WaiterCallResponse)
def attend_waiter_call(
    call_id: uuid.UUID,
    user: _WaiterDep,
    restaurant_id: _RidDep,
    db: _DbDep,
) -> WaiterCallResponse:
    """Confirm attendance to a call: PENDING -> ATTENDED. Clears it on all dashboards."""
    try:
        call = waiter_call_service.attend_call(db, restaurant_id, call_id, actor=user)
    except OrderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    return WaiterCallResponse.from_call(call)


@router.post("/items/{item_id}/served", response_model=OrderItemResponse)
def mark_served(
    item_id: uuid.UUID,
    user: _WaiterDep,
    restaurant_id: _RidDep,
    db: _DbDep,
) -> OrderItemResponse:
    """
    Mark an item SERVED (from NEW, PREPARING, or READY — the kitchen queue is
    optional when the printed KOT drives the kitchen). Sets served_at.
    """
    try:
        item = order_service.transition_item(
            db, restaurant_id, item_id,
            OrderItemStatus.SERVED,
            actor_type=user.role.value,
            actor_id=user.id,
        )
    except OrderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    return OrderItemResponse.model_validate(_reload_item(db, item.id))


@router.post("/orders/{order_id}/meal-finished", response_model=OrderResponse)
def meal_finished(
    order_id: uuid.UUID,
    user: _WaiterDep,
    restaurant_id: _RidDep,
    db: _DbDep,
) -> OrderResponse:
    """Transition an OPEN order to MEAL_FINISHED (customer has requested the bill)."""
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
    user: _WaiterDep,
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
