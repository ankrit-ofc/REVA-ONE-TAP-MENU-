"""
Signed table-access tokens embedded in the QR / NFC link.

The token is opaque to clients — they POST it verbatim to /scan. To keep the
NFC link small (under 180 bytes), the current format packs the two UUIDs into
32 raw bytes, base64url-encodes them, and appends an HMAC signature via
itsdangerous.Signer — yielding a ~71-char token (vs ~176 for the old JSON form).

verify_qr stays backward compatible: it tries the compact format first, then
falls back to the legacy URLSafeSerializer JSON format so QR stickers already
printed in the wild keep working.
"""

import base64
import uuid

from itsdangerous import BadSignature, Signer, URLSafeSerializer

from app.core.config import settings

# Compact format (current): Signer over base64url(restaurant.bytes + table.bytes).
_signer = Signer(settings.QR_SECRET, salt="qr-table-access-v2")

# Legacy format (verify-only): JSON {restaurant_id, table_id, v} via URLSafeSerializer.
_serializer = URLSafeSerializer(settings.QR_SECRET, salt="qr-table-access")


def sign_qr(restaurant_id: str, table_id: str) -> str:
    raw = uuid.UUID(restaurant_id).bytes + uuid.UUID(table_id).bytes  # 32 bytes
    packed = base64.urlsafe_b64encode(raw).rstrip(b"=")
    return _signer.sign(packed).decode()


def _verify_compact(token: str) -> dict:
    """New format. Raises BadSignature/ValueError if the token isn't this format."""
    packed = _signer.unsign(token)  # bytes; raises BadSignature on mismatch
    raw = base64.urlsafe_b64decode(packed + b"=" * (-len(packed) % 4))
    if len(raw) != 32:
        raise ValueError("Malformed QR payload")
    return {
        "restaurant_id": str(uuid.UUID(bytes=raw[:16])),
        "table_id": str(uuid.UUID(bytes=raw[16:])),
    }


def _verify_legacy(token: str) -> dict:
    """Old JSON format, for QR codes signed before the compact format."""
    data: dict = _serializer.loads(token)  # raises BadSignature on mismatch
    if data.get("v") != 1:
        raise ValueError(f"Unsupported QR token version: {data.get('v')!r}")
    return data


def verify_qr(token: str) -> dict:
    """
    Returns {restaurant_id, table_id} (legacy tokens also include {v}).
    Callers must catch ValueError and return 400.
    """
    # base64/UUID failures surface as ValueError (binascii.Error subclasses it);
    # a wrong-format/forged token surfaces as BadSignature. Either way, fall back.
    try:
        return _verify_compact(token)
    except (BadSignature, ValueError):
        pass

    try:
        return _verify_legacy(token)
    except (BadSignature, ValueError):
        raise ValueError("Invalid QR token signature")
