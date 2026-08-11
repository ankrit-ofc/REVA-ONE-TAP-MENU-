import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional, TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint, DateTime, Enum as SAEnum, ForeignKey,
    Integer, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import OrderStatus, OrderItemStatus
from app.models.mixins import TimestampMixin, TenantMixin

if TYPE_CHECKING:
    from app.models.table import Table
    from app.models.invoice import Invoice


class Order(Base, TimestampMixin, TenantMixin):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("restaurant_id", "order_number", name="uq_orders_restaurant_order_number"),
        # Partial unique index (one active order per table) is created in the migration,
        # not expressible as a simple constraint here.
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    table_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tables.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    order_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[OrderStatus] = mapped_column(
        SAEnum(OrderStatus, name="order_status", create_type=False),
        nullable=False,
        server_default="OPEN",
    )
    # Set when the customer taps "Request Bill". Staff may move the order to
    # MEAL_FINISHED only once this is set (enforced in order_service).
    bill_requested_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Contact-capture CARRIER only — not the analytics link (that is
    # invoices.customer_id). The customer submits their email when they tap
    # "Request Bill", which is before staff generate the invoice, so there is no
    # invoice row to point at yet. The value is copied onto the invoice at
    # generation time (invoice_service.generate_invoice and
    # payment_service.quick_bill_and_close). Never exposed in a response schema.
    customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=True
    )
    # The table session this order was opened from — the visit key that
    # table_id alone cannot give (one table hosts many parties a day).
    #
    # Nullable and NEVER backfilled. Rows written before this column existed
    # stay NULL, because the only way to reconstruct them would be to guess from
    # table_id + a session time window — the exact heuristic this column exists
    # to replace. A guessed value in an exact-looking column is worse than a
    # NULL, so every consumer must treat NULL as "before instrumentation" and
    # exclude it from denominators rather than assume it means "no session".
    #
    # Set once at order creation (order_service.place_or_append), never updated:
    # appending a second round to an OPEN order keeps the original session, which
    # is what makes it a visit key rather than a last-touch marker.
    session_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("table_sessions.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    table: Mapped["Table"] = relationship("Table", back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship("OrderItem", back_populates="order")
    invoices: Mapped[list["Invoice"]] = relationship("Invoice", back_populates="order")


class OrderItem(Base, TimestampMixin, TenantMixin):
    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_order_items_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="ck_order_items_unit_price_non_negative"),
        CheckConstraint("tax_rate >= 0", name="ck_order_items_tax_rate_non_negative"),
        CheckConstraint(
            "list_unit_price IS NULL OR list_unit_price >= 0",
            name="ck_order_items_list_price_non_negative",
        ),
        # Provenance is a pair or it is nothing, so `offer_name IS NOT NULL` is a
        # reliable "this line was discounted" test for every consumer.
        CheckConstraint(
            "(offer_name IS NULL) = (list_unit_price IS NULL)",
            name="ck_order_items_offer_provenance",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # FK kept for referential integrity; snapshot cols hold the authoritative data at order time.
    product_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[OrderItemStatus] = mapped_column(
        SAEnum(OrderItemStatus, name="order_item_status", create_type=False),
        nullable=False,
        server_default="NEW",
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    special_instructions: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Snapshot columns — frozen at order time; never updated when the product changes.
    product_name: Mapped[str] = mapped_column(Text, nullable=False)
    variant_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)

    # Offer provenance — set together, only when a Dead Hours offer priced this
    # line. unit_price already records WHAT was charged; these record WHY, so a
    # receipt reprinted months later can show "Rs 150 (Afternoon Special, was
    # Rs 200)" rather than a bare number that reads as a mispriced item.
    # NULL on every line that paid the normal price, and never backfilled: rows
    # written before offers existed had no offer, and copying unit_price into
    # list_unit_price would fabricate an anchor that was never quoted.
    offer_name: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    list_unit_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)

    # State-transition timestamps
    preparing_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ready_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    served_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    order: Mapped["Order"] = relationship("Order", back_populates="items")
    addons: Mapped[list["OrderItemAddon"]] = relationship("OrderItemAddon", back_populates="order_item")


class OrderItemAddon(Base, TimestampMixin, TenantMixin):
    __tablename__ = "order_item_addons"
    __table_args__ = (
        CheckConstraint("addon_price >= 0", name="ck_order_item_addons_price_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_item_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("order_items.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    # Snapshot columns
    addon_name: Mapped[str] = mapped_column(Text, nullable=False)
    addon_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    order_item: Mapped["OrderItem"] = relationship("OrderItem", back_populates="addons")
