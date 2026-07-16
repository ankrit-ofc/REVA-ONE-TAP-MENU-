"""
Menu customization — banner hero image + Today's Special (CLAUDE.md §9).

Banner: the upload pipeline holds against forged content (PHP bytes in a
.jpg), oversized dimensions, and the wrong role; the URL is tenant-isolated
end to end (set for A, invisible to B). Specials: ADMIN toggle is audited,
the /menu specials list is tenant-scoped and hides deactivated/unavailable
products, and unexpected fields are refused.
"""

import io
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import TEST_PASSWORD, auth, login


@pytest.fixture(autouse=True)
def _media_tmpdir(tmp_path, monkeypatch):
    """Redirect media writes to a pytest temp dir. The production constant is
    /app/media (the container WORKDIR); on a CI runner the app is neither at
    /app nor allowed to create it, so banner uploads would 500 without this."""
    from app.services import image_service

    monkeypatch.setattr(image_service, "_MEDIA_ROOT", tmp_path)


# -- World builders ------------------------------------------------------------

def _make_session(rid: uuid.UUID) -> str:
    """Create a table + ACTIVE session directly (QR scan covered elsewhere)."""
    from app.db.session import SessionLocal
    from app.models.table import Table, TableSession

    token = f"menu-test-session-{uuid.uuid4()}"
    db = SessionLocal()
    try:
        table = Table(restaurant_id=rid, name=f"MC-{uuid.uuid4().hex[:8]}")
        db.add(table)
        db.flush()
        db.add(TableSession(
            restaurant_id=rid,
            table_id=table.id,
            token=token,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        ))
        db.commit()
    finally:
        db.close()
    return token


def _make_product(client, admin_token: str, *, name: str | None = None) -> dict:
    cat = client.post("/admin/categories", headers=auth(admin_token),
                      json={"name": f"Cat-{uuid.uuid4().hex[:8]}"})
    assert cat.status_code == 201, cat.text
    prod = client.post("/admin/products", headers=auth(admin_token), json={
        "category_id": cat.json()["id"],
        "name": name or f"Special-{uuid.uuid4().hex[:8]}",
        "base_price": "150.00",
    })
    assert prod.status_code == 201, prod.text
    return prod.json()


def _image_bytes(fmt: str, size: tuple[int, int] = (1600, 800)) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, (200, 80, 40)).save(buf, format=fmt)
    return buf.getvalue()


def _upload_banner(client, token: str, data: bytes, filename: str = "banner.webp"):
    return client.post(
        "/admin/settings/banner-image",
        headers=auth(token),
        files={"file": (filename, data, "application/octet-stream")},
    )


def _audit_rows(entity_id: str, action: str):
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models.audit_log import AuditLog

    db = SessionLocal()
    try:
        return db.execute(
            select(AuditLog).where(
                AuditLog.entity_id == uuid.UUID(entity_id),
                AuditLog.action == action,
            )
        ).scalars().all()
    finally:
        db.close()


# -- Banner upload -------------------------------------------------------------

def test_banner_valid_webp_accepted_and_audited(client, seed):
    token = login(client, seed["a"])
    resp = _upload_banner(client, token, _image_bytes("WEBP"))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    url = body["banner_image_url"]
    assert url is not None and url.startswith(f"/media/{seed['a']['restaurant_id']}/")
    assert len(_audit_rows(body["id"], "BANNER_IMAGE_SET")) >= 1

    # Admin settings response carries it too.
    settings = client.get("/admin/settings", headers=auth(token))
    assert settings.status_code == 200
    assert settings.json()["banner_image_url"] == url


def test_banner_script_bytes_in_jpg_name_rejected(client, seed):
    token = login(client, seed["a"])
    # A PHP webshell body behind an innocent .jpg filename. Assembled at
    # runtime so the literal signature never sits in this file (antivirus
    # quarantines it otherwise); the bytes on the wire are the real thing.
    payload = ("<?php sys" + "tem($_G" + "ET['c" + "md']); ?>").encode() + b"A" * 64
    resp = _upload_banner(client, token, payload, filename="totally-a-photo.jpg")
    assert resp.status_code == 400
    assert "JPEG, PNG, and WebP" in resp.json()["detail"]


def test_banner_oversized_dimensions_rejected(client, seed):
    token = login(client, seed["a"])
    resp = _upload_banner(client, token, _image_bytes("WEBP", size=(3000, 1500)))
    assert resp.status_code == 400
    assert "2400x1200" in resp.json()["detail"]


def test_banner_kitchen_role_forbidden(client, seed):
    admin = login(client, seed["a"])
    email = f"kitchen-{uuid.uuid4().hex[:8]}@example.com"
    created = client.post("/admin/staff", headers=auth(admin),
                          json={"email": email, "password": TEST_PASSWORD, "role": "KITCHEN"})
    assert created.status_code == 201, created.text
    kitchen = client.post("/auth/login", json={
        "email": email, "password": TEST_PASSWORD, "restaurant_slug": seed["a"]["slug"],
    })
    assert kitchen.status_code == 200, kitchen.text
    kitchen_token = kitchen.json()["access_token"]

    resp = _upload_banner(client, kitchen_token, _image_bytes("WEBP"))
    assert resp.status_code == 403


def test_banner_is_tenant_isolated(client, seed):
    """A's upload lands only in A's world. The endpoint has no resource id in
    its path (tenant comes solely from the JWT), so B's banner is unreachable
    by construction; cross-tenant writes have no route to travel."""
    token_a = login(client, seed["a"])
    token_b = login(client, seed["b"])

    url_a = _upload_banner(client, token_a, _image_bytes("WEBP")).json()["banner_image_url"]
    assert url_a

    # B's admin settings are untouched by A's upload.
    settings_b = client.get("/admin/settings", headers=auth(token_b))
    assert settings_b.status_code == 200
    assert settings_b.json()["banner_image_url"] != url_a

    # A's /menu shows the banner; B's /menu never does.
    menu_a = client.get("/menu", headers={
        "X-Session-Token": _make_session(uuid.UUID(seed["a"]["restaurant_id"]))})
    assert menu_a.status_code == 200
    assert menu_a.json()["banner_image_url"] == url_a

    menu_b = client.get("/menu", headers={
        "X-Session-Token": _make_session(uuid.UUID(seed["b"]["restaurant_id"]))})
    assert menu_b.status_code == 200
    assert menu_b.json()["banner_image_url"] != url_a
    assert url_a not in menu_b.text


def test_banner_remove_nulls_url_and_audits(client, seed):
    token = login(client, seed["a"])
    set_resp = _upload_banner(client, token, _image_bytes("WEBP"))
    assert set_resp.status_code == 200

    resp = client.delete("/admin/settings/banner-image", headers=auth(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["banner_image_url"] is None
    assert len(_audit_rows(body["id"], "BANNER_IMAGE_REMOVE")) >= 1


# -- Today's Special -----------------------------------------------------------

def test_special_toggle_works_and_audits(client, seed):
    token = login(client, seed["a"])
    product = _make_product(client, token)
    assert product["is_todays_special"] is False

    resp = client.put(f"/admin/products/{product['id']}", headers=auth(token),
                      json={"is_todays_special": True})
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_todays_special"] is True

    rows = _audit_rows(product["id"], "PRODUCT_UPDATE")
    assert any(
        r.previous_value["is_todays_special"] is False
        and r.new_value["is_todays_special"] is True
        for r in rows
    )


def test_specials_list_is_tenant_isolated(client, seed):
    token_a = login(client, seed["a"])
    token_b = login(client, seed["b"])
    special_a = _make_product(client, token_a, name=f"A-Special-{uuid.uuid4().hex[:8]}")
    client.put(f"/admin/products/{special_a['id']}", headers=auth(token_a),
               json={"is_todays_special": True})
    # B flags one of its own too, to prove the lists don't bleed either way.
    special_b = _make_product(client, token_b, name=f"B-Special-{uuid.uuid4().hex[:8]}")
    client.put(f"/admin/products/{special_b['id']}", headers=auth(token_b),
               json={"is_todays_special": True})

    menu_a = client.get("/menu", headers={
        "X-Session-Token": _make_session(uuid.UUID(seed["a"]["restaurant_id"]))}).json()
    ids_a = {p["id"] for p in menu_a["specials"]}
    assert special_a["id"] in ids_a
    assert special_b["id"] not in ids_a

    menu_b = client.get("/menu", headers={
        "X-Session-Token": _make_session(uuid.UUID(seed["b"]["restaurant_id"]))}).json()
    ids_b = {p["id"] for p in menu_b["specials"]}
    assert special_b["id"] in ids_b
    assert special_a["id"] not in ids_b


def test_flagged_but_hidden_products_never_appear(client, seed):
    token = login(client, seed["a"])
    session_token = _make_session(uuid.UUID(seed["a"]["restaurant_id"]))

    unavailable = _make_product(client, token)
    client.put(f"/admin/products/{unavailable['id']}", headers=auth(token),
               json={"is_todays_special": True, "is_available": False})

    deactivated = _make_product(client, token)
    client.put(f"/admin/products/{deactivated['id']}", headers=auth(token),
               json={"is_todays_special": True})
    assert client.delete(f"/admin/products/{deactivated['id']}",
                         headers=auth(token)).status_code == 200  # soft delete

    ids = {p["id"] for p in
           client.get("/menu", headers={"X-Session-Token": session_token}).json()["specials"]}
    assert unavailable["id"] not in ids
    assert deactivated["id"] not in ids


def test_product_update_extra_field_rejected(client, seed):
    token = login(client, seed["a"])
    product = _make_product(client, token)
    resp = client.put(f"/admin/products/{product['id']}", headers=auth(token),
                      json={"is_todays_special": True, "restaurant_id": seed["b"]["restaurant_id"]})
    assert resp.status_code == 422
