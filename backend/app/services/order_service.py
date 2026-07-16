"""
Core ordering business logic.

place_or_append  — customer places or appends items to the active table order.
get_current_order — returns the OPEN order for the caller's table session.
transition_order  — Phase 6 staff endpoints call this to drive order status.
transition_item   — Phase 6 staff endpoints call this to drive item status.

Security invariants enforced here (never in the router):
- restaurant_id is always derived from the validated session/JWT, never the client.
- Product name/price/tax are looked up and SNAPSHOTTED from the DB; no client value
  for price, name, or tax is accepted.
- A product must be tenant-owned, active, AND available before it can be ordered.
- A variant must belong to the product and be tenant-owned.
- Each addon must be mapped to the product in the same tenant.
- Appending items is only allowed when the order is OPEN.
- All state transitions are validated by order_state before being applied.
- Every append and every transition writes an audit_logs row.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.audit_log import AuditLog
from app.models.enums import OrderItemStatus, OrderStatus, Role
from app.models.order import Order, OrderItem, OrderItemAddon
from app.models.product import Product, ProductAddonMapping, ProductVariant
from app.models.restaurant import RestaurantSettings
from app.models.table import Table, TableSession
from app.realtime.events import (
    BillRequestedEvent,
    KotPrintEvent,
    OrderApprovalDecidedEvent,
    OrderApprovalRequestedEvent,
    OrderCreatedEvent,
    OrderItemStatusChangedEvent,
    OrderStatusChangedEvent,
)
from app.realtime.manager import _fire, manager as rt_manager
from app.services import kot_print_service, numbering_service, push_service
from app.services.order_state import (
    OrderError,
    assert_valid_item_transition,
    assert_valid_order_transition,
)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _load_order_with_items(db: Session, order_id: uuid.UUID) -> Order:
    return db.execute(
        select(Order)
        .where(Order.id == order_id)
        .options(selectinload(Order.items).selectinload(OrderItem.addons))
    ).scalar_one()


# ── Customer-facing operations ────────────────────────────────────────────────

def place_or_append(
    db: Session,
    session: TableSession,
    request,  # PlaceOrderRequest — typed as Any to avoid circular import at module load
) -> Order:
    """
    Places a new order or appends items to the existing OPEN order for the table.

    Flow:
    1. Lock the table row (FOR UPDATE) — serialises concurrent appends so only
       one transaction can inspect/create the active order at a time.
    2. Find any non-CLOSED order for the table:
       - OPEN          → append items to it.
       - MEAL_FINISHED → reject; customer cannot bypass checkout state.
       - None          → create a new OPEN order with a gapless order_number.
    3. Validate and snapshot every item (tenant check, availability, variant FK,
       addon mapping).  Prices and names come exclusively from the DB.
    4. Write an audit_logs row.  Commit.
    """
    restaurant_id: uuid.UUID = session.restaurant_id
    table_id: uuid.UUID = session.table_id

    # 1. Lock the table row — prevents concurrent "create first order" race.
    table = db.execute(
        select(Table)
        .where(Table.id == table_id, Table.restaurant_id == restaurant_id)
        .with_for_update()
    ).scalar_one_or_none()
    if table is None or not table.is_active:
        raise OrderError("Table not found or inactive", status_code=404)

    # 2. Find any non-CLOSED order for this table.
    existing = db.execute(
        select(Order).where(
            Order.table_id == table_id,
            Order.restaurant_id == restaurant_id,
            Order.status != OrderStatus.CLOSED,
        )
    ).scalar_one_or_none()

    order_created = False
    if existing is None:
        order_number = numbering_service.next_number(db, restaurant_id, "order")
        order = Order(
            id=uuid.uuid4(),
            restaurant_id=restaurant_id,
            table_id=table_id,
            order_number=order_number,
            status=OrderStatus.OPEN,
        )
        db.add(order)
        db.flush()
        order_created = True
    elif existing.status != OrderStatus.OPEN:
        raise OrderError(
            f"Order #{existing.order_number} is {existing.status.value} — "
            "cannot add items until staff reopens it",
            status_code=409,
        )
    else:
        order = existing

    prev_item_count = 0 if order_created else len(order.items)

    # Settings drive both the approval gate (item status below) and, later, the
    # KOT pipeline and currency — fetch once, before the item loop.
    _settings = db.execute(
        select(RestaurantSettings).where(
            RestaurantSettings.restaurant_id == restaurant_id
        )
    ).scalar_one_or_none()
    # Approval gate: gated batches are created PENDING_APPROVAL — invisible to
    # the kitchen and unprinted until a waiter approves them (approve_pending_items).
    require_approval = bool(_settings is not None and _settings.require_order_approval)

    # Compact snapshot of the items added in THIS call, for the KOT that rides the
    # order.created event (kitchen ticket printing). Money accumulates in Decimal and
    # is serialised to strings on the event.
    kot_items: list[dict] = []
    _kot_subtotal = Decimal("0")
    _kot_tax = Decimal("0")

    # 3. Validate and snapshot each requested item.
    for item_data in request.items:
        # Tenant-scoped product lookup — also guards cross-tenant access.
        product = db.execute(
            select(Product).where(
                Product.id == item_data.product_id,
                Product.restaurant_id == restaurant_id,
                Product.is_active.is_(True),
            )
        ).scalar_one_or_none()
        if product is None:
            raise OrderError(
                f"Product {item_data.product_id} not found",
                status_code=404,
            )
        if not product.is_available:
            raise OrderError(
                f"Product '{product.name}' is not currently available",
                status_code=400,
            )

        # Variant — must belong to this product in this tenant.
        # A product with variants is priced by its variant, never base_price, so
        # the customer MUST pick one. Reject an order that omits it.
        if product.has_variants and item_data.variant_id is None:
            raise OrderError(
                f"Product '{product.name}' requires a variant selection",
                status_code=400,
            )

        unit_price = product.base_price
        variant_name = None
        if item_data.variant_id is not None:
            variant = db.execute(
                select(ProductVariant).where(
                    ProductVariant.id == item_data.variant_id,
                    ProductVariant.product_id == product.id,
                    ProductVariant.restaurant_id == restaurant_id,
                    ProductVariant.is_active.is_(True),
                )
            ).scalar_one_or_none()
            if variant is None:
                raise OrderError(
                    f"Variant {item_data.variant_id} not found or does not belong to this product",
                    status_code=404,
                )
            unit_price = variant.price
            variant_name = variant.name

        order_item = OrderItem(
            id=uuid.uuid4(),
            restaurant_id=restaurant_id,
            order_id=order.id,
            product_id=product.id,
            quantity=item_data.quantity,
            special_instructions=item_data.special_instructions,
            # Snapshots — frozen at order time; immune to later product edits.
            product_name=product.name,
            variant_name=variant_name,
            unit_price=unit_price,
            tax_rate=product.tax_rate,
            status=(
                OrderItemStatus.PENDING_APPROVAL
                if require_approval
                else OrderItemStatus.NEW
            ),
        )
        db.add(order_item)
        db.flush()

        # Addons — each must be mapped to this product in this tenant.
        addon_names: list[str] = []
        addon_unit_total = Decimal("0")  # per-unit addon price sum, for the KOT line total
        seen_addon_ids: set[uuid.UUID] = set()
        for addon_id in item_data.addon_ids:
            if addon_id in seen_addon_ids:
                continue  # silently deduplicate
            seen_addon_ids.add(addon_id)

            if not product.allows_addons:
                raise OrderError(
                    f"Product '{product.name}' does not allow addons",
                    status_code=400,
                )

            mapping = db.execute(
                select(ProductAddonMapping)
                .where(
                    ProductAddonMapping.product_id == product.id,
                    ProductAddonMapping.addon_id == addon_id,
                    ProductAddonMapping.restaurant_id == restaurant_id,
                )
                .options(selectinload(ProductAddonMapping.addon))
            ).scalar_one_or_none()
            if mapping is None or not mapping.addon.is_active:
                raise OrderError(
                    f"Addon {addon_id} is not available for this product",
                    status_code=400,
                )

            db.add(OrderItemAddon(
                id=uuid.uuid4(),
                restaurant_id=restaurant_id,
                order_item_id=order_item.id,
                # Addon name and price snapshotted — never updated by later addon edits.
                addon_name=mapping.addon.name,
                addon_price=mapping.addon.price,
            ))
            addon_names.append(mapping.addon.name)
            addon_unit_total += mapping.addon.price

        # KOT line total = (unit price + per-unit addons) × qty; tax from the product rate.
        line_total = (unit_price + addon_unit_total) * item_data.quantity
        line_tax = line_total * product.tax_rate / Decimal("100")
        _kot_subtotal += line_total
        _kot_tax += line_tax

        kot_items.append({
            "product_name": product.name,
            "variant_name": variant_name,
            "quantity": item_data.quantity,
            "special_instructions": item_data.special_instructions,
            "addons": addon_names,
            "line_total": f"{line_total:.2f}",
        })

    # 4. Audit log.
    db.add(AuditLog(
        id=uuid.uuid4(),
        restaurant_id=restaurant_id,
        actor_type="CUSTOMER_SESSION",
        actor_user_id=None,
        entity_type="order",
        entity_id=order.id,
        action="ORDER_CREATED" if order_created else "ITEMS_APPENDED",
        previous_value=(
            None if order_created
            else {"status": order.status.value, "item_count": prev_item_count}
        ),
        new_value={
            "order_number": order.order_number,
            "new_item_count": len(request.items),
            **({"requires_approval": True} if require_approval else {}),
        },
    ))

    # Save values before commit (SQLAlchemy expires ORM attrs on commit).
    _order_id_str = str(order.id)
    _order_number = order.order_number
    _table_id_str = str(table_id)
    _restaurant_id_str = str(restaurant_id)
    _new_item_count = len(request.items)
    _was_created = order_created
    _table_name = db.scalar(select(Table.name).where(Table.id == table_id)) or ""
    _currency = (_settings.currency if _settings else None) or "Rs"
    _kot_total = _kot_subtotal + _kot_tax

    # Worker-mode KOT: queue the ticket in the same transaction as the order
    # round, so the kot-printer service picks it up iff the round committed.
    # (Browser mode keeps printing from the order.created event instead.)
    # A gated batch queues nothing — approve_pending_items runs this on approval.
    if (
        not require_approval
        and _settings is not None
        and _settings.print_kot_enabled
        and _settings.kot_print_mode == "worker"
        and kot_items
    ):
        kot_print_service.enqueue_job(
            db,
            restaurant_id=restaurant_id,
            order_id=order.id,
            order_number=_order_number,
            table_name=_table_name,
            kot_items=kot_items,
        )

    db.commit()

    # Post-commit (gated batch): kitchen/counter/print station hear nothing yet.
    # Waiters get the approval request; the customer's table channel gets it too
    # so the status page can show "waiting for confirmation" immediately.
    if require_approval:
        approval_ev = OrderApprovalRequestedEvent(
            order_id=_order_id_str,
            order_number=_order_number,
            table_id=_table_id_str,
            table_name=_table_name,
            restaurant_id=_restaurant_id_str,
            item_count=_new_item_count,
        )
        _fire(rt_manager.broadcast_to_roles(
            _restaurant_id_str, approval_ev, [Role.WAITER, Role.ADMIN]
        ))
        _fire(rt_manager.broadcast_to_table(
            _restaurant_id_str, _table_id_str, approval_ev
        ))
        push_service.notify(db, approval_ev)
        return _load_order_with_items(db, order.id)

    # Post-commit: kitchen and counter see both new orders and appended items (the counter
    # is the KOT print station — it must get every round to auto-print), and the counter
    # display board refreshes so brand-new NEW items appear without waiting for its poll.
    # Only the initial creation pings the waiter (a new table arriving); appended rounds
    # don't need a per-round waiter ping.
    ev = OrderCreatedEvent(
        order_id=_order_id_str,
        order_number=_order_number,
        table_id=_table_id_str,
        restaurant_id=_restaurant_id_str,
        item_count=_new_item_count,
        table_name=_table_name,
        items=kot_items,
        currency=_currency,
        subtotal=f"{_kot_subtotal:.2f}",
        tax_total=f"{_kot_tax:.2f}",
        total=f"{_kot_total:.2f}",
    )
    # ADMIN is included so an admin-logged-in counter/print station receives the KOT
    # and auto-prints it (mirrors invoice.paid, which already targets ADMIN).
    _target_roles = (
        [Role.KITCHEN, Role.WAITER, Role.COUNTER, Role.COUNTER_DISPLAY, Role.ADMIN]
        if _was_created
        else [Role.KITCHEN, Role.COUNTER, Role.COUNTER_DISPLAY, Role.ADMIN]
    )
    _fire(rt_manager.broadcast_to_roles(_restaurant_id_str, ev, _target_roles))
    push_service.notify(db, ev)

    return _load_order_with_items(db, order.id)


def get_current_order(db: Session, session: TableSession) -> Order | None:
    """Returns the OPEN order for the session's table, eagerly loading items+addons."""
    order = db.execute(
        select(Order).where(
            Order.table_id == session.table_id,
            Order.restaurant_id == session.restaurant_id,
            Order.status == OrderStatus.OPEN,
        )
    ).scalar_one_or_none()
    if order is None:
        return None
    return _load_order_with_items(db, order.id)


def request_bill(db: Session, session: TableSession) -> Order:
    """
    Customer asks for the bill. Stamps the order's bill_requested_at (which is what
    unlocks staff's "move to billing" — see transition_order) and emits a
    `bill.requested` event to waiter + counter. Idempotent; 404 if no live order.
    """
    order = db.execute(
        select(Order).where(
            Order.table_id == session.table_id,
            Order.restaurant_id == session.restaurant_id,
            Order.status != OrderStatus.CLOSED,
        )
    ).scalar_one_or_none()
    if order is None:
        raise OrderError("No active order to bill", status_code=404)

    # Record the request once (gates staff's move-to-billing); audited.
    if order.bill_requested_at is None:
        order.bill_requested_at = datetime.now(timezone.utc)
        db.add(AuditLog(
            id=uuid.uuid4(),
            restaurant_id=session.restaurant_id,
            actor_type="CUSTOMER_SESSION",
            actor_user_id=None,
            entity_type="order",
            entity_id=order.id,
            action="BILL_REQUESTED",
            previous_value=None,
            new_value={"bill_requested": True},
        ))
        db.commit()

    table_name = db.scalar(
        select(Table.name).where(Table.id == session.table_id)
    ) or ""

    ev = BillRequestedEvent(
        order_id=str(order.id),
        order_number=order.order_number,
        table_id=str(session.table_id),
        table_name=table_name,
        restaurant_id=str(session.restaurant_id),
    )
    _fire(rt_manager.broadcast_to_roles(
        str(session.restaurant_id), ev, [Role.WAITER, Role.COUNTER]
    ))
    push_service.notify(db, ev)

    return _load_order_with_items(db, order.id)


def staff_start_billing(db: Session, restaurant_id: uuid.UUID, order_id: uuid.UUID, actor) -> Order:
    """
    Staff override: stamp bill_requested_at on an OPEN order so billing can proceed
    even though the customer never tapped Request Bill (dead phone / can't request).
    Audited as a staff action; idempotent; emits bill.requested so lists refresh.
    """
    order = db.execute(
        select(Order)
        .where(Order.id == order_id, Order.restaurant_id == restaurant_id)
        .with_for_update()
    ).scalar_one_or_none()
    if order is None:
        raise OrderError("Order not found", status_code=404)
    if order.status != OrderStatus.OPEN:
        raise OrderError(
            f"Cannot start billing: order is {order.status.value}", status_code=409
        )

    if order.bill_requested_at is None:
        order.bill_requested_at = datetime.now(timezone.utc)
        db.add(AuditLog(
            id=uuid.uuid4(),
            restaurant_id=restaurant_id,
            actor_type=actor.role.value,
            actor_user_id=actor.id,
            entity_type="order",
            entity_id=order.id,
            action="BILL_REQUESTED_STAFF",
            previous_value=None,
            new_value={"bill_requested": True, "by": "staff"},
        ))
        db.commit()

    table_name = db.scalar(select(Table.name).where(Table.id == order.table_id)) or ""
    ev = BillRequestedEvent(
        order_id=str(order.id),
        order_number=order.order_number,
        table_id=str(order.table_id),
        table_name=table_name,
        restaurant_id=str(restaurant_id),
    )
    _fire(rt_manager.broadcast_to_roles(
        str(restaurant_id), ev, [Role.WAITER, Role.COUNTER]
    ))
    return _load_order_with_items(db, order.id)


def list_open_orders(db: Session, restaurant_id: uuid.UUID) -> list[Order]:
    """
    Returns OPEN orders for the tenant (oldest first), with table + items
    eagerly loaded. Backs the waiter/counter 'move to billing' queues so the
    action stays reachable after every item has been served.

    Approval gate: an order whose only live items are still PENDING_APPROVAL is
    withheld — the counter must not see (or bill) a table until a waiter has
    approved its order. An order is shown once it has at least one approved item
    (NEW / PREPARING / READY / SERVED). Orders that have no pending items at all
    (the normal case, and fully-cancelled orders) are unaffected, so an all-
    rejected table still surfaces for staff to close out.
    """
    _APPROVED_STATES = (
        OrderItemStatus.NEW,
        OrderItemStatus.PREPARING,
        OrderItemStatus.READY,
        OrderItemStatus.SERVED,
    )
    has_approved_item = (
        select(OrderItem.id)
        .where(
            OrderItem.order_id == Order.id,
            OrderItem.restaurant_id == restaurant_id,
            OrderItem.status.in_(_APPROVED_STATES),
        )
        .exists()
    )
    has_pending_item = (
        select(OrderItem.id)
        .where(
            OrderItem.order_id == Order.id,
            OrderItem.restaurant_id == restaurant_id,
            OrderItem.status == OrderItemStatus.PENDING_APPROVAL,
        )
        .exists()
    )
    return db.scalars(
        select(Order)
        .where(
            Order.restaurant_id == restaurant_id,
            Order.status == OrderStatus.OPEN,
            or_(has_approved_item, ~has_pending_item),
        )
        .options(
            joinedload(Order.table),
            selectinload(Order.items),
        )
        .order_by(Order.created_at.asc())
    ).all()


# ── Manual KOT (re)print relay ───────────────────────────────────────────────
# A roaming waiter has no local printer, so their "print this table's order"
# action is relayed: build the kitchen ticket from the persisted order and emit a
# kot.print event to the print station (COUNTER/ADMIN), whose PrintController prints
# it on the paired kitchen printer.

def build_items_kot(
    order_items: list[OrderItem],
) -> tuple[list[dict], Decimal, Decimal, Decimal]:
    """
    Build the KOT item snapshot + (subtotal, tax, total) from the given items —
    the caller picks the batch (no status filtering here). Same line shape
    place_or_append puts on order.created: line_total = (unit_price +
    Σ addon_price) × quantity; tax from the item's tax_rate.
    Requires each item's .addons to be loaded.
    """
    items: list[dict] = []
    subtotal = Decimal("0")
    tax = Decimal("0")
    for it in order_items:
        addon_unit_total = sum((a.addon_price for a in it.addons), Decimal("0"))
        line_total = (it.unit_price + addon_unit_total) * it.quantity
        subtotal += line_total
        tax += line_total * it.tax_rate / Decimal("100")
        items.append({
            "product_name": it.product_name,
            "variant_name": it.variant_name,
            "quantity": it.quantity,
            "special_instructions": it.special_instructions,
            "addons": [a.addon_name for a in it.addons],
            "line_total": f"{line_total:.2f}",
        })
    return items, subtotal, tax, subtotal + tax


def build_order_kot(order: Order) -> tuple[list[dict], Decimal, Decimal, Decimal]:
    """
    Whole-order KOT (manual reprints): skips CANCELLED items and PENDING_APPROVAL
    items — an unapproved batch must never leak onto a printed ticket.
    Requires order.items and each item's .addons to be loaded.
    """
    return build_items_kot([
        it for it in order.items
        if it.status not in (
            OrderItemStatus.CANCELLED, OrderItemStatus.PENDING_APPROVAL
        )
    ])


def request_kot_print(
    db: Session, restaurant_id: uuid.UUID, order_id: uuid.UUID, actor
) -> None:
    """
    Relay a manual kitchen-ticket print for an existing order to the print station.
    Tenant-scoped; raises OrderError(404) for an unknown/other-tenant order. Writes an
    audit row (who reprinted) and broadcasts a kot.print event to COUNTER/ADMIN.
    """
    order = db.execute(
        select(Order)
        .where(Order.id == order_id, Order.restaurant_id == restaurant_id)
        .options(
            joinedload(Order.table),
            selectinload(Order.items).selectinload(OrderItem.addons),
        )
    ).scalar_one_or_none()
    if order is None:
        raise OrderError("Order not found", status_code=404)

    items, subtotal, tax, total = build_order_kot(order)
    _settings = db.execute(
        select(RestaurantSettings).where(
            RestaurantSettings.restaurant_id == restaurant_id
        )
    ).scalar_one_or_none()
    currency = (_settings.currency if _settings else None) or "Rs"

    _table_name = order.table.name if order.table else ""
    _order_number = order.order_number
    _order_id_str = str(order.id)
    _rid_str = str(restaurant_id)

    db.add(AuditLog(
        id=uuid.uuid4(),
        restaurant_id=restaurant_id,
        actor_type=actor.role.value,
        actor_user_id=actor.id,
        entity_type="order",
        entity_id=order.id,
        action="KOT_PRINT_REQUESTED",
        previous_value=None,
        new_value={"order_number": _order_number, "item_count": len(items)},
    ))

    # Worker mode: the reprint goes to the kot-printer queue, not the browser
    # print station (whose PrintController also ignores kot.print in this mode).
    if _settings is not None and _settings.kot_print_mode == "worker":
        kot_print_service.enqueue_job(
            db,
            restaurant_id=restaurant_id,
            order_id=order.id,
            order_number=_order_number,
            table_name=_table_name,
            kot_items=items,
            title="ORDER REPRINT",
        )
        db.commit()
        return

    db.commit()

    ev = KotPrintEvent(
        order_id=_order_id_str,
        order_number=_order_number,
        table_name=_table_name,
        restaurant_id=_rid_str,
        job_id=uuid.uuid4().hex,
        items=items,
        currency=currency,
        subtotal=f"{subtotal:.2f}",
        tax_total=f"{tax:.2f}",
        total=f"{total:.2f}",
    )
    _fire(rt_manager.broadcast_to_roles(_rid_str, ev, [Role.COUNTER, Role.ADMIN]))


# ── Waiter order-approval (require_order_approval gate) ─────────────────────
# When the toggle is on, place_or_append parks each customer batch in
# PENDING_APPROVAL. A waiter approves the batch (items -> NEW, the deferred KOT
# fires) or rejects it (items -> CANCELLED). One transaction, one audit row,
# batch-level events — deliberately NOT routed through transition_item, which
# commits and broadcasts per item.

def _lock_pending_batch(
    db: Session, restaurant_id: uuid.UUID, order_id: uuid.UUID
) -> tuple[Order, list[OrderItem]]:
    """
    Lock the order row (serialises racing approvers — exactly one wins) and
    return it with its PENDING_APPROVAL items, oldest first. Raises OrderError
    404 for unknown/other-tenant orders, 409 if the order is not OPEN or has
    nothing awaiting approval (the replay answer: a second approve is a 409).
    """
    order = db.execute(
        select(Order)
        .where(Order.id == order_id, Order.restaurant_id == restaurant_id)
        .with_for_update()
    ).scalar_one_or_none()
    if order is None:
        raise OrderError("Order not found", status_code=404)
    if order.status != OrderStatus.OPEN:
        raise OrderError(
            f"Order is {order.status.value} — nothing to approve",
            status_code=409,
        )

    items = list(db.scalars(
        select(OrderItem)
        .where(
            OrderItem.order_id == order.id,
            OrderItem.restaurant_id == restaurant_id,
            OrderItem.status == OrderItemStatus.PENDING_APPROVAL,
        )
        .options(selectinload(OrderItem.addons))
        .order_by(OrderItem.created_at.asc())
        .with_for_update(of=OrderItem)
    ).all())
    if not items:
        raise OrderError("No items awaiting approval", status_code=409)
    return order, items


def approve_pending_items(
    db: Session, restaurant_id: uuid.UUID, order_id: uuid.UUID, actor
) -> Order:
    """
    Approve the order's pending batch: items -> NEW and the deferred KOT path
    runs (worker mode queues the ticket in this same transaction; browser mode
    prints off the order.created event fired post-commit). Audited.
    """
    order, items = _lock_pending_batch(db, restaurant_id, order_id)

    for it in items:
        assert_valid_item_transition(it.status, OrderItemStatus.NEW)
        it.status = OrderItemStatus.NEW

    db.add(AuditLog(
        id=uuid.uuid4(),
        restaurant_id=restaurant_id,
        actor_type=actor.role.value,
        actor_user_id=actor.id,
        entity_type="order",
        entity_id=order.id,
        action="ORDER_ITEMS_APPROVED",
        previous_value={
            "item_status": OrderItemStatus.PENDING_APPROVAL.value,
            "item_ids": [str(it.id) for it in items],
        },
        new_value={
            "item_status": OrderItemStatus.NEW.value,
            "item_count": len(items),
        },
    ))

    kot_items, subtotal, tax, total = build_items_kot(items)
    _settings = db.execute(
        select(RestaurantSettings).where(
            RestaurantSettings.restaurant_id == restaurant_id
        )
    ).scalar_one_or_none()
    _currency = (_settings.currency if _settings else None) or "Rs"

    # Save before commit (attr expiry).
    _order_id_str = str(order.id)
    _order_number = order.order_number
    _table_id_str = str(order.table_id)
    _rid_str = str(restaurant_id)
    _item_count = len(items)
    _table_name = db.scalar(select(Table.name).where(Table.id == order.table_id)) or ""

    # This is the batch's FIRST print, deferred from placement (title "ORDER").
    if (
        _settings is not None
        and _settings.print_kot_enabled
        and _settings.kot_print_mode == "worker"
    ):
        kot_print_service.enqueue_job(
            db,
            restaurant_id=restaurant_id,
            order_id=order.id,
            order_number=_order_number,
            table_name=_table_name,
            kot_items=kot_items,
        )

    db.commit()

    # Post-commit: the kitchen/counter/print-station side now hears about the
    # batch exactly as if it had just been placed (order.created drives the
    # kitchen refresh, chime, and browser-mode auto-print).
    created_ev = OrderCreatedEvent(
        order_id=_order_id_str,
        order_number=_order_number,
        table_id=_table_id_str,
        restaurant_id=_rid_str,
        item_count=_item_count,
        table_name=_table_name,
        items=kot_items,
        currency=_currency,
        subtotal=f"{subtotal:.2f}",
        tax_total=f"{tax:.2f}",
        total=f"{total:.2f}",
    )
    _fire(rt_manager.broadcast_to_roles(
        _rid_str, created_ev,
        [Role.KITCHEN, Role.COUNTER, Role.COUNTER_DISPLAY, Role.ADMIN],
    ))
    push_service.notify(db, created_ev)

    decided_ev = OrderApprovalDecidedEvent(
        order_id=_order_id_str,
        order_number=_order_number,
        table_id=_table_id_str,
        table_name=_table_name,
        restaurant_id=_rid_str,
        decision="APPROVED",
        item_count=_item_count,
    )
    _fire(rt_manager.broadcast_to_roles(_rid_str, decided_ev, [Role.WAITER, Role.ADMIN]))
    _fire(rt_manager.broadcast_to_table(_rid_str, _table_id_str, decided_ev))

    return _load_order_with_items(db, order.id)


def reject_pending_items(
    db: Session,
    restaurant_id: uuid.UUID,
    order_id: uuid.UUID,
    actor,
    reason: str | None = None,
) -> Order:
    """
    Reject the order's pending batch: items -> CANCELLED. No KOT, no
    order.created — the kitchen never learns the batch existed. Audited with
    the waiter's optional reason; the customer's table channel is notified.
    """
    order, items = _lock_pending_batch(db, restaurant_id, order_id)

    for it in items:
        assert_valid_item_transition(it.status, OrderItemStatus.CANCELLED)
        it.status = OrderItemStatus.CANCELLED

    db.add(AuditLog(
        id=uuid.uuid4(),
        restaurant_id=restaurant_id,
        actor_type=actor.role.value,
        actor_user_id=actor.id,
        entity_type="order",
        entity_id=order.id,
        action="ORDER_ITEMS_REJECTED",
        previous_value={
            "item_status": OrderItemStatus.PENDING_APPROVAL.value,
            "item_ids": [str(it.id) for it in items],
        },
        new_value={
            "item_status": OrderItemStatus.CANCELLED.value,
            "item_count": len(items),
        },
        reason=reason,
    ))

    # Save before commit (attr expiry).
    _order_id_str = str(order.id)
    _order_number = order.order_number
    _table_id_str = str(order.table_id)
    _rid_str = str(restaurant_id)
    _item_count = len(items)
    _table_name = db.scalar(select(Table.name).where(Table.id == order.table_id)) or ""

    db.commit()

    decided_ev = OrderApprovalDecidedEvent(
        order_id=_order_id_str,
        order_number=_order_number,
        table_id=_table_id_str,
        table_name=_table_name,
        restaurant_id=_rid_str,
        decision="REJECTED",
        item_count=_item_count,
    )
    _fire(rt_manager.broadcast_to_roles(_rid_str, decided_ev, [Role.WAITER, Role.ADMIN]))
    _fire(rt_manager.broadcast_to_table(_rid_str, _table_id_str, decided_ev))

    return _load_order_with_items(db, order.id)


# ── Staff-facing helpers (called by Phase 6 endpoints) ───────────────────────

def transition_order(
    db: Session,
    restaurant_id: uuid.UUID,
    order_id: uuid.UUID,
    new_status: OrderStatus,
    actor_type: str,
    actor_id: uuid.UUID | None = None,
    reason: str | None = None,
    allow_reopen: bool = False,
) -> Order:
    """
    Drives the order state machine under a row lock.
    Phase 6 staff endpoints call this; customers never call it directly.
    Raises OrderError on invalid transitions.
    """
    order = db.execute(
        select(Order)
        .where(Order.id == order_id, Order.restaurant_id == restaurant_id)
        .with_for_update()
    ).scalar_one_or_none()
    if order is None:
        raise OrderError("Order not found", status_code=404)

    prev_status = order.status
    assert_valid_order_transition(prev_status, new_status, allow_reopen=allow_reopen, reason=reason)

    # Gate: a table can only move to billing after the customer requested the bill.
    if new_status == OrderStatus.MEAL_FINISHED and order.bill_requested_at is None:
        raise OrderError(
            "Cannot move to billing: the customer has not requested the bill yet",
            status_code=409,
        )

    # Gate: a batch awaiting waiter approval must be approved or rejected before
    # the order can move to billing (pending items are neither cooked nor billed).
    if new_status == OrderStatus.MEAL_FINISHED:
        pending = db.scalar(
            select(OrderItem.id).where(
                OrderItem.order_id == order.id,
                OrderItem.restaurant_id == restaurant_id,
                OrderItem.status == OrderItemStatus.PENDING_APPROVAL,
            ).limit(1)
        )
        if pending is not None:
            raise OrderError(
                "Cannot move to billing: items are awaiting approval — "
                "approve or reject them first",
                status_code=409,
            )

    order.status = new_status
    db.add(AuditLog(
        id=uuid.uuid4(),
        restaurant_id=restaurant_id,
        actor_type=actor_type,
        actor_user_id=actor_id,
        entity_type="order",
        entity_id=order.id,
        action=f"ORDER_{new_status.value}",
        previous_value={"status": prev_status.value},
        new_value={"status": new_status.value},
        reason=reason,
    ))

    # Save before commit to avoid attr expiry.
    _oid_str = str(order.id)
    _onum = order.order_number
    _tid_str = str(order.table_id)
    _rid_str = str(restaurant_id)
    _prev_str = prev_status.value
    _new_str = new_status.value

    db.commit()

    # Post-commit: route event to appropriate staff roles and the customer table.
    ev = OrderStatusChangedEvent(
        order_id=_oid_str,
        order_number=_onum,
        table_id=_tid_str,
        restaurant_id=_rid_str,
        previous_status=_prev_str,
        new_status=_new_str,
    )
    if new_status == OrderStatus.MEAL_FINISHED:
        _fire(rt_manager.broadcast_to_roles(_rid_str, ev, [Role.WAITER, Role.COUNTER]))
    elif new_status == OrderStatus.OPEN:
        _fire(rt_manager.broadcast_to_roles(_rid_str, ev, [Role.KITCHEN, Role.WAITER]))
    # Customer always gets order status changes.
    _fire(rt_manager.broadcast_to_table(_rid_str, _tid_str, ev))

    return _load_order_with_items(db, order.id)


def transition_item(
    db: Session,
    restaurant_id: uuid.UUID,
    order_item_id: uuid.UUID,
    new_status: OrderItemStatus,
    actor_type: str,
    actor_id: uuid.UUID | None = None,
) -> OrderItem:
    """
    Drives the order-item state machine under a row lock, setting transition
    timestamps (preparing_at / ready_at / served_at) and writing an audit row.
    Phase 6 staff endpoints call this.
    Raises OrderError on invalid transitions.
    """
    item = db.execute(
        select(OrderItem)
        .where(OrderItem.id == order_item_id, OrderItem.restaurant_id == restaurant_id)
        .with_for_update()
    ).scalar_one_or_none()
    if item is None:
        raise OrderError("Order item not found", status_code=404)

    prev_status = item.status
    assert_valid_item_transition(prev_status, new_status)

    now = datetime.now(timezone.utc)
    item.status = new_status
    if new_status == OrderItemStatus.PREPARING:
        item.preparing_at = now
    elif new_status == OrderItemStatus.READY:
        item.ready_at = now
    elif new_status == OrderItemStatus.SERVED:
        item.served_at = now

    db.add(AuditLog(
        id=uuid.uuid4(),
        restaurant_id=restaurant_id,
        actor_type=actor_type,
        actor_user_id=actor_id,
        entity_type="order_item",
        entity_id=item.id,
        action=f"ITEM_{new_status.value}",
        previous_value={"status": prev_status.value},
        new_value={"status": new_status.value},
    ))

    # Save before commit.
    _iid_str = str(item.id)
    _oid_str = str(item.order_id)
    _rid_str = str(restaurant_id)
    _pname = item.product_name
    _prev_str = prev_status.value
    _new_str = new_status.value

    db.commit()
    db.refresh(item)

    # Fetch the table_id for customer routing (one read-only query, post-commit).
    _table_id = db.scalar(select(Order.table_id).where(Order.id == item.order_id))
    _tid_str = str(_table_id) if _table_id else None

    ev = OrderItemStatusChangedEvent(
        order_item_id=_iid_str,
        order_id=_oid_str,
        table_id=_tid_str or "",
        restaurant_id=_rid_str,
        product_name=_pname,
        previous_status=_prev_str,
        new_status=_new_str,
    )
    # Kitchen sees NEW / PREPARING / READY; waiter sees READY / SERVED;
    # the counter display board tracks the full lifecycle (NEW → SERVED) and never
    # clears, so it gets every non-CANCELLED transition.
    _staff_roles: list[Role] = []
    if new_status in {OrderItemStatus.NEW, OrderItemStatus.PREPARING, OrderItemStatus.READY}:
        _staff_roles.append(Role.KITCHEN)
    if new_status in {OrderItemStatus.READY, OrderItemStatus.SERVED}:
        _staff_roles.append(Role.WAITER)
    if new_status != OrderItemStatus.CANCELLED:
        _staff_roles.append(Role.COUNTER_DISPLAY)
    if _staff_roles:
        _fire(rt_manager.broadcast_to_roles(_rid_str, ev, _staff_roles))
    # Customer always gets item status changes for their table's order.
    if _tid_str:
        _fire(rt_manager.broadcast_to_table(_rid_str, _tid_str, ev))

    return item
