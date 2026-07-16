"""
Tenant-scoped service for the optional per-product AR / 3D-model feature.

Every query filters on restaurant_id derived from the verified JWT (never client
input). View images and model URLs are backend-set only. Soft-delete on replace;
no hard DELETE. Privileged writes emit audit_logs rows.

M1 scope: capture (upload the 5 labeled view images) + read model status.
Generation / marking / editor land in later milestones and extend this module.
"""

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ar import GenerationJob, ModelAnnotation, ProductViewImage
from app.models.audit_log import AuditLog
from app.models.enums import (
    AnnotationSource,
    AnnotationStatus,
    ArModelStatus,
    ProductView,
)
from app.models.product import Product
from app.models.user import User
from app.schemas.ar import AnnotationCreate, AnnotationUpdate


def _now() -> datetime:
    return datetime.now(timezone.utc)


# NOT NULL coordinate columns — an update must never null these out (see update_annotation).
_COORD_FIELDS = frozenset(
    {"position_x", "position_y", "position_z", "normal_x", "normal_y", "normal_z"}
)


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
    """Stage an audit_logs row for a privileged AR write (CLAUDE.md §3)."""
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


# ──────────────────────────────────────────────────────────────────────────────
# View images (capture)
# ──────────────────────────────────────────────────────────────────────────────

def list_active_views(
    db: Session, restaurant_id: uuid.UUID, product_id: uuid.UUID
) -> list[ProductViewImage]:
    return list(db.execute(
        select(ProductViewImage)
        .where(
            ProductViewImage.product_id == product_id,
            ProductViewImage.restaurant_id == restaurant_id,
            ProductViewImage.is_active.is_(True),
        )
        .order_by(ProductViewImage.view)
    ).scalars().all())


def upsert_view_image(
    db: Session,
    restaurant_id: uuid.UUID,
    product_id: uuid.UUID,
    view: ProductView,
    image_url: str,
    actor: User,
) -> ProductViewImage:
    """
    Store a labeled source photo for one view slot. If an active image already
    exists for that (product, view), it is soft-replaced (is_active=False) so the
    partial-unique index never collides and history is preserved.
    """
    product = _get_product_or_404(db, restaurant_id, product_id)

    existing = db.execute(
        select(ProductViewImage).where(
            ProductViewImage.product_id == product.id,
            ProductViewImage.restaurant_id == restaurant_id,
            ProductViewImage.view == view,
            ProductViewImage.is_active.is_(True),
        )
    ).scalar_one_or_none()

    previous_url = None
    if existing is not None:
        previous_url = existing.image_url
        existing.is_active = False
        existing.updated_at = _now()
        db.flush()  # deactivate before insert so the active partial-unique index is free

    image = ProductViewImage(
        id=uuid.uuid4(),
        restaurant_id=restaurant_id,
        product_id=product.id,
        view=view,
        image_url=image_url,
        is_active=True,
    )
    db.add(image)

    _audit(
        db,
        restaurant_id=restaurant_id,
        actor=actor,
        entity_type="product_view_image",
        entity_id=product.id,
        action="PRODUCT_VIEW_UPLOAD",
        previous_value={"view": view.value, "image_url": previous_url},
        new_value={"view": view.value, "image_url": image_url},
    )

    db.commit()
    db.refresh(image)
    return image


# ──────────────────────────────────────────────────────────────────────────────
# Model status (read)
# ──────────────────────────────────────────────────────────────────────────────

def get_model_status_parts(
    db: Session, restaurant_id: uuid.UUID, product_id: uuid.UUID
) -> tuple[Product, list[ProductViewImage], list[GenerationJob], list[ModelAnnotation]]:
    """Fetch the product plus its active views, jobs, and annotations (tenant-scoped)."""
    product = _get_product_or_404(db, restaurant_id, product_id)

    views = list_active_views(db, restaurant_id, product_id)

    jobs = list(db.execute(
        select(GenerationJob)
        .where(
            GenerationJob.product_id == product_id,
            GenerationJob.restaurant_id == restaurant_id,
            GenerationJob.is_active.is_(True),
        )
        .order_by(GenerationJob.created_at)
    ).scalars().all())

    annotations = list(db.execute(
        select(ModelAnnotation)
        .where(
            ModelAnnotation.product_id == product_id,
            ModelAnnotation.restaurant_id == restaurant_id,
            ModelAnnotation.is_active.is_(True),
        )
        .order_by(ModelAnnotation.created_at)
    ).scalars().all())

    return product, views, jobs, annotations


# ──────────────────────────────────────────────────────────────────────────────
# Annotation editor (M4)
# ──────────────────────────────────────────────────────────────────────────────

def _get_annotation_or_404(
    db: Session, restaurant_id: uuid.UUID, product_id: uuid.UUID, annotation_id: uuid.UUID
) -> ModelAnnotation:
    row = db.execute(
        select(ModelAnnotation).where(
            ModelAnnotation.id == annotation_id,
            ModelAnnotation.product_id == product_id,
            ModelAnnotation.restaurant_id == restaurant_id,
            ModelAnnotation.is_active.is_(True),
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Annotation not found")
    return row


def _annotation_snapshot(a: ModelAnnotation) -> dict:
    """JSON-serialisable view of an annotation for audit previous/new values."""
    def num(v):  # Decimal → str so the audit JSON is exact and serialisable
        return None if v is None else str(v)
    return {
        "label": a.label,
        "calories": num(a.calories),
        "protein_g": num(a.protein_g),
        "carbs_g": num(a.carbs_g),
        "fat_g": num(a.fat_g),
        "allergens": list(a.allergens or []),
        "position": [a.position_x, a.position_y, a.position_z],
        "status": a.status.value,
    }


def create_annotation(
    db: Session, restaurant_id: uuid.UUID, product_id: uuid.UUID,
    data: AnnotationCreate, actor: User,
) -> ModelAnnotation:
    """A manually added tag is human-authored → source=MANUAL, status=ADMIN_VERIFIED."""
    _get_product_or_404(db, restaurant_id, product_id)
    ann = ModelAnnotation(
        id=uuid.uuid4(), restaurant_id=restaurant_id, product_id=product_id,
        label=data.label,
        position_x=data.position_x, position_y=data.position_y, position_z=data.position_z,
        normal_x=data.normal_x, normal_y=data.normal_y, normal_z=data.normal_z,
        calories=data.calories, protein_g=data.protein_g, carbs_g=data.carbs_g, fat_g=data.fat_g,
        allergens=list(data.allergens),
        source=AnnotationSource.MANUAL, status=AnnotationStatus.ADMIN_VERIFIED,
    )
    db.add(ann)
    _audit(
        db, restaurant_id=restaurant_id, actor=actor,
        entity_type="model_annotation", entity_id=ann.id, action="ANNOTATION_CREATE",
        previous_value=None, new_value=_annotation_snapshot(ann),
    )
    db.commit()
    db.refresh(ann)
    return ann


def update_annotation(
    db: Session, restaurant_id: uuid.UUID, product_id: uuid.UUID, annotation_id: uuid.UUID,
    data: AnnotationUpdate, actor: User,
) -> ModelAnnotation:
    """
    Apply the provided fields and flip the tag to ADMIN_VERIFIED — a human has
    reviewed it (drives the green trust colour on the frontend).
    """
    ann = _get_annotation_or_404(db, restaurant_id, product_id, annotation_id)
    previous = _annotation_snapshot(ann)

    fields = data.model_dump(exclude_unset=True)
    for key, value in fields.items():
        # Coordinate columns are NOT NULL — never write a null into them (a bad client
        # sending null would otherwise raise an IntegrityError → 500). Nutrient fields
        # stay nullable so they can be explicitly cleared.
        if key in _COORD_FIELDS and value is None:
            continue
        if key == "allergens" and value is not None:
            value = list(value)
        setattr(ann, key, value)
    ann.status = AnnotationStatus.ADMIN_VERIFIED
    ann.updated_at = _now()

    _audit(
        db, restaurant_id=restaurant_id, actor=actor,
        entity_type="model_annotation", entity_id=ann.id, action="ANNOTATION_UPDATE",
        previous_value=previous, new_value=_annotation_snapshot(ann),
    )
    db.commit()
    db.refresh(ann)
    return ann


def delete_annotation(
    db: Session, restaurant_id: uuid.UUID, product_id: uuid.UUID, annotation_id: uuid.UUID,
    actor: User,
) -> ModelAnnotation:
    """Soft-delete (is_active=False); business/audit history is preserved."""
    ann = _get_annotation_or_404(db, restaurant_id, product_id, annotation_id)
    previous = _annotation_snapshot(ann)
    ann.is_active = False
    ann.updated_at = _now()
    _audit(
        db, restaurant_id=restaurant_id, actor=actor,
        entity_type="model_annotation", entity_id=ann.id, action="ANNOTATION_DELETE",
        previous_value=previous, new_value={"is_active": False},
    )
    db.commit()
    db.refresh(ann)
    return ann


def set_published(
    db: Session, restaurant_id: uuid.UUID, product_id: uuid.UUID, published: bool, actor: User,
) -> Product:
    """
    Publish gate: only a READY model with a GLB may be published to customers.
    Unpublishing is always allowed.
    """
    product = _get_product_or_404(db, restaurant_id, product_id)

    if published:
        if product.model_status != ArModelStatus.READY or not product.model_glb_url:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Model must be READY with a generated GLB before publishing",
            )

    previous = product.model_published
    product.model_published = published
    product.updated_at = _now()
    _audit(
        db, restaurant_id=restaurant_id, actor=actor,
        entity_type="product_model", entity_id=product.id,
        action="MODEL_PUBLISH" if published else "MODEL_UNPUBLISH",
        previous_value={"model_published": previous},
        new_value={"model_published": published},
    )
    db.commit()
    db.refresh(product)
    return product
