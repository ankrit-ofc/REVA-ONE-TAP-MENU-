"""
Tenant-scoped CRUD for the menu domain.

Every query filters on restaurant_id derived from the verified JWT — never from
client input.  Foreign key cross-tenant checks (e.g. a product's category_id must
belong to the same restaurant) are enforced here, not in routers.

Soft delete only: is_active=False.  No hard DELETE on menu entities.
Exception: ProductAddonMapping has no is_active column (junction table, not a
financial record); its rows are hard-deleted when a mapping is removed.
"""

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.models.audit_log import AuditLog
from app.models.category import Category
from app.models.product import Product, ProductAddon, ProductAddonMapping, ProductVariant
from app.models.restaurant import RestaurantSettings
from app.models.user import User
from app.schemas.menu import (
    AddonCreate,
    AddonMappingCreate,
    AddonPublic,
    AddonUpdate,
    CategoryCreate,
    CategoryPublic,
    CategoryUpdate,
    MenuPublic,
    ProductCreate,
    ProductPublic,
    ProductUpdate,
    SettingsUpdate,
    VariantCreate,
    VariantPublic,
    VariantUpdate,
)


# ──────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _audit(
    db: Session,
    *,
    restaurant_id: uuid.UUID,
    actor: User,
    entity_type: str,
    entity_id: uuid.UUID,
    action: str,
    previous_value: dict | None = None,
    new_value: dict | None = None,
) -> None:
    """Append an audit_logs row for a privileged menu write (CLAUDE.md §3).

    Staged on the session; the caller commits in the same transaction as the
    write it describes.
    """
    db.add(AuditLog(
        id=uuid.uuid4(),
        restaurant_id=restaurant_id,
        actor_type=actor.role.value,
        actor_user_id=actor.id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        previous_value=previous_value,
        new_value=new_value,
    ))


def _get_category_or_404(db: Session, restaurant_id: uuid.UUID, category_id: uuid.UUID) -> Category:
    row = db.execute(
        select(Category).where(
            Category.id == category_id,
            Category.restaurant_id == restaurant_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    return row


def _get_product_or_404(db: Session, restaurant_id: uuid.UUID, product_id: uuid.UUID) -> Product:
    row = db.execute(
        select(Product).where(
            Product.id == product_id,
            Product.restaurant_id == restaurant_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return row


def _get_variant_or_404(
    db: Session, restaurant_id: uuid.UUID, product_id: uuid.UUID, variant_id: uuid.UUID
) -> ProductVariant:
    row = db.execute(
        select(ProductVariant).where(
            ProductVariant.id == variant_id,
            ProductVariant.product_id == product_id,
            ProductVariant.restaurant_id == restaurant_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found")
    return row


def _get_addon_or_404(db: Session, restaurant_id: uuid.UUID, addon_id: uuid.UUID) -> ProductAddon:
    row = db.execute(
        select(ProductAddon).where(
            ProductAddon.id == addon_id,
            ProductAddon.restaurant_id == restaurant_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Addon not found")
    return row


# ──────────────────────────────────────────────────────────────────────────────
# Categories
# ──────────────────────────────────────────────────────────────────────────────

_MAX_CATEGORY_DEPTH = 6  # guard against pathological trees / runaway UI


def _get_active_parent_or_422(
    db: Session, restaurant_id: uuid.UUID, parent_id: uuid.UUID
) -> Category:
    """A parent must be a live category in the same tenant."""
    parent = db.execute(
        select(Category).where(
            Category.id == parent_id,
            Category.restaurant_id == restaurant_id,
            Category.is_active.is_(True),
        )
    ).scalar_one_or_none()
    if parent is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Parent category not found",
        )
    return parent


def _depth_of(db: Session, restaurant_id: uuid.UUID, parent_id: uuid.UUID) -> int:
    """Number of ancestors of `parent_id` (root parent = depth 1). Bounded walk."""
    depth = 1
    current: uuid.UUID | None = parent_id
    seen: set[uuid.UUID] = set()
    while current is not None:
        if current in seen:  # defensive: existing data cycle
            break
        seen.add(current)
        row = db.execute(
            select(Category.parent_id).where(
                Category.id == current, Category.restaurant_id == restaurant_id
            )
        ).scalar_one_or_none()
        current = row
        if current is not None:
            depth += 1
        if depth > _MAX_CATEGORY_DEPTH + 2:  # hard stop
            break
    return depth


def _descendant_ids(
    db: Session, restaurant_id: uuid.UUID, category_id: uuid.UUID
) -> set[uuid.UUID]:
    """All descendants of a category (BFS over children), for the cycle guard."""
    result: set[uuid.UUID] = set()
    frontier = [category_id]
    while frontier:
        rows = db.execute(
            select(Category.id).where(
                Category.restaurant_id == restaurant_id,
                Category.parent_id.in_(frontier),
            )
        ).scalars().all()
        new = [r for r in rows if r not in result]
        result.update(new)
        frontier = new
    return result


def create_category(
    db: Session, restaurant_id: uuid.UUID, data: CategoryCreate, actor: User
) -> Category:
    if data.parent_id is not None:
        _get_active_parent_or_422(db, restaurant_id, data.parent_id)
        if _depth_of(db, restaurant_id, data.parent_id) >= _MAX_CATEGORY_DEPTH:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Category nesting is limited to {_MAX_CATEGORY_DEPTH} levels",
            )

    cat = Category(
        id=uuid.uuid4(),
        restaurant_id=restaurant_id,
        parent_id=data.parent_id,
        name=data.name,
        display_order=data.display_order,
        is_active=True,
        is_available=data.is_available,
    )
    db.add(cat)
    db.flush()  # assign cat.id before the audit row references it
    _audit(
        db,
        restaurant_id=restaurant_id,
        actor=actor,
        entity_type="category",
        entity_id=cat.id,
        action="CATEGORY_CREATE",
        new_value={
            "name": cat.name,
            "display_order": cat.display_order,
            "is_available": cat.is_available,
            "parent_id": str(cat.parent_id) if cat.parent_id else None,
        },
    )
    db.commit()
    db.refresh(cat)
    return cat


def list_categories(db: Session, restaurant_id: uuid.UUID) -> list[Category]:
    # Soft-deleted (is_active=False) categories are hidden from the admin list too.
    return list(
        db.execute(
            select(Category)
            .where(
                Category.restaurant_id == restaurant_id,
                Category.is_active.is_(True),
            )
            .order_by(Category.display_order, Category.created_at)
        ).scalars().all()
    )


def get_category(db: Session, restaurant_id: uuid.UUID, category_id: uuid.UUID) -> Category:
    return _get_category_or_404(db, restaurant_id, category_id)


def update_category(
    db: Session, restaurant_id: uuid.UUID, category_id: uuid.UUID, data: CategoryUpdate, actor: User
) -> Category:
    cat = _get_category_or_404(db, restaurant_id, category_id)
    previous = {
        "name": cat.name,
        "display_order": cat.display_order,
        "is_available": cat.is_available,
        "parent_id": str(cat.parent_id) if cat.parent_id else None,
    }

    if data.name is not None:
        cat.name = data.name
    if data.display_order is not None:
        cat.display_order = data.display_order

    # Re-parent only when explicitly requested (parent_id_set). parent_id=None then
    # means "make this a root". Guard against cycles and over-deep trees.
    if data.parent_id_set:
        new_parent = data.parent_id
        if new_parent is not None:
            if new_parent == cat.id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="A category cannot be its own parent",
                )
            _get_active_parent_or_422(db, restaurant_id, new_parent)
            if new_parent in _descendant_ids(db, restaurant_id, cat.id):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Cannot move a category under one of its own descendants",
                )
            if _depth_of(db, restaurant_id, new_parent) >= _MAX_CATEGORY_DEPTH:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Category nesting is limited to {_MAX_CATEGORY_DEPTH} levels",
                )
        cat.parent_id = new_parent

    cascaded_products = False
    if data.is_available is not None:
        became_unavailable = cat.is_available and not data.is_available
        cat.is_available = data.is_available
        # Cascade (one-directional): hiding a category hides its products too.
        if became_unavailable:
            db.execute(
                update(Product)
                .where(
                    Product.restaurant_id == restaurant_id,
                    Product.category_id == cat.id,
                )
                .values(is_available=False, updated_at=_now())
            )
            cascaded_products = True

    cat.updated_at = _now()
    new = {
        "name": cat.name,
        "display_order": cat.display_order,
        "is_available": cat.is_available,
        "parent_id": str(cat.parent_id) if cat.parent_id else None,
        "cascaded_products_hidden": cascaded_products,
    }
    _audit(
        db,
        restaurant_id=restaurant_id,
        actor=actor,
        entity_type="category",
        entity_id=cat.id,
        action="CATEGORY_UPDATE",
        previous_value=previous,
        new_value=new,
    )
    db.commit()
    db.refresh(cat)
    return cat


def soft_delete_category(
    db: Session, restaurant_id: uuid.UUID, category_id: uuid.UUID, actor: User
) -> Category:
    cat = _get_category_or_404(db, restaurant_id, category_id)
    cat.is_active = False
    cat.updated_at = _now()
    _audit(
        db,
        restaurant_id=restaurant_id,
        actor=actor,
        entity_type="category",
        entity_id=cat.id,
        action="CATEGORY_DELETE",
        previous_value={"is_active": True},
        new_value={"is_active": False},
    )
    db.commit()
    db.refresh(cat)
    return cat


# ──────────────────────────────────────────────────────────────────────────────
# Products
# ──────────────────────────────────────────────────────────────────────────────

def create_product(
    db: Session, restaurant_id: uuid.UUID, data: ProductCreate, actor: User
) -> Product:
    # Validate that the category belongs to this restaurant
    _get_category_or_404(db, restaurant_id, data.category_id)

    product = Product(
        id=uuid.uuid4(),
        restaurant_id=restaurant_id,
        category_id=data.category_id,
        name=data.name,
        description=data.description,
        base_price=data.base_price,
        tax_rate=data.tax_rate,
        food_type=data.food_type,
        is_available=data.is_available,
        has_variants=data.has_variants,
        allows_addons=data.allows_addons,
        is_active=True,
        image_url=None,
    )
    db.add(product)
    db.flush()
    _audit(
        db,
        restaurant_id=restaurant_id,
        actor=actor,
        entity_type="product",
        entity_id=product.id,
        action="PRODUCT_CREATE",
        new_value={
            "name": product.name,
            "category_id": str(product.category_id),
            "base_price": str(product.base_price),
            "tax_rate": str(product.tax_rate),
            "food_type": product.food_type.value,
            "is_available": product.is_available,
            "has_variants": product.has_variants,
            "allows_addons": product.allows_addons,
        },
    )
    db.commit()
    db.refresh(product)
    return product


def list_products(
    db: Session, restaurant_id: uuid.UUID, category_id: uuid.UUID | None = None
) -> list[Product]:
    # Only live products in a live category are listed — soft-deleted products,
    # and products of a soft-deleted category, disappear from the admin list.
    q = (
        select(Product)
        .join(Category, Product.category_id == Category.id)
        .where(
            Product.restaurant_id == restaurant_id,
            Product.is_active.is_(True),
            Category.is_active.is_(True),
        )
    )
    if category_id is not None:
        q = q.where(Product.category_id == category_id)
    q = q.order_by(Product.created_at)
    return list(db.execute(q).scalars().all())


def get_product(db: Session, restaurant_id: uuid.UUID, product_id: uuid.UUID) -> Product:
    return _get_product_or_404(db, restaurant_id, product_id)


def _product_snapshot(p: Product) -> dict:
    return {
        "name": p.name,
        "description": p.description,
        "category_id": str(p.category_id),
        "base_price": str(p.base_price),
        "tax_rate": str(p.tax_rate),
        "food_type": p.food_type.value,
        "is_available": p.is_available,
        "has_variants": p.has_variants,
        "allows_addons": p.allows_addons,
        "is_todays_special": p.is_todays_special,
    }


def update_product(
    db: Session, restaurant_id: uuid.UUID, product_id: uuid.UUID, data: ProductUpdate, actor: User
) -> Product:
    product = _get_product_or_404(db, restaurant_id, product_id)
    previous = _product_snapshot(product)

    if data.category_id is not None:
        # Validate the new category belongs to this restaurant
        _get_category_or_404(db, restaurant_id, data.category_id)
        product.category_id = data.category_id
    if data.name is not None:
        product.name = data.name
    if data.description is not None:
        # Empty string clears the description (stored as NULL).
        product.description = data.description or None
    if data.base_price is not None:
        product.base_price = data.base_price
    if data.tax_rate is not None:
        product.tax_rate = data.tax_rate
    if data.food_type is not None:
        product.food_type = data.food_type
    if data.is_available is not None:
        product.is_available = data.is_available
    if data.has_variants is not None:
        product.has_variants = data.has_variants
    if data.allows_addons is not None:
        product.allows_addons = data.allows_addons
    if data.is_todays_special is not None:
        product.is_todays_special = data.is_todays_special

    product.updated_at = _now()
    _audit(
        db,
        restaurant_id=restaurant_id,
        actor=actor,
        entity_type="product",
        entity_id=product.id,
        action="PRODUCT_UPDATE",
        previous_value=previous,
        new_value=_product_snapshot(product),
    )
    db.commit()
    db.refresh(product)
    return product


def soft_delete_product(
    db: Session, restaurant_id: uuid.UUID, product_id: uuid.UUID, actor: User
) -> Product:
    product = _get_product_or_404(db, restaurant_id, product_id)
    product.is_active = False
    product.updated_at = _now()
    _audit(
        db,
        restaurant_id=restaurant_id,
        actor=actor,
        entity_type="product",
        entity_id=product.id,
        action="PRODUCT_DELETE",
        previous_value={"is_active": True},
        new_value={"is_active": False},
    )
    db.commit()
    db.refresh(product)
    return product


def set_product_image(
    db: Session, restaurant_id: uuid.UUID, product_id: uuid.UUID, image_url: str, actor: User
) -> Product:
    product = _get_product_or_404(db, restaurant_id, product_id)
    previous_url = product.image_url
    product.image_url = image_url
    product.updated_at = _now()
    _audit(
        db,
        restaurant_id=restaurant_id,
        actor=actor,
        entity_type="product",
        entity_id=product.id,
        action="PRODUCT_IMAGE_SET",
        previous_value={"image_url": previous_url},
        new_value={"image_url": image_url},
    )
    db.commit()
    db.refresh(product)
    return product


# ──────────────────────────────────────────────────────────────────────────────
# Product Variants
# ──────────────────────────────────────────────────────────────────────────────

def create_variant(
    db: Session, restaurant_id: uuid.UUID, product_id: uuid.UUID, data: VariantCreate, actor: User
) -> ProductVariant:
    _get_product_or_404(db, restaurant_id, product_id)

    variant = ProductVariant(
        id=uuid.uuid4(),
        restaurant_id=restaurant_id,
        product_id=product_id,
        name=data.name,
        price=data.price,
        is_active=True,
    )
    db.add(variant)
    db.flush()
    _audit(
        db,
        restaurant_id=restaurant_id,
        actor=actor,
        entity_type="variant",
        entity_id=variant.id,
        action="VARIANT_CREATE",
        new_value={"product_id": str(product_id), "name": variant.name, "price": str(variant.price)},
    )
    db.commit()
    db.refresh(variant)
    return variant


def list_variants(
    db: Session, restaurant_id: uuid.UUID, product_id: uuid.UUID
) -> list[ProductVariant]:
    # Confirm product belongs to restaurant before listing its variants
    _get_product_or_404(db, restaurant_id, product_id)
    return list(
        db.execute(
            select(ProductVariant).where(
                ProductVariant.product_id == product_id,
                ProductVariant.restaurant_id == restaurant_id,
            ).order_by(ProductVariant.created_at)
        ).scalars().all()
    )


def update_variant(
    db: Session,
    restaurant_id: uuid.UUID,
    product_id: uuid.UUID,
    variant_id: uuid.UUID,
    data: VariantUpdate,
    actor: User,
) -> ProductVariant:
    variant = _get_variant_or_404(db, restaurant_id, product_id, variant_id)
    previous = {"name": variant.name, "price": str(variant.price)}
    if data.name is not None:
        variant.name = data.name
    if data.price is not None:
        variant.price = data.price
    variant.updated_at = _now()
    _audit(
        db,
        restaurant_id=restaurant_id,
        actor=actor,
        entity_type="variant",
        entity_id=variant.id,
        action="VARIANT_UPDATE",
        previous_value=previous,
        new_value={"name": variant.name, "price": str(variant.price)},
    )
    db.commit()
    db.refresh(variant)
    return variant


def soft_delete_variant(
    db: Session, restaurant_id: uuid.UUID, product_id: uuid.UUID, variant_id: uuid.UUID, actor: User
) -> ProductVariant:
    variant = _get_variant_or_404(db, restaurant_id, product_id, variant_id)
    variant.is_active = False
    variant.updated_at = _now()
    _audit(
        db,
        restaurant_id=restaurant_id,
        actor=actor,
        entity_type="variant",
        entity_id=variant.id,
        action="VARIANT_DELETE",
        previous_value={"is_active": True},
        new_value={"is_active": False},
    )
    db.commit()
    db.refresh(variant)
    return variant


# ──────────────────────────────────────────────────────────────────────────────
# Product Addons
# ──────────────────────────────────────────────────────────────────────────────

def create_addon(
    db: Session, restaurant_id: uuid.UUID, data: AddonCreate, actor: User
) -> ProductAddon:
    addon = ProductAddon(
        id=uuid.uuid4(),
        restaurant_id=restaurant_id,
        name=data.name,
        price=data.price,
        is_active=True,
    )
    db.add(addon)
    db.flush()
    _audit(
        db,
        restaurant_id=restaurant_id,
        actor=actor,
        entity_type="addon",
        entity_id=addon.id,
        action="ADDON_CREATE",
        new_value={"name": addon.name, "price": str(addon.price)},
    )
    db.commit()
    db.refresh(addon)
    return addon


def list_addons(db: Session, restaurant_id: uuid.UUID) -> list[ProductAddon]:
    return list(
        db.execute(
            select(ProductAddon)
            .where(ProductAddon.restaurant_id == restaurant_id)
            .order_by(ProductAddon.created_at)
        ).scalars().all()
    )


def get_addon(db: Session, restaurant_id: uuid.UUID, addon_id: uuid.UUID) -> ProductAddon:
    return _get_addon_or_404(db, restaurant_id, addon_id)


def update_addon(
    db: Session, restaurant_id: uuid.UUID, addon_id: uuid.UUID, data: AddonUpdate, actor: User
) -> ProductAddon:
    addon = _get_addon_or_404(db, restaurant_id, addon_id)
    previous = {"name": addon.name, "price": str(addon.price)}
    if data.name is not None:
        addon.name = data.name
    if data.price is not None:
        addon.price = data.price
    addon.updated_at = _now()
    _audit(
        db,
        restaurant_id=restaurant_id,
        actor=actor,
        entity_type="addon",
        entity_id=addon.id,
        action="ADDON_UPDATE",
        previous_value=previous,
        new_value={"name": addon.name, "price": str(addon.price)},
    )
    db.commit()
    db.refresh(addon)
    return addon


def soft_delete_addon(
    db: Session, restaurant_id: uuid.UUID, addon_id: uuid.UUID, actor: User
) -> ProductAddon:
    addon = _get_addon_or_404(db, restaurant_id, addon_id)
    addon.is_active = False
    addon.updated_at = _now()
    _audit(
        db,
        restaurant_id=restaurant_id,
        actor=actor,
        entity_type="addon",
        entity_id=addon.id,
        action="ADDON_DELETE",
        previous_value={"is_active": True},
        new_value={"is_active": False},
    )
    db.commit()
    db.refresh(addon)
    return addon


# ──────────────────────────────────────────────────────────────────────────────
# Addon Mappings (product ↔ addon)
# ──────────────────────────────────────────────────────────────────────────────

def create_addon_mapping(
    db: Session,
    restaurant_id: uuid.UUID,
    product_id: uuid.UUID,
    data: AddonMappingCreate,
    actor: User,
) -> ProductAddonMapping:
    # Both product and addon must belong to this restaurant
    _get_product_or_404(db, restaurant_id, product_id)
    _get_addon_or_404(db, restaurant_id, data.addon_id)

    # Reject duplicate mapping
    existing = db.execute(
        select(ProductAddonMapping).where(
            ProductAddonMapping.product_id == product_id,
            ProductAddonMapping.addon_id == data.addon_id,
            ProductAddonMapping.restaurant_id == restaurant_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Addon already mapped to this product")

    mapping = ProductAddonMapping(
        id=uuid.uuid4(),
        restaurant_id=restaurant_id,
        product_id=product_id,
        addon_id=data.addon_id,
    )
    db.add(mapping)
    db.flush()
    _audit(
        db,
        restaurant_id=restaurant_id,
        actor=actor,
        entity_type="addon_mapping",
        entity_id=mapping.id,
        action="ADDON_MAP",
        new_value={"product_id": str(product_id), "addon_id": str(data.addon_id)},
    )
    db.commit()

    # Re-load with addon eagerly so the response schema can serialize it
    mapping = db.execute(
        select(ProductAddonMapping)
        .where(ProductAddonMapping.id == mapping.id)
        .options(selectinload(ProductAddonMapping.addon))
    ).scalar_one()
    return mapping


def list_addon_mappings(
    db: Session, restaurant_id: uuid.UUID, product_id: uuid.UUID
) -> list[ProductAddonMapping]:
    _get_product_or_404(db, restaurant_id, product_id)
    return list(
        db.execute(
            select(ProductAddonMapping)
            .where(
                ProductAddonMapping.product_id == product_id,
                ProductAddonMapping.restaurant_id == restaurant_id,
            )
            .options(selectinload(ProductAddonMapping.addon))
            .order_by(ProductAddonMapping.created_at)
        ).scalars().all()
    )


def delete_addon_mapping(
    db: Session, restaurant_id: uuid.UUID, product_id: uuid.UUID, addon_id: uuid.UUID, actor: User
) -> None:
    # ProductAddonMapping is a configuration junction table (no is_active).
    # Historical order items snapshot addon data at order time (Phase 5), so
    # removing this mapping does not corrupt past orders.
    mapping = db.execute(
        select(ProductAddonMapping).where(
            ProductAddonMapping.product_id == product_id,
            ProductAddonMapping.addon_id == addon_id,
            ProductAddonMapping.restaurant_id == restaurant_id,
        )
    ).scalar_one_or_none()
    if mapping is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mapping not found")
    _audit(
        db,
        restaurant_id=restaurant_id,
        actor=actor,
        entity_type="addon_mapping",
        entity_id=mapping.id,
        action="ADDON_UNMAP",
        previous_value={"product_id": str(product_id), "addon_id": str(addon_id)},
    )
    db.delete(mapping)
    db.commit()


# ──────────────────────────────────────────────────────────────────────────────
# Restaurant Settings
# ──────────────────────────────────────────────────────────────────────────────

def get_or_create_settings(db: Session, restaurant_id: uuid.UUID) -> RestaurantSettings:
    settings = db.execute(
        select(RestaurantSettings).where(RestaurantSettings.restaurant_id == restaurant_id)
    ).scalar_one_or_none()
    if settings is None:
        settings = RestaurantSettings(
            id=uuid.uuid4(),
            restaurant_id=restaurant_id,
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


_SETTINGS_FIELDS = (
    "enable_qr_payment",
    "waiter_can_accept_payment",
    "allow_order_reopen",
    "require_order_approval",
    "currency",
    "timezone",
    "require_location",
    "latitude",
    "longitude",
    "geofence_radius_meters",
    "print_kot_enabled",
    "print_bill_enabled",
    "bill_copies",
    "kot_print_mode",
    "kot_printer_name",
)


def update_settings(
    db: Session, restaurant_id: uuid.UUID, data: SettingsUpdate, actor: User
) -> RestaurantSettings:
    settings = get_or_create_settings(db, restaurant_id)

    # Validate geofence consistency on the *resulting* state: enabling location
    # ordering requires a point to compare against.
    final_require = (
        data.require_location if data.require_location is not None else settings.require_location
    )
    final_lat = data.latitude if data.latitude is not None else settings.latitude
    final_lng = data.longitude if data.longitude is not None else settings.longitude
    if final_require and (final_lat is None or final_lng is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Set the restaurant location before requiring location to order.",
        )

    previous: dict[str, object] = {}
    changed: dict[str, object] = {}
    for field in _SETTINGS_FIELDS:
        new = getattr(data, field)
        if new is None:
            continue
        if field == "kot_printer_name":
            new = new.strip() or None  # "" clears the printer name
        old = getattr(settings, field)
        if new != old:
            previous[field] = old
            changed[field] = new
            setattr(settings, field, new)

    if changed:
        settings.updated_at = _now()
        _audit(
            db,
            restaurant_id=restaurant_id,
            actor=actor,
            entity_type="restaurant_settings",
            entity_id=settings.id,
            action="updated",
            previous_value=previous,
            new_value=changed,
        )
        db.commit()
        db.refresh(settings)
    return settings


def set_banner_image(
    db: Session, restaurant_id: uuid.UUID, banner_image_url: str, actor: User
) -> RestaurantSettings:
    """Point the customer-menu hero at a freshly stored upload. The URL comes
    from image_service.validate_and_store_banner only — never from the client."""
    settings = get_or_create_settings(db, restaurant_id)
    previous_url = settings.banner_image_url
    settings.banner_image_url = banner_image_url
    settings.updated_at = _now()
    _audit(
        db,
        restaurant_id=restaurant_id,
        actor=actor,
        entity_type="restaurant_settings",
        entity_id=settings.id,
        action="BANNER_IMAGE_SET",
        previous_value={"banner_image_url": previous_url},
        new_value={"banner_image_url": banner_image_url},
    )
    db.commit()
    db.refresh(settings)
    return settings


def remove_banner_image(
    db: Session, restaurant_id: uuid.UUID, actor: User
) -> RestaurantSettings:
    """Null out the hero banner (customer page falls back to the stock image)."""
    settings = get_or_create_settings(db, restaurant_id)
    previous_url = settings.banner_image_url
    settings.banner_image_url = None
    settings.updated_at = _now()
    _audit(
        db,
        restaurant_id=restaurant_id,
        actor=actor,
        entity_type="restaurant_settings",
        entity_id=settings.id,
        action="BANNER_IMAGE_REMOVE",
        previous_value={"banner_image_url": previous_url},
        new_value={"banner_image_url": None},
    )
    db.commit()
    db.refresh(settings)
    return settings


# ──────────────────────────────────────────────────────────────────────────────
# Customer-facing menu read
# ──────────────────────────────────────────────────────────────────────────────

def _product_public(p: Product) -> ProductPublic:
    """Customer-facing view of one product, with active variants/addons."""
    variants = [
        VariantPublic(id=v.id, name=v.name, price=v.price)
        for v in p.variants
        if v.is_active
    ]
    addons = [
        AddonPublic(id=m.addon.id, name=m.addon.name, price=m.addon.price)
        for m in p.addon_mappings
        if m.addon.is_active
    ]
    # Only expose AR model URLs for a PUBLISHED model (publish requires READY + GLB).
    ar_published = p.model_published and bool(p.model_glb_url)
    return ProductPublic(
        id=p.id,
        name=p.name,
        description=p.description,
        base_price=p.base_price,
        tax_rate=p.tax_rate,
        food_type=p.food_type,
        image_url=p.image_url,
        has_variants=p.has_variants,
        allows_addons=p.allows_addons,
        variants=variants,
        addons=addons,
        model_glb_url=p.model_glb_url if ar_published else None,
        model_usdz_url=p.model_usdz_url if ar_published else None,
    )


def _public_products(cat: Category) -> list[ProductPublic]:
    """Active + available products of a category, with active variants/addons."""
    return [
        _product_public(p)
        for p in cat.products
        if p.is_active and p.is_available
    ]


def get_todays_specials(db: Session, restaurant_id: uuid.UUID) -> list[ProductPublic]:
    """Featured products for THIS restaurant only: flagged AND active AND
    available. Deactivated/hidden products never appear even if still flagged."""
    rows = db.execute(
        select(Product)
        .where(
            Product.restaurant_id == restaurant_id,
            Product.is_todays_special.is_(True),
            Product.is_active.is_(True),
            Product.is_available.is_(True),
        )
        .options(
            selectinload(Product.variants),
            selectinload(Product.addon_mappings).options(
                selectinload(ProductAddonMapping.addon)
            ),
        )
        .order_by(Product.name)
    ).scalars().all()
    return [_product_public(p) for p in rows]


def get_customer_menu(db: Session, restaurant_id: uuid.UUID) -> list[CategoryPublic]:
    """
    Returns the menu as a nested tree of active + available categories, each carrying
    its own active/available products and its subcategories (children). A category is
    pruned if its entire subtree has zero visible products, so empty branches never show.

    One query loads every active+available category (with eager products/variants/addons);
    the tree is assembled in memory (no per-node queries). A subcategory whose parent is
    hidden/soft-deleted is unreachable from an included parent, so hiding a parent hides
    its whole subtree automatically. Sorted by display_order then name at every level.
    """
    categories = db.execute(
        select(Category)
        .where(
            Category.restaurant_id == restaurant_id,
            Category.is_active.is_(True),
            Category.is_available.is_(True),
        )
        .options(
            selectinload(Category.products).options(
                selectinload(Product.variants),
                selectinload(Product.addon_mappings).options(
                    selectinload(ProductAddonMapping.addon)
                ),
            )
        )
    ).scalars().all()

    # Group children by their parent_id. Only genuine roots (parent_id IS NULL) start
    # the tree; a category whose parent is hidden/soft-deleted is not in `categories`,
    # so its build() never runs and its whole subtree is dropped (hiding a parent hides
    # its children — they are NOT re-rooted to the top level).
    children_of: dict[uuid.UUID, list[Category]] = {}
    roots: list[Category] = []
    for c in categories:
        if c.parent_id is None:
            roots.append(c)
        else:
            children_of.setdefault(c.parent_id, []).append(c)

    def build(cat: Category) -> CategoryPublic | None:
        kids = sorted(
            children_of.get(cat.id, []),
            key=lambda c: (c.display_order, c.name.lower()),
        )
        child_nodes = [n for c in kids if (n := build(c)) is not None]
        products = _public_products(cat)
        # Prune: a category with no products anywhere in its subtree doesn't render.
        if not products and not child_nodes:
            return None
        return CategoryPublic(
            id=cat.id,
            name=cat.name,
            display_order=cat.display_order,
            products=products,
            children=child_nodes,
        )

    roots.sort(key=lambda c: (c.display_order, c.name.lower()))
    return [n for c in roots if (n := build(c)) is not None]


def get_customer_menu_page(db: Session, restaurant_id: uuid.UUID) -> MenuPublic:
    """The whole GET /menu payload: hero banner + today's specials + category tree."""
    settings = get_or_create_settings(db, restaurant_id)
    return MenuPublic(
        banner_image_url=settings.banner_image_url,
        specials=get_todays_specials(db, restaurant_id),
        categories=get_customer_menu(db, restaurant_id),
    )
