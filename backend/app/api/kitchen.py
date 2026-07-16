"""
Kitchen-staff endpoints (Phase 6).

All endpoints require KITCHEN or ADMIN role.  restaurant_id is derived from
the verified JWT via tenant_scope — never from the request body or query params.

Transitions exposed:
  NEW       -> PREPARING  (POST /kitchen/items/{id}/preparing)
  PREPARING -> READY      (POST /kitchen/items/{id}/ready)
  NEW       -> CANCELLED  (POST /kitchen/items/{id}/cancel)

Queue:
  GET /kitchen/queue  — NEW + PREPARING items for this tenant, oldest first.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import get_db, require_role, tenant_scope
from app.models.enums import OrderItemStatus, Role
from app.models.order import OrderItem
from app.models.user import User
from app.schemas.order import OrderItemAddonResponse, OrderItemResponse
from app.schemas.workflow import QueueItemResponse
from app.services import order_service
from app.services.order_state import OrderError

router = APIRouter(prefix="/kitchen", tags=["kitchen"])

_KitchenDep = Annotated[User, Depends(require_role(Role.KITCHEN, Role.ADMIN))]
_RidDep = Annotated[uuid.UUID, Depends(tenant_scope)]
_DbDep = Annotated[Session, Depends(get_db)]


# ── Internal helpers ──────────────────────────────────────────────────────────

def _to_queue_item(item: OrderItem) -> QueueItemResponse:
    return QueueItemResponse(
        id=item.id,
        order_id=item.order_id,
        order_number=item.order.order_number,
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
    """Reload an OrderItem with its addons eagerly loaded."""
    return db.execute(
        select(OrderItem)
        .where(OrderItem.id == item_id)
        .options(selectinload(OrderItem.addons))
    ).scalar_one()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/queue", response_model=list[QueueItemResponse])
def get_kitchen_queue(
    _user: _KitchenDep,
    restaurant_id: _RidDep,
    db: _DbDep,
) -> list[QueueItemResponse]:
    """Returns all NEW and PREPARING items for this tenant, ordered oldest first."""
    items = db.execute(
        select(OrderItem)
        .where(
            OrderItem.restaurant_id == restaurant_id,
            OrderItem.status.in_([OrderItemStatus.NEW, OrderItemStatus.PREPARING]),
        )
        .options(
            selectinload(OrderItem.order),
            selectinload(OrderItem.addons),
        )
        .order_by(OrderItem.created_at.asc())
    ).scalars().all()
    return [_to_queue_item(item) for item in items]


@router.post("/items/{item_id}/preparing", response_model=OrderItemResponse)
def mark_preparing(
    item_id: uuid.UUID,
    user: _KitchenDep,
    restaurant_id: _RidDep,
    db: _DbDep,
) -> OrderItemResponse:
    """Transition a NEW item to PREPARING. Sets preparing_at timestamp."""
    try:
        item = order_service.transition_item(
            db, restaurant_id, item_id,
            OrderItemStatus.PREPARING,
            actor_type=user.role.value,
            actor_id=user.id,
        )
    except OrderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    return OrderItemResponse.model_validate(_reload_item(db, item.id))


@router.post("/items/{item_id}/ready", response_model=OrderItemResponse)
def mark_ready(
    item_id: uuid.UUID,
    user: _KitchenDep,
    restaurant_id: _RidDep,
    db: _DbDep,
) -> OrderItemResponse:
    """Transition a PREPARING item to READY. Sets ready_at timestamp."""
    try:
        item = order_service.transition_item(
            db, restaurant_id, item_id,
            OrderItemStatus.READY,
            actor_type=user.role.value,
            actor_id=user.id,
        )
    except OrderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    return OrderItemResponse.model_validate(_reload_item(db, item.id))


@router.post("/items/{item_id}/cancel", response_model=OrderItemResponse)
def cancel_item(
    item_id: uuid.UUID,
    user: _KitchenDep,
    restaurant_id: _RidDep,
    db: _DbDep,
) -> OrderItemResponse:
    """Cancel a NEW item (NEW -> CANCELLED). Only allowed before prep starts."""
    try:
        item = order_service.transition_item(
            db, restaurant_id, item_id,
            OrderItemStatus.CANCELLED,
            actor_type=user.role.value,
            actor_id=user.id,
        )
    except OrderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    return OrderItemResponse.model_validate(_reload_item(db, item.id))
