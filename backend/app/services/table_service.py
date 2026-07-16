"""Business logic for admin table management."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.table import Table
from app.schemas.admin_tables import TableCreate, TableUpdate


def _get_table(db: Session, restaurant_id: uuid.UUID, table_id: uuid.UUID) -> Table:
    table = db.execute(
        select(Table).where(
            Table.id == table_id,
            Table.restaurant_id == restaurant_id,
        )
    ).scalar_one_or_none()
    if table is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Table not found")
    return table


def list_tables(db: Session, restaurant_id: uuid.UUID) -> list[Table]:
    return list(
        db.scalars(
            select(Table)
            .where(Table.restaurant_id == restaurant_id)
            .order_by(Table.name.asc())
        ).all()
    )


def create_table(db: Session, restaurant_id: uuid.UUID, data: TableCreate) -> Table:
    existing = db.execute(
        select(Table).where(
            Table.name == data.name,
            Table.restaurant_id == restaurant_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Table '{data.name}' already exists",
        )

    table = Table(restaurant_id=restaurant_id, name=data.name)
    db.add(table)
    db.commit()
    db.refresh(table)
    return table


def update_table(
    db: Session,
    restaurant_id: uuid.UUID,
    table_id: uuid.UUID,
    data: TableUpdate,
) -> Table:
    table = _get_table(db, restaurant_id, table_id)

    if data.name is not None and data.name != table.name:
        clash = db.execute(
            select(Table).where(
                Table.name == data.name,
                Table.restaurant_id == restaurant_id,
                Table.id != table_id,
            )
        ).scalar_one_or_none()
        if clash is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Table '{data.name}' already exists",
            )
        table.name = data.name

    if data.is_active is not None:
        table.is_active = data.is_active

    db.commit()
    db.refresh(table)
    return table


def deactivate_table(
    db: Session, restaurant_id: uuid.UUID, table_id: uuid.UUID
) -> Table:
    return update_table(db, restaurant_id, table_id, TableUpdate(is_active=False))
