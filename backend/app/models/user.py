import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum as SAEnum, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import Role
from app.models.mixins import TimestampMixin, TenantMixin

if TYPE_CHECKING:
    from app.models.restaurant import Restaurant


class User(Base, TimestampMixin, TenantMixin):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", "restaurant_id", name="uq_users_email_restaurant"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[Role] = mapped_column(
        SAEnum(Role, name="role", create_type=False), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    restaurant: Mapped["Restaurant"] = relationship("Restaurant", back_populates="users")
