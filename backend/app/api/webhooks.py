"""
Payment gateway callback endpoints (Phase 7).

NO staff/session authentication — these are called by the gateway or the
customer's browser redirecting from the gateway.

Security is enforced by signature verification inside each gateway adapter:
  eSewa   — HMAC-SHA256 over (total_amount, transaction_uuid, product_code)
  Khalti  — server-side lookup POST to Khalti API (no local HMAC)
  Fonepay — HMAC-SHA512 (DV field), constant-time comparison

Endpoint design:
  GET /webhooks/esewa    — eSewa success/failure redirect (browser GET with ?data=)
  GET /webhooks/khalti   — Khalti return URL redirect (browser GET with ?pidx=)
  POST /webhooks/fonepay — Fonepay server-to-server webhook (form-encoded body)

After processing, GET endpoints redirect the browser to the frontend success or
failure page (303 See Other).  The POST endpoint returns a JSON acknowledgement.

All endpoints are strictly idempotent: a replay of the same gateway callback
returns 200 / redirects to success without a second credit (the gateway adapter
and the invoice service both guard this independently).
"""

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_db
from app.payments.esewa import ESewaGateway
from app.payments.fonepay import FonepayGateway
from app.payments.khalti import KhaltiGateway
from app.services import payment_service
from app.services.payment_state import InvoiceError

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

_DbDep = Annotated[Session, Depends(get_db)]

_SUCCESS_URL = f"{settings.FRONTEND_BASE_URL}/payment/success"
_FAILURE_URL = f"{settings.FRONTEND_BASE_URL}/payment/failure"


# ── eSewa — browser redirect with ?data=<base64-json> ─────────────────────────

@router.get("/esewa")
def esewa_callback(
    request: Request,
    db: _DbDep,
) -> RedirectResponse:
    """
    eSewa redirects the user's browser here after payment.
    The `data` query param is Base64-encoded JSON signed with HMAC-SHA256.
    We decode, verify, update the invoice, then redirect the browser to the
    frontend success/failure page.
    """
    data_param = request.query_params.get("data", "")
    if not data_param:
        return RedirectResponse(
            url=f"{_FAILURE_URL}?reason=missing_data",
            status_code=303,
        )

    gateway = ESewaGateway(settings)
    try:
        invoice = payment_service.handle_webhook(
            db, gateway, "ESEWA",
            headers=dict(request.headers),
            raw_body=data_param.encode(),   # adapter decodes the base64 internally
        )
        return RedirectResponse(
            url=f"{_SUCCESS_URL}?invoice_id={invoice.id}",
            status_code=303,
        )
    except InvoiceError as exc:
        return RedirectResponse(
            url=f"{_FAILURE_URL}?reason={exc}",
            status_code=303,
        )


# ── Khalti — browser redirect with ?pidx=…&transaction_id=… ──────────────────

@router.get("/khalti")
def khalti_callback(
    request: Request,
    db: _DbDep,
) -> RedirectResponse:
    """
    Khalti redirects the user's browser here after payment.
    We extract `pidx`, perform a server-side Khalti lookup (no local HMAC),
    and redirect to the frontend.
    """
    pidx = request.query_params.get("pidx", "")
    if not pidx:
        return RedirectResponse(
            url=f"{_FAILURE_URL}?reason=missing_pidx",
            status_code=303,
        )

    gateway = KhaltiGateway(settings)
    raw_body = json.dumps({"pidx": pidx}).encode()
    try:
        invoice = payment_service.handle_webhook(
            db, gateway, "KHALTI",
            headers=dict(request.headers),
            raw_body=raw_body,
        )
        return RedirectResponse(
            url=f"{_SUCCESS_URL}?invoice_id={invoice.id}",
            status_code=303,
        )
    except InvoiceError as exc:
        return RedirectResponse(
            url=f"{_FAILURE_URL}?reason={exc}",
            status_code=303,
        )


# ── Fonepay — server-to-server POST with form-encoded body ────────────────────

@router.post("/fonepay")
async def fonepay_webhook(
    request: Request,
    db: _DbDep,
) -> dict:
    """
    Fonepay sends a server-to-server POST with form-encoded payment data.
    The DV field (HMAC-SHA512) is verified before any state change.
    Returns {"status": "ok"} on success; 400 on any verification failure.
    Strictly idempotent: a replay returns {"status": "ok"} without re-processing.
    """
    raw_body = await request.body()
    gateway = FonepayGateway(settings)
    try:
        invoice = payment_service.handle_webhook(
            db, gateway, "FONEPAY",
            headers=dict(request.headers),
            raw_body=raw_body,
        )
        return {"status": "ok", "invoice_id": str(invoice.id)}
    except InvoiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
