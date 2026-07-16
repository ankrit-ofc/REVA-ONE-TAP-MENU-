"""
WebSocket connection manager (Phase 8).

Maintains two keyed registries per tenant:
  _staff     : restaurant_id → role_value → {WebSocket}
  _customers : restaurant_id → table_id   → {WebSocket}

Tenant scope is ALWAYS derived from the authenticated token; clients can never
choose their restaurant_id or channel.

Broadcast helpers are async coroutines.  Services are synchronous (called from
FastAPI's thread pool), so they schedule broadcasts via _fire(), which calls
asyncio.run_coroutine_threadsafe() on the main event loop stored at startup.

_fire() is fire-and-forget: it never raises, never blocks the HTTP response,
and is a no-op if no event loop has been registered (e.g. during tests).
"""

import asyncio
import json
from collections import defaultdict
from dataclasses import asdict
from typing import Any

from fastapi import WebSocket

from app.models.enums import Role

# ── Event loop reference ───────────────────────────────────────────────────────

_main_loop: asyncio.AbstractEventLoop | None = None


def _set_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Called from the FastAPI lifespan to capture the running event loop."""
    global _main_loop
    _main_loop = loop


def _fire(coro: Any) -> None:
    """Schedule an async broadcast coroutine from any thread (fire-and-forget)."""
    if _main_loop is not None and _main_loop.is_running():
        try:
            asyncio.run_coroutine_threadsafe(coro, _main_loop)
        except Exception:
            pass


# ── Connection manager ─────────────────────────────────────────────────────────

class ConnectionManager:
    def __init__(self) -> None:
        # {restaurant_id_str: {role_value_str: {WebSocket}}}
        self._staff: dict[str, dict[str, set[WebSocket]]] = defaultdict(
            lambda: defaultdict(set)
        )
        # {restaurant_id_str: {table_id_str: {WebSocket}}}
        self._customers: dict[str, dict[str, set[WebSocket]]] = defaultdict(
            lambda: defaultdict(set)
        )

    # ── Registration ──────────────────────────────────────────────────────────

    def register_staff(self, restaurant_id: str, role: Role, ws: WebSocket) -> None:
        self._staff[restaurant_id][role.value].add(ws)

    def deregister_staff(self, restaurant_id: str, role: Role, ws: WebSocket) -> None:
        self._staff[restaurant_id][role.value].discard(ws)

    def register_customer(self, restaurant_id: str, table_id: str, ws: WebSocket) -> None:
        self._customers[restaurant_id][table_id].add(ws)

    def deregister_customer(self, restaurant_id: str, table_id: str, ws: WebSocket) -> None:
        self._customers[restaurant_id][table_id].discard(ws)

    # ── Broadcast ─────────────────────────────────────────────────────────────

    async def broadcast_to_roles(
        self,
        restaurant_id: str,
        event: Any,
        roles: list[Role],
    ) -> None:
        """
        Send event to all connected staff WebSockets for restaurant_id whose
        role is in roles.  Dead sockets are silently removed.
        """
        msg = json.dumps(asdict(event))
        rid = str(restaurant_id)
        dead: list[tuple[str, WebSocket]] = []

        for role in roles:
            for ws in list(self._staff.get(rid, {}).get(role.value, set())):
                try:
                    await ws.send_text(msg)
                except Exception:
                    dead.append((role.value, ws))

        for role_val, ws in dead:
            self._staff[rid][role_val].discard(ws)

    async def broadcast_to_table(
        self,
        restaurant_id: str,
        table_id: str,
        event: Any,
    ) -> None:
        """
        Send event to all customer WebSockets connected for the given table.
        Tenant scope is the restaurant_id derived from the session token — the
        table_id alone is never sufficient to address a connection.
        """
        msg = json.dumps(asdict(event))
        rid, tid = str(restaurant_id), str(table_id)
        dead: list[WebSocket] = []

        for ws in list(self._customers.get(rid, {}).get(tid, set())):
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)

        for ws in dead:
            self._customers[rid][tid].discard(ws)

    # ── Heartbeat ─────────────────────────────────────────────────────────────

    async def heartbeat(self) -> None:
        """
        Send a keepalive frame to every connection (staff + customer) and prune
        any socket that fails. Without periodic traffic, idle WebSockets are
        silently closed by intermediaries (Cloudflare's ~100s idle timeout),
        which stops event delivery until the client happens to reconnect. The
        heartbeat keeps quiet connections alive AND gives clients a liveness
        signal so they can detect and re-establish a half-open socket.
        """
        for by_role in list(self._staff.values()):
            for conns in list(by_role.values()):
                for ws in list(conns):
                    try:
                        await ws.send_text(_HEARTBEAT)
                    except Exception:
                        conns.discard(ws)

        for by_table in list(self._customers.values()):
            for conns in list(by_table.values()):
                for ws in list(conns):
                    try:
                        await ws.send_text(_HEARTBEAT)
                    except Exception:
                        conns.discard(ws)


# Server→client keepalive frame. `type` mirrors the event envelope so clients
# route it like any other frame; screens ignore it, they just count as activity.
_HEARTBEAT = json.dumps({"type": "heartbeat"})

# Interval must sit comfortably under the tightest proxy idle timeout on the path
# (Cloudflare ≈ 100s); 25s leaves margin for a missed beat before a close.
HEARTBEAT_INTERVAL_S = 25.0

_heartbeat_task: "asyncio.Task[None] | None" = None


async def _heartbeat_loop(interval: float) -> None:
    while True:
        await asyncio.sleep(interval)
        try:
            await manager.heartbeat()
        except asyncio.CancelledError:
            raise
        except Exception:
            # A single bad socket must never kill the keepalive loop.
            pass


def start_heartbeat(
    loop: asyncio.AbstractEventLoop, interval: float = HEARTBEAT_INTERVAL_S
) -> None:
    """Start the background keepalive loop (idempotent). Called from lifespan."""
    global _heartbeat_task
    if _heartbeat_task is None or _heartbeat_task.done():
        _heartbeat_task = loop.create_task(_heartbeat_loop(interval))


async def stop_heartbeat() -> None:
    """Cancel the keepalive loop on shutdown."""
    global _heartbeat_task
    if _heartbeat_task is not None:
        _heartbeat_task.cancel()
        try:
            await _heartbeat_task
        except asyncio.CancelledError:
            pass
        _heartbeat_task = None


# Module-level singleton — imported by services and ws.py
manager = ConnectionManager()
