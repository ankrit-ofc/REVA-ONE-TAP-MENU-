import uuid
from datetime import time
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean, Enum as SAEnum, Float, Integer, String, Text, Time, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import RestaurantPlan
from app.models.mixins import TimestampMixin, TenantMixin

if TYPE_CHECKING:
    from app.models.user import User


class Restaurant(Base, TimestampMixin):
    __tablename__ = "restaurants"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    # Platform plan label (basic|starter|custom). Assigning a plan WRITES the
    # four preset booleans via apply_plan_preset; reads always use the STORED
    # columns below (overrides persist — never recompute from plan on read).
    plan: Mapped[RestaurantPlan] = mapped_column(
        SAEnum(RestaurantPlan, name="restaurant_plan", create_type=False, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        server_default=RestaurantPlan.CUSTOM.value,
    )
    # STORED feature flags — source of truth for gating + customer UI.
    order_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    call_waiter_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    ar_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    qr_pay_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

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
    # SOFT-DEPRECATED: sole source of truth is restaurants.qr_pay_enabled.
    # Column kept so older staff-mobile clients that still PUT enable_qr_payment
    # do not 422; SettingsUpdate accept-and-ignores it. Drop in a later migration
    # once mobile stops sending the field.
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

    # Customer menu hero image. Set only by the backend upload handler (Phase 4
    # image pipeline); never accepted from the client. NULL → stock hero.
    banner_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Payment QR (eSewa/Khalti/Fonepay) shown to guests on the staff Billing
    # screen. Same rules as the banner: set only by the backend upload handler,
    # never accepted from the client. NULL → no QR configured.
    payment_qr_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Customer-menu presentation. menu_template picks one of six layouts
    # (see MENU_TEMPLATES); "classic" is today's thumbnail-left list and the
    # default, so theming is opt-in and no restaurant's menu changes on
    # deploy until an admin picks a different template. menu_accent_color is
    # a hex colour applied to buttons/headings/chips/price/cart badge only.
    # NULL accent → client default. Both are admin-editable via SettingsUpdate.
    menu_template: Mapped[str] = mapped_column(String(20), nullable=False, server_default="classic")
    menu_accent_color: Mapped[str | None] = mapped_column(String(7), nullable=True)

    # Heading for the customer menu's "Today's Special" section. NULL → client
    # falls back to the default "Today's Special" text. Admin-editable via
    # SettingsUpdate; whitespace-only input is normalized to NULL on write.
    specials_section_title: Mapped[str | None] = mapped_column(String(80), nullable=True)

    # Promotional popup shown on first menu load of a table session (admin
    # Menu Design → "Scan popup"). popup_enabled gates it; every popup_*_text
    # field is NULL/whitespace = hidden on the customer side, except headline
    # (falls back to restaurant name) and cta_text (falls back to "See the
    # menu"). popup_illustration_url is set only by the backend upload
    # handler, mirroring banner_image_url — never accepted from the client
    # directly. popup_product_ids is an ordered JSON array of up to 5 product
    # UUID strings (order matters; products are never hard-deleted in this
    # codebase, so a stale id just stops resolving via the customer menu
    # tree — no FK needed).
    popup_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    popup_badge_text: Mapped[str | None] = mapped_column(String(30), nullable=True)
    popup_headline: Mapped[str | None] = mapped_column(String(60), nullable=True)
    popup_masthead_subline: Mapped[str | None] = mapped_column(String(80), nullable=True)
    popup_bubble_text: Mapped[str | None] = mapped_column(String(100), nullable=True)
    popup_kicker: Mapped[str | None] = mapped_column(String(60), nullable=True)
    popup_tagline: Mapped[str | None] = mapped_column(String(100), nullable=True)
    popup_section_label: Mapped[str | None] = mapped_column(String(40), nullable=True)
    popup_cta_text: Mapped[str | None] = mapped_column(String(40), nullable=True)
    popup_footer_text: Mapped[str | None] = mapped_column(String(80), nullable=True)
    popup_illustration_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    popup_product_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default="[]")

    # Nightly One-Liner: the daily summary email sent to the owner at closing
    # time. daily_report_closing_time is a LOCAL wall-clock time, interpreted in
    # this restaurant's `timezone` above — never UTC. The two must be read
    # together, which is why both live in the same settings row and the same
    # admin page section. NULL recipient → all active ADMIN users of the tenant.
    daily_report_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    daily_report_closing_time: Mapped[time] = mapped_column(
        Time(timezone=False), nullable=False, server_default="22:00"
    )
    daily_report_recipient: Mapped[str | None] = mapped_column(String(255), nullable=True)

    restaurant: Mapped["Restaurant"] = relationship("Restaurant", back_populates="settings")
