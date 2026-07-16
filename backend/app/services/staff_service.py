"""Business logic for admin staff management."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import security
from app.models.enums import Role
from app.models.user import User
from app.schemas.admin_staff import StaffCreate, StaffResponse, StaffUpdate

_PROTECTED_ROLES = {Role.SUPERADMIN}


def _get_staff(db: Session, restaurant_id: uuid.UUID, user_id: uuid.UUID) -> User:
    user = db.execute(
        select(User).where(
            User.id == user_id,
            User.restaurant_id == restaurant_id,
        )
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staff member not found")
    return user


def list_staff(db: Session, restaurant_id: uuid.UUID) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .where(
                User.restaurant_id == restaurant_id,
                User.role != Role.SUPERADMIN,
                User.is_active.is_(True),  # hide deleted staff (hard-deleted rows are gone)
            )
            .order_by(User.created_at.asc())
        ).all()
    )


def create_staff(db: Session, restaurant_id: uuid.UUID, data: StaffCreate) -> User:
    if data.role in _PROTECTED_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot create SUPERADMIN users via this endpoint",
        )

    existing = db.execute(
        select(User).where(
            User.email == data.email,
            User.restaurant_id == restaurant_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A staff member with that email already exists",
        )

    user = User(
        restaurant_id=restaurant_id,
        email=data.email,
        password_hash=security.hash_password(data.password),
        role=data.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_staff(
    db: Session,
    restaurant_id: uuid.UUID,
    user_id: uuid.UUID,
    data: StaffUpdate,
    actor_id: uuid.UUID,
) -> User:
    user = _get_staff(db, restaurant_id, user_id)

    if user.role in _PROTECTED_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot modify a SUPERADMIN account",
        )
    if data.role is not None and data.role in _PROTECTED_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot promote to SUPERADMIN via this endpoint",
        )
    # Prevent an admin from deactivating their own account (lockout guard)
    if data.is_active is False and user_id == actor_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot deactivate your own account",
        )

    if data.role is not None:
        user.role = data.role
    if data.is_active is not None:
        user.is_active = data.is_active

    db.commit()
    db.refresh(user)
    return user


def delete_staff(
    db: Session,
    restaurant_id: uuid.UUID,
    user_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> StaffResponse:
    """
    Remove a staff member.

    Non-admin staff (KITCHEN/WAITER/COUNTER/COUNTER_DISPLAY) are HARD-deleted so
    their email frees up for reuse. This is referentially safe: audit_logs.actor_user_id
    is ON DELETE SET NULL and the token tables CASCADE, so action history is preserved.

    ADMIN accounts are kept recoverable (soft-delete, is_active=False) — they mirror
    the superadmin-managed accounts and there is no created_by to distinguish them.

    SUPERADMIN is never touched, and an actor cannot delete their own account.
    """
    user = _get_staff(db, restaurant_id, user_id)

    if user.role in _PROTECTED_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot modify a SUPERADMIN account",
        )
    if user_id == actor_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot delete your own account",
        )

    # Snapshot before mutating — the ORM instance expires/deletes on commit.
    snapshot = StaffResponse.model_validate(user)

    if user.role == Role.ADMIN:
        user.is_active = False
        db.commit()
        return StaffResponse.model_validate(user)

    db.delete(user)
    db.commit()
    return snapshot
