"""
THE single place a Dead Hours offer price is computed.

Read this before touching anything here.

A product's price is resolved in exactly two places in this codebase: the
customer menu (menu_service._product_public) and order placement
(order_service.place_or_append, which snapshots it onto order_items.unit_price
and from there onto every bill, receipt and KOT). If those two ever compute a
discount independently, the menu will one day show Rs 150 while the bill charges
Rs 200. That is the worst bug this feature can produce, so BOTH call sites go
through `PriceBook` below and neither is permitted its own copy of the
arithmetic. If you find yourself writing `anchor - discount` anywhere else, stop.

THE RULES, AND WHERE THEY ARE ENFORCED

1. DISCOUNTS ONLY, never surge. Enforced three times over: PERCENT is capped at
   100 by a Pydantic bound AND a DB CHECK, and `resolve` clamps the result to
   the anchor unconditionally as its last step. The clamp is what survives bad
   data — a floor configured above an item's price cannot raise that price.

2. The anchor NEVER changes. Nothing here writes to products.base_price or
   product_variants.price. The anchor is read, an offer price is computed
   alongside it, and both travel to the customer so the menu can show the normal
   price struck through next to the offer.

3. A badge means a real saving. `resolve` returns None when the computed price
   is not STRICTLY below the anchor, so an offer whose floor eats the entire
   discount produces no badge rather than one advertising a saving of zero.

4. The engine proposes, the owner approves. Only offers with is_enabled AND
   is_active are ever considered.

TIMEZONE
"Is this window live" is answered in the RESTAURANT'S local wall-clock time, via
daily_report_service.restaurant_tz. Never UTC: the weekday derived from a UTC
timestamp flips at 18:15 in Kathmandu, which would run a Tuesday offer on Monday
evenings.

WHAT IS NOT DISCOUNTED
Addons. An addon's price is snapshotted separately (order_items -> addons) and
is never touched by an offer, so "Rs 50 off" means Rs 50 off the item, not off
the item plus its extras. Tax needs no special handling: it is computed per line
on the discounted unit_price downstream in invoice_service, so a discount
correctly reduces the tax charged.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.enums import OfferAppliesTo, OfferDiscountType
from app.models.offer import OfferWindow, OfferWindowProduct
from app.services.daily_report_service import restaurant_tz

_TWO_PLACES = Decimal("0.01")
_HUNDRED = Decimal("100")


def _q(value: Decimal) -> Decimal:
    return value.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class OfferPrice:
    """A live offer applied to one anchor. Only ever constructed when the
    resulting price is strictly below the anchor."""

    final_price: Decimal
    anchor_price: Decimal
    offer_id: uuid.UUID
    offer_name: str
    ends_at: str  # "17:00", local wall clock — the "till 5pm" in the badge


def is_live(offer: OfferWindow, now_local: datetime) -> bool:
    """Is this offer running at `now_local` (restaurant-local wall clock)?

    Half-open [start, end): an offer that ends at 17:00 is over at 17:00:00, so
    a badge reading "till 5pm" is literally true. The DB forbids end <= start,
    so there is no midnight wrap to special-case.
    """
    if not (offer.is_enabled and offer.is_active):
        return False
    if not offer.weekday_mask & (1 << now_local.weekday()):
        return False
    return offer.start_time <= now_local.time() < offer.end_time


def apply(offer: OfferWindow, anchor: Decimal) -> Decimal:
    """The discount arithmetic. The ONLY copy of it in the codebase.

    Returns the resulting price, already clamped and rounded. May return the
    anchor unchanged (when a floor absorbs the whole discount) — deciding
    whether that counts as an offer is `resolve`'s job, not this one's.
    """
    if offer.discount_type is OfferDiscountType.FIXED:
        raw = anchor - offer.discount_value
    else:
        raw = anchor * (_HUNDRED - offer.discount_value) / _HUNDRED

    # The floor the owner stated. Required for FIXED, optional for PERCENT — but
    # never inert: when it is set it is honoured for both types.
    floor = offer.min_resulting_price if offer.min_resulting_price is not None else Decimal("0")
    final = max(raw, floor)
    # RULE 1, last and unconditional: an offer can never raise a price, whatever
    # the configuration says. A floor above the anchor collapses to the anchor.
    final = min(final, anchor)
    return _q(final)


class PriceBook:
    """Every live offer for one restaurant, ready to price any of its items.

    Built once per request (one menu load, one order placement) so a menu with
    200 products issues two queries rather than 200, and — more importantly —
    so every item on that menu is priced against the SAME instant. Pricing each
    product at its own `datetime.now()` would let a window expire midway through
    building one response.
    """

    def __init__(
        self,
        offers: list[OfferWindow],
        product_offers: dict[uuid.UUID, list[OfferWindow]],
        category_offers: dict[uuid.UUID, list[OfferWindow]],
        now_local: datetime,
    ) -> None:
        self._offers = offers
        self._by_product = product_offers
        self._by_category = category_offers
        self.now_local = now_local

    @property
    def has_offers(self) -> bool:
        return bool(self._offers)

    def _candidates(
        self, product_id: uuid.UUID, category_id: uuid.UUID
    ) -> list[OfferWindow]:
        return self._by_product.get(product_id, []) + self._by_category.get(category_id, [])

    def resolve(
        self, product_id: uuid.UUID, category_id: uuid.UUID, anchor: Decimal
    ) -> OfferPrice | None:
        """The best live offer for one anchor price, or None if none applies.

        `anchor` is passed in rather than read from the product because a
        product with variants is priced by its VARIANT — each variant is
        resolved against its own price, and the product's base_price is not
        what would be charged.

        Overlapping offers resolve to the LOWEST resulting price, ties broken by
        created_at ascending (the offer that has been running longest wins). The
        ordering is total, so two identical requests can never disagree.
        """
        priced = [
            (final, offer.created_at, offer)
            for offer in self._candidates(product_id, category_id)
            # Not strictly cheaper => not an offer. No badge for a saving of zero.
            if (final := apply(offer, anchor)) < anchor
        ]
        if not priced:
            return None

        final, _created_at, offer = min(priced, key=lambda row: (row[0], row[1]))
        return OfferPrice(
            final_price=final,
            anchor_price=_q(anchor),
            offer_id=offer.id,
            offer_name=offer.name,
            ends_at=offer.end_time.strftime("%H:%M"),
        )


def build_price_book(db: Session, restaurant_id: uuid.UUID) -> PriceBook:
    """Load this restaurant's currently-live offers into a PriceBook.

    Tenant-scoped on both tables. `now_local` is computed once here and carried
    on the book, so every price derived from it shares one instant.
    """
    now_local = datetime.now(restaurant_tz(db, restaurant_id))

    offers = list(db.scalars(
        select(OfferWindow)
        .where(
            OfferWindow.restaurant_id == restaurant_id,
            OfferWindow.is_active.is_(True),
            OfferWindow.is_enabled.is_(True),
        )
        .options(selectinload(OfferWindow.products))
        .order_by(OfferWindow.created_at.asc())
    ).all())

    live = [o for o in offers if is_live(o, now_local)]

    by_product: dict[uuid.UUID, list[OfferWindow]] = {}
    by_category: dict[uuid.UUID, list[OfferWindow]] = {}
    for offer in live:
        if offer.applies_to is OfferAppliesTo.CATEGORY and offer.category_id is not None:
            by_category.setdefault(offer.category_id, []).append(offer)
        else:
            for link in offer.products:
                by_product.setdefault(link.product_id, []).append(offer)

    return PriceBook(live, by_product, by_category, now_local)


def empty_price_book(db: Session, restaurant_id: uuid.UUID) -> PriceBook:
    """A book with no offers — for callers that must not price (tests, and any
    surface deliberately showing anchor prices only)."""
    return PriceBook([], {}, {}, datetime.now(restaurant_tz(db, restaurant_id)))


def products_reaching_floor(
    db: Session, offer: OfferWindow, anchors: list[Decimal]
) -> int:
    """How many of `anchors` have their discount cut short by the floor.

    Powers the admin editor's configuration-time warning ("this discount reaches
    the floor on 4 of the selected items"). Order time clamps SILENTLY — a
    customer's order must never fail over pricing config — so authoring time is
    the only place this can be surfaced before it turns up on a bill.
    """
    if offer.min_resulting_price is None:
        return 0
    count = 0
    for anchor in anchors:
        if offer.discount_type is OfferDiscountType.FIXED:
            raw = anchor - offer.discount_value
        else:
            raw = anchor * (_HUNDRED - offer.discount_value) / _HUNDRED
        if raw < offer.min_resulting_price:
            count += 1
    return count
