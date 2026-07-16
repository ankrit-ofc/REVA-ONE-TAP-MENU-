"""
WebSocket authentication helpers (Phase 8; hardened per HANDOVER §8 #7).

Auth transport: a short-lived, SINGLE-USE ticket in the `ticket` query param
(both staff and customers), minted by POST /auth/ws-ticket (staff JWT) or
POST /session/ws-ticket (customer session header). Raw long-lived credentials
(?token= / ?session_token=) are REJECTED outright — query strings end up in
proxy/access logs, and a logged 60-second one-shot ticket is worthless while
a logged JWT or session token is a live credential.

On auth failure the connection is accepted first (required by Starlette to
send a close frame), then immediately closed with WS code 1008 (Policy
Violation), and RuntimeError is raised so the caller can return early.

restaurant_id (and role / table_id) are derived EXCLUSIVELY from the
redeemed ticket + database row — never from any client-supplied value.
"""

import uuid
from datetime import datetime, timezone

from fastapi import WebSocket
from sqlalchemy.orm import Session

from app.models.enums import SessionStatus
from app.models.table import TableSession
from app.models.user import User
from app.realtime.tickets import redeem_ticket

WS_POLICY_VIOLATION = 1008

_LEGACY_PARAMS = ("token", "session_token")


async def _reject(ws: WebSocket, reason: str) -> None:
    """Close an already-accepted WebSocket with a policy-violation code."""
    try:
        await ws.close(code=WS_POLICY_VIOLATION, reason=reason)
    except Exception:
        pass


async def _extract_ticket(ws: WebSocket) -> str:
    """Common ticket extraction; rejects legacy raw-token params outright."""
    if any(param in ws.query_params for param in _LEGACY_PARAMS):
        await _reject(ws, "Raw tokens are not accepted; obtain a ws-ticket")
        raise RuntimeError("Legacy token query param rejected")

    ticket = ws.query_params.get("ticket")
    if not ticket:
        await _reject(ws, "Missing ticket query param")
        raise RuntimeError("Missing ticket")
    return ticket


# ── Staff ─────────────────────────────────────────────────────────────────────

async def authenticate_staff_ws(ws: WebSocket, db: Session) -> User:
    """
    Redeem the single-use `ticket` query param (kind=staff) and load the user.
    Closes the WS with 1008 and raises RuntimeError on any failure.
    """
    ticket = await _extract_ticket(ws)

    claims = redeem_ticket(ticket, kind="staff")
    if claims is None:
        await _reject(ws, "Invalid, expired, or already-used ticket")
        raise RuntimeError("Ticket redemption failed")

    user: User | None = db.get(User, uuid.UUID(claims.subject_id))
    if user is None or not user.is_active:
        await _reject(ws, "User not found or inactive")
        raise RuntimeError("User not found or inactive")

    # Tenant pin: the bucket the connection joins comes from the ticket, and
    # the ticket must still match the user's current tenant.
    if str(user.restaurant_id) != claims.restaurant_id:
        await _reject(ws, "Ticket/tenant mismatch")
        raise RuntimeError("Ticket/tenant mismatch")

    return user


# ── Customer ──────────────────────────────────────────────────────────────────

async def authenticate_customer_ws(ws: WebSocket, db: Session) -> TableSession:
    """
    Redeem the single-use `ticket` query param (kind=customer) and load the
    ACTIVE TableSession. Closes the WS with 1008 and raises RuntimeError on
    any failure.
    """
    ticket = await _extract_ticket(ws)

    claims = redeem_ticket(ticket, kind="customer")
    if claims is None:
        await _reject(ws, "Invalid, expired, or already-used ticket")
        raise RuntimeError("Ticket redemption failed")

    session: TableSession | None = db.get(TableSession, uuid.UUID(claims.subject_id))
    if session is None:
        await _reject(ws, "Session not found")
        raise RuntimeError("Session not found")

    now = datetime.now(timezone.utc)
    if session.status == SessionStatus.ACTIVE and session.expires_at <= now:
        session.status = SessionStatus.EXPIRED
        db.commit()

    if session.status != SessionStatus.ACTIVE:
        await _reject(ws, "Session expired or invalidated")
        raise RuntimeError("Session expired or invalidated")

    if str(session.restaurant_id) != claims.restaurant_id:
        await _reject(ws, "Ticket/tenant mismatch")
        raise RuntimeError("Ticket/tenant mismatch")

    return session
