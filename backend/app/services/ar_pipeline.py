"""
AR generation + marking pipeline (non-blocking, provider-abstracted).

enqueue_generation() validates that the 5 labeled views exist, creates the
generation + marking jobs, flips the product to GENERATING, and returns immediately.
run_pipeline() is executed off the request path (FastAPI BackgroundTasks): it runs
the two jobs, then a converge step that auto-places the nutrition hotspots and flips
the product to READY. Generation is serialized single-concurrency via a Postgres
advisory lock ("one model at a time"); marking runs alongside.

Providers are dummy stubs this milestone (no external calls / no new deps).
"""

import logging
import math
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.ar import GenerationJob, ModelAnnotation, ProductViewImage
from app.models.enums import (
    AnnotationSource,
    AnnotationStatus,
    ArModelStatus,
    GenerationJobKind,
    GenerationJobStatus,
    ProductView,
)
from app.models.product import Product
from app.models.user import User
from app.services import ar_providers, ar_service, image_service, model_processing

_log = logging.getLogger("app.ar")

# Front/back/left/right feed 3D generation; the top-down photo feeds nutrition marking.
_GENERATION_VIEWS = {ProductView.FRONT, ProductView.BACK, ProductView.LEFT, ProductView.RIGHT}
_MARKING_VIEW = ProductView.TOP
_REQUIRED_VIEWS = _GENERATION_VIEWS | {_MARKING_VIEW}

# One 3D generation at a time, globally (the "pipeline one after another" contract).
_GENERATION_LOCK_KEY = 0x4152_3344  # "AR3D"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _set_rls(db: Session, restaurant_id: uuid.UUID) -> None:
    """Set the tenant GUC for the off-request session (RLS net + future non-owner roles)."""
    db.execute(
        text("SELECT set_config('app.current_restaurant_id', :rid, TRUE)"),
        {"rid": str(restaurant_id)},
    )


# ──────────────────────────────────────────────────────────────────────────────
# Enqueue (on the request path)
# ──────────────────────────────────────────────────────────────────────────────

def enqueue_generation(
    db: Session, restaurant_id: uuid.UUID, product_id: uuid.UUID, actor: User,
    model_key: str | None = None,
) -> Product:
    """
    Validate the captured views and queue generation + marking. `model_key` selects the
    fal 3D model (defaults to AR_DEFAULT_THREED_MODEL); it's persisted on the GENERATION
    job's `provider` and read back by the pipeline. Idempotent while a run is in flight.
    """
    product = ar_service._get_product_or_404(db, restaurant_id, product_id)

    resolved_model = model_key or settings.AR_DEFAULT_THREED_MODEL
    if resolved_model not in ar_providers.FAL_THREED_MODELS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown 3D model: {resolved_model!r}",
        )

    present = {v.view for v in ar_service.list_active_views(db, restaurant_id, product_id)}
    missing = sorted(v.value for v in (_REQUIRED_VIEWS - present))
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Missing required view images: {', '.join(missing)}",
        )

    in_flight = db.execute(
        select(GenerationJob).where(
            GenerationJob.product_id == product_id,
            GenerationJob.restaurant_id == restaurant_id,
            GenerationJob.is_active.is_(True),
            GenerationJob.status.in_([GenerationJobStatus.QUEUED, GenerationJobStatus.RUNNING]),
        )
    ).scalars().first()
    if in_flight is not None:
        return product  # a run is already in progress — no double-run

    previous_status = product.model_status.value
    marking = ar_providers.get_marking_provider()

    # The GENERATION job's provider carries the chosen model key (the pipeline reads it).
    db.add(GenerationJob(
        id=uuid.uuid4(), restaurant_id=restaurant_id, product_id=product_id,
        kind=GenerationJobKind.GENERATION, provider=resolved_model,
        status=GenerationJobStatus.QUEUED,
    ))
    db.add(GenerationJob(
        id=uuid.uuid4(), restaurant_id=restaurant_id, product_id=product_id,
        kind=GenerationJobKind.MARKING, provider=marking.name,
        status=GenerationJobStatus.QUEUED,
    ))

    product.model_status = ArModelStatus.GENERATING
    product.updated_at = _now()

    ar_service._audit(
        db, restaurant_id=restaurant_id, actor=actor,
        entity_type="product_model", entity_id=product_id, action="MODEL_GENERATE_ENQUEUE",
        previous_value={"model_status": previous_status},
        new_value={"model_status": ArModelStatus.GENERATING.value, "model": resolved_model},
    )

    db.commit()
    db.refresh(product)
    return product


# ──────────────────────────────────────────────────────────────────────────────
# Run (off the request path — FastAPI BackgroundTasks)
# ──────────────────────────────────────────────────────────────────────────────

def run_pipeline(restaurant_id: uuid.UUID, product_id: uuid.UUID) -> None:
    """Process the queued jobs for one product, then converge to READY."""
    db = SessionLocal()
    try:
        _set_rls(db, restaurant_id)
        _run_generation(db, restaurant_id, product_id)
        _run_marking(db, restaurant_id, product_id)
        _converge(db, restaurant_id, product_id)
    except Exception:  # noqa: BLE001 — last-resort guard so a bug can't wedge the product
        _log.exception("AR pipeline crashed for product %s", product_id)
        _fail_product(db, restaurant_id, product_id, "pipeline error")
    finally:
        db.close()


def _active_job(
    db: Session, restaurant_id: uuid.UUID, product_id: uuid.UUID, kind: GenerationJobKind
) -> GenerationJob | None:
    return db.execute(
        select(GenerationJob).where(
            GenerationJob.product_id == product_id,
            GenerationJob.restaurant_id == restaurant_id,
            GenerationJob.kind == kind,
            GenerationJob.is_active.is_(True),
            GenerationJob.status.in_([GenerationJobStatus.QUEUED, GenerationJobStatus.RUNNING]),
        ).order_by(GenerationJob.created_at)
    ).scalars().first()


def _run_generation(db: Session, restaurant_id: uuid.UUID, product_id: uuid.UUID) -> None:
    job = _active_job(db, restaurant_id, product_id, GenerationJobKind.GENERATION)
    if job is None:
        return
    try:
        # Serialize generation across the whole app: one model at a time. The lock
        # is held for this transaction only and released on commit.
        db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _GENERATION_LOCK_KEY})
        job.status = GenerationJobStatus.RUNNING
        job.updated_at = _now()
        db.flush()

        views = {
            v.view: v.image_url
            for v in ar_service.list_active_views(db, restaurant_id, product_id)
            if v.view in _GENERATION_VIEWS
        }
        # The GENERATION job's provider carries the admin-selected model key.
        model = ar_providers.get_threed_provider().generate(views, job.provider)

        # Pull the model into our own /media storage and compress it (the raw fal GLB
        # is ~30 MB). Provider-agnostic post-step; download failure fails the job.
        # web_glb = compressed (viewer); source_glb = uncompressed (USDZ input).
        web_glb, source_glb = model_processing.localize_and_compress(model.glb_url, restaurant_id)

        # USDZ is best-effort — a converter failure must not fail the whole job; the
        # compressed GLB still lands and the product still reaches READY. Convert from
        # the decimated, uncompressed-geometry source (a small mesh Blender can import).
        usdz_url: str | None = None
        try:
            usdz_url = ar_providers.get_usdz_converter().to_usdz(source_glb)
        except Exception:  # noqa: BLE001
            _log.warning("USDZ conversion failed for product %s; leaving usdz null",
                         product_id, exc_info=True)

        # The uncompressed source is only needed for USDZ; drop it once we have a
        # separate compressed web GLB (keep it if it *is* the web GLB).
        if source_glb != web_glb:
            image_service.delete_image(source_glb)

        product = ar_service._get_product_or_404(db, restaurant_id, product_id)
        product.model_glb_url = web_glb
        product.model_usdz_url = usdz_url
        product.updated_at = _now()

        job.status = GenerationJobStatus.DONE
        job.updated_at = _now()
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        _fail_job(db, job.id, str(exc))
        raise


def _run_marking(db: Session, restaurant_id: uuid.UUID, product_id: uuid.UUID) -> None:
    job = _active_job(db, restaurant_id, product_id, GenerationJobKind.MARKING)
    if job is None:
        return
    try:
        job.status = GenerationJobStatus.RUNNING
        job.updated_at = _now()
        db.flush()

        top = db.execute(
            select(ProductViewImage).where(
                ProductViewImage.product_id == product_id,
                ProductViewImage.restaurant_id == restaurant_id,
                ProductViewImage.view == _MARKING_VIEW,
                ProductViewImage.is_active.is_(True),
            )
        ).scalars().first()
        top_url = top.image_url if top else ""

        # Replace, don't stack: soft-clear prior AI drafts so re-running marking
        # (e.g. "Regenerate") doesn't accumulate duplicates. Human-verified and
        # manually added tags are preserved.
        stale = db.execute(
            select(ModelAnnotation).where(
                ModelAnnotation.product_id == product_id,
                ModelAnnotation.restaurant_id == restaurant_id,
                ModelAnnotation.is_active.is_(True),
                ModelAnnotation.source == AnnotationSource.AI,
                ModelAnnotation.status == AnnotationStatus.AI_ESTIMATED,
            )
        ).scalars().all()
        for old in stale:
            old.is_active = False
            old.updated_at = _now()

        drafts = ar_providers.get_marking_provider().mark(top_url)
        for d in drafts:
            db.add(ModelAnnotation(
                id=uuid.uuid4(), restaurant_id=restaurant_id, product_id=product_id,
                label=d.label,
                calories=d.calories, protein_g=d.protein_g, carbs_g=d.carbs_g, fat_g=d.fat_g,
                allergens=d.allergens,
                source=AnnotationSource.AI, status=AnnotationStatus.AI_ESTIMATED,
            ))

        job.status = GenerationJobStatus.DONE
        job.updated_at = _now()
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        _fail_job(db, job.id, str(exc))
        raise


def _converge(db: Session, restaurant_id: uuid.UUID, product_id: uuid.UUID) -> None:
    """When generation + marking are both DONE, auto-place hotspots and flip to READY."""
    kinds_done = set(db.execute(
        select(GenerationJob.kind).where(
            GenerationJob.product_id == product_id,
            GenerationJob.restaurant_id == restaurant_id,
            GenerationJob.is_active.is_(True),
            GenerationJob.status == GenerationJobStatus.DONE,
        )
    ).scalars().all())
    if not {GenerationJobKind.GENERATION, GenerationJobKind.MARKING} <= kinds_done:
        return

    product = ar_service._get_product_or_404(db, restaurant_id, product_id)
    if not product.model_glb_url:
        return

    _auto_project(db, restaurant_id, product_id)

    product.model_status = ArModelStatus.READY
    product.updated_at = _now()
    db.commit()


def _auto_project(db: Session, restaurant_id: uuid.UUID, product_id: uuid.UUID) -> None:
    """
    Stub auto-projection: spread the hotspots evenly on the top surface so the admin
    sees them placed and can drag them precisely in the editor (M4). Real projection
    ray-casts the top photo's 2D centroids onto the mesh; that lands with the VLM work.
    """
    rows = db.execute(
        select(ModelAnnotation).where(
            ModelAnnotation.product_id == product_id,
            ModelAnnotation.restaurant_id == restaurant_id,
            ModelAnnotation.is_active.is_(True),
            ModelAnnotation.position_x == 0,
            ModelAnnotation.position_y == 0,
            ModelAnnotation.position_z == 0,
        )
    ).scalars().all()
    n = len(rows)
    if n == 0:
        return
    radius = 0.08  # metres — inside a ~0.30 m pizza
    for i, ann in enumerate(rows):
        angle = (2 * math.pi * i) / n
        ann.position_x = round(radius * math.cos(angle), 4)
        ann.position_y = 0.03  # just above the top surface
        ann.position_z = round(radius * math.sin(angle), 4)
        ann.normal_x, ann.normal_y, ann.normal_z = 0.0, 1.0, 0.0
        ann.updated_at = _now()


def _fail_job(db: Session, job_id: uuid.UUID, error: str) -> None:
    job = db.get(GenerationJob, job_id)
    if job is not None:
        job.status = GenerationJobStatus.FAILED
        job.error = error[:2000]
        job.updated_at = _now()
        db.commit()


def _fail_product(
    db: Session, restaurant_id: uuid.UUID, product_id: uuid.UUID, error: str
) -> None:
    try:
        db.rollback()
        product = db.execute(
            select(Product).where(
                Product.id == product_id, Product.restaurant_id == restaurant_id
            )
        ).scalars().first()
        if product is not None:
            product.model_status = ArModelStatus.FAILED
            product.updated_at = _now()
            db.commit()
    except Exception:  # noqa: BLE001
        _log.exception("failed to mark product %s FAILED", product_id)
