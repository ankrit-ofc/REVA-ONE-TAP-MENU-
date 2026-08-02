"""
GET /waiter/tables — floor-map coverage.

Covers: zero tables, free table, two OPEN orders with merged items, WAITER 200,
unauthorised role 403. Does not modify /dashboard/active-tables.

Also covers the GET /admin/tables floor-read widening (ADMIN/WAITER/COUNTER):
qr_token/scan_url present for ADMIN, absent (not null) for WAITER/COUNTER, and
a tripwire asserting the five always-present fields never get swept up by
response_model_exclude_none.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from tests.conftest import TEST_PASSWORD, auth, login


def _create_staff(client, admin_token: str, *, role: str, email: str) -> str:
    r = client.post(
        "/admin/staff",
        headers=auth(admin_token),
        json={"email": email, "password": TEST_PASSWORD, "role": role},
    )
    assert r.status_code == 201, r.text
    return email


def _login_role(client, seed_a: dict, email: str) -> str:
    resp = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": TEST_PASSWORD,
            "restaurant_slug": seed_a["slug"],
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _add_table(db_rid: uuid.UUID, name: str, *, is_active: bool = True) -> str:
    from app.db.session import SessionLocal
    from app.models.table import Table

    db = SessionLocal()
    try:
        t = Table(restaurant_id=db_rid, name=name, is_active=is_active)
        db.add(t)
        db.commit()
        db.refresh(t)
        return str(t.id)
    finally:
        db.close()


def _session_on_table(rid: uuid.UUID, table_id: str) -> str:
    from app.db.session import SessionLocal
    from app.models.table import TableSession

    token = f"wtables-{uuid.uuid4()}"
    db = SessionLocal()
    try:
        db.add(
            TableSession(
                restaurant_id=rid,
                table_id=uuid.UUID(table_id),
                token=token,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            )
        )
        db.commit()
    finally:
        db.close()
    return token


def _menu_product(client, admin: str, *, name: str, price: str = "100.00") -> str:
    cat = client.post(
        "/admin/categories",
        headers=auth(admin),
        json={"name": f"Cat-{uuid.uuid4().hex[:6]}"},
    )
    assert cat.status_code == 201, cat.text
    prod = client.post(
        "/admin/products",
        headers=auth(admin),
        json={
            "category_id": cat.json()["id"],
            "name": name,
            "base_price": price,
            "tax_rate": "0",
        },
    )
    assert prod.status_code == 201, prod.text
    return prod.json()["id"]


def _fresh_tenant() -> dict:
    """
    A restaurant no other test writes to, for assertions on an empty/exact
    table list. seed["a"]/seed["b"] are session-scoped and shared across the
    whole test run (see conftest.py) — by the time this file runs, both
    already have tables from test_menu_customization.py and
    test_payments_and_transitions.py (confirmed: tenant A had 13, tenant B
    had 2 "MC-" tables at this point in a full run). Mirrors the seed
    fixture's own construction, scoped to a single test instead of the
    session.
    """
    from app.core import security
    from app.db.session import SessionLocal
    from app.models.enums import Role
    from app.models.restaurant import Restaurant, RestaurantSettings
    from app.models.user import User

    db = SessionLocal()
    try:
        slug = f"wtables-zero-{uuid.uuid4().hex[:10]}"
        r = Restaurant(name="Tenant Zero-Tables", slug=slug, is_active=True)
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


def test_waiter_tables_zero_tables(client):
    tenant = _fresh_tenant()
    admin = login(client, tenant)
    r = client.get("/waiter/tables", headers=auth(admin))
    assert r.status_code == 200, r.text
    assert r.json() == []


def test_waiter_tables_free_table_row(client, seed):
    # seed["a"] is session-scoped and shared with other test files — filter to
    # this test's own table by id (matching
    # test_waiter_tables_occupied_items_and_cancelled_excluded below) rather
    # than asserting on the full list.
    admin = login(client, seed["a"])
    rid = uuid.UUID(seed["a"]["restaurant_id"])
    free_id = _add_table(rid, f"Free-{uuid.uuid4().hex[:6]}")
    dead_id = _add_table(rid, f"Dead-{uuid.uuid4().hex[:6]}", is_active=False)

    r = client.get("/waiter/tables", headers=auth(admin))
    assert r.status_code == 200, r.text
    rows = r.json()
    ids = {row["table_id"] for row in rows}
    assert dead_id not in ids  # deactivated must not appear
    row = next(t for t in rows if t["table_id"] == free_id)
    assert row["occupied"] is False
    assert row["order_count"] == 0
    assert row["items"] == []
    assert row["orders"] == []
    assert row["total_amount"] == "0.00"
    assert row["earliest_placed_at"] is None


def test_waiter_tables_occupied_items_and_cancelled_excluded(client, seed):
    """
    One OPEN order per table (DB unique partial index uq_orders_active_table).
    Card `items` lists non-cancelled lines; cancelled names are omitted.
    `orders` still carries the nested breakdown (length 1 when occupied).
    """
    from decimal import Decimal

    from app.db.session import SessionLocal
    from app.models.enums import OrderItemStatus
    from app.models.order import OrderItem

    admin = login(client, seed["a"])
    rid = uuid.UUID(seed["a"]["restaurant_id"])
    table_id = _add_table(rid, f"Occ-{uuid.uuid4().hex[:6]}")
    pid_momo = _menu_product(client, admin, name="Chicken Momo", price="200.00")
    pid_tea = _menu_product(client, admin, name="Milk Tea", price="50.00")

    tok = _session_on_table(rid, table_id)
    o1 = client.post(
        "/orders/items",
        headers={"X-Session-Token": tok},
        json={
            "items": [
                {"product_id": pid_momo, "quantity": 2},
                {"product_id": pid_tea, "quantity": 3},
            ]
        },
    )
    assert o1.status_code == 200, o1.text
    order_id = uuid.UUID(o1.json()["id"])

    # Cancelled line must not appear in merged/card items.
    db = SessionLocal()
    try:
        db.add(
            OrderItem(
                restaurant_id=rid,
                order_id=order_id,
                product_id=uuid.UUID(pid_tea),
                product_name="Ghost Tea",
                variant_name=None,
                unit_price=Decimal("50.00"),
                tax_rate=Decimal("0"),
                quantity=9,
                status=OrderItemStatus.CANCELLED,
            )
        )
        db.commit()
    finally:
        db.close()

    # Second placement appends to the same OPEN order (unique active-table index).
    o2 = client.post(
        "/orders/items",
        headers={"X-Session-Token": tok},
        json={"items": [{"product_id": pid_momo, "quantity": 1}]},
    )
    assert o2.status_code == 200, o2.text

    r = client.get("/waiter/tables", headers=auth(admin))
    assert r.status_code == 200, r.text
    row = next(t for t in r.json() if t["table_id"] == table_id)
    assert row["occupied"] is True
    assert row["order_count"] == 1
    assert len(row["orders"]) == 1

    by_name = {i["name"]: i["quantity"] for i in row["items"]}
    assert by_name["Chicken Momo"] == 3  # 2 + 1 appended
    assert by_name["Milk Tea"] == 3
    assert "Ghost Tea" not in by_name
    assert row["earliest_placed_at"] is not None
    assert row["total_amount"] != "0.00"


def test_waiter_tables_waiter_ok_kitchen_forbidden(client, seed):
    admin = login(client, seed["a"])
    waiter_email = f"waiter-{uuid.uuid4().hex[:6]}@example.com"
    kitchen_email = f"kitchen-{uuid.uuid4().hex[:6]}@example.com"
    _create_staff(client, admin, role="WAITER", email=waiter_email)
    _create_staff(client, admin, role="KITCHEN", email=kitchen_email)

    waiter_tok = _login_role(client, seed["a"], waiter_email)
    kitchen_tok = _login_role(client, seed["a"], kitchen_email)

    ok = client.get("/waiter/tables", headers=auth(waiter_tok))
    assert ok.status_code == 200, ok.text

    forbidden = client.get("/waiter/tables", headers=auth(kitchen_tok))
    assert forbidden.status_code == 403, forbidden.text


_ALWAYS_PRESENT_FIELDS = {"id", "name", "is_active", "created_at", "updated_at"}


def test_admin_tables_admin_gets_qr_fields_populated(client, seed):
    admin = login(client, seed["a"])
    rid = uuid.UUID(seed["a"]["restaurant_id"])
    table_id = _add_table(rid, f"Adm-{uuid.uuid4().hex[:6]}")

    r = client.get("/admin/tables", headers=auth(admin))
    assert r.status_code == 200, r.text
    row = next(t for t in r.json() if t["id"] == table_id)
    assert isinstance(row["qr_token"], str) and row["qr_token"] != ""
    assert isinstance(row["scan_url"], str) and row["scan_url"] != ""
    assert row["scan_url"].endswith(row["qr_token"])


def test_admin_tables_waiter_and_counter_get_no_qr_fields(client, seed):
    admin = login(client, seed["a"])
    rid = uuid.UUID(seed["a"]["restaurant_id"])
    table_id = _add_table(rid, f"Flr-{uuid.uuid4().hex[:6]}")

    waiter_email = f"waiter-{uuid.uuid4().hex[:6]}@example.com"
    counter_email = f"counter-{uuid.uuid4().hex[:6]}@example.com"
    _create_staff(client, admin, role="WAITER", email=waiter_email)
    _create_staff(client, admin, role="COUNTER", email=counter_email)
    waiter_tok = _login_role(client, seed["a"], waiter_email)
    counter_tok = _login_role(client, seed["a"], counter_email)

    for tok in (waiter_tok, counter_tok):
        r = client.get("/admin/tables", headers=auth(tok))
        assert r.status_code == 200, r.text
        row = next(t for t in r.json() if t["id"] == table_id)
        # Fields must be genuinely ABSENT (response_model_exclude_none), not
        # present-and-null — that's the whole point of the fix.
        assert "qr_token" not in row, row
        assert "scan_url" not in row, row


def test_admin_tables_kitchen_still_forbidden(client, seed):
    admin = login(client, seed["a"])
    kitchen_email = f"kitchen-{uuid.uuid4().hex[:6]}@example.com"
    _create_staff(client, admin, role="KITCHEN", email=kitchen_email)
    kitchen_tok = _login_role(client, seed["a"], kitchen_email)

    r = client.get("/admin/tables", headers=auth(kitchen_tok))
    assert r.status_code == 403, r.text


def test_admin_tables_exclude_none_tripwire(client, seed):
    """
    response_model_exclude_none is a blanket switch on the route. This pins
    down that the five always-present TableResponse fields survive it for a
    non-ADMIN caller — if one of them ever became Optional and happened to be
    None, this is what would catch it silently disappearing too.
    """
    admin = login(client, seed["a"])
    rid = uuid.UUID(seed["a"]["restaurant_id"])
    _add_table(rid, f"Trp-{uuid.uuid4().hex[:6]}")

    waiter_email = f"waiter-{uuid.uuid4().hex[:6]}@example.com"
    _create_staff(client, admin, role="WAITER", email=waiter_email)
    waiter_tok = _login_role(client, seed["a"], waiter_email)

    r = client.get("/admin/tables", headers=auth(waiter_tok))
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) >= 1
    for row in rows:
        assert _ALWAYS_PRESENT_FIELDS <= row.keys(), row
