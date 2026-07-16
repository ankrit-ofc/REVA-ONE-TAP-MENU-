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


def _build(t: Table, restaurant_id: uuid.UUID) -> TableResponse:
    token = qr.sign_qr(str(restaurant_id), str(t.id))
    return TableResponse(
        id=t.id,
        name=t.name,
        is_active=t.is_active,
        created_at=t.created_at,
        updated_at=t.updated_at,
        qr_token=token,
        scan_url=f"{settings.FRONTEND_BASE_URL}/scan?token={token}",
    )

router = APIRouter(prefix="/admin/tables", tags=["admin-tables"])

_AdminDep = Annotated[User, Depends(require_role(Role.ADMIN))]
_RidDep = Annotated[uuid.UUID, Depends(tenant_scope)]
_DbDep = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[TableResponse])
def list_tables(
    restaurant_id: _RidDep,
    _user: _AdminDep,
    db: _DbDep,
) -> list[TableResponse]:
    tables = table_service.list_tables(db, restaurant_id)
    return [_build(t, restaurant_id) for t in tables]


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
