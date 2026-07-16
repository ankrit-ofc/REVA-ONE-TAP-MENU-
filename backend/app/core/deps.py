import uuid
from collections.abc import Callable, Generator
from datetime import datetime, timezone
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core import security
from app.db.session import SessionLocal
from app.models.enums import Role, SessionStatus
from app.models.table import TableSession
from app.models.user import User

_bearer = HTTPBearer(auto_error=False)


# ── Database ──────────────────────────────────────────────────────────────────

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Staff authentication ───────────────────────────────────────────────────────

def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """
    Decodes the Bearer access token, verifies it is an 'access' token,
    then loads the active User from the database.
    Raises 401 on any failure — never leaks the reason to the client.
    """
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    try:
        payload = security.decode_token(credentials.credentials)
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    raw_id: str | None = payload.get("sub")
    if not raw_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    try:
        user_uuid = uuid.UUID(raw_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    user: User | None = db.get(User, user_uuid)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    # Tenant pin (HANDOVER §8 #8): the token's restaurant_id claim must match
    # the user's current tenant. A token minted before an account was moved —
    # or forged with a mismatched claim — is rejected, so a user row is never
    # loaded "by PK alone" without its tenant being cross-checked.
    claim_rid = payload.get("restaurant_id")
    if claim_rid is None or str(claim_rid) != str(user.restaurant_id):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token claims")

    return user


# ── Staff authorization ────────────────────────────────────────────────────────

def require_role(*roles: Role) -> Callable:
    """
    Returns a FastAPI dependency that enforces the given roles.
    Raises 403 if the authenticated user's role is not in the allowed set.
    Usage: Depends(require_role(Role.ADMIN, Role.SUPERADMIN))
    """
    def _check_role(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user

    return _check_role


# ── Staff tenant scoping ───────────────────────────────────────────────────────

def tenant_scope(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> uuid.UUID:
    """
    Extracts restaurant_id from the verified JWT claim and sets the Postgres GUC
    `app.current_restaurant_id` so Phase 1 RLS policies engage for this session.

    restaurant_id is NEVER read from the request body, query params, or headers.
    Any client-supplied restaurant_id is irrelevant and ignored here.
    """
    # set_config(name, value, is_local=TRUE) is the parameterizable equivalent of
    # SET LOCAL — PostgreSQL rejects $1 placeholders in SET LOCAL syntax.
    db.execute(
        text("SELECT set_config('app.current_restaurant_id', :rid, TRUE)"),
        {"rid": str(user.restaurant_id)},
    )
    return user.restaurant_id


# ── Customer session auth ──────────────────────────────────────────────────────

def get_current_session(
    x_session_token: Annotated[str | None, Header(alias="X-Session-Token")] = None,
    db: Annotated[Session, Depends(get_db)] = None,
) -> TableSession:
    """
    Validates the customer session token from the X-Session-Token header.
    - Rejects missing, invalid, expired, or invalidated tokens (401).
    - Auto-marks ACTIVE sessions whose expires_at has passed as EXPIRED.
    - Sets the Postgres GUC app.current_restaurant_id for RLS.
    - Exposes session.table_id to handlers (never taken from request body).
    """
    if x_session_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Session-Token header missing",
        )

    session: TableSession | None = db.execute(
        select(TableSession).where(TableSession.token == x_session_token)
    ).scalar_one_or_none()

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session token",
        )

    now = datetime.now(timezone.utc)

    if session.status == SessionStatus.ACTIVE and session.expires_at <= now:
        session.status = SessionStatus.EXPIRED
        db.commit()

    if session.status != SessionStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalidated",
        )

    db.execute(
        text("SELECT set_config('app.current_restaurant_id', :rid, TRUE)"),
        {"rid": str(session.restaurant_id)},
    )

    return session
