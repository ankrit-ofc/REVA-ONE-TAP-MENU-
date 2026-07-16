"""
ADMIN-only endpoints for the optional per-product AR / 3D-model feature.

Every endpoint is tenant-scoped (restaurant_id from the JWT via tenant_scope) and
role-gated to ADMIN. Uploaded images are validated + stored by image_service; the
client can never set image_url / model URLs directly.

M1 scope: upload the 5 labeled view images + read model status. Generation, marking,
and the annotation editor extend this router in later milestones.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_role, tenant_scope
from app.models.enums import ProductView, Role
from app.models.user import User
from app.schemas.ar import (
    AnnotationCreate,
    AnnotationResponse,
    AnnotationUpdate,
    GenerateRequest,
    GenerationJobResponse,
    ModelStatusResponse,
    ProductViewImageResponse,
    PublishRequest,
)
from app.services import ar_pipeline, ar_service, image_service

router = APIRouter(prefix="/admin", tags=["admin-ar"])

_AdminDep = Annotated[User, Depends(require_role(Role.ADMIN))]
_RidDep = Annotated[uuid.UUID, Depends(tenant_scope)]
_DbDep = Annotated[Session, Depends(get_db)]


def _build_status(
    db: Session, restaurant_id: uuid.UUID, product_id: uuid.UUID
) -> ModelStatusResponse:
    product, views, jobs, annotations = ar_service.get_model_status_parts(
        db, restaurant_id, product_id
    )
    return ModelStatusResponse(
        product_id=product.id,
        model_status=product.model_status,
        model_glb_url=product.model_glb_url,
        model_usdz_url=product.model_usdz_url,
        model_published=product.model_published,
        views=[ProductViewImageResponse.model_validate(v) for v in views],
        jobs=[GenerationJobResponse.model_validate(j) for j in jobs],
        annotations=[AnnotationResponse.model_validate(a) for a in annotations],
    )


@router.post(
    "/products/{product_id}/model/views/{view}",
    response_model=ProductViewImageResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_model_view(
    product_id: uuid.UUID,
    view: ProductView,
    file: UploadFile,
    restaurant_id: _RidDep,
    _user: _AdminDep,
    db: _DbDep,
) -> ProductViewImageResponse:
    """
    Upload one labeled source photo (FRONT/BACK/LEFT/RIGHT/TOP) for the product's
    3D model. The file is validated by magic bytes, normalised, stripped of metadata,
    and stored under a server-generated UUID filename. Re-uploading a view slot
    soft-replaces the previous image.
    """
    raw = file.file.read()
    try:
        image_url = image_service.validate_and_store(raw, restaurant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    image = ar_service.upsert_view_image(
        db, restaurant_id, product_id, view, image_url, _user
    )
    return ProductViewImageResponse.model_validate(image)


@router.post(
    "/products/{product_id}/model/generate",
    response_model=ModelStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def generate_model(
    product_id: uuid.UUID,
    restaurant_id: _RidDep,
    _user: _AdminDep,
    db: _DbDep,
    background: BackgroundTasks,
    data: GenerateRequest = GenerateRequest(),
) -> ModelStatusResponse:
    """
    Queue 3D generation + nutrition marking for the product (needs all 5 views).
    `data.model` picks the fal 3D model (defaults to AR_DEFAULT_THREED_MODEL).
    Returns 202 immediately with model_status=GENERATING; the jobs run off the
    request path and the product flips to READY when done. Non-blocking: the admin
    can keep working. Re-calling while a run is in flight does not double-run.
    """
    model_key = data.model.value if data.model else None
    ar_pipeline.enqueue_generation(db, restaurant_id, product_id, _user, model_key)
    background.add_task(ar_pipeline.run_pipeline, restaurant_id, product_id)
    return _build_status(db, restaurant_id, product_id)


@router.get(
    "/products/{product_id}/model",
    response_model=ModelStatusResponse,
)
def get_model_status(
    product_id: uuid.UUID,
    restaurant_id: _RidDep,
    _user: _AdminDep,
    db: _DbDep,
) -> ModelStatusResponse:
    """Current model status for the product: state, URLs, captured views, jobs, tags."""
    return _build_status(db, restaurant_id, product_id)


# ──────────────────────────────────────────────────────────────────────────────
# Annotation editor (M4)
# ──────────────────────────────────────────────────────────────────────────────

@router.post(
    "/products/{product_id}/annotations",
    response_model=AnnotationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_annotation(
    product_id: uuid.UUID,
    data: AnnotationCreate,
    restaurant_id: _RidDep,
    _user: _AdminDep,
    db: _DbDep,
) -> AnnotationResponse:
    """Add a manual nutrition tag (human-authored → verified)."""
    ann = ar_service.create_annotation(db, restaurant_id, product_id, data, _user)
    return AnnotationResponse.model_validate(ann)


@router.put(
    "/products/{product_id}/annotations/{annotation_id}",
    response_model=AnnotationResponse,
)
def update_annotation(
    product_id: uuid.UUID,
    annotation_id: uuid.UUID,
    data: AnnotationUpdate,
    restaurant_id: _RidDep,
    _user: _AdminDep,
    db: _DbDep,
) -> AnnotationResponse:
    """Edit values / reposition a tag — flips it to admin_verified (green)."""
    ann = ar_service.update_annotation(db, restaurant_id, product_id, annotation_id, data, _user)
    return AnnotationResponse.model_validate(ann)


@router.delete(
    "/products/{product_id}/annotations/{annotation_id}",
    response_model=AnnotationResponse,
)
def delete_annotation(
    product_id: uuid.UUID,
    annotation_id: uuid.UUID,
    restaurant_id: _RidDep,
    _user: _AdminDep,
    db: _DbDep,
) -> AnnotationResponse:
    """Soft-delete a tag."""
    ann = ar_service.delete_annotation(db, restaurant_id, product_id, annotation_id, _user)
    return AnnotationResponse.model_validate(ann)


@router.post(
    "/products/{product_id}/model/publish",
    response_model=ModelStatusResponse,
)
def publish_model(
    product_id: uuid.UUID,
    data: PublishRequest,
    restaurant_id: _RidDep,
    _user: _AdminDep,
    db: _DbDep,
) -> ModelStatusResponse:
    """Publish (or unpublish) a ready model to customers. Publishing requires READY + GLB."""
    ar_service.set_published(db, restaurant_id, product_id, data.published, _user)
    return _build_status(db, restaurant_id, product_id)
