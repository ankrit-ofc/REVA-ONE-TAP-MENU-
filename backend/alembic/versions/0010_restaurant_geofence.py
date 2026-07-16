"""add geofence columns to restaurant_settings

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-26 00:00:00.000000

Location-based ordering. When require_location is true and latitude/longitude are
set, POST /scan rejects scans whose device location is farther than
geofence_radius_meters from the restaurant point. All columns default to a safe
"off" state so existing tenants are unaffected.
"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE restaurant_settings "
        "ADD COLUMN require_location BOOLEAN NOT NULL DEFAULT false"
    ))
    op.execute(sa.text(
        "ALTER TABLE restaurant_settings ADD COLUMN latitude DOUBLE PRECISION"
    ))
    op.execute(sa.text(
        "ALTER TABLE restaurant_settings ADD COLUMN longitude DOUBLE PRECISION"
    ))
    op.execute(sa.text(
        "ALTER TABLE restaurant_settings "
        "ADD COLUMN geofence_radius_meters DOUBLE PRECISION NOT NULL DEFAULT 50"
    ))


def downgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE restaurant_settings DROP COLUMN IF EXISTS geofence_radius_meters"
    ))
    op.execute(sa.text("ALTER TABLE restaurant_settings DROP COLUMN IF EXISTS longitude"))
    op.execute(sa.text("ALTER TABLE restaurant_settings DROP COLUMN IF EXISTS latitude"))
    op.execute(sa.text(
        "ALTER TABLE restaurant_settings DROP COLUMN IF EXISTS require_location"
    ))
