"""
WebSocket authentication helpers (Phase 8).

Auth transport: query param (both staff and customers).
  Staff   : ?token=<jwt_access_token>
  Customer: ?session_token=<table_session_token>

Using query params because the WebSocket API in browsers does not allow
setting the Authorization header — query param is the standard alternative.

On auth failure the connection is accepted first (required by Starlette to
send a close frame), then immediately closed with WS code 1008 (Policy
Violation), and RuntimeError is raised so the caller can return early.

restaurant_id (and role / table_id) are derived EXCLUSIVELY from the
verified credential — never from any client-supplied query param or body.
"""

import uuid
from datetime import datetime, timezone

import jwt
from fastapi import WebSocket
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import security
from app.models.enums import SessionStatus
from app.models.table import TableSession
from app.models.user import User

WS_POLICY_VIOLATION = 1008


async def _reject(ws: WebSocket, reason: str) -> None:
    """Close an already-accepted WebSocket with a policy-violation code."""
    try:
        await ws.close(code=WS_POLICY_VIOLATION, reason=reason)
    except Exception:
        pass


# ── Staff ─────────────────────────────────────────────────────────────────────

async def authenticate_staff_ws(ws: WebSocket, db: Session) -> User:
    """
    Validate the JWT access token from the `token` query param.
    Returns the active User on success.
    Closes the WS with 1008 and raises RuntimeError on any failure.
    """
    token = ws.query_params.get("token")
    if not token:
        await _reject(ws, "Missing token query param")
        raise RuntimeError("Missing token")

    try:
        payload = security.decode_token(token)
    except jwt.PyJWTError:
        await _reject(ws, "Invalid or expired token")
        raise RuntimeError("Invalid or expired token")

    if payload.get("type") != "access":
        await _reject(ws, "Invalid token type")
        raise RuntimeError("Invalid token type")

    try:
        user_id = uuid.UUID(str(payload.get("sub", "")))
    except ValueError:
        await _reject(ws, "Invalid token claims")
        raise RuntimeError("Invalid token claims")

    user: User | None = db.get(User, user_id)
    if user is None or not user.is_active:
        await _reject(ws, "User not found or inactive")
        raise RuntimeError("User not found or inactive")

    return user


# ── Customer ──────────────────────────────────────────────────────────────────

async def authenticate_customer_ws(ws: WebSocket, db: Session) -> TableSession:
    """
    Validate the table session token from the `session_token` query param.
    Returns the ACTIVE TableSession on success.
    Closes the WS with 1008 and raises RuntimeError on any failure.
    """
    token = ws.query_params.get("session_token")
    if not token:
        await _reject(ws, "Missing session_token query param")
        raise RuntimeError("Missing session_token")

    session: TableSession | None = db.execute(
        select(TableSession).where(TableSession.token == token)
    ).scalar_one_or_none()

    if session is None:
        await _reject(ws, "Invalid session token")
        raise RuntimeError("Invalid session token")

    now = datetime.now(timezone.utc)
    if session.status == SessionStatus.ACTIVE and session.expires_at <= now:
        session.status = SessionStatus.EXPIRED
        db.commit()

    if session.status != SessionStatus.ACTIVE:
        await _reject(ws, "Session expired or invalidated")
        raise RuntimeError("Session expired or invalidated")

    return session
