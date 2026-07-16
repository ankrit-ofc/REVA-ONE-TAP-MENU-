"""
ADMIN-only endpoints for staff user management.

All routes require ADMIN role. restaurant_id is derived from the verified JWT
via tenant_scope — never from the request body.

SUPERADMIN accounts are never listed, created, or modified here.
An ADMIN cannot deactivate their own account (prevents self-lockout).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_role, tenant_scope
from app.models.enums import Role
from app.models.user import User
from app.schemas.admin_staff import StaffCreate, StaffResponse, StaffUpdate
from app.services import staff_service

router = APIRouter(prefix="/admin/staff", tags=["admin-staff"])

_AdminDep = Annotated[User, Depends(require_role(Role.ADMIN))]
_RidDep = Annotated[uuid.UUID, Depends(tenant_scope)]
_DbDep = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[StaffResponse])
def list_staff(
    restaurant_id: _RidDep,
    _user: _AdminDep,
    db: _DbDep,
) -> list[StaffResponse]:
    members = staff_service.list_staff(db, restaurant_id)
    return [StaffResponse.model_validate(m) for m in members]


@router.post("", response_model=StaffResponse, status_code=status.HTTP_201_CREATED)
def create_staff(
    data: StaffCreate,
    restaurant_id: _RidDep,
    _user: _AdminDep,
    db: _DbDep,
) -> StaffResponse:
    member = staff_service.create_staff(db, restaurant_id, data)
    return StaffResponse.model_validate(member)


@router.put("/{user_id}", response_model=StaffResponse)
def update_staff(
    user_id: uuid.UUID,
    data: StaffUpdate,
    restaurant_id: _RidDep,
    user: _AdminDep,
    db: _DbDep,
) -> StaffResponse:
    member = staff_service.update_staff(db, restaurant_id, user_id, data, actor_id=user.id)
    return StaffResponse.model_validate(member)


@router.delete("/{user_id}", response_model=StaffResponse)
def delete_staff(
    user_id: uuid.UUID,
    restaurant_id: _RidDep,
    user: _AdminDep,
    db: _DbDep,
) -> StaffResponse:
    """Deactivate a staff member (soft delete). The email is freed for reuse by
    the partial unique index on active rows; the row and audit trail remain."""
    return staff_service.delete_staff(db, restaurant_id, user_id, actor=user)
