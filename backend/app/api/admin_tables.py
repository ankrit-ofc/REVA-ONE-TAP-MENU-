"""
ADMIN-only endpoints for table management.

All routes require ADMIN role. restaurant_id is derived from the verified JWT
via tenant_scope — never from the request body.

Soft-delete only — tables are never hard-deleted (preserves order history).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core import qr
from app.core.config import settings
from app.core.deps import get_db, require_role, tenant_scope
from app.models.enums import Role
from app.models.table import Table
from app.models.user import User
from app.schemas.admin_tables import TableCreate, TableResponse, TableUpdate
from app.services import table_service


def _build(t: Table, restaurant_id: uuid.UUID, *, include_qr: bool = True) -> TableResponse:
    qr_token = None
    scan_url = None
    if include_qr:
        qr_token = qr.sign_qr(str(restaurant_id), str(t.id))
        scan_url = f"{settings.FRONTEND_BASE_URL}/scan?token={qr_token}"
    return TableResponse(
        id=t.id,
        name=t.name,
        is_active=t.is_active,
        created_at=t.created_at,
        updated_at=t.updated_at,
        qr_token=qr_token,
        scan_url=scan_url,
    )

router = APIRouter(prefix="/admin/tables", tags=["admin-tables"])

_AdminDep = Annotated[User, Depends(require_role(Role.ADMIN))]
# Floor staff need the full table roster for Available/Occupied cards (mobile
# Tables tab). Writes stay ADMIN-only below. Prefer GET /waiter/tables when
# deployed — it omits QR tokens; this widening is the interim unlock on prod.
_FloorReadDep = Annotated[
    User, Depends(require_role(Role.ADMIN, Role.WAITER, Role.COUNTER))
]
_RidDep = Annotated[uuid.UUID, Depends(tenant_scope)]
_DbDep = Annotated[Session, Depends(get_db)]


# exclude_none is a blanket switch: it drops every None field from the
# response, not just qr_token/scan_url. Safe today because the other five
# TableResponse fields (id/name/is_active/created_at/updated_at) are all
# non-Optional and therefore never None. If a future Optional field is added
# to TableResponse, it will silently vanish from this endpoint's output too —
# check that before adding one.
@router.get("", response_model=list[TableResponse], response_model_exclude_none=True)
def list_tables(
    restaurant_id: _RidDep,
    user: _FloorReadDep,
    db: _DbDep,
) -> list[TableResponse]:
    include_qr = user.role == Role.ADMIN
    tables = table_service.list_tables(db, restaurant_id)
    return [_build(t, restaurant_id, include_qr=include_qr) for t in tables]


@router.post("", response_model=TableResponse, status_code=status.HTTP_201_CREATED)
def create_table(
    data: TableCreate,
    restaurant_id: _RidDep,
    _user: _AdminDep,
    db: _DbDep,
) -> TableResponse:
    table = table_service.create_table(db, restaurant_id, data)
    return _build(table, restaurant_id)


@router.put("/{table_id}", response_model=TableResponse)
def update_table(
    table_id: uuid.UUID,
    data: TableUpdate,
    restaurant_id: _RidDep,
    _user: _AdminDep,
    db: _DbDep,
) -> TableResponse:
    table = table_service.update_table(db, restaurant_id, table_id, data)
    return _build(table, restaurant_id)


@router.delete("/{table_id}", response_model=TableResponse)
def deactivate_table(
    table_id: uuid.UUID,
    restaurant_id: _RidDep,
    _user: _AdminDep,
    db: _DbDep,
) -> TableResponse:
    table = table_service.deactivate_table(db, restaurant_id, table_id)
    return _build(table, restaurant_id)
