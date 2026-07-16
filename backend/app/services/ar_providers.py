"""
Provider adapters for the AR pipeline — the seam that lets 3D generation, nutrition
marking, and USDZ conversion move from stubs → hosted APIs → own GPU by config swap,
with no changes to the pipeline or the rest of the app.

Two families of adapter live here:
  - DUMMY: no external calls / keys / deps — the dummy 3D provider assigns the
    hardcoded spike model to every product, and the dummy marker returns canned
    pizza components. Used until real keys are configured.
  - REAL: `FalThreeDProvider` (fal.ai image-to-3D) and `ClaudeMarkingProvider`
    (Anthropic vision → per-component nutrition). Selected by config; both keys
    stay server-side. USDZ conversion + evf-sam segmentation remain later work.
"""

import base64
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Protocol

from app.core.config import settings
from app.models.enums import ProductView, ThreeDModelKey
from app.services import image_service

_log = logging.getLogger("app.ar")


@dataclass
class GeneratedModel:
    """A produced 3D model (URLs the customer viewer will load)."""
    glb_url: str


@dataclass
class DraftAnnotation:
    """A per-component nutrition draft from the marking track (AI-estimated)."""
    label: str
    calories: Decimal | None = None
    protein_g: Decimal | None = None
    carbs_g: Decimal | None = None
    fat_g: Decimal | None = None
    allergens: list[str] = field(default_factory=list)


# ── Protocols ───────────────────────────────────────────────────────────────────

class ThreeDProvider(Protocol):
    name: str
    def generate(self, views: dict[ProductView, str], model_key: str) -> GeneratedModel: ...


class MarkingProvider(Protocol):
    name: str
    def mark(self, top_image_url: str) -> list[DraftAnnotation]: ...


class UsdzConverter(Protocol):
    name: str
    def to_usdz(self, glb_url: str) -> str: ...


# ── Dummy implementations ─────────────────────────────────────────────────────────

class DummyThreeDProvider:
    """Returns the hardcoded spike GLB — no generation, no external call."""
    name = "dummy"

    def generate(self, views: dict[ProductView, str], model_key: str = "") -> GeneratedModel:
        return GeneratedModel(glb_url=settings.AR_SPIKE_GLB_URL)


class DummyUsdzConverter:
    """Returns the hardcoded spike USDZ — stands in for GLB→USDZ conversion."""
    name = "dummy"

    def to_usdz(self, glb_url: str) -> str:
        return settings.AR_SPIKE_USDZ_URL


class DummyMarkingProvider:
    """Returns a canned set of pizza components with plausible per-component nutrition."""
    name = "dummy"

    def mark(self, top_image_url: str) -> list[DraftAnnotation]:
        return [
            DraftAnnotation(
                label="Crust",
                calories=Decimal("220"),
                protein_g=Decimal("7"),
                carbs_g=Decimal("42"),
                fat_g=Decimal("3"),
                allergens=["gluten"],
            ),
            DraftAnnotation(
                label="Cheese",
                calories=Decimal("180"),
                protein_g=Decimal("12"),
                carbs_g=Decimal("2"),
                fat_g=Decimal("14"),
                allergens=["dairy"],
            ),
            DraftAnnotation(
                label="Tomato sauce",
                calories=Decimal("35"),
                protein_g=Decimal("2"),
                carbs_g=Decimal("7"),
                fat_g=Decimal("0.5"),
                allergens=[],
            ),
        ]


# ── Real implementations ──────────────────────────────────────────────────────────

def _to_decimal(value: object) -> Decimal | None:
    """Coerce a model-returned number/string to Decimal; None on missing/garbage."""
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


# ── fal 3D model registry ─────────────────────────────────────────────────────────
# Each model is an admin-selectable option. Endpoints have different input shapes but
# all return the GLB at model_mesh.url / model_glb.url (see _extract_glb_url). The
# admin picks per generation; the choice is stored on the generation job's `provider`.

@dataclass(frozen=True)
class ThreeDModelSpec:
    key: str
    label: str
    endpoint: str
    required_views: tuple[ProductView, ...]
    # Build the fal `arguments` from a {view: uploaded_fal_url} map for required_views.
    build_inputs: Callable[[dict[ProductView, str]], dict]


_V = ProductView
FAL_THREED_MODELS: dict[str, ThreeDModelSpec] = {
    ThreeDModelKey.HUNYUAN3D_V3.value: ThreeDModelSpec(
        key=ThreeDModelKey.HUNYUAN3D_V3.value,
        label="Hunyuan3D v3 (single image)",
        endpoint="fal-ai/hunyuan3d-v3/image-to-3d",
        required_views=(_V.FRONT,),
        build_inputs=lambda u: {"input_image_url": u[_V.FRONT]},
    ),
    ThreeDModelKey.HUNYUAN3D_V2_MULTIVIEW.value: ThreeDModelSpec(
        key=ThreeDModelKey.HUNYUAN3D_V2_MULTIVIEW.value,
        label="Hunyuan3D v2 multi-view",
        endpoint="fal-ai/hunyuan3d/v2/multi-view",
        required_views=(_V.FRONT, _V.BACK, _V.LEFT),
        # textured_mesh so food renders with colour (not a grey mesh); ~3x white price.
        build_inputs=lambda u: {
            "front_image_url": u[_V.FRONT],
            "back_image_url": u[_V.BACK],
            "left_image_url": u[_V.LEFT],
            "textured_mesh": True,
        },
    ),
    ThreeDModelKey.TRELLIS_MULTI.value: ThreeDModelSpec(
        key=ThreeDModelKey.TRELLIS_MULTI.value,
        label="Trellis (multi-image)",
        endpoint="fal-ai/trellis/multi",
        required_views=(_V.FRONT, _V.BACK, _V.LEFT, _V.RIGHT),
        build_inputs=lambda u: {
            "image_urls": [u[_V.FRONT], u[_V.BACK], u[_V.LEFT], u[_V.RIGHT]],
        },
    ),
}


def resolve_threed_spec(model_key: str) -> ThreeDModelSpec:
    """Return the spec for a model key, falling back to the configured default."""
    return (
        FAL_THREED_MODELS.get(model_key)
        or FAL_THREED_MODELS.get(settings.AR_DEFAULT_THREED_MODEL)
        or FAL_THREED_MODELS[ThreeDModelKey.HUNYUAN3D_V2_MULTIVIEW.value]
    )


class FalThreeDProvider:
    """
    fal.ai image-to-3D. The concrete model is chosen per generation (admin dropdown)
    from FAL_THREED_MODELS: v3 (single image), v2 multi-view, or Trellis. Uploads only
    the views that model needs to fal storage (a relative /media URL isn't reachable by
    fal's servers) and returns the generated GLB URL.
    """
    name = "fal"

    def generate(self, views: dict[ProductView, str], model_key: str) -> GeneratedModel:
        import fal_client

        if not settings.FAL_KEY:
            raise ValueError("FAL_KEY is not set")
        spec = resolve_threed_spec(model_key)
        missing = [v.value for v in spec.required_views if not views.get(v)]
        if missing:
            raise ValueError(f"{spec.key} needs views {missing}")

        # Explicit client so we never depend on FAL_KEY being injected into os.environ.
        client = fal_client.SyncClient(key=settings.FAL_KEY)
        uploaded = {
            v: client.upload_file(str(image_service.resolve_media_path(views[v])))
            for v in spec.required_views
        }

        result = client.subscribe(
            spec.endpoint,
            arguments=spec.build_inputs(uploaded),
            with_logs=False,
        )
        glb_url = self._extract_glb_url(result)
        if not glb_url:
            raise ValueError(f"fal returned no model mesh URL: keys={list(result)}")
        _log.info("fal 3D generation ok (%s): %s", spec.key, glb_url)
        return GeneratedModel(glb_url=glb_url)

    @staticmethod
    def _extract_glb_url(result: dict) -> str | None:
        # hunyuan3d returns {"model_mesh": {"url": ...}}; be tolerant of near variants.
        for key in ("model_mesh", "model_glb", "mesh", "model"):
            node = result.get(key)
            if isinstance(node, dict) and node.get("url"):
                return node["url"]
            if isinstance(node, str) and node.startswith("http"):
                return node
        return None


class SidecarUsdzConverter:
    """
    GLB → USDZ via the headless-Blender sidecar. Takes the LOCAL compressed GLB
    (a /media URL), asks the sidecar to convert it (files exchanged over the shared
    /media volume by path), and returns the local /media USDZ URL.
    """
    name = "sidecar"

    def to_usdz(self, glb_url: str) -> str:
        import httpx

        if not glb_url.startswith("/media/"):
            raise ValueError(f"expected a local /media glb url, got {glb_url!r}")
        rel = glb_url.removeprefix("/media/").lstrip("/")  # "<rid>/<uuid>.glb"

        resp = httpx.post(
            f"{settings.MODEL_CONVERTER_URL}/to-usdz",
            json={"glb_path": rel},
            timeout=600.0,
        )
        resp.raise_for_status()
        usdz_rel = resp.json()["usdz_path"]
        _log.info("usdz conversion ok: %s", usdz_rel)
        return f"/media/{usdz_rel}"


class ClaudeMarkingProvider:
    """
    Anthropic vision → per-component nutrition drafts from the top-down photo. Uses a
    forced tool call for reliable structured JSON. Model id is config (AR_MARKING_MODEL);
    the same key covers Haiku/Sonnet/Opus. Keeps output small to protect the budget.
    """
    name = "claude"

    _TOOL = {
        "name": "record_components",
        "description": "Record the visible food components and their estimated nutrition.",
        "input_schema": {
            "type": "object",
            "properties": {
                "components": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string", "description": "Component name, e.g. 'Crust'"},
                            "calories": {"type": "number"},
                            "protein_g": {"type": "number"},
                            "carbs_g": {"type": "number"},
                            "fat_g": {"type": "number"},
                            "allergens": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["label"],
                    },
                }
            },
            "required": ["components"],
        },
    }

    def mark(self, top_image_url: str) -> list[DraftAnnotation]:
        import anthropic

        if not top_image_url:
            raise ValueError("no top-view image for nutrition marking")

        local_path = image_service.resolve_media_path(top_image_url)
        media_type = "image/png" if local_path.suffix.lower() == ".png" else "image/jpeg"
        b64 = base64.standard_b64encode(local_path.read_bytes()).decode("ascii")

        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        message = client.messages.create(
            model=settings.AR_MARKING_MODEL,
            max_tokens=1024,
            tools=[self._TOOL],
            tool_choice={"type": "tool", "name": "record_components"},
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": b64},
                    },
                    {
                        "type": "text",
                        "text": (
                            "This is a top-down photo of a single food dish. Identify its "
                            "visible components (e.g. crust, cheese, sauce, toppings) and "
                            "estimate per-component nutrition for the portion shown. Record "
                            "them with the record_components tool. Use grams for macros and "
                            "list common allergens (gluten, dairy, nuts, egg, soy, shellfish)."
                        ),
                    },
                ],
            }],
        )

        components: list[dict] = []
        for block in message.content:
            if block.type == "tool_use" and block.name == "record_components":
                components = block.input.get("components", [])
                break
        if not components:
            raise ValueError("Claude returned no components")

        drafts: list[DraftAnnotation] = []
        for c in components:
            label = (c.get("label") or "").strip()
            if not label:
                continue
            allergens = [str(a) for a in (c.get("allergens") or []) if str(a).strip()]
            drafts.append(DraftAnnotation(
                label=label,
                calories=_to_decimal(c.get("calories")),
                protein_g=_to_decimal(c.get("protein_g")),
                carbs_g=_to_decimal(c.get("carbs_g")),
                fat_g=_to_decimal(c.get("fat_g")),
                allergens=allergens,
            ))
        if not drafts:
            raise ValueError("Claude components had no usable labels")
        _log.info("claude marking ok: %d components", len(drafts))
        return drafts


# ── Factories (config-selected) ──────────────────────────────────────────────────

def get_threed_provider() -> ThreeDProvider:
    if settings.AR_THREED_PROVIDER == "dummy":
        return DummyThreeDProvider()
    if settings.AR_THREED_PROVIDER == "fal":
        return FalThreeDProvider()
    raise ValueError(f"Unknown AR_THREED_PROVIDER: {settings.AR_THREED_PROVIDER!r}")


def get_marking_provider() -> MarkingProvider:
    if settings.AR_MARKING_PROVIDER == "dummy":
        return DummyMarkingProvider()
    if settings.AR_MARKING_PROVIDER == "claude":
        return ClaudeMarkingProvider()
    raise ValueError(f"Unknown AR_MARKING_PROVIDER: {settings.AR_MARKING_PROVIDER!r}")


def get_usdz_converter() -> UsdzConverter:
    if settings.AR_USDZ_CONVERTER == "dummy":
        return DummyUsdzConverter()
    if settings.AR_USDZ_CONVERTER == "sidecar":
        return SidecarUsdzConverter()
    raise ValueError(f"Unknown AR_USDZ_CONVERTER: {settings.AR_USDZ_CONVERTER!r}")
