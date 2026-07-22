"""
Admin dashboard read-endpoints.

ADMIN-only, tenant-scoped (restaurant_id derived from the JWT via tenant_scope,
never from the client). All four endpoints are plain aggregations over existing
order/invoice data — no writes, no state transitions, no forecasting.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_role, tenant_scope
from app.models.enums import Role
from app.models.user import User
from app.schemas.dashboard import (
    ActiveTable,
    OrdersThisWeek,
    RevenueToday,
    TopProducts,
)
from app.services import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_AdminDep = Annotated[User, Depends(require_role(Role.ADMIN))]
_RidDep = Annotated[uuid.UUID, Depends(tenant_scope)]
_DbDep = Annotated[Session, Depends(get_db)]


@router.get("/active-tables", response_model=list[ActiveTable])
def get_active_tables(
    _user: _AdminDep,
    restaurant_id: _RidDep,
    db: _DbDep,
) -> list[ActiveTable]:
    """Tables with at least one active (OPEN) order, longest-waiting first."""
    return dashboard_service.active_tables(db, restaurant_id)


@router.get("/revenue-today", response_model=RevenueToday)
def get_revenue_today(
    _user: _AdminDep,
    restaurant_id: _RidDep,
    db: _DbDep,
) -> RevenueToday:
    """Sum of PAID invoice totals dated today (restaurant timezone)."""
    return dashboard_service.revenue_today(db, restaurant_id)


@router.get("/orders-this-week", response_model=OrdersThisWeek)
def get_orders_this_week(
    _user: _AdminDep,
    restaurant_id: _RidDep,
    db: _DbDep,
) -> OrdersThisWeek:
    """Count of orders placed since Sunday 00:00 (restaurant timezone)."""
    return dashboard_service.orders_this_week(db, restaurant_id)


@router.get("/top-products", response_model=TopProducts)
def get_top_products(
    _user: _AdminDep,
    restaurant_id: _RidDep,
    db: _DbDep,
) -> TopProducts:
    """Top 5 products by quantity sold over the last 7 days."""
    return dashboard_service.top_products(db, restaurant_id)
