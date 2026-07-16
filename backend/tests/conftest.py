"""
Test fixtures: dedicated test database + seeded two-tenant world.

The suite NEVER touches the dev/prod database. Before any app module is
imported, DATABASE_URL is rewritten to point at "<dbname>_test" on the same
Postgres server; the fixture then drops/recreates that database from scratch
and runs the full Alembic chain against it, exactly like dev/CI.

Required environment (present in the compose backend container and in CI):
  DATABASE_URL       app connection (restricted role) — rewritten to *_test
  POSTGRES_USER      Postgres superuser (creates/drops the test database)
  POSTGRES_PASSWORD  its password
  SECRET_KEY / QR_SECRET
"""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]

# ── Rewrite DATABASE_URL BEFORE any app import (settings reads it at import) ──

_ORIG_URL = os.environ["DATABASE_URL"]
_parts = urlsplit(_ORIG_URL)
_BASE_DB = _parts.path.lstrip("/")
TEST_DB = f"{_BASE_DB}_test"
assert TEST_DB != _BASE_DB and TEST_DB.endswith("_test"), "refusing to run against a non-test database"
TEST_DATABASE_URL = _ORIG_URL.rsplit("/", 1)[0] + "/" + TEST_DB
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

_APP_ROLE = unquote(_parts.username or "")
_HOST_PORT = _parts.netloc.rsplit("@", 1)[-1]
_ADMIN_URL = (
    f"postgresql+psycopg://{quote(os.environ['POSTGRES_USER'], safe='')}:"
    f"{quote(os.environ['POSTGRES_PASSWORD'], safe='')}@{_HOST_PORT}/postgres"
)

TEST_PASSWORD = "CorrectHorse!Battery9"


# ── Database lifecycle (once per test session) ────────────────────────────────

@pytest.fixture(scope="session")
def database():
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text

    admin = create_engine(_ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{TEST_DB}"'))
    admin_test = create_engine(
        _ADMIN_URL.rsplit("/", 1)[0] + f'/{TEST_DB}', isolation_level="AUTOCOMMIT"
    )
    with admin_test.connect() as conn:
        # Mirror db/init/01_roles.sql: the restricted app role owns its tables.
        conn.execute(text(f'GRANT CONNECT ON DATABASE "{TEST_DB}" TO "{_APP_ROLE}"'))
        conn.execute(text(f'GRANT USAGE, CREATE ON SCHEMA public TO "{_APP_ROLE}"'))
    admin_test.dispose()

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(cfg, "head")

    yield

    # Leave the test DB behind for post-mortem; it is dropped on the next run.
    admin.dispose()


# ── Seed: two tenants, one ADMIN each ─────────────────────────────────────────

@pytest.fixture(scope="session")
def seed(database):
    from app.core import security
    from app.db.session import SessionLocal
    from app.models.enums import Role
    from app.models.restaurant import Restaurant, RestaurantSettings
    from app.models.user import User

    db = SessionLocal()
    data = {}
    for key in ("a", "b"):
        r = Restaurant(name=f"Tenant {key.upper()}", slug=f"tenant-{key}", is_active=True)
        db.add(r)
        db.flush()
        db.add(RestaurantSettings(restaurant_id=r.id))
        user = User(
            restaurant_id=r.id,
            email=f"admin.{key}@example.com",
            password_hash=security.hash_password(TEST_PASSWORD),
            role=Role.ADMIN,
        )
        db.add(user)
        db.flush()
        data[key] = {
            "restaurant_id": str(r.id),
            "slug": r.slug,
            "email": user.email,
            "user_id": str(user.id),
        }
    db.commit()
    db.close()
    return data


# ── App client (rate-limit buckets reset per test for isolation) ─────────────

@pytest.fixture()
def client(database):
    from fastapi.testclient import TestClient

    from app.core.limiter import limiter
    from app.main import app

    limiter.reset()
    with TestClient(app) as c:
        yield c
    limiter.reset()


# ── Helpers ───────────────────────────────────────────────────────────────────

def login(client, tenant: dict) -> str:
    """Log a seeded ADMIN in; returns the access token."""
    resp = client.post(
        "/auth/login",
        json={
            "email": tenant["email"],
            "password": TEST_PASSWORD,
            "restaurant_slug": tenant["slug"],
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def make_expired_access_token(tenant: dict) -> str:
    """A structurally valid access token whose exp is in the past."""
    import jwt

    from app.core.config import settings

    now = datetime.now(timezone.utc)
    payload = {
        "sub": tenant["user_id"],
        "restaurant_id": tenant["restaurant_id"],
        "role": "ADMIN",
        "type": "access",
        "iat": now - timedelta(minutes=10),
        "exp": now - timedelta(minutes=5),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
