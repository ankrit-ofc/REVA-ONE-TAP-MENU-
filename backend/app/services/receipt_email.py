"""
Emailed customer receipts, via Resend.

Two hard rules, both load-bearing:

1. This must never break billing. `send_receipt_safely` swallows everything —
   a Resend outage, a DNS failure, a bug in this module — and logs it. Payment
   has already committed by the time we are called; nothing here may undo it or
   surface an error to the counter.
2. It must work before Resend is configured. With RESEND_API_KEY empty the
   service logs what it WOULD have sent (invoice id + redacted recipient) and
   reports success, so the whole capture flow ships and is testable today. Same
   pattern as the SMTP fallback in email_service and the dark-by-default
   EXPO_ACCESS_TOKEN in config.

Receipt content is built from invoice_service.build_receipt — the exact data
behind GET /invoices/{id}/receipt. Totals are never re-derived here.
"""

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.customer import Customer
from app.models.invoice import Invoice
from app.services import invoice_service
from app.services.customer_service import redact_email

logger = logging.getLogger("app.receipt_email")


def send_receipt_safely(db: Session, restaurant_id: uuid.UUID, invoice_id: uuid.UUID) -> None:
    """
    Fire-and-forget wrapper. Call this from billing paths — never `send_receipt`
    directly — so a failure can only ever produce a log line.
    """
    try:
        send_receipt(db, restaurant_id, invoice_id)
    except Exception:  # noqa: BLE001 — a receipt must never fail a payment
        logger.exception("Receipt email failed for invoice=%s", invoice_id)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            logger.exception("Rollback after receipt failure also failed")


def send_receipt(db: Session, restaurant_id: uuid.UUID, invoice_id: uuid.UUID) -> bool:
    """
    Send the receipt for `invoice_id` to its linked customer, at most once.

    Returns True when a receipt was claimed and dispatched (including the
    dev/no-key path, which counts as sent), False when there was nothing to do —
    no linked customer, or already sent.

    The send-once guard is a row lock plus `receipt_sent_at`, stamped and
    committed BEFORE dispatch. Two concurrent callers cannot both get past it;
    the cost of that ordering is that a hard delivery failure is not retried,
    which is the right trade for money-adjacent mail.
    """
    invoice = db.execute(
        select(Invoice)
        .where(Invoice.id == invoice_id, Invoice.restaurant_id == restaurant_id)
        .with_for_update()
    ).scalar_one_or_none()

    if invoice is None:
        logger.warning("Receipt requested for unknown invoice=%s", invoice_id)
        return False

    if invoice.customer_id is None:
        return False  # nobody asked for a receipt on this bill

    if invoice.receipt_sent_at is not None:
        logger.info("Receipt already sent for invoice=%s — skipping", invoice_id)
        return False

    customer = db.execute(
        select(Customer).where(
            Customer.id == invoice.customer_id,
            Customer.restaurant_id == restaurant_id,
        )
    ).scalar_one_or_none()
    if customer is None or not customer.is_active:
        return False

    receipt = invoice_service.build_receipt(db, restaurant_id, invoice_id)

    # Claim the send before dispatching — see docstring.
    invoice.receipt_sent_at = datetime.now(timezone.utc)
    db.commit()

    subject = f"Your receipt from {receipt['restaurant_name']} ({receipt['invoice_number']})"
    _dispatch(
        to=customer.email,
        subject=subject,
        text_body=_render_text(receipt, customer.name),
        html_body=_render_html(receipt, customer.name),
        invoice_id=invoice_id,
    )
    return True


# ── Rendering ─────────────────────────────────────────────────────────────────

def _money(value: Decimal | str, currency: str) -> str:
    return f"{currency} {Decimal(str(value)):.2f}"


def _line_label(line: dict) -> str:
    label = line["product_name"]
    if line.get("variant_name"):
        label += f" ({line['variant_name']})"
    addons = line.get("addons") or []
    if addons:
        label += " + " + ", ".join(a["addon_name"] for a in addons)
    if line["quantity"] > 1:
        label = f"{line['quantity']}x {label}"
    return label


def _render_text(receipt: dict, name: str | None) -> str:
    currency = receipt["currency"]
    greeting = f"Hi {name}," if name else "Hi,"
    lines = [
        greeting,
        "",
        f"Thanks for dining at {receipt['restaurant_name']}.",
        f"Receipt {receipt['invoice_number']} — table {receipt['table_name']}, "
        f"order #{receipt['order_number']}",
        "",
    ]
    for line in receipt["items"]:
        lines.append(f"  {_line_label(line)}  {_money(line['line_total'], currency)}")
    lines += [
        "",
        f"  Subtotal   {_money(receipt['subtotal'], currency)}",
    ]
    if Decimal(str(receipt["discount"])) > 0:
        lines.append(f"  Discount  -{_money(receipt['discount'], currency)}")
    lines += [
        f"  Tax        {_money(receipt['tax_total'], currency)}",
        f"  TOTAL      {_money(receipt['total'], currency)}",
        "",
        "We hope to see you again soon.",
        "",
        "You're receiving this because you asked for your receipt by email. "
        "You can unsubscribe at any time by replying to this message.",
    ]
    return "\n".join(lines)


def _render_html(receipt: dict, name: str | None) -> str:
    currency = receipt["currency"]
    greeting = f"Hi {name}," if name else "Hi,"
    rows = "".join(
        f"<tr><td>{_esc(_line_label(line))}</td>"
        f"<td align='right'>{_esc(_money(line['line_total'], currency))}</td></tr>"
        for line in receipt["items"]
    )
    discount_row = ""
    if Decimal(str(receipt["discount"])) > 0:
        discount_row = (
            f"<tr><td>Discount</td><td align='right'>"
            f"-{_esc(_money(receipt['discount'], currency))}</td></tr>"
        )
    return (
        f"<p>{_esc(greeting)}</p>"
        f"<p>Thanks for dining at <strong>{_esc(receipt['restaurant_name'])}</strong>.</p>"
        f"<p>Receipt {_esc(receipt['invoice_number'])} — table {_esc(receipt['table_name'])}, "
        f"order #{_esc(str(receipt['order_number']))}</p>"
        f"<table cellpadding='4'>{rows}"
        f"<tr><td>Subtotal</td><td align='right'>"
        f"{_esc(_money(receipt['subtotal'], currency))}</td></tr>"
        f"{discount_row}"
        f"<tr><td>Tax</td><td align='right'>"
        f"{_esc(_money(receipt['tax_total'], currency))}</td></tr>"
        f"<tr><td><strong>Total</strong></td><td align='right'><strong>"
        f"{_esc(_money(receipt['total'], currency))}</strong></td></tr></table>"
        f"<p>We hope to see you again soon.</p>"
        f"<p style='font-size:12px;color:#666'>You're receiving this because you asked "
        f"for your receipt by email. You can unsubscribe at any time by replying to "
        f"this message.</p>"
    )


def _esc(value: str) -> str:
    """Escape user-controlled text (product names, customer name) for HTML."""
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ── Transport ─────────────────────────────────────────────────────────────────

def _dispatch(
    to: str,
    subject: str,
    text_body: str,
    html_body: str,
    invoice_id: uuid.UUID,
) -> None:
    """
    Hand the message to Resend, or log it when no key is configured.

    Never raises: the caller has already committed the payment and stamped the
    send. Recipient is redacted in every log line (PII rule).
    """
    if not settings.RESEND_API_KEY.strip():
        logger.info(
            "RECEIPT EMAIL (not sent — RESEND_API_KEY unset) invoice=%s to=%s subject=%s",
            invoice_id,
            redact_email(to),
            subject,
        )
        return

    try:
        response = httpx.post(
            settings.RESEND_API_URL,
            headers={
                "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "from": settings.RESEND_FROM,
                "to": [to],
                "subject": subject,
                "text": text_body,
                "html": html_body,
            },
            timeout=10,
        )
        if response.status_code >= 400:
            logger.error(
                "Resend rejected receipt invoice=%s to=%s status=%s",
                invoice_id,
                redact_email(to),
                response.status_code,
            )
            return
        logger.info(
            "Receipt emailed invoice=%s to=%s", invoice_id, redact_email(to)
        )
    except Exception:  # noqa: BLE001 — delivery must never break billing
        logger.exception(
            "Resend request failed invoice=%s to=%s", invoice_id, redact_email(to)
        )
