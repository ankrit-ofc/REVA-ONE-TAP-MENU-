"""
Push-notification registration endpoints.

Any authenticated staff user registers their device's Expo push token after
login and deactivates it on logout. restaurant_id/user come from the verified
JWT (get_current_user / tenant_scope) — never from the request body.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, tenant_scope
from app.models.user import User
from app.schemas.push import (
    DeviceTokenResponse,
    RegisterDeviceRequest,
    UnregisterDeviceRequest,
)
from app.services import push_service

router = APIRouter(prefix="/push", tags=["push"])

_UserDep = Annotated[User, Depends(get_current_user)]
_RidDep = Annotated[uuid.UUID, Depends(tenant_scope)]
_DbDep = Annotated[Session, Depends(get_db)]


@router.post("/register", response_model=DeviceTokenResponse)
def register_device(
    body: RegisterDeviceRequest,
    user: _UserDep,
    _restaurant_id: _RidDep,
    db: _DbDep,
) -> DeviceTokenResponse:
    """Register/refresh this device's Expo push token for the logged-in user."""
    row = push_service.register_device(db, user, body.token, body.platform)
    return DeviceTokenResponse.model_validate(row)


@router.post("/unregister", status_code=204)
def unregister_device(
    body: UnregisterDeviceRequest,
    _user: _UserDep,
    restaurant_id: _RidDep,
    db: _DbDep,
) -> None:
    """Deactivate a token on logout so a shared device stops receiving alerts."""
    push_service.deactivate_device(db, restaurant_id, body.token)
