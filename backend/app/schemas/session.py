import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class ScanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    qr_token: str
    # Device location, sent only on the geofence retry (see the 428 handshake).
    # Optional so non-geofenced restaurants never need to provide them.
    latitude: Annotated[float, Field(ge=-90, le=90)] | None = None
    longitude: Annotated[float, Field(ge=-180, le=180)] | None = None
    accuracy: Annotated[float, Field(ge=0)] | None = None


class SessionResponse(BaseModel):
    session_token: str
    table_name: str
    restaurant_name: str
    expires_at: datetime


class InvalidateRequest(BaseModel):
    """
    Body for POST /session/invalidate.
    Customer path: send empty body {} (session identified via X-Session-Token header).
    Staff path: send {"session_id": "<uuid>"} alongside a Bearer JWT with
                ADMIN/WAITER/COUNTER role.
    """
    model_config = ConfigDict(extra="forbid")

    session_id: uuid.UUID | None = None
