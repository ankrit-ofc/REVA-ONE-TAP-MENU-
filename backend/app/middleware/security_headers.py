from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Applies defense-in-depth HTTP security headers to every response.

    Headers applied to all responses:
      - X-Content-Type-Options: nosniff
      - X-Frame-Options: DENY
      - Referrer-Policy: strict-origin-when-cross-origin
      - Content-Security-Policy: default-src 'none'; frame-ancestors 'none'

    Additional header in production only:
      - Strict-Transport-Security: max-age=63072000; includeSubDomains; preload
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Permitted-Cross-Domain-Policies"] = "none"

        if request.url.path.startswith("/ar-banner/"):
            # AR Quick Look's custom-banner web view embeds this page inside its
            # own native UI — functionally a frame load. The blanket DENY /
            # frame-ancestors 'none' below would make Apple's banner silently
            # fail to render, so this one route gets a narrower, purpose-built
            # policy instead: still no scripts ever (default-src 'none'), just
            # enough to render a static, inline-styled card (style-src/img-src)
            # and be embeddable by anyone (frame-ancestors *) — the content is
            # public, read-only nutrition text, nothing an embedder could trick
            # a user into doing.
            response.headers["Content-Security-Policy"] = (
                "default-src 'none'; style-src 'unsafe-inline'; img-src 'self' data:; frame-ancestors *"
            )
        else:
            response.headers["X-Frame-Options"] = "DENY"
            # Pure JSON API — no scripts, images, or frames served from here.
            response.headers["Content-Security-Policy"] = (
                "default-src 'none'; frame-ancestors 'none'"
            )

        if settings.ENVIRONMENT == "production":
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains; preload"
            )

        return response
