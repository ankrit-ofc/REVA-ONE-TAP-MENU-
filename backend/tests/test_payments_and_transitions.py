"""
Payment idempotency, illegal state transitions, webhook replay, money
integrity, and snapshot immutability (CLAUDE.md §3 money/history + §9).

Pure acceptance tests — each test builds its own world (category → product →
table → session → order) in tenant A through the real API, then attacks the
payment/transition surface the way a Postman/Burp user would.
"""

import base64
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select, text

from tests.conftest import auth, login

CASH = {"method": "CASH"}


# ── World builder ─────────────────────────────────────────────────────────────

def _make_session(rid: uuid.UUID) -> tuple[str, str]:
    """Create a table + ACTIVE session directly (QR scan covered elsewhere)."""
    from app.db.session import SessionLocal
    from app.models.table import Table, TableSession

    token = f"pay-test-session-{uuid.uuid4()}"
    db = SessionLocal()
    try:
        table = Table(restaurant_id=rid, name=f"PT-{uuid.uuid4().hex[:8]}")
        db.add(table)
        db.flush()
        table_id = str(table.id)
        db.add(TableSession(
            restaurant_id=rid,
            table_id=table.id,
            token=token,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        ))
        db.commit()
    finally:
        db.close()
    return token, table_id


def _world(client, seed, *, qty=2, price="250.00", tax="13"):
    """Admin creates menu; a customer session places an order. Returns context."""
    admin = login(client, seed["a"])
    rid = seed["a"]["restaurant_id"]

    cat = client.post("/admin/categories", headers=auth(admin),
                      json={"name": f"Cat-{uuid.uuid4().hex[:8]}"})
    assert cat.status_code == 201, cat.text
    prod = client.post("/admin/products", headers=auth(admin), json={
        "category_id": cat.json()["id"],
        "name": f"Momo-{uuid.uuid4().hex[:8]}",
        "base_price": price,
        "tax_rate": tax,
    })
    assert prod.status_code == 201, prod.text

    session_token, table_id = _make_session(uuid.UUID(rid))
    order = client.post("/orders/items", headers={"X-Session-Token": session_token},
                        json={"items": [{"product_id": prod.json()["id"], "quantity": qty}]})
    assert order.status_code == 200, order.text

    return {
        "admin": admin,
        "rid": rid,
        "product": prod.json(),
        "order": order.json(),
        "session_token": session_token,
        "table_id": table_id,
    }


def _finish_and_invoice(client, w) -> dict:
    """bill requested → MEAL_FINISHED → DRAFT invoice; returns the invoice JSON."""
    oid = w["order"]["id"]
    r = client.post("/orders/request-bill",
                    headers={"X-Session-Token": w["session_token"]}, json={})
    assert r.status_code == 200, r.text
    r = client.post(f"/counter/orders/{oid}/meal-finished", headers=auth(w["admin"]), json={})
    assert r.status_code == 200, r.text
    r = client.post("/invoices", headers=auth(w["admin"]), json={"order_id": oid})
    assert r.status_code == 201, r.text
    return r.json()


def _audit_rows(entity_id: str, action: str | None = None):
    from app.db.session import SessionLocal
    from app.models.audit_log import AuditLog

    db = SessionLocal()
    try:
        stmt = select(AuditLog).where(AuditLog.entity_id == uuid.UUID(entity_id))
        if action:
            stmt = stmt.where(AuditLog.action == action)
        return db.scalars(stmt).all()
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


# ── 1. Counter payment idempotency ────────────────────────────────────────────

def test_counter_payment_idempotency(client, seed):
    w = _world(client, seed)
    inv = _finish_and_invoice(client, w)
    key = f"idem-{uuid.uuid4()}"

    first = client.post(f"/invoices/{inv['id']}/pay", headers={**auth(w["admin"]),
                        "Idempotency-Key": key}, json=CASH)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "PAID"

    # Same key replayed → same result, NOT double-applied.
    replay = client.post(f"/invoices/{inv['id']}/pay", headers={**auth(w["admin"]),
                         "Idempotency-Key": key}, json=CASH)
    assert replay.status_code == 200, replay.text
    assert replay.json()["status"] == "PAID"

    # Exactly ONE payment credit and ONE order close in the audit trail.
    assert len(_audit_rows(inv["id"], "INVOICE_PAID")) == 1
    assert len(_audit_rows(w["order"]["id"], "ORDER_CLOSED")) == 1

    # A DIFFERENT key against the already-paid invoice → rejected.
    other = client.post(f"/invoices/{inv['id']}/pay", headers={**auth(w["admin"]),
                        "Idempotency-Key": f"idem-{uuid.uuid4()}"}, json=CASH)
    assert other.status_code == 409
    assert len(_audit_rows(inv["id"], "INVOICE_PAID")) == 1  # still exactly one


# ── 2. Illegal state transitions ──────────────────────────────────────────────

def test_serving_unapproved_item_rejected(client, seed):
    from app.db.session import SessionLocal
    from app.models.restaurant import RestaurantSettings

    rid = uuid.UUID(seed["a"]["restaurant_id"])
    db = SessionLocal()
    try:
        settings_row = db.execute(select(RestaurantSettings).where(
            RestaurantSettings.restaurant_id == rid)).scalar_one()
        settings_row.require_order_approval = True
        db.commit()

        w = _world(client, seed)
        item = w["order"]["items"][-1]
        assert item["status"] == "PENDING_APPROVAL"

        served = client.post(f"/waiter/items/{item['id']}/served",
                             headers=auth(w["admin"]), json={})
        assert served.status_code == 409, served.text
    finally:
        settings_row.require_order_approval = False
        db.commit()
        db.close()


def test_paying_void_and_paid_invoices_rejected(client, seed):
    from app.db.session import SessionLocal
    from app.models.enums import InvoiceStatus
    from app.models.invoice import Invoice

    w = _world(client, seed)
    inv = _finish_and_invoice(client, w)

    # Force VOID (terminal), then try to pay.
    db = SessionLocal()
    try:
        row = db.get(Invoice, uuid.UUID(inv["id"]))
        row.status = InvoiceStatus.VOID
        db.commit()
    finally:
        db.close()

    r = client.post(f"/invoices/{inv['id']}/pay", headers=auth(w["admin"]), json=CASH)
    assert r.status_code == 409, r.text
    assert _db_invoice(inv["id"]).status.value == "VOID"  # unchanged
    assert len(_audit_rows(inv["id"], "INVOICE_PAID")) == 0


def test_reopen_requires_reason_and_legal_transitions_are_audited(client, seed):
    from app.db.session import SessionLocal
    from app.models.restaurant import RestaurantSettings

    # Reopening is gated by a per-restaurant setting — enable it for this test.
    rid = uuid.UUID(seed["a"]["restaurant_id"])
    db = SessionLocal()
    settings_row = db.execute(select(RestaurantSettings).where(
        RestaurantSettings.restaurant_id == rid)).scalar_one()
    settings_row.allow_order_reopen = True
    db.commit()

    try:
        _run_reopen_assertions(client, seed)
    finally:
        settings_row.allow_order_reopen = False
        db.commit()
        db.close()


def _run_reopen_assertions(client, seed):
    w = _world(client, seed)
    oid = w["order"]["id"]
    admin = auth(w["admin"])

    # Legal: bill requested, then OPEN → MEAL_FINISHED (audited as ORDER_MEAL_FINISHED).
    assert client.post("/orders/request-bill",
                       headers={"X-Session-Token": w["session_token"]},
                       json={}).status_code == 200
    assert client.post(f"/counter/orders/{oid}/meal-finished",
                       headers=admin, json={}).status_code == 200
    assert len(_audit_rows(oid, "ORDER_MEAL_FINISHED")) == 1

    # Illegal: reopen without a reason (empty body / too-short reason) → 422.
    assert client.post(f"/counter/orders/{oid}/reopen",
                       headers=admin, json={}).status_code == 422
    assert client.post(f"/counter/orders/{oid}/reopen",
                       headers=admin, json={"reason": "ab"}).status_code == 422
    assert len(_audit_rows(oid, "ORDER_OPEN")) == 0  # nothing happened

    # Legal: reopen WITH a reason (audited, reason recorded).
    reopened = client.post(f"/counter/orders/{oid}/reopen", headers=admin,
                           json={"reason": "guest wants dessert"})
    assert reopened.status_code == 200, reopened.text
    reopen_audits = _audit_rows(oid, "ORDER_OPEN")
    assert len(reopen_audits) == 1
    assert reopen_audits[0].reason == "guest wants dessert"

    # Legal item transition: serve a NEW item (audited as ITEM_SERVED).
    item_id = w["order"]["items"][0]["id"]
    assert client.post(f"/waiter/items/{item_id}/served",
                       headers=admin, json={}).status_code == 200
    assert len(_audit_rows(item_id, "ITEM_SERVED")) == 1

    # Illegal: SERVED is terminal — serving again must fail.
    assert client.post(f"/waiter/items/{item_id}/served",
                       headers=admin, json={}).status_code == 409

    # Finish + invoice + pay, then verify the full legal chain is audited.
    inv = _finish_and_invoice(client, w)
    assert len(_audit_rows(inv["id"], "INVOICE_GENERATED")) == 1
    assert client.post(f"/invoices/{inv['id']}/pay", headers=admin,
                       json=CASH).status_code == 200
    assert len(_audit_rows(inv["id"], "INVOICE_PAID")) == 1
    assert len(_audit_rows(oid, "ORDER_CLOSED")) == 1

    # Illegal: a CLOSED order cannot be re-finished.
    assert client.post(f"/counter/orders/{oid}/meal-finished",
                       headers=admin, json={}).status_code == 409


# ── 3. Webhook replay ─────────────────────────────────────────────────────────

def _esewa_data_param(invoice_id: str, total: str, txn_code: str) -> str:
    from app.core.config import settings
    from app.payments.esewa import ESewaGateway

    gateway = ESewaGateway(settings)
    payload = {
        "transaction_code": txn_code,
        "status": "COMPLETE",
        "total_amount": total,
        "transaction_uuid": invoice_id,
        "product_code": settings.ESEWA_PRODUCT_CODE,
        "signature": gateway._sign(total, invoice_id),
    }
    return base64.b64encode(json.dumps(payload).encode()).decode()


def test_esewa_webhook_replay_does_not_double_credit(client, seed):
    w = _world(client, seed)
    inv = _finish_and_invoice(client, w)
    data = _esewa_data_param(inv["id"], inv["total"], f"ES-{uuid.uuid4().hex[:10]}")

    first = client.get(f"/webhooks/esewa?data={data}", follow_redirects=False)
    assert first.status_code == 303
    assert "/payment/success" in first.headers["location"]
    assert _db_invoice(inv["id"]).status.value == "PAID"

    # Identical replay → success redirect again, but NO second credit.
    replay = client.get(f"/webhooks/esewa?data={data}", follow_redirects=False)
    assert replay.status_code == 303
    assert "/payment/success" in replay.headers["location"]
    assert len(_audit_rows(inv["id"], "INVOICE_PAID_VIA_GATEWAY")) == 1
    assert len(_audit_rows(w["order"]["id"], "ORDER_CLOSED")) == 1

    # A DIFFERENT transaction against the paid invoice → failure redirect.
    other = _esewa_data_param(inv["id"], inv["total"], f"ES-{uuid.uuid4().hex[:10]}")
    third = client.get(f"/webhooks/esewa?data={other}", follow_redirects=False)
    assert third.status_code == 303
    assert "/payment/failure" in third.headers["location"]
    assert len(_audit_rows(inv["id"], "INVOICE_PAID_VIA_GATEWAY")) == 1


def test_esewa_webhook_bad_signature_rejected(client, seed):
    w = _world(client, seed)
    inv = _finish_and_invoice(client, w)
    payload = {
        "transaction_code": "ES-FORGED", "status": "COMPLETE",
        "total_amount": inv["total"], "transaction_uuid": inv["id"],
        "product_code": "EPAYTEST", "signature": "Zm9yZ2VkLXNpZ25hdHVyZQ==",
    }
    data = base64.b64encode(json.dumps(payload).encode()).decode()
    r = client.get(f"/webhooks/esewa?data={data}", follow_redirects=False)
    assert r.status_code == 303 and "/payment/failure" in r.headers["location"]
    assert _db_invoice(inv["id"]).status.value == "DRAFT"  # untouched


def test_fonepay_webhook_replay_does_not_double_credit(client, seed, monkeypatch):
    from app.core.config import settings

    # Dev config ships Fonepay disabled; give the gateway test credentials so
    # the REAL HMAC-SHA512 verification path runs.
    monkeypatch.setattr(settings, "FONEPAY_MERCHANT_CODE", "TESTPID")
    monkeypatch.setattr(settings, "FONEPAY_SECRET_KEY", "fonepay-test-secret")

    w = _world(client, seed)
    inv = _finish_and_invoice(client, w)
    prn, r_amt = inv["id"], inv["total"]
    dv = hmac.new(b"fonepay-test-secret", f"TESTPID|{prn}|{r_amt}".encode(),
                  hashlib.sha512).hexdigest().upper()
    form = {"PRN": prn, "PID": "TESTPID", "PS": "true", "RC": "successful",
            "UID": f"FP-{uuid.uuid4().hex[:10]}", "BC": "TESTBANK", "INI": "test",
            "P_AMT": r_amt, "R_AMT": r_amt, "DV": dv}

    first = client.post("/webhooks/fonepay", data=form)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "ok"
    assert _db_invoice(inv["id"]).status.value == "PAID"

    replay = client.post("/webhooks/fonepay", data=form)
    assert replay.status_code == 200, replay.text
    assert len(_audit_rows(inv["id"], "INVOICE_PAID_VIA_GATEWAY")) == 1
    assert len(_audit_rows(w["order"]["id"], "ORDER_CLOSED")) == 1


def test_khalti_webhook_replay_does_not_double_credit(client, seed, monkeypatch):
    """Khalti verification is a server-side lookup call to Khalti's API — that
    external hop is stubbed; the replay/idempotency logic under test is the
    shared payment_service.handle_webhook path."""
    from app.payments.base import WebhookPayload
    from app.payments.khalti import KhaltiGateway

    w = _world(client, seed)
    inv = _finish_and_invoice(client, w)
    txn = f"KH-{uuid.uuid4().hex[:10]}"

    def fake_verify(self, headers, raw_body):
        return WebhookPayload(transaction_id=txn, status="PAID",
                              amount=Decimal(inv["total"]), invoice_ref=inv["id"])

    monkeypatch.setattr(KhaltiGateway, "verify_webhook", fake_verify)

    first = client.get("/webhooks/khalti?pidx=test-pidx", follow_redirects=False)
    assert first.status_code == 303 and "/payment/success" in first.headers["location"]
    assert _db_invoice(inv["id"]).status.value == "PAID"

    replay = client.get("/webhooks/khalti?pidx=test-pidx", follow_redirects=False)
    assert replay.status_code == 303 and "/payment/success" in replay.headers["location"]
    assert len(_audit_rows(inv["id"], "INVOICE_PAID_VIA_GATEWAY")) == 1


# ── 4. Money integrity (Decimal end-to-end, no float anywhere) ───────────────

def test_money_is_decimal_end_to_end(client, seed):
    from app.db.session import SessionLocal
    from app.models.invoice import Invoice
    from app.models.order import OrderItem

    w = _world(client, seed, qty=3, price="250.00", tax="13")
    inv = _finish_and_invoice(client, w)

    # API contract: money serialized as strings, never JSON floats.
    for field in ("subtotal", "tax_total", "discount", "total"):
        assert isinstance(inv[field], str), f"{field} serialized as {type(inv[field])}"
    for item in w["order"]["items"]:
        assert isinstance(item["unit_price"], str)

    # Exact Decimal arithmetic: 3 × 250.00 = 750.00, +13% tax = 847.50.
    assert Decimal(inv["subtotal"]) == Decimal("750.00")
    assert Decimal(inv["tax_total"]) == Decimal("97.50")
    assert Decimal(inv["total"]) == Decimal("847.50")

    # ORM layer: every money attribute is Decimal, never float.
    db = SessionLocal()
    try:
        row = db.get(Invoice, uuid.UUID(inv["id"]))
        for name in ("subtotal", "tax_total", "discount", "total"):
            value = getattr(row, name)
            assert isinstance(value, Decimal) and not isinstance(value, float), name
        item_row = db.get(OrderItem, uuid.UUID(w["order"]["items"][0]["id"]))
        assert isinstance(item_row.unit_price, Decimal)
        assert isinstance(item_row.tax_rate, Decimal)

        # Schema layer: no float/double column exists in any money-bearing table.
        floats = db.execute(text(
            """
            SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name IN ('orders', 'order_items', 'order_item_addons',
                                 'invoices', 'products', 'product_variants', 'addons')
              AND data_type IN ('real', 'double precision')
            """
        )).all()
        assert floats == [], f"float columns found: {floats}"
    finally:
        db.close()


# ── 5. Snapshot immutability ──────────────────────────────────────────────────

def test_product_edit_never_alters_historical_order_snapshot(client, seed):
    from app.db.session import SessionLocal
    from app.models.order import OrderItem

    w = _world(client, seed, qty=2, price="250.00", tax="13")
    original_name = w["product"]["name"]
    item_id = w["order"]["items"][0]["id"]

    # Admin rewrites the product after the order exists.
    edited = client.put(f"/admin/products/{w['product']['id']}",
                        headers=auth(w["admin"]),
                        json={"base_price": "999.00", "name": "Renamed Dish"})
    assert edited.status_code == 200, edited.text
    assert edited.json()["base_price"] == "999.00"

    # The historical snapshot is untouched.
    db = SessionLocal()
    try:
        item = db.get(OrderItem, uuid.UUID(item_id))
        assert item.unit_price == Decimal("250.00")
        assert item.product_name == original_name
    finally:
        db.close()

    # And an invoice generated AFTER the edit still bills from the snapshot:
    # 2 × 250.00 = 500.00, +13% = 565.00 (not 999-based).
    inv = _finish_and_invoice(client, w)
    assert Decimal(inv["subtotal"]) == Decimal("500.00")
    assert Decimal(inv["total"]) == Decimal("565.00")
