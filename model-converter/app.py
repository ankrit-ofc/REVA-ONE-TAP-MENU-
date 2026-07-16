"""
Tiny HTTP wrapper around headless Blender for GLB → USDZ conversion.

The backend and this sidecar share the /media volume. The backend passes a
media-relative path to an existing .glb; we convert it with Blender and write the
.usdz alongside it (same tenant dir), returning the new media-relative path. No file
bytes cross the wire — only paths — so large models never inflate request bodies.
"""

import logging
import subprocess
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict

_MEDIA_ROOT = Path("/media").resolve()
_CONVERT_TIMEOUT = 600  # seconds

app = FastAPI(title="model-converter")
_log = logging.getLogger("uvicorn.error")


class ConvertIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    glb_path: str  # media-relative, e.g. "<restaurant_id>/<uuid>.glb"


class ConvertOut(BaseModel):
    usdz_path: str  # media-relative, e.g. "<restaurant_id>/<uuid>.usdz"
    size: int


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _resolve_inside_media(rel: str) -> Path:
    """Resolve a media-relative path, rejecting traversal outside /media."""
    p = (_MEDIA_ROOT / rel).resolve()
    if p != _MEDIA_ROOT and _MEDIA_ROOT not in p.parents:
        raise HTTPException(status_code=400, detail="path escapes media root")
    return p


@app.post("/to-usdz", response_model=ConvertOut)
def to_usdz(body: ConvertIn) -> ConvertOut:
    src = _resolve_inside_media(body.glb_path)
    if src.suffix.lower() != ".glb" or not src.is_file():
        raise HTTPException(status_code=404, detail="glb not found")

    filename = f"{uuid.uuid4()}.usdz"
    dst = src.parent / filename

    proc = subprocess.run(
        ["blender", "-b", "--factory-startup", "-noaudio",
         "-P", "/srv/glb_to_usdz.py", "--", str(src), str(dst)],
        capture_output=True, timeout=_CONVERT_TIMEOUT,
    )
    if proc.returncode != 0 or not dst.exists():
        _log.error("blender conversion failed: %s", proc.stderr.decode(errors="replace")[-2000:])
        raise HTTPException(status_code=500, detail="conversion failed")

    return ConvertOut(usdz_path=f"{src.parent.name}/{filename}", size=dst.stat().st_size)
