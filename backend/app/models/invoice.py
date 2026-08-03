import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional, TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint, DateTime, Enum as SAEnum, ForeignKey, Numeric, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import InvoiceStatus, PaymentMethod
from app.models.mixins import TimestampMixin, TenantMixin

if TYPE_CHECKING:
    from app.models.order import Order


class Invoice(Base, TimestampMixin, TenantMixin):
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("restaurant_id", "invoice_number", name="uq_invoices_restaurant_invoice_number"),
        UniqueConstraint("gateway_transaction_id", name="uq_invoices_gateway_transaction_id"),
        CheckConstraint("subtotal >= 0", name="ck_invoices_subtotal_non_negative"),
        CheckConstraint("discount >= 0", name="ck_invoices_discount_non_negative"),
        CheckConstraint("tax_total >= 0", name="ck_invoices_tax_total_non_negative"),
        CheckConstraint("total >= 0", name="ck_invoices_total_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    invoice_number: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[InvoiceStatus] = mapped_column(
        SAEnum(InvoiceStatus, name="invoice_status", create_type=False),
        nullable=False,
        server_default="DRAFT",
    )
    payment_method: Mapped[Optional[PaymentMethod]] = mapped_column(
        SAEnum(PaymentMethod, name="payment_method", create_type=False), nullable=True
    )
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    discount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, server_default="0")
    tax_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, server_default="0")
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    gateway_transaction_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # The diner who asked for an emailed receipt. THIS is the analytics link:
    # repeat visits and lifetime spend are GROUP BY customer_id over invoices,
    # one bill = one payer. Nullable — most invoices have no captured contact.
    customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=True
    )
    # Send-once guard for the emailed receipt. Stamped under the invoice row lock
    # BEFORE dispatch, so two concurrent callers can never both send.
    receipt_sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    order: Mapped["Order"] = relationship("Order", back_populates="invoices")
