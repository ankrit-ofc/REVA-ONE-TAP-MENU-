"""
KOT print-worker queue.

When restaurant_settings.kot_print_mode == 'worker', kitchen tickets are queued
in kot_print_jobs instead of being printed by the counter browser. The external
kot-printer Windows service polls POST /printworker/kot/get with the
restaurant's kot_worker_token, prints each ticket to the configured Windows
printer, then POSTs /printworker/kot/ack with the queue_ids that printed.

Tenant scoping: the worker never names a restaurant — it is derived server-side
from the bearer token (unique per restaurant). Ticket content is snapshotted at
enqueue time; only the printer name is resolved at fetch time so an admin can
repoint pending jobs from the Devices page.
"""

import secrets
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.kot_print_job import KotPrintJob
from app.models.restaurant import Restaurant, RestaurantSettings
from app.models.user import User


def build_ticket_items(kot_items: list[dict]) -> list[dict]:
    """
    Convert the internal KOT line shape (product_name/variant_name/quantity/
    special_instructions/addons) to the worker's contract:
    {sn, item_name, quantity, remark}.
    """
    items: list[dict] = []
    for sn, it in enumerate(kot_items, start=1):
        name = it.get("product_name") or ""
        variant = it.get("variant_name")
        if variant:
            name = f"{name} ({variant})"
        remarks: list[str] = []
        addons = it.get("addons") or []
        if addons:
            remarks.append("+ " + ", ".join(addons))
        instructions = it.get("special_instructions")
        if instructions:
            remarks.append(instructions)
        items.append({
            "sn": sn,
            "item_name": name,
            "quantity": it.get("quantity", 1),
            "remark": " | ".join(remarks),
        })
    return items


def enqueue_job(
    db: Session,
    *,
    restaurant_id: uuid.UUID,
    order_id: uuid.UUID,
    order_number: int,
    table_name: str,
    kot_items: list[dict],
    title: str = "ORDER",
) -> KotPrintJob:
    """
    Add a pending print job (no commit — rides the caller's transaction so the
    ticket is queued iff the order round itself commits).
    """
    job = KotPrintJob(
        id=uuid.uuid4(),
        restaurant_id=restaurant_id,
        order_id=order_id,
        title=title,
        ticket={
            "kot_no": f"#{order_number}",
            "table_name": table_name,
            "items": build_ticket_items(kot_items),
        },
    )
    db.add(job)
    return job


# ── Worker-facing (token-authenticated) ──────────────────────────────────────

def get_settings_by_token(db: Session, token: str) -> RestaurantSettings | None:
    """Resolve the tenant from the worker's bearer token. Inactive restaurants
    are treated as unknown (worker gets 401, not an empty queue)."""
    if not token:
        return None
    return db.execute(
        select(RestaurantSettings)
        .join(Restaurant, Restaurant.id == RestaurantSettings.restaurant_id)
        .where(
            RestaurantSettings.kot_worker_token == token,
            Restaurant.is_active.is_(True),
        )
    ).scalar_one_or_none()


def fetch_pending(db: Session, settings: RestaurantSettings, limit: int = 20) -> list[dict]:
    """Pending tickets, oldest first, shaped for the worker's kot/get response."""
    jobs = db.scalars(
        select(KotPrintJob)
        .where(
            KotPrintJob.restaurant_id == settings.restaurant_id,
            KotPrintJob.printed_at.is_(None),
        )
        .order_by(KotPrintJob.queue_id.asc())
        .limit(limit)
    ).all()
    if not jobs:
        return []

    outlet_name = db.scalar(
        select(Restaurant.name).where(Restaurant.id == settings.restaurant_id)
    ) or ""
    try:
        tz = ZoneInfo(settings.timezone)
    except Exception:
        tz = ZoneInfo("UTC")

    tickets: list[dict] = []
    for job in jobs:
        local = job.created_at.astimezone(tz)
        tickets.append({
            "queue_id": job.queue_id,
            "kot_no": job.ticket.get("kot_no", ""),
            "title": job.title,
            "printer": settings.kot_printer_name or "",
            "paper_width": 80,
            "outlet_name": outlet_name,
            "table_name": job.ticket.get("table_name", ""),
            "order_type": "DINE IN",
            "date": local.strftime("%Y-%m-%d"),
            "time": local.strftime("%I:%M %p"),
            "items": job.ticket.get("items", []),
        })
    return tickets


def ack_jobs(db: Session, restaurant_id: uuid.UUID, printed_ids: list[int]) -> list[int]:
    """
    Mark jobs printed. Idempotent and tenant-scoped: ids belonging to another
    restaurant or already acked are silently ignored (the worker may retry acks).
    Commits. Returns the queue_ids actually updated.
    """
    if not printed_ids:
        return []
    updated = db.execute(
        update(KotPrintJob)
        .where(
            KotPrintJob.restaurant_id == restaurant_id,
            KotPrintJob.queue_id.in_(printed_ids),
            KotPrintJob.printed_at.is_(None),
        )
        .values(printed_at=datetime.now(timezone.utc))
        .returning(KotPrintJob.queue_id)
    ).scalars().all()
    db.commit()
    return list(updated)


# ── Admin-facing ─────────────────────────────────────────────────────────────

def rotate_worker_token(db: Session, restaurant_id: uuid.UUID, actor: User) -> str:
    """Generate (or replace) the restaurant's worker token. Audited (value is
    never written to the audit log — it is a credential). Commits."""
    settings = db.execute(
        select(RestaurantSettings).where(
            RestaurantSettings.restaurant_id == restaurant_id
        )
    ).scalar_one()
    had_token = settings.kot_worker_token is not None
    settings.kot_worker_token = secrets.token_hex(32)
    db.add(AuditLog(
        id=uuid.uuid4(),
        restaurant_id=restaurant_id,
        actor_type=actor.role.value,
        actor_user_id=actor.id,
        entity_type="restaurant_settings",
        entity_id=settings.id,
        action="KOT_WORKER_TOKEN_ROTATED",
        previous_value={"had_token": had_token},
        new_value={"had_token": True},
    ))
    db.commit()
    return settings.kot_worker_token
