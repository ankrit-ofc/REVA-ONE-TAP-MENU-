import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import qr
from app.core.config import settings
from app.core.deps import get_db
from app.core.geo import haversine_meters
from app.core.limiter import limiter
from app.models.restaurant import Restaurant, RestaurantSettings
from app.models.table import Table
from app.schemas.session import ScanRequest, SessionResponse
from app.services import session_service

router = APIRouter(tags=["scan"])


@router.post("/scan", response_model=SessionResponse)
@limiter.limit(settings.RATE_LIMIT_SCAN)
def scan_qr(
    request: Request,
    body: ScanRequest,
    db: Annotated[Session, Depends(get_db)],
) -> SessionResponse:
    """
    Exchanges a signed QR token for an active TableSession.
    - Verifies the QR signature (BadSignature → 400).
    - Loads the table, verifying it belongs to the restaurant in the QR payload
      (table_id is never trusted from the request body — it comes from the signed token).
    - Returns the existing ACTIVE session for the table or creates a new one.
    """
    try:
        qr_data = qr.verify_qr(body.qr_token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    try:
        restaurant_id = uuid.UUID(qr_data["restaurant_id"])
        table_id = uuid.UUID(qr_data["table_id"])
    except (ValueError, KeyError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed QR payload",
        )

    restaurant: Restaurant | None = db.get(Restaurant, restaurant_id)
    if not restaurant or not restaurant.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant not found")

    # Location-based ordering: when this restaurant requires it (and has a point
    # set), the device must be within the geofence radius. The frontend first
    # scans without coordinates; a 428 tells it to request location and retry.
    rsettings: RestaurantSettings | None = db.execute(
        select(RestaurantSettings).where(RestaurantSettings.restaurant_id == restaurant_id)
    ).scalar_one_or_none()
    if (
        rsettings is not None
        and rsettings.require_location
        and rsettings.latitude is not None
        and rsettings.longitude is not None
    ):
        if body.latitude is None or body.longitude is None:
            # 428 Precondition Required → client must supply location and retry.
            raise HTTPException(
                status_code=status.HTTP_428_PRECONDITION_REQUIRED,
                detail="location_required",
            )
        distance_m = haversine_meters(
            rsettings.latitude, rsettings.longitude, body.latitude, body.longitude
        )
        if distance_m > rsettings.geofence_radius_meters:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"You appear to be about {round(distance_m)} m away. "
                    "Please order from inside the restaurant."
                ),
            )

    table: Table | None = db.execute(
        select(Table).where(
            Table.id == table_id,
            Table.restaurant_id == restaurant_id,
            Table.is_active.is_(True),
        )
    ).scalar_one_or_none()
    if table is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Table not found")

    # Capture names before session_service.create_or_reuse_session commits the
    # transaction (committing detaches the ORM objects).
    restaurant_name = restaurant.name
    table_name = table.name

    raw_token, session = session_service.create_or_reuse_session(db, table)

    return SessionResponse(
        session_token=raw_token,
        table_name=table_name,
        restaurant_name=restaurant_name,
        expires_at=session.expires_at,
    )
