"""
Gapless per-restaurant sequence numbers (order #, invoice # in Phase 7).

Uses SELECT ... FOR UPDATE to serialize increments within a transaction.
A savepoint handles the rare race when the counter row does not yet exist
and two transactions try to INSERT it simultaneously.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.restaurant_counter import RestaurantCounter


def next_number(db: Session, restaurant_id: uuid.UUID, counter_type: str) -> int:
    """
    Atomically increments and returns the next number for (restaurant_id, counter_type).

    Locked with FOR UPDATE so concurrent callers within the same restaurant
    always receive distinct, gapless values.
    """
    counter = db.execute(
        select(RestaurantCounter)
        .where(
            RestaurantCounter.restaurant_id == restaurant_id,
            RestaurantCounter.counter_type == counter_type,
        )
        .with_for_update()
    ).scalar_one_or_none()

    if counter is None:
        # First number for this (restaurant, type) pair.
        # Savepoint guards against the unlikely concurrent-INSERT race when two
        # different tables in the same restaurant get their very first orders
        # simultaneously.
        try:
            sp = db.begin_nested()
            counter = RestaurantCounter(
                id=uuid.uuid4(),
                restaurant_id=restaurant_id,
                counter_type=counter_type,
                current_value=1,
            )
            db.add(counter)
            db.flush()
            sp.commit()
            return 1
        except Exception:
            sp.rollback()
            # Another transaction won the race; re-acquire the lock and increment.
            counter = db.execute(
                select(RestaurantCounter)
                .where(
                    RestaurantCounter.restaurant_id == restaurant_id,
                    RestaurantCounter.counter_type == counter_type,
                )
                .with_for_update()
            ).scalar_one()
            counter.current_value += 1
            db.flush()
            return counter.current_value
    else:
        counter.current_value += 1
        db.flush()
        return counter.current_value
