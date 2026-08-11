"""
Dead Hours offer pricing — the MONEY path.

The single most important assertion in this file is
test_menu_price_equals_order_price_at_one_instant: the price the customer menu
advertises must be the price the order snapshots and the bill charges. Every
other test defends some edge of that guarantee.

CONFTEST TRAP (CLAUDE.md): `database` and `seed` are session-scoped with no
rollback, and files run alphabetically — rows written by any test are visible to
every later one. Every test here builds its OWN restaurant via _fresh_tenant()
and asserts only against ids it created. Nothing depends on seed["a"]/seed["b"].

Offers are seeded LIVE relative to the restaurant's own local clock (see
_live_window), so the suite does not depend on when it is run.
"""

import uuid
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

from tests.conftest import TEST_PASSWORD, auth, login

_KTM = "Asia/Kathmandu"


# ── World builders ────────────────────────────────────────────────────────────

def _fresh_tenant(prefix: str = "off", tz: str = _KTM) -> dict:
    from app.core import security
    from app.db.session import SessionLocal
    from app.models.enums import Role
    from app.models.restaurant import Restaurant, RestaurantSettings
    from app.models.user import User

    slug = f"{prefix}-{uuid.uuid4().hex[:10]}"
    db = SessionLocal()
    try:
        restaurant = Restaurant(name=f"Offer {slug}", slug=slug, is_active=True)
        db.add(restaurant)
        db.flush()
        db.add(RestaurantSettings(restaurant_id=restaurant.id, timezone=tz, currency="NPR"))
        user = User(
            restaurant_id=restaurant.id,
            email=f"admin.{slug}@example.com",
            password_hash=security.hash_password(TEST_PASSWORD),
            role=Role.ADMIN,
        )
        db.add(user)
        db.flush()
        info = {
            "restaurant_id": str(restaurant.id),
            "slug": slug,
            "email": user.email,
            "user_id": str(user.id),
            "tz": tz,
        }
        db.commit()
    finally:
        db.close()
    return info


def _category(rid: str, name: str = "Snacks") -> str:
    from app.db.session import SessionLocal
    from app.models.category import Category

    db = SessionLocal()
    try:
        cat = Category(restaurant_id=uuid.UUID(rid), name=name, display_order=0)
        db.add(cat)
        db.commit()
        return str(cat.id)
    finally:
        db.close()


def _product(
    rid: str,
    category_id: str,
    name: str,
    base_price: str,
    *,
    tax_rate: str = "0",
    has_variants: bool = False,
    allows_addons: bool = False,
) -> str:
    from app.db.session import SessionLocal
    from app.models.product import Product

    db = SessionLocal()
    try:
        product = Product(
            restaurant_id=uuid.UUID(rid),
            category_id=uuid.UUID(category_id),
            name=name,
            base_price=Decimal(base_price),
            tax_rate=Decimal(tax_rate),
            has_variants=has_variants,
            allows_addons=allows_addons,
            is_available=True,
            is_active=True,
        )
        db.add(product)
        db.commit()
        return str(product.id)
    finally:
        db.close()


def _variant(rid: str, product_id: str, name: str, price: str) -> str:
    from app.db.session import SessionLocal
    from app.models.product import ProductVariant

    db = SessionLocal()
    try:
        variant = ProductVariant(
            restaurant_id=uuid.UUID(rid),
            product_id=uuid.UUID(product_id),
            name=name,
            price=Decimal(price),
            is_active=True,
        )
        db.add(variant)
        db.commit()
        return str(variant.id)
    finally:
        db.close()


def _addon(rid: str, product_id: str, name: str, price: str) -> str:
    from app.db.session import SessionLocal
    from app.models.product import ProductAddon, ProductAddonMapping

    db = SessionLocal()
    try:
        addon = ProductAddon(
            restaurant_id=uuid.UUID(rid), name=name, price=Decimal(price), is_active=True
        )
        db.add(addon)
        db.flush()
        db.add(ProductAddonMapping(
            restaurant_id=uuid.UUID(rid),
            product_id=uuid.UUID(product_id),
            addon_id=addon.id,
        ))
        db.commit()
        return str(addon.id)
    finally:
        db.close()


def _session(rid: str) -> tuple[str, str]:
    """Table + ACTIVE table session (the QR scan path is tested elsewhere)."""
    from app.db.session import SessionLocal
    from app.models.table import Table, TableSession

    token = f"offer-test-{uuid.uuid4()}"
    db = SessionLocal()
    try:
        table = Table(restaurant_id=uuid.UUID(rid), name=f"OT-{uuid.uuid4().hex[:8]}")
        db.add(table)
        db.flush()
        table_id = str(table.id)
        db.add(TableSession(
            restaurant_id=uuid.UUID(rid),
            table_id=table.id,
            token=token,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        ))
        db.commit()
    finally:
        db.close()
    return token, table_id


def _live_window(tz_name: str = _KTM, *, live: bool = True) -> dict:
    """A window that is (or is not) running right now in the restaurant's tz.

    Live windows straddle the current local hour with an hour either side, so a
    test is never flaky at a boundary. The weekday mask covers only TODAY's
    local weekday, which is what makes the weekday check meaningful rather than
    vacuously true.
    """
    now_local = datetime.now(ZoneInfo(tz_name))
    if live:
        start = (now_local - timedelta(hours=1)).replace(minute=0)
        end = (now_local + timedelta(hours=1)).replace(minute=0)
        # Keep inside one day so the DB's end > start CHECK holds.
        start_t = max(time(0, 0), start.time())
        end_t = min(time(23, 59), end.time())
        if end_t <= start_t:  # around midnight — widen to the whole day
            start_t, end_t = time(0, 0), time(23, 59)
        weekday = now_local.weekday()
    else:
        # Same shape, but tomorrow's weekday only.
        start_t, end_t = time(0, 0), time(23, 59)
        weekday = (now_local.weekday() + 1) % 7
    return {
        "start_time": start_t.strftime("%H:%M:%S"),
        "end_time": end_t.strftime("%H:%M:%S"),
        "weekday_mask": 1 << weekday,
    }


def _offer_body(**over) -> dict:
    body = {
        "name": "Afternoon Special",
        "discount_type": "PERCENT",
        "discount_value": "25.00",
        "applies_to": "PRODUCTS",
        "product_ids": [],
        "is_enabled": True,
        **_live_window(),
    }
    body.update(over)
    return body


def _create_offer(client, tenant: dict, **over):
    token = login(client, tenant)
    return client.post("/admin/offers", headers=auth(token), json=_offer_body(**over))


def _menu(client, session_token: str) -> dict:
    resp = client.get("/menu", headers={"X-Session-Token": session_token})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _find_product(menu: dict, product_id: str) -> dict:
    def walk(nodes):
        for node in nodes:
            for p in node["products"]:
                if p["id"] == product_id:
                    return p
            found = walk(node["children"])
            if found:
                return found
        return None

    product = walk(menu["categories"])
    assert product is not None, f"{product_id} not in menu"
    return product


def _place_order(client, session_token: str, items: list[dict]):
    resp = client.post(
        "/orders/items",
        headers={"X-Session-Token": session_token},
        json={"items": items},
    )
    assert resp.status_code == 200, resp.text
    return resp


def _order_items(order_id: str) -> list[dict]:
    """Read the persisted snapshots straight from the DB — the bill's source."""
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        rows = db.execute(text(
            "SELECT product_name, unit_price, list_unit_price, offer_name, tax_rate "
            "FROM order_items WHERE order_id = :oid ORDER BY created_at"
        ), {"oid": order_id}).mappings().all()
        return [dict(r) for r in rows]
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
# THE core guarantee
# ══════════════════════════════════════════════════════════════════════════════

def test_menu_price_equals_order_price_at_one_instant(client):
    """The advertised price IS the charged price. The whole feature rests here."""
    tenant = _fresh_tenant()
    rid = tenant["restaurant_id"]
    cat = _category(rid)
    product_id = _product(rid, cat, "Momo", "200.00")
    session_token, _ = _session(rid)

    resp = _create_offer(
        client, tenant,
        discount_type="PERCENT", discount_value="25.00",
        applies_to="PRODUCTS", product_ids=[product_id],
    )
    assert resp.status_code == 201, resp.text

    menu_product = _find_product(_menu(client, session_token), product_id)
    order = _place_order(client, session_token, [{"product_id": product_id, "quantity": 2}])
    snapshot = _order_items(order.json()["id"])[0]

    # The anchor is untouched on the menu, and the offer sits beside it.
    assert Decimal(menu_product["base_price"]) == Decimal("200.00")
    assert Decimal(menu_product["offer_price"]) == Decimal("150.00")
    assert menu_product["offer_name"] == "Afternoon Special"

    # ...and the bill charges exactly what the menu advertised.
    assert snapshot["unit_price"] == Decimal("150.00")
    assert Decimal(menu_product["offer_price"]) == snapshot["unit_price"]


def test_anchor_price_is_never_mutated_by_an_offer(client):
    """products.base_price is untouched — the menu keeps showing the normal price."""
    tenant = _fresh_tenant()
    rid = tenant["restaurant_id"]
    cat = _category(rid)
    product_id = _product(rid, cat, "Momo", "200.00")
    session_token, _ = _session(rid)
    _create_offer(client, tenant, applies_to="PRODUCTS", product_ids=[product_id])

    _place_order(client, session_token, [{"product_id": product_id, "quantity": 1}])

    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        stored = db.execute(
            text("SELECT base_price FROM products WHERE id = :pid"), {"pid": product_id}
        ).scalar_one()
    finally:
        db.close()
    assert stored == Decimal("200.00")


def test_outside_the_window_nothing_is_discounted(client):
    tenant = _fresh_tenant()
    rid = tenant["restaurant_id"]
    cat = _category(rid)
    product_id = _product(rid, cat, "Momo", "200.00")
    session_token, _ = _session(rid)

    resp = _create_offer(
        client, tenant, applies_to="PRODUCTS", product_ids=[product_id],
        **_live_window(live=False),
    )
    assert resp.status_code == 201, resp.text

    menu_product = _find_product(_menu(client, session_token), product_id)
    assert menu_product["offer_price"] is None
    assert menu_product["offer_name"] is None

    order = _place_order(client, session_token, [{"product_id": product_id, "quantity": 1}])
    snapshot = _order_items(order.json()["id"])[0]
    assert snapshot["unit_price"] == Decimal("200.00")
    assert snapshot["offer_name"] is None
    assert snapshot["list_unit_price"] is None


def test_a_disabled_offer_prices_nothing(client):
    """The engine proposes, the owner approves — until then, normal prices."""
    tenant = _fresh_tenant()
    rid = tenant["restaurant_id"]
    cat = _category(rid)
    product_id = _product(rid, cat, "Momo", "200.00")
    session_token, _ = _session(rid)
    _create_offer(
        client, tenant, applies_to="PRODUCTS", product_ids=[product_id], is_enabled=False
    )

    menu_product = _find_product(_menu(client, session_token), product_id)
    assert menu_product["offer_price"] is None

    order = _place_order(client, session_token, [{"product_id": product_id, "quantity": 1}])
    assert _order_items(order.json()["id"])[0]["unit_price"] == Decimal("200.00")


# ══════════════════════════════════════════════════════════════════════════════
# The floor (min_resulting_price)
# ══════════════════════════════════════════════════════════════════════════════

def test_floor_clamps_a_real_order_and_is_still_badged(client):
    """Rs 50 off with a Rs 100 floor: a Rs 120 item stops at Rs 100, badged."""
    tenant = _fresh_tenant()
    rid = tenant["restaurant_id"]
    cat = _category(rid)
    dear = _product(rid, cat, "Momo", "200.00")
    near_floor = _product(rid, cat, "Sandwich", "120.00")
    session_token, _ = _session(rid)

    resp = _create_offer(
        client, tenant,
        discount_type="FIXED", discount_value="50.00", min_resulting_price="100.00",
        applies_to="PRODUCTS", product_ids=[dear, near_floor],
    )
    assert resp.status_code == 201, resp.text

    menu = _menu(client, session_token)
    assert Decimal(_find_product(menu, dear)["offer_price"]) == Decimal("150.00")
    assert Decimal(_find_product(menu, near_floor)["offer_price"]) == Decimal("100.00")
    # Partial saving still earns a badge — the customer sees the real price.
    assert _find_product(menu, near_floor)["offer_name"] == "Afternoon Special"

    order = _place_order(client, session_token, [
        {"product_id": dear, "quantity": 1},
        {"product_id": near_floor, "quantity": 1},
    ])
    charged = {r["product_name"]: r for r in _order_items(order.json()["id"])}
    assert charged["Momo"]["unit_price"] == Decimal("150.00")
    assert charged["Sandwich"]["unit_price"] == Decimal("100.00")   # clamped, silently
    assert charged["Sandwich"]["list_unit_price"] == Decimal("120.00")


def test_item_already_at_or_below_the_floor_gets_no_offer_and_no_badge(client):
    """A badge advertising a saving of zero is the trust failure we avoid."""
    tenant = _fresh_tenant()
    rid = tenant["restaurant_id"]
    cat = _category(rid)
    cheap = _product(rid, cat, "Samosa", "80.00")
    session_token, _ = _session(rid)
    _create_offer(
        client, tenant,
        discount_type="FIXED", discount_value="50.00", min_resulting_price="100.00",
        applies_to="PRODUCTS", product_ids=[cheap],
    )

    menu_product = _find_product(_menu(client, session_token), cheap)
    assert menu_product["offer_price"] is None
    assert menu_product["offer_name"] is None
    assert menu_product["offer_ends_at"] is None

    order = _place_order(client, session_token, [{"product_id": cheap, "quantity": 1}])
    snapshot = _order_items(order.json()["id"])[0]
    assert snapshot["unit_price"] == Decimal("80.00")   # never raised to the floor
    assert snapshot["offer_name"] is None


def test_floor_is_honoured_on_a_percent_offer_too(client):
    """Optional for PERCENT, but never inert."""
    tenant = _fresh_tenant()
    rid = tenant["restaurant_id"]
    cat = _category(rid)
    product_id = _product(rid, cat, "Platter", "2000.00")
    session_token, _ = _session(rid)

    # 40% off would be Rs 1200; the floor stops it at Rs 1500.
    resp = _create_offer(
        client, tenant,
        discount_type="PERCENT", discount_value="40.00", min_resulting_price="1500.00",
        applies_to="PRODUCTS", product_ids=[product_id],
    )
    assert resp.status_code == 201, resp.text

    menu_product = _find_product(_menu(client, session_token), product_id)
    assert Decimal(menu_product["offer_price"]) == Decimal("1500.00")

    order = _place_order(client, session_token, [{"product_id": product_id, "quantity": 1}])
    assert _order_items(order.json()["id"])[0]["unit_price"] == Decimal("1500.00")


def test_floor_warning_counts_items_reaching_the_floor(client):
    """Configuration-time warning — order time clamps silently."""
    tenant = _fresh_tenant()
    rid = tenant["restaurant_id"]
    cat = _category(rid)
    ids = [
        _product(rid, cat, "A", "200.00"),   # 200-50 = 150, clear of the floor
        _product(rid, cat, "B", "120.00"),   # 120-50 =  70, reaches the floor
        _product(rid, cat, "C", "130.00"),   # 130-50 =  80, reaches the floor
    ]
    created = _create_offer(
        client, tenant,
        discount_type="FIXED", discount_value="50.00", min_resulting_price="100.00",
        applies_to="PRODUCTS", product_ids=ids,
    )
    offer_id = created.json()["id"]

    token = login(client, tenant)
    resp = client.get(f"/admin/offers/{offer_id}/floor-warning", headers=auth(token))
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"item_count": 3, "reaching_floor": 2}


# ══════════════════════════════════════════════════════════════════════════════
# Validation — Pydantic AND the database
# ══════════════════════════════════════════════════════════════════════════════

def test_percent_over_100_rejected_by_pydantic(client):
    tenant = _fresh_tenant()
    product_id = _product(tenant["restaurant_id"], _category(tenant["restaurant_id"]), "M", "100.00")
    resp = _create_offer(
        client, tenant, discount_type="PERCENT", discount_value="150.00",
        applies_to="PRODUCTS", product_ids=[product_id],
    )
    assert resp.status_code == 422, resp.text
    assert "cannot exceed 100" in resp.text


def test_percent_over_100_rejected_by_the_database(client):
    """The CHECK holds even if a row reaches the table by another route."""
    from app.db.session import SessionLocal
    from sqlalchemy.exc import IntegrityError

    tenant = _fresh_tenant()
    db = SessionLocal()
    try:
        with pytest.raises(IntegrityError) as exc:
            db.execute(text(
                "INSERT INTO offer_windows (id, restaurant_id, name, discount_type, "
                "discount_value, start_time, end_time, weekday_mask, applies_to) "
                "VALUES (gen_random_uuid(), :rid, 'Bad', 'PERCENT', 150, "
                "'14:00', '17:00', 127, 'PRODUCTS')"
            ), {"rid": tenant["restaurant_id"]})
            db.commit()
        assert "ck_offer_windows_percent_max" in str(exc.value)
    finally:
        db.rollback()
        db.close()


def test_fixed_without_a_floor_rejected_by_pydantic(client):
    tenant = _fresh_tenant()
    product_id = _product(tenant["restaurant_id"], _category(tenant["restaurant_id"]), "M", "100.00")
    resp = _create_offer(
        client, tenant, discount_type="FIXED", discount_value="50.00",
        applies_to="PRODUCTS", product_ids=[product_id],
    )
    assert resp.status_code == 422, resp.text
    assert "min_resulting_price is required" in resp.text


def test_fixed_without_a_floor_rejected_by_the_database(client):
    from app.db.session import SessionLocal
    from sqlalchemy.exc import IntegrityError

    tenant = _fresh_tenant()
    db = SessionLocal()
    try:
        with pytest.raises(IntegrityError) as exc:
            db.execute(text(
                "INSERT INTO offer_windows (id, restaurant_id, name, discount_type, "
                "discount_value, start_time, end_time, weekday_mask, applies_to) "
                "VALUES (gen_random_uuid(), :rid, 'Bad', 'FIXED', 50, "
                "'14:00', '17:00', 127, 'PRODUCTS')"
            ), {"rid": tenant["restaurant_id"]})
            db.commit()
        assert "ck_offer_windows_fixed_needs_floor" in str(exc.value)
    finally:
        db.rollback()
        db.close()


def test_extra_field_is_rejected(client):
    tenant = _fresh_tenant()
    product_id = _product(tenant["restaurant_id"], _category(tenant["restaurant_id"]), "M", "100.00")
    token = login(client, tenant)
    body = _offer_body(applies_to="PRODUCTS", product_ids=[product_id])
    body["surge_multiplier"] = "2.0"   # the field this feature must never have
    resp = client.post("/admin/offers", headers=auth(token), json=body)
    assert resp.status_code == 422, resp.text


def test_window_may_not_wrap_past_midnight(client):
    tenant = _fresh_tenant()
    product_id = _product(tenant["restaurant_id"], _category(tenant["restaurant_id"]), "M", "100.00")
    resp = _create_offer(
        client, tenant, applies_to="PRODUCTS", product_ids=[product_id],
        start_time="22:00:00", end_time="02:00:00", weekday_mask=127,
    )
    assert resp.status_code == 422, resp.text
    assert "wrap past midnight" in resp.text


# ══════════════════════════════════════════════════════════════════════════════
# Tenancy
# ══════════════════════════════════════════════════════════════════════════════

def test_another_tenants_offer_never_prices_our_menu(client):
    tenant_a = _fresh_tenant("offa")
    tenant_b = _fresh_tenant("offb")
    cat_b = _category(tenant_b["restaurant_id"])
    product_b = _product(tenant_b["restaurant_id"], cat_b, "Momo", "200.00")
    session_b, _ = _session(tenant_b["restaurant_id"])

    # A creates a live offer. It must not touch B's identically-named product.
    cat_a = _category(tenant_a["restaurant_id"])
    product_a = _product(tenant_a["restaurant_id"], cat_a, "Momo", "200.00")
    _create_offer(client, tenant_a, applies_to="PRODUCTS", product_ids=[product_a])

    menu_b = _find_product(_menu(client, session_b), product_b)
    assert menu_b["offer_price"] is None

    order_b = _place_order(client, session_b, [{"product_id": product_b, "quantity": 1}])
    assert _order_items(order_b.json()["id"])[0]["unit_price"] == Decimal("200.00")


def test_cannot_attach_another_tenants_product_to_an_offer(client):
    tenant_a = _fresh_tenant("offa")
    tenant_b = _fresh_tenant("offb")
    product_b = _product(
        tenant_b["restaurant_id"], _category(tenant_b["restaurant_id"]), "Momo", "200.00"
    )
    resp = _create_offer(
        client, tenant_a, applies_to="PRODUCTS", product_ids=[product_b]
    )
    assert resp.status_code == 422, resp.text
    assert "Products not found" in resp.text


def test_cannot_read_another_tenants_offer(client):
    tenant_a = _fresh_tenant("offa")
    tenant_b = _fresh_tenant("offb")
    product_a = _product(
        tenant_a["restaurant_id"], _category(tenant_a["restaurant_id"]), "Momo", "200.00"
    )
    created = _create_offer(client, tenant_a, applies_to="PRODUCTS", product_ids=[product_a])
    offer_id = created.json()["id"]

    token_b = login(client, tenant_b)
    resp = client.get(f"/admin/offers/{offer_id}", headers=auth(token_b))
    assert resp.status_code == 404, resp.text


def test_offers_require_admin(client):
    from app.core import security
    from app.db.session import SessionLocal
    from app.models.enums import Role
    from app.models.user import User

    tenant = _fresh_tenant()
    email = f"waiter.{uuid.uuid4().hex[:10]}@example.com"
    db = SessionLocal()
    try:
        db.add(User(
            restaurant_id=uuid.UUID(tenant["restaurant_id"]),
            email=email,
            password_hash=security.hash_password(TEST_PASSWORD),
            role=Role.WAITER,
        ))
        db.commit()
    finally:
        db.close()

    token = login(client, {"email": email, "slug": tenant["slug"]})
    assert client.get("/admin/offers", headers=auth(token)).status_code == 403
    assert client.post("/admin/offers", headers=auth(token), json=_offer_body()).status_code == 403


def test_offers_require_authentication(client):
    assert client.get("/admin/offers").status_code == 401


# ══════════════════════════════════════════════════════════════════════════════
# Overlapping offers, variants, addons, timezone
# ══════════════════════════════════════════════════════════════════════════════

def test_overlapping_offers_resolve_to_the_lowest_price(client):
    tenant = _fresh_tenant()
    rid = tenant["restaurant_id"]
    cat = _category(rid)
    product_id = _product(rid, cat, "Momo", "200.00")
    session_token, _ = _session(rid)

    _create_offer(
        client, tenant, name="Small Deal", discount_type="PERCENT", discount_value="10.00",
        applies_to="PRODUCTS", product_ids=[product_id],
    )
    _create_offer(
        client, tenant, name="Big Deal", discount_type="PERCENT", discount_value="40.00",
        applies_to="CATEGORY", category_id=cat, product_ids=[],
    )

    menu_product = _find_product(_menu(client, session_token), product_id)
    assert Decimal(menu_product["offer_price"]) == Decimal("120.00")
    assert menu_product["offer_name"] == "Big Deal"

    order = _place_order(client, session_token, [{"product_id": product_id, "quantity": 1}])
    snapshot = _order_items(order.json()["id"])[0]
    assert snapshot["unit_price"] == Decimal("120.00")
    assert snapshot["offer_name"] == "Big Deal"


def test_equal_offers_break_the_tie_on_created_at(client):
    """Identical savings: the offer that has been running longest wins."""
    tenant = _fresh_tenant()
    rid = tenant["restaurant_id"]
    cat = _category(rid)
    product_id = _product(rid, cat, "Momo", "200.00")
    session_token, _ = _session(rid)

    _create_offer(
        client, tenant, name="First", discount_type="PERCENT", discount_value="25.00",
        applies_to="PRODUCTS", product_ids=[product_id],
    )
    _create_offer(
        client, tenant, name="Second", discount_type="PERCENT", discount_value="25.00",
        applies_to="CATEGORY", category_id=cat, product_ids=[],
    )

    menu_product = _find_product(_menu(client, session_token), product_id)
    assert Decimal(menu_product["offer_price"]) == Decimal("150.00")
    assert menu_product["offer_name"] == "First"

    order = _place_order(client, session_token, [{"product_id": product_id, "quantity": 1}])
    assert _order_items(order.json()["id"])[0]["offer_name"] == "First"


def test_variant_priced_from_its_own_anchor(client):
    """A variant product is charged by its VARIANT, so that is what discounts."""
    tenant = _fresh_tenant()
    rid = tenant["restaurant_id"]
    cat = _category(rid)
    product_id = _product(rid, cat, "Pizza", "100.00", has_variants=True)
    large = _variant(rid, product_id, "Large", "400.00")
    session_token, _ = _session(rid)

    _create_offer(
        client, tenant, discount_type="PERCENT", discount_value="25.00",
        applies_to="PRODUCTS", product_ids=[product_id],
    )

    menu_product = _find_product(_menu(client, session_token), product_id)
    variant = next(v for v in menu_product["variants"] if v["id"] == large)
    assert Decimal(variant["price"]) == Decimal("400.00")        # anchor intact
    assert Decimal(variant["offer_price"]) == Decimal("300.00")

    order = _place_order(client, session_token, [
        {"product_id": product_id, "variant_id": large, "quantity": 1}
    ])
    snapshot = _order_items(order.json()["id"])[0]
    assert snapshot["unit_price"] == Decimal("300.00")
    assert snapshot["list_unit_price"] == Decimal("400.00")
    assert Decimal(variant["offer_price"]) == snapshot["unit_price"]


def test_addons_are_never_discounted(client):
    """"Rs 50 off" means off the item, not off the item plus its extras."""
    tenant = _fresh_tenant()
    rid = tenant["restaurant_id"]
    cat = _category(rid)
    product_id = _product(rid, cat, "Momo", "200.00", allows_addons=True)
    addon_id = _addon(rid, product_id, "Extra Cheese", "60.00")
    session_token, _ = _session(rid)

    _create_offer(
        client, tenant, discount_type="PERCENT", discount_value="50.00",
        applies_to="PRODUCTS", product_ids=[product_id],
    )

    menu_product = _find_product(_menu(client, session_token), product_id)
    assert Decimal(menu_product["addons"][0]["price"]) == Decimal("60.00")

    order = _place_order(client, session_token, [
        {"product_id": product_id, "quantity": 1, "addon_ids": [addon_id]}
    ])

    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        addon_price = db.execute(text(
            "SELECT a.addon_price FROM order_item_addons a "
            "JOIN order_items i ON i.id = a.order_item_id WHERE i.order_id = :oid"
        ), {"oid": order.json()["id"]}).scalar_one()
    finally:
        db.close()
    assert addon_price == Decimal("60.00")   # untouched
    assert _order_items(order.json()["id"])[0]["unit_price"] == Decimal("100.00")


def test_weekday_is_the_restaurants_local_weekday(client):
    """A UTC weekday flips at 18:15 in Kathmandu — the offer must not.

    The offer is masked to the restaurant's CURRENT local weekday only. When
    that differs from the UTC weekday, a UTC-based implementation would find the
    offer dead and charge full price.
    """
    tenant = _fresh_tenant(tz="Pacific/Kiritimati")   # UTC+14
    rid = tenant["restaurant_id"]
    cat = _category(rid)
    product_id = _product(rid, cat, "Momo", "200.00")
    session_token, _ = _session(rid)

    local_weekday = datetime.now(ZoneInfo("Pacific/Kiritimati")).weekday()
    resp = _create_offer(
        client, tenant, applies_to="PRODUCTS", product_ids=[product_id],
        start_time="00:00:00", end_time="23:59:00", weekday_mask=1 << local_weekday,
    )
    assert resp.status_code == 201, resp.text

    menu_product = _find_product(_menu(client, session_token), product_id)
    assert Decimal(menu_product["offer_price"]) == Decimal("150.00")

    order = _place_order(client, session_token, [{"product_id": product_id, "quantity": 1}])
    assert _order_items(order.json()["id"])[0]["unit_price"] == Decimal("150.00")


# ══════════════════════════════════════════════════════════════════════════════
# Receipt provenance
# ══════════════════════════════════════════════════════════════════════════════

def test_receipt_shows_the_anchor_and_the_offer(client):
    """A bill reprinted later must say WHY the price was low, not just what it was."""
    tenant = _fresh_tenant()
    rid = tenant["restaurant_id"]
    cat = _category(rid)
    product_id = _product(rid, cat, "Momo", "200.00", tax_rate="10")
    session_token, table_id = _session(rid)
    _create_offer(
        client, tenant, discount_type="PERCENT", discount_value="25.00",
        applies_to="PRODUCTS", product_ids=[product_id],
    )

    order = _place_order(client, session_token, [{"product_id": product_id, "quantity": 2}])
    order_id = order.json()["id"]
    snapshot = _order_items(order_id)[0]

    assert snapshot["unit_price"] == Decimal("150.00")
    assert snapshot["list_unit_price"] == Decimal("200.00")
    assert snapshot["offer_name"] == "Afternoon Special"

    # Provenance survives a later edit to the product's price — it is a snapshot,
    # not a lookup.
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        db.execute(
            text("UPDATE products SET base_price = 999 WHERE id = :pid"), {"pid": product_id}
        )
        db.commit()
    finally:
        db.close()

    after = _order_items(order_id)[0]
    assert after["unit_price"] == Decimal("150.00")
    assert after["list_unit_price"] == Decimal("200.00")


def test_provenance_columns_are_set_together_or_not_at_all(client):
    """ck_order_items_offer_provenance — `offer_name IS NOT NULL` stays a
    reliable "this line was discounted" test."""
    from app.db.session import SessionLocal
    from sqlalchemy.exc import IntegrityError

    tenant = _fresh_tenant()
    rid = tenant["restaurant_id"]
    cat = _category(rid)
    product_id = _product(rid, cat, "Momo", "200.00")
    session_token, _ = _session(rid)
    order = _place_order(client, session_token, [{"product_id": product_id, "quantity": 1}])
    item_id = _order_items_ids(order.json()["id"])[0]

    db = SessionLocal()
    try:
        with pytest.raises(IntegrityError) as exc:
            db.execute(
                text("UPDATE order_items SET offer_name = 'Half Truth' WHERE id = :iid"),
                {"iid": item_id},
            )
            db.commit()
        assert "ck_order_items_offer_provenance" in str(exc.value)
    finally:
        db.rollback()
        db.close()


def _order_items_ids(order_id: str) -> list[str]:
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        return [str(r) for r in db.execute(
            text("SELECT id FROM order_items WHERE order_id = :oid"), {"oid": order_id}
        ).scalars().all()]
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
# Resolver unit checks (no HTTP)
# ══════════════════════════════════════════════════════════════════════════════

def _offer(**over):
    """A detached OfferWindow for pure-arithmetic checks."""
    from app.models.enums import OfferAppliesTo, OfferDiscountType
    from app.models.offer import OfferWindow

    kwargs = dict(
        id=uuid.uuid4(),
        name="X",
        discount_type=OfferDiscountType.PERCENT,
        discount_value=Decimal("25"),
        min_resulting_price=None,
        start_time=time(0, 0),
        end_time=time(23, 59),
        weekday_mask=127,
        applies_to=OfferAppliesTo.PRODUCTS,
        is_enabled=True,
        is_active=True,
    )
    kwargs.update(over)
    return OfferWindow(**kwargs)


def test_apply_can_never_raise_a_price_even_with_an_absurd_floor():
    """RULE 1 survives misconfiguration, not just correct configuration."""
    from app.services.pricing_service import apply
    from app.models.enums import OfferDiscountType

    offer = _offer(
        discount_type=OfferDiscountType.FIXED,
        discount_value=Decimal("10"),
        min_resulting_price=Decimal("100000"),   # far above any real anchor
    )
    assert apply(offer, Decimal("200.00")) == Decimal("200.00")


def test_apply_never_returns_a_negative_price():
    from app.services.pricing_service import apply
    from app.models.enums import OfferDiscountType

    offer = _offer(
        discount_type=OfferDiscountType.FIXED,
        discount_value=Decimal("500"),
        min_resulting_price=Decimal("1"),
    )
    assert apply(offer, Decimal("200.00")) == Decimal("1.00")


def test_apply_rounds_to_two_places():
    from app.services.pricing_service import apply

    # 33.33% off 100.00 = 66.67
    assert apply(_offer(discount_value=Decimal("33.33")), Decimal("100.00")) == Decimal("66.67")


def test_is_live_is_half_open_at_the_end():
    """"till 5pm" must be literally true at 17:00:00."""
    from app.services.pricing_service import is_live

    offer = _offer(start_time=time(14, 0), end_time=time(17, 0), weekday_mask=127)
    tz = ZoneInfo(_KTM)
    base = datetime.now(tz).replace(minute=0, second=0, microsecond=0)
    assert is_live(offer, base.replace(hour=14))
    assert is_live(offer, base.replace(hour=16))
    assert not is_live(offer, base.replace(hour=17))
    assert not is_live(offer, base.replace(hour=13))
