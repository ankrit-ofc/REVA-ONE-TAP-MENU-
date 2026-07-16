import uuid
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import SessionStatus
from app.models.mixins import TimestampMixin, TenantMixin

if TYPE_CHECKING:
    from app.models.order import Order


class Table(Base, TimestampMixin, TenantMixin):
    __tablename__ = "tables"
    __table_args__ = (
        UniqueConstraint("name", "restaurant_id", name="uq_tables_name_restaurant"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        __import__("sqlalchemy").Boolean, nullable=False, server_default="true"
    )

    sessions: Mapped[list["TableSession"]] = relationship("TableSession", back_populates="table")
    orders: Mapped[list["Order"]] = relationship("Order", back_populates="table")


class TableSession(Base, TimestampMixin, TenantMixin):
    __tablename__ = "table_sessions"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    table_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tables.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    token: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    status: Mapped[SessionStatus] = mapped_column(
        SAEnum(SessionStatus, name="session_status", create_type=False),
        nullable=False,
        server_default="ACTIVE",
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    invalidated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    table: Mapped["Table"] = relationship("Table", back_populates="sessions")
