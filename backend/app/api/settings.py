"""
Restaurant settings — ADMIN get/update.

Settings are created with server-side defaults on first access if they don't
exist yet (new restaurants won't always have a row from day one).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_role, tenant_scope
from app.models.enums import Role
from app.models.user import User
from app.schemas.menu import SettingsResponse, SettingsUpdate
from app.services import kot_print_service, menu_service

router = APIRouter(prefix="/admin", tags=["admin-settings"])

_AdminDep = Annotated[User, Depends(require_role(Role.ADMIN))]
_RidDep = Annotated[uuid.UUID, Depends(tenant_scope)]
_DbDep = Annotated[Session, Depends(get_db)]


@router.get("/settings", response_model=SettingsResponse)
def get_settings(
    restaurant_id: _RidDep,
    _user: _AdminDep,
    db: _DbDep,
) -> SettingsResponse:
    settings = menu_service.get_or_create_settings(db, restaurant_id)
    return SettingsResponse.model_validate(settings)


@router.put("/settings", response_model=SettingsResponse)
def update_settings(
    data: SettingsUpdate,
    restaurant_id: _RidDep,
    user: _AdminDep,
    db: _DbDep,
) -> SettingsResponse:
    settings = menu_service.update_settings(db, restaurant_id, data, actor=user)
    return SettingsResponse.model_validate(settings)


@router.post("/settings/kot-worker-token", response_model=SettingsResponse)
def rotate_kot_worker_token(
    restaurant_id: _RidDep,
    user: _AdminDep,
    db: _DbDep,
) -> SettingsResponse:
    """Generate (or replace) the token the kot-printer worker authenticates
    with. Rotating invalidates the previous token immediately; audited."""
    menu_service.get_or_create_settings(db, restaurant_id)
    kot_print_service.rotate_worker_token(db, restaurant_id, actor=user)
    settings = menu_service.get_or_create_settings(db, restaurant_id)
    return SettingsResponse.model_validate(settings)
