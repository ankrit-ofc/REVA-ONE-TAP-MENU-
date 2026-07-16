"""
Pydantic schemas for the invoice and payment domain.

Security notes:
- extra="forbid" on all request schemas — extra fields are rejected (422).
- No client-supplied price, total, or subtotal field exists on any request schema;
  those are computed server-side from order-item snapshots.
- CounterPaymentRequest.method is restricted to counter-accepted methods only;
  QR_GATEWAY and MANUAL_OVERRIDE cannot be submitted by a client to this endpoint.
- Idempotency-Key is read from the request HEADER, not the body.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import InvoiceStatus, PaymentMethod


# ── Request schemas ───────────────────────────────────────────────────────────

class GenerateInvoiceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: uuid.UUID
    discount_type: Literal["flat", "percent"] = "flat"
    discount_value: Annotated[Decimal, Field(ge=Decimal("0"), decimal_places=2)] = Decimal("0.00")

    @model_validator(mode="after")
    def _validate_percent_bound(self) -> "GenerateInvoiceRequest":
        if self.discount_type == "percent" and self.discount_value > Decimal("100"):
            raise ValueError("Discount percentage cannot exceed 100")
        return self


class CounterPaymentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: PaymentMethod

    @field_validator("method")
    @classmethod
    def _only_counter_methods(cls, v: PaymentMethod) -> PaymentMethod:
        allowed = {PaymentMethod.CASH, PaymentMethod.CARD, PaymentMethod.COUNTER_WALLET}
        if v not in allowed:
            raise ValueError(
                f"Counter payment method must be one of: "
                f"{', '.join(m.value for m in allowed)}"
            )
        return v


class ManualOverrideRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Annotated[str, Field(min_length=3, max_length=500)]


class GatewayIntentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gateway: Literal["esewa", "khalti", "fonepay"]


# ── Response schemas ──────────────────────────────────────────────────────────

class InvoiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_id: uuid.UUID
    invoice_number: str
    status: InvoiceStatus
    payment_method: PaymentMethod | None
    subtotal: Decimal
    discount: Decimal
    tax_total: Decimal
    total: Decimal
    gateway_transaction_id: str | None
    created_at: datetime
    updated_at: datetime


# ── Printable receipt (itemized bill for thermal printing) ────────────────────

class ReceiptAddon(BaseModel):
    addon_name: str
    addon_price: Decimal


class ReceiptLine(BaseModel):
    product_name: str
    variant_name: str | None
    quantity: int
    unit_price: Decimal
    line_total: Decimal          # qty × (unit_price + addon prices), display-only
    special_instructions: str | None
    addons: list[ReceiptAddon]


class ReceiptResponse(BaseModel):
    """Everything a thermal printer needs to render an itemized bill. Totals are
    the authoritative invoice values; per-line amounts are for display."""
    invoice_number: str
    status: InvoiceStatus
    payment_method: PaymentMethod | None
    currency: str
    restaurant_name: str
    table_name: str
    order_number: int
    created_at: datetime
    items: list[ReceiptLine]
    subtotal: Decimal
    discount: Decimal
    tax_total: Decimal
    total: Decimal
