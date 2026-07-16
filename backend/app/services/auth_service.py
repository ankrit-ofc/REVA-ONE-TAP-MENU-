import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import settings
from app.models.audit_log import AuditLog
from app.models.password_reset_token import PasswordResetToken
from app.models.refresh_token import RefreshToken
from app.models.restaurant import Restaurant
from app.models.user import User
from app.services import email_service


def authenticate(db: Session, email: str, password: str, restaurant_slug: str) -> User:
    """
    Looks up the user by (email, restaurant_slug) and verifies the password.

    Always runs the Argon2 hash verification even when the user is not found to
    prevent timing-based enumeration of valid email/restaurant combinations.
    """
    restaurant: Restaurant | None = db.execute(
        select(Restaurant).where(
            Restaurant.slug == restaurant_slug,
            Restaurant.is_active.is_(True),
        )
    ).scalar_one_or_none()

    user: User | None = None
    if restaurant is not None:
        user = db.execute(
            select(User).where(
                User.email == email,
                User.restaurant_id == restaurant.id,
            )
        ).scalar_one_or_none()

    # Always verify — prevents timing attacks regardless of whether user exists.
    candidate_hash = user.password_hash if user is not None else security._DUMMY_HASH
    password_ok = security.verify_password(password, candidate_hash)

    if user is None or not password_ok or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    return user


def issue_tokens(db: Session, user: User, remember: bool = False) -> tuple[str, str]:
    """
    Creates a short-lived access token and a longer-lived refresh token.
    Persists the refresh token to the DB for rotation tracking.

    Enforces **one active session per account**: any of this user's still-active
    refresh tokens (i.e. other devices/browsers) are revoked first, so logging in
    anywhere displaces the previous session. This is per-user — other accounts are
    untouched. The displaced device self-ejects on its next /auth/refresh (401).

    `remember` (the login "Remember me" option) extends the refresh-token window.

    Returns (access_token, refresh_token_string).
    """
    now = datetime.now(timezone.utc)

    # Lock the user row so two concurrent logins for the same account can't both
    # survive (mirrors the FOR UPDATE guard in rotate_refresh).
    db.execute(select(User.id).where(User.id == user.id).with_for_update())

    # Revoke every still-active session for this account (single-session policy).
    revoked = db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    ).rowcount

    access_token = security.create_access_token(
        user_id=str(user.id),
        restaurant_id=str(user.restaurant_id),
        role=user.role.value,
    )
    refresh_token_str, jti = security.create_refresh_token(
        user_id=str(user.id),
        restaurant_id=str(user.restaurant_id),
        role=user.role.value,
        remember=remember,
    )

    db.add(RefreshToken(
        user_id=user.id,
        restaurant_id=user.restaurant_id,
        jti=jti,
        expires_at=now + security.refresh_token_ttl(user.role.value, remember),
    ))

    # Audit the forced displacement (only when a prior session actually existed).
    if revoked:
        db.add(AuditLog(
            restaurant_id=user.restaurant_id,
            actor_user_id=user.id,
            actor_type=user.role.value,
            entity_type="user",
            entity_id=user.id,
            action="session_superseded",
            new_value={"revoked_sessions": revoked},
        ))

    db.commit()

    return access_token, refresh_token_str


def rotate_refresh(db: Session, refresh_token_str: str) -> tuple[str, str, User, bool]:
    """
    Validates the incoming refresh token, revokes it, and issues a fresh pair.
    Uses SELECT FOR UPDATE to prevent concurrent rotation races.
    Returns (new_access_token, new_refresh_token, user, remember).
    """
    try:
        payload = security.decode_token(refresh_token_str)
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    jti: str | None = payload.get("jti")
    raw_user_id: str | None = payload.get("sub")
    if not jti or not raw_user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    # Lock the row to prevent two concurrent refresh requests on the same token.
    rt: RefreshToken | None = db.execute(
        select(RefreshToken)
        .where(RefreshToken.jti == jti, RefreshToken.revoked_at.is_(None))
        .with_for_update()
    ).scalar_one_or_none()

    if rt is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token revoked or not found",
        )

    try:
        user: User | None = db.get(User, uuid.UUID(raw_user_id))
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    if user is None or not user.is_active:
        rt.revoked_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    # Revoke old token and issue new pair atomically.
    rt.revoked_at = datetime.now(timezone.utc)

    # Preserve the "Remember me" longevity across rotations.
    remember = bool(payload.get("remember", False))

    new_access = security.create_access_token(
        user_id=str(user.id),
        restaurant_id=str(user.restaurant_id),
        role=user.role.value,
    )
    new_refresh, new_jti = security.create_refresh_token(
        user_id=str(user.id),
        restaurant_id=str(user.restaurant_id),
        role=user.role.value,
        remember=remember,
    )
    db.add(RefreshToken(
        user_id=user.id,
        restaurant_id=user.restaurant_id,
        jti=new_jti,
        expires_at=datetime.now(timezone.utc)
        + security.refresh_token_ttl(user.role.value, remember),
    ))
    db.commit()

    return new_access, new_refresh, user, remember


def revoke_refresh(db: Session, refresh_token_str: str) -> None:
    """
    Marks the refresh token as revoked. Silently succeeds on invalid/expired
    tokens so that logout always returns 200 — the client should clear its state
    regardless.
    """
    try:
        payload = security.decode_token(refresh_token_str)
    except jwt.PyJWTError:
        return

    jti: str | None = payload.get("jti")
    if not jti:
        return

    rt: RefreshToken | None = db.execute(
        select(RefreshToken).where(RefreshToken.jti == jti)
    ).scalar_one_or_none()

    if rt is not None and rt.revoked_at is None:
        rt.revoked_at = datetime.now(timezone.utc)
        db.commit()


def request_password_reset(db: Session, restaurant_slug: str, email: str) -> None:
    """
    Starts the forgot-password flow. Resolves the user by (slug, email); if found
    and active, invalidates any prior unused reset tokens, mints a new single-use
    token, emails the reset link, and audits the request.

    Returns None unconditionally and never reveals whether the account exists —
    callers must always respond with the same generic message (no enumeration).
    """
    restaurant: Restaurant | None = db.execute(
        select(Restaurant).where(
            Restaurant.slug == restaurant_slug,
            Restaurant.is_active.is_(True),
        )
    ).scalar_one_or_none()

    user: User | None = None
    if restaurant is not None:
        user = db.execute(
            select(User).where(
                User.email == email,
                User.restaurant_id == restaurant.id,
            )
        ).scalar_one_or_none()

    if user is None or not user.is_active:
        return

    now = datetime.now(timezone.utc)

    # Invalidate any still-valid prior tokens for this user (only one live link).
    db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        )
        .values(used_at=now)
    )

    raw_token = security.generate_reset_token()
    db.add(PasswordResetToken(
        user_id=user.id,
        restaurant_id=user.restaurant_id,
        token_hash=security.hash_reset_token(raw_token),
        expires_at=now + timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES),
    ))
    db.add(AuditLog(
        restaurant_id=user.restaurant_id,
        actor_user_id=user.id,
        actor_type=user.role.value,
        entity_type="user",
        entity_id=user.id,
        action="password_reset_requested",
    ))
    db.commit()

    reset_link = f"{settings.FRONTEND_BASE_URL}/reset-password?token={raw_token}"
    email_service.send_password_reset_email(user.email, reset_link)


def reset_password(db: Session, raw_token: str, new_password: str) -> None:
    """
    Completes a password reset. Validates the (hashed) token under a row lock,
    rejecting missing / already-used / expired tokens with 400. On success: sets
    the new password, marks the token used, revokes all the user's refresh tokens
    (forcing re-login everywhere), and audits the change — all in one transaction.
    """
    token_hash = security.hash_reset_token(raw_token)
    now = datetime.now(timezone.utc)

    prt: PasswordResetToken | None = db.execute(
        select(PasswordResetToken)
        .where(PasswordResetToken.token_hash == token_hash)
        .with_for_update()
    ).scalar_one_or_none()

    if prt is None or prt.used_at is not None or prt.expires_at <= now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    user: User | None = db.get(User, prt.user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    user.password_hash = security.hash_password(new_password)
    prt.used_at = now

    # Kill all existing sessions so a reset (possibly by an account owner locked
    # out by an attacker) revokes the attacker's access immediately.
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    db.add(AuditLog(
        restaurant_id=user.restaurant_id,
        actor_user_id=user.id,
        actor_type=user.role.value,
        entity_type="user",
        entity_id=user.id,
        action="password_reset_completed",
    ))
    db.commit()
