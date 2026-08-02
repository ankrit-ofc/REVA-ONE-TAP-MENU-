"""
Pydantic schemas for the ordering domain.

Data contract:
- OrderItemCreate accepts product_id / variant_id / addon_ids / quantity /
  special_instructions ONLY.  No price, name, or tax field is present;
  extra="forbid" guarantees the client cannot inject one.
- special_instructions doubles as the customer's per-item note (preset chips +
  free text on the client). Trimmed and capped at 140 chars server-side;
  whitespace-only input normalizes to NULL rather than an empty string.
- All snapshot fields (product_name, unit_price, tax_rate, addon prices) appear
  only in *Response* models — they are set server-side, never accepted from the
  client.
- order_number (human-readable int, e.g. 42) is the user-facing identifier;
  the internal UUID id is included for client-side keying but never shown to
  end-users as the canonical reference.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import OrderItemStatus, OrderStatus


# ── Request schemas ───────────────────────────────────────────────────────────

class OrderItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: uuid.UUID
    variant_id: uuid.UUID | None = None
    addon_ids: list[uuid.UUID] = Field(default_factory=list)
    quantity: Annotated[int, Field(ge=1, le=99)]
    special_instructions: Annotated[str, Field(max_length=140)] | None = None

    @field_validator("special_instructions", mode="before")
    @classmethod
    def _normalize_special_instructions(cls, v: str | None) -> str | None:
        """Trim before the length cap is checked; blank input becomes NULL."""
        if v is None:
            return None
        v = v.strip()
        return v or None


class PlaceOrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: Annotated[list[OrderItemCreate], Field(min_length=1, max_length=50)]


# ── Response schemas ──────────────────────────────────────────────────────────

class OrderItemAddonResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    addon_name: str
    addon_price: Decimal


class OrderItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
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


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_number: int
    status: OrderStatus
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemResponse]


class CounterOrderSummaryItem(BaseModel):
    """One line on a billing-queue summary — enough for staff to read the order
    back to a guest, without the pricing detail the full invoice carries."""

    name: str
    quantity: int


class CounterOrderSummary(BaseModel):
    """Lightweight order summary for the counter/waiter billing queues."""

    id: uuid.UUID
    order_number: int
    status: OrderStatus
    table_name: str
    item_count: int
    # Items awaiting waiter approval (require_order_approval gate). item_count
    # includes them — they are prospective items, just not yet in the kitchen.
    pending_item_count: int
    bill_requested: bool
    created_at: datetime
    updated_at: datetime
    # Non-cancelled lines, so the Billing screen can show what was ordered.
    # Same visibility rule as item_count above.
    items: list[CounterOrderSummaryItem]

    @classmethod
    def from_order(cls, order) -> "CounterOrderSummary":
        """Build a summary from a loaded Order (requires .table and .items)."""
        return cls(
            id=order.id,
            order_number=order.order_number,
            status=order.status,
            table_name=order.table.name,
            item_count=sum(
                1 for item in order.items if item.status != OrderItemStatus.CANCELLED
            ),
            pending_item_count=sum(
                1 for item in order.items
                if item.status == OrderItemStatus.PENDING_APPROVAL
            ),
            bill_requested=order.bill_requested_at is not None,
            created_at=order.created_at,
            updated_at=order.updated_at,
            items=[
                CounterOrderSummaryItem(name=item.product_name, quantity=item.quantity)
                for item in order.items
                if item.status != OrderItemStatus.CANCELLED
            ],
        )
