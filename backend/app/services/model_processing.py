"""
Post-generation model handling: pull the remote GLB into our own storage and
compress it, so the customer/admin viewer loads a small, self-hosted file instead
of a ~30 MB model on fal's servers.

Provider-agnostic (runs after any ThreeDProvider). Compression uses the
`gltf-transform` CLI baked into the backend image, targeting **quantized geometry
(KHR_mesh_quantization) + WebP textures** — both decode natively in
@google/model-viewer with no decoder and no external CDN fetch. (Meshopt is
deliberately NOT used: model-viewer 4.3.x ships no meshopt decoder and rejects
EXT_meshopt_compression GLBs with "setMeshoptDecoder must be called".)

Robustness: if the CLI is missing / errors / times out, we still store the *raw*
downloaded GLB locally (self-hosted + durable) and log a warning — compression is
best-effort and must never fail the generation job. Only a failed download raises.
"""

import logging
import subprocess
import tempfile
import uuid
from pathlib import Path

import httpx

from app.core.config import settings
from app.services import image_service

_log = logging.getLogger("app.ar")

_DOWNLOAD_TIMEOUT = 120.0   # seconds — fal GLBs can be tens of MB
_COMPRESS_TIMEOUT = 300     # seconds — gltf-transform on a large mesh

# USDZ source: Blender's glTF importer can't read meshopt, and it re-exports geometry
# uncompressed — so a raw hunyuan mesh (~30 MB, dense) balloons a USDZ to ~50 MB. We
# feed Blender a decimated, texture-capped, *uncompressed-geometry* GLB instead, which
# yields a ~2 MB USDZ. (Empirically: 51 MB → ~1.9 MB.)
_USDZ_TEXTURE_SIZE = "1024"
_USDZ_SIMPLIFY_ERROR = "0.005"


def _download(url: str, dest: Path) -> None:
    with httpx.stream("GET", url, timeout=_DOWNLOAD_TIMEOUT, follow_redirects=True) as r:
        r.raise_for_status()
        with dest.open("wb") as fh:
            for chunk in r.iter_bytes():
                fh.write(chunk)


def _compress(src: Path, dst: Path) -> None:
    """Web GLB: quantized geometry + WebP textures (decodes natively in model-viewer,
    no decoder). NOT meshopt — model-viewer has no meshopt decoder and won't render it."""
    subprocess.run(
        [
            "gltf-transform", "optimize", str(src), str(dst),
            "--compress", "quantize",
            "--texture-compress", "webp",
            "--texture-size", str(settings.AR_MODEL_TEXTURE_SIZE),
        ],
        check=True,
        capture_output=True,
        timeout=_COMPRESS_TIMEOUT,
    )


def _prep_usdz_source(src: Path, dst: Path) -> None:
    """USDZ source: decimated + texture-capped, UNcompressed geometry (Blender reads it)."""
    subprocess.run(
        [
            "gltf-transform", "optimize", str(src), str(dst),
            "--compress", "false",
            "--simplify", "true", "--simplify-error", _USDZ_SIMPLIFY_ERROR,
            "--texture-compress", "auto", "--texture-size", _USDZ_TEXTURE_SIZE,
        ],
        check=True,
        capture_output=True,
        timeout=_COMPRESS_TIMEOUT,
    )


def localize_and_compress(glb_url: str, restaurant_id: uuid.UUID) -> tuple[str, str]:
    """
    Download the generated GLB and store it under tenant media, returning
    `(web_glb_url, source_glb_url)`:
      - `web_glb_url`     — the compressed model the customer/admin viewer loads
                            (quantize + WebP). Falls back to the raw GLB if compression
                            is disabled or fails.
      - `source_glb_url`  — a decimated, *uncompressed-geometry* GLB for USDZ conversion
                            (Blender). Kept separate so Blender gets a small, importable
                            mesh regardless of how the web GLB is encoded. Equals
                            `web_glb_url` when no separate compressed file was produced.
    The caller deletes `source_glb_url` after USDZ, unless it equals `web_glb_url`.
    Raises only if the download itself fails.
    """
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "model.glb"
        _download(glb_url, raw)  # download failure propagates → job FAILED / retry
        raw_size = raw.stat().st_size

        # USDZ source (Blender-importable): decimated + texture-capped, uncompressed.
        # On failure fall back to the raw GLB (Blender still imports it, just larger).
        usdz_src = Path(tmp) / "model.src.glb"
        try:
            _prep_usdz_source(raw, usdz_src)
            source_url = image_service.store_model_bytes(usdz_src.read_bytes(), restaurant_id, ".glb")
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
            _log.warning("USDZ-source prep failed (%s); using raw GLB", type(exc).__name__)
            source_url = image_service.store_model_bytes(raw.read_bytes(), restaurant_id, ".glb")

        # Web GLB (viewer): quantize + WebP. On failure, serve the USDZ source instead.
        if settings.AR_COMPRESS_MODELS:
            out = Path(tmp) / "model.opt.glb"
            try:
                _compress(raw, out)
                data = out.read_bytes()
                _log.info(
                    "model compressed: %d → %d bytes (%.0f%%)",
                    raw_size, len(data), 100 * len(data) / raw_size if raw_size else 0,
                )
                return image_service.store_model_bytes(data, restaurant_id, ".glb"), source_url
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
                detail = getattr(exc, "stderr", b"") or b""
                _log.warning(
                    "model compression failed (%s); serving USDZ-source GLB. %s",
                    type(exc).__name__, detail[:500] if isinstance(detail, bytes) else detail,
                )

        return source_url, source_url
