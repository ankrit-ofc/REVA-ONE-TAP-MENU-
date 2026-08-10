import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Enum as SAEnum, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import DailyReportStatus
from app.models.mixins import TimestampMixin, TenantMixin


class DailyReportSend(Base, TimestampMixin, TenantMixin):
    """
    One row per restaurant per LOCAL report date: the send ledger for the
    Nightly One-Liner.

    It exists for two reasons, both load-bearing:

    1. Idempotency. The scheduler is an in-process tick loop, so a container
       restart near closing time would otherwise re-send. The unique constraint
       on (restaurant_id, report_date) makes a second send impossible, including
       if the backend is ever scaled past one replica.
    2. Retry. Unlike receipt_email — which claims `invoices.receipt_sent_at`
       before dispatch and deliberately never retries, because a duplicate
       money-adjacent mail is worse than a missing one — a summary email is
       safe to retry and useless if silently dropped. So this ledger tracks
       `attempts` and a status rather than a bare timestamp.

    report_date is the restaurant's LOCAL date, not a UTC date. Two restaurants
    in different timezones closing at the same instant get different rows.
    """

    __tablename__ = "daily_report_sends"
    __table_args__ = (
        UniqueConstraint("restaurant_id", "report_date", name="uq_daily_report_sends_restaurant_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[DailyReportStatus] = mapped_column(
        SAEnum(DailyReportStatus, name="daily_report_status", create_type=False),
        nullable=False,
        server_default=DailyReportStatus.PENDING.value,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Last failure reason, for operator diagnosis. Never contains the recipient
    # address in full (PII rule — see receipt_email.redact_email).
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
