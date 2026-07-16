"""
Request and response schemas for Phase 6 role-workflow endpoints.

Request schemas use extra="forbid" to prevent clients from injecting
unexpected fields (e.g. price overrides, status manipulation).

Response schemas re-use OrderItemAddonResponse from schemas.order and
extend it with order context (order_id, order_number) for queue views.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import OrderItemStatus
from app.schemas.order import OrderItemAddonResponse


# ── Request schemas ───────────────────────────────────────────────────────────

class ItemTransitionRequest(BaseModel):
    """Empty body for item-transition POST endpoints.

    extra="forbid" ensures the client cannot inject rogue fields.
    The target transition is determined by the URL path, not the body.
    """
    model_config = ConfigDict(extra="forbid")


class MealFinishRequest(BaseModel):
    """Empty body for meal-finished POST endpoints."""
    model_config = ConfigDict(extra="forbid")


class ReopenRequest(BaseModel):
    """Body for order-reopen endpoints — a mandatory, non-trivial reason."""
    model_config = ConfigDict(extra="forbid")

    reason: Annotated[str, Field(min_length=3, max_length=500)]


class RejectItemsRequest(BaseModel):
    """Body for the waiter batch-reject endpoint — reason optional but bounded."""
    model_config = ConfigDict(extra="forbid")

    reason: Annotated[str, Field(min_length=3, max_length=500)] | None = None


# ── Response schemas ──────────────────────────────────────────────────────────

class QueueItemResponse(BaseModel):
    """Order-item enriched with order context for kitchen/waiter queue views."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_id: uuid.UUID
    order_number: int
    # Table the order was placed from — shown as the primary label on the waiter
    # queue. Optional so the kitchen queue (which doesn't set it) is unaffected.
    table_name: str | None = None
    product_name: str
    variant_name: str | None
    unit_price: Decimal
    tax_rate: Decimal
    quantity: int
    special_instructions: str | None
    status: OrderItemStatus
    preparing_at: datetime | None
    ready_at: datetime | None
    served_at: datetime | None
    addons: list[OrderItemAddonResponse]


class WaiterCallResponse(BaseModel):
    """An open 'Call Waiter' request for the waiter dashboard's attend list."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    table_id: uuid.UUID
    table_name: str
    status: str
    created_at: datetime

    @classmethod
    def from_call(cls, call) -> "WaiterCallResponse":
        return cls(
            id=call.id,
            table_id=call.table_id,
            table_name=call.table.name if call.table else "",
            status=call.status,
            created_at=call.created_at,
        )


class DisplayBoardItem(BaseModel):
    """A single row on the passive counter display: a recent NEW/PREPARING/READY/SERVED item."""

    id: uuid.UUID
    order_number: int
    table_name: str
    product_name: str
    variant_name: str | None
    quantity: int
    status: OrderItemStatus      # NEW / PREPARING / READY / SERVED (CANCELLED excluded)
    ready_at: datetime | None
    served_at: datetime | None
