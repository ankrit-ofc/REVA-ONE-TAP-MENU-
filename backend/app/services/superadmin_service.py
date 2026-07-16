"""Business logic for superadmin platform management."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

from app.core import security
from app.models.audit_log import AuditLog
from app.models.enums import Role
from app.models.restaurant import Restaurant, RestaurantSettings
from app.models.user import User
from app.schemas.superadmin import AdminEmailUpdate, RestaurantCreate, RestaurantUpdate


def _set_tenant_guc(db: Session, restaurant_id: uuid.UUID) -> None:
    """Set the transaction-local RLS GUC so writes to tenant tables (users,
    audit_logs) pass the WITH CHECK / USING policies. Superadmin endpoints don't
    go through tenant_scope, so we set it explicitly (mirrors create_restaurant)."""
    db.execute(
        text("SELECT set_config('app.current_restaurant_id', :rid, TRUE)"),
        {"rid": str(restaurant_id)},
    )


def _audit(
    db: Session,
    *,
    restaurant_id: uuid.UUID,
    actor: User,
    entity_type: str,
    entity_id: uuid.UUID,
    action: str,
    previous_value: dict | None = None,
    new_value: dict | None = None,
) -> None:
    """Append an audit_logs row for a privileged superadmin write (CLAUDE.md §3).
    Staged on the session; the caller commits in the same transaction."""
    db.add(AuditLog(
        id=uuid.uuid4(),
        restaurant_id=restaurant_id,
        actor_type=actor.role.value,
        actor_user_id=actor.id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        previous_value=previous_value,
        new_value=new_value,
    ))


def list_restaurants(db: Session) -> list[Restaurant]:
    return list(
        db.scalars(
            select(Restaurant)
            .options(selectinload(Restaurant.users))
            .order_by(Restaurant.created_at.asc())
        ).all()
    )


def get_restaurant(db: Session, restaurant_id: uuid.UUID) -> Restaurant:
    restaurant = db.get(Restaurant, restaurant_id)
    if restaurant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant not found")
    return restaurant


def create_restaurant(
    db: Session, data: RestaurantCreate
) -> tuple[Restaurant, str]:
    """
    Creates a new restaurant with default settings and an initial ADMIN user.

    Steps (all in one transaction):
    1. Check slug uniqueness.
    2. Insert the Restaurant row.
    3. Set the Postgres GUC so tenant-scoped RLS allows the subsequent inserts.
    4. Insert RestaurantSettings (defaults).
    5. Insert the initial ADMIN user.
    Returns (restaurant, admin_email).
    """
    existing_slug = db.execute(
        select(Restaurant).where(Restaurant.slug == data.slug)
    ).scalar_one_or_none()
    if existing_slug is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Slug '{data.slug}' is already taken",
        )

    restaurant = Restaurant(name=data.name, slug=data.slug)
    db.add(restaurant)
    db.flush()  # populate restaurant.id before the GUC + FK inserts

    # Set transaction-local GUC so RLS WITH CHECK passes for tenant tables.
    db.execute(
        text("SELECT set_config('app.current_restaurant_id', :rid, TRUE)"),
        {"rid": str(restaurant.id)},
    )

    settings = RestaurantSettings(restaurant_id=restaurant.id)
    db.add(settings)

    admin_user = User(
        restaurant_id=restaurant.id,
        email=data.admin_email,
        password_hash=security.hash_password(data.admin_password),
        role=Role.ADMIN,
    )
    db.add(admin_user)

    db.commit()
    db.refresh(restaurant)
    return restaurant, data.admin_email


def update_restaurant(
    db: Session, restaurant_id: uuid.UUID, data: RestaurantUpdate, actor: User
) -> Restaurant:
    restaurant = get_restaurant(db, restaurant_id)

    previous: dict[str, object] = {}
    changed: dict[str, object] = {}

    if data.name is not None and data.name != restaurant.name:
        previous["name"] = restaurant.name
        changed["name"] = data.name
        restaurant.name = data.name
    if data.is_active is not None and data.is_active != restaurant.is_active:
        previous["is_active"] = restaurant.is_active
        changed["is_active"] = data.is_active
        restaurant.is_active = data.is_active

    if changed:
        _set_tenant_guc(db, restaurant_id)
        _audit(
            db,
            restaurant_id=restaurant_id,
            actor=actor,
            entity_type="restaurant",
            entity_id=restaurant.id,
            action="updated",
            previous_value=previous,
            new_value=changed,
        )

    db.commit()
    db.refresh(restaurant)
    return restaurant


def update_admin_email(
    db: Session,
    restaurant_id: uuid.UUID,
    user_id: uuid.UUID,
    data: AdminEmailUpdate,
    actor: User,
) -> Restaurant:
    """Superadmin edits an ADMIN user's login email. Scoped to ADMIN users of the
    given restaurant only — never other staff (those belong to the admin)."""
    restaurant = get_restaurant(db, restaurant_id)

    admin = db.execute(
        select(User).where(
            User.id == user_id,
            User.restaurant_id == restaurant_id,
            User.role == Role.ADMIN,
        )
    ).scalar_one_or_none()
    if admin is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin user not found")

    new_email = data.email
    if new_email != admin.email:
        # Uniqueness within the restaurant (DB also guards via uq_users_email_restaurant).
        conflict = db.execute(
            select(User).where(
                User.email == new_email,
                User.restaurant_id == restaurant_id,
                User.id != user_id,
            )
        ).scalar_one_or_none()
        if conflict is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with that email already exists",
            )

        _set_tenant_guc(db, restaurant_id)
        _audit(
            db,
            restaurant_id=restaurant_id,
            actor=actor,
            entity_type="user",
            entity_id=admin.id,
            action="email_changed",
            previous_value={"email": admin.email},
            new_value={"email": new_email},
        )
        admin.email = new_email
        db.commit()

    db.refresh(restaurant)
    return restaurant
