"""
Per-client rate limiting behind a trusted proxy (HANDOVER.md §8 known issue #2).

Proves the limiter key derives from the real client IP:
  - behind a TRUSTED proxy peer, distinct X-Forwarded-For clients get
    independent login rate-limit buckets;
  - a DIRECT (untrusted) connection cannot mint fresh buckets by spoofing
    X-Forwarded-For — the header is ignored and the TCP peer stays the key.

httpx's ASGITransport lets us set the ASGI scope's client address, simulating
the TCP peer uvicorn would report.
"""

import asyncio

import httpx

# Inside TRUSTED_PROXY_IPS (172.16.0.0/12) — simulates Caddy on the Docker net.
TRUSTED_PEER = ("172.31.99.7", 51234)
# Loopback is NOT in the trusted range — simulates a direct connection.
UNTRUSTED_PEER = ("127.0.0.1", 51234)

RATE_LIMIT_LOGIN = 5  # default "5/minute" (app/core/config.py)


def _bad_login_body(seed):
    return {
        "email": seed["a"]["email"],
        "password": "definitely-wrong-password",
        "restaurant_slug": seed["a"]["slug"],
    }


def _post_logins(peer, body, header_sequence):
    """POST /auth/login once per headers dict, from the given TCP peer."""
    from app.main import app

    async def run():
        transport = httpx.ASGITransport(app=app, client=peer)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            return [
                (await client.post("/auth/login", json=body, headers=h)).status_code
                for h in header_sequence
            ]

    return asyncio.run(run())


def test_trusted_proxy_clients_get_independent_buckets(database, seed):
    from app.core.limiter import limiter

    limiter.reset()
    try:
        client_a = {"X-Forwarded-For": "203.0.113.10"}
        client_b = {"X-Forwarded-For": "203.0.113.99"}

        # Client A exhausts its own bucket…
        statuses = _post_logins(
            TRUSTED_PEER, _bad_login_body(seed), [client_a] * (RATE_LIMIT_LOGIN + 1)
        )
        assert statuses[:RATE_LIMIT_LOGIN] == [401] * RATE_LIMIT_LOGIN
        assert statuses[RATE_LIMIT_LOGIN] == 429

        # …while client B, arriving through the same proxy, is untouched.
        (status_b,) = _post_logins(TRUSTED_PEER, _bad_login_body(seed), [client_b])
        assert status_b == 401
    finally:
        limiter.reset()


def test_direct_spoofed_xff_does_not_get_fresh_bucket(database, seed):
    from app.core.limiter import limiter

    limiter.reset()
    try:
        # Direct connection exhausts the bucket keyed on its TCP peer address,
        # even while spoofing X-Forwarded-For…
        spoof_a = {"X-Forwarded-For": "198.51.100.1"}
        statuses = _post_logins(
            UNTRUSTED_PEER, _bad_login_body(seed), [spoof_a] * RATE_LIMIT_LOGIN
        )
        assert statuses == [401] * RATE_LIMIT_LOGIN

        # …so switching the spoofed value must NOT reset the limit.
        spoof_b = {"X-Forwarded-For": "198.51.100.2"}
        (status,) = _post_logins(UNTRUSTED_PEER, _bad_login_body(seed), [spoof_b])
        assert status == 429
    finally:
        limiter.reset()
