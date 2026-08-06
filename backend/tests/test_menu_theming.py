"""
Menu theming — restaurant_settings.menu_template / menu_accent_color
(CLAUDE.md §9, admin Settings "Edit menu").

CONFTEST TRAP (CLAUDE.md): `database` and `seed` are session-scoped with no
rollback, and files run alphabetically — rows written by any test are visible
to every later one. Every test here builds its OWN restaurant via
_fresh_tenant() and asserts only against ids it created. Nothing below depends
on seed["a"]/seed["b"] being clean.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import TEST_PASSWORD, auth, login


# ── World builders ────────────────────────────────────────────────────────────

def _fresh_tenant(prefix: str = "mt") -> dict:
    """A brand-new restaurant + settings + ADMIN. Never reuses a seeded tenant."""
    from app.core import security
    from app.db.session import SessionLocal
    from app.models.enums import Role
    from app.models.restaurant import Restaurant, RestaurantSettings
    from app.models.user import User

    slug = f"{prefix}-{uuid.uuid4().hex[:10]}"
    db = SessionLocal()
    try:
        restaurant = Restaurant(name=f"Theming {slug}", slug=slug, is_active=True)
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
        info = {
            "restaurant_id": str(restaurant.id),
            "slug": slug,
            "email": user.email,
            "user_id": str(user.id),
        }
        db.commit()
    finally:
        db.close()
    return info


def _make_session(rid: str) -> str:
    """Table + ACTIVE session created directly (the QR scan path is tested elsewhere)."""
    from app.db.session import SessionLocal
    from app.models.table import Table, TableSession

    token = f"menu-theming-test-{uuid.uuid4()}"
    db = SessionLocal()
    try:
        table = Table(restaurant_id=uuid.UUID(rid), name=f"MT-{uuid.uuid4().hex[:8]}")
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


# -- Default applies when unset -------------------------------------------------

def test_admin_settings_default_template_and_no_accent(client):
    tenant = _fresh_tenant()
    token = login(client, tenant)

    resp = client.get("/admin/settings", headers=auth(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["menu_template"] == "classic"
    assert body["menu_accent_color"] is None


def test_customer_menu_default_template_and_no_accent(client):
    tenant = _fresh_tenant()
    session_token = _make_session(tenant["restaurant_id"])

    resp = client.get("/menu", headers={"X-Session-Token": session_token})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["menu_template"] == "classic"
    assert body["menu_accent_color"] is None


def test_pre_existing_settings_row_reads_safe_defaults(client):
    """A settings row inserted without ever touching the new columns — the shape
    of every restaurant that existed before this migration — still reads the
    safe DB defaults, not NULL/error."""
    from app.db.session import SessionLocal
    from app.models.restaurant import RestaurantSettings

    tenant = _fresh_tenant()
    db = SessionLocal()
    try:
        row = db.query(RestaurantSettings).filter_by(
            restaurant_id=uuid.UUID(tenant["restaurant_id"])
        ).one()
        db.refresh(row)
        assert row.menu_template == "classic"
        assert row.menu_accent_color is None
    finally:
        db.close()


def test_menu_template_server_default_matches_migration(database):
    """Guards against the model and the applied migration drifting apart —
    exactly the model-says-classic / migration-says-photo_grid mismatch that
    nearly shipped. If these two diverge again, `alembic upgrade head` on a
    fresh database renders a different default than the ORM model declares,
    silently changing what every untouched restaurant renders."""
    from sqlalchemy import text
    from app.db.session import SessionLocal
    from app.models.restaurant import RestaurantSettings

    model_default = RestaurantSettings.__table__.columns["menu_template"].server_default.arg
    assert model_default == "classic"

    db = SessionLocal()
    try:
        db_default = db.execute(text(
            "SELECT column_default FROM information_schema.columns "
            "WHERE table_name = 'restaurant_settings' AND column_name = 'menu_template'"
        )).scalar_one()
    finally:
        db.close()

    assert db_default is not None
    assert f"'{model_default}'" in db_default, (
        f"model server_default={model_default!r} but the migrated DB column_default is "
        f"{db_default!r} — the model and the applied migration have drifted apart."
    )


# -- Each template value accepted -----------------------------------------------

@pytest.mark.parametrize("template", [
    "classic", "photo_grid", "elegant_list", "compact_list", "magazine", "bold_cards",
])
def test_each_menu_template_accepted_and_round_trips(client, template):
    tenant = _fresh_tenant()
    token = login(client, tenant)

    resp = client.put("/admin/settings", headers=auth(token), json={"menu_template": template})
    assert resp.status_code == 200, resp.text
    assert resp.json()["menu_template"] == template

    again = client.get("/admin/settings", headers=auth(token))
    assert again.status_code == 200, again.text
    assert again.json()["menu_template"] == template


# -- Unknown template rejected ---------------------------------------------------

def test_unknown_menu_template_rejected(client):
    tenant = _fresh_tenant()
    token = login(client, tenant)

    resp = client.put("/admin/settings", headers=auth(token), json={"menu_template": "does_not_exist"})
    assert resp.status_code == 422, resp.text


# -- Invalid hex rejected ---------------------------------------------------------

@pytest.mark.parametrize("bad_hex", [
    "1D9E75",       # missing '#'
    "#1D9E7",       # too short
    "#1D9E755",     # too long
    "#GGGGGG",      # non-hex characters
    "red",          # named colour, not hex
    "#1d9e75; ",    # trailing junk (injection-style)
])
def test_invalid_menu_accent_color_rejected(client, bad_hex):
    tenant = _fresh_tenant()
    token = login(client, tenant)

    resp = client.put("/admin/settings", headers=auth(token), json={"menu_accent_color": bad_hex})
    assert resp.status_code == 422, resp.text


def test_valid_menu_accent_color_accepted_and_audited(client):
    tenant = _fresh_tenant()
    token = login(client, tenant)

    settings_id = client.get("/admin/settings", headers=auth(token)).json()["id"]

    resp = client.put("/admin/settings", headers=auth(token), json={"menu_accent_color": "#1D9E75"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["menu_accent_color"] == "#1D9E75"

    rows = _audit_rows(settings_id, "updated")
    assert any(r.new_value.get("menu_accent_color") == "#1D9E75" for r in rows)


def test_menu_accent_color_case_insensitive_hex_accepted(client):
    tenant = _fresh_tenant()
    token = login(client, tenant)

    resp = client.put("/admin/settings", headers=auth(token), json={"menu_accent_color": "#abcdef"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["menu_accent_color"] == "#abcdef"


# -- Extra/unexpected fields rejected (standing invariant, §3 Input) -----------

def test_settings_update_extra_field_rejected(client):
    tenant = _fresh_tenant()
    token = login(client, tenant)

    resp = client.put(
        "/admin/settings", headers=auth(token),
        json={"menu_template": "classic", "menu_wallpaper": "nope"},
    )
    assert resp.status_code == 422, resp.text


# -- Settings round-trip (both fields together) ---------------------------------

def test_menu_theming_round_trip_both_fields(client):
    tenant = _fresh_tenant()
    token = login(client, tenant)

    resp = client.put(
        "/admin/settings", headers=auth(token),
        json={"menu_template": "bold_cards", "menu_accent_color": "#FF6A00"},
    )
    assert resp.status_code == 200, resp.text

    again = client.get("/admin/settings", headers=auth(token))
    body = again.json()
    assert body["menu_template"] == "bold_cards"
    assert body["menu_accent_color"] == "#FF6A00"

    # And the customer-facing /menu payload reflects the same values, with no
    # extra request needed beyond the one it already makes.
    session_token = _make_session(tenant["restaurant_id"])
    menu = client.get("/menu", headers={"X-Session-Token": session_token})
    assert menu.status_code == 200, menu.text
    assert menu.json()["menu_template"] == "bold_cards"
    assert menu.json()["menu_accent_color"] == "#FF6A00"


# -- Tenant isolation -------------------------------------------------------------

def test_menu_theming_is_tenant_isolated(client):
    a = _fresh_tenant("mt-a")
    b = _fresh_tenant("mt-b")
    token_a = login(client, a)
    token_b = login(client, b)

    resp = client.put(
        "/admin/settings", headers=auth(token_a),
        json={"menu_template": "elegant_list", "menu_accent_color": "#123ABC"},
    )
    assert resp.status_code == 200, resp.text

    b_settings = client.get("/admin/settings", headers=auth(token_b)).json()
    assert b_settings["menu_template"] == "classic"
    assert b_settings["menu_accent_color"] is None


# -- RBAC: non-ADMIN roles cannot edit settings ----------------------------------

def test_menu_theming_update_forbidden_for_non_admin(client):
    from app.core import security
    from app.db.session import SessionLocal
    from app.models.enums import Role
    from app.models.user import User

    tenant = _fresh_tenant()
    db = SessionLocal()
    try:
        waiter = User(
            restaurant_id=uuid.UUID(tenant["restaurant_id"]),
            email=f"waiter.{tenant['slug']}@example.com",
            password_hash=security.hash_password(TEST_PASSWORD),
            role=Role.WAITER,
        )
        db.add(waiter)
        db.commit()
    finally:
        db.close()

    resp = client.post("/auth/login", json={
        "email": f"waiter.{tenant['slug']}@example.com",
        "password": TEST_PASSWORD,
        "restaurant_slug": tenant["slug"],
    })
    assert resp.status_code == 200, resp.text
    waiter_token = resp.json()["access_token"]

    update = client.put(
        "/admin/settings", headers=auth(waiter_token),
        json={"menu_template": "magazine"},
    )
    assert update.status_code == 403, update.text
