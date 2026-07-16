"""
Security acceptance baseline — CLAUDE.md §9.

Proves, against a real app + real Postgres, that the API holds against an
attacker with curl/Burp: broken/expired/missing credentials are rejected,
tenants cannot see each other's data, unexpected fields are refused, the
login rate limit engages, and customer endpoints demand a session token.
"""

from tests.conftest import auth, login, make_expired_access_token


# ── 1. Missing / tampered / expired JWT → 401 ────────────────────────────────

def test_missing_token_rejected(client):
    resp = client.get("/auth/me")
    assert resp.status_code == 401


def test_tampered_token_rejected(client, seed):
    token = login(client, seed["a"])
    # Flip the last character of the signature.
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
    resp = client.get("/auth/me", headers=auth(tampered))
    assert resp.status_code == 401


def test_expired_token_rejected(client, seed):
    expired = make_expired_access_token(seed["a"])
    resp = client.get("/auth/me", headers=auth(expired))
    assert resp.status_code == 401


# ── 2. Cross-tenant access → 404, no data leak ───────────────────────────────

def test_cross_tenant_resource_is_404_and_leaks_nothing(client, seed):
    secret_name = "Tenant A Secret Starters"
    token_a = login(client, seed["a"])
    created = client.post(
        "/admin/categories", json={"name": secret_name}, headers=auth(token_a)
    )
    assert created.status_code == 201, created.text
    category_id = created.json()["id"]

    # Owner can read it back.
    own = client.get(f"/admin/categories/{category_id}", headers=auth(token_a))
    assert own.status_code == 200

    # Tenant B gets 404 — indistinguishable from "does not exist" — and the
    # response body must not leak the resource's contents.
    token_b = login(client, seed["b"])
    other = client.get(f"/admin/categories/{category_id}", headers=auth(token_b))
    assert other.status_code == 404
    assert secret_name not in other.text


# ── 3. Extra/unexpected fields → 422 ─────────────────────────────────────────

def test_extra_fields_rejected(client, seed):
    resp = client.post(
        "/auth/login",
        json={
            "email": seed["a"]["email"],
            "password": "irrelevant-password",
            "restaurant_slug": seed["a"]["slug"],
            # Forged authority fields an attacker might inject:
            "role": "SUPERADMIN",
            "restaurant_id": seed["b"]["restaurant_id"],
        },
    )
    assert resp.status_code == 422


# ── 4. Login rate limit on repeated failures ─────────────────────────────────

def test_login_rate_limit_triggers(client, seed):
    body = {
        "email": seed["a"]["email"],
        "password": "definitely-wrong-password",
        "restaurant_slug": seed["a"]["slug"],
    }
    # RATE_LIMIT_LOGIN defaults to 5/minute: five failures pass through as 401…
    for _ in range(5):
        resp = client.post("/auth/login", json=body)
        assert resp.status_code == 401, resp.text
    # …the sixth attempt inside the window is throttled.
    resp = client.post("/auth/login", json=body)
    assert resp.status_code == 429


# ── 5. Customer endpoint without X-Session-Token → 401 ──────────────────────

def test_customer_menu_requires_session_token(client, seed):
    resp = client.get("/menu")
    assert resp.status_code == 401

    resp = client.get("/menu", headers={"X-Session-Token": "forged-or-guessed-token"})
    assert resp.status_code == 401
