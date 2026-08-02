"""Pydantic schemas for superadmin platform management."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import RestaurantPlan

RestaurantPlanLiteral = Literal["basic", "starter", "custom"]


class RestaurantCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=255)]
    slug: Annotated[str, Field(min_length=1, max_length=100, pattern=r'^[a-z0-9-]+$')]
    admin_email: Annotated[str, Field(min_length=1, max_length=255)]
    admin_password: Annotated[str, Field(min_length=8, max_length=100)]


class RestaurantUpdate(BaseModel):
    """Partial update. Precedence when both plan and bools are sent:
    1) apply plan + its four preset bools
    2) apply any explicit bool overrides on top (explicit wins).
    """

    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=255)] | None = None
    is_active: bool | None = None
    plan: RestaurantPlanLiteral | None = None
    order_enabled: bool | None = None
    call_waiter_enabled: bool | None = None
    ar_enabled: bool | None = None
    qr_pay_enabled: bool | None = None


class AdminEmailUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: Annotated[str, Field(min_length=1, max_length=255)]


class AdminInfo(BaseModel):
    id: uuid.UUID
    email: str


class RestaurantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: uuid.UUID
    name: str
    slug: str
    is_active: bool
    plan: RestaurantPlan
    order_enabled: bool
    call_waiter_enabled: bool
    ar_enabled: bool
    qr_pay_enabled: bool
    created_at: datetime
    updated_at: datetime
    admins: list[AdminInfo] = []


class RestaurantCreateResponse(BaseModel):
    restaurant: RestaurantResponse
    admin_email: str
