"""
Counter Display endpoint (Phase 2).

A passive, read-only wall board for the counter. Shows the full live lifecycle of
recent items — NEW (ordered), PREPARING, READY and SERVED — so staff and guests can
follow each item from order to delivery. SERVED rows are NOT cleared (unlike the
waiter's queue); the board keeps the last few items visible. CANCELLED items are
excluded.

Read-only; allowed for COUNTER_DISPLAY (the wall account), plus COUNTER and ADMIN.
restaurant_id is derived from the verified JWT via tenant_scope.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.deps import get_db, require_role, tenant_scope
from app.models.enums import OrderItemStatus, Role
from app.models.order import Order, OrderItem
from app.models.user import User
from app.schemas.workflow import DisplayBoardItem

router = APIRouter(prefix="/counter-display", tags=["counter-display"])

_DisplayDep = Annotated[
    User, Depends(require_role(Role.COUNTER_DISPLAY, Role.COUNTER, Role.ADMIN))
]
_RidDep = Annotated[uuid.UUID, Depends(tenant_scope)]
_DbDep = Annotated[Session, Depends(get_db)]

_BOARD_LIMIT = 30


@router.get("/board", response_model=list[DisplayBoardItem])
def get_board(
    _user: _DisplayDep,
    restaurant_id: _RidDep,
    db: _DbDep,
) -> list[DisplayBoardItem]:
    """
    Return the last ~30 active items (NEW / PREPARING / READY / SERVED), most-recently
    touched first. Ordering uses the latest available lifecycle timestamp, falling back
    to created_at for items still NEW (which have no transition timestamps yet).
    CANCELLED items are excluded.
    """
    items = db.execute(
        select(OrderItem)
        .where(
            OrderItem.restaurant_id == restaurant_id,
            OrderItem.status.in_([
                OrderItemStatus.NEW,
                OrderItemStatus.PREPARING,
                OrderItemStatus.READY,
                OrderItemStatus.SERVED,
            ]),
        )
        .options(selectinload(OrderItem.order).joinedload(Order.table))
        .order_by(
            func.coalesce(
                OrderItem.served_at,
                OrderItem.ready_at,
                OrderItem.preparing_at,
                OrderItem.created_at,
            ).desc()
        )
        .limit(_BOARD_LIMIT)
    ).scalars().all()

    return [
        DisplayBoardItem(
            id=item.id,
            order_number=item.order.order_number,
            table_name=item.order.table.name,
            product_name=item.product_name,
            variant_name=item.variant_name,
            quantity=item.quantity,
            status=item.status,
            ready_at=item.ready_at,
            served_at=item.served_at,
        )
        for item in items
    ]
