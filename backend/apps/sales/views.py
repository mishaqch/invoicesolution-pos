"""Sales API.

POST /api/sales/invoices/checkout/      — atomic checkout (create invoice)
GET  /api/sales/invoices/               — list (filterable)
GET  /api/sales/invoices/<id>/          — detail
POST /api/sales/invoices/<id>/hold/     — flip is_held + label
POST /api/sales/invoices/<id>/recall/   — flip is_held off
POST /api/sales/invoices/<id>/cancel/   — manual cancel (manager+; Phase 4 enforces FBR rules)

POST /api/sales/cash-sessions/open/
POST /api/sales/cash-sessions/<id>/close/
GET  /api/sales/cash-sessions/<id>/x-report/  — running totals for the open or recently closed session
"""

from __future__ import annotations

from django.core.exceptions import ValidationError as DjValidationError
from rest_framework import filters, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from apps.accounts.permissions import HasRolePerm, IsTenantMember
from apps.customers.models import Customer
from apps.tenants.models import Branch, CashSession, Terminal

from .models import Invoice
from .serializers import (
    CancelSerializer,
    CheckoutSerializer,
    EditItemSerializer,
    HoldSerializer,
    InvoiceSerializer,
    SessionCloseSerializer,
    SessionOpenSerializer,
)
from .services import cancellation, checkout, holds, sessions


def _dj_error_message(exc: DjValidationError) -> str:
    """First human message from a Django ValidationError (for DRF responses)."""
    messages = exc.messages if hasattr(exc, "messages") else [str(exc)]
    return messages[0] if messages else "Validation error."


class _TenantQuerySetMixin:
    def get_queryset(self):  # type: ignore[override]
        qs = super().get_queryset()  # type: ignore[misc]
        tenant_id = getattr(self.request, "tenant_id", None)
        if tenant_id is None:
            return qs.none()
        return qs.filter(tenant_id=tenant_id)


class InvoiceViewSet(
    _TenantQuerySetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    queryset = (
        Invoice.objects
        .select_related("branch", "terminal", "cashier", "customer")
        .prefetch_related("items", "payments")
        .order_by("-invoice_date", "-created_at")
    )
    serializer_class = InvoiceSerializer
    permission_classes = [IsTenantMember]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["invoice_date", "grand_total", "created_at"]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if (b := params.get("branch")):
            qs = qs.filter(branch_id=b)
        if (t := params.get("terminal")):
            qs = qs.filter(terminal_id=t)
        if (c := params.get("cashier")):
            qs = qs.filter(cashier_id=c)
        if (cust := params.get("customer")):
            qs = qs.filter(customer_id=cust)
        if (st := params.get("status")):
            qs = qs.filter(status=st)
        if (start := params.get("from")):
            qs = qs.filter(invoice_date__gte=start)
        if (end := params.get("to")):
            qs = qs.filter(invoice_date__lte=end)
        if (held := params.get("held")):
            qs = qs.filter(is_held=held.lower() in ("1", "true"))
        if (q := params.get("q")):
            # Free-text search the three fields a tenant typically pastes in:
            # the local invoice number from a printed receipt, the FBR
            # invoice number returned by PRAL, or a buyer name.
            from django.db.models import Q
            qs = qs.filter(
                Q(local_invoice_number__icontains=q)
                | Q(fbr_invoice_number__icontains=q)
                | Q(buyer_name__icontains=q),
            )
        return qs

    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        """Aggregate counts for the invoices KPI strip.

        Honours the same `branch`, `from`, `to` filters as list — so
        the KPI tiles match what the table is showing. Returns one
        row per status plus a grand total + total revenue (Decimal).
        """
        from decimal import Decimal

        from django.db.models import Count, Sum

        qs = self.get_queryset()
        rows = (
            qs.values("status")
            .annotate(count=Count("id"), revenue=Sum("grand_total"))
        )
        by_status = {
            r["status"]: {
                "count": r["count"],
                "revenue": str(r["revenue"] or Decimal("0")),
            }
            for r in rows
        }
        totals = qs.aggregate(count=Count("id"), revenue=Sum("grand_total"))
        return Response({
            "by_status": by_status,
            "total_count": totals["count"] or 0,
            "total_revenue": str(totals["revenue"] or Decimal("0")),
        })

    @action(detail=False, methods=["get"], url_path="timeseries")
    def timeseries(self, request):
        """Bucketed invoice counts + revenue for the chart on the
        Dashboard (matches PRAL DI manual page 20–21).

        Query params:
          interval = day | month | quarter | year  (default: day)
          invoice_type = sale | debit_note | credit_note (default: sale)
          from, to: same date filters as `list` and `summary`.

        Returns: { interval, invoice_type, buckets: [{label, count,
        revenue}] } sorted chronologically. Empty buckets are NOT
        padded — the chart should show whatever the DB has.
        """
        from decimal import Decimal

        from django.db.models import Count, Sum
        from django.db.models.functions import (
            TruncDay, TruncMonth, TruncQuarter, TruncYear,
        )

        interval = (request.query_params.get("interval") or "day").lower()
        invoice_type = request.query_params.get("invoice_type") or "sale"

        trunc_map = {
            "day": (TruncDay, "%Y-%m-%d"),
            "month": (TruncMonth, "%Y-%m"),
            "quarter": (TruncQuarter, "%Y-Q%q"),
            "year": (TruncYear, "%Y"),
        }
        if interval not in trunc_map:
            return Response(
                {"detail": (
                    f"interval must be one of {sorted(trunc_map)}; "
                    f"got {interval!r}."
                )},
                status=status.HTTP_400_BAD_REQUEST,
            )

        TruncCls, _label_fmt = trunc_map[interval]

        qs = self.get_queryset().filter(invoice_type=invoice_type)
        rows = (
            qs.annotate(bucket=TruncCls("invoice_date"))
            .values("bucket")
            .annotate(count=Count("id"), revenue=Sum("grand_total"))
            .order_by("bucket")
        )

        def _fmt(bucket) -> str:
            # %q isn't portable across Postgres/SQLite; compute quarter
            # manually for the quarter case.
            if interval == "quarter":
                q = (bucket.month - 1) // 3 + 1
                return f"{bucket.year}-Q{q}"
            return bucket.strftime(trunc_map[interval][1])

        buckets = [
            {
                "label": _fmt(r["bucket"]),
                "count": r["count"],
                "revenue": str(r["revenue"] or Decimal("0")),
            }
            for r in rows
        ]
        return Response({
            "interval": interval,
            "invoice_type": invoice_type,
            "buckets": buckets,
        })

    @action(detail=False, methods=["post"], url_path="checkout",
            permission_classes=[HasRolePerm.with_perm("sales.create")])
    def checkout(self, request):
        """POS terminal checkout — always requires an explicit branch +
        terminal because the cashier is physically ringing up a sale
        on a specific counter. The implicit-default fallback is only
        for the /manual/ office-invoice flow.
        """
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        v = serializer.validated_data
        if not v.get("branch") or not v.get("terminal"):
            return Response(
                {"detail": "branch and terminal are required for POS checkout."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        branch = self._fetch_tenant_object(Branch, v["branch"])
        terminal = self._fetch_tenant_object(Terminal, v["terminal"])
        session = (
            CashSession.objects.for_tenant(request.tenant_id).filter(
                pk=v.get("cash_session"),
            ).first()
            if v.get("cash_session") else None
        )
        customer = (
            Customer.objects.for_tenant(request.tenant_id).filter(
                pk=v.get("customer"),
            ).first()
            if v.get("customer") else None
        )

        try:
            invoice = checkout.create_invoice(
                tenant_id=request.tenant_id,
                branch=branch,
                terminal=terminal,
                cashier=request.user,
                cash_session=session,
                customer=customer,
                cart_lines=[dict(line) for line in v["cart_lines"]],
                cart_discount_pct=v.get("cart_discount_pct", 0),
                payments=[dict(p) for p in v["payments"]],
                client_uuid=v["client_uuid"],
                notes=v.get("notes"),
                request=request,
            )
        except DjValidationError as exc:
            from rest_framework.exceptions import ValidationError as DrfValidationError
            raise DrfValidationError({"detail": _dj_error_message(exc)})
        return Response(
            InvoiceSerializer(invoice).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["post"], url_path="manual",
            permission_classes=[HasRolePerm.with_perm("sales.create")])
    def manual_create(self, request):
        """Create an invoice without going through a POS terminal checkout.

        Two distinct tenant shapes converge on this endpoint:

          A) Cashier-counter tenants WITH the branches/terminals modules
             enabled. They send explicit branch + terminal UUIDs picked
             from dropdowns in the admin web. Same flow as before.

          B) Office-invoice tenants WITHOUT those modules. They omit
             branch/terminal entirely. The server provisions an implicit
             default branch + terminal once per tenant and reuses them
             for every subsequent manual invoice. The tenant never sees
             a "branch" or "terminal" concept anywhere in their UI.

        Also handles debit / credit notes when invoice_type and
        reference_invoice are supplied: same pipeline, different
        invoice_type stored, reference_invoice FK set so the original
        and the note are linked. The buyer block is copied from the
        reference if no explicit customer override is sent.

        After creation, the invoice is queued for FBR submission via the
        existing Celery task (matches the POS flow).
        """
        from apps.fbr.tasks import submit_invoice_to_fbr
        from apps.tenants.implicit import ensure_implicit_branch_and_terminal
        from apps.tenants.models import Tenant

        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        v = serializer.validated_data

        # Branch + terminal resolution. If the body supplies them, look
        # them up; if it doesn't (Shape B office-invoice flow), fall
        # back to the implicit default pair which is created on demand.
        if v.get("branch") and v.get("terminal"):
            branch = self._fetch_tenant_object(Branch, v["branch"])
            terminal = self._fetch_tenant_object(Terminal, v["terminal"])
        else:
            tenant = Tenant.objects.get(pk=request.tenant_id)
            branch, terminal = ensure_implicit_branch_and_terminal(tenant)
        customer = (
            Customer.objects.for_tenant(request.tenant_id).filter(
                pk=v.get("customer"),
            ).first()
            if v.get("customer") else None
        )

        # Resolve + validate the reference invoice (debit/credit note flow).
        # Tenant scoping is enforced through Invoice.objects.for_tenant; we
        # also gate on a state that makes a debit note meaningful: validated
        # or finalized invoices, never cancelled / failed / pending.
        reference = None
        invoice_type = v.get("invoice_type", "sale")
        if v.get("reference_invoice"):
            reference = (
                Invoice.objects.for_tenant(request.tenant_id)
                .filter(pk=v["reference_invoice"])
                .first()
            )
            if reference is None:
                return Response(
                    {"reference_invoice": "Original invoice not found."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if reference.status not in ("valid", "finalized", "edited",
                                        "partially_edited",
                                        "partially_cancelled",
                                        "partially_edited_and_cancelled"):
                return Response(
                    {"reference_invoice":
                        f"Cannot issue {invoice_type} against a "
                        f"{reference.get_status_display()} invoice."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        try:
            invoice = checkout.create_invoice(
                tenant_id=request.tenant_id,
                branch=branch,
                terminal=terminal,
                cashier=request.user,
                cash_session=None,
                customer=customer,
                cart_lines=[dict(line) for line in v["cart_lines"]],
                cart_discount_pct=v.get("cart_discount_pct", 0),
                payments=[dict(p) for p in v["payments"]],
                client_uuid=v["client_uuid"],
                notes=v.get("notes"),
                invoice_type=invoice_type,
                reference_invoice=reference,
                reason=v.get("reason"),
                reason_notes=v.get("reason_notes"),
                request=request,
            )
        except DjValidationError as exc:
            from rest_framework.exceptions import ValidationError as DrfValidationError
            raise DrfValidationError({"detail": _dj_error_message(exc)})
        # NB: deliberately NOT auto-submitting to FBR here. The manual
        # invoice flow lets the operator review the saved invoice on
        # the detail page, optionally run "Validate with FBR" as a free
        # dry-run, and only then click "Submit to FBR" to issue the
        # FBR Invoice Number. The POS terminal `/checkout/` flow still
        # auto-submits because cashiers can't afford a two-step UX at
        # the counter. Office-staff manual invoices are different —
        # they want control over the moment of submission.
        return Response(
            InvoiceSerializer(invoice).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"],
            permission_classes=[HasRolePerm.with_perm("sales.create")])
    def hold(self, request, pk=None):
        invoice = self.get_object()
        body = HoldSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        holds.hold(invoice, label=body.validated_data["label"], user=request.user, request=request)
        return Response(InvoiceSerializer(invoice).data)

    @action(detail=True, methods=["post"],
            permission_classes=[HasRolePerm.with_perm("sales.create")])
    def recall(self, request, pk=None):
        invoice = self.get_object()
        holds.recall(invoice, user=request.user, request=request)
        return Response(InvoiceSerializer(invoice).data)

    @action(detail=True, methods=["post"], url_path="force-cancel",
            permission_classes=[HasRolePerm.with_perm("sales.cancel.threshold_high")])
    def force_cancel(self, request, pk=None):
        """LOCAL-ONLY force-cancel escape hatch — does NOT touch PRAL.

        The compliant, FBR-aware cancel lives at
        `/api/fbr/invoices/<id>/cancel/` (CancelInvoiceFbrView). That
        endpoint consumes the tenant's 10% monthly cancel-budget AND
        calls PRAL's `cancelinvoice` endpoint so the invoice is also
        amended on FBR's side. The React 'Cancel sale' button points
        there.

        This endpoint exists for the rare case where the tenant needs
        to mark an invoice locally cancelled WITHOUT notifying PRAL —
        e.g. an invoice that was created locally, never reached PRAL
        (status='failed' with no fbr_invoice_number) and should be
        removed from the operator's view without ever being submitted.
        Even here, the rules layer still gates pre-validation states
        away from this path; the only realistic caller is offline-mode
        cleanup on terminals.

        Renamed from `cancel` so the URL difference (`force-cancel`
        vs `cancel`) discourages accidental use from the UI.
        """
        invoice = self.get_object()
        body = CancelSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            cancellation.cancel_invoice(
                invoice, reason=body.validated_data["reason"],
                user=request.user, request=request,
            )
        except DjValidationError as exc:
            messages = (
                exc.messages if hasattr(exc, "messages") else [str(exc)]
            )
            return Response(
                {"detail": messages[0] if messages else "Cannot cancel."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        invoice.refresh_from_db()
        return Response(InvoiceSerializer(invoice).data)

    @action(detail=True, methods=["post"], url_path="resubmit",
            permission_classes=[HasRolePerm.with_perm("sales.create")])
    def resubmit(self, request, pk=None):
        """Re-queue a failed invoice for FBR submission.

        Only invoices in `failed` or `pending_sync` status without an
        FBR invoice number are eligible. The Celery task already
        idempotently handles the retry.
        """
        from apps.fbr.services import resubmit_failed_invoice
        invoice = self.get_object()
        try:
            resubmit_failed_invoice(invoice, user=request.user, request=request)
        except Exception as exc:
            from rest_framework.exceptions import ValidationError as DrfValidationError
            if hasattr(exc, "message_dict"):
                return Response(exc.message_dict, status=status.HTTP_400_BAD_REQUEST)
            if isinstance(exc, DrfValidationError):
                return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
            raise
        invoice.refresh_from_db()
        return Response(InvoiceSerializer(invoice).data)

    @action(detail=True, methods=["get"], url_path="fiscal-payload",
            permission_classes=[HasRolePerm.with_perm("sales.create")])
    def fiscal_payload(self, request, pk=None):
        """What the LOCAL SDC needs to fiscalize this invoice.

        Returned to the client app (browser / POS terminal) running on the
        same machine as the branch's FBR SDC. The client POSTs this to
        http://localhost:8524/api/IMSFiscal/... using the branch POS ID, then
        sends the result back via `fiscal-result`. The cloud server never
        contacts the SDC itself (it can't reach a branch's localhost).
        """
        from apps.fbr.sdc_client import build_sdc_payload, SUBMIT_PATH

        invoice = self.get_object()
        pos_id = getattr(invoice.branch, "fbr_pos_id", None)
        already = bool(invoice.fbr_invoice_number)
        body = None
        if not already and pos_id:
            # Real SDC (IMSFiscal) request body — POSTed by the client to the
            # local SDC at http://localhost:8524/api/IMSFiscal/GetInvoiceNumberByModel
            body = build_sdc_payload(invoice=invoice, pos_id=pos_id)
        return Response({
            "invoice_id": str(invoice.id),
            "local_invoice_number": invoice.local_invoice_number,
            "branch_fbr_pos_id": pos_id,
            "already_fiscalized": already,
            "fbr_invoice_number": invoice.fbr_invoice_number,
            # Where the client should POST the body, on its own machine:
            "sdc_submit_path": SUBMIT_PATH,  # /api/IMSFiscal/GetInvoiceNumberByModel
            # The exact SDC request body (null if no POS ID, or already done).
            "sdc_payload": body,
        })

    @action(detail=True, methods=["post"], url_path="fiscal-result",
            permission_classes=[HasRolePerm.with_perm("sales.create")])
    def fiscal_result(self, request, pk=None):
        """Save the FBR fiscal number + QR the LOCAL SDC returned.

        Idempotent + anti-duplication: if the invoice ALREADY has an FBR
        number, we DO NOT overwrite (the number is immutable) — we return the
        existing one with `already=true`. So retries, double-clicks, or two
        terminals racing all converge on one number; never a duplicate.

        Body: { "fbr_invoice_number": "...", "qr_payload": "<optional>" }
        """
        from django.utils import timezone
        from apps.fbr.qr import build_qr_payload
        from apps.fbr.budget import compute_edit_deadline
        from apps.audit.services import log as audit_log

        invoice = self.get_object()

        # Anti-duplication guard: already fiscalized → return existing, no write.
        if invoice.fbr_invoice_number:
            return Response({
                "ok": True, "already": True,
                "fbr_invoice_number": invoice.fbr_invoice_number,
            })

        fbr_no = (request.data.get("fbr_invoice_number") or "").strip()
        if not fbr_no:
            return Response(
                {"detail": "fbr_invoice_number is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        qr = (request.data.get("qr_payload") or "").strip() or build_qr_payload(
            fbr_invoice_number=fbr_no, validated_at=timezone.now(),
            amount=invoice.grand_total, seller_ntn=invoice.tenant.ntn,
        )
        now = timezone.now()
        invoice.fbr_invoice_number = fbr_no
        invoice.fbr_qr_payload = qr
        invoice.fbr_submitted_at = invoice.fbr_submitted_at or now
        invoice.fbr_validated_at = now
        invoice.edit_deadline_at = compute_edit_deadline(invoice.fbr_submitted_at)
        invoice.status = "valid"
        invoice.save(update_fields=[
            "fbr_invoice_number", "fbr_qr_payload", "fbr_submitted_at",
            "fbr_validated_at", "edit_deadline_at", "status", "updated_at",
        ])
        audit_log(
            tenant_id=invoice.tenant_id, entity_type="invoice",
            entity_id=invoice.id, action="fbr_validated_via_sdc",
            after={"fbr_invoice_number": fbr_no}, request=request,
        )
        return Response({
            "ok": True, "already": False,
            "fbr_invoice_number": fbr_no,
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="validate",
            permission_classes=[HasRolePerm.with_perm("sales.create")])
    def validate(self, request, pk=None):
        """Lint the invoice payload against PRAL's /validateinvoicedata
        without persisting a submission. Returns PRAL's verdict so the
        operator can fix problems before spending sandbox/production
        budget on a real submit.

        Logs the roundtrip as an FbrSubmission with endpoint
        'validateinvoicedata' so the FBR-log panel shows it alongside
        actual submits. The invoice itself is NOT mutated — no status
        change, no fbr_invoice_number write.
        """
        from apps.fbr.builder import build_invoice_payload
        from apps.fbr.client import (
            FbrClient,
            PralBusinessError,
            PralError,
            PralValidationError,
            PralTransientError,
        )
        from apps.fbr.models import FbrSubmission, FbrToken

        invoice = self.get_object()
        tenant = invoice.tenant
        token = (
            FbrToken.objects.filter(tenant=tenant, environment="production", is_active=True).first()
            or FbrToken.objects.filter(tenant=tenant, environment="sandbox", is_active=True).first()
        )
        if token is None:
            return Response(
                {"detail": "No FBR token configured for this tenant."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        environment = token.environment
        if environment == "sandbox":
            # PRAL's scenarioId applies to the WHOLE invoice (every line
            # must be compatible). SN007 demands ALL lines be 3rd-
            # Schedule; mixed invoices must fall back to the standard
            # scenario (SN001/SN002) and rely on per-line `saleType` +
            # `fixedNotifiedValueOrRetailPrice` to communicate the 3rd-
            # Schedule treatment of individual lines. See apps/fbr/
            # tasks.py for the longer explanation.
            items = list(invoice.items.all())
            all_third_schedule = items and all(
                i.fixed_notified_value is not None and i.fixed_notified_value > 0
                for i in items
            )
            if all_third_schedule:
                scenario_id = "SN007"
            elif (invoice.buyer_registration_type or "").lower() == "registered":
                scenario_id = "SN001"
            else:
                scenario_id = "SN002"
        else:
            scenario_id = None
        payload = build_invoice_payload(invoice, environment=environment, scenario_id=scenario_id)

        client = FbrClient(
            environment=environment, token=token.token,
            endpoint_base=token.api_endpoint or "https://gw.fbr.gov.pk",
        )

        try:
            result = client.validate_invoice(payload)
        except (PralValidationError, PralBusinessError) as exc:
            FbrSubmission.objects.create(
                tenant_id=tenant.id, invoice=invoice, environment=environment,
                endpoint="validateinvoicedata", request_payload=payload,
                response_payload=exc.response or {"error": str(exc)},
                http_status=getattr(exc, "http_status", None),
                status_code="01",
                error_message=str(exc),
                attempt_number=1,
            )
            return Response(
                {"valid": False, "error": str(exc), "error_code": getattr(exc, "error_code", None)},
                status=status.HTTP_200_OK,
            )
        except (PralTransientError, PralError) as exc:
            # PRAL's gateway misbehaved (timeout, non-JSON page, 5xx).
            # Persist the attempt so the operator can see WHAT PRAL
            # returned — without this, transient failures are invisible
            # in the submissions log and the operator has no way to
            # distinguish "PRAL service down" from "we built a bad
            # payload". The `kind: 'transient'` flag tells the
            # admin-web error UI to show a service-status message
            # instead of "rejected the payload".
            FbrSubmission.objects.create(
                tenant_id=tenant.id, invoice=invoice, environment=environment,
                endpoint="validateinvoicedata", request_payload=payload,
                response_payload=getattr(exc, "response", None) or {"error": str(exc)},
                http_status=getattr(exc, "http_status", None),
                status_code="transient",
                error_message=str(exc),
                attempt_number=1,
            )
            return Response(
                {
                    "valid": False,
                    "kind": "transient",
                    "detail": (
                        f"FBR's PRAL gateway is not responding correctly "
                        f"right now ({exc}). This is on FBR's side, not "
                        f"a problem with your invoice. Wait a moment and "
                        f"click Validate again — sandbox is often flaky "
                        f"during business hours."
                    ),
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # Success — record the validate roundtrip for audit. We do
        # NOT touch the invoice's fbr_invoice_number; validate doesn't
        # issue one.
        FbrSubmission.objects.create(
            tenant_id=tenant.id, invoice=invoice, environment=environment,
            endpoint="validateinvoicedata", request_payload=payload,
            response_payload=result.body,
            http_status=result.http_status,
            status_code=result.status_code,
            attempt_number=1, duration_ms=result.duration_ms,
        )
        return Response({"valid": True, "response": result.body})

    @action(detail=True, methods=["post"],
            url_path="items/(?P<item_id>[^/.]+)/edit",
            permission_classes=[HasRolePerm.with_perm("sales.cancel.threshold_high")])
    def edit_item(self, request, pk=None, item_id=None):
        """Edit one line on an FBR-validated invoice (within 72h).

        Per FBR Digital Invoicing Manual §4.1.2 an item can be edited
        once within 72 hours of submission. Honors the same 10% monthly
        budget as cancellations. The service layer enforces all rules;
        we just validate the body shape and translate exceptions.
        """
        from apps.fbr.services import edit_invoice_item_with_fbr
        invoice = self.get_object()
        try:
            item = invoice.items.get(pk=item_id)
        except invoice.items.model.DoesNotExist:
            raise NotFound("Item not found on this invoice.")

        body = EditItemSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        v = body.validated_data
        new_values = {
            k: v[k] for k in ("quantity", "unit_price", "tax_rate") if k in v
        }
        try:
            edit_invoice_item_with_fbr(
                invoice, item,
                new_values=new_values,
                reason=v["reason"],
                user=request.user,
                request=request,
            )
        except Exception as exc:
            if hasattr(exc, "message_dict"):
                return Response(exc.message_dict, status=status.HTTP_400_BAD_REQUEST)
            from django.core.exceptions import ValidationError as DjValidationError
            if isinstance(exc, DjValidationError):
                return Response(
                    {"detail": exc.messages[0] if exc.messages else str(exc)},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            raise
        invoice.refresh_from_db()
        return Response(InvoiceSerializer(invoice).data)

    @action(detail=True, methods=["post"],
            url_path="items/(?P<item_id>[^/.]+)/cancel",
            permission_classes=[HasRolePerm.with_perm("sales.cancel.threshold_high")])
    def cancel_item(self, request, pk=None, item_id=None):
        """Cancel one line on an invoice (PRAL per-item cancel pattern).

        Per the FBR Digital Invoicing Manual section 4.1.2, individual
        items can be cancelled within the 72-hour window. The rule
        check is per-line (`can_cancel_item`) — not invoice-wide —
        because a previously-edited item on the same invoice doesn't
        block cancelling a *different* item.
        """
        from apps.fbr.rules import can_cancel_item
        invoice = self.get_object()
        try:
            item = invoice.items.get(pk=item_id)
        except invoice.items.model.DoesNotExist:
            raise NotFound("Item not found on this invoice.")
        allowed, why = can_cancel_item(invoice, item)
        if not allowed:
            return Response({"detail": why}, status=status.HTTP_400_BAD_REQUEST)
        body = CancelSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        cancellation.cancel_sale_item(
            invoice, item_id,
            reason=body.validated_data["reason"],
            user=request.user, request=request,
        )
        invoice.refresh_from_db()
        return Response(InvoiceSerializer(invoice).data)

    @action(detail=True, methods=["get"], url_path="pdf")
    def pdf(self, request, pk=None):
        """Render the invoice as an FBR-compliant PDF.

        Layout matches the PRAL Digital Invoicing User Manual page 24:
        tenant logo + business info, FBR DI logo + QR (when validated),
        seller/buyer/summary blocks, line items table with C/E status
        flags. The QR is only rendered for FBR-validated invoices —
        a missing FBR number means the QR is intentionally absent so
        customers can see the invoice hasn't been confirmed yet.
        """
        from django.http import HttpResponse
        from .services.invoice_pdf import render_invoice_pdf

        invoice = self.get_object()
        # The renderer needs the related tenant for header branding.
        invoice.tenant  # touch to materialise the FK
        pdf_bytes = render_invoice_pdf(invoice)
        resp = HttpResponse(pdf_bytes, content_type="application/pdf")
        filename = f"invoice-{invoice.local_invoice_number}.pdf"
        disposition = "attachment" if request.query_params.get("download") else "inline"
        resp["Content-Disposition"] = f'{disposition}; filename="{filename}"'
        return resp

    def _fetch_tenant_object(self, model, pk):
        try:
            return model.objects.for_tenant(self.request.tenant_id).get(pk=pk)
        except model.DoesNotExist:
            raise NotFound(f"{model.__name__} not found.")


class CashSessionViewSet(
    _TenantQuerySetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    queryset = CashSession.objects.select_related("branch", "terminal", "cashier").all()
    permission_classes = [IsTenantMember]
    serializer_class = type(  # tiny inline serializer; nothing fancy
        "CashSessionSerializer", (object,), {},
    )

    def get_serializer_class(self):
        from rest_framework import serializers

        class _Ser(serializers.ModelSerializer):
            class Meta:
                model = CashSession
                fields = (
                    "id", "branch", "terminal", "cashier",
                    "opened_at", "opened_with_amount",
                    "closed_at", "closed_with_amount",
                    "expected_amount", "variance", "variance_reason",
                    "total_sales", "total_returns", "cash_in", "cash_out",
                    "status", "created_at", "updated_at",
                )
                read_only_fields = fields
        return _Ser

    @action(detail=False, methods=["post"], url_path="open",
            permission_classes=[HasRolePerm.with_perm("sales.create")])
    def open(self, request):
        body = SessionOpenSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        v = body.validated_data
        branch = Branch.objects.for_tenant(request.tenant_id).get(pk=v["branch"])
        terminal = Terminal.objects.for_tenant(request.tenant_id).get(pk=v["terminal"])
        session = sessions.open_session(
            tenant_id=request.tenant_id, branch=branch, terminal=terminal,
            cashier=request.user, opening_amount=v["opening_amount"],
            request=request,
        )
        return Response(self.get_serializer(session).data, status=201)

    @action(detail=True, methods=["post"],
            permission_classes=[HasRolePerm.with_perm("sales.create")])
    def close(self, request, pk=None):
        session = self.get_object()
        body = SessionCloseSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        v = body.validated_data
        sessions.close_session(
            session=session,
            declared_amount=v["declared_amount"],
            variance_reason=v.get("variance_reason", ""),
            cashier=request.user,
            request=request,
        )
        return Response(self.get_serializer(session).data)


# ---------------------------------------------------------------------------
# Public (signed-URL) endpoints
# ---------------------------------------------------------------------------
#
# Reachable WITHOUT authentication — the security boundary is the
# HMAC-signed token in the URL itself. Used by SendToBuyer so the
# seller can paste a link into a WhatsApp / email message and the
# buyer can fetch the PDF without an account.

from django.http import HttpResponse, HttpResponseNotFound
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from .services.share_links import (
    BadSignature,
    SignatureExpired,
    verify_share_token,
)


@csrf_exempt  # No cookies/CSRF; auth IS the signed token in the URL.
@require_GET
def public_invoice_pdf(request, token: str):
    """GET /p/inv/<token>.pdf

    The path captures `<token>.pdf` so when the buyer's browser
    auto-downloads it, the filename has the right extension. We strip
    the `.pdf` suffix before verifying the token.
    """
    from apps.sales.services.invoice_pdf import render_invoice_pdf

    # Strip trailing .pdf if present — the URL template captures it as
    # part of the slug for the filename, but the signed payload is
    # just the invoice id.
    raw = token[:-4] if token.endswith(".pdf") else token

    try:
        invoice_id = verify_share_token(raw)
    except SignatureExpired:
        return HttpResponse(
            "This share link has expired. Ask the seller for a new link.",
            status=410, content_type="text/plain",
        )
    except BadSignature:
        return HttpResponseNotFound("Invalid link.")

    try:
        invoice = (
            Invoice.objects
            .select_related("tenant", "branch", "customer")
            .prefetch_related("items", "items__product")
            .get(pk=invoice_id)
        )
    except Invoice.DoesNotExist:
        return HttpResponseNotFound("Invoice not found.")

    # Defensive: only share invoices that actually have an FBR number.
    # build_share_url already gates on this, but a stale token from
    # before a cancellation could still arrive here.
    if not invoice.fbr_invoice_number:
        return HttpResponse(
            "This invoice is no longer available for sharing.",
            status=410, content_type="text/plain",
        )

    pdf_bytes = render_invoice_pdf(invoice)
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    # `inline` so it previews in the browser tab; the buyer can hit
    # download from there. Filename uses the local invoice number, not
    # the FBR one (shorter, more readable).
    filename = f"invoice-{invoice.local_invoice_number}.pdf"
    resp["Content-Disposition"] = f'inline; filename="{filename}"'
    return resp
