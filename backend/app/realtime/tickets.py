"""
Short-lived, single-use WebSocket tickets (HANDOVER.md §8 issue #7).

Browsers cannot set the Authorization header on a WebSocket, and long-lived
credentials in a query string leak into proxy/access logs and browser history.
Instead, clients POST to an authenticated REST endpoint (/auth/ws-ticket for
staff, /session/ws-ticket for customers) to obtain an opaque one-shot ticket,
then connect with ?ticket=<...>. The ticket:

  - expires WS_TICKET_TTL_SECONDS after issue,
  - is consumed on first redemption (replay from a log is worthless),
  - pins kind (staff/customer), subject, and restaurant_id server-side —
    the WebSocket bucket is derived from the ticket, never from the client.

The store is in-memory BY DESIGN: tickets live 60 seconds and the stack runs
a single backend process, so cross-process sharing isn't needed. A restart
simply forces clients to fetch a fresh ticket before reconnecting (the
frontend does this on every connect attempt anyway).
"""

import secrets
import threading
import time
from dataclasses import dataclass

WS_TICKET_TTL_SECONDS = 60


@dataclass(frozen=True)
class TicketClaims:
    kind: str          # "staff" | "customer"
    subject_id: str    # User.id (staff) or TableSession.id (customer)
    restaurant_id: str


_lock = threading.Lock()
# ticket -> (claims, monotonic expiry)
_store: dict[str, tuple[TicketClaims, float]] = {}


def issue_ticket(kind: str, subject_id: object, restaurant_id: object) -> str:
    ticket = secrets.token_urlsafe(32)
    now = time.monotonic()
    with _lock:
        # Opportunistic prune so abandoned tickets can't accumulate.
        for stale in [t for t, (_, exp) in _store.items() if exp <= now]:
            del _store[stale]
        _store[ticket] = (
            TicketClaims(kind=kind, subject_id=str(subject_id), restaurant_id=str(restaurant_id)),
            now + WS_TICKET_TTL_SECONDS,
        )
    return ticket


def redeem_ticket(ticket: str, kind: str) -> TicketClaims | None:
    """
    Atomically consume a ticket. Returns its claims when the ticket exists,
    has not expired, and matches the expected kind — otherwise None. The
    ticket is removed even on a failed redemption (strictly single-use).
    """
    now = time.monotonic()
    with _lock:
        entry = _store.pop(ticket, None)
    if entry is None:
        return None
    claims, expires_at = entry
    if expires_at <= now or claims.kind != kind:
        return None
    return claims
