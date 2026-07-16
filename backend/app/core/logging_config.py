"""
Structured JSON logging with request tracing and sensitive-data redaction.

Rules:
- Every log line is a JSON object with: ts, level, logger, msg.
- Request logs additionally carry: request_id, method, path, status, latency_ms, actor_id.
- Authorization headers, tokens, passwords, and cookies are NEVER logged.
- actor_id is the JWT sub (a UUID), extracted without logging the raw token.
"""
import json
import logging
import re
import time
import uuid
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Regex matches JSON-style sensitive key/value pairs in log messages.
# e.g.  "password": "secret123"   or   password=secret123
_REDACT_RE = re.compile(
    r'(?i)("?(?:password|token|secret|authorization|refresh_token|access_token|'
    r'cookie|set-cookie)"?\s*[=:]\s*["\']?)([^\s"\'&,}]+)',
)


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data: dict = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        for key in ("request_id", "method", "path", "status", "latency_ms", "actor_id"):
            if hasattr(record, key):
                data[key] = getattr(record, key)
        return json.dumps(data, default=str)


class _RedactionFilter(logging.Filter):
    """
    Last-resort safety net: redacts sensitive key=value / key: value patterns
    from any log record before it is emitted.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        redacted = _REDACT_RE.sub(lambda m: m.group(0)[: len(m.group(1))] + "[REDACTED]", msg)
        if redacted != msg:
            record.msg = redacted
            record.args = ()
        return True


def setup_logging() -> None:
    """
    Installs the JSON formatter and redaction filter on the root logger.
    Call this once at application startup (before first request).
    """
    handler = logging.StreamHandler()
    handler.setFormatter(_JsonFormatter())
    handler.addFilter(_RedactionFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    # Suppress uvicorn's plain-text access log; we emit our own structured line.
    logging.getLogger("uvicorn.access").propagate = False
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


_req_logger = logging.getLogger("app.request")
_err_logger = logging.getLogger("app.errors")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Emits one structured log line per request:
      {request_id, method, path, status, latency_ms, actor_id}

    actor_id is the UUID from the JWT sub claim, extracted WITHOUT logging
    the raw token. If the token is absent or invalid, actor_id is null.

    Authorization headers and cookie values are never logged.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        t0 = time.monotonic()
        response = await call_next(request)
        latency_ms = int((time.monotonic() - t0) * 1000)

        actor_id: str | None = _extract_actor_id(request)

        _req_logger.info(
            "%s %s %s",
            request.method,
            request.url.path,
            response.status_code,
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "latency_ms": latency_ms,
                "actor_id": actor_id,
            },
        )

        response.headers["X-Request-ID"] = request_id
        return response


def _extract_actor_id(request: Request) -> str | None:
    """
    Parses the JWT in the Authorization header to extract the sub (actor UUID).
    The raw token string is never stored or logged — only the sub claim.
    Returns None if the header is absent, malformed, or the token is invalid.
    """
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return None
    raw_token = auth[7:]
    if not raw_token:
        return None
    try:
        import jwt as _jwt
        from app.core.config import settings

        payload = _jwt.decode(
            raw_token,
            settings.SECRET_KEY,
            algorithms=["HS256"],
            # Allow expired tokens here — we only want the actor_id for logging,
            # not for authorization. Auth is enforced separately in deps.py.
            options={"verify_exp": False},
        )
        return payload.get("sub")
    except Exception:
        return None
