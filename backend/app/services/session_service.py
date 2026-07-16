import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.config import settings
from app.models.enums import SessionStatus
from app.models.table import Table, TableSession
from app.services import waiter_call_service


def create_or_reuse_session(db: DBSession, table: Table) -> tuple[str, TableSession]:
    """
    Returns (raw_token, session).
    If an ACTIVE, non-expired session already exists for the table, returns it so
    multiple diners who scan the same QR share one session.
    A row lock on the table prevents concurrent duplicate creation.

    Tokens are stored raw (not hashed) because the re-scan path must return the
    existing token — hashing would make it unrecoverable.
    """
    now = datetime.now(timezone.utc)

    # Acquire a row-level lock on the table to serialise concurrent scans.
    db.execute(select(Table).where(Table.id == table.id).with_for_update())

    existing: TableSession | None = db.execute(
        select(TableSession).where(
            TableSession.table_id == table.id,
            TableSession.restaurant_id == table.restaurant_id,
            TableSession.status == SessionStatus.ACTIVE,
            TableSession.expires_at > now,
        )
    ).scalar_one_or_none()

    if existing is not None:
        return existing.token, existing

    raw_token = secrets.token_urlsafe(32)  # 256-bit entropy
    session = TableSession(
        id=uuid.uuid4(),
        restaurant_id=table.restaurant_id,
        table_id=table.id,
        token=raw_token,
        status=SessionStatus.ACTIVE,
        expires_at=now + timedelta(hours=settings.TABLE_SESSION_TTL_HOURS),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return raw_token, session


def invalidate_session(db: DBSession, session: TableSession) -> None:
    session.status = SessionStatus.INVALIDATED
    session.invalidated_at = datetime.now(timezone.utc)
    db.commit()


def call_waiter(db: DBSession, session: TableSession) -> str:
    """
    Ring every waiter's dashboard for this table and persist the call so a waiter
    can confirm attendance later (see waiter_call_service). Order-independent —
    works any time the session is valid. Returns the table name so the caller can
    echo it back to the customer.
    """
    table_name, _call = waiter_call_service.create_call(db, session)
    return table_name
