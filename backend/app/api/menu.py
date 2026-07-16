"""
Customer-facing menu read.

Requires a valid table session (X-Session-Token header).
Returns only active categories with available + active products.
Inactive/unavailable items are silently omitted — never 404'd — so the
customer sees a clean menu without knowing what's been hidden.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_current_session
from app.models.table import TableSession
from app.schemas.menu import MenuPublic
from app.services import menu_service

router = APIRouter(tags=["menu"])


@router.get("/menu", response_model=MenuPublic)
def get_menu(
    session: Annotated[TableSession, Depends(get_current_session)],
    db: Annotated[Session, Depends(get_db)],
) -> MenuPublic:
    """
    Returns the full customer-visible menu page for the restaurant bound to
    the caller's table session: hero banner, today's specials, and the
    category tree.

    restaurant_id is derived exclusively from the validated session — never
    from a query param or request body.
    """
    return menu_service.get_customer_menu_page(db, session.restaurant_id)
