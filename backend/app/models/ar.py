"""
SQLAlchemy models for the optional per-product AR / 3D-model feature.

All three tables are tenant-owned (TenantMixin → restaurant_id NOT NULL + RLS) and
soft-deleted (is_active). Backend-set URLs only; the client never supplies image_url /
model URLs. See migration 0012 for the DDL and RLS policies.
"""

import uuid
from decimal import Decimal
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Boolean, Float, ForeignKey, Numeric, Text, Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import (
    AnnotationSource,
    AnnotationStatus,
    GenerationJobKind,
    GenerationJobStatus,
    ProductView,
)
from app.models.mixins import TenantMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.product import Product


class ProductViewImage(Base, TimestampMixin, TenantMixin):
    """One labeled source photo (front/back/left/right/top) for generation + marking."""

    __tablename__ = "product_view_images"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    view: Mapped[ProductView] = mapped_column(
        SAEnum(ProductView, name="product_view", create_type=False), nullable=False
    )
    # Backend-set via image_service; never accepted from the client.
    image_url: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    product: Mapped["Product"] = relationship("Product", back_populates="view_images")


class ModelAnnotation(Base, TimestampMixin, TenantMixin):
    """A per-component nutrition hotspot on the model (AI draft → admin verified)."""

    __tablename__ = "model_annotations"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(Text, nullable=False)

    # Hotspot placement on the mesh surface (geometry → float, not money).
    position_x: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    position_y: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    position_z: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    normal_x: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    normal_y: Mapped[float] = mapped_column(Float, nullable=False, server_default="1")
    normal_z: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")

    # Nutrition values — NUMERIC/Decimal (never float), nullable until known.
    calories: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    protein_g: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    carbs_g: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    fat_g: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    allergens: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default="[]")

    source: Mapped[AnnotationSource] = mapped_column(
        SAEnum(AnnotationSource, name="annotation_source", create_type=False), nullable=False
    )
    status: Mapped[AnnotationStatus] = mapped_column(
        SAEnum(AnnotationStatus, name="annotation_status", create_type=False), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    product: Mapped["Product"] = relationship("Product", back_populates="annotations")


class GenerationJob(Base, TimestampMixin, TenantMixin):
    """Drives the generation / marking pipeline for one product."""

    __tablename__ = "generation_jobs"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    kind: Mapped[GenerationJobKind] = mapped_column(
        SAEnum(GenerationJobKind, name="generation_job_kind", create_type=False), nullable=False
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[GenerationJobStatus] = mapped_column(
        SAEnum(GenerationJobStatus, name="generation_job_status", create_type=False),
        nullable=False,
        server_default=GenerationJobStatus.QUEUED.value,
    )
    external_job_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    product: Mapped["Product"] = relationship("Product", back_populates="generation_jobs")
