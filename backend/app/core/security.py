import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import settings
from app.models.enums import Role

_ph = PasswordHasher()

# Pre-computed dummy hash used in authenticate() to keep verification time constant
# regardless of whether the user exists, preventing timing-based enumeration attacks.
_DUMMY_HASH = _ph.hash("__dummy_constant_time_placeholder__")


def hash_password(plain: str) -> str:
    return _ph.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        _ph.verify(hashed, plain)
        return True
    except (VerifyMismatchError, InvalidHashError, VerificationError):
        return False


def create_access_token(user_id: str, restaurant_id: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "restaurant_id": restaurant_id,
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def refresh_token_ttl(role: str, remember: bool = False) -> timedelta:
    """
    Refresh-token lifetime per role: a long window for the always-on counter
    wall display (COUNTER_DISPLAY), a short sliding window for everyone else.

    When `remember` is set (the login "Remember me" checkbox), non-DISPLAY roles
    get an extended window so they stay signed in across browser restarts.
    """
    if role == Role.COUNTER_DISPLAY.value:
        return timedelta(hours=settings.REFRESH_TOKEN_DISPLAY_EXPIRE_HOURS)
    if remember:
        return timedelta(hours=settings.REMEMBER_ME_REFRESH_TOKEN_EXPIRE_HOURS)
    return timedelta(hours=settings.REFRESH_TOKEN_EXPIRE_HOURS)


def create_refresh_token(
    user_id: str, restaurant_id: str, role: str, remember: bool = False
) -> tuple[str, str]:
    """
    Returns (signed_token, jti). The jti is stored in the DB for revocation.
    The `remember` flag is embedded as a claim so rotation preserves the chosen
    longevity across the frequent access-token refresh cycle.
    """
    jti = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "restaurant_id": restaurant_id,
        "type": "refresh",
        "jti": jti,
        "remember": remember,
        "iat": now,
        "exp": now + refresh_token_ttl(role, remember),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256"), jti


def decode_token(token: str) -> dict:
    """
    Decodes and verifies a JWT (signature + expiry).
    Raises jwt.PyJWTError (or subclass) on any failure — callers must catch it.
    """
    return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])


def generate_reset_token() -> str:
    """A high-entropy, URL-safe opaque token for the password-reset link."""
    return secrets.token_urlsafe(32)


def hash_reset_token(raw: str) -> str:
    """
    SHA-256 hex digest of a reset token. Only the hash is stored, so a DB leak
    can't be used to reset passwords. SHA-256 (not Argon2) is appropriate here
    because the token is itself high-entropy and looked up directly by hash.
    """
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
