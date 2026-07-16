"""users: partial unique email index on active rows (staff soft-delete)

Revision ID: 0019
Revises: 0018
Create Date: 2026-07-16 00:00:00.000000

Staff deletion is now a soft delete (is_active=false) per CLAUDE.md §3 — no
DELETE on users. The old table-wide UNIQUE (email, restaurant_id) would lock a
deactivated member's email forever, so it is replaced by a partial unique
index that only active rows contend for: the email frees up on deactivation
while the historical row (and its audit trail) is preserved.

Downgrade restores the original constraint. NOTE: the downgrade fails by
design if the same (email, restaurant_id) exists on both an active and an
inactive row — that data is only valid under the partial index; resolve the
duplicates before downgrading.
"""

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE users DROP CONSTRAINT uq_users_email_restaurant"
    ))
    op.execute(sa.text(
        """
        CREATE UNIQUE INDEX uq_users_email_restaurant_active
        ON users (email, restaurant_id)
        WHERE is_active
        """
    ))


def downgrade() -> None:
    op.execute(sa.text(
        "DROP INDEX uq_users_email_restaurant_active"
    ))
    op.execute(sa.text(
        """
        ALTER TABLE users
        ADD CONSTRAINT uq_users_email_restaurant UNIQUE (email, restaurant_id)
        """
    ))
