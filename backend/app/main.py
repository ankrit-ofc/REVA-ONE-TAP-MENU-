import asyncio
import logging
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.health import router as health_router
from app.api.auth import router as auth_router
from app.api._probe import router as probe_router
from app.api.scan import router as scan_router
from app.api.session import router as session_router
from app.api.admin_menu import router as admin_menu_router, media_router
from app.api.admin_ar import router as admin_ar_router
from app.api.admin_staff import router as admin_staff_router
from app.api.admin_tables import router as admin_tables_router
from app.api.menu import router as menu_router
from app.api.settings import router as settings_router
from app.api.orders import router as orders_router
from app.api.kitchen import router as kitchen_router
from app.api.waiter import router as waiter_router
from app.api.counter import router as counter_router
from app.api.counter_display import router as counter_display_router
from app.api.invoices import router as invoices_router
from app.api.webhooks import router as webhooks_router
from app.api.ws import router as ws_router
from app.api.superadmin import router as superadmin_router
from app.api.printworker import router as printworker_router
from app.api.push import router as push_router

from app.core.config import settings
from app.core.limiter import limiter
from app.core.logging_config import RequestLoggingMiddleware, setup_logging
from app.middleware.security_headers import SecurityHeadersMiddleware

# Configure structured JSON logging before any logger is used.
setup_logging()

_err_logger = logging.getLogger("app.errors")


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.realtime.manager import _set_loop, start_heartbeat, stop_heartbeat
    loop = asyncio.get_running_loop()
    _set_loop(loop)
    # Keep idle WebSockets alive through proxies (Cloudflare ~100s idle timeout)
    # so staff notifications keep flowing during quiet stretches.
    start_heartbeat(loop)
    try:
        yield
    finally:
        await stop_heartbeat()


app = FastAPI(
    title="Restaurant QR Ordering SaaS",
    lifespan=lifespan,
    # Disable the default /docs and /redoc in production to reduce attack surface.
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
)

# ── Rate-limiting state ────────────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── Global unhandled-exception handler ───────────────────────────────────────
# Returns a safe "Internal server error" to the client; logs the full traceback
# server-side only. Never exposes stack traces or internal detail to callers.
@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    _err_logger.error(
        "Unhandled exception on %s %s\n%s",
        request.method,
        request.url.path,
        traceback.format_exc(),
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )

# ── Middleware stack (first added = outermost) ────────────────────────────────
# Order: CORS handles OPTIONS before anything else; then security headers are
# applied to all non-OPTIONS responses; then request logging wraps the inner app.
_allowed_origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Session-Token"],
    expose_headers=["X-Request-ID", "Retry-After"],
    max_age=600,
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestLoggingMiddleware)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(probe_router)
app.include_router(scan_router)
app.include_router(session_router)
app.include_router(admin_menu_router)
app.include_router(admin_ar_router)
app.include_router(admin_staff_router)
app.include_router(admin_tables_router)
app.include_router(media_router)
app.include_router(menu_router)
app.include_router(settings_router)
app.include_router(orders_router)
app.include_router(kitchen_router)
app.include_router(waiter_router)
app.include_router(counter_router)
app.include_router(counter_display_router)
app.include_router(invoices_router)
app.include_router(webhooks_router)
app.include_router(ws_router)
app.include_router(superadmin_router)
app.include_router(printworker_router)
app.include_router(push_router)
