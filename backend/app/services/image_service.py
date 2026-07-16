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
