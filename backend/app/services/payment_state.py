"""
Invoice state machine.

Transitions:
  DRAFT            -> PENDING_PAYMENT  (gateway intent initiated)
  DRAFT            -> PAID             (counter cash/card — no pending phase)
  DRAFT            -> VOID             (staff voids before any payment attempt)
  PENDING_PAYMENT  -> PAID             (gateway confirmed / counter fallback)
  PENDING_PAYMENT  -> FAILED           (gateway reported failure)
  PENDING_PAYMENT  -> VOID             (staff voids a stuck pending invoice)
  PAID             -> REFUNDED         (future refund — guard only; endpoint optional)

Terminal states: FAILED, VOID, REFUNDED cannot transition further.
A FAILED or VOID invoice does NOT block generating a new invoice on the same order.
"""

from app.models.enums import InvoiceStatus


class InvoiceError(Exception):
    """Domain error for the invoice/payment service. Carries an HTTP status hint."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


_INVOICE_ALLOWED: dict[InvoiceStatus, set[InvoiceStatus]] = {
    InvoiceStatus.DRAFT: {
        InvoiceStatus.PENDING_PAYMENT,
        InvoiceStatus.PAID,    # counter cash — skip PENDING_PAYMENT
        InvoiceStatus.VOID,
    },
    InvoiceStatus.PENDING_PAYMENT: {
        InvoiceStatus.PAID,
        InvoiceStatus.FAILED,
        InvoiceStatus.VOID,
    },
    InvoiceStatus.PAID: {InvoiceStatus.REFUNDED},
    InvoiceStatus.FAILED: set(),
    InvoiceStatus.VOID: set(),
    InvoiceStatus.REFUNDED: set(),
}


def assert_valid_invoice_transition(
    current: InvoiceStatus,
    target: InvoiceStatus,
) -> None:
    """Raises InvoiceError (409) if the transition is not permitted."""
    allowed = _INVOICE_ALLOWED.get(current, set())
    if target not in allowed:
        raise InvoiceError(
            f"Cannot transition invoice from {current.value} to {target.value}",
            status_code=409,
        )
