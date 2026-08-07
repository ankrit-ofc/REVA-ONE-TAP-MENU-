"""
Secure product-image upload service (V1: local volume).

Validates input by content (magic bytes), not extension — accepts only real
JPEG/PNG/WebP. Accepts large, any-resolution, any-aspect-ratio photos (e.g. straight
from a phone camera), then normalises every product image to a uniform square:
center-cropped to 1:1 and downscaled to a fixed target, re-encoded as compressed JPEG.
EXIF orientation is applied first (so photos aren't sideways) and all metadata is then
stripped. Writes under a server-generated UUID filename in a tenant-scoped path.

The MEDIA_ROOT constant is the only coupling to the storage backend.
Replace this module's storage calls with an object-storage SDK (D8) in a later phase.
"""

import io
import uuid
from pathlib import Path

from PIL import Image, ImageOps

_MAX_BYTES: int = 25 * 1024 * 1024  # 25 MB — comfortably fits high-res phone photos
_TARGET: int = 500                  # output square side, in pixels (1:1) — small + fast on menus
_JPEG_QUALITY: int = 80             # good compression; menu cards don't need more
_MEDIA_ROOT: Path = Path("/app/media")  # /app is the container WORKDIR; bind-mounted to ./backend/


def _detect_image_type(header: bytes) -> tuple[str, str] | None:
    """
    Inspects the first 12 bytes (magic bytes) to identify the image format.
    Returns (file_extension, PIL_format_name) or None if unrecognised.
    Extension is intentionally never taken from the client-supplied filename.
    """
    if header[:3] == b'\xff\xd8\xff':
        return 'jpg', 'JPEG'
    if header[:8] == b'\x89PNG\r\n\x1a\n':
        return 'png', 'PNG'
    if header[:4] == b'RIFF' and header[8:12] == b'WEBP':
        return 'webp', 'WEBP'
    return None


def validate_and_store(raw: bytes, restaurant_id: uuid.UUID) -> str:
    """
    Full validation + normalisation pipeline + write.

    1. Enforce max byte size (25 MB).
    2. Detect type by magic bytes — rejects non-image files regardless of extension.
    3. Decode with Pillow to confirm the payload is a valid image (Pillow's
       decompression-bomb guard rejects absurd pixel counts).
    4. Apply EXIF orientation, then flatten any transparency onto white.
    5. Center-crop to 1:1 and downscale to a fixed square (_TARGET × _TARGET).
    6. Re-encode as compressed JPEG with all metadata stripped (exif=b"").
    7. Write to /app/media/<restaurant_id>/<uuid>.jpg

    Any source resolution/aspect ratio is accepted — the output is always a uniform
    square so product cards never stretch or up/down-scale awkwardly.

    Returns the public image_url path (/media/<restaurant_id>/<filename>).
    Raises ValueError on any validation failure (caller converts to HTTP 400).
    """
    if len(raw) > _MAX_BYTES:
        raise ValueError("Image exceeds the 25 MB size limit")

    if _detect_image_type(raw[:12]) is None:
        raise ValueError("Only JPEG, PNG, and WebP images are accepted")

    try:
        img = Image.open(io.BytesIO(raw))
        img.load()  # force full decode; catches truncated/corrupt and bomb payloads
    except Exception as exc:
        raise ValueError(f"Cannot decode image: {exc}") from exc

    # Honour the camera's EXIF orientation before we discard metadata, so portrait
    # phone photos aren't stored sideways.
    img = ImageOps.exif_transpose(img)

    # Flatten transparency onto white (JPEG has no alpha channel).
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[-1])
        img = background
    else:
        img = img.convert("RGB")

    # Center-crop to 1:1 and resize to the target square in one step.
    img = ImageOps.fit(img, (_TARGET, _TARGET), method=Image.LANCZOS, centering=(0.5, 0.5))

    # Re-encode as JPEG; exif=b"" strips all metadata.
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=_JPEG_QUALITY, optimize=True, progressive=True, exif=b"")

    filename = f"{uuid.uuid4()}.jpg"
    dest = _MEDIA_ROOT / str(restaurant_id) / filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(out.getvalue())

    return f"/media/{restaurant_id}/{filename}"


_BANNER_MAX_W: int = 2400   # hero images are wide — cap suited to a full-width banner
_BANNER_MAX_H: int = 1200
_BANNER_JPEG_QUALITY: int = 82


def validate_and_store_banner(raw: bytes, restaurant_id: uuid.UUID) -> str:
    """
    Banner (menu hero) variant of the product-image pipeline. Same validation
    chain — max byte size, magic-bytes type check (JPEG/PNG/WebP only), full
    Pillow decode, EXIF orientation + metadata strip, UUID filename under the
    tenant media path — but banner-specific dimension rules: the source keeps
    its aspect ratio (no square crop) and must fit within 2400×1200; anything
    larger is rejected rather than silently resized, so admins upload an asset
    actually prepared for the hero slot.

    Returns the public /media URL path. Raises ValueError on any failure
    (caller converts to HTTP 400).
    """
    if len(raw) > _MAX_BYTES:
        raise ValueError("Image exceeds the 25 MB size limit")

    if _detect_image_type(raw[:12]) is None:
        raise ValueError("Only JPEG, PNG, and WebP images are accepted")

    try:
        img = Image.open(io.BytesIO(raw))
        img.load()  # force full decode; catches truncated/corrupt and bomb payloads
    except Exception as exc:
        raise ValueError(f"Cannot decode image: {exc}") from exc

    img = ImageOps.exif_transpose(img)

    if img.width > _BANNER_MAX_W or img.height > _BANNER_MAX_H:
        raise ValueError(
            f"Banner image must be at most {_BANNER_MAX_W}x{_BANNER_MAX_H} pixels "
            f"(got {img.width}x{img.height})"
        )

    # Flatten transparency onto white (JPEG has no alpha channel).
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[-1])
        img = background
    else:
        img = img.convert("RGB")

    # Re-encode as JPEG; exif=b"" strips all metadata.
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=_BANNER_JPEG_QUALITY, optimize=True, progressive=True, exif=b"")

    filename = f"{uuid.uuid4()}.jpg"
    dest = _MEDIA_ROOT / str(restaurant_id) / filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(out.getvalue())

    return f"/media/{restaurant_id}/{filename}"


_POPUP_ILLUSTRATION_MAX_SIDE: int = 1000  # a small side illustration, not a hero
_POPUP_ILLUSTRATION_JPEG_QUALITY: int = 82


def validate_and_store_popup_illustration(raw: bytes, restaurant_id: uuid.UUID) -> str:
    """
    Scan-popup illustration variant of the image pipeline. Same validation
    chain as the banner — max byte size, magic-bytes type check (JPEG/PNG/WebP
    only), full Pillow decode, EXIF orientation + metadata strip, UUID
    filename under the tenant media path — but sized for a small side
    illustration rather than a wide hero: source aspect ratio is kept whole
    (no crop) and capped at 1000x1000, anything larger is rejected rather
    than silently resized.

    Returns the public /media URL path. Raises ValueError on any failure
    (caller converts to HTTP 400).
    """
    if len(raw) > _MAX_BYTES:
        raise ValueError("Image exceeds the 25 MB size limit")

    if _detect_image_type(raw[:12]) is None:
        raise ValueError("Only JPEG, PNG, and WebP images are accepted")

    try:
        img = Image.open(io.BytesIO(raw))
        img.load()  # force full decode; catches truncated/corrupt and bomb payloads
    except Exception as exc:
        raise ValueError(f"Cannot decode image: {exc}") from exc

    img = ImageOps.exif_transpose(img)

    if img.width > _POPUP_ILLUSTRATION_MAX_SIDE or img.height > _POPUP_ILLUSTRATION_MAX_SIDE:
        raise ValueError(
            f"Illustration must be at most {_POPUP_ILLUSTRATION_MAX_SIDE}x{_POPUP_ILLUSTRATION_MAX_SIDE} "
            f"pixels (got {img.width}x{img.height})"
        )

    # Flatten transparency onto white (JPEG has no alpha channel).
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[-1])
        img = background
    else:
        img = img.convert("RGB")

    # Re-encode as JPEG; exif=b"" strips all metadata.
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=_POPUP_ILLUSTRATION_JPEG_QUALITY, optimize=True, progressive=True, exif=b"")

    filename = f"{uuid.uuid4()}.jpg"
    dest = _MEDIA_ROOT / str(restaurant_id) / filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(out.getvalue())

    return f"/media/{restaurant_id}/{filename}"


_QR_MAX_SIDE: int = 1200  # QR codes are square-ish; cap the stored side


def validate_and_store_payment_qr(raw: bytes, restaurant_id: uuid.UUID) -> str:
    """
    Payment-QR variant of the image pipeline. Same validation chain as the
    banner — max byte size, magic-bytes type check (JPEG/PNG/WebP only), full
    Pillow decode, EXIF orientation + metadata strip, UUID filename under the
    tenant media path — but with two deliberate differences, because a QR code
    is machine-read rather than looked at:

    - NO center-crop. ImageOps.fit would slice off the finder patterns in the
      corners and make the code unscannable, so the source aspect ratio is
      kept whole and anything over 1200x1200 is rejected rather than resized.
    - Stored as LOSSLESS PNG, not JPEG. JPEG ringing around the high-contrast
      module edges degrades scan reliability, especially on a phone camera
      pointed at a screen.

    Returns the public /media URL path. Raises ValueError on any failure
    (caller converts to HTTP 400).
    """
    if len(raw) > _MAX_BYTES:
        raise ValueError("Image exceeds the 25 MB size limit")

    if _detect_image_type(raw[:12]) is None:
        raise ValueError("Only JPEG, PNG, and WebP images are accepted")

    try:
        img = Image.open(io.BytesIO(raw))
        img.load()  # force full decode; catches truncated/corrupt and bomb payloads
    except Exception as exc:
        raise ValueError(f"Cannot decode image: {exc}") from exc

    img = ImageOps.exif_transpose(img)

    if img.width > _QR_MAX_SIDE or img.height > _QR_MAX_SIDE:
        raise ValueError(
            f"Payment QR must be at most {_QR_MAX_SIDE}x{_QR_MAX_SIDE} pixels "
            f"(got {img.width}x{img.height})"
        )

    # Flatten transparency onto white so a transparent-background QR stays
    # black-on-white (a dark viewer background would otherwise kill contrast).
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[-1])
        img = background
    else:
        img = img.convert("RGB")

    # Re-encode as PNG. Pillow writes no EXIF here, so re-encoding is itself the
    # metadata strip; optimize=True is lossless (it only tunes the deflate pass).
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)

    filename = f"{uuid.uuid4()}.png"
    dest = _MEDIA_ROOT / str(restaurant_id) / filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(out.getvalue())

    return f"/media/{restaurant_id}/{filename}"


def store_model_bytes(data: bytes, restaurant_id: uuid.UUID, suffix: str = ".glb") -> str:
    """
    Write arbitrary 3D-model bytes (a compressed .glb or converted .usdz) under a
    server-generated UUID filename in the tenant media dir. Mirrors the image-store
    pattern (never trusts a client filename). Returns the public /media URL path.
    """
    if suffix not in (".glb", ".usdz"):
        raise ValueError(f"unsupported model suffix: {suffix!r}")
    filename = f"{uuid.uuid4()}{suffix}"
    dest_dir = _MEDIA_ROOT / str(restaurant_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    (dest_dir / filename).write_bytes(data)
    return f"/media/{restaurant_id}/{filename}"


def resolve_media_path(image_url: str) -> Path:
    """
    Map a stored `/media/<rid>/<file>` URL back to its on-disk path under _MEDIA_ROOT.

    Used by the AR provider adapters, which must read the raw image bytes (to upload
    to fal / base64 to Claude) since a relative /media URL isn't reachable by an
    external service. Raises ValueError for anything that isn't a controlled media URL.
    """
    if not image_url.startswith("/media/"):
        raise ValueError(f"not a /media URL: {image_url!r}")
    relative = image_url.removeprefix("/media/").lstrip("/")
    return _MEDIA_ROOT / relative


def delete_image(image_url: str) -> None:
    """
    Best-effort removal of a previously stored image.
    Used when replacing a product image — silently ignores missing files.
    """
    if not image_url.startswith("/media/"):
        return
    relative = image_url.removeprefix("/media/").lstrip("/")
    path = _MEDIA_ROOT / relative
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
