"""
Bulk product import from a CSV (admin uploads a photographed/AI-extracted menu).

Two phases, both tenant-scoped:
  preview() — parses + validates the CSV and reports what WOULD happen. Writes
              nothing.
  commit()  — re-parses + re-validates the same CSV, then creates categories and
              products inside a single transaction (all-or-nothing). Refuses if
              any row has an error.

Row validation is delegated to app.schemas.menu.ProductCreate (the exact same
Pydantic model the single-product "Add Product" endpoint uses) so field bounds
(name length, price >= 0, tax_rate 0-100, ...) live in one place. Row writes are
delegated to menu_service.build_category / build_product for the same reason —
the importer never duplicates business rules, only CSV-specific parsing
(header/row shape, food_type aliasing, blank -> default substitution, and
duplicate detection, none of which the single-product endpoint needs).

Row numbers in ImportRowError follow spreadsheet convention: the header is row 1,
the first data row is row 2.
"""

import csv
import io
import uuid
from dataclasses import dataclass, field

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.enums import FoodType
from app.models.product import Product
from app.models.user import User
from app.schemas.menu import (
    CategoryCreate,
    ImportCommitResponse,
    ImportPreviewResponse,
    ImportRowError,
    ProductCreate,
)
from app.services import menu_service

REQUIRED_COLUMNS = {"category", "name"}

# CSV food_type values are free text from an AI menu extraction ("Non-veg",
# "non veg", "NONVEG", ...) — normalize before matching the strict enum.
_FOOD_TYPE_ALIASES: dict[str, FoodType] = {
    "VEG": FoodType.VEG,
    "NON_VEG": FoodType.NON_VEG,
    "NONVEG": FoodType.NON_VEG,
    "EGG": FoodType.EGG,
    "BEVERAGE": FoodType.BEVERAGE,
    "SMOKE": FoodType.SMOKE,
}

# Pydantic's ValidationError reports the ProductCreate field name; map it back to
# the CSV column name (and the original, un-substituted raw cell) for the report.
_LOC_TO_CSV_FIELD = {"is_available": "available"}


def _normalize_food_type(raw: str) -> FoodType | None:
    key = raw.strip().upper().replace(" ", "_").replace("-", "_")
    return _FOOD_TYPE_ALIASES.get(key)


@dataclass
class ParsedRow:
    row: int
    category_name: str
    product: ProductCreate  # category_id is a placeholder, replaced at commit time


@dataclass
class ImportPlan:
    # (row, normalized-category-name) for every product that would be created
    to_create: list[tuple[ParsedRow, str]] = field(default_factory=list)
    duplicates: list[ParsedRow] = field(default_factory=list)
    new_category_names: list[str] = field(default_factory=list)
    existing_category_names: list[str] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────────────
# Parsing
# ──────────────────────────────────────────────────────────────────────────────

def _decode_csv(raw: bytes) -> tuple[str | None, ImportRowError | None]:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None, ImportRowError(row=1, field="file", message="File is not valid UTF-8 text.", raw="")
    if not text.strip():
        return None, ImportRowError(row=1, field="file", message="File is empty.", raw="")
    return text, None


def _read_rows(raw: bytes) -> tuple[list[tuple[int, dict[str, str]]], list[ImportRowError]]:
    text, decode_error = _decode_csv(raw)
    if decode_error is not None:
        return [], [decode_error]
    assert text is not None

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return [], [ImportRowError(row=1, field="file", message="File is empty.", raw="")]

    headers = {(h or "").strip().lower() for h in reader.fieldnames}
    missing = REQUIRED_COLUMNS - headers
    if missing:
        return [], [
            ImportRowError(row=1, field=col, message=f"Missing required column '{col}'.", raw="")
            for col in sorted(missing)
        ]

    rows: list[tuple[int, dict[str, str]]] = []
    for i, raw_row in enumerate(reader, start=2):
        norm = {(k or "").strip().lower(): (v or "").strip() for k, v in raw_row.items() if k}
        rows.append((i, norm))
    return rows, []


def _validate_row(row_num: int, raw: dict[str, str]) -> tuple[ParsedRow | None, list[ImportRowError]]:
    errors: list[ImportRowError] = []

    category_name = raw.get("category", "")
    if not category_name:
        errors.append(ImportRowError(row=row_num, field="category", message="Category is required.", raw=""))

    food_raw = raw.get("food_type", "")
    if food_raw:
        food_type = _normalize_food_type(food_raw)
        if food_type is None:
            errors.append(ImportRowError(
                row=row_num, field="food_type",
                message=f"Unknown food_type '{food_raw}' — expected veg, non-veg, egg, beverage, or smoke.",
                raw=food_raw,
            ))
            food_type = FoodType.NON_VEG  # placeholder so other field errors still surface
    else:
        food_type = FoodType.NON_VEG

    name_raw = raw.get("name", "")
    desc_raw = raw.get("short_description", "")
    price_raw = raw.get("base_price", "")
    tax_raw = raw.get("tax_rate", "")
    avail_raw = raw.get("available", "")
    raw_by_field = {
        "name": name_raw,
        "description": desc_raw,
        "base_price": price_raw,
        "tax_rate": tax_raw,
        "available": avail_raw,
    }

    product: ProductCreate | None = None
    try:
        product = ProductCreate(
            category_id=uuid.uuid4(),  # placeholder; resolved to a real category at commit time
            name=name_raw,
            description=desc_raw or None,
            base_price=price_raw or "0",
            tax_rate=tax_raw or "0",
            food_type=food_type,
            is_available=avail_raw or "true",
            has_variants=False,
            allows_addons=False,
        )
    except ValidationError as exc:
        for e in exc.errors():
            loc = str(e["loc"][0]) if e["loc"] else "row"
            csv_field = _LOC_TO_CSV_FIELD.get(loc, loc)
            errors.append(ImportRowError(
                row=row_num, field=csv_field, message=e["msg"], raw=raw_by_field.get(csv_field, ""),
            ))
        product = None

    if errors or product is None:
        return None, errors

    return ParsedRow(row=row_num, category_name=category_name, product=product), []


# ──────────────────────────────────────────────────────────────────────────────
# Planning (category resolution + duplicate detection)
# ──────────────────────────────────────────────────────────────────────────────

def _active_categories(db: Session, restaurant_id: uuid.UUID) -> list[Category]:
    return list(
        db.execute(
            select(Category).where(
                Category.restaurant_id == restaurant_id,
                Category.is_active.is_(True),
            )
        ).scalars().all()
    )


def _existing_product_keys(db: Session, restaurant_id: uuid.UUID) -> set[tuple[str, str]]:
    """(category name, product name) pairs, both lowercased, for every live
    product in a live category — the duplicate-skip check."""
    rows = db.execute(
        select(Product.name, Category.name)
        .join(Category, Product.category_id == Category.id)
        .where(
            Product.restaurant_id == restaurant_id,
            Product.is_active.is_(True),
            Category.is_active.is_(True),
        )
    ).all()
    return {(cat_name.strip().lower(), prod_name.strip().lower()) for prod_name, cat_name in rows}


def _plan(db: Session, restaurant_id: uuid.UUID, parsed: list[ParsedRow]) -> ImportPlan:
    # Category name match is case-insensitive across the whole tenant tree (the
    # CSV has no parent column to disambiguate by depth); if two categories
    # share a name at different depths, the first one found wins.
    existing_categories = {c.name.strip().lower(): c.name.strip() for c in _active_categories(db, restaurant_id)}
    existing_products = _existing_product_keys(db, restaurant_id)

    plan = ImportPlan()
    new_seen: set[str] = set()
    existing_seen: set[str] = set()
    planned_pairs: set[tuple[str, str]] = set()

    for pr in parsed:
        cat_norm = pr.category_name.strip().lower()
        if cat_norm in existing_categories:
            if cat_norm not in existing_seen:
                existing_seen.add(cat_norm)
                plan.existing_category_names.append(existing_categories[cat_norm])
        elif cat_norm not in new_seen:
            new_seen.add(cat_norm)
            plan.new_category_names.append(pr.category_name.strip())

        pair = (cat_norm, pr.product.name.strip().lower())
        if pair in existing_products or pair in planned_pairs:
            plan.duplicates.append(pr)
        else:
            planned_pairs.add(pair)
            plan.to_create.append((pr, cat_norm))

    return plan


def _parse_and_plan(
    db: Session, restaurant_id: uuid.UUID, raw_csv: bytes
) -> tuple[list[ImportRowError], ImportPlan]:
    rows, header_errors = _read_rows(raw_csv)
    row_errors = list(header_errors)
    parsed: list[ParsedRow] = []
    for row_num, raw_row in rows:
        pr, errs = _validate_row(row_num, raw_row)
        row_errors.extend(errs)
        if pr is not None:
            parsed.append(pr)
    return row_errors, _plan(db, restaurant_id, parsed)


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def preview(db: Session, restaurant_id: uuid.UUID, raw_csv: bytes) -> ImportPreviewResponse:
    row_errors, plan = _parse_and_plan(db, restaurant_id, raw_csv)
    return ImportPreviewResponse(
        valid_rows=len(plan.to_create) + len(plan.duplicates),
        products_to_create=len(plan.to_create),
        duplicates_skipped=len(plan.duplicates),
        new_categories=plan.new_category_names,
        existing_categories=plan.existing_category_names,
        errors=row_errors,
    )


def commit(
    db: Session, restaurant_id: uuid.UUID, raw_csv: bytes, actor: User
) -> ImportCommitResponse:
    row_errors, plan = _parse_and_plan(db, restaurant_id, raw_csv)
    if row_errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "CSV contains validation errors — fix and re-preview.",
                "errors": [e.model_dump() for e in row_errors],
            },
        )

    try:
        category_by_norm = {c.name.strip().lower(): c for c in _active_categories(db, restaurant_id)}
        categories_created = 0
        for name in plan.new_category_names:
            cat = menu_service.build_category(
                db, restaurant_id, CategoryCreate(name=name, display_order=0, is_available=True), actor,
            )
            category_by_norm[name.strip().lower()] = cat
            categories_created += 1

        products_created = 0
        for pr, cat_norm in plan.to_create:
            category = category_by_norm[cat_norm]
            product_data = pr.product.model_copy(update={"category_id": category.id})
            menu_service.build_product(db, restaurant_id, product_data, actor)
            products_created += 1

        db.commit()
    except Exception:
        db.rollback()
        raise

    return ImportCommitResponse(
        categories_created=categories_created,
        products_created=products_created,
        duplicates_skipped=len(plan.duplicates),
    )
