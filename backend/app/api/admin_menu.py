"""
ADMIN-only endpoints for the menu domain and media file serving.

Two routers are exported:
  router       → prefix /admin, requires ADMIN JWT on every endpoint
  media_router → prefix /media, public (no auth) for serving uploaded images
"""

import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_role, tenant_scope
from app.models.enums import Role
from app.models.user import User
from app.schemas.menu import (
    AddonCreate,
    AddonMappingCreate,
    AddonMappingResponse,
    AddonResponse,
    AddonUpdate,
    CategoryCreate,
    CategoryResponse,
    CategoryUpdate,
    ProductCreate,
    ProductResponse,
    ProductUpdate,
    VariantCreate,
    VariantResponse,
    VariantUpdate,
)
from app.services import image_service, menu_service

router = APIRouter(prefix="/admin", tags=["admin-menu"])
media_router = APIRouter(tags=["media"])

# Shared dependency aliases for brevity
_AdminDep = Annotated[User, Depends(require_role(Role.ADMIN))]
_RidDep = Annotated[uuid.UUID, Depends(tenant_scope)]
_DbDep = Annotated[Session, Depends(get_db)]


# ──────────────────────────────────────────────────────────────────────────────
# Categories
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/categories", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
def create_category(
    data: CategoryCreate,
    restaurant_id: _RidDep,
    _user: _AdminDep,
    db: _DbDep,
) -> CategoryResponse:
    cat = menu_service.create_category(db, restaurant_id, data, _user)
    return CategoryResponse.model_validate(cat)


@router.get("/categories", response_model=list[CategoryResponse])
def list_categories(
    restaurant_id: _RidDep,
    _user: _AdminDep,
    db: _DbDep,
) -> list[CategoryResponse]:
    cats = menu_service.list_categories(db, restaurant_id)
    return [CategoryResponse.model_validate(c) for c in cats]


@router.get("/categories/{category_id}", response_model=CategoryResponse)
def get_category(
    category_id: uuid.UUID,
    restaurant_id: _RidDep,
    _user: _AdminDep,
    db: _DbDep,
) -> CategoryResponse:
    cat = menu_service.get_category(db, restaurant_id, category_id)
    return CategoryResponse.model_validate(cat)


@router.put("/categories/{category_id}", response_model=CategoryResponse)
def update_category(
    category_id: uuid.UUID,
    data: CategoryUpdate,
    restaurant_id: _RidDep,
    _user: _AdminDep,
    db: _DbDep,
) -> CategoryResponse:
    cat = menu_service.update_category(db, restaurant_id, category_id, data, _user)
    return CategoryResponse.model_validate(cat)


@router.delete("/categories/{category_id}", response_model=CategoryResponse)
def delete_category(
    category_id: uuid.UUID,
    restaurant_id: _RidDep,
    _user: _AdminDep,
    db: _DbDep,
) -> CategoryResponse:
    cat = menu_service.soft_delete_category(db, restaurant_id, category_id, _user)
    return CategoryResponse.model_validate(cat)


# ──────────────────────────────────────────────────────────────────────────────
# Products
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/products", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def create_product(
    data: ProductCreate,
    restaurant_id: _RidDep,
    _user: _AdminDep,
    db: _DbDep,
) -> ProductResponse:
    product = menu_service.create_product(db, restaurant_id, data, _user)
    return ProductResponse.model_validate(product)


@router.get("/products", response_model=list[ProductResponse])
def list_products(
    restaurant_id: _RidDep,
    _user: _AdminDep,
    db: _DbDep,
    category_id: uuid.UUID | None = None,
) -> list[ProductResponse]:
    products = menu_service.list_products(db, restaurant_id, category_id)
    return [ProductResponse.model_validate(p) for p in products]


@router.get("/products/{product_id}", response_model=ProductResponse)
def get_product(
    product_id: uuid.UUID,
    restaurant_id: _RidDep,
    _user: _AdminDep,
    db: _DbDep,
) -> ProductResponse:
    product = menu_service.get_product(db, restaurant_id, product_id)
    return ProductResponse.model_validate(product)


@router.put("/products/{product_id}", response_model=ProductResponse)
def update_product(
    product_id: uuid.UUID,
    data: ProductUpdate,
    restaurant_id: _RidDep,
    _user: _AdminDep,
    db: _DbDep,
) -> ProductResponse:
    product = menu_service.update_product(db, restaurant_id, product_id, data, _user)
    return ProductResponse.model_validate(product)


@router.delete("/products/{product_id}", response_model=ProductResponse)
def delete_product(
    product_id: uuid.UUID,
    restaurant_id: _RidDep,
    _user: _AdminDep,
    db: _DbDep,
) -> ProductResponse:
    product = menu_service.soft_delete_product(db, restaurant_id, product_id, _user)
    return ProductResponse.model_validate(product)


@router.post("/products/{product_id}/image", response_model=ProductResponse)
def upload_product_image(
    product_id: uuid.UUID,
    file: UploadFile,
    restaurant_id: _RidDep,
    _user: _AdminDep,
    db: _DbDep,
) -> ProductResponse:
    """
    Accepts a multipart file upload of any resolution/aspect ratio (up to 25 MB),
    validated by magic bytes. The image is auto-oriented, center-cropped to 1:1,
    downscaled to a uniform square, compressed to JPEG, and stripped of metadata,
    then stored under a UUID filename. The client cannot set image_url directly —
    only this endpoint may update it.
    """
    raw = file.file.read()
    try:
        image_url = image_service.validate_and_store(raw, restaurant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    product = menu_service.set_product_image(db, restaurant_id, product_id, image_url, _user)
    return ProductResponse.model_validate(product)


# ──────────────────────────────────────────────────────────────────────────────
# Product Variants
# ──────────────────────────────────────────────────────────────────────────────

@router.post(
    "/products/{product_id}/variants",
    response_model=VariantResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_variant(
    product_id: uuid.UUID,
    data: VariantCreate,
    restaurant_id: _RidDep,
    _user: _AdminDep,
    db: _DbDep,
) -> VariantResponse:
    variant = menu_service.create_variant(db, restaurant_id, product_id, data, _user)
    return VariantResponse.model_validate(variant)


@router.get("/products/{product_id}/variants", response_model=list[VariantResponse])
def list_variants(
    product_id: uuid.UUID,
    restaurant_id: _RidDep,
    _user: _AdminDep,
    db: _DbDep,
) -> list[VariantResponse]:
    variants = menu_service.list_variants(db, restaurant_id, product_id)
    return [VariantResponse.model_validate(v) for v in variants]


@router.put(
    "/products/{product_id}/variants/{variant_id}",
    response_model=VariantResponse,
)
def update_variant(
    product_id: uuid.UUID,
    variant_id: uuid.UUID,
    data: VariantUpdate,
    restaurant_id: _RidDep,
    _user: _AdminDep,
    db: _DbDep,
) -> VariantResponse:
    variant = menu_service.update_variant(db, restaurant_id, product_id, variant_id, data, _user)
    return VariantResponse.model_validate(variant)


@router.delete(
    "/products/{product_id}/variants/{variant_id}",
    response_model=VariantResponse,
)
def delete_variant(
    product_id: uuid.UUID,
    variant_id: uuid.UUID,
    restaurant_id: _RidDep,
    _user: _AdminDep,
    db: _DbDep,
) -> VariantResponse:
    variant = menu_service.soft_delete_variant(db, restaurant_id, product_id, variant_id, _user)
    return VariantResponse.model_validate(variant)


# ──────────────────────────────────────────────────────────────────────────────
# Addons
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/addons", response_model=AddonResponse, status_code=status.HTTP_201_CREATED)
def create_addon(
    data: AddonCreate,
    restaurant_id: _RidDep,
    _user: _AdminDep,
    db: _DbDep,
) -> AddonResponse:
    addon = menu_service.create_addon(db, restaurant_id, data, _user)
    return AddonResponse.model_validate(addon)


@router.get("/addons", response_model=list[AddonResponse])
def list_addons(
    restaurant_id: _RidDep,
    _user: _AdminDep,
    db: _DbDep,
) -> list[AddonResponse]:
    addons = menu_service.list_addons(db, restaurant_id)
    return [AddonResponse.model_validate(a) for a in addons]


@router.put("/addons/{addon_id}", response_model=AddonResponse)
def update_addon(
    addon_id: uuid.UUID,
    data: AddonUpdate,
    restaurant_id: _RidDep,
    _user: _AdminDep,
    db: _DbDep,
) -> AddonResponse:
    addon = menu_service.update_addon(db, restaurant_id, addon_id, data, _user)
    return AddonResponse.model_validate(addon)


@router.delete("/addons/{addon_id}", response_model=AddonResponse)
def delete_addon(
    addon_id: uuid.UUID,
    restaurant_id: _RidDep,
    _user: _AdminDep,
    db: _DbDep,
) -> AddonResponse:
    addon = menu_service.soft_delete_addon(db, restaurant_id, addon_id, _user)
    return AddonResponse.model_validate(addon)


# ──────────────────────────────────────────────────────────────────────────────
# Addon Mappings  (product ↔ addon links)
# ──────────────────────────────────────────────────────────────────────────────

@router.post(
    "/products/{product_id}/addons",
    response_model=AddonMappingResponse,
    status_code=status.HTTP_201_CREATED,
)
def map_addon_to_product(
    product_id: uuid.UUID,
    data: AddonMappingCreate,
    restaurant_id: _RidDep,
    _user: _AdminDep,
    db: _DbDep,
) -> AddonMappingResponse:
    mapping = menu_service.create_addon_mapping(db, restaurant_id, product_id, data, _user)
    return AddonMappingResponse.model_validate(mapping)


@router.get("/products/{product_id}/addons", response_model=list[AddonMappingResponse])
def list_product_addons(
    product_id: uuid.UUID,
    restaurant_id: _RidDep,
    _user: _AdminDep,
    db: _DbDep,
) -> list[AddonMappingResponse]:
    mappings = menu_service.list_addon_mappings(db, restaurant_id, product_id)
    return [AddonMappingResponse.model_validate(m) for m in mappings]


@router.delete(
    "/products/{product_id}/addons/{addon_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def unmap_addon_from_product(
    product_id: uuid.UUID,
    addon_id: uuid.UUID,
    restaurant_id: _RidDep,
    _user: _AdminDep,
    db: _DbDep,
) -> None:
    menu_service.delete_addon_mapping(db, restaurant_id, product_id, addon_id, _user)


# ──────────────────────────────────────────────────────────────────────────────
# Media file serving  (public — no auth; UUID filenames prevent enumeration)
# ──────────────────────────────────────────────────────────────────────────────

_MEDIA_ROOT = Path("/app/media")


@media_router.get("/media/{restaurant_id}/{filename}")
def serve_media(restaurant_id: str, filename: str) -> Response:
    """
    Serves uploaded product images by their server-generated UUID path.

    Security controls:
    - restaurant_id must be a valid UUID (rejects path traversal like "../")
    - filename must contain no path separators or ".." sequences
    - Files are served from the controlled /app/media directory only
    - No directory listing (exact path required)
    """
    try:
        uuid.UUID(restaurant_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    path = _MEDIA_ROOT / restaurant_id / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    suffix = path.suffix.lower()
    content_type_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".glb": "model/gltf-binary",
        ".usdz": "model/vnd.usdz+zip",
    }
    content_type = content_type_map.get(suffix, "application/octet-stream")

    # Filenames are server-generated UUIDs and never change content → cache hard.
    return Response(
        content=path.read_bytes(),
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
