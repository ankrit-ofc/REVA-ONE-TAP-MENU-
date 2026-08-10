"""restaurant_settings: nightly one-liner report + daily_report_sends ledger

Revision ID: 0030
Revises: 0029
Create Date: 2026-08-10 00:00:00.000000

Three additive, non-destructive columns on restaurant_settings:

- daily_report_enabled (BOOLEAN, NOT NULL, DEFAULT false): admin on/off switch.
  The server_default backfills every existing row false, so no restaurant
  starts receiving mail on deploy — the feature is strictly opt-in.
- daily_report_closing_time (TIME, NOT NULL, DEFAULT '22:00'): the LOCAL
  wall-clock time the summary is sent, interpreted in restaurant_settings.
  timezone. Deliberately TIME and not TIMESTAMPTZ: "we close at 22:00" is a
  recurring local fact, and storing an instant would drift across DST for any
  tenant outside Nepal.
- daily_report_recipient (VARCHAR(255), nullable): optional override address.
  NULL means the report goes to every active ADMIN user of the tenant, which
  is the sensible default and needs no data entry to start working.

Plus one new table, daily_report_sends — the send ledger. See the model
docstring for why it exists; in short, the scheduler is an in-process tick
loop, so without a uniqueness guard a container restart near closing time
would re-send, and without an attempt counter a transient provider failure
would be silently dropped.

report_date is the restaurant's LOCAL date (DATE, not TIMESTAMPTZ). The
unique constraint on (restaurant_id, report_date) is what makes a second send
impossible, including if the backend is ever scaled past one replica.

No data migration is required and no existing row is rewritten. Downgrade
drops the table, the enum type, and the three columns — losing only report
scheduling config and send history, never financial or order data.
"""

import sqlalchemy as sa
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text(
        "CREATE TYPE daily_report_status AS ENUM "
        "('PENDING','SENT','SKIPPED_NO_SALES','FAILED')"
    ))

    op.add_column(
        "restaurant_settings",
        sa.Column(
            "daily_report_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "restaurant_settings",
        sa.Column(
            "daily_report_closing_time",
            sa.Time(timezone=False),
            nullable=False,
            server_default=sa.text("'22:00'::time"),
        ),
    )
    op.add_column(
        "restaurant_settings",
        sa.Column("daily_report_recipient", sa.String(length=255), nullable=True),
    )

    op.execute(sa.text(
        """
        CREATE TABLE daily_report_sends (
            id UUID PRIMARY KEY,
            restaurant_id UUID NOT NULL REFERENCES restaurants(id) ON DELETE RESTRICT,
            report_date DATE NOT NULL,
            status daily_report_status NOT NULL DEFAULT 'PENDING',
            attempts INTEGER NOT NULL DEFAULT 0,
            sent_at TIMESTAMPTZ,
            error TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_daily_report_sends_restaurant_date
                UNIQUE (restaurant_id, report_date)
        )
        """
    ))
    # The scheduler's hot query is "has this tenant been sent today's report?",
    # which the unique constraint's implicit index already serves. This second
    # index serves the retry sweep: "any unfinished rows, oldest first".
    op.execute(sa.text(
        "CREATE INDEX ix_daily_report_sends_status_date "
        "ON daily_report_sends (status, report_date)"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ix_daily_report_sends_status_date"))
    op.execute(sa.text("DROP TABLE IF EXISTS daily_report_sends"))
    op.drop_column("restaurant_settings", "daily_report_recipient")
    op.drop_column("restaurant_settings", "daily_report_closing_time")
    op.drop_column("restaurant_settings", "daily_report_enabled")
    op.execute(sa.text("DROP TYPE IF EXISTS daily_report_status"))
