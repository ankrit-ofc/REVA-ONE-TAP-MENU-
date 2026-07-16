"""
Waiter-call service — the persisted 'Call Waiter' log.

create_call        — customer taps Call Waiter; upserts one PENDING call per table.
list_pending_calls — the waiter dashboard's open-calls list (oldest first).
attend_call        — a waiter confirms they attended: PENDING -> ATTENDED, stamps
                     who/when, audited, and clears the call on every staff dashboard.

Security invariants (never in the router):
- restaurant_id is derived from the validated session/JWT, never the client.
- Every tenant-owned query is scoped by restaurant_id.
- Attending is a state transition, so it emits an audit_logs row.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.models.audit_log import AuditLog
from app.models.enums import Role, WaiterCallStatus
from app.models.table import Table, TableSession
from app.models.user import User
from app.models.waiter_call import WaiterCall
from app.realtime.events import WaiterCallAttendedEvent, WaiterCalledEvent
from app.realtime.manager import _fire, manager as rt_manager
from app.services import push_service
from app.services.order_state import OrderError


def create_call(db: Session, session: TableSession) -> tuple[str, WaiterCall]:
    """
    Persist a customer's Call Waiter request and ring the staff dashboards.

    At most one PENDING call exists per table (enforced by a partial unique index):
    a repeated tap reuses the open call rather than piling up duplicates. Returns
    (table_name, call). Broadcasts waiter.called to WAITER/COUNTER/COUNTER_DISPLAY/ADMIN.
    """
    restaurant_id = session.restaurant_id
    table_id = session.table_id

    table_name = db.scalar(select(Table.name).where(Table.id == table_id)) or ""

    existing = db.execute(
        select(WaiterCall).where(
            WaiterCall.table_id == table_id,
            WaiterCall.restaurant_id == restaurant_id,
            WaiterCall.status == WaiterCallStatus.PENDING.value,
        )
    ).scalar_one_or_none()

    if existing is not None:
        call = existing
    else:
        call = WaiterCall(
            id=uuid.uuid4(),
            restaurant_id=restaurant_id,
            table_id=table_id,
            status=WaiterCallStatus.PENDING.value,
        )
        db.add(call)
        db.add(AuditLog(
            id=uuid.uuid4(),
            restaurant_id=restaurant_id,
            actor_type="CUSTOMER_SESSION",
            actor_user_id=None,
            entity_type="waiter_call",
            entity_id=call.id,
            action="WAITER_CALLED",
            previous_value=None,
            new_value={"table_id": str(table_id)},
        ))
        try:
            db.commit()
        except IntegrityError:
            # A concurrent tap won the unique-index race — reuse its PENDING call.
            db.rollback()
            call = db.execute(
                select(WaiterCall).where(
                    WaiterCall.table_id == table_id,
                    WaiterCall.restaurant_id == restaurant_id,
                    WaiterCall.status == WaiterCallStatus.PENDING.value,
                )
            ).scalar_one()

    _call_id = str(call.id)
    ev = WaiterCalledEvent(
        table_id=str(table_id),
        table_name=table_name,
        restaurant_id=str(restaurant_id),
        call_id=_call_id,
    )
    _fire(rt_manager.broadcast_to_roles(
        str(restaurant_id),
        ev,
        [Role.WAITER, Role.COUNTER, Role.COUNTER_DISPLAY, Role.ADMIN],
    ))
    push_service.notify(db, ev)
    return table_name, call


def list_pending_calls(db: Session, restaurant_id: uuid.UUID) -> list[WaiterCall]:
    """Open (PENDING) calls for the tenant, oldest first, with the table eagerly loaded."""
    return list(db.scalars(
        select(WaiterCall)
        .where(
            WaiterCall.restaurant_id == restaurant_id,
            WaiterCall.status == WaiterCallStatus.PENDING.value,
        )
        .options(joinedload(WaiterCall.table))
        .order_by(WaiterCall.created_at.asc())
    ).all())


def attend_call(
    db: Session, restaurant_id: uuid.UUID, call_id: uuid.UUID, actor: User
) -> WaiterCall:
    """
    A waiter confirms they attended a call: PENDING -> ATTENDED under a row lock,
    stamping attended_at / attended_by_user_id. Audited. Broadcasts
    waiter.call_attended so the call clears on every staff dashboard.

    Raises OrderError 404 (unknown/other-tenant call) or 409 (already attended).
    """
    call = db.execute(
        select(WaiterCall)
        .where(WaiterCall.id == call_id, WaiterCall.restaurant_id == restaurant_id)
        .with_for_update()
    ).scalar_one_or_none()
    if call is None:
        raise OrderError("Waiter call not found", status_code=404)
    if call.status != WaiterCallStatus.PENDING.value:
        # Idempotent-ish: a second attend is a no-op conflict, not a double-apply.
        raise OrderError("This call has already been attended", status_code=409)

    call.status = WaiterCallStatus.ATTENDED.value
    call.attended_at = datetime.now(timezone.utc)
    call.attended_by_user_id = actor.id

    db.add(AuditLog(
        id=uuid.uuid4(),
        restaurant_id=restaurant_id,
        actor_type=actor.role.value,
        actor_user_id=actor.id,
        entity_type="waiter_call",
        entity_id=call.id,
        action="WAITER_CALL_ATTENDED",
        previous_value={"status": WaiterCallStatus.PENDING.value},
        new_value={"status": WaiterCallStatus.ATTENDED.value},
    ))

    # Save before commit (attrs expire on commit).
    _call_id = str(call.id)
    _table_id = str(call.table_id)
    _rid_str = str(restaurant_id)
    _attended_by = actor.email

    db.commit()

    table_name = db.scalar(select(Table.name).where(Table.id == call.table_id)) or ""
    ev = WaiterCallAttendedEvent(
        call_id=_call_id,
        table_id=_table_id,
        table_name=table_name,
        restaurant_id=_rid_str,
        attended_by=_attended_by,
    )
    _fire(rt_manager.broadcast_to_roles(
        _rid_str, ev, [Role.WAITER, Role.COUNTER, Role.COUNTER_DISPLAY, Role.ADMIN]
    ))

    db.refresh(call)
    return call
