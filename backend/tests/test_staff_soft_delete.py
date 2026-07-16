"""
Staff soft-delete (HANDOVER.md §8 known issue #3, CLAUDE.md §3 history/deletes).

Deleting a staff member must deactivate, never DELETE: the account fails login
and JWT validation afterwards, the email becomes reusable (partial unique
index on active rows, migration 0019), the historical row survives, and the
deactivation emits an audit_logs row.
"""

import uuid

from tests.conftest import auth, login

STAFF_EMAIL = "waiter.reusable@example.com"
STAFF_PASSWORD = "W4iter!Password42"


def _create_staff(client, admin_token, email=STAFF_EMAIL):
    return client.post(
        "/admin/staff",
        json={"email": email, "password": STAFF_PASSWORD, "role": "WAITER"},
        headers=auth(admin_token),
    )


def _staff_login(client, seed):
    return client.post(
        "/auth/login",
        json={
            "email": STAFF_EMAIL,
            "password": STAFF_PASSWORD,
            "restaurant_slug": seed["a"]["slug"],
        },
    )


def test_staff_soft_delete_lifecycle(client, seed):
    admin_token = login(client, seed["a"])

    # Create a staff member; they can log in.
    created = _create_staff(client, admin_token)
    assert created.status_code == 201, created.text
    staff_id = created.json()["id"]

    live_login = _staff_login(client, seed)
    assert live_login.status_code == 200
    staff_token = live_login.json()["access_token"]
    assert client.get("/auth/me", headers=auth(staff_token)).status_code == 200

    # Delete → deactivation, not removal.
    deleted = client.delete(f"/admin/staff/{staff_id}", headers=auth(admin_token))
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["is_active"] is False

    # 1. Login now fails.
    assert _staff_login(client, seed).status_code == 401

    # 2. The still-unexpired JWT is rejected (deps.get_current_user checks is_active).
    assert client.get("/auth/me", headers=auth(staff_token)).status_code == 401

    # 3. The row still exists (soft delete) …
    from app.db.session import SessionLocal
    from app.models.user import User

    db = SessionLocal()
    try:
        row = db.get(User, uuid.UUID(staff_id))
        assert row is not None and row.is_active is False

        # 4. … and the deactivation was audited.
        from app.models.audit_log import AuditLog
        from sqlalchemy import select

        audit = db.execute(
            select(AuditLog).where(
                AuditLog.entity_type == "user",
                AuditLog.entity_id == row.id,
                AuditLog.action == "STAFF_DEACTIVATED",
            )
        ).scalar_one()
        assert str(audit.actor_user_id) == seed["a"]["user_id"]
        assert audit.actor_type == "ADMIN"
        assert audit.previous_value == {
            "is_active": True,
            "email": STAFF_EMAIL,
            "role": "WAITER",
        }
        assert audit.new_value == {"is_active": False}
        assert str(audit.restaurant_id) == seed["a"]["restaurant_id"]
    finally:
        db.close()

    # 5. The email is reusable for a brand-new staff member…
    recreated = _create_staff(client, admin_token)
    assert recreated.status_code == 201, recreated.text
    new_id = recreated.json()["id"]
    assert new_id != staff_id

    # …who can log in (the active-rows-only lookup finds exactly one user).
    assert _staff_login(client, seed).status_code == 200

    # 6. Reactivating the OLD account would collide with the reused email → 409.
    reactivate = client.put(
        f"/admin/staff/{staff_id}",
        json={"is_active": True},
        headers=auth(admin_token),
    )
    assert reactivate.status_code == 409


def test_deleting_own_account_still_blocked(client, seed):
    admin_token = login(client, seed["a"])
    resp = client.delete(
        f"/admin/staff/{seed['a']['user_id']}", headers=auth(admin_token)
    )
    assert resp.status_code == 400
