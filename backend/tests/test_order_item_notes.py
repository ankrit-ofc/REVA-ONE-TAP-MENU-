"""
Customer per-item note (special_instructions doubling as the note field).

Covers: note stored and returned on the customer's own order, empty/whitespace
input normalizes to NULL (not an empty string), leading/trailing whitespace is
trimmed, >140 chars is rejected with 422, both waiter queues
(/waiter/ready and /waiter/pending-approvals) surface the field, and an item
placed without a note round-trips as null everywhere.

Each test builds its own restaurant (see conftest.py's session-scoped-fixture
trap note) so results never depend on what earlier test files left behind.
"""

import uuid
from datetime import datetime, timedelta, timezone

from tests.conftest import TEST_PASSWORD, auth, login


# -- World builders (mirrors the pattern in test_waiter_tables.py) ------------

def _fresh_tenant() -> dict:
    from app.core import security
    from app.db.session import SessionLocal
    from app.models.enums import Role
    from app.models.restaurant import Restaurant, RestaurantSettings
    from app.models.user import User

    db = SessionLocal()
    try:
        slug = f"notes-{uuid.uuid4().hex[:10]}"
        r = Restaurant(name="Tenant Notes", slug=slug, is_active=True)
        db.add(r)
        db.flush()
        db.add(RestaurantSettings(restaurant_id=r.id))
        email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
        user = User(
            restaurant_id=r.id,
            email=email,
            password_hash=security.hash_password(TEST_PASSWORD),
            role=Role.ADMIN,
        )
        db.add(user)
        db.commit()
        return {"restaurant_id": str(r.id), "slug": slug, "email": email}
    finally:
        db.close()


def _make_session(rid: uuid.UUID) -> str:
    from app.db.session import SessionLocal
    from app.models.table import Table, TableSession

    token = f"notes-test-session-{uuid.uuid4()}"
    db = SessionLocal()
    try:
        table = Table(restaurant_id=rid, name=f"NT-{uuid.uuid4().hex[:8]}")
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


def _make_product(client, admin_token: str) -> dict:
    cat = client.post("/admin/categories", headers=auth(admin_token),
                      json={"name": f"Cat-{uuid.uuid4().hex[:8]}"})
    assert cat.status_code == 201, cat.text
    prod = client.post("/admin/products", headers=auth(admin_token), json={
        "category_id": cat.json()["id"],
        "name": f"Dish-{uuid.uuid4().hex[:8]}",
        "base_price": "250.00",
    })
    assert prod.status_code == 201, prod.text
    return prod.json()


def _make_waiter(client, admin_token: str, slug: str) -> str:
    email = f"waiter-{uuid.uuid4().hex[:8]}@example.com"
    created = client.post("/admin/staff", headers=auth(admin_token),
                          json={"email": email, "password": TEST_PASSWORD, "role": "WAITER"})
    assert created.status_code == 201, created.text
    resp = client.post("/auth/login", json={
        "email": email, "password": TEST_PASSWORD, "restaurant_slug": slug,
    })
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _place_item(client, session_token: str, product_id: str, *, special_instructions=None):
    body = {"product_id": product_id, "quantity": 1}
    if special_instructions is not None:
        body["special_instructions"] = special_instructions
    return client.post(
        "/orders/items",
        headers={"X-Session-Token": session_token},
        json={"items": [body]},
    )


def _setup(client) -> dict:
    tenant = _fresh_tenant()
    admin_token = login(client, tenant)
    product = _make_product(client, admin_token)
    session_token = _make_session(uuid.UUID(tenant["restaurant_id"]))
    return {**tenant, "admin_token": admin_token, "product": product, "session_token": session_token}


# -- Stored / returned ----------------------------------------------------------

def test_note_stored_and_returned_on_current_order(client):
    world = _setup(client)
    resp = _place_item(client, world["session_token"], world["product"]["id"],
                       special_instructions="Less spicy, no onion")
    assert resp.status_code == 200, resp.text
    item = resp.json()["items"][0]
    assert item["special_instructions"] == "Less spicy, no onion"

    current = client.get("/orders/current", headers={"X-Session-Token": world["session_token"]})
    assert current.status_code == 200
    assert current.json()["items"][0]["special_instructions"] == "Less spicy, no onion"


def test_note_leading_trailing_whitespace_trimmed(client):
    world = _setup(client)
    resp = _place_item(client, world["session_token"], world["product"]["id"],
                       special_instructions="   Less spicy   ")
    assert resp.status_code == 200, resp.text
    assert resp.json()["items"][0]["special_instructions"] == "Less spicy"


# -- Empty / whitespace-only -> NULL --------------------------------------------

def test_note_empty_string_stores_null(client):
    world = _setup(client)
    resp = _place_item(client, world["session_token"], world["product"]["id"],
                       special_instructions="")
    assert resp.status_code == 200, resp.text
    assert resp.json()["items"][0]["special_instructions"] is None


def test_note_whitespace_only_stores_null(client):
    world = _setup(client)
    resp = _place_item(client, world["session_token"], world["product"]["id"],
                       special_instructions="     ")
    assert resp.status_code == 200, resp.text
    assert resp.json()["items"][0]["special_instructions"] is None


# -- Item without a note ---------------------------------------------------------

def test_item_without_note_returns_null(client):
    world = _setup(client)
    resp = _place_item(client, world["session_token"], world["product"]["id"])
    assert resp.status_code == 200, resp.text
    assert resp.json()["items"][0]["special_instructions"] is None


# -- Length cap ------------------------------------------------------------------

def test_note_over_140_chars_rejected(client):
    world = _setup(client)
    resp = _place_item(client, world["session_token"], world["product"]["id"],
                       special_instructions="x" * 141)
    assert resp.status_code == 422, resp.text


def test_note_exactly_140_chars_accepted(client):
    world = _setup(client)
    resp = _place_item(client, world["session_token"], world["product"]["id"],
                       special_instructions="x" * 140)
    assert resp.status_code == 200, resp.text
    assert resp.json()["items"][0]["special_instructions"] == "x" * 140


# -- Waiter queues -----------------------------------------------------------

def test_waiter_ready_includes_note(client):
    world = _setup(client)
    place = _place_item(client, world["session_token"], world["product"]["id"],
                        special_instructions="Extra spicy")
    assert place.status_code == 200, place.text
    item_id = place.json()["items"][0]["id"]

    waiter_token = _make_waiter(client, world["admin_token"], world["slug"])
    ready = client.get("/waiter/ready", headers=auth(waiter_token))
    assert ready.status_code == 200, ready.text
    matching = [i for i in ready.json() if i["id"] == item_id]
    assert len(matching) == 1
    assert matching[0]["special_instructions"] == "Extra spicy"


def test_waiter_ready_item_without_note_is_null(client):
    world = _setup(client)
    place = _place_item(client, world["session_token"], world["product"]["id"])
    assert place.status_code == 200, place.text
    item_id = place.json()["items"][0]["id"]

    waiter_token = _make_waiter(client, world["admin_token"], world["slug"])
    ready = client.get("/waiter/ready", headers=auth(waiter_token))
    matching = [i for i in ready.json() if i["id"] == item_id]
    assert len(matching) == 1
    assert matching[0]["special_instructions"] is None


def test_waiter_pending_approvals_includes_note(client):
    world = _setup(client)
    settings_resp = client.put("/admin/settings", headers=auth(world["admin_token"]),
                               json={"require_order_approval": True})
    assert settings_resp.status_code == 200, settings_resp.text

    place = _place_item(client, world["session_token"], world["product"]["id"],
                        special_instructions="No garlic")
    assert place.status_code == 200, place.text
    item_id = place.json()["items"][0]["id"]

    waiter_token = _make_waiter(client, world["admin_token"], world["slug"])
    pending = client.get("/waiter/pending-approvals", headers=auth(waiter_token))
    assert pending.status_code == 200, pending.text
    matching = [i for i in pending.json() if i["id"] == item_id]
    assert len(matching) == 1
    assert matching[0]["special_instructions"] == "No garlic"
