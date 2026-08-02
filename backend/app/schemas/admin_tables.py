"""Pydantic schemas for admin table management."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class TableCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=100)]


class TableUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    is_active: bool | None = None


class TableResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    # Populated for ADMIN only; None (and dropped by response_model_exclude_none)
    # for the WAITER/COUNTER floor-read widening on GET /admin/tables.
    qr_token: str | None = None
    scan_url: str | None = None
