import uuid
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import WaiterCallStatus
from app.models.mixins import TimestampMixin, TenantMixin

if TYPE_CHECKING:
    from app.models.table import Table
    from app.models.user import User


class WaiterCall(Base, TimestampMixin, TenantMixin):
    """
    A customer's 'Call Waiter' request. Stored (not merely broadcast) so the waiter
    dashboard shows a live list of open calls and can confirm attendance — who
    attended and when. Rows are never deleted (history); status moves PENDING ->
    ATTENDED only. A partial unique index keeps at most one PENDING call per table.
    """

    __tablename__ = "waiter_calls"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'ATTENDED')",
            name="ck_waiter_calls_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    table_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tables.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # Stored as VARCHAR + CHECK (mirrors restaurant_settings.kot_print_mode) rather
    # than a native PG enum; WaiterCallStatus supplies the allowed values in code.
    status: Mapped[str] = mapped_column(String(10), nullable=False, server_default=WaiterCallStatus.PENDING.value)
    attended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    attended_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )

    table: Mapped["Table"] = relationship("Table")
    attended_by: Mapped[Optional["User"]] = relationship("User")
