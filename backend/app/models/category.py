import uuid
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, TenantMixin

if TYPE_CHECKING:
    from app.models.product import Product


class Category(Base, TimestampMixin, TenantMixin):
    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Self-referencing parent for a multilevel menu tree (NULL = root category).
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("categories.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    # is_active = soft-delete flag (Delete). is_available = show/hide toggle that
    # gates the customer menu and cascades to products when turned off.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    products: Mapped[list["Product"]] = relationship("Product", back_populates="category")
    parent: Mapped[Optional["Category"]] = relationship(
        "Category", remote_side=[id], back_populates="children"
    )
    children: Mapped[list["Category"]] = relationship(
        "Category", back_populates="parent"
    )
