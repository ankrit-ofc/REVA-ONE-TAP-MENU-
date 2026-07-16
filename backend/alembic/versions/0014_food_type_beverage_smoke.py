"""add BEVERAGE and SMOKE to food_type enum

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-03 00:00:00.000000

Extends the per-product food_type classification with two more tags:
BEVERAGE (drinks) and SMOKE (hookah and other smokeables). Additive only —
existing rows keep their current value; the column default stays NON_VEG.
"""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run in a transaction that later *uses*
    # the new value; we only add here. autocommit_block keeps it safe on all
    # PG versions. IF NOT EXISTS makes the migration idempotent (PG 12+).
    with op.get_context().autocommit_block():
        op.execute(sa.text("ALTER TYPE food_type ADD VALUE IF NOT EXISTS 'BEVERAGE'"))
        op.execute(sa.text("ALTER TYPE food_type ADD VALUE IF NOT EXISTS 'SMOKE'"))


def downgrade() -> None:
    # PostgreSQL has no DROP VALUE for enums; removing a member would require
    # recreating the type and rewriting the column. Intentionally a no-op.
    pass
