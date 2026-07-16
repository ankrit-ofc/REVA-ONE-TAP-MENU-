"""
Fail-fast production config validation (HANDOVER.md §8 issue #4).

Settings() runs the guard at construction — the same instantiation that
happens at app import — so an unsafe production configuration prevents boot.
Tests construct Settings directly with _env_file=None and explicit kwargs
(init kwargs take precedence over the container's real env vars).
"""

import pytest
from pydantic import ValidationError

from app.core.config import Settings

BASE = {
    "DATABASE_URL": "postgresql+psycopg://u:p@localhost:5432/db",
    "SECRET_KEY": "unit-test-secret-key-long-enough-000000",
    "QR_SECRET": "unit-test-qr-secret-long-enough-0000000",
}
PROD_ORIGINS = {"ALLOWED_ORIGINS": "https://order.example.com"}
# All gateway fields pinned empty — tests override individual fields on top of
# this so the ambient container/CI environment can never leak in.
NO_GATEWAYS = {
    "ESEWA_SECRET_KEY": "",
    "ESEWA_PRODUCT_CODE": "",
    "KHALTI_SECRET_KEY": "",
    "FONEPAY_MERCHANT_CODE": "",
    "FONEPAY_SECRET_KEY": "",
}


def test_development_boots_with_no_gateways_and_empty_defaults():
    s = Settings(_env_file=None, **BASE, **NO_GATEWAYS)
    assert s.ENVIRONMENT == "development"
    # The dangerous CODE defaults are gone: gateways are OFF unless env-set.
    assert Settings.model_fields["ESEWA_SECRET_KEY"].default == ""
    assert Settings.model_fields["ESEWA_PRODUCT_CODE"].default == ""


def test_development_allows_localhost_origins_and_partial_gateways():
    s = Settings(_env_file=None, ESEWA_PRODUCT_CODE="EPAYTEST", **BASE)
    assert "localhost" in s.ALLOWED_ORIGINS  # dev default, unchanged


def test_production_missing_esewa_key_refuses_to_boot():
    with pytest.raises(ValidationError) as excinfo:
        Settings(
            _env_file=None,
            ENVIRONMENT="production",
            **{**NO_GATEWAYS, "ESEWA_PRODUCT_CODE": "MY_REAL_MERCHANT_CODE"},  # key forgotten
            **BASE,
            **PROD_ORIGINS,
        )
    message = str(excinfo.value)
    assert "eSewa" in message and "ESEWA_SECRET_KEY" in message


def test_production_sandbox_esewa_credentials_refused():
    with pytest.raises(ValidationError) as excinfo:
        Settings(
            _env_file=None,
            ENVIRONMENT="production",
            **{
                **NO_GATEWAYS,
                "ESEWA_SECRET_KEY": "8gBm/:&EnhH.1/q(",
                "ESEWA_PRODUCT_CODE": "EPAYTEST",
            },
            **BASE,
            **PROD_ORIGINS,
        )
    assert "SANDBOX" in str(excinfo.value)


def test_production_partial_fonepay_refused():
    with pytest.raises(ValidationError) as excinfo:
        Settings(
            _env_file=None,
            ENVIRONMENT="production",
            **{**NO_GATEWAYS, "FONEPAY_MERCHANT_CODE": "PID123"},  # secret forgotten
            **BASE,
            **PROD_ORIGINS,
        )
    message = str(excinfo.value)
    assert "Fonepay" in message and "FONEPAY_SECRET_KEY" in message


def test_production_localhost_origins_refused():
    with pytest.raises(ValidationError) as excinfo:
        Settings(
            _env_file=None,
            ENVIRONMENT="production",
            ALLOWED_ORIGINS="https://order.example.com,http://localhost:3000",
            **BASE,
            **NO_GATEWAYS,
        )
    assert "localhost" in str(excinfo.value)


def test_production_missing_core_secrets_refused():
    with pytest.raises(ValidationError) as excinfo:
        Settings(
            _env_file=None,
            ENVIRONMENT="production",
            DATABASE_URL=BASE["DATABASE_URL"],
            SECRET_KEY="   ",
            QR_SECRET="",
            **PROD_ORIGINS,
            **NO_GATEWAYS,
        )
    message = str(excinfo.value)
    assert "SECRET_KEY" in message and "QR_SECRET" in message


def test_production_valid_config_boots():
    s = Settings(
        _env_file=None,
        ENVIRONMENT="production",
        ESEWA_SECRET_KEY="real-merchant-secret",
        ESEWA_PRODUCT_CODE="REALCODE",
        KHALTI_SECRET_KEY="live_secret_key",
        FONEPAY_MERCHANT_CODE="PID123",
        FONEPAY_SECRET_KEY="fonepay-hmac-secret",
        **BASE,
        **PROD_ORIGINS,
    )
    assert s.ENVIRONMENT == "production"


def test_production_no_gateways_at_all_is_allowed():
    # CASH/CARD/manual-only operation is supported until merchant accounts exist.
    s = Settings(
        _env_file=None, ENVIRONMENT="production", **BASE, **PROD_ORIGINS, **NO_GATEWAYS
    )
    assert s.ESEWA_SECRET_KEY == ""
