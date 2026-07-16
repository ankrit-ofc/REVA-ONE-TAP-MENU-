"""
Single-use WebSocket tickets + JWT tenant-claim verification
(HANDOVER.md §8 issues #7 and #8).

WS endpoints accept ONLY short-lived one-shot tickets (?ticket=). A valid
ticket connects and lands in its own tenant's bucket; expired, reused, and
legacy raw-token connections are all closed with 1008.
"""

import time as _time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from starlette.websockets import WebSocketDisconnect

from tests.conftest import auth, login

WS_POLICY_VIOLATION = 1008


def _staff_ticket(client, token) -> str:
    resp = client.post("/auth/ws-ticket", headers=auth(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["expires_in"] == 60
    return body["ticket"]


def _assert_ws_rejected(client, url):
    with client.websocket_connect(url) as ws:
        with pytest.raises(WebSocketDisconnect) as excinfo:
            ws.receive_text()
    assert excinfo.value.code == WS_POLICY_VIOLATION


def _wait_for_registration(rid: str, role: str = "ADMIN", timeout: float = 2.0):
    """The endpoint registers right after redeeming the ticket; poll briefly."""
    from app.realtime.manager import manager

    deadline = _time.time() + timeout
    while _time.time() < deadline:
        if manager._staff[rid][role]:
            return set(manager._staff[rid][role])
        _time.sleep(0.02)
    return set()


def test_valid_ticket_connects_and_joins_own_tenant_bucket(client, seed):
    from app.realtime.manager import manager

    token = login(client, seed["a"])
    ticket = _staff_ticket(client, token)
    rid_a, rid_b = seed["a"]["restaurant_id"], seed["b"]["restaurant_id"]

    with client.websocket_connect(f"/ws/staff?ticket={ticket}"):
        registered = _wait_for_registration(rid_a)
        assert registered, "connection was not registered in tenant A's bucket"
        # Tenant isolation: the socket exists ONLY under tenant A — a ticket
        # from tenant A cannot land in tenant B's bucket (the client sent
        # nothing tenant-related; the bucket comes from the redeemed ticket).
        assert not any(manager._staff[rid_b].values())


def test_reused_ticket_rejected(client, seed):
    token = login(client, seed["a"])
    ticket = _staff_ticket(client, token)

    with client.websocket_connect(f"/ws/staff?ticket={ticket}"):
        assert _wait_for_registration(seed["a"]["restaurant_id"])

    # Second redemption of the SAME ticket must fail (single-use).
    _assert_ws_rejected(client, f"/ws/staff?ticket={ticket}")


def test_expired_ticket_rejected(client, seed):
    from app.realtime import tickets as tickets_mod

    token = login(client, seed["a"])
    ticket = _staff_ticket(client, token)
    # Force expiry without waiting 60s.
    claims, _ = tickets_mod._store[ticket]
    tickets_mod._store[ticket] = (claims, _time.monotonic() - 1)

    _assert_ws_rejected(client, f"/ws/staff?ticket={ticket}")


def test_garbage_ticket_rejected(client, database):
    _assert_ws_rejected(client, "/ws/staff?ticket=not-a-real-ticket")


def test_legacy_raw_token_query_params_rejected(client, seed):
    token = login(client, seed["a"])
    # A perfectly valid access token is no longer accepted on the WS.
    _assert_ws_rejected(client, f"/ws/staff?token={token}")
    _assert_ws_rejected(client, "/ws/customer?session_token=whatever")


def test_staff_ticket_cannot_open_customer_ws(client, seed):
    token = login(client, seed["a"])
    ticket = _staff_ticket(client, token)
    _assert_ws_rejected(client, f"/ws/customer?ticket={ticket}")


def test_customer_ticket_flow(client, seed):
    """Customer: session header → ticket → connect; no ticket → no endpoint."""
    from app.db.session import SessionLocal
    from app.models.table import Table, TableSession
    from app.realtime.manager import manager

    rid = uuid.UUID(seed["a"]["restaurant_id"])
    session_token = f"test-session-token-{uuid.uuid4()}"
    db = SessionLocal()
    try:
        table = Table(restaurant_id=rid, name=f"T-{uuid.uuid4().hex[:6]}")
        db.add(table)
        db.flush()
        table_id = str(table.id)
        db.add(TableSession(
            restaurant_id=rid,
            table_id=table.id,
            token=session_token,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        ))
        db.commit()
    finally:
        db.close()

    # No session header → no ticket.
    assert client.post("/session/ws-ticket").status_code == 401

    resp = client.post("/session/ws-ticket", headers={"X-Session-Token": session_token})
    assert resp.status_code == 200, resp.text
    ticket = resp.json()["ticket"]

    with client.websocket_connect(f"/ws/customer?ticket={ticket}"):
        deadline = _time.time() + 2
        registered = False
        while _time.time() < deadline:
            if manager._customers[str(rid)][table_id]:
                registered = True
                break
            _time.sleep(0.02)
        assert registered, "customer socket not registered under its table bucket"


def test_jwt_missing_tenant_claim_rejected(client, seed):
    """HANDOVER §8 #8: a token whose restaurant_id claim is absent or wrong → 401."""
    import jwt

    from app.core.config import settings

    now = datetime.now(timezone.utc)
    base = {
        "sub": seed["a"]["user_id"],
        "role": "ADMIN",
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }

    no_claim = jwt.encode(base, settings.SECRET_KEY, algorithm="HS256")
    assert client.get("/auth/me", headers=auth(no_claim)).status_code == 401

    wrong_claim = jwt.encode(
        {**base, "restaurant_id": seed["b"]["restaurant_id"]},
        settings.SECRET_KEY,
        algorithm="HS256",
    )
    assert client.get("/auth/me", headers=auth(wrong_claim)).status_code == 401

    # Sanity: the legitimate token (correct claim) still works.
    good = login(client, seed["a"])
    assert client.get("/auth/me", headers=auth(good)).status_code == 200
