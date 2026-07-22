"""
Push-notification service — Expo Push (→ FCM on Android, APNs on iOS).

Delivers staff alerts (new order, waiter called, bill requested, approval
needed) even when the app is backgrounded or fully closed, which a WebSocket
alone cannot do once the OS kills the process.

Design:
- register_device / deactivate_device manage a tenant-scoped token per physical
  device (the mobile app registers on login, deactivates on logout).
- notify(db, event) is called right after each WS broadcast. It maps the event
  to (roles, message), looks up the active tokens for those roles' users in the
  restaurant (synchronously, on the request's RLS-scoped session), then fires a
  best-effort HTTP POST to Expo's push API on the event loop — never blocking or
  failing the originating request.

Security / tenancy:
- restaurant_id comes from the authenticated actor (token registration) or the
  post-commit event (notify) — never from a client body.
- Token queries are tenant-scoped and RLS-backed; the background receipt handler
  re-sets app.current_restaurant_id on its own session before touching rows.
"""

import uuid

import httpx
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.device_token import DeviceToken
from app.models.enums import Role
from app.models.user import User
from app.realtime.manager import _fire

# Android notification channel the mobile app must create with this exact id so
# high-priority (heads-up + sound + lock-screen) delivery applies.
_ANDROID_CHANNEL = "staff-v2"

# Which staff roles should be pushed for each event type — mirrors the WS
# broadcast targets, minus COUNTER_DISPLAY (a passive screen that never needs a
# phone alert).
_EVENT_ROLES: dict[str, list[Role]] = {
    "order.created": [Role.KITCHEN, Role.WAITER, Role.COUNTER, Role.ADMIN],
    "order.approval_requested": [Role.WAITER, Role.ADMIN],
    "waiter.called": [Role.WAITER, Role.COUNTER, Role.ADMIN],
    "bill.requested": [Role.WAITER, Role.COUNTER, Role.ADMIN],
}


# ── Registration ───────────────────────────────────────────────────────────────

def register_device(db: Session, user: User, token: str, platform: str) -> DeviceToken:
    """
    Upsert this device's push token for the logged-in staff user. Re-registering
    an existing token (same device, new login) reassigns it to the current
    user/restaurant and reactivates it. Tenant scope comes from the user, never
    the request body.
    """
    existing = db.execute(
        select(DeviceToken).where(DeviceToken.token == token)
    ).scalar_one_or_none()

    if existing is not None:
        existing.restaurant_id = user.restaurant_id
        existing.user_id = user.id
        existing.platform = platform
        existing.is_active = True
        db.commit()
        db.refresh(existing)
        return existing

    row = DeviceToken(
        id=uuid.uuid4(),
        restaurant_id=user.restaurant_id,
        user_id=user.id,
        token=token,
        platform=platform,
        is_active=True,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        # A concurrent registration won the unique-token race — reuse it.
        db.rollback()
        row = db.execute(
            select(DeviceToken).where(DeviceToken.token == token)
        ).scalar_one()
        row.restaurant_id = user.restaurant_id
        row.user_id = user.id
        row.platform = platform
        row.is_active = True
        db.commit()
    db.refresh(row)
    return row


def deactivate_device(db: Session, restaurant_id: uuid.UUID, token: str) -> None:
    """Soft-deactivate a token (logout). No error if it is unknown/already off."""
    db.execute(
        update(DeviceToken)
        .where(DeviceToken.token == token, DeviceToken.restaurant_id == restaurant_id)
        .values(is_active=False)
    )
    db.commit()


# ── Outbound notifications ──────────────────────────────────────────────────────

def _message_for(event: object) -> tuple[str, str] | None:
    """(title, body) for a push, mirroring the mobile in-app alert copy."""
    t = getattr(event, "type", None)
    table_name = getattr(event, "table_name", "") or ""
    table = f"Table {table_name}" if table_name else "A table"
    num = getattr(event, "order_number", None)
    suffix = f" (order #{num})" if num is not None else ""
    if t == "order.created":
        return "New order", f"{table} placed an order{suffix}."
    if t == "order.approval_requested":
        return "Approval needed", f"{table} placed an order{suffix} — approve or reject it."
    if t == "waiter.called":
        return "Waiter called", f"{table} needs a waiter."
    if t == "bill.requested":
        return "Bill requested", f"{table} asked for the bill{suffix}."
    return None


def notify(db: Session, event: object) -> None:
    """
    Fire a best-effort push for a domain event. Called post-commit, right beside
    the WS broadcast. Looks up target tokens synchronously (fast, indexed) then
    hands the HTTP send off to the event loop. Never raises.
    """
    if not settings.EXPO_PUSH_ENABLED:
        return
    roles = _EVENT_ROLES.get(getattr(event, "type", ""))
    if not roles:
        return
    msg = _message_for(event)
    if msg is None:
        return
    rid_raw = getattr(event, "restaurant_id", None)
    if not rid_raw:
        return
    try:
        rid = uuid.UUID(str(rid_raw))
    except ValueError:
        return

    tokens = db.execute(
        select(DeviceToken.token)
        .join(User, User.id == DeviceToken.user_id)
        .where(
            DeviceToken.restaurant_id == rid,
            DeviceToken.is_active.is_(True),
            User.role.in_(roles),
            User.is_active.is_(True),
        )
    ).scalars().all()
    if not tokens:
        return

    title, body = msg
    _fire(_send_expo(list(tokens), title, body, str(rid)))


async def _send_expo(tokens: list[str], title: str, body: str, rid: str) -> None:
    """POST messages to Expo's push API in ≤100-token chunks; retire dead tokens."""
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if settings.EXPO_ACCESS_TOKEN:
        headers["Authorization"] = f"Bearer {settings.EXPO_ACCESS_TOKEN}"

    dead: list[str] = []
    async with httpx.AsyncClient(timeout=10.0) as client:
        for i in range(0, len(tokens), 100):
            chunk = tokens[i : i + 100]
            messages = [
                {
                    "to": tok,
                    "title": title,
                    "body": body,
                    "sound": "default",
                    "priority": "high",
                    "channelId": _ANDROID_CHANNEL,
                }
                for tok in chunk
            ]
            try:
                resp = await client.post(settings.EXPO_PUSH_URL, json=messages, headers=headers)
                payload = resp.json()
            except Exception:
                continue
            # Expo returns {"data": [{"status": "ok"|"error", "details": {...}}, ...]}
            data = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(data, list):
                continue
            for tok, receipt in zip(chunk, data):
                if (
                    isinstance(receipt, dict)
                    and receipt.get("status") == "error"
                    and (receipt.get("details") or {}).get("error") == "DeviceNotRegistered"
                ):
                    dead.append(tok)

    if dead:
        _deactivate_tokens(dead, rid)


def _deactivate_tokens(tokens: list[str], rid: str) -> None:
    """Retire tokens Expo rejected as unregistered, on a fresh RLS-scoped session."""
    db = SessionLocal()
    try:
        db.execute(
            text("SELECT set_config('app.current_restaurant_id', :rid, TRUE)"),
            {"rid": rid},
        )
        db.execute(
            update(DeviceToken)
            .where(DeviceToken.token.in_(tokens))
            .values(is_active=False)
        )
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()
