"""
Pure order and order-item state machine logic.

No DB access, no HTTP concerns.  Raises OrderError on illegal transitions.
Phase 6 staff endpoints call transition_order / transition_item in order_service,
which delegate validation here.
"""

from app.models.enums import OrderItemStatus, OrderStatus


class OrderError(Exception):
    """Domain error for the ordering service.  Carries an HTTP status code hint."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


# ── Order state machine ───────────────────────────────────────────────────────
# OPEN -> MEAL_FINISHED -> CLOSED
# MEAL_FINISHED -> OPEN  (reopen, requires permission + reason)

_ORDER_ALLOWED: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.OPEN: {OrderStatus.MEAL_FINISHED},
    OrderStatus.MEAL_FINISHED: {OrderStatus.CLOSED, OrderStatus.OPEN},
    OrderStatus.CLOSED: set(),
}


def assert_valid_order_transition(
    current: OrderStatus,
    target: OrderStatus,
    allow_reopen: bool = False,
    reason: str | None = None,
) -> None:
    """
    Raises OrderError if (current -> target) is not a permitted transition.

    Reopen (MEAL_FINISHED -> OPEN) additionally requires allow_reopen=True and
    a non-empty reason string; this guards against customers reopening their own
    order (Phase 6 passes the flag only for authorised staff roles).
    """
    allowed = _ORDER_ALLOWED.get(current, set())
    if target not in allowed:
        raise OrderError(
            f"Cannot transition order from {current.value} to {target.value}",
            status_code=409,
        )
    if target == OrderStatus.OPEN:
        if not allow_reopen:
            raise OrderError(
                "Reopening an order requires explicit staff permission",
                status_code=403,
            )
        if not reason or not reason.strip():
            raise OrderError(
                "A reason is required when reopening an order",
                status_code=422,
            )


# ── Order-item state machine ──────────────────────────────────────────────────
# PENDING_APPROVAL -> NEW        (waiter approves the batch)
# PENDING_APPROVAL -> CANCELLED  (waiter rejects the batch)
# NEW -> PREPARING -> READY -> SERVED
# NEW -> CANCELLED  (only while NEW — cannot cancel mid-prep)
# NEW / PREPARING -> SERVED      (waiter serves directly — kitchens that work
#                                 off the printed KOT never touch the queue
#                                 screen, so READY is optional, not required)

_ITEM_ALLOWED: dict[OrderItemStatus, set[OrderItemStatus]] = {
    OrderItemStatus.PENDING_APPROVAL: {OrderItemStatus.NEW, OrderItemStatus.CANCELLED},
    OrderItemStatus.NEW: {
        OrderItemStatus.PREPARING,
        OrderItemStatus.SERVED,
        OrderItemStatus.CANCELLED,
    },
    OrderItemStatus.PREPARING: {OrderItemStatus.READY, OrderItemStatus.SERVED},
    OrderItemStatus.READY: {OrderItemStatus.SERVED},
    OrderItemStatus.SERVED: set(),
    OrderItemStatus.CANCELLED: set(),
}


def assert_valid_item_transition(
    current: OrderItemStatus,
    target: OrderItemStatus,
) -> None:
    """Raises OrderError if (current -> target) is not a permitted item transition."""
    allowed = _ITEM_ALLOWED.get(current, set())
    if target not in allowed:
        raise OrderError(
            f"Cannot transition item from {current.value} to {target.value}",
            status_code=409,
        )
