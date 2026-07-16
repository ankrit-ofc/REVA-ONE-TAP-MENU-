"""
Abstract payment gateway interface.

Each adapter (esewa, khalti, fonepay) implements this.
verify_webhook receives the EXACT raw bytes from the incoming request so that
HMAC / signature checks operate on the unmodified payload.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.invoice import Invoice


@dataclass
class WebhookPayload:
    """Normalised result returned by every gateway's verify_webhook."""

    transaction_id: str   # gateway's own reference (stored as gateway_transaction_id)
    status: str           # "PAID" | "FAILED"
    amount: Decimal       # in NPR — compared server-side with invoice.total
    invoice_ref: str      # our invoice UUID (str) — set as reference when creating intent


class PaymentGateway(ABC):

    @abstractmethod
    def create_intent(self, invoice: "Invoice") -> dict:
        """
        Initiate a payment at the gateway.

        Returns a dict of gateway-specific parameters the frontend needs to
        proceed (e.g., signed form fields for eSewa, payment_url for Khalti,
        QR params for Fonepay).

        Must NOT change any DB state — that is the caller's responsibility.
        """

    @abstractmethod
    def verify_webhook(self, headers: dict, raw_body: bytes) -> WebhookPayload:
        """
        Verify the incoming gateway callback and return a normalised payload.

        Raises ValueError with a descriptive message on any verification failure
        (bad/missing signature, invalid payload, network error for server-side
        lookup gateways). The caller maps ValueError → HTTP 400 and must NOT
        update any invoice state on failure.

        raw_body is the unmodified request body bytes — essential for HMAC
        verification. Never pass a decoded/re-encoded body to this method.
        """
