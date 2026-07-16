import uuid

from sqlalchemy import Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, TenantMixin


class RestaurantCounter(Base, TimestampMixin, TenantMixin):
    """
    Gapless per-restaurant sequence counters (order numbers, invoice numbers).
    Incremented under SELECT FOR UPDATE to prevent races.
    """

    __tablename__ = "restaurant_counters"
    __table_args__ = (
        UniqueConstraint("restaurant_id", "counter_type", name="uq_restaurant_counters_restaurant_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    counter_type: Mapped[str] = mapped_column(Text, nullable=False)
    current_value: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
