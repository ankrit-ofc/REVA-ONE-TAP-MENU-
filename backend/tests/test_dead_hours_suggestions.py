"""
Dead Hours suggestions: GET /admin/offers/suggestions and dead_hours_service.

CONFTEST TRAP (CLAUDE.md): `database` and `seed` are session-scoped with no
rollback, and files run alphabetically — rows written by any test are visible to
every later one. Every test here therefore builds its OWN restaurant via
_fresh_tenant() and asserts only against ids it created. Nothing below depends
on seed["a"]/seed["b"] being clean, and nothing asserts on a full-list result
for a shared tenant.

The suggestion engine reads PAID invoices only, so each test seeds invoices
directly at chosen LOCAL wall-clock instants rather than driving the ordering
and billing endpoints — the arithmetic under test is the local-time bucketing,
not the order lifecycle.
"""

import uuid
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from tests.conftest import TEST_PASSWORD, auth, login


# ── World builders ────────────────────────────────────────────────────────────

def _fresh_tenant(prefix: str = "dh", tz: str = "Asia/Kathmandu") -> dict:
    """A brand-new restaurant + settings + ADMIN. Never reuses a seeded tenant."""
    from app.core import security
    from app.db.session import SessionLocal
    from app.models.enums import Role
    from app.models.restaurant import Restaurant, RestaurantSettings
    from app.models.user import User

    slug = f"{prefix}-{uuid.uuid4().hex[:10]}"
    db = SessionLocal()
    try:
        restaurant = Restaurant(name=f"Dead Hours {slug}", slug=slug, is_active=True)
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


def _staff_user(tenant: dict, role_name: str) -> dict:
    """An extra non-ADMIN login in an existing tenant, for RBAC assertions."""
    from app.core import security
    from app.db.session import SessionLocal
    from app.models.enums import Role
    from app.models.user import User

    email = f"{role_name.lower()}.{uuid.uuid4().hex[:10]}@example.com"
    db = SessionLocal()
    try:
        db.add(User(
            restaurant_id=uuid.UUID(tenant["restaurant_id"]),
            email=email,
            password_hash=security.hash_password(TEST_PASSWORD),
            role=Role[role_name],
        ))
        db.commit()
    finally:
        db.close()
    return {"email": email, "slug": tenant["slug"]}


def _table(rid: str) -> str:
    from app.db.session import SessionLocal
    from app.models.table import Table

    db = SessionLocal()
    try:
        table = Table(restaurant_id=uuid.UUID(rid), name=f"DH-{uuid.uuid4().hex[:8]}")
        db.add(table)
        db.commit()
        return str(table.id)
    finally:
        db.close()


def _recent_weekdays(tz: ZoneInfo, weekday: int, count: int) -> list[date]:
    """The `count` most recent past local dates falling on `weekday`.

    Walks back from YESTERDAY: the service excludes today (a part-finished day
    is not a sample) and looks back exactly 8 weeks, which is 8 occurrences of
    every weekday, so count<=8 always lands inside the window.
    """
    today = datetime.now(tz).date()
    out: list[date] = []
    cursor = today - timedelta(days=1)
    while len(out) < count:
        if cursor.weekday() == weekday:
            out.append(cursor)
        cursor -= timedelta(days=1)
    return out


def _seed(
    rid: str,
    table_id: str,
    tz: ZoneInfo,
    days: list[date],
    hour_amounts: dict[int, str],
    *,
    status: str = "PAID",
    start_order_number: int = 1,
) -> list[datetime]:
    """One invoice per (day, hour) at LOCAL hour:30, returning the UTC instants.

    Orders are CLOSED so the `uq_orders_active_table` partial unique index (at
    most one OPEN/MEAL_FINISHED order per table) does not reject the batch.
    """
    from app.db.session import SessionLocal
    from app.models.enums import InvoiceStatus, OrderStatus
    from app.models.invoice import Invoice
    from app.models.order import Order

    utc_instants: list[datetime] = []
    number = start_order_number
    db = SessionLocal()
    try:
        for day in days:
            for hour, amount in hour_amounts.items():
                when_utc = datetime.combine(
                    day, time(hour, 30), tzinfo=tz
                ).astimezone(timezone.utc)
                utc_instants.append(when_utc)

                order = Order(
                    restaurant_id=uuid.UUID(rid),
                    table_id=uuid.UUID(table_id),
                    order_number=number,
                    status=OrderStatus.CLOSED,
                    created_at=when_utc,
                )
                db.add(order)
                db.flush()
                db.add(Invoice(
                    restaurant_id=uuid.UUID(rid),
                    order_id=order.id,
                    invoice_number=f"INV-TEST-{number:05d}",
                    status=InvoiceStatus[status],
                    subtotal=Decimal(amount),
                    total=Decimal(amount),
                    created_at=when_utc,
                ))
                number += 1
        db.commit()
    finally:
        db.close()
    return utc_instants


# A plausible trading day: busy lunch, dead mid-afternoon, busy dinner.
_BUSY = {11: "800.00", 12: "1500.00", 13: "1200.00",
         17: "900.00", 18: "1600.00", 19: "2000.00", 20: "1700.00", 21: "1100.00"}


def _fetch(client, tenant: dict) -> dict:
    token = login(client, tenant)
    resp = client.get("/admin/offers/suggestions", headers=auth(token))
    assert resp.status_code == 200, resp.text
    return resp.json()


# ── Core behaviour ────────────────────────────────────────────────────────────

def test_dead_stretch_is_found_and_reported(client):
    """8 Tuesdays with nothing sold 14:00-17:00 → exactly that window."""
    tenant = _fresh_tenant()
    tz = ZoneInfo(tenant["tz"])
    table_id = _table(tenant["restaurant_id"])
    _seed(tenant["restaurant_id"], table_id, tz,
          _recent_weekdays(tz, 1, 8), _BUSY)

    body = _fetch(client, tenant)

    assert body["window_hours"] == 3
    assert body["lookback_weeks"] == 8
    assert body["min_samples"] == 4
    assert body["currency"] == "NPR"
    assert body["timezone"] == "Asia/Kathmandu"

    assert len(body["windows"]) == 1, body["windows"]
    window = body["windows"][0]
    assert window["weekday"] == 1
    assert window["weekday_label"] == "Tuesday"
    assert window["start_hour"] == 14
    assert window["end_hour"] == 17
    assert Decimal(window["median_revenue"]) == Decimal("0.00")
    # The window figure is reported against the whole trading day, so "Rs 0"
    # can be read at scale rather than in a vacuum.
    assert Decimal(window["day_median_revenue"]) == Decimal("10800.00")
    assert window["sample_size"] == 8


def test_below_min_samples_suggests_nothing(client):
    """3 Tuesdays is not enough history — refuse rather than guess."""
    tenant = _fresh_tenant()
    tz = ZoneInfo(tenant["tz"])
    table_id = _table(tenant["restaurant_id"])
    _seed(tenant["restaurant_id"], table_id, tz,
          _recent_weekdays(tz, 1, 3), _BUSY)

    body = _fetch(client, tenant)
    assert body["windows"] == []
    # The thresholds ride along so the UI can explain the empty state.
    assert body["min_samples"] == 4


def test_no_history_at_all_suggests_nothing(client):
    tenant = _fresh_tenant()
    body = _fetch(client, tenant)
    assert body["windows"] == []


def test_closed_hours_are_never_suggested(client):
    """A dinner-only restaurant must not be told its 3am is quiet."""
    tenant = _fresh_tenant()
    tz = ZoneInfo(tenant["tz"])
    table_id = _table(tenant["restaurant_id"])
    dinner_only = {18: "2000.00", 19: "2400.00", 20: "600.00",
                   21: "2200.00", 22: "1900.00"}
    _seed(tenant["restaurant_id"], table_id, tz,
          _recent_weekdays(tz, 4, 8), dinner_only)

    body = _fetch(client, tenant)
    assert body["windows"], "expected a suggestion inside trading hours"
    for window in body["windows"]:
        assert window["start_hour"] >= 18, window
        # Never proposes a window an offer could not express (no midnight wrap).
        assert window["end_hour"] <= 23, window


def test_only_paid_invoices_count(client):
    """DRAFT bills in the dead stretch must not disguise it as busy."""
    tenant = _fresh_tenant()
    tz = ZoneInfo(tenant["tz"])
    rid = tenant["restaurant_id"]
    table_id = _table(rid)
    tuesdays = _recent_weekdays(tz, 1, 8)
    _seed(rid, table_id, tz, tuesdays, _BUSY)
    # Large DRAFT invoices right across 14:00-17:00. If these counted, that
    # stretch would look like the busiest part of the day.
    _seed(rid, table_id, tz, tuesdays,
          {14: "9000.00", 15: "9000.00", 16: "9000.00"},
          status="DRAFT", start_order_number=10_000)

    body = _fetch(client, tenant)
    assert len(body["windows"]) == 1
    assert (body["windows"][0]["start_hour"], body["windows"][0]["end_hour"]) == (14, 17)


def test_weakest_first_and_one_window_per_weekday(client):
    """Ranked quietest-first, and a weekday never appears twice."""
    tenant = _fresh_tenant()
    tz = ZoneInfo(tenant["tz"])
    rid = tenant["restaurant_id"]
    table_id = _table(rid)

    # Tuesday's lull is emptier than Wednesday's.
    _seed(rid, table_id, tz, _recent_weekdays(tz, 1, 8), _BUSY)
    wednesday = {**_BUSY, 14: "50.00", 15: "50.00", 16: "50.00"}
    _seed(rid, table_id, tz, _recent_weekdays(tz, 2, 8), wednesday,
          start_order_number=20_000)

    body = _fetch(client, tenant)
    labels = [w["weekday_label"] for w in body["windows"]]
    assert labels == ["Tuesday", "Wednesday"], body["windows"]
    assert len(labels) == len(set(labels))
    medians = [Decimal(w["median_revenue"]) for w in body["windows"]]
    assert medians == sorted(medians)
    assert medians[0] == Decimal("0.00")
    assert medians[1] == Decimal("150.00")


# ── Timezone correctness (the nightly-report trap) ────────────────────────────

def test_local_weekday_and_hour_for_non_kathmandu_timezone(client):
    """A UTC-based implementation would file this trade on the wrong day.

    Seeds local Tuesday 09:00-21:00 in America/Los_Angeles with a dead
    14:00-17:00. In UTC those instants straddle Tuesday evening and Wednesday
    morning, and none of them sits at hour 14.
    """
    tenant = _fresh_tenant(tz="America/Los_Angeles")
    tz = ZoneInfo(tenant["tz"])
    table_id = _table(tenant["restaurant_id"])
    la_day = {9: "700.00", 10: "900.00", 11: "1400.00", 12: "1800.00",
              13: "1100.00", 17: "1300.00", 18: "1900.00", 19: "2100.00",
              20: "1500.00", 21: "800.00"}
    instants = _seed(tenant["restaurant_id"], table_id, tz,
                     _recent_weekdays(tz, 1, 8), la_day)

    # The seeded instants really do disagree with UTC — otherwise this test
    # would pass against a broken, UTC-based implementation.
    utc_weekdays = {i.weekday() for i in instants}
    assert utc_weekdays == {1, 2}, utc_weekdays
    assert 14 not in {i.hour for i in instants}

    body = _fetch(client, tenant)
    assert body["timezone"] == "America/Los_Angeles"
    assert len(body["windows"]) == 1
    window = body["windows"][0]
    assert window["weekday_label"] == "Tuesday"
    assert (window["start_hour"], window["end_hour"]) == (14, 17)


# ── Tenancy ───────────────────────────────────────────────────────────────────

def test_suggestions_are_tenant_scoped(client):
    """Each admin sees only their own restaurant's quiet stretch."""
    tenant_a = _fresh_tenant("dha")
    tenant_b = _fresh_tenant("dhb")
    tz = ZoneInfo(tenant_a["tz"])

    table_a = _table(tenant_a["restaurant_id"])
    table_b = _table(tenant_b["restaurant_id"])

    # A is dead 14-17; B is dead 19-22. Neither may leak into the other.
    _seed(tenant_a["restaurant_id"], table_a, tz, _recent_weekdays(tz, 1, 8), _BUSY)
    b_day = {9: "900.00", 10: "1200.00", 11: "1500.00", 12: "1800.00",
             13: "1600.00", 14: "1400.00", 15: "1300.00", 16: "1250.00",
             17: "1700.00", 18: "1900.00", 22: "1000.00"}
    _seed(tenant_b["restaurant_id"], table_b, tz, _recent_weekdays(tz, 1, 8), b_day)

    body_a = _fetch(client, tenant_a)
    body_b = _fetch(client, tenant_b)

    assert (body_a["windows"][0]["start_hour"], body_a["windows"][0]["end_hour"]) == (14, 17)
    assert (body_b["windows"][0]["start_hour"], body_b["windows"][0]["end_hour"]) == (19, 22)
    assert Decimal(body_a["windows"][0]["day_median_revenue"]) == Decimal("10800.00")
    assert Decimal(body_b["windows"][0]["day_median_revenue"]) == Decimal("15550.00")


# ── Authorization ─────────────────────────────────────────────────────────────

def test_suggestions_require_authentication(client):
    resp = client.get("/admin/offers/suggestions")
    assert resp.status_code == 401, resp.text


def test_suggestions_reject_a_tampered_token(client):
    tenant = _fresh_tenant()
    token = login(client, tenant)
    resp = client.get("/admin/offers/suggestions", headers=auth(token + "x"))
    assert resp.status_code == 401, resp.text


def test_suggestions_are_admin_only(client):
    """Revenue figures — floor staff must not read them."""
    tenant = _fresh_tenant()
    for role_name in ("WAITER", "KITCHEN", "COUNTER"):
        staff = _staff_user(tenant, role_name)
        token = login(client, staff)
        resp = client.get("/admin/offers/suggestions", headers=auth(token))
        assert resp.status_code == 403, f"{role_name}: {resp.text}"


# ── Service-level unit checks (no HTTP) ───────────────────────────────────────

def test_weakest_window_refuses_a_span_too_short_to_rank():
    """One candidate position means the answer would be the whole trading day."""
    from app.services.dead_hours_service import _weakest_window

    # Trading 12:00-14:00 → span 3 → exactly one 3-hour window. No insight.
    days = [{12: Decimal("100"), 13: Decimal("100"), 14: Decimal("100")}] * 8
    assert _weakest_window(days) is None

    # Trading 12:00-15:00 → span 4 → two candidates, so a comparison exists.
    days = [{12: Decimal("100"), 13: Decimal("100"),
             14: Decimal("100"), 15: Decimal("100")}] * 8
    assert _weakest_window(days) is not None


def test_weakest_window_breaks_ties_toward_the_earlier_window():
    from app.services.dead_hours_service import _weakest_window

    # A flat day: every window scores identically, so the earliest must win.
    flat = {h: Decimal("100") for h in range(10, 21)}
    start, end, _ = _weakest_window([flat] * 8)
    assert (start, end) == (10, 13)


def test_weakest_window_never_ends_after_the_latest_expressible_hour():
    """Trading late must not produce a window an offer could not store."""
    from app.services.dead_hours_service import _weakest_window

    # Quietest raw stretch is 21:00-24:00, but 24:00 is not a wall-clock end.
    late = {h: Decimal("1000") for h in range(17, 21)}
    late.update({21: Decimal("1"), 22: Decimal("1"), 23: Decimal("1")})
    start, end, _ = _weakest_window([late] * 8)
    assert end <= 23
    assert (start, end) == (20, 23)
