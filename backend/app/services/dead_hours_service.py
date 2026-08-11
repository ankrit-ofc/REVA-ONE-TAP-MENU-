"""
Dead Hours suggestions — the "data-suggested" half of the Dead Hours Engine.

Read-only. Plain SQL over PAID invoices, aggregated in Python. No writes, no
state transitions, no scheduler, and — deliberately — no path by which an offer
can come into existence. This module PROPOSES; an admin POST is the only thing
that ever creates an offer window.

It reuses, rather than reinvents, the three judgements the Nightly One-Liner
already settled (daily_report_service):

1. Money is anchored on the PAID INVOICE's created_at — "business done" means
   bills settled, not orders opened.
2. Day and hour boundaries are LOCAL to the restaurant, never UTC. A weekday
   derived from a UTC timestamp flips at 18:15 local in Kathmandu, which would
   silently file Tuesday evening trade under Monday.
3. A day on which the restaurant settled nothing is a CLOSED day, not a quiet
   one, and is dropped before any median is taken. Averaging closed Tuesdays in
   would drag the baseline toward zero and make every ordinary Tuesday look
   like a triumph.

Two judgements are new here, and both exist to stop the feature producing
confident nonsense:

- Candidate windows are bounded by that WEEKDAY'S OWN trading hours. The
  quietest three hours of any restaurant's week are always the ones it is shut,
  and a suggestion of "create an offer for 3-6am" is worse than no suggestion.
  Trading hours are computed per weekday because a Sunday brunch service and a
  Tuesday dinner service are not the same business.
- A suggested window must be EXPRESSIBLE AS A REAL OFFER. Offer windows store
  wall-clock start/end times and do not wrap past midnight, so a window ending
  after 23:00 is never proposed. The engine must not suggest something the
  domain would reject.
"""

import uuid
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from statistics import median
from zoneinfo import ZoneInfo

from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import Session

from app.models.enums import InvoiceStatus
from app.models.invoice import Invoice
from app.schemas.offer import DeadHoursSuggestions, DeadHourWindow
from app.services import menu_service
from app.services.daily_report_service import day_bounds_utc, restaurant_tz

_TWO_PLACES = Decimal("0.01")

# Same 8-week lookback as the nightly report's baseline: long enough that one
# festival cannot move a median, short enough to track the season the
# restaurant is actually trading in.
_LOOKBACK_WEEKS = 8

# Below this many usable same-weekdays we show NOTHING rather than a figure an
# owner would reasonably read as meaningful. Mirrors
# daily_report_service._BASELINE_MIN_SAMPLES; a restaurant open three weeks
# gets an empty state, not noise.
_MIN_SAMPLES = 4

# Width of a suggested window. Three hours is the shape of the thing being
# proposed ("2-5pm"), and a window narrower than a meal service is not an offer
# a regular can plan around.
_WINDOW_HOURS = 3

# Offer windows cannot wrap past midnight, so a window may not end after 23:00.
_LATEST_END_HOUR = 23

_MAX_SUGGESTIONS = 3

# Spelled out rather than taken from calendar.day_name or strftime("%A"), both
# of which follow the process locale. The label is part of an API response and
# must not change because a container's LANG did.
_WEEKDAY_LABELS = (
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
)


def _q(value: Decimal) -> Decimal:
    return value.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


# ── Data ──────────────────────────────────────────────────────────────────────

def _hourly_revenue(
    db: Session,
    restaurant_id: uuid.UUID,
    tz: ZoneInfo,
    start_utc: datetime,
    end_utc: datetime,
) -> dict[date, dict[int, Decimal]]:
    """{local_date: {local_hour: revenue}} for PAID invoices in the window.

    Hours with no bills are simply ABSENT from the inner dict. Whether a missing
    hour means "a lull worth zero" or "outside trading hours" is not decidable
    here — it depends on the weekday's trading span — so that call is left to
    _weakest_window, which knows the span.
    """
    local_ts = func.timezone(str(tz), Invoice.created_at)
    local_day = cast(local_ts, Date)
    local_hour = func.extract("hour", local_ts)

    rows = db.execute(
        select(
            local_day.label("day"),
            local_hour.label("hour"),
            func.sum(Invoice.total).label("revenue"),
        )
        .where(
            Invoice.restaurant_id == restaurant_id,
            Invoice.status == InvoiceStatus.PAID,
            Invoice.created_at >= start_utc,
            Invoice.created_at < end_utc,
        )
        .group_by(local_day, local_hour)
    ).all()

    out: dict[date, dict[int, Decimal]] = {}
    for row in rows:
        out.setdefault(row.day, {})[int(row.hour)] = Decimal(row.revenue)
    return out


# ── Analysis ──────────────────────────────────────────────────────────────────

def _weakest_window(
    days: list[dict[int, Decimal]],
) -> tuple[int, int, Decimal] | None:
    """The quietest expressible window for one weekday: (start, end, median).

    `days` is one {hour: revenue} map per trading day, all sharing a weekday.

    Returns None when the weekday cannot support the question: no sales at all,
    or a trading span too short to hold two distinct candidate windows. With
    only one candidate the "quietest stretch" would be the entire trading day,
    which is not an insight.
    """
    hours_with_sales = {h for day in days for h, revenue in day.items() if revenue > 0}
    if not hours_with_sales:
        return None

    first, last = min(hours_with_sales), max(hours_with_sales)
    # A window must fit inside trading hours AND end by _LATEST_END_HOUR.
    last_start = min(last + 1 - _WINDOW_HOURS, _LATEST_END_HOUR - _WINDOW_HOURS)
    if last_start - first + 1 < 2:
        return None

    best: tuple[int, int, Decimal] | None = None
    for start in range(first, last_start + 1):
        end = start + _WINDOW_HOURS
        # An hour INSIDE trading hours with no bills is a real lull worth zero,
        # not missing data — .get(h, 0) is the whole point of bounding the span
        # first. The median is taken over per-day window totals (not over
        # per-hour medians) so the figure reported is a thing that actually
        # happened on some day, and the statistic used to rank windows is the
        # same one shown to the owner.
        totals = [
            sum((day.get(h, Decimal("0")) for h in range(start, end)), Decimal("0"))
            for day in days
        ]
        score = Decimal(str(median(totals)))
        # Strict <, so ties resolve to the EARLIEST window — an owner reads an
        # earlier dead stretch as the more natural one to fill.
        if best is None or score < best[2]:
            best = (start, end, score)
    return best


def suggest(db: Session, restaurant_id: uuid.UUID) -> DeadHoursSuggestions:
    """Up to _MAX_SUGGESTIONS quietest windows for this restaurant, weakest first.

    At most one window per weekday: three suggestions all landing on Tuesday
    would be one insight wearing three hats. Ranking across weekdays instead
    gives the owner genuinely different windows to choose between.
    """
    tz = restaurant_tz(db, restaurant_id)
    settings = menu_service.get_or_create_settings(db, restaurant_id)

    today_local = datetime.now(tz).date()
    lookback_start_local = today_local - timedelta(weeks=_LOOKBACK_WEEKS)
    start_utc, _ = day_bounds_utc(tz, lookback_start_local)
    # Today is excluded: a part-finished day is not a sample, and including it
    # would make the suggestion drift over the course of every afternoon.
    end_utc, _ = day_bounds_utc(tz, today_local)

    by_day = _hourly_revenue(db, restaurant_id, tz, start_utc, end_utc)

    by_weekday: dict[int, list[dict[int, Decimal]]] = {}
    for day, hours in by_day.items():
        if not any(revenue > 0 for revenue in hours.values()):
            continue  # closed (or fully refunded) day — not a quiet day
        by_weekday.setdefault(day.weekday(), []).append(hours)

    windows: list[DeadHourWindow] = []
    for weekday, days in by_weekday.items():
        if len(days) < _MIN_SAMPLES:
            continue
        best = _weakest_window(days)
        if best is None:
            continue
        start_hour, end_hour, window_median = best
        day_totals = [sum(day.values(), Decimal("0")) for day in days]
        windows.append(DeadHourWindow(
            weekday=weekday,
            weekday_label=_WEEKDAY_LABELS[weekday],
            start_hour=start_hour,
            end_hour=end_hour,
            median_revenue=_q(window_median),
            day_median_revenue=_q(Decimal(str(median(day_totals)))),
            sample_size=len(days),
        ))

    # Quietest first. weekday/start_hour only break ties, so the ordering is
    # total and the endpoint is deterministic for a fixed dataset.
    windows.sort(key=lambda w: (w.median_revenue, w.weekday, w.start_hour))

    return DeadHoursSuggestions(
        currency=settings.currency,
        timezone=str(tz),
        lookback_weeks=_LOOKBACK_WEEKS,
        min_samples=_MIN_SAMPLES,
        window_hours=_WINDOW_HOURS,
        windows=windows[:_MAX_SUGGESTIONS],
    )
