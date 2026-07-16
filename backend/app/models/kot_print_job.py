import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, TenantMixin


class KotPrintJob(Base, TimestampMixin, TenantMixin):
    """
    One queued kitchen ticket for the external kot-printer worker (a Windows
    service that polls POST /printworker/kot/get and acks what it printed).

    The ticket content is snapshotted at enqueue time (same immutability rule as
    order items); only the target printer name is resolved at fetch time so an
    admin can repoint pending jobs. printed_at IS NULL = pending; rows are never
    deleted (print history).
    """
    __tablename__ = "kot_print_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Numeric id the worker echoes back in kot/ack (its contract requires a number).
    queue_id: Mapped[int] = mapped_column(
        BigInteger, Identity(), nullable=False, unique=True, index=True
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("orders.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    # ORDER (new round) | ORDER REPRINT (manual relay) — shown as the ticket title.
    title: Mapped[str] = mapped_column(String(40), nullable=False, server_default="ORDER")
    # Worker-shaped ticket body: kot_no, table_name, items [{sn, item_name, quantity, remark}].
    ticket: Mapped[dict] = mapped_column(JSONB, nullable=False)
    printed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
