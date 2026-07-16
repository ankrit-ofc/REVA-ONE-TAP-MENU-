"""add self-referencing parent to categories (multilevel menu)

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-02 12:00:00.000000

Adds categories.parent_id so categories form an adjacency-list tree
(Beverage → Domestic Liquors → Whiskey → …). Additive + nullable: every existing
category keeps parent_id NULL and becomes a root, so nothing changes for current
menus. ON DELETE RESTRICT preserves history (categories are soft-deleted anyway).
categories already has RLS (tenant_isolation) — the new column needs no policy.
"""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE categories ADD COLUMN parent_id UUID NULL "
        "REFERENCES categories(id) ON DELETE RESTRICT"
    ))
    op.execute(sa.text(
        "CREATE INDEX ix_categories_parent_id ON categories (parent_id)"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ix_categories_parent_id"))
    op.execute(sa.text("ALTER TABLE categories DROP COLUMN IF EXISTS parent_id"))
