from ipaddress import ip_address, ip_network

from slowapi import Limiter
from starlette.requests import Request

from app.core.config import settings

# Proxy networks whose X-Forwarded-For we accept (comma-separated CIDRs/IPs).
_TRUSTED_NETWORKS = [
    ip_network(part.strip(), strict=False)
    for part in settings.TRUSTED_PROXY_IPS.split(",")
    if part.strip()
]


def _is_trusted_peer(host: str | None) -> bool:
    if not host:
        return False
    try:
        addr = ip_address(host)
    except ValueError:  # e.g. the test client's literal "testclient" host
        return False
    return any(addr in net for net in _TRUSTED_NETWORKS)


def rate_limit_client_ip(request: Request) -> str:
    """
    Rate-limit key: the real client IP.

    Direct connections are keyed on the TCP peer address; X-Forwarded-For from
    an untrusted peer is IGNORED (a spoofer cannot mint fresh buckets). Only
    when the peer is a trusted proxy (Caddy, on the Docker network) is
    X-Forwarded-For consulted — and then the RIGHTMOST entry is used: the
    address the trusted proxy itself observed. A client-sent forgery gets the
    real client appended after it by Caddy, so rightmost stays authentic.

    uvicorn's --proxy-headers/--forwarded-allow-ips performs the same rewrite
    at the server level; once it has resolved request.client to the end-user
    IP, that IP falls outside TRUSTED_PROXY_IPS and is used here as-is.
    """
    peer = request.client.host if request.client else "127.0.0.1"
    if _is_trusted_peer(peer):
        xff = request.headers.get("X-Forwarded-For", "")
        if xff:
            candidate = xff.split(",")[-1].strip()
            try:
                return str(ip_address(candidate))
            except ValueError:
                return peer
    return peer


limiter = Limiter(key_func=rate_limit_client_ip)
