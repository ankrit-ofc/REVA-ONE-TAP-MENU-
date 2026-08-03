"""
Customer contact capture: POST /session/contact, the customers table, the
order->invoice carrier copy, and the Resend receipt service.

CONFTEST TRAP (CLAUDE.md): `database` and `seed` are session-scoped with no
rollback, and files run alphabetically — rows written by any test are visible to
every later one. Every test here therefore builds its OWN restaurant via
_fresh_tenant() and asserts only against ids it created. Nothing below depends
on seed["a"]/seed["b"] being clean.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text

from tests.conftest import TEST_PASSWORD, auth, login


# ── World builders ────────────────────────────────────────────────────────────

def _fresh_tenant(prefix: str = "cc") -> dict:
    """A brand-new restaurant + settings + ADMIN. Never reuses a seeded tenant."""
    from app.core import security
    from app.db.session import SessionLocal
    from app.models.enums import Role
    from app.models.restaurant import Restaurant, RestaurantSettings
    from app.models.user import User

    slug = f"{prefix}-{uuid.uuid4().hex[:10]}"
    db = SessionLocal()
    try:
        restaurant = Restaurant(name=f"Contact {slug}", slug=slug, is_active=True)
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


def _make_session(rid: str) -> tuple[str, str]:
    """Table + ACTIVE session created directly (the QR scan path is tested elsewhere)."""
    from app.db.session import SessionLocal
    from app.models.table import Table, TableSession

    token = f"contact-test-{uuid.uuid4()}"
    db = SessionLocal()
    try:
        table = Table(restaurant_id=uuid.UUID(rid), name=f"CT-{uuid.uuid4().hex[:8]}")
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


def _world(client, prefix: str = "cc", *, qty: int = 2, price: str = "250.00") -> dict:
    """Fresh tenant -> category -> product -> table session -> placed order."""
    tenant = _fresh_tenant(prefix)
    admin = login(client, tenant)
    rid = tenant["restaurant_id"]

    cat = client.post("/admin/categories", headers=auth(admin),
                      json={"name": f"Cat-{uuid.uuid4().hex[:8]}"})
    assert cat.status_code == 201, cat.text
    prod = client.post("/admin/products", headers=auth(admin), json={
        "category_id": cat.json()["id"],
        "name": f"Momo-{uuid.uuid4().hex[:8]}",
        "base_price": price,
        "tax_rate": "13",
    })
    assert prod.status_code == 201, prod.text

    session_token, table_id = _make_session(rid)
    order = client.post("/orders/items", headers={"X-Session-Token": session_token},
                        json={"items": [{"product_id": prod.json()["id"], "quantity": qty}]})
    assert order.status_code == 200, order.text

    return {
        "tenant": tenant,
        "admin": admin,
        "rid": rid,
        "product": prod.json(),
        "order": order.json(),
        "session_token": session_token,
        "table_id": table_id,
    }


def _sess(token: str) -> dict:
    return {"X-Session-Token": token}


def _request_bill(client, w) -> None:
    r = client.post("/orders/request-bill", headers=_sess(w["session_token"]), json={})
    assert r.status_code == 200, r.text


def _finish_and_invoice(client, w) -> dict:
    """bill requested -> MEAL_FINISHED -> DRAFT invoice (the staff billing path)."""
    oid = w["order"]["id"]
    _request_bill(client, w)
    r = client.post(f"/counter/orders/{oid}/meal-finished", headers=auth(w["admin"]), json={})
    assert r.status_code == 200, r.text
    r = client.post("/invoices", headers=auth(w["admin"]), json={"order_id": oid})
    assert r.status_code == 201, r.text
    return r.json()


# ── DB probes ─────────────────────────────────────────────────────────────────

def _customers(rid: str) -> list:
    from app.db.session import SessionLocal
    from app.models.customer import Customer

    db = SessionLocal()
    try:
        return list(db.scalars(
            select(Customer).where(Customer.restaurant_id == uuid.UUID(rid))
        ).all())
    finally:
        db.close()


def _db_order(order_id: str):
    from app.db.session import SessionLocal
    from app.models.order import Order

    db = SessionLocal()
    try:
        return db.get(Order, uuid.UUID(order_id))
    finally:
        db.close()


def _db_invoice(invoice_id: str):
    from app.db.session import SessionLocal
    from app.models.invoice import Invoice

    db = SessionLocal()
    try:
        return db.get(Invoice, uuid.UUID(invoice_id))
    finally:
        db.close()


def _invalidate_session(token: str, *, minutes_ago: float) -> None:
    """Mark a session INVALIDATED with a backdated invalidated_at."""
    from app.db.session import SessionLocal
    from app.models.enums import SessionStatus
    from app.models.table import TableSession

    db = SessionLocal()
    try:
        session = db.execute(
            select(TableSession).where(TableSession.token == token)
        ).scalar_one()
        session.status = SessionStatus.INVALIDATED
        session.invalidated_at = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
        db.commit()
    finally:
        db.close()


# ── 1. Happy path ─────────────────────────────────────────────────────────────

def test_valid_capture_creates_customer_and_links_order(client, seed):
    w = _world(client, "cc-ok")
    _request_bill(client, w)

    r = client.post("/session/contact", headers=_sess(w["session_token"]),
                    json={"email": "diner@example.com", "name": "Ram", "phone": "9800000000"})
    assert r.status_code == 200, r.text
    # Write-only: the ack carries no stored data back.
    assert r.json() == {"status": "ok"}

    rows = _customers(w["rid"])
    assert len(rows) == 1
    assert rows[0].email == "diner@example.com"
    assert rows[0].name == "Ram"
    assert rows[0].phone == "9800000000"

    # The carrier is set while the order is still open (no invoice exists yet).
    assert _db_order(w["order"]["id"]).customer_id == rows[0].id


def test_invalid_email_rejected(client, seed):
    w = _world(client, "cc-bademail")
    for bad in ("not-an-email", "@example.com", "a@b", ""):
        r = client.post("/session/contact", headers=_sess(w["session_token"]),
                        json={"email": bad})
        assert r.status_code == 422, f"{bad!r} -> {r.status_code} {r.text}"
    assert _customers(w["rid"]) == []


def test_extra_field_rejected(client, seed):
    """extra='forbid' (§3 input) — a forged field must 422, not be ignored."""
    w = _world(client, "cc-extra")
    r = client.post("/session/contact", headers=_sess(w["session_token"]),
                    json={"email": "x@example.com", "restaurant_id": str(uuid.uuid4())})
    assert r.status_code == 422, r.text


def test_name_and_phone_optional_and_blank_becomes_null(client, seed):
    w = _world(client, "cc-optional")

    r = client.post("/session/contact", headers=_sess(w["session_token"]),
                    json={"email": "minimal@example.com"})
    assert r.status_code == 200, r.text
    rows = _customers(w["rid"])
    assert len(rows) == 1
    assert rows[0].name is None and rows[0].phone is None

    # Whitespace-only strings normalise to NULL rather than being stored.
    w2 = _world(client, "cc-blank")
    r = client.post("/session/contact", headers=_sess(w2["session_token"]),
                    json={"email": "  blank@example.com  ", "name": "   ", "phone": ""})
    assert r.status_code == 200, r.text
    rows2 = _customers(w2["rid"])
    assert len(rows2) == 1
    assert rows2[0].email == "blank@example.com"  # trimmed
    assert rows2[0].name is None and rows2[0].phone is None


# ── 2. Upsert semantics ───────────────────────────────────────────────────────

def test_same_email_twice_updates_instead_of_duplicating(client, seed):
    w = _world(client, "cc-upsert")

    r = client.post("/session/contact", headers=_sess(w["session_token"]),
                    json={"email": "repeat@example.com"})
    assert r.status_code == 200, r.text

    # Second submission adds a name; must update the same row, not insert.
    r = client.post("/session/contact", headers=_sess(w["session_token"]),
                    json={"email": "repeat@example.com", "name": "Sita", "phone": "9811111111"})
    assert r.status_code == 200, r.text

    rows = _customers(w["rid"])
    assert len(rows) == 1, "same email must not create a second customer"
    assert rows[0].name == "Sita"
    assert rows[0].phone == "9811111111"

    # A third submission omitting the name must NOT blank the one we hold.
    r = client.post("/session/contact", headers=_sess(w["session_token"]),
                    json={"email": "repeat@example.com"})
    assert r.status_code == 200, r.text
    rows = _customers(w["rid"])
    assert len(rows) == 1
    assert rows[0].name == "Sita"


def test_email_normalisation_is_case_insensitive(client, seed):
    """Ram@X.com and ram@x.com are one human, therefore one row."""
    w = _world(client, "cc-case")

    r = client.post("/session/contact", headers=_sess(w["session_token"]),
                    json={"email": "Ram@Example.COM", "name": "Ram"})
    assert r.status_code == 200, r.text
    r = client.post("/session/contact", headers=_sess(w["session_token"]),
                    json={"email": "  ram@example.com ", "phone": "9822222222"})
    assert r.status_code == 200, r.text

    rows = _customers(w["rid"])
    assert len(rows) == 1, "case/whitespace variants must resolve to the same row"
    assert rows[0].email == "ram@example.com"
    assert rows[0].name == "Ram"
    assert rows[0].phone == "9822222222"


def test_same_email_in_another_restaurant_is_a_separate_record(client, seed):
    a = _world(client, "cc-tenant-a")
    b = _world(client, "cc-tenant-b")
    assert a["rid"] != b["rid"]

    shared = "shared@example.com"
    for w in (a, b):
        r = client.post("/session/contact", headers=_sess(w["session_token"]),
                        json={"email": shared})
        assert r.status_code == 200, r.text

    rows_a = _customers(a["rid"])
    rows_b = _customers(b["rid"])
    assert len(rows_a) == 1 and len(rows_b) == 1
    assert rows_a[0].id != rows_b[0].id, "tenants must not share a customer row"
    assert rows_a[0].restaurant_id != rows_b[0].restaurant_id


# ── 3. Carrier -> invoice copy (both invoice-minting paths) ───────────────────

def test_capture_at_request_bill_reaches_the_invoice(client, seed):
    """The standard staff path: POST /invoices copies orders.customer_id over."""
    w = _world(client, "cc-carry")
    _request_bill(client, w)

    r = client.post("/session/contact", headers=_sess(w["session_token"]),
                    json={"email": "carry@example.com"})
    assert r.status_code == 200, r.text
    customer_id = _customers(w["rid"])[0].id

    oid = w["order"]["id"]
    r = client.post(f"/counter/orders/{oid}/meal-finished", headers=auth(w["admin"]), json={})
    assert r.status_code == 200, r.text
    inv = client.post("/invoices", headers=auth(w["admin"]), json={"order_id": oid})
    assert inv.status_code == 201, inv.text

    assert _db_invoice(inv.json()["id"]).customer_id == customer_id


def test_quick_bill_path_copies_customer_to_invoice(client, seed):
    """
    quick_bill_and_close mints its OWN invoice — a second place the carrier copy
    could be forgotten, so it gets its own test rather than riding on the first.
    """
    w = _world(client, "cc-quickbill")
    _request_bill(client, w)

    r = client.post("/session/contact", headers=_sess(w["session_token"]),
                    json={"email": "quick@example.com"})
    assert r.status_code == 200, r.text
    customer_id = _customers(w["rid"])[0].id

    oid = w["order"]["id"]
    r = client.post(f"/counter/orders/{oid}/quick-bill", headers=auth(w["admin"]),
                    json={"method": "CASH"})
    assert r.status_code == 200, r.text

    invoice = _db_invoice(r.json()["id"])
    assert invoice.customer_id == customer_id, "quick-bill dropped the captured customer"


# ── 4. Grace window (the widened auth surface) ────────────────────────────────

def test_capture_allowed_just_after_payment_invalidates_the_session(client, seed):
    w = _world(client, "cc-grace-ok")
    invoice = _finish_and_invoice(client, w)
    r = client.post(f"/invoices/{invoice['id']}/pay", headers=auth(w["admin"]),
                    json={"method": "CASH"})
    assert r.status_code == 200, r.text

    # Payment invalidated the session; the post-payment form must still submit.
    r = client.post("/session/contact", headers=_sess(w["session_token"]),
                    json={"email": "afterpay@example.com"})
    assert r.status_code == 200, r.text
    assert _db_invoice(invoice["id"]).customer_id == _customers(w["rid"])[0].id


def test_session_invalidated_beyond_grace_window_is_rejected(client, seed):
    """31 minutes > the 30-minute window: the token is dead for writes too."""
    w = _world(client, "cc-grace-expired")
    _invalidate_session(w["session_token"], minutes_ago=31)

    r = client.post("/session/contact", headers=_sess(w["session_token"]),
                    json={"email": "toolate@example.com"})
    assert r.status_code == 401, r.text
    assert _customers(w["rid"]) == []


def test_expired_session_is_never_accepted_by_the_grace_path(client, seed):
    """Only INVALIDATED (what payment leaves) is forgiven — not TTL expiry."""
    from app.db.session import SessionLocal
    from app.models.table import TableSession

    w = _world(client, "cc-grace-expiry")
    db = SessionLocal()
    try:
        session = db.execute(
            select(TableSession).where(TableSession.token == w["session_token"])
        ).scalar_one()
        session.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    finally:
        db.close()

    r = client.post("/session/contact", headers=_sess(w["session_token"]),
                    json={"email": "expired@example.com"})
    assert r.status_code == 401, r.text
    assert _customers(w["rid"]) == []


def test_grace_token_cannot_write_to_another_tables_bill(client, seed):
    """
    A stale token stays confined to its own visit. Two tables in ONE restaurant:
    table A's paid-and-invalidated token must not attach a customer to table B's
    bill, even though both are inside the same tenant and the window is open.
    """
    a = _world(client, "cc-crosstable")
    rid = a["rid"]

    # Second table + order in the same restaurant, billed and paid.
    b_token, _b_table = _make_session(rid)
    r = client.post("/orders/items", headers=_sess(b_token),
                    json={"items": [{"product_id": a["product"]["id"], "quantity": 1}]})
    assert r.status_code == 200, r.text
    b_order_id = r.json()["id"]
    r = client.post("/orders/request-bill", headers=_sess(b_token), json={})
    assert r.status_code == 200, r.text
    r = client.post(f"/counter/orders/{b_order_id}/quick-bill", headers=auth(a["admin"]),
                    json={"method": "CASH"})
    assert r.status_code == 200, r.text
    b_invoice_id = r.json()["id"]

    # Table A pays too, then submits contact within its grace window.
    a_invoice = _finish_and_invoice(client, a)
    r = client.post(f"/invoices/{a_invoice['id']}/pay", headers=auth(a["admin"]),
                    json={"method": "CASH"})
    assert r.status_code == 200, r.text
    r = client.post("/session/contact", headers=_sess(a["session_token"]),
                    json={"email": "tablea@example.com"})
    assert r.status_code == 200, r.text

    customer_id = _customers(rid)[0].id
    assert _db_invoice(a_invoice["id"]).customer_id == customer_id
    assert _db_invoice(b_invoice_id).customer_id is None, \
        "table A's token reached table B's invoice"


def test_stale_token_cannot_overwrite_a_later_partys_bill(client, seed):
    """
    The reuse case the grace window could enable: a second party sits at the SAME
    table while the previous guest's token is still inside the window. The old
    token must not attach its customer to the new party's bill — the
    created_at <= invalidated_at filter is what prevents it.
    """
    w = _world(client, "cc-secondparty")
    rid = w["rid"]
    table_id = w["table_id"]

    # First party pays; their session is invalidated (grace window now open).
    first_invoice = _finish_and_invoice(client, w)
    r = client.post(f"/invoices/{first_invoice['id']}/pay", headers=auth(w["admin"]),
                    json={"method": "CASH"})
    assert r.status_code == 200, r.text

    # Second party at the same table: new session, new order, own invoice.
    from app.db.session import SessionLocal
    from app.models.table import TableSession

    second_token = f"contact-test-{uuid.uuid4()}"
    db = SessionLocal()
    try:
        db.add(TableSession(
            restaurant_id=uuid.UUID(rid),
            table_id=uuid.UUID(table_id),
            token=second_token,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        ))
        db.commit()
    finally:
        db.close()

    r = client.post("/orders/items", headers=_sess(second_token),
                    json={"items": [{"product_id": w["product"]["id"], "quantity": 1}]})
    assert r.status_code == 200, r.text
    second_order_id = r.json()["id"]
    r = client.post("/orders/request-bill", headers=_sess(second_token), json={})
    assert r.status_code == 200, r.text
    r = client.post(f"/counter/orders/{second_order_id}/quick-bill",
                    headers=auth(w["admin"]), json={"method": "CASH"})
    assert r.status_code == 200, r.text
    second_invoice_id = r.json()["id"]

    # The FIRST party's stale token submits now, still inside the window.
    r = client.post("/session/contact", headers=_sess(w["session_token"]),
                    json={"email": "firstparty@example.com"})
    assert r.status_code == 200, r.text

    customer_id = _customers(rid)[0].id
    assert _db_invoice(first_invoice["id"]).customer_id == customer_id
    assert _db_invoice(second_invoice_id).customer_id is None, \
        "a stale token reached the next party's bill"


def test_paid_invoice_customer_is_not_reassigned(client, seed):
    """A settled bill's payer is not rewritable by a second, different submission."""
    w = _world(client, "cc-noreassign")
    invoice = _finish_and_invoice(client, w)
    r = client.post(f"/invoices/{invoice['id']}/pay", headers=auth(w["admin"]),
                    json={"method": "CASH"})
    assert r.status_code == 200, r.text

    r = client.post("/session/contact", headers=_sess(w["session_token"]),
                    json={"email": "first@example.com"})
    assert r.status_code == 200, r.text
    first_id = _db_invoice(invoice["id"]).customer_id
    assert first_id is not None

    r = client.post("/session/contact", headers=_sess(w["session_token"]),
                    json={"email": "second@example.com"})
    assert r.status_code == 409, r.text
    assert _db_invoice(invoice["id"]).customer_id == first_id

    # Re-submitting the SAME address stays idempotent, not a conflict.
    r = client.post("/session/contact", headers=_sess(w["session_token"]),
                    json={"email": "first@example.com"})
    assert r.status_code == 200, r.text


def test_grace_path_sets_the_rls_guc(client, seed):
    """
    The widened dependency must still pin app.current_restaurant_id from the
    token, or the RLS net is off for exactly these requests.
    """
    from app.core.deps import get_contact_capture_session
    from app.db.session import SessionLocal

    w = _world(client, "cc-guc")
    _invalidate_session(w["session_token"], minutes_ago=1)

    db = SessionLocal()
    try:
        session = get_contact_capture_session(x_session_token=w["session_token"], db=db)
        guc = db.execute(text("SELECT current_setting('app.current_restaurant_id', TRUE)")).scalar()
        assert guc == w["rid"]
        assert str(session.restaurant_id) == w["rid"]
    finally:
        db.close()


def test_missing_and_bogus_tokens_are_rejected(client, seed):
    r = client.post("/session/contact", json={"email": "nobody@example.com"})
    assert r.status_code == 401, r.text
    r = client.post("/session/contact", headers=_sess("not-a-real-token"),
                    json={"email": "nobody@example.com"})
    assert r.status_code == 401, r.text


# ── 5. Receipt email service ──────────────────────────────────────────────────

def test_receipt_service_no_ops_safely_without_api_key(client, seed, caplog):
    """
    Empty RESEND_API_KEY must log-and-succeed, never raise — that is what lets
    the whole feature ship before Resend is configured.
    """
    from app.core.config import settings
    from app.db.session import SessionLocal
    from app.services import receipt_email

    assert settings.RESEND_API_KEY == "", "test env must not carry a real Resend key"

    w = _world(client, "cc-nokey")
    _request_bill(client, w)
    r = client.post("/session/contact", headers=_sess(w["session_token"]),
                    json={"email": "nokey@example.com"})
    assert r.status_code == 200, r.text

    oid = w["order"]["id"]
    r = client.post(f"/counter/orders/{oid}/quick-bill", headers=auth(w["admin"]),
                    json={"method": "CASH"})
    assert r.status_code == 200, r.text
    invoice_id = r.json()["id"]

    # Payment succeeded and the receipt was marked sent, with no key configured.
    invoice = _db_invoice(invoice_id)
    assert invoice.receipt_sent_at is not None

    # A direct second call is a no-op and still does not raise.
    db = SessionLocal()
    try:
        assert receipt_email.send_receipt(db, uuid.UUID(w["rid"]), uuid.UUID(invoice_id)) is False
    finally:
        db.close()


def test_receipt_is_not_sent_twice(client, seed):
    from app.db.session import SessionLocal
    from app.services import receipt_email

    w = _world(client, "cc-once")
    _request_bill(client, w)
    r = client.post("/session/contact", headers=_sess(w["session_token"]),
                    json={"email": "once@example.com"})
    assert r.status_code == 200, r.text

    invoice = _finish_and_invoice(client, w)
    r = client.post(f"/invoices/{invoice['id']}/pay", headers=auth(w["admin"]),
                    json={"method": "CASH"})
    assert r.status_code == 200, r.text

    first_stamp = _db_invoice(invoice["id"]).receipt_sent_at
    assert first_stamp is not None

    db = SessionLocal()
    try:
        assert receipt_email.send_receipt(db, uuid.UUID(w["rid"]), uuid.UUID(invoice["id"])) is False
    finally:
        db.close()
    assert _db_invoice(invoice["id"]).receipt_sent_at == first_stamp


def test_no_receipt_stamp_when_no_contact_was_captured(client, seed):
    """Skipping the form must leave billing completely untouched."""
    w = _world(client, "cc-skipped")
    invoice = _finish_and_invoice(client, w)
    r = client.post(f"/invoices/{invoice['id']}/pay", headers=auth(w["admin"]),
                    json={"method": "CASH"})
    assert r.status_code == 200, r.text

    row = _db_invoice(invoice["id"])
    assert row.customer_id is None
    assert row.receipt_sent_at is None


def test_receipt_body_uses_invoice_totals_not_re_derived_ones(client, seed):
    from app.db.session import SessionLocal
    from app.services import invoice_service, receipt_email

    w = _world(client, "cc-receipt", qty=2, price="250.00")
    invoice = _finish_and_invoice(client, w)

    db = SessionLocal()
    try:
        receipt = invoice_service.build_receipt(
            db, uuid.UUID(w["rid"]), uuid.UUID(invoice["id"])
        )
    finally:
        db.close()

    body = receipt_email._render_text(receipt, "Ram")
    assert str(receipt["invoice_number"]) in body
    assert f"{receipt['total']:.2f}" in body
    assert receipt["items"], "receipt should be itemised"
    assert receipt["items"][0]["product_name"] in body


def test_log_redaction_hides_the_address(client, seed):
    from app.services.customer_service import redact_email

    assert redact_email("ram@example.com") == "r***@example.com"
    assert "ram@example.com" not in redact_email("ram@example.com")


# ── 6. PII must not leak into staff-facing responses ──────────────────────────

def test_customer_pii_absent_from_staff_endpoint_responses(client, seed):
    """
    Capturing contact details must not widen any staff response body. Adding
    columns to orders/invoices is only safe because every staff response model
    lists its fields explicitly — this asserts that, rather than trusting it.
    """
    w = _world(client, "cc-pii")
    _request_bill(client, w)
    r = client.post("/session/contact", headers=_sess(w["session_token"]),
                    json={"email": "private@example.com", "name": "Private Person",
                          "phone": "9899999999"})
    assert r.status_code == 200, r.text

    oid = w["order"]["id"]
    r = client.post(f"/counter/orders/{oid}/quick-bill", headers=auth(w["admin"]),
                    json={"method": "CASH"})
    assert r.status_code == 200, r.text
    invoice_id = r.json()["id"]

    headers = auth(w["admin"])
    responses = [
        client.get("/counter/orders", headers=headers),
        client.get("/counter/open-orders", headers=headers),
        client.get("/counter/order-history", headers=headers),
        client.get("/waiter/tables", headers=headers),
        client.get("/waiter/open-orders", headers=headers),
        client.get("/waiter/ready", headers=headers),
        client.get("/waiter/calls", headers=headers),
        client.get("/kitchen/queue", headers=headers),
        client.get("/dashboard/active-tables", headers=headers),
        client.get("/dashboard/revenue-today", headers=headers),
        client.get(f"/invoices/{invoice_id}", headers=headers),
        client.get(f"/invoices/{invoice_id}/receipt", headers=headers),
    ]

    for resp in responses:
        assert resp.status_code == 200, f"{resp.request.url} -> {resp.status_code} {resp.text}"
        body = resp.text
        assert "private@example.com" not in body, f"email leaked via {resp.request.url}"
        assert "Private Person" not in body, f"name leaked via {resp.request.url}"
        assert "9899999999" not in body, f"phone leaked via {resp.request.url}"
        assert "customer_id" not in body, f"customer_id exposed via {resp.request.url}"
