import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, TenantMixin

if TYPE_CHECKING:
    from app.models.user import User


class Restaurant(Base, TimestampMixin):
    __tablename__ = "restaurants"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    settings: Mapped["RestaurantSettings"] = relationship(
        "RestaurantSettings", back_populates="restaurant", uselist=False
    )
    users: Mapped[list["User"]] = relationship("User", back_populates="restaurant")


class RestaurantSettings(Base, TimestampMixin, TenantMixin):
    __tablename__ = "restaurant_settings"
    __table_args__ = (
        UniqueConstraint("restaurant_id", name="uq_restaurant_settings_restaurant"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enable_qr_payment: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    waiter_can_accept_payment: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    allow_order_reopen: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    # When true, each batch of customer-ordered items waits in PENDING_APPROVAL
    # (invisible to kitchen, no KOT) until a waiter approves or rejects it.
    require_order_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="NPR")
    timezone: Mapped[str] = mapped_column(Text, nullable=False, server_default="Asia/Kathmandu")

    # Location-based ordering (geofence). When require_location is true and a point
    # is set, POST /scan rejects devices farther than geofence_radius_meters.
    require_location: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    geofence_radius_meters: Mapped[float] = mapped_column(Float, nullable=False, server_default="50")

    # Thermal printing (counter computer auto-prints via WebUSB). Pairing is
    # browser-local; these toggles/copies are the shared per-restaurant config.
    print_kot_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    print_bill_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    bill_copies: Mapped[int] = mapped_column(Integer, nullable=False, server_default="2")

    # KOT print pipeline: 'browser' = counter browser prints via WebUSB (original
    # behaviour); 'worker' = tickets are queued in kot_print_jobs for the external
    # kot-printer Windows service, which authenticates with kot_worker_token and
    # prints to the installed Windows printer named kot_printer_name.
    kot_print_mode: Mapped[str] = mapped_column(String(10), nullable=False, server_default="browser")
    kot_printer_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    kot_worker_token: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)

    restaurant: Mapped["Restaurant"] = relationship("Restaurant", back_populates="settings")
