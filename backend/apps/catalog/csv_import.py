"""Product CSV / Excel import: parse → dry-run preview → commit.

Accepts BOTH CSV and Excel (.xlsx):
  - CSV: UTF-8 with optional BOM, LF or CRLF, quoted fields.
  - Excel: first worksheet, row 1 = headers (openpyxl, read-only).

Smart + forgiving header + value handling (never guesses tax/price VALUES):
  - Headers are normalised: lower-cased, spaces/dashes → underscores, and a set
    of common aliases mapped (e.g. "price" → sale_price, "unit" → uom_code).
  - Values are trimmed; numbers tolerate thousands separators and a leading
    "Rs"/"PKR"; booleans accept yes/no/true/false/1/0.
  - tax_rate accepts a name ("Standard 18%") OR a percentage ("18%", "18") that
    is matched to a configured TaxRate by its numeric rate — it is NEVER invented.
  - Missing CATEGORIES are auto-created on commit; uom/hs_code/tax_rate must
    pre-exist (tax-critical) and produce a clear row error otherwise.

SKU is the natural key for upsert. Match by SKU within tenant.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from io import BytesIO, StringIO
from typing import Iterable

from django.db import transaction
from django.utils.text import slugify

from .models import Category, HsCode, Product, TaxRate, UnitOfMeasure

REQUIRED = {"sku", "name", "uom_code", "sale_price"}
OPTIONAL = {
    "barcode", "name_ur", "description", "category", "hs_code",
    "tax_rate", "cost_price", "retail_price", "min_sale_price",
    "max_discount_pct", "reorder_level", "is_active", "is_taxable",
}
ALL_FIELDS = REQUIRED | OPTIONAL

# Common header aliases → canonical field. Keys are already normalised
# (lower-cased, non-alphanumerics collapsed to "_"). Lets a client's natural
# spreadsheet headers ("Product Name", "Sale Price", "Unit") import cleanly.
HEADER_ALIASES = {
    "product_name": "name", "item_name": "name", "title": "name",
    "urdu_name": "name_ur", "name_urdu": "name_ur",
    "price": "sale_price", "sales_price": "sale_price", "selling_price": "sale_price",
    "rate": "sale_price", "mrp": "retail_price",
    "cost": "cost_price", "purchase_price": "cost_price", "buy_price": "cost_price",
    "unit": "uom_code", "uom": "uom_code", "unit_of_measure": "uom_code",
    "code": "sku", "product_code": "sku", "item_code": "sku",
    "bar_code": "barcode", "ean": "barcode", "upc": "barcode",
    "category_name": "category", "group": "category",
    "hs": "hs_code", "hscode": "hs_code",
    "tax": "tax_rate", "gst": "tax_rate", "sales_tax": "tax_rate",
    "active": "is_active", "taxable": "is_taxable",
    "reorder": "reorder_level", "reorder_point": "reorder_level",
    "min_price": "min_sale_price", "max_discount": "max_discount_pct",
}


def _normalise_header(h: str) -> str:
    """lower-case, collapse spaces/dashes/dots to underscore, map aliases."""
    key = "_".join("".join(ch if ch.isalnum() else " " for ch in str(h)).split()).lower()
    if key in ALL_FIELDS:
        return key
    return HEADER_ALIASES.get(key, key)


@dataclass
class CsvRow:
    line: int
    sku: str
    fields: dict
    errors: list[dict] = field(default_factory=list)


def _read_records(file_obj) -> tuple[list[str], list[dict]]:
    """Return (raw_headers, list-of-row-dicts) from CSV or Excel.

    Detects Excel by the .xlsx magic bytes (a ZIP header "PK\\x03\\x04") so a
    mislabelled file still parses. Everything else is treated as CSV.
    """
    raw = file_obj.read()
    name = (getattr(file_obj, "name", "") or "").lower()
    is_xlsx = name.endswith(".xlsx") or (isinstance(raw, bytes) and raw[:4] == b"PK\x03\x04")

    if is_xlsx:
        import openpyxl  # installed (see pyproject); Excel path only

        wb = openpyxl.load_workbook(BytesIO(raw), read_only=True, data_only=True)
        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        try:
            header_row = next(rows_iter)
        except StopIteration:
            return [], []
        headers = [("" if h is None else str(h)) for h in header_row]
        records: list[dict] = []
        for values in rows_iter:
            if values is None or all(v is None or str(v).strip() == "" for v in values):
                continue  # skip fully-blank rows
            rec = {}
            for i, h in enumerate(headers):
                v = values[i] if i < len(values) else None
                rec[h] = "" if v is None else str(v)
            records.append(rec)
        return headers, records

    # CSV path
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8-sig")
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    # Drop leading "#" comment/guide lines (our downloadable template carries a
    # short guide block) and blank lines before the header so an unedited
    # template still imports.
    lines = text.split("\n")
    while lines and (lines[0].strip() == "" or lines[0].lstrip().startswith("#")):
        lines.pop(0)
    text = "\n".join(lines)
    reader = csv.DictReader(StringIO(text))
    headers = list(reader.fieldnames or [])
    return headers, list(reader)


def parse_csv(file_obj) -> tuple[list[CsvRow], list[dict]]:
    """Read a CSV or Excel file. Returns (rows, parse_errors)."""
    raw_headers, records = _read_records(file_obj)

    # Normalise headers (case-insensitive + aliases) and remember the mapping so
    # each record's values land under canonical field names.
    header_map = {h: _normalise_header(h) for h in raw_headers}
    canonical = set(header_map.values())
    parse_errors: list[dict] = []

    missing = REQUIRED - canonical
    if missing:
        parse_errors.append({
            "row": 0,
            "column": ", ".join(sorted(missing)),
            "message": (
                f"Missing required column(s): {', '.join(sorted(missing))}. "
                "Download the template for the exact format."
            ),
        })
        return [], parse_errors

    unknown = canonical - ALL_FIELDS
    if unknown:
        parse_errors.append({
            "row": 0,
            "column": ", ".join(sorted(unknown)),
            "message": (
                f"Unrecognised column(s) ignored: {', '.join(sorted(unknown))}. "
                "See the template for supported columns."
            ),
        })

    rows: list[CsvRow] = []
    for line_no, raw_row in enumerate(records, start=2):  # row 1 = header
        fields = {}
        for raw_key, value in raw_row.items():
            canon = header_map.get(raw_key, _normalise_header(raw_key))
            if canon in ALL_FIELDS:
                fields[canon] = value.strip() if isinstance(value, str) else value
        sku = (fields.get("sku") or "").strip()
        rows.append(CsvRow(line=line_no, sku=sku, fields=fields))
    return rows, parse_errors


def _clean_number(value) -> str:
    """Strip currency symbols, thousands separators and a trailing % so common
    spreadsheet formats ("Rs 1,250.00", "18%") parse. VALUE is not invented —
    only cleaned."""
    s = str(value).strip()
    low = s.lower()
    # Remove currency prefixes case-insensitively (operate on the original via
    # the lower-cased view length).
    for token in ("rs.", "pkr", "rs", "₨"):
        if low.startswith(token):
            s = s[len(token):]
            break
    return s.replace(",", "").replace("%", "").strip()


def _coerce_decimal(value, field_name: str) -> tuple[Decimal | None, str | None]:
    if value is None or str(value).strip() == "":
        return None, None
    try:
        return Decimal(_clean_number(value)), None
    except (InvalidOperation, ValueError):
        return None, f"Not a valid number in {field_name}: {value!r}"


def _coerce_bool(value) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "y", "on")


def _match_tax_rate(value, lookups):
    """Resolve a tax_rate cell to a configured TaxRate.

    Accepts either the exact NAME ("Standard 18%") or a PERCENTAGE ("18%", "18",
    "18.00") matched to a TaxRate by its numeric `rate`. Returns (TaxRate|None,
    matched?). We never CREATE a tax rate — an unmatched value is a row error so
    tax is never silently wrong.
    """
    raw = str(value).strip()
    if not raw:
        return None, True  # blank = no tax rate, that's fine
    if raw in lookups["tax_rates_by_name"]:
        return lookups["tax_rates_by_name"][raw], True
    # Try as a percentage → match by numeric rate.
    try:
        pct = Decimal(_clean_number(raw))
    except (InvalidOperation, ValueError):
        return None, False
    return lookups["tax_rates_by_rate"].get(pct, None), pct in lookups["tax_rates_by_rate"]


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

    # category: no error — a missing category is AUTO-CREATED on commit.

    if (hs := f.get("hs_code")) and hs not in lookups["hs_codes"]:
        row.errors.append({
            "row": row.line, "column": "hs_code",
            "message": f"unknown hs_code '{hs}' — add it under HS codes first",
        })

    # tax_rate: accept a name or a percentage; must match a CONFIGURED rate.
    if f.get("tax_rate"):
        _, matched = _match_tax_rate(f["tax_rate"], lookups)
        if not matched:
            row.errors.append({
                "row": row.line, "column": "tax_rate",
                "message": (
                    f"unknown tax_rate '{f['tax_rate']}' — use a configured tax "
                    "rate name or percentage (e.g. 18%)"
                ),
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
        # Also index tax rates by their numeric percentage so "18%"/"18" match.
        "tax_rates_by_rate": {
            t.rate: t for t in TaxRate.objects.filter(tenant_id=tenant_id)
        },
        "existing_skus": set(
            Product.objects.filter(tenant_id=tenant_id).values_list("sku", flat=True)
        ),
    }


def _unique_category_slug(tenant_id, name: str) -> str:
    """A tenant-unique slug for an auto-created category."""
    base = slugify(name) or "category"
    slug = base
    n = 2
    existing = set(
        Category.objects.filter(tenant_id=tenant_id, slug__startswith=base)
        .values_list("slug", flat=True)
    )
    while slug in existing:
        slug = f"{base}-{n}"
        n += 1
    return slug


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
    created_categories: list[str] = []

    for row in rows:
        _validate_row(row, lookups)
        if row.errors:
            continue

        f = row.fields
        # Category: match by name/slug, else AUTO-CREATE it (and cache so later
        # rows referencing the same new category reuse it).
        cat_name = (f.get("category") or "").strip()
        category = None
        if cat_name:
            category = lookups["categories_by_name"].get(cat_name) \
                or lookups["categories_by_slug"].get(cat_name)
            if category is None:
                category = Category.objects.create(
                    tenant_id=tenant_id, name=cat_name,
                    slug=_unique_category_slug(tenant_id, cat_name),
                )
                lookups["categories_by_name"][category.name] = category
                lookups["categories_by_slug"][category.slug] = category
                created_categories.append(cat_name)
        # Tax rate: resolve name or percentage to a CONFIGURED rate (never made).
        tax_rate, _ = _match_tax_rate(f.get("tax_rate", ""), lookups)

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
            # Use _clean_number so "Rs 1,250.00" / "18%"-style cells parse the
            # same way they validated in the dry-run.
            cost_price=Decimal(_clean_number(f.get("cost_price") or "0")),
            sale_price=Decimal(_clean_number(f["sale_price"])),
            retail_price=Decimal(_clean_number(f["retail_price"])) if f.get("retail_price") else None,
            min_sale_price=Decimal(_clean_number(f["min_sale_price"])) if f.get("min_sale_price") else None,
            max_discount_pct=Decimal(_clean_number(f["max_discount_pct"])) if f.get("max_discount_pct") else None,
            reorder_level=Decimal(_clean_number(f["reorder_level"])) if f.get("reorder_level") else None,
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
        "categories_created": sorted(set(created_categories)),
    }
