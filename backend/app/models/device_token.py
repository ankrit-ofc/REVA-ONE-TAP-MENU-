import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, TenantMixin


class DeviceToken(Base, TimestampMixin, TenantMixin):
    """
    A staff device's Expo push token, so the backend can deliver notifications
    (order created, waiter called, bill requested) even when the app is closed.

    Tenant-scoped (restaurant_id via TenantMixin) and tied to the staff user who
    registered it. Soft-deactivated (is_active=False) rather than deleted when a
    token becomes invalid, so registration history is preserved.
    """

    __tablename__ = "device_tokens"
    __table_args__ = (
        CheckConstraint(
            "platform IN ('android', 'ios')",
            name="ck_device_tokens_platform",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # The Expo push token string (ExponentPushToken[...]). Unique across the table.
    token: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    platform: Mapped[str] = mapped_column(String(10), nullable=False, server_default="android")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
