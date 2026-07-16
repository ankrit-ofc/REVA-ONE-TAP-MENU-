"""
Khalti payment gateway adapter (Smart Payment Gateway / ePay v2).

Verification scheme (confirmed from https://docs.khalti.com/api/verification/):
  Khalti does NOT use local HMAC; verification is always server-side.

  create_intent:
    POST https://a.khalti.com/api/v2/epayment/initiate/
    Headers: Authorization: Key <KHALTI_SECRET_KEY>
    Body: {return_url, website_url, amount (paisa), purchase_order_id, purchase_order_name}
    Returns: {pidx, payment_url}

  verify_webhook (called when browser returns to our return_url):
    POST https://khalti.com/api/v2/epayment/lookup/
    Headers: Authorization: Key <KHALTI_SECRET_KEY>
    Body: {pidx}
    Response status field: "Completed" | "Initiated" | "Refunded" | "Expired" | "User canceled" | "Pending"

Amount in Khalti is always in PAISA (1 NPR = 100 paisa).
We convert: NPR → paisa for intent, paisa → NPR for comparison.

purchase_order_id is set to str(invoice.id) so the lookup response maps back
to our invoice without extra storage.

NOTE: KHALTI_SECRET_KEY must be set in .env and never committed.
"""

import json
from decimal import Decimal
from typing import TYPE_CHECKING

import httpx

from app.payments.base import PaymentGateway, WebhookPayload

if TYPE_CHECKING:
    from app.models.invoice import Invoice

_INITIATE_URL = "https://a.khalti.com/api/v2/epayment/initiate/"
_LOOKUP_URL = "https://khalti.com/api/v2/epayment/lookup/"


class KhaltiGateway(PaymentGateway):

    def __init__(self, settings) -> None:
        self._secret = settings.KHALTI_SECRET_KEY
        self._website_url = settings.KHALTI_WEBSITE_URL
        self._backend_base = settings.BACKEND_BASE_URL

    def _auth_header(self) -> dict:
        return {"Authorization": f"Key {self._secret}"}

    # ── PaymentGateway interface ──────────────────────────────────────────────

    def create_intent(self, invoice: "Invoice") -> dict:
        """
        Creates a Khalti payment intent and returns {pidx, payment_url}.
        Raises ValueError on any gateway or network error.
        Amount is sent in paisa (NPR * 100).
        """
        if not self._secret:
            raise ValueError("Khalti secret key is not configured")

        amount_paisa = int(invoice.total * 100)
        return_url = f"{self._backend_base}/webhooks/khalti"

        try:
            resp = httpx.post(
                _INITIATE_URL,
                headers=self._auth_header(),
                json={
                    "return_url": return_url,
                    "website_url": self._website_url,
                    "amount": amount_paisa,
                    "purchase_order_id": str(invoice.id),
                    "purchase_order_name": f"Invoice {invoice.invoice_number}",
                },
                timeout=10.0,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ValueError(f"Khalti: failed to create payment intent: {exc}") from exc

        data = resp.json()
        if "pidx" not in data or "payment_url" not in data:
            raise ValueError(f"Khalti: unexpected initiate response: {data}")

        return {"pidx": data["pidx"], "payment_url": data["payment_url"]}

    def verify_webhook(self, headers: dict, raw_body: bytes) -> WebhookPayload:
        """
        raw_body is JSON: {"pidx": "<payment index from Khalti redirect>"}.
        Performs server-side lookup at Khalti and returns a normalised payload.
        Raises ValueError on any failure (network, bad sig, bad status).
        """
        if not self._secret:
            raise ValueError("Khalti secret key is not configured")

        try:
            body = json.loads(raw_body)
            pidx = body["pidx"]
        except Exception as exc:
            raise ValueError(f"Khalti: cannot parse webhook body: {exc}") from exc

        try:
            resp = httpx.post(
                _LOOKUP_URL,
                headers=self._auth_header(),
                json={"pidx": pidx},
                timeout=10.0,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ValueError(f"Khalti: lookup call failed: {exc}") from exc

        data = resp.json()
        khalti_status = data.get("status", "")
        status = "PAID" if khalti_status == "Completed" else "FAILED"

        try:
            # Khalti returns total_amount in paisa; convert to NPR
            amount_npr = Decimal(str(data["total_amount"])) / Decimal("100")
        except Exception as exc:
            raise ValueError(f"Khalti: invalid amount in lookup response: {exc}") from exc

        # purchase_order_id was set to str(invoice.id) when the intent was created
        invoice_ref = data.get("purchase_order_id", "")
        if not invoice_ref:
            raise ValueError("Khalti: lookup response missing purchase_order_id")

        transaction_id = data.get("transaction_id") or pidx

        return WebhookPayload(
            transaction_id=transaction_id,
            status=status,
            amount=amount_npr,
            invoice_ref=invoice_ref,
        )
