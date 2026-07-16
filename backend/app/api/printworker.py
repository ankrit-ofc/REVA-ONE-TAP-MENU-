"""
Endpoints for the external kot-printer worker (Windows print service).

The worker polls POST /printworker/kot/get and acknowledges printed tickets via
POST /printworker/kot/ack — request/response shapes follow the worker's contract
(see kot-printer/README.md), so the worker needs no code changes, only config.

Auth: `Authorization: Bearer <kot_worker_token>`. The token is per-restaurant
(generated on the admin Devices page); the tenant is derived from it server-side
— never from the request body. The body's `identity` field (the worker sends the
same token there) is accepted but ignored for auth.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.models.restaurant import RestaurantSettings
from app.services import kot_print_service

router = APIRouter(prefix="/printworker", tags=["printworker"])


class KotGetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    identity: str | None = Field(default=None, max_length=128)
    outlet_code: list[str] = Field(default_factory=list, max_length=50)
    is_central_kot: bool = False


class KotAckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    identity: str | None = Field(default=None, max_length=128)
    printed_ids: list[int] = Field(max_length=200)


def _worker_settings(
    db: Annotated[Session, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
) -> RestaurantSettings:
    """Resolve the tenant from the worker's bearer token, 401 otherwise."""
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    settings = kot_print_service.get_settings_by_token(db, token)
    if settings is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing print-worker token",
        )
    return settings


_SettingsDep = Annotated[RestaurantSettings, Depends(_worker_settings)]
_DbDep = Annotated[Session, Depends(get_db)]


@router.post("/kot/get")
def get_pending_tickets(
    _body: KotGetRequest,
    settings: _SettingsDep,
    db: _DbDep,
) -> dict:
    """Pending kitchen tickets for the token's restaurant (idempotent — tickets
    keep being returned until acked)."""
    tickets = kot_print_service.fetch_pending(db, settings)
    return {"is_success": True, "tickets": tickets}


@router.post("/kot/ack")
def acknowledge_tickets(
    body: KotAckRequest,
    settings: _SettingsDep,
    db: _DbDep,
) -> dict:
    """Mark tickets printed. Safe to replay; other tenants' queue_ids are ignored."""
    updated = kot_print_service.ack_jobs(db, settings.restaurant_id, body.printed_ids)
    return {"is_success": True, "updated_ids": updated}
