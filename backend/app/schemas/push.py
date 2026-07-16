"""Request/response schemas for staff push-notification device registration."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class RegisterDeviceRequest(BaseModel):
    """A staff device registering its Expo push token after login."""
    model_config = ConfigDict(extra="forbid")

    # Expo tokens look like "ExponentPushToken[xxxxxxxx]"; bound the length so a
    # client can't submit an unbounded blob.
    token: Annotated[str, Field(min_length=1, max_length=255)]
    platform: Literal["android", "ios"] = "android"


class UnregisterDeviceRequest(BaseModel):
    """Deactivate a token on logout so a shared device stops receiving alerts."""
    model_config = ConfigDict(extra="forbid")

    token: Annotated[str, Field(min_length=1, max_length=255)]


class DeviceTokenResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    platform: str
    is_active: bool
