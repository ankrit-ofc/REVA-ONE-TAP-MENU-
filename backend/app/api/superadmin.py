"""
SUPERADMIN-only endpoints for platform restaurant management.

These endpoints are NOT scoped to a single restaurant — they operate on the
full `restaurants` table. tenant_scope is deliberately NOT used here because
the superadmin needs cross-tenant visibility.

Auth: Bearer JWT with role=SUPERADMIN, verified via _require_superadmin.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models.enums import Role
from app.models.user import User
from app.schemas.superadmin import (
    AdminEmailUpdate,
    AdminInfo,
    RestaurantCreate,
    RestaurantCreateResponse,
    RestaurantResponse,
    RestaurantUpdate,
)
from app.services import superadmin_service

router = APIRouter(prefix="/superadmin", tags=["superadmin"])


def _require_superadmin(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.role != Role.SUPERADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    return user


_SuperadminDep = Annotated[User, Depends(_require_superadmin)]
_DbDep = Annotated[Session, Depends(get_db)]


@router.get("/restaurants", response_model=list[RestaurantResponse])
def list_restaurants(
    _user: _SuperadminDep,
    db: _DbDep,
) -> list[dict]:
    restaurants = superadmin_service.list_restaurants(db)
    result = []
    for r in restaurants:
        admin_users = [u for u in r.users if u.role == Role.ADMIN and u.is_active]
        result.append({
            "id": r.id,
            "name": r.name,
            "slug": r.slug,
            "is_active": r.is_active,
            "created_at": r.created_at,
            "updated_at": r.updated_at,
            "admins": [AdminInfo(id=u.id, email=u.email) for u in admin_users],
        })
    return result


@router.post(
    "/restaurants",
    response_model=RestaurantCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_restaurant(
    data: RestaurantCreate,
    _user: _SuperadminDep,
    db: _DbDep,
) -> RestaurantCreateResponse:
    restaurant, admin_email = superadmin_service.create_restaurant(db, data)
    return RestaurantCreateResponse(
        restaurant=RestaurantResponse.model_validate(restaurant),
        admin_email=admin_email,
    )


@router.put("/restaurants/{restaurant_id}", response_model=RestaurantResponse)
def update_restaurant(
    restaurant_id: uuid.UUID,
    data: RestaurantUpdate,
    user: _SuperadminDep,
    db: _DbDep,
) -> RestaurantResponse:
    restaurant = superadmin_service.update_restaurant(db, restaurant_id, data, actor=user)
    return RestaurantResponse.model_validate(restaurant)


@router.put(
    "/restaurants/{restaurant_id}/admins/{user_id}",
    response_model=RestaurantResponse,
)
def update_admin_email(
    restaurant_id: uuid.UUID,
    user_id: uuid.UUID,
    data: AdminEmailUpdate,
    user: _SuperadminDep,
    db: _DbDep,
) -> RestaurantResponse:
    restaurant = superadmin_service.update_admin_email(
        db, restaurant_id, user_id, data, actor=user
    )
    return RestaurantResponse.model_validate(restaurant)
