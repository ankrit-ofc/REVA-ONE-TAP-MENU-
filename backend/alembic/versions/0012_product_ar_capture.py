"""add product AR/3D model capture schema

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-02 00:00:00.000000

Optional, per-product AR 3D-model + nutrition feature (additive, non-breaking).

Adds AR columns to products (model_status defaults to 'NONE' so every existing
product behaves exactly as before) and three new tenant-owned tables:
  - product_view_images : the 5 labeled source photos (front/back/left/right/top)
  - model_annotations   : per-component nutrition hotspots (AI draft → admin verified)
  - generation_jobs      : drives the generation + marking pipeline

Each new table is tenant-scoped (restaurant_id NOT NULL) with the standard
tenant_isolation RLS policy, matching every other tenant table (see 0002).
"""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

_NEW_TABLES = ["product_view_images", "model_annotations", "generation_jobs"]
_NEW_ENUMS = [
    "ar_model_status",
    "product_view",
    "annotation_source",
    "annotation_status",
    "generation_job_kind",
    "generation_job_status",
]


def upgrade() -> None:
    # ── ENUM types ────────────────────────────────────────────────────────────
    op.execute(sa.text(
        "CREATE TYPE ar_model_status AS ENUM "
        "('NONE','PENDING','GENERATING','READY','FAILED')"
    ))
    op.execute(sa.text(
        "CREATE TYPE product_view AS ENUM ('FRONT','BACK','LEFT','RIGHT','TOP')"
    ))
    op.execute(sa.text("CREATE TYPE annotation_source AS ENUM ('AI','MANUAL')"))
    op.execute(sa.text(
        "CREATE TYPE annotation_status AS ENUM ('AI_ESTIMATED','ADMIN_VERIFIED')"
    ))
    op.execute(sa.text("CREATE TYPE generation_job_kind AS ENUM ('GENERATION','MARKING')"))
    op.execute(sa.text(
        "CREATE TYPE generation_job_status AS ENUM ('QUEUED','RUNNING','DONE','FAILED')"
    ))

    # ── products: AR columns (all safe defaults → existing rows unaffected) ────
    op.execute(sa.text(
        "ALTER TABLE products ADD COLUMN model_status ar_model_status "
        "NOT NULL DEFAULT 'NONE'"
    ))
    op.execute(sa.text("ALTER TABLE products ADD COLUMN model_glb_url TEXT"))
    op.execute(sa.text("ALTER TABLE products ADD COLUMN model_usdz_url TEXT"))
    op.execute(sa.text(
        "ALTER TABLE products ADD COLUMN model_published BOOLEAN NOT NULL DEFAULT FALSE"
    ))

    # ── product_view_images ───────────────────────────────────────────────────
    op.execute(sa.text("""
        CREATE TABLE product_view_images (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            restaurant_id UUID NOT NULL REFERENCES restaurants(id),
            product_id    UUID NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
            view          product_view NOT NULL,
            image_url     TEXT NOT NULL,
            is_active     BOOLEAN NOT NULL DEFAULT TRUE,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX ix_product_view_images_restaurant_id "
        "ON product_view_images (restaurant_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX ix_product_view_images_product_id "
        "ON product_view_images (product_id)"
    ))
    # One active image per (product, view); soft-replaced images don't collide.
    op.execute(sa.text(
        "CREATE UNIQUE INDEX uq_product_view_images_active_view "
        "ON product_view_images (product_id, view) WHERE is_active"
    ))

    # ── model_annotations ─────────────────────────────────────────────────────
    op.execute(sa.text("""
        CREATE TABLE model_annotations (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            restaurant_id UUID NOT NULL REFERENCES restaurants(id),
            product_id    UUID NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
            label         TEXT NOT NULL,
            position_x    DOUBLE PRECISION NOT NULL DEFAULT 0,
            position_y    DOUBLE PRECISION NOT NULL DEFAULT 0,
            position_z    DOUBLE PRECISION NOT NULL DEFAULT 0,
            normal_x      DOUBLE PRECISION NOT NULL DEFAULT 0,
            normal_y      DOUBLE PRECISION NOT NULL DEFAULT 1,
            normal_z      DOUBLE PRECISION NOT NULL DEFAULT 0,
            calories      NUMERIC(10, 2),
            protein_g     NUMERIC(10, 2),
            carbs_g       NUMERIC(10, 2),
            fat_g         NUMERIC(10, 2),
            allergens     JSONB NOT NULL DEFAULT '[]'::jsonb,
            source        annotation_source NOT NULL,
            status        annotation_status NOT NULL,
            is_active     BOOLEAN NOT NULL DEFAULT TRUE,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX ix_model_annotations_restaurant_id "
        "ON model_annotations (restaurant_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX ix_model_annotations_product_id "
        "ON model_annotations (product_id)"
    ))

    # ── generation_jobs ───────────────────────────────────────────────────────
    op.execute(sa.text("""
        CREATE TABLE generation_jobs (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            restaurant_id   UUID NOT NULL REFERENCES restaurants(id),
            product_id      UUID NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
            kind            generation_job_kind NOT NULL,
            provider        TEXT NOT NULL,
            status          generation_job_status NOT NULL DEFAULT 'QUEUED',
            external_job_id TEXT,
            error           TEXT,
            is_active       BOOLEAN NOT NULL DEFAULT TRUE,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX ix_generation_jobs_restaurant_id ON generation_jobs (restaurant_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX ix_generation_jobs_product_id ON generation_jobs (product_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX ix_generation_jobs_status ON generation_jobs (status)"
    ))

    # ── Row-Level Security (second line of defense; app-layer filter is first) ─
    for table in _NEW_TABLES:
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING (restaurant_id = current_setting('app.current_restaurant_id', TRUE)::uuid)"
        ))


def downgrade() -> None:
    for table in reversed(_NEW_TABLES):
        op.execute(sa.text(f"DROP POLICY IF EXISTS tenant_isolation ON {table}"))
        op.execute(sa.text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"DROP TABLE IF EXISTS {table} CASCADE"))

    for column in ("model_published", "model_usdz_url", "model_glb_url", "model_status"):
        op.execute(sa.text(f"ALTER TABLE products DROP COLUMN IF EXISTS {column}"))

    for enum_name in _NEW_ENUMS:
        op.execute(sa.text(f"DROP TYPE IF EXISTS {enum_name}"))
