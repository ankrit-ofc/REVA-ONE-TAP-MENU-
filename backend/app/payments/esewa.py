"""
eSewa ePay v2 adapter.

Signing scheme (confirmed from https://developer.esewa.com.np/pages/Epay):
  message  = "total_amount=<NPR>,transaction_uuid=<invoice_id>,product_code=<code>"
  key      = merchant secret key (env: ESEWA_SECRET_KEY)
  digest   = HMAC-SHA256(key, message)
  signature = base64.b64encode(digest)

Callback flow:
  eSewa redirects the user's browser to our success URL:
    GET /webhooks/esewa?data=<base64-encoded-json>
  The JSON payload contains transaction_code, status, total_amount,
  transaction_uuid, product_code, and signature.
  We decode, recompute the HMAC over the same three fields, and compare
  using hmac.compare_digest (constant-time) to prevent timing attacks.

transaction_uuid is set to str(invoice.id) when the intent is created, so
the callback payload maps directly back to the invoice.
"""

import base64
import hashlib
import hmac
import json
from decimal import Decimal
from typing import TYPE_CHECKING

from app.payments.base import PaymentGateway, WebhookPayload

if TYPE_CHECKING:
    from app.models.invoice import Invoice


class ESewaGateway(PaymentGateway):

    def __init__(self, settings) -> None:
        self._secret = settings.ESEWA_SECRET_KEY
        self._product_code = settings.ESEWA_PRODUCT_CODE
        self._backend_base = settings.BACKEND_BASE_URL

    # ── Signature helper ──────────────────────────────────────────────────────

    def _sign(self, total_amount: str, transaction_uuid: str) -> str:
        """Return Base64-encoded HMAC-SHA256 signature (eSewa canonical format)."""
        message = (
            f"total_amount={total_amount},"
            f"transaction_uuid={transaction_uuid},"
            f"product_code={self._product_code}"
        )
        digest = hmac.new(
            self._secret.encode(),
            message.encode(),
            hashlib.sha256,
        ).digest()
        return base64.b64encode(digest).decode()

    # ── PaymentGateway interface ──────────────────────────────────────────────

    def create_intent(self, invoice: "Invoice") -> dict:
        """
        Returns signed form parameters for eSewa ePay v2.
        The frontend builds a hidden <form> and POSTs it to eSewa's payment URL.
        The success_url is our backend webhook so the redirect hits us directly.
        """
        transaction_uuid = str(invoice.id)
        total_amount = str(invoice.total)
        return {
            "amount": str(invoice.subtotal - invoice.discount),
            "tax_amount": str(invoice.tax_total),
            "total_amount": total_amount,
            "transaction_uuid": transaction_uuid,
            "product_code": self._product_code,
            "product_service_charge": "0",
            "product_delivery_charge": "0",
            "success_url": f"{self._backend_base}/webhooks/esewa",
            "failure_url": f"{self._backend_base}/webhooks/esewa",
            "signed_field_names": "total_amount,transaction_uuid,product_code",
            "signature": self._sign(total_amount, transaction_uuid),
            # Payment URL — frontend POSTs this form to:
            "payment_url": "https://rc-epay.esewa.com.np/api/epay/main/v2/form",
        }

    def verify_webhook(self, headers: dict, raw_body: bytes) -> WebhookPayload:
        """
        raw_body is the Base64-encoded `data` query param bytes from eSewa's redirect.
        Decodes → JSON → verifies HMAC-SHA256 → returns WebhookPayload.
        Raises ValueError on any verification failure.
        """
        try:
            decoded = base64.b64decode(raw_body).decode()
            payload = json.loads(decoded)
        except Exception as exc:
            raise ValueError(f"eSewa: cannot decode callback data: {exc}") from exc

        required = {"transaction_code", "status", "total_amount", "transaction_uuid",
                    "product_code", "signature"}
        missing = required - set(payload.keys())
        if missing:
            raise ValueError(f"eSewa: missing fields in callback: {missing}")

        # Recompute signature and compare (constant-time)
        expected_sig = self._sign(payload["total_amount"], payload["transaction_uuid"])
        received_sig = payload["signature"]
        if not hmac.compare_digest(expected_sig.encode(), received_sig.encode()):
            raise ValueError("eSewa: signature verification failed")

        esewa_status = payload["status"].upper()
        status = "PAID" if esewa_status == "COMPLETE" else "FAILED"

        try:
            amount = Decimal(str(payload["total_amount"]))
        except Exception as exc:
            raise ValueError(f"eSewa: invalid amount in payload: {exc}") from exc

        return WebhookPayload(
            transaction_id=payload["transaction_code"],
            status=status,
            amount=amount,
            invoice_ref=payload["transaction_uuid"],
        )
