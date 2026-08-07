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
from app.models.restaurant import Restaurant
from app.models.user import User
from app.schemas.menu import SettingsResponse, SettingsUpdate
from app.services import image_service, kot_print_service, menu_service

router = APIRouter(prefix="/admin", tags=["admin-settings"])

_AdminDep = Annotated[User, Depends(require_role(Role.ADMIN))]
_RidDep = Annotated[uuid.UUID, Depends(tenant_scope)]
_DbDep = Annotated[Session, Depends(get_db)]


def _settings_response(db: Session, restaurant_id: uuid.UUID, settings) -> SettingsResponse:
    restaurant = db.get(Restaurant, restaurant_id)
    base = SettingsResponse.model_validate(settings)
    return base.model_copy(
        update={
            "ar_enabled": bool(restaurant.ar_enabled) if restaurant else True,
            "qr_pay_enabled": bool(restaurant.qr_pay_enabled) if restaurant else True,
        }
    )


@router.get("/settings", response_model=SettingsResponse)
def get_settings(
    restaurant_id: _RidDep,
    _user: _AdminDep,
    db: _DbDep,
) -> SettingsResponse:
    settings = menu_service.get_or_create_settings(db, restaurant_id)
    return _settings_response(db, restaurant_id, settings)


@router.put("/settings", response_model=SettingsResponse)
def update_settings(
    data: SettingsUpdate,
    restaurant_id: _RidDep,
    user: _AdminDep,
    db: _DbDep,
) -> SettingsResponse:
    # enable_qr_payment on SettingsUpdate is accept-and-ignore (soft-deprecated).
    settings = menu_service.update_settings(db, restaurant_id, data, actor=user)
    return _settings_response(db, restaurant_id, settings)


@router.post("/settings/banner-image", response_model=SettingsResponse)
def upload_banner_image(
    file: UploadFile,
    restaurant_id: _RidDep,
    user: _AdminDep,
    db: _DbDep,
) -> SettingsResponse:
    raw = file.file.read()
    try:
        banner_url = image_service.validate_and_store_banner(raw, restaurant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    settings = menu_service.get_or_create_settings(db, restaurant_id)
    previous_url = settings.banner_image_url
    settings = menu_service.set_banner_image(db, restaurant_id, banner_url, actor=user)
    if previous_url:
        image_service.delete_image(previous_url)
    return _settings_response(db, restaurant_id, settings)


@router.delete("/settings/banner-image", response_model=SettingsResponse)
def remove_banner_image(
    restaurant_id: _RidDep,
    user: _AdminDep,
    db: _DbDep,
) -> SettingsResponse:
    settings = menu_service.get_or_create_settings(db, restaurant_id)
    previous_url = settings.banner_image_url
    settings = menu_service.remove_banner_image(db, restaurant_id, actor=user)
    if previous_url:
        image_service.delete_image(previous_url)
    return _settings_response(db, restaurant_id, settings)


@router.post("/settings/payment-qr", response_model=SettingsResponse)
def upload_payment_qr(
    file: UploadFile,
    restaurant_id: _RidDep,
    user: _AdminDep,
    db: _DbDep,
) -> SettingsResponse:
    raw = file.file.read()
    try:
        qr_url = image_service.validate_and_store_payment_qr(raw, restaurant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    settings = menu_service.get_or_create_settings(db, restaurant_id)
    previous_url = settings.payment_qr_url
    settings = menu_service.set_payment_qr(db, restaurant_id, qr_url, actor=user)
    if previous_url:
        image_service.delete_image(previous_url)
    return _settings_response(db, restaurant_id, settings)


@router.delete("/settings/payment-qr", response_model=SettingsResponse)
def remove_payment_qr(
    restaurant_id: _RidDep,
    user: _AdminDep,
    db: _DbDep,
) -> SettingsResponse:
    settings = menu_service.get_or_create_settings(db, restaurant_id)
    previous_url = settings.payment_qr_url
    settings = menu_service.remove_payment_qr(db, restaurant_id, actor=user)
    if previous_url:
        image_service.delete_image(previous_url)
    return _settings_response(db, restaurant_id, settings)


@router.post("/settings/popup-illustration", response_model=SettingsResponse)
def upload_popup_illustration(
    file: UploadFile,
    restaurant_id: _RidDep,
    user: _AdminDep,
    db: _DbDep,
) -> SettingsResponse:
    raw = file.file.read()
    try:
        illustration_url = image_service.validate_and_store_popup_illustration(raw, restaurant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    settings = menu_service.get_or_create_settings(db, restaurant_id)
    previous_url = settings.popup_illustration_url
    settings = menu_service.set_popup_illustration(db, restaurant_id, illustration_url, actor=user)
    if previous_url:
        image_service.delete_image(previous_url)
    return _settings_response(db, restaurant_id, settings)


@router.delete("/settings/popup-illustration", response_model=SettingsResponse)
def remove_popup_illustration(
    restaurant_id: _RidDep,
    user: _AdminDep,
    db: _DbDep,
) -> SettingsResponse:
    settings = menu_service.get_or_create_settings(db, restaurant_id)
    previous_url = settings.popup_illustration_url
    settings = menu_service.remove_popup_illustration(db, restaurant_id, actor=user)
    if previous_url:
        image_service.delete_image(previous_url)
    return _settings_response(db, restaurant_id, settings)


@router.post("/settings/kot-worker-token", response_model=SettingsResponse)
def rotate_kot_worker_token(
    restaurant_id: _RidDep,
    user: _AdminDep,
    db: _DbDep,
) -> SettingsResponse:
    menu_service.get_or_create_settings(db, restaurant_id)
    kot_print_service.rotate_worker_token(db, restaurant_id, actor=user)
    settings = menu_service.get_or_create_settings(db, restaurant_id)
    return _settings_response(db, restaurant_id, settings)
