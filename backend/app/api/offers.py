"""
Dead Hours Engine — admin endpoints.

Mounted under the existing /admin prefix on purpose. Caddy routes the backend by
an explicit path list plus a path_regexp that already contains `admin`, so a new
route here needs NO edge config change. A new TOP-LEVEL prefix (/offers) would
405 at the edge — the trap documented in CLAUDE.md that has cost an outage once.

Currently read-only: the suggestion endpoint is a SELECT. Offer window CRUD
joins this router when the offer_windows table exists, at which point this file
gains the writes and their audit rows.

ADMIN-only. The response carries revenue figures, so it sits with the analytics
endpoints in dashboard.py rather than with anything floor staff can read.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_role, tenant_scope
from app.models.enums import Role
from app.models.user import User
from app.schemas.offer import DeadHoursSuggestions
from app.services import dead_hours_service

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
