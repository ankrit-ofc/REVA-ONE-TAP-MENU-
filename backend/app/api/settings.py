"""
Restaurant settings — ADMIN get/update.

Settings are created with server-side defaults on first access if they don't
exist yet (new restaurants won't always have a row from day one).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_role, tenant_scope
from app.models.enums import Role
from app.models.user import User
from app.schemas.menu import SettingsResponse, SettingsUpdate
from app.services import image_service, kot_print_service, menu_service

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


@router.post("/settings/banner-image", response_model=SettingsResponse)
def upload_banner_image(
    file: UploadFile,
    restaurant_id: _RidDep,
    user: _AdminDep,
    db: _DbDep,
) -> SettingsResponse:
    """
    Sets the customer-menu hero banner. Multipart upload validated by magic
    bytes (JPEG/PNG/WebP only), max 25 MB, max 2400x1200, EXIF stripped, then
    stored under a UUID filename in this tenant's media path. banner_image_url
    is only ever set by this endpoint — never accepted from the client. Audited.
    """
    raw = file.file.read()
    try:
        banner_url = image_service.validate_and_store_banner(raw, restaurant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    settings = menu_service.get_or_create_settings(db, restaurant_id)
    previous_url = settings.banner_image_url
    settings = menu_service.set_banner_image(db, restaurant_id, banner_url, actor=user)
    if previous_url:
        image_service.delete_image(previous_url)  # best-effort cleanup of the replaced file
    return SettingsResponse.model_validate(settings)


@router.delete("/settings/banner-image", response_model=SettingsResponse)
def remove_banner_image(
    restaurant_id: _RidDep,
    user: _AdminDep,
    db: _DbDep,
) -> SettingsResponse:
    """Removes the hero banner (customer page falls back to the stock image). Audited."""
    settings = menu_service.get_or_create_settings(db, restaurant_id)
    previous_url = settings.banner_image_url
    settings = menu_service.remove_banner_image(db, restaurant_id, actor=user)
    if previous_url:
        image_service.delete_image(previous_url)
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
