"""Business logic for admin staff management."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import security
from app.models.audit_log import AuditLog
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

    # Only ACTIVE rows block reuse — a deactivated member's email is free again
    # (enforced in the DB by the partial unique index, migration 0019).
    existing = db.execute(
        select(User).where(
            User.email == data.email,
            User.restaurant_id == restaurant_id,
            User.is_active.is_(True),
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

    # Reactivation guard: the email may have been reused by a newer ACTIVE
    # account — surface a clean 409 instead of the partial unique index's 500.
    if data.is_active is True and not user.is_active:
        conflict = db.execute(
            select(User).where(
                User.email == user.email,
                User.restaurant_id == restaurant_id,
                User.is_active.is_(True),
                User.id != user.id,
            )
        ).scalar_one_or_none()
        if conflict is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An active staff member with that email already exists",
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
    actor: User,
) -> StaffResponse:
    """
    Deactivate a staff member (soft delete, CLAUDE.md §3: no DELETE on users).

    All roles are handled the same way: is_active=False. The account row and
    its audit trail are preserved; the email is freed for reuse by the partial
    unique index (active rows only, migration 0019). Deactivated users fail
    login (auth_service.authenticate) and their existing JWTs are rejected on
    the next request (deps.get_current_user checks is_active).

    SUPERADMIN is never touched, and an actor cannot delete their own account.
    """
    user = _get_staff(db, restaurant_id, user_id)

    if user.role in _PROTECTED_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot modify a SUPERADMIN account",
        )
    if user_id == actor.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot delete your own account",
        )
    if not user.is_active:
        # Already deactivated — hidden from list_staff, treat as gone.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staff member not found")

    user.is_active = False
    db.add(AuditLog(
        id=uuid.uuid4(),
        restaurant_id=restaurant_id,
        actor_type=actor.role.value,
        actor_user_id=actor.id,
        entity_type="user",
        entity_id=user.id,
        action="STAFF_DEACTIVATED",
        previous_value={"is_active": True, "email": user.email, "role": user.role.value},
        new_value={"is_active": False},
    ))
    db.commit()
    db.refresh(user)
    return StaffResponse.model_validate(user)
