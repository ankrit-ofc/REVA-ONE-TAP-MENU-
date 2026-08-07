from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AnnotationStatus, FoodType


# ──────────────────────────────────────────────────────────────────────────────
# Category
# ──────────────────────────────────────────────────────────────────────────────

class CategoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Annotated[str, Field(min_length=1, max_length=80)]
    display_order: Annotated[int, Field(ge=0)] = 0
    is_available: bool = True
    # NULL = top-level category; otherwise a subcategory of parent_id (same tenant).
    parent_id: uuid.UUID | None = None


class CategoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Annotated[str, Field(min_length=1, max_length=80)] | None = None
    display_order: Annotated[int, Field(ge=0)] | None = None
    is_available: bool | None = None
    # Move under a new parent; None keeps the current parent (use parent_id_set to clear).
    parent_id: uuid.UUID | None = None
    # Explicit flag to distinguish "don't change parent" (False) from "set to root/NULL"
    # or "set to a value" (True) — since parent_id=None is ambiguous otherwise.
    parent_id_set: bool = False


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    restaurant_id: uuid.UUID
    parent_id: uuid.UUID | None
    name: str
    display_order: int
    is_active: bool
    is_available: bool
    created_at: datetime
    updated_at: datetime


# ──────────────────────────────────────────────────────────────────────────────
# Product
# ──────────────────────────────────────────────────────────────────────────────

class ProductCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category_id: uuid.UUID
    name: Annotated[str, Field(min_length=1, max_length=120)]
    description: Annotated[str, Field(max_length=255)] | None = None
    base_price: Annotated[Decimal, Field(ge=Decimal("0"))]
    tax_rate: Annotated[Decimal, Field(ge=Decimal("0"), le=Decimal("100"))] = Decimal("0")
    food_type: FoodType = FoodType.NON_VEG
    is_available: bool = True
    has_variants: bool = False
    allows_addons: bool = False
    # image_url intentionally absent — set only by the backend upload handler


class ProductUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category_id: uuid.UUID | None = None
    name: Annotated[str, Field(min_length=1, max_length=120)] | None = None
    description: Annotated[str, Field(max_length=255)] | None = None
    base_price: Annotated[Decimal, Field(ge=Decimal("0"))] | None = None
    tax_rate: Annotated[Decimal, Field(ge=Decimal("0"), le=Decimal("100"))] | None = None
    food_type: FoodType | None = None
    is_available: bool | None = None
    has_variants: bool | None = None
    allows_addons: bool | None = None
    # Feature/unfeature in the customer menu's "Today's Special" section.
    is_todays_special: bool | None = None
    # image_url intentionally absent — set only by the backend upload handler


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    restaurant_id: uuid.UUID
    category_id: uuid.UUID
    name: str
    description: str | None
    base_price: Decimal
    tax_rate: Decimal
    food_type: FoodType
    is_available: bool
    is_active: bool
    has_variants: bool
    allows_addons: bool
    is_todays_special: bool
    image_url: str | None
    created_at: datetime
    updated_at: datetime


# ──────────────────────────────────────────────────────────────────────────────
# Product CSV Import
# ──────────────────────────────────────────────────────────────────────────────

class ImportRowError(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    row: int
    field: str
    message: str
    raw: str


class ImportPreviewResponse(BaseModel):
    valid_rows: int
    products_to_create: int
    duplicates_skipped: int
    new_categories: list[str]
    existing_categories: list[str]
    errors: list[ImportRowError]


class ImportCommitResponse(BaseModel):
    categories_created: int
    products_created: int
    duplicates_skipped: int


# ──────────────────────────────────────────────────────────────────────────────
# Product Variant
# ──────────────────────────────────────────────────────────────────────────────

class VariantCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Annotated[str, Field(min_length=1, max_length=60)]
    price: Annotated[Decimal, Field(ge=Decimal("0"))]


class VariantUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Annotated[str, Field(min_length=1, max_length=60)] | None = None
    price: Annotated[Decimal, Field(ge=Decimal("0"))] | None = None


class VariantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    product_id: uuid.UUID
    restaurant_id: uuid.UUID
    name: str
    price: Decimal
    is_active: bool


# ──────────────────────────────────────────────────────────────────────────────
# Product Addon
# ──────────────────────────────────────────────────────────────────────────────

class AddonCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Annotated[str, Field(min_length=1, max_length=60)]
    price: Annotated[Decimal, Field(ge=Decimal("0"))]


class AddonUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Annotated[str, Field(min_length=1, max_length=60)] | None = None
    price: Annotated[Decimal, Field(ge=Decimal("0"))] | None = None


class AddonResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    restaurant_id: uuid.UUID
    name: str
    price: Decimal
    is_active: bool


# ──────────────────────────────────────────────────────────────────────────────
# Addon Mapping
# ──────────────────────────────────────────────────────────────────────────────

class AddonMappingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    addon_id: uuid.UUID


class AddonMappingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    product_id: uuid.UUID
    addon_id: uuid.UUID
    addon: AddonResponse


# ──────────────────────────────────────────────────────────────────────────────
# Restaurant Settings
# ──────────────────────────────────────────────────────────────────────────────

# Six customer-menu layouts (admin Settings → "Edit menu"). "classic" is the
# thumbnail-left list every restaurant already renders today — it is the
# server_default so theming stays opt-in and no existing restaurant's menu
# changes appearance until an admin actively picks one of the other five.
# Shared by the admin update/response schemas and the customer-facing
# MenuPublic payload.
MenuTemplate = Literal["classic", "photo_grid", "elegant_list", "compact_list", "magazine", "bold_cards"]
MENU_TEMPLATES: tuple[str, ...] = ("classic", "photo_grid", "elegant_list", "compact_list", "magazine", "bold_cards")
_HEX_COLOR_PATTERN = r"^#[0-9A-Fa-f]{6}$"


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # SOFT-DEPRECATED: accepted so staff-mobile clients do not 422, but IGNORED
    # by update_settings. Sole truth is restaurants.qr_pay_enabled (superadmin).
    enable_qr_payment: bool | None = None
    waiter_can_accept_payment: bool | None = None
    allow_order_reopen: bool | None = None
    # Waiter must approve each batch of customer-ordered items before the
    # kitchen sees it / the KOT prints.
    require_order_approval: bool | None = None
    currency: Annotated[str, Field(min_length=3, max_length=3)] | None = None
    timezone: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    # Location-based ordering (geofence). lat/lng are captured by the admin's
    # "Use my current location" button; they may be set back to null to clear.
    require_location: bool | None = None
    latitude: Annotated[float, Field(ge=-90, le=90)] | None = None
    longitude: Annotated[float, Field(ge=-180, le=180)] | None = None
    geofence_radius_meters: Annotated[float, Field(gt=0, le=100000)] | None = None
    # Thermal printing (counter auto-print toggles + bill copy count).
    print_kot_enabled: bool | None = None
    print_bill_enabled: bool | None = None
    bill_copies: Annotated[int, Field(ge=1, le=3)] | None = None
    # KOT pipeline: browser (WebUSB print station) or worker (kot-printer service).
    kot_print_mode: Literal["browser", "worker"] | None = None
    # Windows printer name the worker routes tickets to. "" clears it.
    kot_printer_name: Annotated[str, Field(max_length=120)] | None = None
    # Customer-menu presentation (admin Settings → "Edit menu").
    menu_template: MenuTemplate | None = None
    menu_accent_color: Annotated[str, Field(pattern=_HEX_COLOR_PATTERN)] | None = None
    # Heading for the customer menu's "Today's Special" section. Whitespace-only
    # (including "") is normalized to NULL by update_settings, restoring the
    # default "Today's Special" text.
    specials_section_title: Annotated[str, Field(max_length=80)] | None = None
    # Promotional popup (admin Menu Design → "Scan popup"). Every *_text field
    # below is whitespace-normalized to NULL by update_settings, same rule as
    # specials_section_title. popup_illustration_url is intentionally absent
    # here — set only via POST /admin/settings/popup-illustration, mirroring
    # banner_image_url.
    popup_enabled: bool | None = None
    popup_badge_text: Annotated[str, Field(max_length=30)] | None = None
    popup_headline: Annotated[str, Field(max_length=60)] | None = None
    popup_masthead_subline: Annotated[str, Field(max_length=80)] | None = None
    popup_bubble_text: Annotated[str, Field(max_length=100)] | None = None
    popup_kicker: Annotated[str, Field(max_length=60)] | None = None
    popup_tagline: Annotated[str, Field(max_length=100)] | None = None
    popup_section_label: Annotated[str, Field(max_length=40)] | None = None
    popup_cta_text: Annotated[str, Field(max_length=40)] | None = None
    popup_footer_text: Annotated[str, Field(max_length=80)] | None = None
    # Ordered list of up to 5 featured product ids.
    popup_product_ids: Annotated[list[uuid.UUID], Field(max_length=5)] | None = None


class SettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    restaurant_id: uuid.UUID
    # enable_qr_payment removed from response — sole truth is restaurants.qr_pay_enabled.
    waiter_can_accept_payment: bool
    allow_order_reopen: bool
    require_order_approval: bool
    currency: str
    timezone: str
    require_location: bool
    latitude: float | None
    longitude: float | None
    geofence_radius_meters: float
    print_kot_enabled: bool
    print_bill_enabled: bool
    bill_copies: int
    kot_print_mode: str
    kot_printer_name: str | None
    # Worker credential — exposed on the ADMIN-only settings response so the
    # Devices page can show it for the worker's config.json. Never in PrintConfig.
    kot_worker_token: str | None
    # Customer menu hero image; set only via POST /admin/settings/banner-image.
    banner_image_url: str | None
    # Payment QR shown to guests at billing; set only via POST /admin/settings/payment-qr.
    payment_qr_url: str | None
    # Customer-menu presentation (admin Settings → "Edit menu").
    menu_template: str
    menu_accent_color: str | None
    specials_section_title: str | None
    # Promotional popup (admin Menu Design → "Scan popup").
    popup_enabled: bool
    popup_badge_text: str | None
    popup_headline: str | None
    popup_masthead_subline: str | None
    popup_bubble_text: str | None
    popup_kicker: str | None
    popup_tagline: str | None
    popup_section_label: str | None
    popup_cta_text: str | None
    popup_footer_text: str | None
    # Set only via POST /admin/settings/popup-illustration.
    popup_illustration_url: str | None
    popup_product_ids: list[uuid.UUID]
    # Read-only STORED restaurants flags (for admin UI; not editable here).
    ar_enabled: bool = True
    qr_pay_enabled: bool = True


class PaymentQrResponse(BaseModel):
    """The restaurant's payment QR, readable by billing staff (COUNTER/ADMIN/
    WAITER) so the staff app can display it to a guest. Settings themselves
    remain ADMIN-only to edit. NULL → no QR configured."""
    model_config = ConfigDict(from_attributes=True)
    payment_qr_url: str | None


class PrintConfigResponse(BaseModel):
    """Minimal printer config readable by counter staff (settings are ADMIN-only)."""
    model_config = ConfigDict(from_attributes=True)
    print_kot_enabled: bool
    print_bill_enabled: bool
    bill_copies: int
    kot_print_mode: str
    kot_printer_name: str | None


# ──────────────────────────────────────────────────────────────────────────────
# Customer-facing menu schemas (read-only, hides inactive/unavailable)
# ──────────────────────────────────────────────────────────────────────────────

class AddonPublic(BaseModel):
    id: uuid.UUID
    name: str
    price: Decimal


class VariantPublic(BaseModel):
    id: uuid.UUID
    name: str
    price: Decimal


class AnnotationPublic(BaseModel):
    """Customer-facing view of a per-component nutrition hotspot. Only ever built from
    admin_verified, active annotations on a published model — see menu_service._product_public.
    Deliberately narrower than the admin AnnotationResponse (app/schemas/ar.py): no
    product_id (redundant here), no source, no timestamps. `id` is kept (not in the
    original field spec) because the frontend needs a stable key for the model-viewer
    hotspot slot name and the React list key; it leaks nothing sensitive."""
    id: uuid.UUID
    label: str
    position_x: float
    position_y: float
    position_z: float
    normal_x: float
    normal_y: float
    normal_z: float
    calories: Decimal | None
    protein_g: Decimal | None
    carbs_g: Decimal | None
    fat_g: Decimal | None
    allergens: list[str]
    status: AnnotationStatus


class ProductPublic(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    base_price: Decimal
    tax_rate: Decimal
    food_type: FoodType
    image_url: str | None
    has_variants: bool
    allows_addons: bool
    variants: list[VariantPublic]
    addons: list[AddonPublic]
    # AR model URLs — only set when the admin has PUBLISHED a ready model. The customer
    # shows the "View on my table" AR button (GLB on Android/web, USDZ on iOS) iff these
    # are present; unpublished/draft models are never exposed here.
    model_glb_url: str | None = None
    model_usdz_url: str | None = None
    # Admin-verified nutrition hotspots for the AR viewer. Only present alongside a
    # published model (same gate as model_glb_url above); optional/None everywhere else
    # so older cached responses and non-AR products are unaffected.
    annotations: list[AnnotationPublic] | None = None


class CategoryPublic(BaseModel):
    id: uuid.UUID
    name: str
    display_order: int
    products: list[ProductPublic]
    # Nested subcategories (empty for leaf categories). The customer menu is a tree.
    children: list["CategoryPublic"] = []


class MenuPublic(BaseModel):
    """Full customer menu page payload: per-restaurant hero banner (NULL →
    client falls back to the stock image), today's specials, and the category
    tree. All derived from the table session's restaurant only."""
    banner_image_url: str | None
    specials: list[ProductPublic]
    categories: list[CategoryPublic]
    # STORED restaurants.* flags — refreshed on every GET /menu.
    order_enabled: bool
    call_waiter_enabled: bool
    ar_enabled: bool
    qr_pay_enabled: bool
    # Menu theming (admin Settings → "Edit menu"). menu_accent_color NULL →
    # client falls back to its built-in default accent.
    menu_template: str
    menu_accent_color: str | None
    # "Today's Special" section heading. NULL → client falls back to the
    # default "Today's Special" text.
    specials_section_title: str | None
    # Promotional popup shown on first menu load of a table session (admin
    # Menu Design → "Scan popup"). Client renders it only when popup_enabled
    # and at least one of popup_product_ids resolves against categories/
    # specials above. popup_headline NULL falls back to the restaurant name;
    # popup_cta_text NULL falls back to "See the menu"; every other popup_*
    # field NULL/blank hides that element entirely.
    popup_enabled: bool
    popup_badge_text: str | None
    popup_headline: str | None
    popup_masthead_subline: str | None
    popup_bubble_text: str | None
    popup_kicker: str | None
    popup_tagline: str | None
    popup_section_label: str | None
    popup_cta_text: str | None
    popup_footer_text: str | None
    popup_illustration_url: str | None
    popup_product_ids: list[uuid.UUID]
