"""Pydantic schemas for admin staff management."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Role


class StaffCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: Annotated[str, Field(min_length=1, max_length=255)]
    password: Annotated[str, Field(min_length=8, max_length=100)]
    # SUPERADMIN cannot be created via this endpoint — enforced in the service.
    role: Role


class StaffUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Role | None = None
    is_active: bool | None = None


class StaffResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role: Role
    is_active: bool
    created_at: datetime
    updated_at: datetime
