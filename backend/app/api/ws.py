"""
WebSocket endpoints (Phase 8; ticket auth per HANDOVER §8 #7).

  /ws/staff    — staff connections; single-use ticket via ?ticket=<...>
                 (minted by POST /auth/ws-ticket with a staff JWT)
  /ws/customer — customer connections; single-use ticket via ?ticket=<...>
                 (minted by POST /session/ws-ticket with X-Session-Token)

Raw long-lived credentials (?token= / ?session_token=) are rejected — query
strings leak into proxy logs; a 60-second one-shot ticket does not matter there.

On connect:
  1. Accept the WebSocket upgrade.
  2. Authenticate (close with 1008 on failure; return early).
  3. Register with the connection manager, scoped to the token's restaurant_id.
  4. Loop: receive_text() keeps the connection alive (clients may send pings;
     we don't parse them — real-time is server→client only in this phase).
  5. On disconnect (WebSocketDisconnect), deregister from the manager.

Security: restaurant_id is ALWAYS taken from the verified token, never from
any client-chosen query param or channel string.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.realtime.auth import authenticate_customer_ws, authenticate_staff_ws
from app.realtime.manager import manager

router = APIRouter(tags=["websockets"])

_DbDep = Annotated[Session, Depends(get_db)]


@router.websocket("/ws/staff")
async def ws_staff(ws: WebSocket, db: _DbDep) -> None:
    """
    Staff WebSocket.  Single-use `ticket` query param is mandatory.
    The connection is registered to the role/restaurant bucket derived from
    the redeemed ticket — no client can choose a different role or restaurant.
    """
    await ws.accept()
    try:
        user = await authenticate_staff_ws(ws, db)
    except RuntimeError:
        return  # WS already closed inside authenticate_staff_ws

    rid = str(user.restaurant_id)
    manager.register_staff(rid, user.role, ws)
    try:
        while True:
            await ws.receive_text()  # keeps the connection open
    except WebSocketDisconnect:
        pass
    finally:
        manager.deregister_staff(rid, user.role, ws)


@router.websocket("/ws/customer")
async def ws_customer(ws: WebSocket, db: _DbDep) -> None:
    """
    Customer WebSocket.  Single-use `ticket` query param is mandatory.
    The connection is registered to the table bucket derived from the ticket's
    session — customers at table T only receive events for table T's orders.
    """
    await ws.accept()
    try:
        session = await authenticate_customer_ws(ws, db)
    except RuntimeError:
        return

    rid = str(session.restaurant_id)
    tid = str(session.table_id)
    manager.register_customer(rid, tid, ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.deregister_customer(rid, tid, ws)
