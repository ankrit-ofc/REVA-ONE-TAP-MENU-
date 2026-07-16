"""add password_reset_tokens table

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-20 00:00:00.000000

Stores single-use, hashed password reset tokens for the forgot-password flow.
used_at marks a consumed token; expires_at bounds its validity window.
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE password_reset_tokens (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            restaurant_id UUID NOT NULL REFERENCES restaurants(id),
            user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash    TEXT NOT NULL,
            expires_at    TIMESTAMPTZ NOT NULL,
            used_at       TIMESTAMPTZ,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_password_reset_tokens_token_hash UNIQUE (token_hash)
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX ix_password_reset_tokens_restaurant_id "
        "ON password_reset_tokens (restaurant_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX ix_password_reset_tokens_user_id ON password_reset_tokens (user_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX ix_password_reset_tokens_token_hash ON password_reset_tokens (token_hash)"
    ))

    op.execute(sa.text("ALTER TABLE password_reset_tokens ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text(
        "CREATE POLICY tenant_isolation ON password_reset_tokens "
        "USING (restaurant_id = current_setting('app.current_restaurant_id', TRUE)::uuid)"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP POLICY IF EXISTS tenant_isolation ON password_reset_tokens"))
    op.execute(sa.text("ALTER TABLE password_reset_tokens DISABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("DROP TABLE IF EXISTS password_reset_tokens CASCADE"))
