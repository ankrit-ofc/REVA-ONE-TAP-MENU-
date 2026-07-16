"""
Typed WebSocket event payloads (Phase 8).

Each dataclass is serialised with dataclasses.asdict() + json.dumps() before
being sent over the wire.  The `type` field is a non-init constant so that
client code can switch on it without extra metadata.

Events emitted post-commit only — clients never observe uncommitted state.
"""

from dataclasses import dataclass, field


@dataclass
class OrderCreatedEvent:
    """Emitted when place_or_append creates a new order OR appends items.

    `items` carries a compact snapshot of the items added in THIS call so the
    counter can print a kitchen ticket (KOT) straight from the event without a
    follow-up fetch. Each entry:
        {product_name, variant_name, quantity, special_instructions,
         addons: [name], line_total: "0.00"}
    Money fields are Decimal serialised as strings (JSON can't carry Decimal;
    never float for money). subtotal/tax_total/total cover the items in THIS call.
    """
    order_id: str
    order_number: int
    table_id: str
    restaurant_id: str
    item_count: int          # number of items added in this call
    table_name: str = ""
    items: list[dict] = field(default_factory=list)
    currency: str = "Rs"
    subtotal: str = "0.00"
    tax_total: str = "0.00"
    total: str = "0.00"
    type: str = field(default="order.created", init=False)


@dataclass
class KotPrintEvent:
    """
    Emitted when a staff member (waiter/counter/admin) manually requests a kitchen
    ticket for an existing order. Relayed to the print station (COUNTER/ADMIN), whose
    PrintController prints it on the paired kitchen printer — so a roaming waiter with
    no local printer can still print to the restaurant's printer.

    Same KOT payload as OrderCreatedEvent (items snapshot + money as strings). `job_id`
    is a fresh id per request so the station de-dups a re-delivered frame but still
    prints once per click. Distinct `type` so it never re-triggers the new-order chime.
    """
    order_id: str
    order_number: int
    table_name: str
    restaurant_id: str
    job_id: str
    items: list[dict] = field(default_factory=list)
    currency: str = "Rs"
    subtotal: str = "0.00"
    tax_total: str = "0.00"
    total: str = "0.00"
    type: str = field(default="kot.print", init=False)


@dataclass
class OrderItemStatusChangedEvent:
    """Emitted after every successful transition_item commit."""
    order_item_id: str
    order_id: str
    table_id: str
    restaurant_id: str
    product_name: str
    previous_status: str
    new_status: str
    type: str = field(default="order_item.status_changed", init=False)


@dataclass
class OrderStatusChangedEvent:
    """Emitted after every successful transition_order commit."""
    order_id: str
    order_number: int
    table_id: str
    restaurant_id: str
    previous_status: str
    new_status: str
    type: str = field(default="order.status_changed", init=False)


@dataclass
class InvoicePaidEvent:
    """Emitted after counter payment, gateway webhook (PAID), or manual override."""
    invoice_id: str
    invoice_number: str
    order_id: str
    restaurant_id: str
    total: str              # Decimal serialised as string
    payment_method: str
    type: str = field(default="invoice.paid", init=False)


@dataclass
class OrderClosedEvent:
    """Emitted alongside InvoicePaidEvent when _close_order_and_reset_table runs."""
    order_id: str
    order_number: int
    table_id: str
    restaurant_id: str
    type: str = field(default="order.closed", init=False)


@dataclass
class BillRequestedEvent:
    """
    Emitted when a customer taps 'Request Bill'. Notify-only: it carries no state
    change — staff (waiter/counter) use it to highlight a table that wants its bill.
    """
    order_id: str
    order_number: int
    table_id: str
    table_name: str
    restaurant_id: str
    type: str = field(default="bill.requested", init=False)


@dataclass
class OrderApprovalRequestedEvent:
    """
    Emitted when require_order_approval gates a batch of customer-ordered items.
    Sent to WAITER/ADMIN (approve/reject queue) and the customer's table channel
    (status page shows 'waiting for confirmation'). Kitchen/counter hear nothing
    until the batch is approved.
    """
    order_id: str
    order_number: int
    table_id: str
    table_name: str
    restaurant_id: str
    item_count: int          # items awaiting approval in this batch
    type: str = field(default="order.approval_requested", init=False)


@dataclass
class OrderApprovalDecidedEvent:
    """
    Emitted after a waiter approves or rejects a pending batch. Sent to
    WAITER/ADMIN (clear the approval queue) and the customer's table channel.
    On approval the kitchen/counter side is driven by the accompanying
    OrderCreatedEvent, not this one.
    """
    order_id: str
    order_number: int
    table_id: str
    table_name: str
    restaurant_id: str
    decision: str            # "APPROVED" | "REJECTED"
    item_count: int
    type: str = field(default="order.approval_decided", init=False)


@dataclass
class WaiterCalledEvent:
    """
    Emitted when a customer taps 'Call Waiter'. Rings the waiters' dashboard so
    someone attends the table. The call is persisted (waiter_calls); call_id lets
    the dashboard reconcile with the pending-calls list it fetches.
    """
    table_id: str
    table_name: str
    restaurant_id: str
    call_id: str
    type: str = field(default="waiter.called", init=False)


@dataclass
class WaiterCallAttendedEvent:
    """
    Emitted when a waiter confirms they attended a call. Clears the call from every
    staff dashboard and records who attended (display only; the audit row is authoritative).
    """
    call_id: str
    table_id: str
    table_name: str
    restaurant_id: str
    attended_by: str
    type: str = field(default="waiter.call_attended", init=False)
