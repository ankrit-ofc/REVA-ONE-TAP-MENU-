import uuid
from datetime import datetime, timezone
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import settings
from app.core.deps import get_contact_capture_session, get_current_session, get_db
from app.core.limiter import limiter
from app.models.enums import Role, SessionStatus
from app.models.table import TableSession
from app.models.user import User
from app.realtime import tickets
from app.schemas.auth import WsTicketResponse
from app.schemas.customer import CustomerContactAck, CustomerContactRequest
from app.schemas.session import InvalidateRequest
from app.services import customer_service, session_service
from app.services.customer_service import CustomerCaptureError

router = APIRouter(prefix="/session", tags=["session"])

_bearer = HTTPBearer(auto_error=False)


@router.post("/invalidate")
def invalidate_session_endpoint(
    body: InvalidateRequest,
    db: Annotated[Session, Depends(get_db)],
    x_session_token: Annotated[str | None, Header(alias="X-Session-Token")] = None,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> dict[str, str]:
    """
    Invalidates an active table session.

    Customer path  — X-Session-Token header: session is identified by the token.
    Staff path     — Bearer JWT (ADMIN/WAITER/COUNTER) + body {"session_id": "<uuid>"}.
    """
    now = datetime.now(timezone.utc)

    if x_session_token is not None:
        # ── Customer path ─────────────────────────────────────────────────────
        session: TableSession | None = db.execute(
            select(TableSession).where(TableSession.token == x_session_token)
        ).scalar_one_or_none()

        if session is None or session.status != SessionStatus.ACTIVE or session.expires_at <= now:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired session",
            )

    elif credentials is not None:
        # ── Staff path ────────────────────────────────────────────────────────
        try:
            payload = security.decode_token(credentials.credentials)
        except jwt.PyJWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            )

        if payload.get("type") != "access":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

        try:
            user: User | None = db.get(User, uuid.UUID(payload["sub"]))
        except (ValueError, TypeError):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

        if user is None or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

        if user.role not in (Role.ADMIN, Role.WAITER, Role.COUNTER):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )

        if body.session_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="session_id is required in the request body for staff invalidation",
            )

        # Tenant-scoped lookup — never trust session_id alone without restaurant check.
        session = db.execute(
            select(TableSession).where(
                TableSession.id == body.session_id,
                TableSession.restaurant_id == user.restaurant_id,
            )
        ).scalar_one_or_none()

        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required (X-Session-Token or Bearer JWT)",
        )

    session_service.invalidate_session(db, session)
    return {"status": "ok"}


@router.post("/ws-ticket", response_model=WsTicketResponse)
def create_ws_ticket(
    session: Annotated[TableSession, Depends(get_current_session)],
) -> WsTicketResponse:
    """
    Mint a short-lived, single-use ticket for /ws/customer. The WebSocket
    accepts ONLY these tickets — raw session tokens in the query string are
    rejected (they would leak into proxy logs; HANDOVER §8 #7).
    """
    ticket = tickets.issue_ticket("customer", session.id, session.restaurant_id)
    return WsTicketResponse(ticket=ticket, expires_in=tickets.WS_TICKET_TTL_SECONDS)


@router.post("/contact", response_model=CustomerContactAck)
@limiter.limit(settings.RATE_LIMIT_ORDERS)
def capture_contact_endpoint(
    request: Request,
    body: CustomerContactRequest,
    session: Annotated[TableSession, Depends(get_contact_capture_session)],
    db: Annotated[Session, Depends(get_db)],
) -> CustomerContactAck:
    """
    Customer submits their contact details so we can email them their receipt.

    WRITE-ONLY BY DESIGN: the response is a bare {"status": "ok"} and never
    echoes stored data, so this endpoint cannot be used to look up whether an
    address is known to a restaurant, or to read another diner's details.

    restaurant_id and table_id come from the validated session token only.
    Accepts a session invalidated within the grace window, because paying kills
    the session before the customer reaches the post-payment form — see
    deps.get_contact_capture_session.
    """
    try:
        customer_service.capture_contact(db, session, body)
    except CustomerCaptureError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    return CustomerContactAck()


@router.post("/call-waiter")
@limiter.limit(settings.RATE_LIMIT_CALL_WAITER)
def call_waiter_endpoint(
    request: Request,
    session: Annotated[TableSession, Depends(get_current_session)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    """
    Customer rings the waiters' dashboards for their table. Notify-only and
    order-independent — works any time the session is valid. Returns the table name.
    """
    from app.services.order_state import OrderError

    try:
        table_name = session_service.call_waiter(db, session)
    except OrderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    return {"table_name": table_name}
