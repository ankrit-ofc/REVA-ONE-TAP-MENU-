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

Layout: a wrapping grid of small, non-interactive "chip" boxes (one per
annotation), styled to match the in-page AR hotspot cards (TableArView.module
.css's .card/.cardLabel/.cardMacros/.cardAllergens) so the two nutrition
surfaces read as one design language, even though this page can't see the
customer app's CSS or --menu-accent (it's rendered standalone, inside Quick
Look's own sandboxed view) — colours below are fixed, not theme-derived.

Apple's banner view does NOT scroll: content that overflows is silently
clipped, confirmed on a real device. So this route caps how many boxes it
ever renders (see _MAX_VISIBLE below) and appends a "+N more" box instead of
letting Apple cut one off mid-element. The banner is a single tap target with
no per-box interactivity (Apple platform constraint) — boxes are plain
display, nothing here should read as tappable.
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

# Apple doesn't publish exact pixel heights for customHeight="large", and this
# view never scrolls, so overflow has to be prevented rather than detected.
# Conservative worst-case budget for an iPhone mini-width screen (~375pt) at
# "large" height: a ~20pt single-line header, then a 2-column grid where each
# box (label + macro line + optional allergen line + padding/gap) runs
# ~50-56pt tall — roughly 4 grid rows fit before the sheet's available height
# is used up, i.e. ~8 boxes. _MAX_VISIBLE stays one row short of that on
# purpose (room for the "+more" box itself, and margin for a taller product
# name or an allergen line pushing a box's height up) — verify against a real
# device if this ever feels too conservative or still clips.
_MAX_VISIBLE = 7

_STYLE = """
* { box-sizing: border-box; }
body {
  margin: 0;
  padding: 0.625rem 0.75rem 0.75rem;
  font-family: -apple-system, BlinkMacSystemFont, 'Helvetica Neue', Arial, sans-serif;
  background: #fff;
  color: #1a1a1a;
  -webkit-text-size-adjust: 100%;
}
h1 {
  margin: 0 0 0.5rem;
  font-size: 0.8125rem;
  font-weight: 700;
  line-height: 1.2;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(6.25rem, 1fr));
  gap: 0.4rem;
}
.box {
  background: rgba(15, 23, 42, 0.92);
  border-radius: 0.5rem;
  padding: 0.375rem 0.5rem;
  min-width: 0;
}
.label {
  margin: 0;
  font-size: 0.6875rem;
  font-weight: 700;
  color: #fff;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.macro {
  margin: 0.15rem 0 0;
  font-size: 0.625rem;
  font-weight: 600;
  color: #a7f3d0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.al {
  margin: 0.15rem 0 0;
  font-size: 0.5625rem;
  font-weight: 600;
  color: #fca5a5;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.more {
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
}
.moreText {
  margin: 0;
  font-size: 0.6875rem;
  font-weight: 600;
  color: #cbd5e1;
}
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


def _macro_line(a: AnnotationPublic) -> str | None:
    """Compact "420 · P8 C58 F16" form — no units, calories bare, macros
    prefixed with their initial. Omits any missing value; None if none present."""
    parts = []
    kcal = _fmt_macro(a.calories)
    if kcal:
        parts.append(kcal)
    protein = _fmt_macro(a.protein_g)
    if protein:
        parts.append(f"P{protein}")
    carbs = _fmt_macro(a.carbs_g)
    if carbs:
        parts.append(f"C{carbs}")
    fat = _fmt_macro(a.fat_g)
    if fat:
        parts.append(f"F{fat}")
    return " · ".join(parts) if parts else None


def _box_html(a: AnnotationPublic) -> str:
    macro = _macro_line(a)
    macro_html = f'<p class="macro">{_esc(macro)}</p>' if macro else ""
    # Abbreviated via the same single-line ellipsis as the label, rather than
    # hand-truncating the list server-side — one visual treatment to reason
    # about, and it degrades the same way a long label does.
    allergens_html = (
        f'<p class="al">{_esc(", ".join(a.allergens))}</p>' if a.allergens else ""
    )
    return f'<div class="box"><p class="label">{_esc(a.label)}</p>{macro_html}{allergens_html}</div>'


def _more_box_html(count: int) -> str:
    return f'<div class="box more"><p class="moreText">+{count} more in menu</p></div>'


def _render(title: str, grid_html: str) -> str:
    return (
        "<!doctype html><html><head>"
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{title}</title>"
        f"<style>{_STYLE}</style>"
        "</head><body>"
        f"<h1>{title}</h1>"
        f"{grid_html}"
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
    if annotations:
        visible = annotations[:_MAX_VISIBLE]
        remaining = len(annotations) - len(visible)
        boxes = "".join(_box_html(a) for a in visible)
        if remaining > 0:
            boxes += _more_box_html(remaining)
        grid_html = f'<div class="grid">{boxes}</div>'
    else:
        grid_html = '<p class="empty">Nutrition info coming soon.</p>'

    # Short public cache: this changes only when an admin edits/re-verifies
    # annotations, not on every request, but it's not immutable like /media/*.
    return HTMLResponse(content=_render(title, grid_html), headers={"Cache-Control": "public, max-age=300"})
