"""
Customer-facing ordering endpoints (Phase 5).

Both endpoints require a valid table session (X-Session-Token header).
restaurant_id and table_id are derived exclusively from the validated session;
the client cannot inject them.

Staff transition endpoints (kitchen queue, waiter actions) are Phase 6 and call
order_service.transition_order / transition_item directly.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_session, get_db
from app.core.limiter import limiter
from app.models.table import TableSession
from app.schemas.order import OrderResponse, PlaceOrderRequest
from app.services import order_service
from app.services.order_state import OrderError

router = APIRouter(prefix="/orders", tags=["orders"])

_SessionDep = Annotated[TableSession, Depends(get_current_session)]
_DbDep = Annotated[Session, Depends(get_db)]


@router.post("/items", response_model=OrderResponse)
@limiter.limit(settings.RATE_LIMIT_ORDERS)
def place_or_append_items(
    request: Request,
    body: PlaceOrderRequest,
    session: _SessionDep,
    db: _DbDep,
) -> OrderResponse:
    """
    Places a new order for the table, or appends items to the existing OPEN order.

    - Prices, names, and taxes are NEVER taken from the request; they are looked
      up from the DB and snapshotted at order time.
    - Extra fields in the request body (e.g. unit_price) are rejected with 422.
    - Rejected when the table's order is MEAL_FINISHED (checkout state).
    - Rejected when the product is unavailable or belongs to another tenant.
    """
    try:
        order = order_service.place_or_append(db, session, body)
    except OrderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    return OrderResponse.model_validate(order)


@router.get("/current", response_model=OrderResponse)
def get_current_order(
    session: _SessionDep,
    db: _DbDep,
) -> OrderResponse:
    """
    Returns the active OPEN order for the caller's table, including item statuses
    and snapshotted prices.  Returns 404 if no active order exists.
    """
    order = order_service.get_current_order(db, session)
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active order for this table",
        )
    return OrderResponse.model_validate(order)


@router.post("/request-bill", response_model=OrderResponse)
@limiter.limit(settings.RATE_LIMIT_ORDERS)
def request_bill(
    request: Request,
    session: _SessionDep,
    db: _DbDep,
) -> OrderResponse:
    """
    Customer asks for the bill. Notify-only: signals waiter + counter to move the
    table to billing; performs no state change. Returns 404 if no active order.
    """
    try:
        order = order_service.request_bill(db, session)
    except OrderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    return OrderResponse.model_validate(order)
