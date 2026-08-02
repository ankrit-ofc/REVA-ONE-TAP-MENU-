"""
Pydantic schemas for the admin dashboard's live/analytics widgets.

All values are computed server-side from persisted order/invoice data — these
are Response-only models; nothing here is ever accepted from the client.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.enums import OrderStatus


# ── Active Tables ─────────────────────────────────────────────────────────────

class ActiveTableItem(BaseModel):
    """A single (non-cancelled) line on an active order, for the expanded view."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    quantity: int


class ActiveTableOrder(BaseModel):
    """One active (OPEN) order sitting on a table."""

    order_id: uuid.UUID
    order_number: int
    status: OrderStatus
    placed_at: datetime
    items: list[ActiveTableItem]


class ActiveTable(BaseModel):
    """A table that currently has at least one active (OPEN) order."""

    table_id: uuid.UUID
    table_label: str
    order_count: int
    earliest_placed_at: datetime
    # Running tab across all active orders on the table (subtotal + tax, no
    # discount — the order is not yet invoiced). Display estimate, not an invoice.
    total_amount: Decimal
    orders: list[ActiveTableOrder]


class WaiterTable(BaseModel):
    """
    Floor-map row for GET /waiter/tables: every *active* table, occupied or free.

    Extends the ActiveTable shape with `occupied` and a flat merged `items` list
    for card display. Money is a Decimal string ("0.00"), matching staff WS /
    receipt conventions — not a float.

    Note: Postgres partial unique index `uq_orders_active_table` currently allows
    at most one OPEN order per table, so `orders` is typically length 0 or 1.
    Merge-by-name still applies when a single order has repeated product names
    (e.g. after place_or_append).
    """

    table_id: uuid.UUID
    table_label: str
    occupied: bool
    order_count: int
    earliest_placed_at: datetime | None
    total_amount: str
    items: list[ActiveTableItem]
    orders: list[ActiveTableOrder]


# ── Analytics cards ───────────────────────────────────────────────────────────

class RevenueToday(BaseModel):
    """Sum of PAID invoice totals created today (restaurant timezone)."""

    # None => the metric cannot be computed (kept for forward-compat; billing
    # persists invoices.total today, so in practice this is always populated).
    amount: Decimal | None
    currency: str


class OrdersThisWeek(BaseModel):
    """Count of orders placed in the current week (Sunday-start, restaurant tz)."""

    count: int


class TopProduct(BaseModel):
    product_name: str
    quantity_sold: int


class TopProducts(BaseModel):
    """Top products by quantity sold over a rolling window."""

    window_days: int
    products: list[TopProduct]
