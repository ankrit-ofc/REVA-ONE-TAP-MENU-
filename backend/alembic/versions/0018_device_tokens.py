"""add device_tokens (staff push-notification registrations)

Revision ID: 0018
Revises: 0017
Create Date: 2026-07-14 00:00:00.000000

Staff devices register an Expo push token so the backend can deliver order /
waiter-call notifications even when the app is closed (Expo Push → FCM/APNs).
Tokens are tenant-scoped and soft-deactivated (is_active) — never hard-deleted —
so a token that Expo reports as unregistered is retired, not erased.
"""

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text(
        """
        CREATE TABLE device_tokens (
            id UUID PRIMARY KEY,
            restaurant_id UUID NOT NULL REFERENCES restaurants(id) ON DELETE RESTRICT,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            token TEXT NOT NULL,
            platform VARCHAR(10) NOT NULL DEFAULT 'android',
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_device_tokens_platform CHECK (platform IN ('android', 'ios'))
        )
        """
    ))
    # One row per physical token; re-registration updates the existing row.
    op.execute(sa.text(
        "CREATE UNIQUE INDEX uq_device_tokens_token ON device_tokens (token)"
    ))
    op.execute(sa.text(
        "CREATE INDEX ix_device_tokens_restaurant_id ON device_tokens (restaurant_id)"
    ))
    # The send-time lookup: active tokens for a restaurant.
    op.execute(sa.text(
        "CREATE INDEX ix_device_tokens_active "
        "ON device_tokens (restaurant_id, user_id) WHERE is_active"
    ))

    # ── Row-Level Security (second line of defense; app-layer filter is first) ─
    op.execute(sa.text("ALTER TABLE device_tokens ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text(
        "CREATE POLICY tenant_isolation ON device_tokens "
        "USING (restaurant_id = current_setting('app.current_restaurant_id', TRUE)::uuid)"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP POLICY IF EXISTS tenant_isolation ON device_tokens"))
    op.execute(sa.text("ALTER TABLE device_tokens DISABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("DROP TABLE IF EXISTS device_tokens CASCADE"))
