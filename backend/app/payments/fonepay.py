"""
Fonepay QR payment adapter (NepalPay interoperable QR).

Signing scheme (HMAC-SHA512, uppercase hex):
  message = f"{PID}|{PRN}|{R_AMT}"
  key     = FONEPAY_SECRET_KEY
  DV      = HMAC-SHA512(key, message).hexdigest().upper()

  !! IMPORTANT: Confirm the exact field concatenation order against Fonepay's
  official merchant integration guide before deploying to production.
  The order used here (PID|PRN|R_AMT) matches the most widely-referenced
  community implementations as of 2025, but Fonepay's docs are the authority.

Callback flow:
  Fonepay POSTs form data to our webhook URL (server-to-server):
    PRN  — our invoice ID (set as the payment reference number)
    PID  — Fonepay merchant code
    PS   — payment status ("true" = success)
    RC   — response code
    UID  — unique transaction ID from Fonepay
    BC   — bank code
    INI  — initiator type
    P_AMT — requested amount
    R_AMT — received/actual amount (this is what we verify against invoice.total)
    DV   — HMAC-SHA512 signature

raw_body is form-encoded (application/x-www-form-urlencoded).
We parse it, verify DV, then return a normalised WebhookPayload.

PRN is set to str(invoice.id) when the QR params are generated.
"""

import hashlib
import hmac
from decimal import Decimal
from typing import TYPE_CHECKING
from urllib.parse import parse_qs

from app.payments.base import PaymentGateway, WebhookPayload

if TYPE_CHECKING:
    from app.models.invoice import Invoice


class FonepayGateway(PaymentGateway):

    def __init__(self, settings) -> None:
        self._merchant_code = settings.FONEPAY_MERCHANT_CODE   # PID
        self._secret = settings.FONEPAY_SECRET_KEY

    # ── Signature helper ──────────────────────────────────────────────────────

    def _sign(self, prn: str, r_amt: str) -> str:
        """Return uppercase hex HMAC-SHA512 DV."""
        message = f"{self._merchant_code}|{prn}|{r_amt}"
        return hmac.new(
            self._secret.encode(),
            message.encode(),
            hashlib.sha512,
        ).hexdigest().upper()

    # ── PaymentGateway interface ──────────────────────────────────────────────

    def create_intent(self, invoice: "Invoice") -> dict:
        """
        Returns Fonepay QR payment parameters.
        The frontend uses these to generate / display the NepalPay QR code.
        PRN (payment reference number) = str(invoice.id).
        """
        if not self._merchant_code or not self._secret:
            raise ValueError("Fonepay merchant code / secret key is not configured")

        prn = str(invoice.id)
        p_amt = str(invoice.total)
        return {
            "PID": self._merchant_code,
            "PRN": prn,
            "P_AMT": p_amt,
        }

    def verify_webhook(self, headers: dict, raw_body: bytes) -> WebhookPayload:
        """
        raw_body is form-encoded Fonepay webhook data.
        Parses the fields, verifies DV (HMAC-SHA512 uppercase hex), and returns
        a normalised WebhookPayload.  Raises ValueError on verification failure.
        """
        if not self._secret:
            raise ValueError("Fonepay secret key is not configured")

        try:
            params = parse_qs(raw_body.decode())
            # parse_qs returns lists; take the first value of each key
            flat = {k: v[0] for k, v in params.items()}
        except Exception as exc:
            raise ValueError(f"Fonepay: cannot parse webhook body: {exc}") from exc

        required = {"PRN", "PID", "PS", "RC", "UID", "R_AMT", "DV"}
        missing = required - set(flat.keys())
        if missing:
            raise ValueError(f"Fonepay: missing fields in webhook: {missing}")

        prn = flat["PRN"]
        r_amt = flat["R_AMT"]
        received_dv = flat["DV"].upper()

        expected_dv = self._sign(prn, r_amt)
        if not hmac.compare_digest(expected_dv, received_dv):
            raise ValueError("Fonepay: DV signature verification failed")

        ps = flat["PS"].lower()
        status = "PAID" if ps == "true" else "FAILED"

        try:
            amount = Decimal(r_amt)
        except Exception as exc:
            raise ValueError(f"Fonepay: invalid R_AMT value: {exc}") from exc

        return WebhookPayload(
            transaction_id=flat["UID"],
            status=status,
            amount=amount,
            invoice_ref=prn,
        )
