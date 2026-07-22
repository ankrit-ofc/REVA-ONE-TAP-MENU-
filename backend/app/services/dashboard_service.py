"""
Read-only aggregation service for the admin dashboard.

Everything here is plain SQL over existing order/invoice data — no forecasting,
no new writes, no state transitions. "Active order" reuses the exact OPEN-order
definition from order_service.list_open_orders; the running-tab math mirrors
invoice_service.generate_invoice (subtotal + per-line tax, no discount).
"""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import InvoiceStatus, OrderItemStatus
from app.models.invoice import Invoice
from app.models.order import Order, OrderItem
from app.schemas.dashboard import (
    ActiveTable,
    ActiveTableItem,
    ActiveTableOrder,
    OrdersThisWeek,
    RevenueToday,
    TopProduct,
    TopProducts,
)
from app.services import menu_service, order_service

_TWO_PLACES = Decimal("0.01")
_TOP_PRODUCTS_WINDOW_DAYS = 7
_TOP_PRODUCTS_LIMIT = 5

# Items that don't count toward a bill / a table's running tab.
_NON_BILLABLE = (OrderItemStatus.CANCELLED, OrderItemStatus.PENDING_APPROVAL)


def _q(value: Decimal) -> Decimal:
    return value.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


def _restaurant_tz(db: Session, restaurant_id: uuid.UUID) -> ZoneInfo:
    """The restaurant's configured display timezone (default Asia/Kathmandu)."""
    settings = menu_service.get_or_create_settings(db, restaurant_id)
    try:
        return ZoneInfo(settings.timezone)
    except Exception:
        return ZoneInfo("Asia/Kathmandu")


def _start_of_today_utc(tz: ZoneInfo) -> datetime:
    now_local = datetime.now(tz)
    start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    return start_local.astimezone(timezone.utc)


def _start_of_week_utc(tz: ZoneInfo) -> datetime:
    """Sunday 00:00 of the current week, in the restaurant tz, as UTC."""
    now_local = datetime.now(tz)
    today_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    # Python weekday(): Mon=0 … Sun=6.  Days since the most recent Sunday:
    days_since_sunday = (now_local.weekday() + 1) % 7
    start_local = today_local - timedelta(days=days_since_sunday)
    return start_local.astimezone(timezone.utc)


# ── A. Active Tables ──────────────────────────────────────────────────────────

def active_tables(db: Session, restaurant_id: uuid.UUID) -> list[ActiveTable]:
    """
    Tables that currently have at least one active (OPEN) order, longest-waiting
    first. "Active" is order_service.list_open_orders' exact predicate — a table
    is occupied iff it has an OPEN order (no separate table-session concept).
    """
    # Reuse the canonical OPEN-order query (already scoped, with table + items
    # eager-loaded). item.addons lazy-loads per item when the running tab is
    # computed below — open tables are few, so N+1 here is not a concern.
    orders = order_service.list_open_orders(db, restaurant_id)

    grouped: dict[uuid.UUID, dict] = {}
    for order in orders:
        billable = [i for i in order.items if i.status not in _NON_BILLABLE]
        visible = [i for i in order.items if i.status != OrderItemStatus.CANCELLED]

        order_total = Decimal("0")
        for item in billable:
            addon_sum = sum((a.addon_price for a in item.addons), Decimal("0"))
            line_sub = item.quantity * (item.unit_price + addon_sum)
            line_tax = line_sub * item.tax_rate / Decimal("100")
            order_total += line_sub + line_tax

        entry = grouped.setdefault(
            order.table_id,
            {
                "table_label": order.table.name,
                "orders": [],
                "total_amount": Decimal("0"),
                "earliest_placed_at": order.created_at,
            },
        )
        entry["orders"].append(
            ActiveTableOrder(
                order_id=order.id,
                order_number=order.order_number,
                status=order.status,
                placed_at=order.created_at,
                items=[
                    ActiveTableItem(name=i.product_name, quantity=i.quantity)
                    for i in visible
                ],
            )
        )
        entry["total_amount"] += order_total
        if order.created_at < entry["earliest_placed_at"]:
            entry["earliest_placed_at"] = order.created_at

    tables = [
        ActiveTable(
            table_id=table_id,
            table_label=data["table_label"],
            order_count=len(data["orders"]),
            earliest_placed_at=data["earliest_placed_at"],
            total_amount=_q(data["total_amount"]),
            orders=data["orders"],
        )
        for table_id, data in grouped.items()
    ]
    tables.sort(key=lambda t: t.earliest_placed_at)
    return tables


# ── B. Revenue Today ──────────────────────────────────────────────────────────

def revenue_today(db: Session, restaurant_id: uuid.UUID) -> RevenueToday:
    """
    Sum of PAID invoice totals dated today (restaurant tz). There is no paid_at
    column; invoice.created_at is the payment instant for quick-bill (create+pay
    in one call) and the bill instant for the two-step flow — see the endpoint doc.
    """
    tz = _restaurant_tz(db, restaurant_id)
    start_utc = _start_of_today_utc(tz)
    settings = menu_service.get_or_create_settings(db, restaurant_id)

    total = db.scalar(
        select(func.coalesce(func.sum(Invoice.total), 0)).where(
            Invoice.restaurant_id == restaurant_id,
            Invoice.status == InvoiceStatus.PAID,
            Invoice.created_at >= start_utc,
        )
    )
    return RevenueToday(amount=_q(Decimal(total)), currency=settings.currency)


# ── C. Orders This Week ───────────────────────────────────────────────────────

def orders_this_week(db: Session, restaurant_id: uuid.UUID) -> OrdersThisWeek:
    """Count of orders placed since Sunday 00:00 (restaurant tz)."""
    tz = _restaurant_tz(db, restaurant_id)
    start_utc = _start_of_week_utc(tz)
    count = db.scalar(
        select(func.count(Order.id)).where(
            Order.restaurant_id == restaurant_id,
            Order.created_at >= start_utc,
        )
    )
    return OrdersThisWeek(count=int(count or 0))


# ── D. Top-Selling Products ───────────────────────────────────────────────────

def top_products(db: Session, restaurant_id: uuid.UUID) -> TopProducts:
    """
    Top products by quantity sold over a rolling 7-day window (orders placed in
    the last 7 days), grouped by product, excluding cancelled/pending items.
    """
    since = datetime.now(timezone.utc) - timedelta(days=_TOP_PRODUCTS_WINDOW_DAYS)
    rows = db.execute(
        select(
            OrderItem.product_id,
            func.min(OrderItem.product_name).label("product_name"),
            func.sum(OrderItem.quantity).label("qty"),
        )
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            OrderItem.restaurant_id == restaurant_id,
            OrderItem.status.notin_(_NON_BILLABLE),
            Order.created_at >= since,
        )
        .group_by(OrderItem.product_id)
        .order_by(func.sum(OrderItem.quantity).desc())
        .limit(_TOP_PRODUCTS_LIMIT)
    ).all()

    return TopProducts(
        window_days=_TOP_PRODUCTS_WINDOW_DAYS,
        products=[
            TopProduct(product_name=r.product_name, quantity_sold=int(r.qty))
            for r in rows
        ],
    )
