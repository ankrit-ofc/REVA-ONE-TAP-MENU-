"""
Read-only aggregation for the Nightly One-Liner — the daily summary email an
owner gets at closing time.

Everything here is plain SQL over existing invoice/order data. No writes, no
state transitions, no forecasting. The send ledger and dispatch live in
daily_report_email.py and jobs/nightly_report.py; this module only computes.

Two conventions worth stating once, because they are the difference between
numbers that agree and numbers that quietly don't:

1. EVERY metric is anchored on the PAID INVOICE's created_at — "today's
   business" means bills settled today. There is no paid_at column (see
   dashboard_service.revenue_today), so created_at is the payment instant for
   quick-bill and the bill instant for the two-step flow. Anchoring some
   metrics on orders.created_at instead would put an order opened at 23:50 and
   paid at 00:10 on different days for different numbers, and average order
   value would stop being revenue / orders.

2. Day boundaries are LOCAL to the restaurant, never UTC. Each local midnight
   is computed separately rather than by adding 24h, so a DST transition can
   never produce a 23- or 25-hour "day" for tenants outside Nepal.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from statistics import median
from zoneinfo import ZoneInfo

from sqlalchemy import Date, and_, cast, exists, func, select
from sqlalchemy.orm import Session

from app.models.enums import InvoiceStatus, OrderItemStatus
from app.models.invoice import Invoice
from app.models.order import Order, OrderItem
from app.models.restaurant import Restaurant
from app.models.table import TableSession
from app.services import menu_service

_TWO_PLACES = Decimal("0.01")

# Baseline window: the last 8 same-weekdays, excluding today. Eight weeks is long
# enough that one outlier (a party booking, a festival) cannot move the median,
# and short enough to still track the season a restaurant is actually in.
_BASELINE_LOOKBACK_WEEKS = 8
# Below this many usable same-weekdays we show no comparison at all rather than
# a figure the owner would reasonably read as meaningful.
_BASELINE_MIN_SAMPLES = 4

# The "quietest stretch" bucket width, in hours.
_QUIET_BUCKET_HOURS = 2

# Items that never count toward a bill (mirrors dashboard_service._NON_BILLABLE).
_NON_BILLABLE = (OrderItemStatus.CANCELLED, OrderItemStatus.PENDING_APPROVAL)


def _q(value: Decimal) -> Decimal:
    return value.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


# ── Result shapes ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Comparison:
    """A metric measured against the median of recent same-weekdays.

    `pct` is None whenever we refuse to compare — too little history, or a zero
    baseline. The renderer must show nothing at all in that case, never "0%".
    """
    baseline: Decimal | None
    pct: float | None
    sample_size: int


@dataclass(frozen=True)
class QuietStretch:
    start_hour: int
    end_hour: int
    revenue: Decimal


@dataclass(frozen=True)
class DailyReport:
    restaurant_name: str
    currency: str
    local_date: date
    weekday_label: str          # "Tuesday" — used verbatim as "your usual Tuesday"
    revenue: Decimal
    orders: int
    aov: Decimal
    revenue_cmp: Comparison
    orders_cmp: Comparison
    aov_cmp: Comparison
    best_seller_name: str | None
    best_seller_qty: int
    quiet: QuietStretch | None
    browsed_no_order: int

    @property
    def has_sales(self) -> bool:
        return self.orders > 0


# ── Timezone / day boundaries ─────────────────────────────────────────────────

def restaurant_tz(db: Session, restaurant_id: uuid.UUID) -> ZoneInfo:
    """The restaurant's configured display timezone (default Asia/Kathmandu).

    Same fallback as dashboard_service._restaurant_tz: an unparseable value must
    never take the scheduler down for every other tenant.
    """
    settings = menu_service.get_or_create_settings(db, restaurant_id)
    try:
        return ZoneInfo(settings.timezone)
    except Exception:  # noqa: BLE001 — bad tz string is config error, not fatal
        return ZoneInfo("Asia/Kathmandu")


def day_bounds_utc(tz: ZoneInfo, local_day: date) -> tuple[datetime, datetime]:
    """[start, end) of one LOCAL calendar day, as UTC instants.

    Both midnights are constructed independently — adding timedelta(days=1) to
    the start would be wrong across a DST boundary.
    """
    start_local = datetime.combine(local_day, time(0, 0), tzinfo=tz)
    end_local = datetime.combine(local_day + timedelta(days=1), time(0, 0), tzinfo=tz)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


# ── Core aggregates ───────────────────────────────────────────────────────────

def _revenue_and_orders(
    db: Session, restaurant_id: uuid.UUID, start_utc: datetime, end_utc: datetime
) -> tuple[Decimal, int]:
    """Settled revenue and distinct bills for one window.

    COUNT(DISTINCT order_id) rather than COUNT(*): an order that was voided and
    re-invoiced would otherwise count twice and deflate average order value.
    """
    row = db.execute(
        select(
            func.coalesce(func.sum(Invoice.total), 0),
            func.count(func.distinct(Invoice.order_id)),
        ).where(
            Invoice.restaurant_id == restaurant_id,
            Invoice.status == InvoiceStatus.PAID,
            Invoice.created_at >= start_utc,
            Invoice.created_at < end_utc,
        )
    ).one()
    return Decimal(row[0]), int(row[1] or 0)


def _same_weekday_history(
    db: Session,
    restaurant_id: uuid.UUID,
    tz: ZoneInfo,
    local_day: date,
) -> list[tuple[Decimal, int]]:
    """(revenue, orders) for each of the recent same-weekdays, most recent first.

    Days on which the restaurant settled no bills are dropped: a closed Tuesday
    is not a quiet Tuesday, and averaging it in would drag the baseline toward
    zero and manufacture a triumphant "+400%" on the next ordinary day.
    """
    window_start_local = local_day - timedelta(weeks=_BASELINE_LOOKBACK_WEEKS)
    window_start_utc, _ = day_bounds_utc(tz, window_start_local)
    today_start_utc, _ = day_bounds_utc(tz, local_day)

    local_date_col = cast(func.timezone(str(tz), Invoice.created_at), Date)
    rows = db.execute(
        select(
            local_date_col.label("local_day"),
            func.sum(Invoice.total).label("revenue"),
            func.count(func.distinct(Invoice.order_id)).label("orders"),
        )
        .where(
            Invoice.restaurant_id == restaurant_id,
            Invoice.status == InvoiceStatus.PAID,
            Invoice.created_at >= window_start_utc,
            Invoice.created_at < today_start_utc,
        )
        .group_by(local_date_col)
        .order_by(local_date_col.desc())
    ).all()

    target_weekday = local_day.weekday()
    return [
        (Decimal(r.revenue), int(r.orders))
        for r in rows
        if r.local_day.weekday() == target_weekday and int(r.orders) > 0
    ]


def _compare(today: Decimal, baseline_values: list[Decimal]) -> Comparison:
    """Today against the median of its recent same-weekdays.

    Median, not mean, for the same reason we drop closed days: one unusually big
    Tuesday should not redefine "usual".
    """
    sample_size = len(baseline_values)
    if sample_size < _BASELINE_MIN_SAMPLES:
        return Comparison(baseline=None, pct=None, sample_size=sample_size)

    baseline = Decimal(str(median(baseline_values)))
    if baseline <= 0:
        return Comparison(baseline=None, pct=None, sample_size=sample_size)

    pct = float((today - baseline) / baseline * 100)
    return Comparison(baseline=_q(baseline), pct=pct, sample_size=sample_size)


def _best_seller(
    db: Session, restaurant_id: uuid.UUID, start_utc: datetime, end_utc: datetime
) -> tuple[str | None, int]:
    """Top product by quantity across bills settled in the window."""
    row = db.execute(
        select(
            func.min(OrderItem.product_name).label("product_name"),
            func.sum(OrderItem.quantity).label("qty"),
        )
        .join(Invoice, Invoice.order_id == OrderItem.order_id)
        .where(
            OrderItem.restaurant_id == restaurant_id,
            OrderItem.status.notin_(_NON_BILLABLE),
            Invoice.status == InvoiceStatus.PAID,
            Invoice.created_at >= start_utc,
            Invoice.created_at < end_utc,
        )
        .group_by(OrderItem.product_id)
        .order_by(func.sum(OrderItem.quantity).desc())
        .limit(1)
    ).first()

    if row is None or not row.qty:
        return None, 0
    return row.product_name, int(row.qty)


def _quietest_stretch(
    db: Session, restaurant_id: uuid.UUID, tz: ZoneInfo, start_utc: datetime, end_utc: datetime
) -> QuietStretch | None:
    """The weakest 2-hour window by revenue, BOUNDED BY TRADING HOURS.

    Without the bound this metric is worthless: the quietest two hours of any
    restaurant's day are always the ones it is closed, and the email would say
    "03:00-05:00" forever. So the candidate buckets run only from the one
    containing the first settled bill to the one containing the last. Fewer
    than two candidates means the day was too short for "quietest" to mean
    anything, and we omit the line entirely.
    """
    local_ts = func.timezone(str(tz), Invoice.created_at)
    bucket = (
        func.floor(func.extract("hour", local_ts) / _QUIET_BUCKET_HOURS) * _QUIET_BUCKET_HOURS
    )
    rows = db.execute(
        select(bucket.label("bucket"), func.sum(Invoice.total).label("revenue"))
        .where(
            Invoice.restaurant_id == restaurant_id,
            Invoice.status == InvoiceStatus.PAID,
            Invoice.created_at >= start_utc,
            Invoice.created_at < end_utc,
        )
        .group_by(bucket)
    ).all()

    if not rows:
        return None

    by_bucket = {int(r.bucket): Decimal(r.revenue) for r in rows}
    first, last = min(by_bucket), max(by_bucket)
    candidates = list(range(first, last + 1, _QUIET_BUCKET_HOURS))
    if len(candidates) < 2:
        return None

    # Buckets inside trading hours with no bills are real lulls — worth zero, not
    # missing — so fill them before taking the minimum. Ties resolve to the
    # earliest window, which reads more naturally than a late one.
    weakest = min(candidates, key=lambda b: (by_bucket.get(b, Decimal("0")), b))
    return QuietStretch(
        start_hour=weakest,
        end_hour=(weakest + _QUIET_BUCKET_HOURS) % 24,
        revenue=_q(by_bucket.get(weakest, Decimal("0"))),
    )


def _browsed_without_ordering(
    db: Session, restaurant_id: uuid.UUID, start_utc: datetime, end_utc: datetime
) -> int:
    """
    APPROXIMATE count of table sessions that opened the menu and never ordered.

    Read the caveat before using this number for anything but a soft nudge:

    - `orders` has NO session_id — only table_id — so a session cannot be joined
      to the orders placed during it. We infer the link by time: an order on the
      same table between the session's creation and its expiry/invalidation.
    - session_service.create_or_reuse_session returns the EXISTING active session
      for a table (TABLE_SESSION_TTL_HOURS = 4), so several consecutive parties
      at one table share a single row. Eight parties across a dinner service may
      produce two sessions, not eight.
    - A session row means "QR scanned", which is a proxy for "opened the menu",
      and re-scans are invisible.

    Net effect: this UNDERCOUNTS, unpredictably, and always in the same
    direction. The email must therefore hedge it ("~N") and never present it as
    a precise figure. Making it exact needs orders.session_id — a schema and
    write-path change, tracked as separate work.
    """
    session_end = func.least(
        TableSession.expires_at,
        func.coalesce(TableSession.invalidated_at, TableSession.expires_at),
    )
    ordered = exists(
        select(Order.id).where(
            Order.restaurant_id == restaurant_id,
            Order.table_id == TableSession.table_id,
            Order.created_at >= TableSession.created_at,
            Order.created_at < session_end,
        )
    )
    count = db.scalar(
        select(func.count(TableSession.id)).where(
            and_(
                TableSession.restaurant_id == restaurant_id,
                TableSession.created_at >= start_utc,
                TableSession.created_at < end_utc,
                ~ordered,
            )
        )
    )
    return int(count or 0)


# ── Entry point ───────────────────────────────────────────────────────────────

def build_report(
    db: Session, restaurant_id: uuid.UUID, local_day: date | None = None
) -> DailyReport:
    """Assemble the whole report for one restaurant and one LOCAL day.

    `local_day` defaults to today in the restaurant's timezone; the test-send
    endpoint passes it explicitly so an owner can preview a day that has data.
    """
    tz = restaurant_tz(db, restaurant_id)
    settings = menu_service.get_or_create_settings(db, restaurant_id)
    restaurant = db.get(Restaurant, restaurant_id)

    if local_day is None:
        local_day = datetime.now(tz).date()
    start_utc, end_utc = day_bounds_utc(tz, local_day)

    revenue, orders = _revenue_and_orders(db, restaurant_id, start_utc, end_utc)
    aov = _q(revenue / orders) if orders else Decimal("0.00")

    history = _same_weekday_history(db, restaurant_id, tz, local_day)
    hist_revenue = [rev for rev, _ in history]
    hist_orders = [Decimal(cnt) for _, cnt in history]
    hist_aov = [rev / cnt for rev, cnt in history if cnt]

    best_name, best_qty = _best_seller(db, restaurant_id, start_utc, end_utc)

    return DailyReport(
        restaurant_name=restaurant.name if restaurant else "Your restaurant",
        currency=settings.currency,
        local_date=local_day,
        weekday_label=local_day.strftime("%A"),
        revenue=_q(revenue),
        orders=orders,
        aov=aov,
        revenue_cmp=_compare(revenue, hist_revenue),
        orders_cmp=_compare(Decimal(orders), hist_orders),
        aov_cmp=_compare(aov, hist_aov),
        best_seller_name=best_name,
        best_seller_qty=best_qty,
        quiet=_quietest_stretch(db, restaurant_id, tz, start_utc, end_utc),
        browsed_no_order=_browsed_without_ordering(db, restaurant_id, start_utc, end_utc),
    )
