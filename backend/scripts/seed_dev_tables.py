#!/usr/bin/env python3
"""
Seed ~8 active floor tables for a local/dev restaurant.

Usage (from repo root, with compose up):
  docker compose exec backend python scripts/seed_dev_tables.py
  docker compose exec backend python scripts/seed_dev_tables.py --slug sujaltest

Idempotent: skips names that already exist for that restaurant.
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.restaurant import Restaurant
from app.models.table import Table

DEFAULT_NAMES = [f"T{i}" for i in range(1, 9)]  # T1 … T8


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--slug",
        default=None,
        help="Restaurant slug (default: first active restaurant)",
    )
    parser.add_argument(
        "--names",
        nargs="+",
        default=DEFAULT_NAMES,
        help="Table names to ensure exist",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        q = select(Restaurant).where(Restaurant.is_active.is_(True))
        if args.slug:
            q = q.where(Restaurant.slug == args.slug)
        restaurant = db.scalars(q.order_by(Restaurant.created_at.asc())).first()
        if restaurant is None:
            print("No restaurant found. Create one first (superadmin / docs).", file=sys.stderr)
            return 1

        existing = {
            t.name
            for t in db.scalars(
                select(Table).where(Table.restaurant_id == restaurant.id)
            ).all()
        }
        created = []
        for name in args.names:
            if name in existing:
                continue
            db.add(Table(restaurant_id=restaurant.id, name=name, is_active=True))
            created.append(name)
        db.commit()
        print(f"restaurant={restaurant.slug!r} id={restaurant.id}")
        print(f"created={created or '[] (all already present)'}")
        print(f"total_names_requested={len(args.names)}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
