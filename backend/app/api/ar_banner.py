"""
Public AR Quick Look custom banner.

Apple's AR Quick Look loads the URL from a `rel="ar"` anchor's
`#custom=<url>` fragment in its own sandboxed web view — it never carries
the customer's session cookies or storage, so this route is intentionally
public, scoped only by the product's own UUID. It mirrors /media/*'s existing
posture (see admin_menu.py's media_router): UUID ids resist enumeration, and
the data returned here is exactly what a customer with an active table
session already sees via GET /menu's ProductPublic.annotations (same filter,
see menu_service.get_public_annotations) — never more.

Server-rendered plain HTML, not the SPA: Apple's banner view should load
near-instantly, and there's nothing here for client JS to do.
"""

import uuid
from html import escape

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session, selectinload

from app.core.deps import get_db
from app.models.product import Product
from app.models.restaurant import Restaurant
from app.schemas.menu import AnnotationPublic
from app.services.menu_service import get_public_annotations
from app.services.plan_features import stored_features

router = APIRouter(tags=["ar-banner"])

_STYLE = """
* { box-sizing: border-box; }
body {
  margin: 0;
  padding: 0.75rem 1rem 1rem;
  font-family: -apple-system, BlinkMacSystemFont, 'Helvetica Neue', Arial, sans-serif;
  background: #fff;
  color: #1a1a1a;
  -webkit-text-size-adjust: 100%;
}
h1 {
  margin: 0 0 0.5rem;
  font-size: 0.9375rem;
  font-weight: 700;
  line-height: 1.25;
}
.row { padding: 0.4rem 0; border-top: 1px solid #eee; }
.row:first-of-type { border-top: none; }
.n { margin: 0; font-size: 0.8125rem; font-weight: 600; }
.m { margin: 0.125rem 0 0; font-size: 0.75rem; color: #555; }
.al { margin: 0.125rem 0 0; font-size: 0.6875rem; color: #b91c1c; }
.empty { margin: 0; font-size: 0.8125rem; color: #666; }
"""


def _esc(value: str) -> str:
    return escape(value, quote=True)


def _fmt_macro(value) -> str | None:
    """Mirrors the frontend's formatMacro (TableArView.tsx): drop the decimal
    for whole numbers, one decimal place otherwise."""
    if value is None:
        return None
    f = float(value)
    return str(int(f)) if f == int(f) else f"{f:.1f}"


def _row_html(a: AnnotationPublic) -> str:
    macro_parts = []
    kcal = _fmt_macro(a.calories)
    protein = _fmt_macro(a.protein_g)
    carbs = _fmt_macro(a.carbs_g)
    fat = _fmt_macro(a.fat_g)
    if kcal:
        macro_parts.append(f"{kcal} kcal")
    if protein:
        macro_parts.append(f"P {protein}g")
    if carbs:
        macro_parts.append(f"C {carbs}g")
    if fat:
        macro_parts.append(f"F {fat}g")
    macros_html = f'<p class="m">{_esc(" · ".join(macro_parts))}</p>' if macro_parts else ""
    allergens_html = (
        f'<p class="al">Contains: {_esc(", ".join(a.allergens))}</p>' if a.allergens else ""
    )
    return f'<div class="row"><p class="n">{_esc(a.label)}</p>{macros_html}{allergens_html}</div>'


def _render(title: str, body: str) -> str:
    return (
        "<!doctype html><html><head>"
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{title}</title>"
        f"<style>{_STYLE}</style>"
        "</head><body>"
        f"<h1>{title}</h1>"
        f"{body}"
        "</body></html>"
    )


@router.get("/ar-banner/{product_id}", response_class=HTMLResponse)
def ar_banner(product_id: uuid.UUID, db: Session = Depends(get_db)) -> HTMLResponse:
    product = db.get(Product, product_id, options=[selectinload(Product.annotations)])
    if product is None or not product.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    restaurant = db.get(Restaurant, product.restaurant_id)
    if restaurant is None or not restaurant.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    ar_published = (
        stored_features(restaurant).ar_enabled
        and product.model_published
        and bool(product.model_glb_url)
    )
    annotations = get_public_annotations(product, ar_published=ar_published) or []

    title = _esc(product.name)
    body = (
        "".join(_row_html(a) for a in annotations)
        if annotations
        else '<p class="empty">Nutrition info coming soon.</p>'
    )

    # Short public cache: this changes only when an admin edits/re-verifies
    # annotations, not on every request, but it's not immutable like /media/*.
    return HTMLResponse(content=_render(title, body), headers={"Cache-Control": "public, max-age=300"})
