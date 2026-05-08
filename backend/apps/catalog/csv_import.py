"""Product CSV import: parse → dry-run preview → commit.

Format:
  - UTF-8 with optional BOM (`utf-8-sig` decoding tolerates both).
  - Both LF and CRLF line endings.
  - Quoted fields with commas (Python csv module handles natively).
  - Strict snake_case headers — see PHASE_1_HEADERS below.
  - SKU is the natural key for upsert. Match by SKU within tenant.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from io import StringIO
from typing import Iterable

from django.db import transaction

from .models import Category, HsCode, Product, TaxRate, UnitOfMeasure

REQUIRED = {"sku", "name", "uom_code", "sale_price"}
OPTIONAL = {
    "barcode", "name_ur", "description", "category", "hs_code",
    "tax_rate", "cost_price", "retail_price", "min_sale_price",
    "max_discount_pct", "reorder_level", "is_active", "is_taxable",
}
ALL_FIELDS = REQUIRED | OPTIONAL


@dataclass
class CsvRow:
    line: int
    sku: str
    fields: dict
    errors: list[dict] = field(default_factory=list)


def parse_csv(file_obj) -> tuple[list[CsvRow], list[dict]]:
    """Read the CSV. Returns (rows, parse_errors)."""
    raw = file_obj.read()
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8-sig")
    text = raw.replace("\r\n", "\n").replace("\r", "\n")

    reader = csv.DictReader(StringIO(text))
    headers = set(reader.fieldnames or [])
    parse_errors: list[dict] = []

    missing = REQUIRED - headers
    if missing:
        parse_errors.append({
            "row": 0,
            "column": ", ".join(sorted(missing)),
            "message": f"Missing required column(s): {', '.join(sorted(missing))}",
        })
        return [], parse_errors

    unknown = headers - ALL_FIELDS
    if unknown:
        parse_errors.append({
            "row": 0,
            "column": ", ".join(sorted(unknown)),
            "message": f"Unknown column(s): {', '.join(sorted(unknown))}. Use the mapping wizard.",
        })

    rows: list[CsvRow] = []
    for line_no, raw_row in enumerate(reader, start=2):  # row 1 = header
        sku = (raw_row.get("sku") or "").strip()
        rows.append(CsvRow(line=line_no, sku=sku, fields={
            k: (v.strip() if isinstance(v, str) else v)
            for k, v in raw_row.items() if k in ALL_FIELDS
        }))
    return rows, parse_errors


def _coerce_decimal(value, field_name: str) -> tuple[Decimal | None, str | None]:
    if value is None or value == "":
        return None, None
    try:
        return Decimal(value), None
    except (InvalidOperation, ValueError):
        return None, f"Not a valid decimal in {field_name}: {value!r}"


def _coerce_bool(value) -> bool:
    return str(value).lower() in ("1", "true", "yes", "y")


def _validate_row(row: CsvRow, lookups) -> None:
    f = row.fields
    if not row.sku:
        row.errors.append({"row": row.line, "column": "sku", "message": "sku is required"})

    if not f.get("name"):
        row.errors.append({"row": row.line, "column": "name", "message": "name is required"})

    uom = f.get("uom_code")
    if not uom:
        row.errors.append({"row": row.line, "column": "uom_code", "message": "uom_code is required"})
    elif uom not in lookups["uoms"]:
        row.errors.append({
            "row": row.line, "column": "uom_code",
            "message": f"unknown uom_code '{uom}'",
        })

    sp, err = _coerce_decimal(f.get("sale_price"), "sale_price")
    if err:
        row.errors.append({"row": row.line, "column": "sale_price", "message": err})
    elif sp is None:
        row.errors.append({"row": row.line, "column": "sale_price", "message": "sale_price is required"})

    for fname in ("cost_price", "retail_price", "min_sale_price",
                  "max_discount_pct", "reorder_level"):
        if f.get(fname):
            _, err = _coerce_decimal(f[fname], fname)
            if err:
                row.errors.append({"row": row.line, "column": fname, "message": err})

    if (cat := f.get("category")) and cat not in lookups["categories_by_name"] \
            and cat not in lookups["categories_by_slug"]:
        row.errors.append({
            "row": row.line, "column": "category",
            "message": f"unknown category '{cat}' (match by name or slug)",
        })

    if (hs := f.get("hs_code")) and hs not in lookups["hs_codes"]:
        row.errors.append({
            "row": row.line, "column": "hs_code",
            "message": f"unknown hs_code '{hs}'",
        })

    if (tax := f.get("tax_rate")) and tax not in lookups["tax_rates_by_name"]:
        row.errors.append({
            "row": row.line, "column": "tax_rate",
            "message": f"unknown tax_rate name '{tax}'",
        })


def _build_lookups(tenant_id):
    return {
        "uoms": set(UnitOfMeasure.objects.values_list("code", flat=True)),
        "hs_codes": set(HsCode.objects.values_list("code", flat=True)),
        "categories_by_name": {
            c.name: c for c in Category.objects.filter(tenant_id=tenant_id)
        },
        "categories_by_slug": {
            c.slug: c for c in Category.objects.filter(tenant_id=tenant_id)
        },
        "tax_rates_by_name": {
            t.name: t for t in TaxRate.objects.filter(tenant_id=tenant_id)
        },
        "existing_skus": set(
            Product.objects.filter(tenant_id=tenant_id).values_list("sku", flat=True)
        ),
    }


def build_dry_run_summary(*, tenant_id, rows: Iterable[CsvRow], parse_errors: list[dict]) -> dict:
    rows = list(rows)
    lookups = _build_lookups(tenant_id)

    seen_skus_in_batch: set[str] = set()
    new_count = updated_count = 0
    errors: list[dict] = list(parse_errors)

    for row in rows:
        _validate_row(row, lookups)

        if row.sku and row.sku in seen_skus_in_batch:
            row.errors.append({
                "row": row.line, "column": "sku",
                "message": f"duplicate sku '{row.sku}' inside this CSV",
            })
        seen_skus_in_batch.add(row.sku)

        if row.errors:
            errors.extend(row.errors)
            continue

        if row.sku in lookups["existing_skus"]:
            updated_count += 1
        else:
            new_count += 1

    return {
        "counts": {
            "new": new_count,
            "updated": updated_count,
            "errored": sum(1 for r in rows if r.errors) + (1 if parse_errors else 0),
            "total_rows": len(rows),
        },
        "errors": errors,
    }


@transaction.atomic
def commit_import(*, tenant_id, user, rows: list[CsvRow]) -> dict:
    lookups = _build_lookups(tenant_id)

    new_products: list[Product] = []
    updates: list[tuple[Product, dict]] = []

    for row in rows:
        _validate_row(row, lookups)
        if row.errors:
            continue

        f = row.fields
        category = lookups["categories_by_name"].get(f.get("category", "")) \
            or lookups["categories_by_slug"].get(f.get("category", ""))
        tax_rate = lookups["tax_rates_by_name"].get(f.get("tax_rate", ""))

        defaults = dict(
            tenant_id=tenant_id,
            name=f["name"],
            name_ur=f.get("name_ur", ""),
            description=f.get("description", ""),
            barcode=f.get("barcode") or None,
            uom_id=f["uom_code"],
            hs_code_id=f.get("hs_code") or None,
            tax_rate=tax_rate,
            category=category,
            is_taxable=_coerce_bool(f.get("is_taxable", "true")),
            is_active=_coerce_bool(f.get("is_active", "true")),
            cost_price=Decimal(f.get("cost_price") or "0"),
            sale_price=Decimal(f["sale_price"]),
            retail_price=Decimal(f["retail_price"]) if f.get("retail_price") else None,
            min_sale_price=Decimal(f["min_sale_price"]) if f.get("min_sale_price") else None,
            max_discount_pct=Decimal(f["max_discount_pct"]) if f.get("max_discount_pct") else None,
            reorder_level=Decimal(f["reorder_level"]) if f.get("reorder_level") else None,
        )

        existing = Product.objects.filter(tenant_id=tenant_id, sku=row.sku).first()
        if existing:
            updates.append((existing, defaults))
        else:
            defaults["sku"] = row.sku
            defaults["created_by"] = user
            new_products.append(Product(**defaults))

    if new_products:
        Product.objects.bulk_create(new_products)

    for prod, defaults in updates:
        for k, v in defaults.items():
            if k == "tenant_id":
                continue
            setattr(prod, k, v)
    if updates:
        Product.objects.bulk_update(
            [p for p, _ in updates],
            fields=[
                "name", "name_ur", "description", "barcode",
                "uom", "hs_code", "tax_rate", "category",
                "is_taxable", "is_active",
                "cost_price", "sale_price", "retail_price",
                "min_sale_price", "max_discount_pct", "reorder_level",
            ],
        )

    return {
        "created": len(new_products),
        "updated": len(updates),
    }
