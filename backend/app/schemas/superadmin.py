"""Pydantic schemas for superadmin platform management."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class RestaurantCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=255)]
    # slug must be lowercase alphanumeric + hyphens only (URL-safe)
    slug: Annotated[str, Field(min_length=1, max_length=100, pattern=r'^[a-z0-9-]+$')]
    admin_email: Annotated[str, Field(min_length=1, max_length=255)]
    admin_password: Annotated[str, Field(min_length=8, max_length=100)]


class RestaurantUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=255)] | None = None
    is_active: bool | None = None


class AdminEmailUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Plain constrained str (no EmailStr — that would add a dependency).
    email: Annotated[str, Field(min_length=1, max_length=255)]


class AdminInfo(BaseModel):
    id: uuid.UUID
    email: str


class RestaurantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    admins: list[AdminInfo] = []


class RestaurantCreateResponse(BaseModel):
    """Returned when creating a new restaurant; includes the admin email for handoff."""

    restaurant: RestaurantResponse
    admin_email: str
