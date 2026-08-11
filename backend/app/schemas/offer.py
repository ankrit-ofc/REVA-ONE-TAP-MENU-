"""
Pydantic schemas for the Dead Hours Engine — offer window CRUD plus the
read-only "your Tuesday 2-5pm is your quietest stretch" suggestion analysis.

The write schemas below are the API contract for a feature that decides what a
customer is CHARGED, so every bound here is duplicated by a CHECK constraint in
migration 0032. Neither layer is decorative: Pydantic gives the admin a 422 with
a readable message, and the CHECK is what holds if anything ever reaches the
table by another route.
"""

from __future__ import annotations

import uuid
from datetime import datetime, time
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import OfferAppliesTo, OfferDiscountType

# Mon..Sun as bits 0..6, matching Python's date.weekday().
_ALL_WEEKDAYS = 127


class DeadHourWindow(BaseModel):
    """One suggested offer window: a weekday plus a wall-clock hour range.

    `start_hour`/`end_hour` are LOCAL hours in the restaurant's own timezone,
    half-open [start, end) — (14, 17) means 2pm up to but not including 5pm, and
    reads to an owner as "2-5pm". Both are always in 0..23 so the suggestion is
    directly expressible as an offer window's wall-clock start/end times.

    `median_revenue` is what a TYPICAL such window actually took: the median of
    the per-day window totals across `sample_size` same-weekdays. Median, not
    mean, for the reason daily_report_service._compare uses one — a single
    party booking must not redefine "usual".

    `day_median_revenue` is the same statistic over the whole trading day, and
    exists so the UI can render the window figure at scale. "Rs 1,240" means
    nothing on its own; "Rs 1,240 of a typical Rs 9,800 Tuesday" is a decision.
    """

    weekday: int          # Python weekday(): 0=Monday … 6=Sunday
    weekday_label: str    # "Tuesday"
    start_hour: int
    end_hour: int
    median_revenue: Decimal
    day_median_revenue: Decimal
    sample_size: int


class DeadHoursSuggestions(BaseModel):
    """The whole GET /admin/offers/suggestions payload.

    An envelope rather than a bare list, so the admin page can render an honest
    empty state. `windows == []` means "we refuse to guess", and the thresholds
    that produced that refusal (`lookback_weeks`, `min_samples`) are returned
    with it so the UI can say WHY instead of showing a blank panel.
    """

    currency: str
    timezone: str
    lookback_weeks: int
    min_samples: int
    window_hours: int
    windows: list[DeadHourWindow]


# ── Offer window CRUD ─────────────────────────────────────────────────────────

class _OfferWindowBase(BaseModel):
    """Shared validation for create and update.

    The two cross-field rules live here rather than in the router or service, so
    a malformed offer is rejected before any code that could act on it runs.
    """

    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=60)]
    discount_type: OfferDiscountType
    # PERCENT is additionally capped at 100 by the validator below and by
    # ck_offer_windows_percent_max. A percentage above 100 would produce a
    # negative price, which is the never-surge rule read backwards.
    discount_value: Annotated[Decimal, Field(gt=Decimal("0"), decimal_places=2)]
    # REQUIRED for FIXED (see the validator). Optional for PERCENT — but never
    # inert: pricing_service.apply honours it for both discount types.
    min_resulting_price: Annotated[Decimal, Field(gt=Decimal("0"), decimal_places=2)] | None = None
    start_time: time
    end_time: time
    weekday_mask: Annotated[int, Field(ge=1, le=_ALL_WEEKDAYS)]
    applies_to: OfferAppliesTo
    category_id: uuid.UUID | None = None
    product_ids: list[uuid.UUID] = Field(default_factory=list)
    is_enabled: bool = False

    @model_validator(mode="after")
    def _check(self) -> "_OfferWindowBase":
        if self.discount_type is OfferDiscountType.PERCENT and self.discount_value > Decimal("100"):
            raise ValueError("A percentage discount cannot exceed 100 — offers may only reduce a price")
        if self.discount_type is OfferDiscountType.FIXED and self.min_resulting_price is None:
            raise ValueError(
                "min_resulting_price is required for a fixed-amount discount — "
                "state the lowest price an item may fall to"
            )
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time — an offer window cannot wrap past midnight")
        if self.applies_to is OfferAppliesTo.CATEGORY:
            if self.category_id is None:
                raise ValueError("category_id is required when applies_to is CATEGORY")
            if self.product_ids:
                raise ValueError("product_ids must be empty when applies_to is CATEGORY")
        else:
            if self.category_id is not None:
                raise ValueError("category_id must be omitted when applies_to is PRODUCTS")
            if not self.product_ids:
                raise ValueError("product_ids must list at least one product when applies_to is PRODUCTS")
            if len(set(self.product_ids)) != len(self.product_ids):
                raise ValueError("product_ids must not contain duplicates")
        return self


class OfferWindowCreate(_OfferWindowBase):
    pass


class OfferWindowUpdate(_OfferWindowBase):
    """A full replacement of the offer's configuration.

    Deliberately not a partial patch: the fields constrain each other (a FIXED
    discount needs a floor, a CATEGORY offer must not carry product_ids), and
    validating a half-specified offer against the stored remainder is how a
    money-path rule quietly stops holding. The admin form always submits the
    whole offer.
    """


class OfferWindowPublic(BaseModel):
    """Admin-facing view of one offer. ADMIN-only — never sent to a customer."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    discount_type: OfferDiscountType
    discount_value: Decimal
    min_resulting_price: Decimal | None
    start_time: time
    end_time: time
    weekday_mask: int
    applies_to: OfferAppliesTo
    category_id: uuid.UUID | None
    product_ids: list[uuid.UUID]
    is_enabled: bool
    # True iff the window is running at the moment this response was built, in
    # the restaurant's own timezone. Lets the admin list show "live now" without
    # the browser re-deriving it from a clock in a different timezone.
    is_live_now: bool
    created_at: datetime
    updated_at: datetime
