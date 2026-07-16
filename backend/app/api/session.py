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
from app.core.deps import get_current_session, get_db
from app.core.limiter import limiter
from app.models.enums import Role, SessionStatus
from app.models.table import TableSession
from app.models.user import User
from app.schemas.session import InvalidateRequest
from app.services import session_service

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
    table_name = session_service.call_waiter(db, session)
    return {"table_name": table_name}
