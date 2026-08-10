"""
Scheduler for the Nightly One-Liner.

Why an in-process tick loop and not APScheduler/Celery/a worker container:
closing time is a LOCAL wall-clock time per restaurant, so there is no single
cron expression to register — every tick has to ask "what time is it *there*"
anyway. A 60-second loop started from the app's lifespan does that with zero new
dependencies, mirroring realtime.manager.start_heartbeat, which is already the
codebase's established background-task shape.

What it costs operationally, stated plainly: the loop dies when the backend
restarts, and a deploy at exactly closing time can miss a tick. That is why the
ledger exists — a missed send is picked up on the next tick, and a restart can
never double-send because (restaurant_id, report_date) is unique. The same
constraint keeps sends single if the backend is ever scaled past one replica.

The DB is synchronous SQLAlchemy, so every tick's work runs in a worker thread
via asyncio.to_thread — blocking the event loop here would stall every
WebSocket and request in the process.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.daily_report_send import DailyReportSend
from app.models.enums import DailyReportStatus, Role
from app.models.restaurant import Restaurant, RestaurantSettings
from app.models.user import User
from app.services import daily_report_email, daily_report_service

logger = logging.getLogger("app.daily_report")

_task: "asyncio.Task[None] | None" = None


# ── Recipients ────────────────────────────────────────────────────────────────

def resolve_recipients(db: Session, restaurant_id: uuid.UUID) -> list[str]:
    """The override address if set, otherwise every active ADMIN of the tenant.

    Defaulting to the ADMIN users means the feature works the moment it is
    switched on, with no extra data entry.
    """
    rsettings = db.execute(
        select(RestaurantSettings).where(RestaurantSettings.restaurant_id == restaurant_id)
    ).scalar_one_or_none()
    if rsettings is not None and rsettings.daily_report_recipient:
        return [rsettings.daily_report_recipient]

    rows = db.execute(
        select(User.email).where(
            User.restaurant_id == restaurant_id,
            User.role == Role.ADMIN,
            User.is_active.is_(True),
        )
    ).scalars().all()
    return list(rows)


# ── Ledger ────────────────────────────────────────────────────────────────────

def _claim_ledger_row(
    db: Session, restaurant_id: uuid.UUID, report_date
) -> DailyReportSend:
    """Insert-or-load today's ledger row and lock it for this attempt.

    ON CONFLICT DO NOTHING + SELECT ... FOR UPDATE rather than a bare "check
    then insert": the unique constraint is the actual guarantee, and the lock
    serialises two attempts that somehow overlap.
    """
    db.execute(
        pg_insert(DailyReportSend)
        .values(
            id=uuid.uuid4(),
            restaurant_id=restaurant_id,
            report_date=report_date,
            status=DailyReportStatus.PENDING,
            attempts=0,
        )
        .on_conflict_do_nothing(index_elements=["restaurant_id", "report_date"])
    )
    db.commit()

    return db.execute(
        select(DailyReportSend)
        .where(
            DailyReportSend.restaurant_id == restaurant_id,
            DailyReportSend.report_date == report_date,
        )
        .with_for_update()
    ).scalar_one()


def send_for_restaurant(
    db: Session, restaurant_id: uuid.UUID, local_day, *, force: bool = False
) -> tuple[DailyReportStatus, bool]:
    """
    Send (or deliberately skip) one restaurant's report for one local day.

    `force` is for the admin "send a test report now" endpoint: it bypasses the
    ledger entirely so a test never consumes or corrupts the real day's row.

    Returns (status, delivered) where `delivered` is False when the message was
    only logged because Resend is unconfigured.
    """
    report = daily_report_service.build_report(db, restaurant_id, local_day)

    if force:
        recipients = resolve_recipients(db, restaurant_id)
        delivered = daily_report_email.send_report(report, recipients, restaurant_id)
        return DailyReportStatus.SENT, delivered

    row = _claim_ledger_row(db, restaurant_id, local_day)

    if row.status in (DailyReportStatus.SENT, DailyReportStatus.SKIPPED_NO_SALES,
                      DailyReportStatus.FAILED):
        db.commit()  # release the lock; nothing to do
        return row.status, False

    # A day with no settled bills has nothing to report, and "Rs 0, down 100%"
    # is noise the owner already knows. Recorded rather than ignored so it is
    # visible in the ledger and never retried all night.
    if not report.has_sales:
        row.status = DailyReportStatus.SKIPPED_NO_SALES
        row.attempts += 1
        db.commit()
        logger.info(
            "Daily report skipped (no sales) restaurant=%s date=%s",
            restaurant_id, local_day,
        )
        return row.status, False

    row.attempts += 1
    delivered = False
    try:
        recipients = resolve_recipients(db, restaurant_id)
        delivered = daily_report_email.send_report(report, recipients, restaurant_id)
    except Exception as exc:  # noqa: BLE001 — recorded, retried, never fatal
        row.error = str(exc)[:500]
        if row.attempts >= settings.DAILY_REPORT_MAX_ATTEMPTS:
            row.status = DailyReportStatus.FAILED
            logger.error(
                "Daily report FAILED after %s attempts restaurant=%s date=%s: %s",
                row.attempts, restaurant_id, local_day, exc,
            )
        else:
            logger.warning(
                "Daily report attempt %s failed restaurant=%s date=%s: %s",
                row.attempts, restaurant_id, local_day, exc,
            )
        db.commit()
        return row.status, False

    row.status = DailyReportStatus.SENT
    row.sent_at = datetime.now(timezone.utc)
    row.error = None
    db.commit()
    return row.status, delivered


# ── Tick ──────────────────────────────────────────────────────────────────────

def run_once() -> None:
    """One pass over every restaurant whose local closing time has passed."""
    db = SessionLocal()
    try:
        rows = db.execute(
            select(Restaurant.id, RestaurantSettings.daily_report_closing_time)
            .join(RestaurantSettings, RestaurantSettings.restaurant_id == Restaurant.id)
            .where(
                Restaurant.is_active.is_(True),
                RestaurantSettings.daily_report_enabled.is_(True),
            )
        ).all()

        for restaurant_id, closing_time in rows:
            try:
                tz = daily_report_service.restaurant_tz(db, restaurant_id)
                now_local = datetime.now(tz)
                # Not closed yet in THIS restaurant's timezone — nothing to do.
                if now_local.time() < closing_time:
                    continue
                send_for_restaurant(db, restaurant_id, now_local.date())
            except Exception:  # noqa: BLE001 — one tenant must never stop the rest
                logger.exception(
                    "Daily report tick failed for restaurant=%s", restaurant_id
                )
                db.rollback()
    finally:
        db.close()


async def _loop(interval: float) -> None:
    while True:
        try:
            await asyncio.to_thread(run_once)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — the loop must outlive any single tick
            logger.exception("Nightly report tick raised")
        await asyncio.sleep(interval)


def start(loop: asyncio.AbstractEventLoop) -> None:
    global _task
    if _task is None or _task.done():
        _task = loop.create_task(_loop(settings.DAILY_REPORT_TICK_SECONDS))


async def stop() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
