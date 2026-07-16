from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import settings
from app.core.deps import get_current_user, get_db
from app.core.limiter import limiter
from app.models.restaurant import Restaurant
from app.models.user import User
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    ResetPasswordRequest,
    TokenResponse,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_refresh_cookie(response: Response, token: str, max_age: int) -> None:
    """
    Writes the refresh token as an HttpOnly, SameSite=Strict cookie.
    max_age (seconds) matches the token's role-aware lifetime so the cookie and
    the JWT/DB record expire together.
    """
    response.set_cookie(
        key="refresh_token",
        value=token,
        httponly=True,
        secure=(settings.ENVIRONMENT != "development"),
        samesite="strict",
        max_age=max_age,
        path="/auth",
    )


@router.post("/login", response_model=TokenResponse)
@limiter.limit(settings.RATE_LIMIT_LOGIN)
def login(
    request: Request,
    body: LoginRequest,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> TokenResponse:
    user = auth_service.authenticate(db, body.email, body.password, body.restaurant_slug)
    access_token, refresh_token = auth_service.issue_tokens(db, user, body.remember_me)
    max_age = int(
        security.refresh_token_ttl(user.role.value, body.remember_me).total_seconds()
    )
    _set_refresh_cookie(response, refresh_token, max_age)
    return TokenResponse(access_token=access_token, token_type="bearer")


@router.post("/forgot-password", response_model=MessageResponse)
@limiter.limit(settings.RATE_LIMIT_PASSWORD_RESET)
def forgot_password(
    request: Request,
    body: ForgotPasswordRequest,
    db: Annotated[Session, Depends(get_db)],
) -> MessageResponse:
    """
    Starts a password reset. Always returns the same generic message regardless of
    whether the account exists, to avoid leaking which emails are registered.
    """
    auth_service.request_password_reset(db, body.restaurant_slug, body.email)
    return MessageResponse(
        message="If an account matches those details, a reset link has been sent."
    )


@router.post("/reset-password", response_model=MessageResponse)
@limiter.limit(settings.RATE_LIMIT_PASSWORD_RESET)
def reset_password(
    request: Request,
    body: ResetPasswordRequest,
    db: Annotated[Session, Depends(get_db)],
) -> MessageResponse:
    """Completes a password reset using a token from the emailed link."""
    auth_service.reset_password(db, body.token, body.new_password)
    return MessageResponse(message="Your password has been reset. You can now sign in.")


@router.post("/refresh", response_model=TokenResponse)
def refresh_tokens(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> TokenResponse:
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token missing",
        )
    new_access, new_refresh, user, remember = auth_service.rotate_refresh(db, refresh_token)
    max_age = int(security.refresh_token_ttl(user.role.value, remember).total_seconds())
    _set_refresh_cookie(response, new_refresh, max_age)
    return TokenResponse(access_token=new_access, token_type="bearer")


@router.get("/me")
def me(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str | None]:
    """Current staff identity + their restaurant's display name (for the UI header)."""
    restaurant = db.get(Restaurant, user.restaurant_id)
    return {
        "email": user.email,
        "role": user.role.value,
        "restaurant_id": str(user.restaurant_id),
        "restaurant_name": restaurant.name if restaurant else None,
    }


@router.post("/logout")
def logout(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> dict[str, str]:
    if refresh_token:
        auth_service.revoke_refresh(db, refresh_token)
    response.delete_cookie("refresh_token", path="/auth")
    return {"status": "ok"}
