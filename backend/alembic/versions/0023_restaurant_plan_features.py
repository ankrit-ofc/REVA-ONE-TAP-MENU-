"""restaurants: subscription plan + starter feature toggles

Revision ID: 0023
Revises: 0022
Create Date: 2026-07-30 00:00:00.000000

Adds platform subscription plan (basic / starter / custom) and two stored
boolean toggles consulted only on starter. DEFAULT plan is 'custom' so every
existing restaurant keeps full Order + Call Waiter functionality.

Effective on/off is computed in app code (plan_features) — these columns are
inputs, not the final button state.
"""

import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text("CREATE TYPE restaurant_plan AS ENUM ('basic', 'starter', 'custom')")
    )
    op.add_column(
        "restaurants",
        sa.Column(
            "plan",
            sa.Enum("basic", "starter", "custom", name="restaurant_plan", create_type=False),
            nullable=False,
            server_default="custom",
        ),
    )
    op.add_column(
        "restaurants",
        sa.Column(
            "order_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "restaurants",
        sa.Column(
            "call_waiter_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    op.drop_column("restaurants", "call_waiter_enabled")
    op.drop_column("restaurants", "order_enabled")
    op.drop_column("restaurants", "plan")
    op.execute(sa.text("DROP TYPE restaurant_plan"))
