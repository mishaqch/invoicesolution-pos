"""Customers API."""

from __future__ import annotations

import csv
import io

from rest_framework import filters, mixins, status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasModule, HasRolePerm, IsTenantMember

_CUSTOMERS_GATE = HasModule.for_module("customers")

from .models import Customer, CustomerGroup, CustomerLedger
from .serializers import (
    CustomerGroupSerializer,
    CustomerLedgerSerializer,
    CustomerSerializer,
)


class _TenantQuerySetMixin:
    def get_queryset(self):  # type: ignore[override]
        qs = super().get_queryset()  # type: ignore[misc]
        tenant_id = getattr(self.request, "tenant_id", None)
        if tenant_id is None:
            return qs.none()
        return qs.filter(tenant_id=tenant_id)


class CustomerGroupViewSet(_TenantQuerySetMixin, viewsets.ModelViewSet):
    queryset = CustomerGroup.objects.all().order_by("name")
    serializer_class = CustomerGroupSerializer
    permission_classes = [
        _CUSTOMERS_GATE,
        HasRolePerm.with_perm("settings.business_profile"),
    ]

    def perform_create(self, serializer):
        serializer.save(tenant_id=self.request.tenant_id)


class CustomerViewSet(_TenantQuerySetMixin, viewsets.ModelViewSet):
    queryset = Customer.objects.filter(deleted_at__isnull=True).order_by("name")
    serializer_class = CustomerSerializer
    permission_classes = [_CUSTOMERS_GATE, IsTenantMember]   # cashier needs read
    filter_backends = [filters.SearchFilter]
    search_fields = ["name", "phone", "cnic", "ntn"]

    def perform_create(self, serializer):
        serializer.save(tenant_id=self.request.tenant_id)

    def perform_destroy(self, instance):
        from django.utils import timezone
        instance.deleted_at = timezone.now()
        instance.is_active = False
        instance.save(update_fields=["deleted_at", "is_active", "updated_at"])


class CustomerLedgerViewSet(
    _TenantQuerySetMixin, mixins.ListModelMixin, viewsets.GenericViewSet,
):
    queryset = CustomerLedger.objects.select_related("customer").order_by("-created_at")
    serializer_class = CustomerLedgerSerializer
    permission_classes = [_CUSTOMERS_GATE, IsTenantMember]

    def get_queryset(self):
        qs = super().get_queryset()
        if (c := self.request.query_params.get("customer")):
            qs = qs.filter(customer_id=c)
        return qs


# ---------------------------------------------------------------------------
# CSV import — bulk-add buyers for Digital Invoicing tenants.
# ---------------------------------------------------------------------------

# Columns accepted in the CSV header (case-insensitive). Order doesn't
# matter; missing columns become empty strings. `name` is the only
# required field.
_CSV_FIELDS = (
    "name", "phone", "email", "ntn", "cnic", "address", "province",
    "registration_type",
)

# Wire values for registration_type. The serializer/model is more
# permissive; we want to keep CSV inputs aligned with the FBR-spec
# Registered/Unregistered framing.
_VALID_REG_TYPES = ("registered", "unregistered")

# Province values that match the Tenant.PROVINCES enum. We don't
# enforce; just normalize common variants.
_PROVINCE_ALIASES = {
    "punjab": "PUNJAB",
    "sindh": "SINDH",
    "kpk": "KP", "kp": "KP",
    "khyber pakhtunkhwa": "KP",
    "balochistan": "BALOCHISTAN", "blochistan": "BALOCHISTAN",
    "ict": "ICT", "islamabad": "ICT",
    "gb": "GB", "gilgit": "GB",
    "ajk": "AJK", "azad kashmir": "AJK",
}


def _parse_csv(file_bytes: bytes) -> tuple[list[dict], list[str]]:
    """Parse the uploaded CSV and return (rows, errors). Each row is
    a dict keyed by the canonical column names in _CSV_FIELDS plus a
    `_row_no` for human-friendly error reporting."""
    errors: list[str] = []
    try:
        text = file_bytes.decode("utf-8-sig")  # Excel adds a BOM
    except UnicodeDecodeError:
        try:
            text = file_bytes.decode("latin-1")
        except Exception:
            errors.append("Could not decode CSV file. Save as UTF-8 and retry.")
            return [], errors

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        errors.append("CSV is empty or has no header row.")
        return [], errors

    # Normalize header names: lower + strip + spaces->underscores.
    header_map: dict[str, str] = {}
    for raw in reader.fieldnames:
        key = (raw or "").strip().lower().replace(" ", "_")
        if key in _CSV_FIELDS:
            header_map[raw] = key
    if "name" not in header_map.values():
        errors.append(
            "CSV must include a 'name' column. Accepted columns: "
            + ", ".join(_CSV_FIELDS)
        )
        return [], errors

    rows: list[dict] = []
    for row_no, raw_row in enumerate(reader, start=2):  # 1 = header
        row: dict[str, str] = {k: "" for k in _CSV_FIELDS}
        for csv_key, canon_key in header_map.items():
            row[canon_key] = (raw_row.get(csv_key) or "").strip()
        if not row["name"]:
            errors.append(f"Row {row_no}: name is required; skipped.")
            continue
        # Normalize registration_type.
        rt = row["registration_type"].lower()
        if rt and rt not in _VALID_REG_TYPES:
            errors.append(
                f"Row {row_no}: registration_type must be 'registered' or "
                f"'unregistered' (got {rt!r}). Treated as 'unregistered'."
            )
            rt = "unregistered"
        row["registration_type"] = rt or "unregistered"
        # Province alias.
        prov_raw = row["province"].lower()
        if prov_raw and prov_raw in _PROVINCE_ALIASES:
            row["province"] = _PROVINCE_ALIASES[prov_raw]
        elif prov_raw:
            # Pass through uppercased; the column accepts free text
            # but the Tenant enum is the safe set.
            row["province"] = row["province"].upper()
        # NTN / CNIC sanity: digits-only, max 15 chars.
        for k in ("ntn", "cnic"):
            row[k] = "".join(ch for ch in row[k] if ch.isdigit())[:15]
        row["_row_no"] = row_no
        rows.append(row)

    return rows, errors


class CustomerImportView(APIView):
    """CSV import — bulk add buyers.

    POST /api/customers/import/  multipart/form-data
        file=<csv>                 (required)
        dry_run=true               (optional, default true)

    Returns:
        { rows_total, rows_valid, rows_skipped, errors[], preview[],
          created, updated, would_create, would_update }

    Dry-run validates + returns a preview without writing. Commit mode
    creates/updates by (tenant, ntn-or-name) — same NTN means same
    buyer.
    """
    permission_classes = [_CUSTOMERS_GATE, IsAuthenticated]

    def post(self, request):
        f = request.FILES.get("file")
        if not f:
            return Response(
                {"detail": "file is required (multipart/form-data)."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        dry_run = str(request.data.get("dry_run", "true")).lower() != "false"

        rows, errors = _parse_csv(f.read())
        if not rows and errors:
            return Response(
                {"rows_total": 0, "rows_valid": 0, "rows_skipped": 0,
                 "errors": errors, "preview": [],
                 "would_create": 0, "would_update": 0,
                 "created": 0, "updated": 0},
                status=status.HTTP_400_BAD_REQUEST,
            )

        tenant_id = request.tenant_id

        # Dedupe key: NTN if present, else (lower name + phone) so two
        # buyers named "M. Ali" don't collapse into one.
        would_create = 0
        would_update = 0
        preview: list[dict] = []
        for row in rows:
            existing = None
            if row["ntn"]:
                existing = Customer.objects.filter(
                    tenant_id=tenant_id, ntn=row["ntn"],
                    deleted_at__isnull=True,
                ).first()
            if existing is None:
                existing = Customer.objects.filter(
                    tenant_id=tenant_id, name__iexact=row["name"],
                    phone=row["phone"],
                    deleted_at__isnull=True,
                ).first()
            preview.append({
                "row_no": row["_row_no"],
                "name": row["name"],
                "ntn": row["ntn"] or None,
                "phone": row["phone"] or None,
                "action": "update" if existing else "create",
            })
            if existing:
                would_update += 1
            else:
                would_create += 1

        result = {
            "rows_total": len(rows),
            "rows_valid": len(rows),
            "rows_skipped": len([e for e in errors if "skipped" in e]),
            "errors": errors,
            "preview": preview,
            "would_create": would_create,
            "would_update": would_update,
            "created": 0,
            "updated": 0,
        }

        if dry_run:
            return Response(result)

        # Commit pass — mirror the preview logic but actually write.
        created = updated = 0
        for row in rows:
            defaults = {
                "name": row["name"],
                "phone": row["phone"] or None,
                "email": row["email"] or None,
                "cnic": row["cnic"] or None,
                "address": row["address"] or "",
                "province": row["province"] or None,
                "registration_type": row["registration_type"],
            }
            if row["ntn"]:
                obj, was_created = Customer.objects.update_or_create(
                    tenant_id=tenant_id, ntn=row["ntn"],
                    deleted_at__isnull=True,
                    defaults={**defaults, "ntn": row["ntn"]},
                )
            else:
                obj, was_created = Customer.objects.update_or_create(
                    tenant_id=tenant_id, name__iexact=row["name"],
                    phone=row["phone"] or None,
                    deleted_at__isnull=True,
                    defaults=defaults,
                )
            if was_created:
                created += 1
            else:
                updated += 1

        result["created"] = created
        result["updated"] = updated
        return Response(result, status=status.HTTP_201_CREATED)
