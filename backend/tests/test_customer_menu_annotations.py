"""
Customer-facing AR nutrition hotspots — model_annotations exposed on GET /menu
(feat/customer-nutrition-hotspots).

CONFTEST TRAP (CLAUDE.md): `database` is session-scoped with no rollback, and
files run alphabetically — rows written by any test are visible to every later
one. Every test here builds its OWN restaurant/category/product via
_fresh_tenant()/_fresh_product() and asserts only against ids it created.

Guardrail under test: an AI-drafted (ai_estimated) nutrition tag must NEVER
reach a customer — wrong nutrition info is worse than none
(AR/ar-3d-model-nutrition.md guardrails). Annotations are only exposed when
BOTH the restaurant's stored ar_enabled flag is on AND the product's model is
published — the same gate that already governs model_glb_url.
"""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from tests.conftest import TEST_PASSWORD


# ── World builders ────────────────────────────────────────────────────────────

def _fresh_tenant(prefix: str = "an", ar_enabled: bool = True) -> dict:
    """A brand-new restaurant + settings + ADMIN, with the AR plan flag set
    explicitly (never relies on a plan preset default)."""
    from app.core import security
    from app.db.session import SessionLocal
    from app.models.enums import Role
    from app.models.restaurant import Restaurant, RestaurantSettings
    from app.models.user import User

    slug = f"{prefix}-{uuid.uuid4().hex[:10]}"
    db = SessionLocal()
    try:
        restaurant = Restaurant(
            name=f"Annotations {slug}", slug=slug, is_active=True, ar_enabled=ar_enabled,
        )
        db.add(restaurant)
        db.flush()
        db.add(RestaurantSettings(restaurant_id=restaurant.id))
        user = User(
            restaurant_id=restaurant.id,
            email=f"admin.{slug}@example.com",
            password_hash=security.hash_password(TEST_PASSWORD),
            role=Role.ADMIN,
        )
        db.add(user)
        db.flush()
        info = {"restaurant_id": str(restaurant.id), "slug": slug}
        db.commit()
    finally:
        db.close()
    return info


def _make_session(rid: str) -> str:
    """Table + ACTIVE session created directly (the QR scan path is tested elsewhere)."""
    from app.db.session import SessionLocal
    from app.models.table import Table, TableSession

    token = f"annotations-test-{uuid.uuid4()}"
    db = SessionLocal()
    try:
        table = Table(restaurant_id=uuid.UUID(rid), name=f"AN-{uuid.uuid4().hex[:8]}")
        db.add(table)
        db.flush()
        db.add(TableSession(
            restaurant_id=uuid.UUID(rid),
            table_id=table.id,
            token=token,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        ))
        db.commit()
    finally:
        db.close()
    return token


def _fresh_product(rid: str, *, published: bool, glb_url: str | None = "/media/x/model.glb") -> str:
    """A category + one active/available product, optionally with a published model."""
    from app.db.session import SessionLocal
    from app.models.category import Category
    from app.models.product import Product

    db = SessionLocal()
    try:
        restaurant_id = uuid.UUID(rid)
        category = Category(restaurant_id=restaurant_id, name=f"Cat-{uuid.uuid4().hex[:8]}")
        db.add(category)
        db.flush()
        product = Product(
            restaurant_id=restaurant_id,
            category_id=category.id,
            name=f"Product-{uuid.uuid4().hex[:8]}",
            base_price=Decimal("100.00"),
            model_published=published,
            model_glb_url=glb_url if published else None,
        )
        db.add(product)
        db.commit()
        return str(product.id)
    finally:
        db.close()


def _add_annotation(rid: str, pid: str, *, source: str, status: str, is_active: bool = True) -> str:
    from app.db.session import SessionLocal
    from app.models.ar import ModelAnnotation
    from app.models.enums import AnnotationSource, AnnotationStatus

    db = SessionLocal()
    try:
        ann = ModelAnnotation(
            id=uuid.uuid4(),
            restaurant_id=uuid.UUID(rid),
            product_id=uuid.UUID(pid),
            label="Cheese",
            position_x=0.01, position_y=0.03, position_z=0.02,
            normal_x=0.0, normal_y=1.0, normal_z=0.0,
            calories=Decimal("180.00"),
            protein_g=Decimal("12.00"),
            carbs_g=Decimal("2.00"),
            fat_g=Decimal("14.00"),
            allergens=["dairy"],
            source=AnnotationSource(source),
            status=AnnotationStatus(status),
            is_active=is_active,
        )
        db.add(ann)
        db.commit()
        return str(ann.id)
    finally:
        db.close()


def _find_product(menu_body: dict, product_id: str) -> dict:
    for cat in menu_body["categories"]:
        for p in cat["products"]:
            if p["id"] == product_id:
                return p
    raise AssertionError(f"product {product_id} not found in /menu response")


# ── Verified annotation reaches the customer ────────────────────────────────────

def test_verified_annotation_on_published_model_reaches_customer(client):
    tenant = _fresh_tenant()
    pid = _fresh_product(tenant["restaurant_id"], published=True)
    ann_id = _add_annotation(
        tenant["restaurant_id"], pid, source="AI", status="ADMIN_VERIFIED",
    )
    session_token = _make_session(tenant["restaurant_id"])

    resp = client.get("/menu", headers={"X-Session-Token": session_token})
    assert resp.status_code == 200, resp.text
    product = _find_product(resp.json(), pid)

    assert product["annotations"] is not None
    assert [a["id"] for a in product["annotations"]] == [ann_id]
    tag = product["annotations"][0]
    assert tag["label"] == "Cheese"
    assert tag["calories"] == "180.00"
    assert tag["protein_g"] == "12.00"
    assert tag["carbs_g"] == "2.00"
    assert tag["fat_g"] == "14.00"
    assert tag["allergens"] == ["dairy"]
    assert tag["status"] == "ADMIN_VERIFIED"
    assert {"position_x", "position_y", "position_z", "normal_x", "normal_y", "normal_z"} <= tag.keys()
    # Admin-only fields must never leak into the customer shape.
    assert "source" not in tag
    assert "product_id" not in tag
    assert "created_at" not in tag
    assert "updated_at" not in tag


# ── Guardrail: unverified AI drafts never reach the customer ───────────────────

def test_ai_estimated_annotation_excluded(client):
    tenant = _fresh_tenant()
    pid = _fresh_product(tenant["restaurant_id"], published=True)
    _add_annotation(tenant["restaurant_id"], pid, source="AI", status="AI_ESTIMATED")
    session_token = _make_session(tenant["restaurant_id"])

    resp = client.get("/menu", headers={"X-Session-Token": session_token})
    assert resp.status_code == 200, resp.text
    product = _find_product(resp.json(), pid)

    assert product["annotations"] == []


def test_soft_deleted_annotation_excluded(client):
    tenant = _fresh_tenant()
    pid = _fresh_product(tenant["restaurant_id"], published=True)
    _add_annotation(
        tenant["restaurant_id"], pid, source="MANUAL", status="ADMIN_VERIFIED", is_active=False,
    )
    session_token = _make_session(tenant["restaurant_id"])

    resp = client.get("/menu", headers={"X-Session-Token": session_token})
    assert resp.status_code == 200, resp.text
    product = _find_product(resp.json(), pid)

    assert product["annotations"] == []


# ── Publish gate: verified annotations on an unpublished model are withheld ────

def test_annotations_withheld_when_model_not_published(client):
    tenant = _fresh_tenant()
    pid = _fresh_product(tenant["restaurant_id"], published=False, glb_url=None)
    _add_annotation(tenant["restaurant_id"], pid, source="MANUAL", status="ADMIN_VERIFIED")
    session_token = _make_session(tenant["restaurant_id"])

    resp = client.get("/menu", headers={"X-Session-Token": session_token})
    assert resp.status_code == 200, resp.text
    product = _find_product(resp.json(), pid)

    assert product["model_glb_url"] is None
    assert product["annotations"] is None


# ── Restaurant-level AR gate overrides a published product ─────────────────────

def test_annotations_withheld_when_restaurant_ar_disabled(client):
    tenant = _fresh_tenant(ar_enabled=False)
    pid = _fresh_product(tenant["restaurant_id"], published=True)
    _add_annotation(tenant["restaurant_id"], pid, source="MANUAL", status="ADMIN_VERIFIED")
    session_token = _make_session(tenant["restaurant_id"])

    resp = client.get("/menu", headers={"X-Session-Token": session_token})
    assert resp.status_code == 200, resp.text
    product = _find_product(resp.json(), pid)

    assert product["model_glb_url"] is None
    assert product["annotations"] is None


# ── No annotations at all: shape is unchanged, no empty-vs-null surprise ───────

def test_product_with_no_annotations_and_no_model_is_unaffected(client):
    """A plain product (no AR at all) — the pre-existing shape must be untouched."""
    tenant = _fresh_tenant()
    pid = _fresh_product(tenant["restaurant_id"], published=False, glb_url=None)
    session_token = _make_session(tenant["restaurant_id"])

    resp = client.get("/menu", headers={"X-Session-Token": session_token})
    assert resp.status_code == 200, resp.text
    product = _find_product(resp.json(), pid)

    assert product["model_glb_url"] is None
    assert product["model_usdz_url"] is None
    assert product["annotations"] is None
