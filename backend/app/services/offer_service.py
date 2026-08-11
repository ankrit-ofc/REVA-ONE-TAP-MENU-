"""
Tenant-scoped CRUD for Dead Hours offer windows.

Every query filters on restaurant_id derived from the verified JWT — never from
client input. Cross-tenant FK checks (an offer's category and every product it
names must belong to the same restaurant) are enforced here, not in the router:
without them an admin could attach another tenant's product id to their own
offer and learn whether it exists.

Soft delete only (is_active=False). is_enabled is a SEPARATE owner switch: the
engine proposes, the owner approves, and a disabled offer prices nothing.
Deactivating or disabling an offer never touches an order already placed — the
charged price, the anchor, and the offer name are snapshotted onto order_items
at order time.

Every write emits an audit_logs row (CLAUDE.md §3). Enable and disable are
audited as their own actions rather than as a generic update, because "who
turned the 40%-off on" is the first question anyone asks about a surprising
day's takings.

Money note: nothing here computes a price. The discount arithmetic lives in
pricing_service and only there.
"""

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.audit_log import AuditLog
from app.models.category import Category
from app.models.enums import OfferAppliesTo
from app.models.offer import OfferWindow, OfferWindowProduct
from app.models.product import Product
from app.models.user import User
from app.schemas.offer import OfferWindowCreate, OfferWindowPublic, OfferWindowUpdate
from app.services import pricing_service
from app.services.daily_report_service import restaurant_tz


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _audit(
    db: Session,
    *,
    restaurant_id: uuid.UUID,
    actor: User,
    offer_id: uuid.UUID,
    action: str,
    previous_value: dict | None = None,
    new_value: dict | None = None,
) -> None:
    db.add(AuditLog(
        id=uuid.uuid4(),
        restaurant_id=restaurant_id,
        actor_type=actor.role.value,
        actor_user_id=actor.id,
        entity_type="offer_window",
        entity_id=offer_id,
        action=action,
        previous_value=previous_value,
        new_value=new_value,
    ))


def _snapshot(offer: OfferWindow, product_ids: list[uuid.UUID]) -> dict:
    """Audit payload. Money values as strings — a Decimal is not JSON."""
    return {
        "name": offer.name,
        "discount_type": offer.discount_type.value,
        "discount_value": str(offer.discount_value),
        "min_resulting_price": (
            str(offer.min_resulting_price) if offer.min_resulting_price is not None else None
        ),
        "start_time": offer.start_time.strftime("%H:%M"),
        "end_time": offer.end_time.strftime("%H:%M"),
        "weekday_mask": offer.weekday_mask,
        "applies_to": offer.applies_to.value,
        "category_id": str(offer.category_id) if offer.category_id else None,
        "product_ids": [str(p) for p in product_ids],
        "is_enabled": offer.is_enabled,
    }


def _get_or_404(db: Session, restaurant_id: uuid.UUID, offer_id: uuid.UUID) -> OfferWindow:
    offer = db.execute(
        select(OfferWindow)
        .where(
            OfferWindow.id == offer_id,
            OfferWindow.restaurant_id == restaurant_id,
            OfferWindow.is_active.is_(True),
        )
        .options(selectinload(OfferWindow.products))
    ).scalar_one_or_none()
    if offer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found")
    return offer


def _validate_targets(
    db: Session, restaurant_id: uuid.UUID, data: OfferWindowCreate | OfferWindowUpdate
) -> None:
    """The category and every product must be live and in THIS tenant.

    422 rather than 404 for an unknown id: the request body is malformed from
    this tenant's point of view, and a 404 here would let an admin probe whether
    another restaurant's product id exists.
    """
    if data.applies_to is OfferAppliesTo.CATEGORY:
        found = db.scalar(
            select(Category.id).where(
                Category.id == data.category_id,
                Category.restaurant_id == restaurant_id,
                Category.is_active.is_(True),
            )
        )
        if found is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Category not found",
            )
        return

    found_ids = set(db.scalars(
        select(Product.id).where(
            Product.id.in_(data.product_ids),
            Product.restaurant_id == restaurant_id,
            Product.is_active.is_(True),
        )
    ).all())
    missing = [str(p) for p in data.product_ids if p not in found_ids]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Products not found: {', '.join(sorted(missing))}",
        )


def _replace_products(
    db: Session, restaurant_id: uuid.UUID, offer: OfferWindow, product_ids: list[uuid.UUID]
) -> None:
    """Reset the offer's product list to exactly `product_ids`.

    Hard-deletes the junction rows: OfferWindowProduct is configuration, not a
    financial record, and past orders keep their own snapshot of what they were
    charged (mirrors ProductAddonMapping).
    """
    for existing in list(offer.products):
        db.delete(existing)
    db.flush()
    for product_id in product_ids:
        db.add(OfferWindowProduct(
            id=uuid.uuid4(),
            restaurant_id=restaurant_id,
            offer_window_id=offer.id,
            product_id=product_id,
        ))


def to_public(offer: OfferWindow, now_local: datetime) -> OfferWindowPublic:
    return OfferWindowPublic(
        id=offer.id,
        name=offer.name,
        discount_type=offer.discount_type,
        discount_value=offer.discount_value,
        min_resulting_price=offer.min_resulting_price,
        start_time=offer.start_time,
        end_time=offer.end_time,
        weekday_mask=offer.weekday_mask,
        applies_to=offer.applies_to,
        category_id=offer.category_id,
        product_ids=[link.product_id for link in offer.products],
        is_enabled=offer.is_enabled,
        is_live_now=pricing_service.is_live(offer, now_local),
        created_at=offer.created_at,
        updated_at=offer.updated_at,
    )


# ── Operations ────────────────────────────────────────────────────────────────

def list_offers(db: Session, restaurant_id: uuid.UUID) -> list[OfferWindowPublic]:
    now_local = datetime.now(restaurant_tz(db, restaurant_id))
    offers = db.scalars(
        select(OfferWindow)
        .where(
            OfferWindow.restaurant_id == restaurant_id,
            OfferWindow.is_active.is_(True),
        )
        .options(selectinload(OfferWindow.products))
        .order_by(OfferWindow.created_at.asc())
    ).all()
    return [to_public(o, now_local) for o in offers]


def get_offer(
    db: Session, restaurant_id: uuid.UUID, offer_id: uuid.UUID
) -> OfferWindowPublic:
    offer = _get_or_404(db, restaurant_id, offer_id)
    return to_public(offer, datetime.now(restaurant_tz(db, restaurant_id)))


def create_offer(
    db: Session, restaurant_id: uuid.UUID, data: OfferWindowCreate, actor: User
) -> OfferWindowPublic:
    _validate_targets(db, restaurant_id, data)

    offer = OfferWindow(
        id=uuid.uuid4(),
        restaurant_id=restaurant_id,
        name=data.name,
        discount_type=data.discount_type,
        discount_value=data.discount_value,
        min_resulting_price=data.min_resulting_price,
        start_time=data.start_time,
        end_time=data.end_time,
        weekday_mask=data.weekday_mask,
        applies_to=data.applies_to,
        category_id=data.category_id,
        is_enabled=data.is_enabled,
        is_active=True,
    )
    db.add(offer)
    db.flush()
    _replace_products(db, restaurant_id, offer, data.product_ids)
    db.flush()

    _audit(
        db,
        restaurant_id=restaurant_id,
        actor=actor,
        offer_id=offer.id,
        action="OFFER_CREATE",
        new_value=_snapshot(offer, data.product_ids),
    )
    db.commit()
    return get_offer(db, restaurant_id, offer.id)


def update_offer(
    db: Session,
    restaurant_id: uuid.UUID,
    offer_id: uuid.UUID,
    data: OfferWindowUpdate,
    actor: User,
) -> OfferWindowPublic:
    offer = _get_or_404(db, restaurant_id, offer_id)
    _validate_targets(db, restaurant_id, data)
    previous = _snapshot(offer, [link.product_id for link in offer.products])

    offer.name = data.name
    offer.discount_type = data.discount_type
    offer.discount_value = data.discount_value
    offer.min_resulting_price = data.min_resulting_price
    offer.start_time = data.start_time
    offer.end_time = data.end_time
    offer.weekday_mask = data.weekday_mask
    offer.applies_to = data.applies_to
    offer.category_id = data.category_id
    offer.is_enabled = data.is_enabled
    offer.updated_at = _now()
    _replace_products(db, restaurant_id, offer, data.product_ids)
    db.flush()

    _audit(
        db,
        restaurant_id=restaurant_id,
        actor=actor,
        offer_id=offer.id,
        action="OFFER_UPDATE",
        previous_value=previous,
        new_value=_snapshot(offer, data.product_ids),
    )
    db.commit()
    return get_offer(db, restaurant_id, offer_id)


def set_enabled(
    db: Session, restaurant_id: uuid.UUID, offer_id: uuid.UUID, enabled: bool, actor: User
) -> OfferWindowPublic:
    """The owner's approve/withdraw switch, audited as its own action.

    Separate from update_offer so the audit log answers "who turned this on, and
    when" directly, without diffing two config snapshots.
    """
    offer = _get_or_404(db, restaurant_id, offer_id)
    previous = offer.is_enabled
    offer.is_enabled = enabled
    offer.updated_at = _now()
    _audit(
        db,
        restaurant_id=restaurant_id,
        actor=actor,
        offer_id=offer.id,
        action="OFFER_ENABLED" if enabled else "OFFER_DISABLED",
        previous_value={"is_enabled": previous},
        new_value={"is_enabled": enabled},
    )
    db.commit()
    return get_offer(db, restaurant_id, offer_id)


def soft_delete_offer(
    db: Session, restaurant_id: uuid.UUID, offer_id: uuid.UUID, actor: User
) -> None:
    """Retire an offer. is_enabled is cleared too, so a later reactivation can
    never quietly resume charging a discount nobody re-approved."""
    offer = _get_or_404(db, restaurant_id, offer_id)
    offer.is_active = False
    offer.is_enabled = False
    offer.updated_at = _now()
    _audit(
        db,
        restaurant_id=restaurant_id,
        actor=actor,
        offer_id=offer.id,
        action="OFFER_DELETE",
        previous_value={"is_active": True},
        new_value={"is_active": False, "is_enabled": False},
    )
    db.commit()


def floor_warning(
    db: Session, restaurant_id: uuid.UUID, offer_id: uuid.UUID
) -> dict:
    """How many of an offer's items have their discount cut short by the floor.

    The admin editor's configuration-time warning. Order time clamps SILENTLY —
    a customer's order must never fail over pricing config — so this is the only
    place the owner can be told before it shows up on a bill.
    """
    offer = _get_or_404(db, restaurant_id, offer_id)

    q = select(Product.base_price).where(
        Product.restaurant_id == restaurant_id,
        Product.is_active.is_(True),
    )
    if offer.applies_to is OfferAppliesTo.CATEGORY:
        q = q.where(Product.category_id == offer.category_id)
    else:
        q = q.where(Product.id.in_([link.product_id for link in offer.products]))

    anchors = list(db.scalars(q).all())
    return {
        "item_count": len(anchors),
        "reaching_floor": pricing_service.products_reaching_floor(db, offer, anchors),
    }
