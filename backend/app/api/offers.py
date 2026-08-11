"""
Dead Hours Engine — admin endpoints.

Mounted under the existing /admin prefix on purpose. Caddy routes the backend by
an explicit path list plus a path_regexp that already contains `admin`, so a new
route here needs NO edge config change. A new TOP-LEVEL prefix (/offers) would
405 at the edge — the trap documented in CLAUDE.md that has cost an outage once.

ADMIN-only, every route. These endpoints configure what a customer is CHARGED
and the suggestion response carries revenue figures, so nothing here is readable
by floor staff — same posture as the analytics endpoints in dashboard.py.

Business logic (tenant scoping, cross-tenant FK checks, audit rows) lives in
offer_service; the discount arithmetic lives in pricing_service and nowhere
else. This module only maps HTTP to those.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_role, tenant_scope
from app.models.enums import Role
from app.models.user import User
from app.schemas.offer import (
    DeadHoursSuggestions,
    OfferWindowCreate,
    OfferWindowPublic,
    OfferWindowUpdate,
)
from app.services import dead_hours_service, offer_service

router = APIRouter(prefix="/admin/offers", tags=["offers"])

_AdminDep = Annotated[User, Depends(require_role(Role.ADMIN))]
_RidDep = Annotated[uuid.UUID, Depends(tenant_scope)]
_DbDep = Annotated[Session, Depends(get_db)]


@router.get("/suggestions", response_model=DeadHoursSuggestions)
def get_suggestions(
    _user: _AdminDep,
    restaurant_id: _RidDep,
    db: _DbDep,
) -> DeadHoursSuggestions:
    """The quietest recurring windows in this restaurant's trading week.

    A SUGGESTION, never an action: nothing is created, enabled, or priced here.
    An empty `windows` list is a real answer meaning "not enough history to say".
    """
    return dead_hours_service.suggest(db, restaurant_id)


# ── Offer window CRUD ─────────────────────────────────────────────────────────
# Declared AFTER /suggestions so the literal path is matched before the
# {offer_id} parameter route — otherwise "suggestions" would be parsed as a UUID
# and 422 the analytics endpoint.

@router.get("", response_model=list[OfferWindowPublic])
def list_offers(
    _user: _AdminDep,
    restaurant_id: _RidDep,
    db: _DbDep,
) -> list[OfferWindowPublic]:
    """Every live (non-deleted) offer for this restaurant, oldest first."""
    return offer_service.list_offers(db, restaurant_id)


@router.post("", response_model=OfferWindowPublic, status_code=status.HTTP_201_CREATED)
def create_offer(
    body: OfferWindowCreate,
    _user: _AdminDep,
    restaurant_id: _RidDep,
    db: _DbDep,
) -> OfferWindowPublic:
    """Create an offer. Starts disabled unless is_enabled is explicitly set —
    the engine proposes, the owner approves."""
    return offer_service.create_offer(db, restaurant_id, body, _user)


@router.get("/{offer_id}", response_model=OfferWindowPublic)
def get_offer(
    offer_id: uuid.UUID,
    _user: _AdminDep,
    restaurant_id: _RidDep,
    db: _DbDep,
) -> OfferWindowPublic:
    return offer_service.get_offer(db, restaurant_id, offer_id)


@router.put("/{offer_id}", response_model=OfferWindowPublic)
def update_offer(
    offer_id: uuid.UUID,
    body: OfferWindowUpdate,
    _user: _AdminDep,
    restaurant_id: _RidDep,
    db: _DbDep,
) -> OfferWindowPublic:
    """Replace an offer's whole configuration (see OfferWindowUpdate for why
    this is not a partial patch)."""
    return offer_service.update_offer(db, restaurant_id, offer_id, body, _user)


@router.post("/{offer_id}/enable", response_model=OfferWindowPublic)
def enable_offer(
    offer_id: uuid.UUID,
    _user: _AdminDep,
    restaurant_id: _RidDep,
    db: _DbDep,
) -> OfferWindowPublic:
    """The owner's approval switch. Audited as its own action."""
    return offer_service.set_enabled(db, restaurant_id, offer_id, True, _user)


@router.post("/{offer_id}/disable", response_model=OfferWindowPublic)
def disable_offer(
    offer_id: uuid.UUID,
    _user: _AdminDep,
    restaurant_id: _RidDep,
    db: _DbDep,
) -> OfferWindowPublic:
    return offer_service.set_enabled(db, restaurant_id, offer_id, False, _user)


@router.delete("/{offer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_offer(
    offer_id: uuid.UUID,
    _user: _AdminDep,
    restaurant_id: _RidDep,
    db: _DbDep,
) -> None:
    """Soft delete (is_active=False) — offers are business records."""
    offer_service.soft_delete_offer(db, restaurant_id, offer_id, _user)


@router.get("/{offer_id}/floor-warning")
def get_floor_warning(
    offer_id: uuid.UUID,
    _user: _AdminDep,
    restaurant_id: _RidDep,
    db: _DbDep,
) -> dict:
    """How many of this offer's items have their discount cut short by the floor.

    Configuration-time only. Order time clamps silently, so this is where the
    owner finds out before a diner does.
    """
    return offer_service.floor_warning(db, restaurant_id, offer_id)
