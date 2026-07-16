"""
Invoice generation service.

generate_invoice:
  - Only allowed when the order is MEAL_FINISHED.
  - Blocks if there is already a DRAFT, PENDING_PAYMENT, or PAID invoice
    on the order (a FAILED or VOID invoice does NOT block a new one).
  - Computes subtotal from order-item snapshots: qty × (unit_price + addon_prices).
  - Tax is computed per-line on the pre-discount subtotal.
  - Invoice-level discount (flat amount or percent of subtotal) is applied
    after computing tax; validated >= 0 and not exceeding subtotal.
  - All arithmetic uses Decimal; final values are quantized to 2 decimal places.
  - Invoice number is a gapless per-restaurant sequence: INV-YYYY-NNNN.
  - A FOR UPDATE lock on the order serialises concurrent generation attempts.
"""

import uuid
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.audit_log import AuditLog
from app.models.enums import InvoiceStatus, OrderItemStatus, OrderStatus, Role
from app.models.invoice import Invoice
from app.models.order import Order, OrderItem
from app.models.restaurant import Restaurant, RestaurantSettings
from app.models.table import Table
from app.services import numbering_service
from app.services.payment_state import InvoiceError

_TWO_PLACES = Decimal("0.01")


def _q(value: Decimal) -> Decimal:
    return value.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


def build_receipt(db: Session, restaurant_id: uuid.UUID, invoice_id: uuid.UUID) -> dict:
    """Assemble an itemized receipt (for thermal printing) from an invoice +
    the order's item snapshots. Totals are the authoritative invoice values;
    per-line amounts mirror the generate_invoice math for display."""
    invoice = db.execute(
        select(Invoice).where(
            Invoice.id == invoice_id,
            Invoice.restaurant_id == restaurant_id,
        )
    ).scalar_one_or_none()
    if invoice is None:
        raise InvoiceError("Invoice not found", status_code=404)

    order = db.execute(
        select(Order).where(
            Order.id == invoice.order_id,
            Order.restaurant_id == restaurant_id,
        )
    ).scalar_one_or_none()
    if order is None:
        raise InvoiceError("Order not found", status_code=404)

    items = db.execute(
        select(OrderItem)
        .where(
            OrderItem.order_id == invoice.order_id,
            OrderItem.status.notin_([
                OrderItemStatus.CANCELLED, OrderItemStatus.PENDING_APPROVAL,
            ]),
        )
        .options(selectinload(OrderItem.addons))
    ).scalars().all()

    restaurant_name = db.scalar(
        select(Restaurant.name).where(Restaurant.id == restaurant_id)
    ) or ""
    table_name = db.scalar(select(Table.name).where(Table.id == order.table_id)) or ""
    settings = db.execute(
        select(RestaurantSettings).where(RestaurantSettings.restaurant_id == restaurant_id)
    ).scalar_one_or_none()
    currency = settings.currency if settings is not None else "NPR"

    lines: list[dict] = []
    for item in items:
        addon_sum = sum((a.addon_price for a in item.addons), Decimal("0"))
        line_total = _q(item.quantity * (item.unit_price + addon_sum))
        lines.append({
            "product_name": item.product_name,
            "variant_name": item.variant_name,
            "quantity": item.quantity,
            "unit_price": item.unit_price,
            "line_total": line_total,
            "special_instructions": item.special_instructions,
            "addons": [
                {"addon_name": a.addon_name, "addon_price": a.addon_price}
                for a in item.addons
            ],
        })

    return {
        "invoice_number": invoice.invoice_number,
        "status": invoice.status,
        "payment_method": invoice.payment_method,
        "currency": currency,
        "restaurant_name": restaurant_name,
        "table_name": table_name,
        "order_number": order.order_number,
        "created_at": invoice.created_at,
        "items": lines,
        "subtotal": invoice.subtotal,
        "discount": invoice.discount,
        "tax_total": invoice.tax_total,
        "total": invoice.total,
    }


def generate_invoice(
    db: Session,
    restaurant_id: uuid.UUID,
    order_id: uuid.UUID,
    discount_type: str,      # "flat" | "percent"
    discount_value: Decimal,
    actor_type: str,
    actor_id: uuid.UUID,
) -> Invoice:
    """
    Generates a DRAFT invoice for a MEAL_FINISHED order.
    Uses FOR UPDATE on the order to serialise concurrent calls.
    """
    # Waiters may only handle billing when the restaurant has enabled it.
    if actor_type == Role.WAITER.value:
        settings = db.execute(
            select(RestaurantSettings).where(
                RestaurantSettings.restaurant_id == restaurant_id
            )
        ).scalar_one_or_none()
        if settings is None or not settings.waiter_can_accept_payment:
            raise InvoiceError(
                "Waiters are not permitted to handle billing at this restaurant",
                status_code=403,
            )

    # Lock the order to prevent concurrent invoice generation
    order = db.execute(
        select(Order)
        .where(Order.id == order_id, Order.restaurant_id == restaurant_id)
        .with_for_update()
    ).scalar_one_or_none()
    if order is None:
        raise InvoiceError("Order not found", status_code=404)
    if order.status != OrderStatus.MEAL_FINISHED:
        raise InvoiceError(
            f"Invoice can only be generated for MEAL_FINISHED orders "
            f"(current status: {order.status.value})",
            status_code=409,
        )

    # Block if an active (non-terminal) invoice already exists
    _ACTIVE_STATUSES = [InvoiceStatus.DRAFT, InvoiceStatus.PENDING_PAYMENT, InvoiceStatus.PAID]
    existing = db.execute(
        select(Invoice).where(
            Invoice.order_id == order_id,
            Invoice.status.in_(_ACTIVE_STATUSES),
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise InvoiceError(
            f"Order already has an active invoice (status: {existing.status.value}). "
            "Void or wait for it to complete before generating a new one.",
            status_code=409,
        )

    # A batch still awaiting waiter approval must be approved or rejected before
    # billing (belt and braces on top of the MEAL_FINISHED transition guard).
    pending = db.scalar(
        select(OrderItem.id).where(
            OrderItem.order_id == order_id,
            OrderItem.restaurant_id == restaurant_id,
            OrderItem.status == OrderItemStatus.PENDING_APPROVAL,
        ).limit(1)
    )
    if pending is not None:
        raise InvoiceError(
            "Order has items awaiting approval — approve or reject them first",
            status_code=409,
        )

    # Load billable items (not cancelled, not awaiting approval) with their addons
    items = db.execute(
        select(OrderItem)
        .where(
            OrderItem.order_id == order_id,
            OrderItem.status.notin_([
                OrderItemStatus.CANCELLED, OrderItemStatus.PENDING_APPROVAL,
            ]),
        )
        .options(selectinload(OrderItem.addons))
    ).scalars().all()

    if not items:
        raise InvoiceError("No billable items on this order", status_code=400)

    # Compute subtotal and tax from snapshots — never from client-supplied values
    subtotal = Decimal("0")
    tax_total = Decimal("0")
    for item in items:
        addon_sum = sum(a.addon_price for a in item.addons)
        line_sub = item.quantity * (item.unit_price + addon_sum)
        line_tax = line_sub * item.tax_rate / Decimal("100")
        subtotal += line_sub
        tax_total += line_tax

    subtotal = _q(subtotal)
    tax_total = _q(tax_total)

    # Compute discount
    if discount_type == "percent":
        discount = _q(subtotal * discount_value / Decimal("100"))
    else:  # flat
        discount = _q(discount_value)

    if discount < Decimal("0"):
        raise InvoiceError("Discount cannot be negative", status_code=400)
    if discount > subtotal:
        raise InvoiceError(
            f"Discount ({discount}) cannot exceed subtotal ({subtotal})",
            status_code=400,
        )

    total = _q(subtotal - discount + tax_total)

    # Assign gapless invoice number: INV-YYYY-NNNN
    seq = numbering_service.next_number(db, restaurant_id, "invoice")
    year = datetime.now(timezone.utc).year
    invoice_number = f"INV-{year}-{seq:04d}"

    invoice = Invoice(
        id=uuid.uuid4(),
        restaurant_id=restaurant_id,
        order_id=order_id,
        invoice_number=invoice_number,
        status=InvoiceStatus.DRAFT,
        subtotal=subtotal,
        discount=discount,
        tax_total=tax_total,
        total=total,
    )
    db.add(invoice)

    db.add(AuditLog(
        id=uuid.uuid4(),
        restaurant_id=restaurant_id,
        actor_type=actor_type,
        actor_user_id=actor_id,
        entity_type="invoice",
        entity_id=invoice.id,
        action="INVOICE_GENERATED",
        previous_value=None,
        new_value={
            "invoice_number": invoice_number,
            "subtotal": str(subtotal),
            "discount": str(discount),
            "discount_type": discount_type,
            "tax_total": str(tax_total),
            "total": str(total),
        },
    ))

    db.commit()
    db.refresh(invoice)
    return invoice
