"""add refresh_tokens table

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-13 00:00:00.000000

Stores persisted refresh tokens for rotation tracking (Phase 2 auth).
Supports multiple concurrent sessions per user; revoked_at marks consumed tokens.
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE refresh_tokens (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            restaurant_id UUID NOT NULL REFERENCES restaurants(id),
            user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            jti           TEXT NOT NULL,
            expires_at    TIMESTAMPTZ NOT NULL,
            revoked_at    TIMESTAMPTZ,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_refresh_tokens_jti UNIQUE (jti)
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX ix_refresh_tokens_restaurant_id ON refresh_tokens (restaurant_id)"
    ))
    op.execute(sa.text("CREATE INDEX ix_refresh_tokens_user_id ON refresh_tokens (user_id)"))
    # jti index is already created via the UNIQUE constraint, but adding explicit for clarity
    op.execute(sa.text("CREATE INDEX ix_refresh_tokens_jti ON refresh_tokens (jti)"))

    op.execute(sa.text("ALTER TABLE refresh_tokens ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text(
        "CREATE POLICY tenant_isolation ON refresh_tokens "
        "USING (restaurant_id = current_setting('app.current_restaurant_id', TRUE)::uuid)"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP POLICY IF EXISTS tenant_isolation ON refresh_tokens"))
    op.execute(sa.text("ALTER TABLE refresh_tokens DISABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("DROP TABLE IF EXISTS refresh_tokens CASCADE"))
