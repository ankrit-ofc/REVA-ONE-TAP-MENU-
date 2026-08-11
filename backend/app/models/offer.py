import uuid
from datetime import time
from decimal import Decimal
from typing import Optional, TYPE_CHECKING

from sqlalchemy import (
    Boolean, CheckConstraint, Enum as SAEnum, ForeignKey, Numeric,
    SmallInteger, String, Time, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import OfferAppliesTo, OfferDiscountType
from app.models.mixins import TimestampMixin, TenantMixin

if TYPE_CHECKING:
    from app.models.product import Product


class OfferWindow(Base, TimestampMixin, TenantMixin):
    """A named, time-boxed DISCOUNT that a restaurant offers on chosen items.

    The engine can only ever price BELOW the normal price — see the CHECK
    constraints, which encode that rule in the database rather than trusting the
    application to remember it. The menu keeps showing the anchor price; what a
    customer sees during a live window is this offer's `name` and its end time
    next to the reduced price, so a diner paying full price at 8pm can see what
    the afternoon deal was and why it does not apply to them.

    `start_time`/`end_time` are LOCAL wall-clock times in the restaurant's own
    timezone (restaurant_settings.timezone), never UTC — same convention as
    daily_report_closing_time, and for the same reason: "2pm" is a recurring
    local fact, not an instant.

    `weekday_mask` is a 7-bit field with bit 0 = Monday, matching Python's
    date.weekday(). The weekday must be derived from the restaurant's LOCAL
    now: a UTC weekday flips at 18:15 in Kathmandu and would file Tuesday
    evening trade under Monday.

    Soft delete via is_active (CLAUDE.md §3 — no hard delete on business
    records). is_enabled is a separate, owner-facing switch: the engine
    proposes, the owner approves, and a disabled offer prices nothing.
    """

    __tablename__ = "offer_windows"
    __table_args__ = (
        CheckConstraint("discount_value > 0", name="ck_offer_windows_discount_positive"),
        CheckConstraint(
            "discount_type <> 'PERCENT' OR discount_value <= 100",
            name="ck_offer_windows_percent_max",
        ),
        CheckConstraint(
            "min_resulting_price IS NULL OR min_resulting_price > 0",
            name="ck_offer_windows_floor_positive",
        ),
        CheckConstraint(
            "discount_type <> 'FIXED' OR min_resulting_price IS NOT NULL",
            name="ck_offer_windows_fixed_needs_floor",
        ),
        CheckConstraint("end_time > start_time", name="ck_offer_windows_time_order"),
        CheckConstraint(
            "weekday_mask BETWEEN 1 AND 127", name="ck_offer_windows_weekday_mask"
        ),
        CheckConstraint(
            "(applies_to = 'CATEGORY') = (category_id IS NOT NULL)",
            name="ck_offer_windows_target",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    discount_type: Mapped[OfferDiscountType] = mapped_column(
        SAEnum(OfferDiscountType, name="offer_discount_type", create_type=False),
        nullable=False,
    )
    discount_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    # The price an item may never be discounted below. REQUIRED for FIXED (the
    # owner states it; there is deliberately no default). Optional for PERCENT,
    # but never inert — when set, the resolver clamps to it either way.
    # Pre-tax, same basis as products.base_price / product_variants.price.
    min_resulting_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    start_time: Mapped[time] = mapped_column(Time(timezone=False), nullable=False)
    end_time: Mapped[time] = mapped_column(Time(timezone=False), nullable=False)
    weekday_mask: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    applies_to: Mapped[OfferAppliesTo] = mapped_column(
        SAEnum(OfferAppliesTo, name="offer_applies_to", create_type=False), nullable=False
    )
    # Set iff applies_to is CATEGORY. Applies to products DIRECTLY in this
    # category — not its subcategories. Descendants are deliberately excluded so
    # that adding a subcategory later cannot silently widen a live discount.
    category_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("categories.id", ondelete="RESTRICT"), nullable=True
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    products: Mapped[list["OfferWindowProduct"]] = relationship(
        "OfferWindowProduct", back_populates="offer_window"
    )


class OfferWindowProduct(Base, TimestampMixin, TenantMixin):
    """Junction: one product covered by a PRODUCTS-scoped offer.

    Configuration, not a financial record — like ProductAddonMapping it has no
    is_active and its rows are removed outright when the owner edits an offer's
    item list. Past orders are unaffected: order_items snapshots the charged
    price, the anchor, and the offer name at order time.
    """

    __tablename__ = "offer_window_products"
    __table_args__ = (
        UniqueConstraint(
            "offer_window_id", "product_id", name="uq_offer_window_products_offer_product"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    offer_window_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("offer_windows.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )

    offer_window: Mapped["OfferWindow"] = relationship(
        "OfferWindow", back_populates="products"
    )
    product: Mapped["Product"] = relationship("Product")
