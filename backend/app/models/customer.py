import uuid
from typing import Optional

from sqlalchemy import Boolean, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, TenantMixin


class Customer(Base, TimestampMixin, TenantMixin):
    """
    A diner who gave us their contact details so we could email them a receipt.

    Scoped per restaurant: the same person eating at two tenants is two rows, so
    one restaurant can never read the other's customer list (STANDING INVARIANT
    §3 — tenancy). `email` is stored already normalised (trimmed + lowercased) by
    customer_service; the unique index below is a plain column index, NOT a
    functional one, so normalising before the write is mandatory — see
    customer_service.normalize_email, the single place that does it.

    No hard delete, ever (§3). `is_active` is the soft-delete/suppression hook;
    honouring unsubscribe requests is a separate piece of work.
    """

    __tablename__ = "customers"
    __table_args__ = (
        Index("uq_customers_restaurant_email", "restaurant_id", "email", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
