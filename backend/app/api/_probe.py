import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.deps import get_current_session, require_role, tenant_scope
from app.models.enums import Role
from app.models.table import TableSession
from app.models.user import User

router = APIRouter(prefix="/_probe", tags=["probe"])


@router.get("/admin")
def probe_admin(
    restaurant_id: Annotated[uuid.UUID, Depends(tenant_scope)],
    _user: Annotated[User, Depends(require_role(Role.ADMIN))],
) -> dict[str, str]:
    """
    Smoke-test: verifies full staff auth + tenancy spine.
    - 401 if token is missing/expired/tampered.
    - 403 if user is not ADMIN.
    - Returns the restaurant_id derived from the JWT (never from the request body).
    Removed in a later phase.
    """
    return {"restaurant_id": str(restaurant_id)}


@router.get("/session")
def probe_session(
    session: Annotated[TableSession, Depends(get_current_session)],
) -> dict[str, str]:
    """
    Smoke-test: verifies customer session auth.
    - 401 if X-Session-Token is missing, invalid, expired, or invalidated.
    - Returns table_id and status derived from the validated session.
    Removed in a later phase.
    """
    return {
        "table_id": str(session.table_id),
        "session_status": session.status.value,
    }
