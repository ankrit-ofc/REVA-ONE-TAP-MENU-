"""
Bulk product CSV import (preview + commit), CLAUDE.md §9.

Every test builds its OWN restaurant + ADMIN — the shared `seed` fixture is
session-scoped with no rollback (see conftest.py), and these tests assert exact
counts/lists, which a shared tenant polluted by other test files would break.
"""

import csv
import io
import uuid

import pytest

from tests.conftest import TEST_PASSWORD, auth, login

_HEADER = ["category", "name", "short_description", "food_type", "base_price", "tax_rate", "available"]

PREVIEW_URL = "/admin/products/import/preview"
COMMIT_URL = "/admin/products/import/commit"


# ── World builder ──────────────────────────────────────────────────────────────

def _fresh_tenant(role: str = "ADMIN") -> dict:
    from app.core import security
    from app.db.session import SessionLocal
    from app.models.enums import Role
    from app.models.restaurant import Restaurant, RestaurantSettings
    from app.models.user import User

    suffix = uuid.uuid4().hex[:10]
    db = SessionLocal()
    try:
        r = Restaurant(name=f"CSV Import {suffix}", slug=f"csv-import-{suffix}", is_active=True)
        db.add(r)
        db.flush()
        db.add(RestaurantSettings(restaurant_id=r.id))
        user = User(
            restaurant_id=r.id,
            email=f"{role.lower()}.{suffix}@example.com",
            password_hash=security.hash_password(TEST_PASSWORD),
            role=Role[role],
        )
        db.add(user)
        db.commit()
        return {
            "restaurant_id": str(r.id),
            "slug": r.slug,
            "email": user.email,
            "user_id": str(user.id),
        }
    finally:
        db.close()


@pytest.fixture()
def tenant(client, database):
    return _fresh_tenant()


@pytest.fixture()
def admin_token(client, tenant):
    return login(client, tenant)


# ── CSV builder ─────────────────────────────────────────────────────────────────

def _csv(rows: list[dict[str, str]], header: list[str] | None = None) -> bytes:
    header = header or _HEADER
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=header)
    w.writeheader()
    for row in rows:
        w.writerow({h: row.get(h, "") for h in header})
    return buf.getvalue().encode("utf-8")


def _upload(client, url: str, token: str, data: bytes, filename: str = "products.csv"):
    return client.post(
        url,
        headers=auth(token),
        files={"file": (filename, data, "text/csv")},
    )


# ── Valid import ──────────────────────────────────────────────────────────────

def test_valid_import_preview_then_commit(client, admin_token):
    rows = [
        {"category": "Momos", "name": "Chicken Momo", "short_description": "Steamed dumplings",
         "food_type": "Non-veg", "base_price": "250.00", "tax_rate": "13", "available": "true"},
        {"category": "Momos", "name": "Veg Momo", "food_type": "veg", "base_price": "200.00"},
        {"category": "Beverages", "name": "Masala Tea", "food_type": "BEVERAGE", "base_price": "80.00"},
    ]
    body = _csv(rows)

    preview = _upload(client, PREVIEW_URL, admin_token, body)
    assert preview.status_code == 200, preview.text
    pv = preview.json()
    assert pv["valid_rows"] == 3
    assert pv["products_to_create"] == 3
    assert pv["duplicates_skipped"] == 0
    assert set(pv["new_categories"]) == {"Momos", "Beverages"}
    assert pv["existing_categories"] == []
    assert pv["errors"] == []

    commit = _upload(client, COMMIT_URL, admin_token, body)
    assert commit.status_code == 200, commit.text
    cm = commit.json()
    assert cm["categories_created"] == 2
    assert cm["products_created"] == 3
    assert cm["duplicates_skipped"] == 0

    products = client.get("/admin/products", headers=auth(admin_token))
    names = {p["name"] for p in products.json()}
    assert names == {"Chicken Momo", "Veg Momo", "Masala Tea"}

    momo = next(p for p in products.json() if p["name"] == "Chicken Momo")
    assert momo["food_type"] == "NON_VEG"
    assert momo["base_price"] == "250.00"
    assert momo["tax_rate"] == "13.00"
    assert momo["is_available"] is True
    assert momo["image_url"] is None

    veg_momo = next(p for p in products.json() if p["name"] == "Veg Momo")
    assert veg_momo["tax_rate"] == "0.00"  # default applied for the blank column


# ── New vs. existing category ────────────────────────────────────────────────

def test_unknown_category_created_existing_category_reused(client, admin_token):
    cat = client.post("/admin/categories", headers=auth(admin_token), json={"name": "Momos"})
    assert cat.status_code == 201, cat.text

    body = _csv([
        {"category": "Momos", "name": "Chicken Momo", "base_price": "250"},
        {"category": "Desserts", "name": "Gulab Jamun", "base_price": "120"},
    ])
    preview = _upload(client, PREVIEW_URL, admin_token, body)
    pv = preview.json()
    assert pv["new_categories"] == ["Desserts"]
    assert pv["existing_categories"] == ["Momos"]

    commit = _upload(client, COMMIT_URL, admin_token, body)
    cm = commit.json()
    assert cm["categories_created"] == 1  # only Desserts; Momos was reused
    assert cm["products_created"] == 2

    cats = client.get("/admin/categories", headers=auth(admin_token)).json()
    momos = [c for c in cats if c["name"] == "Momos"]
    assert len(momos) == 1
    assert momos[0]["id"] == cat.json()["id"]  # the pre-existing row, not a new one


# ── Duplicate skipping + idempotency ─────────────────────────────────────────

def test_duplicate_within_csv_and_against_existing_skipped(client, admin_token):
    existing_cat = client.post("/admin/categories", headers=auth(admin_token), json={"name": "Momos"})
    client.post("/admin/products", headers=auth(admin_token), json={
        "category_id": existing_cat.json()["id"], "name": "Chicken Momo", "base_price": "250",
    })

    body = _csv([
        {"category": "Momos", "name": "Chicken Momo", "base_price": "999"},  # dup of existing product
        {"category": "Momos", "name": "Veg Momo", "base_price": "200"},
        {"category": "Momos", "name": "Veg Momo", "base_price": "200"},  # dup within this CSV
    ])
    preview = _upload(client, PREVIEW_URL, admin_token, body)
    pv = preview.json()
    assert pv["valid_rows"] == 3
    assert pv["products_to_create"] == 1
    assert pv["duplicates_skipped"] == 2

    commit = _upload(client, COMMIT_URL, admin_token, body)
    cm = commit.json()
    assert cm["products_created"] == 1
    assert cm["duplicates_skipped"] == 2

    products = client.get("/admin/products", headers=auth(admin_token)).json()
    veg_momos = [p for p in products if p["name"] == "Veg Momo"]
    assert len(veg_momos) == 1
    chicken_momos = [p for p in products if p["name"] == "Chicken Momo"]
    assert len(chicken_momos) == 1  # the original, price untouched (skip != update)
    assert chicken_momos[0]["base_price"] == "250.00"


def test_reimporting_same_csv_is_a_no_op(client, admin_token):
    body = _csv([
        {"category": "Momos", "name": "Chicken Momo", "base_price": "250"},
        {"category": "Momos", "name": "Veg Momo", "base_price": "200"},
    ])
    first = _upload(client, COMMIT_URL, admin_token, body)
    assert first.json() == {"categories_created": 1, "products_created": 2, "duplicates_skipped": 0}

    second = _upload(client, COMMIT_URL, admin_token, body)
    assert second.status_code == 200, second.text
    assert second.json() == {"categories_created": 0, "products_created": 0, "duplicates_skipped": 2}

    products = client.get("/admin/products", headers=auth(admin_token)).json()
    assert len(products) == 2  # nothing duplicated


# ── Per-row validation errors ────────────────────────────────────────────────

def test_malformed_price_reported_per_row(client, admin_token):
    body = _csv([{"category": "Momos", "name": "Chicken Momo", "base_price": "not-a-number"}])
    resp = _upload(client, PREVIEW_URL, admin_token, body)
    assert resp.status_code == 200, resp.text
    pv = resp.json()
    assert pv["valid_rows"] == 0
    assert len(pv["errors"]) == 1
    err = pv["errors"][0]
    assert err["row"] == 2
    assert err["field"] == "base_price"
    assert err["raw"] == "not-a-number"


def test_invalid_food_type_reported_per_row(client, admin_token):
    body = _csv([{"category": "Momos", "name": "Chicken Momo", "food_type": "carnivore"}])
    resp = _upload(client, PREVIEW_URL, admin_token, body)
    pv = resp.json()
    assert len(pv["errors"]) == 1
    assert pv["errors"][0]["field"] == "food_type"
    assert pv["errors"][0]["raw"] == "carnivore"


def test_food_type_case_and_hyphen_insensitive(client, admin_token):
    body = _csv([
        {"category": "Momos", "name": "A", "food_type": "NON_VEG", "base_price": "1"},
        {"category": "Momos", "name": "B", "food_type": "non-veg", "base_price": "1"},
        {"category": "Momos", "name": "C", "food_type": "  Veg  ", "base_price": "1"},
    ])
    resp = _upload(client, PREVIEW_URL, admin_token, body)
    pv = resp.json()
    assert pv["errors"] == []
    assert pv["valid_rows"] == 3


def test_missing_required_column(client, admin_token):
    body = _csv([{"category": "Momos", "base_price": "1"}], header=["category", "base_price"])
    resp = _upload(client, PREVIEW_URL, admin_token, body)
    assert resp.status_code == 200, resp.text
    pv = resp.json()
    assert pv["valid_rows"] == 0
    assert any(e["field"] == "name" and e["row"] == 1 for e in pv["errors"])


def test_empty_file(client, admin_token):
    resp = _upload(client, PREVIEW_URL, admin_token, b"")
    assert resp.status_code == 200, resp.text
    pv = resp.json()
    assert pv["valid_rows"] == 0
    assert len(pv["errors"]) == 1
    assert pv["errors"][0]["field"] == "file"


# ── Commit refuses on errors; all-or-nothing ─────────────────────────────────

def test_commit_refuses_when_errors_exist_and_writes_nothing(client, admin_token):
    body = _csv([
        {"category": "Momos", "name": "Chicken Momo", "base_price": "250"},  # valid
        {"category": "Momos", "name": "Bad Price", "base_price": "abc"},     # invalid
    ])
    resp = _upload(client, COMMIT_URL, admin_token, body)
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert "errors" in detail
    assert any(e["field"] == "base_price" for e in detail["errors"])

    # All-or-nothing: the valid row must NOT have been created either.
    products = client.get("/admin/products", headers=auth(admin_token)).json()
    assert products == []
    cats = client.get("/admin/categories", headers=auth(admin_token)).json()
    assert cats == []


# ── ADMIN only ────────────────────────────────────────────────────────────────

def test_non_admin_role_forbidden(client):
    tenant = _fresh_tenant(role="WAITER")
    token = login(client, tenant)
    body = _csv([{"category": "Momos", "name": "Chicken Momo", "base_price": "250"}])
    assert _upload(client, PREVIEW_URL, token, body).status_code == 403
    assert _upload(client, COMMIT_URL, token, body).status_code == 403
