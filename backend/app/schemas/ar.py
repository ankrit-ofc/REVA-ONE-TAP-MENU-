"""
Pydantic v2 schemas (API contract) for the optional per-product AR feature.

Request models forbid unexpected fields; response models read from ORM attributes.
Image / model URLs are backend-set and only ever appear on responses — no request
model accepts them.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    AnnotationSource,
    AnnotationStatus,
    ArModelStatus,
    GenerationJobKind,
    GenerationJobStatus,
    ProductView,
    ThreeDModelKey,
)


# ──────────────────────────────────────────────────────────────────────────────
# View images (the 5 labeled source photos)
# ──────────────────────────────────────────────────────────────────────────────

class ProductViewImageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    product_id: uuid.UUID
    view: ProductView
    image_url: str
    created_at: datetime
    updated_at: datetime


# ──────────────────────────────────────────────────────────────────────────────
# Annotations (per-component nutrition hotspots)
# ──────────────────────────────────────────────────────────────────────────────

_Label = Annotated[str, Field(min_length=1, max_length=120)]
_Nutrient = Annotated[Decimal, Field(ge=Decimal("0"), le=Decimal("100000"))]
_Coord = Annotated[float, Field(ge=-1000, le=1000)]


class AnnotationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: _Label
    position_x: _Coord = 0.0
    position_y: _Coord = 0.0
    position_z: _Coord = 0.0
    normal_x: _Coord = 0.0
    normal_y: _Coord = 1.0
    normal_z: _Coord = 0.0
    calories: _Nutrient | None = None
    protein_g: _Nutrient | None = None
    carbs_g: _Nutrient | None = None
    fat_g: _Nutrient | None = None
    allergens: Annotated[list[Annotated[str, Field(max_length=60)]], Field(max_length=30)] = []


class AnnotationUpdate(BaseModel):
    """Every field optional — editing any value flips the annotation to admin_verified."""
    model_config = ConfigDict(extra="forbid")
    label: _Label | None = None
    position_x: _Coord | None = None
    position_y: _Coord | None = None
    position_z: _Coord | None = None
    normal_x: _Coord | None = None
    normal_y: _Coord | None = None
    normal_z: _Coord | None = None
    calories: _Nutrient | None = None
    protein_g: _Nutrient | None = None
    carbs_g: _Nutrient | None = None
    fat_g: _Nutrient | None = None
    allergens: Annotated[list[Annotated[str, Field(max_length=60)]], Field(max_length=30)] | None = None


class AnnotationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    product_id: uuid.UUID
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
    source: AnnotationSource
    status: AnnotationStatus
    created_at: datetime
    updated_at: datetime


# ──────────────────────────────────────────────────────────────────────────────
# Generation jobs + model status
# ──────────────────────────────────────────────────────────────────────────────

class GenerationJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    product_id: uuid.UUID
    kind: GenerationJobKind
    provider: str
    status: GenerationJobStatus
    external_job_id: str | None
    error: str | None
    created_at: datetime
    updated_at: datetime


class PublishRequest(BaseModel):
    """Toggle customer visibility of a ready model."""
    model_config = ConfigDict(extra="forbid")
    published: bool


class GenerateRequest(BaseModel):
    """Optional body for the generate endpoint: which fal 3D model to use."""
    # protected_namespaces=() allows a field literally named `model` without a warning.
    model_config = ConfigDict(extra="forbid", protected_namespaces=())
    model: ThreeDModelKey | None = None


class ModelStatusResponse(BaseModel):
    """Everything the admin editor / status badge needs for one product's model."""
    model_config = ConfigDict(from_attributes=True)
    product_id: uuid.UUID
    model_status: ArModelStatus
    model_glb_url: str | None
    model_usdz_url: str | None
    model_published: bool
    views: list[ProductViewImageResponse]
    jobs: list[GenerationJobResponse]
    annotations: list[AnnotationResponse]
