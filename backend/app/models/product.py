import uuid
from decimal import Decimal
from typing import Optional, TYPE_CHECKING

from sqlalchemy import (
    Boolean, CheckConstraint, Enum as SAEnum, ForeignKey, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import ArModelStatus, FoodType
from app.models.mixins import TimestampMixin, TenantMixin

if TYPE_CHECKING:
    from app.models.category import Category
    from app.models.ar import GenerationJob, ModelAnnotation, ProductViewImage


class Product(Base, TimestampMixin, TenantMixin):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("base_price >= 0", name="ck_products_base_price_non_negative"),
        CheckConstraint("tax_rate >= 0", name="ck_products_tax_rate_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    base_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, server_default="0")
    food_type: Mapped[FoodType] = mapped_column(
        SAEnum(FoodType, name="food_type", create_type=False),
        nullable=False,
        server_default=FoodType.NON_VEG.value,
    )
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    has_variants: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    allows_addons: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    # Featured in the customer menu's "Today's Special" section (admin toggle).
    is_todays_special: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    # Set only by the backend upload handler (Phase 4); never accepted from the client directly.
    image_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Optional AR / 3D model (backend-set URLs only). model_status='NONE' → no model,
    # product behaves exactly as before the AR feature existed.
    model_status: Mapped[ArModelStatus] = mapped_column(
        SAEnum(ArModelStatus, name="ar_model_status", create_type=False),
        nullable=False,
        server_default=ArModelStatus.NONE.value,
    )
    model_glb_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model_usdz_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model_published: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    category: Mapped["Category"] = relationship("Category", back_populates="products")
    variants: Mapped[list["ProductVariant"]] = relationship("ProductVariant", back_populates="product")
    addon_mappings: Mapped[list["ProductAddonMapping"]] = relationship(
        "ProductAddonMapping", back_populates="product"
    )
    view_images: Mapped[list["ProductViewImage"]] = relationship(
        "ProductViewImage", back_populates="product"
    )
    annotations: Mapped[list["ModelAnnotation"]] = relationship(
        "ModelAnnotation", back_populates="product"
    )
    generation_jobs: Mapped[list["GenerationJob"]] = relationship(
        "GenerationJob", back_populates="product"
    )


class ProductVariant(Base, TimestampMixin, TenantMixin):
    __tablename__ = "product_variants"
    __table_args__ = (
        CheckConstraint("price >= 0", name="ck_product_variants_price_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    product: Mapped["Product"] = relationship("Product", back_populates="variants")


class ProductAddon(Base, TimestampMixin, TenantMixin):
    __tablename__ = "product_addons"
    __table_args__ = (
        CheckConstraint("price >= 0", name="ck_product_addons_price_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    mappings: Mapped[list["ProductAddonMapping"]] = relationship(
        "ProductAddonMapping", back_populates="addon"
    )


class ProductAddonMapping(Base, TimestampMixin, TenantMixin):
    __tablename__ = "product_addon_mappings"
    __table_args__ = (
        UniqueConstraint("product_id", "addon_id", name="uq_product_addon_mappings_product_addon"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    addon_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("product_addons.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    product: Mapped["Product"] = relationship("Product", back_populates="addon_mappings")
    addon: Mapped["ProductAddon"] = relationship("ProductAddon", back_populates="mappings")
