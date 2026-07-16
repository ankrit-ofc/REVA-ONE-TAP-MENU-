"""add food_type to products

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-15 00:00:00.000000

Adds a per-product veg/non-veg/egg classification used by the customer
All/Veg/Non filter and the menu card indicator. Native PG enum, matching the
existing enum pattern (role, order_status, …). Legacy rows default to NON_VEG.
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("CREATE TYPE food_type AS ENUM ('VEG','NON_VEG','EGG')"))
    op.execute(sa.text(
        "ALTER TABLE products ADD COLUMN food_type food_type NOT NULL DEFAULT 'NON_VEG'"
    ))


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE products DROP COLUMN IF EXISTS food_type"))
    op.execute(sa.text("DROP TYPE IF EXISTS food_type"))
