"""Sync ingestion services.

Idempotency pattern (DB-constraint-driven):

    try:
        sync_row = SyncLog.objects.create(client_uuid=..., status="received")
    except IntegrityError:
        existing = SyncLog.objects.get(client_uuid=...)
        return _replay(existing)

    process(payload)
    sync_row.mark_processed(entity_id)

The UNIQUE constraint on sync_log.client_uuid is the truth. If two parallel
POSTs arrive for the same client_uuid, exactly one wins the insert race; the
other gets IntegrityError and replays.

Conflict resolution per entity:
  - invoice: never conflicts (pure inserts; client_uuid de-dupes).
  - customer: field-level merge by updated_at.
  - stock_adjustment: append-only; every attempt logs a movement.
"""

from __future__ import annotations

import datetime as dt
import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

from django.db import IntegrityError, transaction
from django.utils.dateparse import parse_datetime

from apps.audit.services import log as audit_log
from apps.customers.models import Customer
from apps.notifications.services import maybe_email_sync_failures, notify
from apps.sales.services import checkout
from apps.tenants.models import Branch, CashSession, Terminal

from .models import SyncLog

logger = logging.getLogger(__name__)


class IngestResult:
    """Outcome of an ingest call.

    `failed=True` means the sync_log row was committed with status='failed'.
    The view should respond 400 to the client; we do NOT raise out of the
    service, because that would let ATOMIC_REQUESTS roll back the row we
    just persisted (which the admin needs to see + retry).
    """
    def __init__(
        self,
        *,
        entity_id: UUID | str | None,
        sync_log: SyncLog,
        was_duplicate: bool,
        failed: bool = False,
        error: str | None = None,
    ):
        self.entity_id = entity_id
        self.sync_log = sync_log
        self.was_duplicate = was_duplicate
        self.failed = failed
        self.error = error


def ingest_invoice(*, tenant_id, terminal_id, payload: dict, request=None) -> IngestResult:
    client_uuid = payload["client_uuid"]

    try:
        with transaction.atomic():
            sync_row = SyncLog.objects.create(
                tenant_id=tenant_id,
                terminal_id=terminal_id,
                client_uuid=client_uuid,
                entity_type="invoice",
                action="create",
                payload=payload,
                status="received",
            )
    except IntegrityError:
        # A SyncLog already exists for this client_uuid. Three sub-cases:
        existing = SyncLog.objects.get(client_uuid=client_uuid)
        if existing.entity_id is not None:
            # Previous attempt succeeded — true idempotent replay.
            # Server is the source of truth; return the existing row id.
            return IngestResult(
                entity_id=existing.entity_id,
                sync_log=existing,
                was_duplicate=True,
            )
        if existing.status == "failed":
            # Previous attempt failed before creating an Invoice. The
            # caller has presumably fixed whatever was broken (catalog
            # drift, missing branch, …). Discard the failed log row
            # and fall through to a fresh attempt instead of returning
            # entity_id=None (which used to crash the view with
            # `Invoice.objects.get(pk=None)`).
            existing.delete()
            sync_row = SyncLog.objects.create(
                tenant_id=tenant_id,
                terminal_id=terminal_id,
                client_uuid=client_uuid,
                entity_type="invoice",
                action="create",
                payload=payload,
                status="received",
            )
        else:
            # 'received' / 'processing' — a parallel POST is mid-flight.
            # Refuse and let the client retry; we don't want two workers
            # racing to create the same invoice.
            return IngestResult(
                entity_id=None,
                sync_log=existing,
                was_duplicate=False,
                failed=True,
                error=(
                    f"Another ingest is already in flight for "
                    f"client_uuid={client_uuid} (status={existing.status}). "
                    "Retry shortly."
                ),
            )

    # Use a savepoint so a failure here doesn't roll back the sync_row.
    sid = transaction.savepoint()
    try:
        invoice = _create_invoice_from_payload(
            tenant_id=tenant_id,
            terminal_id=terminal_id,
            payload=payload,
            request=request,
        )
    except Exception as exc:  # validation or DB error
        transaction.savepoint_rollback(sid)
        logger.exception("ingest_invoice failed for %s", client_uuid)
        sync_row.mark_failed(str(exc))
        _on_failure(sync_row)
        return IngestResult(
            entity_id=None,
            sync_log=sync_row,
            was_duplicate=False,
            failed=True,
            error=str(exc),
        )
    transaction.savepoint_commit(sid)

    sync_row.mark_processed(invoice.id)

    # Phase 4 — kick off FBR submission asynchronously. If the tenant has
    # no token yet (still onboarding), the task no-ops cleanly.
    try:
        from apps.fbr.tasks import submit_invoice_to_fbr
        submit_invoice_to_fbr.delay(str(invoice.id))
    except Exception:  # never let task enqueue failure break ingestion
        logger.exception("failed to enqueue FBR submission for %s", invoice.id)

    return IngestResult(entity_id=invoice.id, sync_log=sync_row, was_duplicate=False)


def ingest_customer(*, tenant_id, terminal_id, payload: dict) -> IngestResult:
    """Customer create-or-merge.

    First insert with a given client_uuid creates the row; subsequent
    payloads with the same client_uuid replay the create response.

    Updates use field-level merge by `updated_at`: if the incoming payload's
    updated_at is older than the row's updated_at, the field is kept.
    """
    client_uuid = payload["client_uuid"]
    op = payload.get("op", "create")  # 'create' or 'update'

    try:
        with transaction.atomic():
            sync_row = SyncLog.objects.create(
                tenant_id=tenant_id,
                terminal_id=terminal_id,
                client_uuid=client_uuid,
                entity_type="customer",
                action=op,
                payload=payload,
                status="received",
            )
    except IntegrityError:
        existing = SyncLog.objects.get(client_uuid=client_uuid)
        return IngestResult(
            entity_id=existing.entity_id,
            sync_log=existing,
            was_duplicate=True,
        )

    sid = transaction.savepoint()
    try:
        customer_id = _upsert_customer_from_payload(
            tenant_id=tenant_id, payload=payload,
        )
    except Exception as exc:
        transaction.savepoint_rollback(sid)
        logger.exception("ingest_customer failed for %s", client_uuid)
        sync_row.mark_failed(str(exc))
        _on_failure(sync_row)
        return IngestResult(
            entity_id=None, sync_log=sync_row,
            was_duplicate=False, failed=True, error=str(exc),
        )
    transaction.savepoint_commit(sid)

    sync_row.mark_processed(customer_id)
    return IngestResult(entity_id=customer_id, sync_log=sync_row, was_duplicate=False)


def retry_failed(sync_row: SyncLog, *, request=None) -> IngestResult:
    if sync_row.status != "failed":
        raise ValueError(f"sync_log {sync_row.id} is not failed (status={sync_row.status})")

    payload = sync_row.payload
    if sync_row.entity_type == "invoice":
        try:
            invoice = _create_invoice_from_payload(
                tenant_id=sync_row.tenant_id,
                terminal_id=sync_row.terminal_id,
                payload=payload,
                request=request,
            )
        except Exception as exc:
            sync_row.error_message = str(exc)
            sync_row.save(update_fields=["error_message", "updated_at"])
            raise
        sync_row.mark_processed(invoice.id)
        return IngestResult(entity_id=invoice.id, sync_log=sync_row, was_duplicate=False)

    if sync_row.entity_type == "customer":
        try:
            cid = _upsert_customer_from_payload(
                tenant_id=sync_row.tenant_id, payload=payload,
            )
        except Exception as exc:
            sync_row.error_message = str(exc)
            sync_row.save(update_fields=["error_message", "updated_at"])
            raise
        sync_row.mark_processed(cid)
        return IngestResult(entity_id=cid, sync_log=sync_row, was_duplicate=False)

    raise ValueError(f"Unknown entity_type {sync_row.entity_type}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_invoice_from_payload(*, tenant_id, terminal_id, payload, request=None):
    """Translate the POS sync payload into a checkout.create_invoice call."""
    branch = Branch.objects.for_tenant(tenant_id).get(pk=payload["branch"])
    terminal = Terminal.objects.for_tenant(tenant_id).get(pk=terminal_id)

    cashier_id = payload["cashier"]
    from django.contrib.auth import get_user_model
    cashier = get_user_model().objects.get(pk=cashier_id)

    cash_session = (
        CashSession.objects.for_tenant(tenant_id).filter(
            pk=payload.get("cash_session"),
        ).first()
        if payload.get("cash_session") else None
    )

    customer = (
        Customer.objects.for_tenant(tenant_id).filter(
            pk=payload.get("customer"),
        ).first()
        if payload.get("customer") else None
    )

    invoice = checkout.create_invoice(
        tenant_id=tenant_id,
        branch=branch,
        terminal=terminal,
        cashier=cashier,
        cash_session=cash_session,
        customer=customer,
        cart_lines=[
            {
                "product": line["product"],
                "variant": line.get("variant"),
                "batch": line.get("batch"),
                "quantity": line["quantity"],
                "unit_price": line["unit_price"],
                "discount_pct": line.get("discount_pct", 0),
                "discount_amount": line.get("discount_amount", 0),
                "tax_rate": line.get("tax_rate", 0),
                "is_taxable": line.get("is_taxable", True),
                # Restaurant (ignored for other verticals).
                "modifiers": line.get("modifiers") or [],
                "course": line.get("course"),
                "item_note": line.get("item_note"),
            }
            for line in payload["cart_lines"]
        ],
        # Restaurant order-level fields (None for other verticals).
        order_type=payload.get("order_type"),
        table_id=payload.get("table"),
        covers=payload.get("covers"),
        cart_discount_pct=payload.get("cart_discount_pct", 0),
        # Pass the WHOLE payment dict, not just method+amount — the per-method
        # adapter needs the proof fields (card_last4, cheque_number, …). Card
        # details are mandatory on this POS path (require_card_details defaults
        # to True): the cashier had the physical slip at the till.
        payments=[dict(p) for p in payload["payments"]],
        client_uuid=payload["client_uuid"],
        notes=payload.get("notes"),
        local_invoice_number=payload.get("local_invoice_number"),
        request=request,
    )
    return invoice


def _upsert_customer_from_payload(*, tenant_id, payload: dict) -> UUID:
    """Create-or-merge a customer row by client_uuid.

    Field-level merge is keyed off `updated_at`: incoming fields with an
    `updated_at` older than the row's are silently skipped.
    """
    cid = payload.get("id") or payload["client_uuid"]
    incoming_updated_at = parse_datetime(payload["updated_at"])

    existing = Customer.objects.filter(tenant_id=tenant_id, pk=cid).first()
    if existing is None:
        Customer.objects.create(
            id=cid,
            tenant_id=tenant_id,
            name=payload["name"],
            phone=payload.get("phone"),
            email=payload.get("email"),
            cnic=payload.get("cnic"),
            ntn=payload.get("ntn"),
            registration_type=payload.get("registration_type", "unregistered"),
            province=payload.get("province"),
            address=payload.get("address", ""),
            store_credit=Decimal(str(payload.get("store_credit", "0"))),
        )
        return cid

    if incoming_updated_at and incoming_updated_at < existing.updated_at:
        # Server has newer data; only update conflicts the client clearly knew.
        return existing.id

    # Field-level merge: copy the simple fields when present.
    fields = ("name", "phone", "email", "cnic", "ntn",
              "registration_type", "province", "address")
    changed = []
    for f in fields:
        if f in payload and payload[f] is not None and payload[f] != getattr(existing, f):
            setattr(existing, f, payload[f])
            changed.append(f)
    if changed:
        existing.save(update_fields=changed + ["updated_at"])
    return existing.id


def _on_failure(sync_row: SyncLog) -> None:
    """Side effects when a sync row enters status='failed'."""
    notify(
        tenant_id=sync_row.tenant_id,
        notification_type="sync.failed",
        title=f"Sync failed for {sync_row.entity_type}",
        message=(sync_row.error_message or "Unknown error")[:500],
        severity="danger",
        data={"sync_log_id": str(sync_row.id)},
    )
    if sync_row.tenant_id:
        from apps.tenants.models import Tenant
        tenant = Tenant.objects.filter(pk=sync_row.tenant_id).first()
        if tenant is not None:
            maybe_email_sync_failures(tenant=tenant)
    audit_log(
        tenant_id=sync_row.tenant_id,
        entity_type="sync_log",
        entity_id=sync_row.id,
        action="failed",
        after={"error": sync_row.error_message},
    )
