"""Sales DRF serializers."""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from .models import Invoice, Payment, SaleItem


class SaleItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = SaleItem
        fields = (
            "id", "line_number",
            "product", "variant", "batch",
            "product_name", "product_sku", "hs_code", "uom_code", "sale_type",
            "quantity", "unit_price", "cost_price",
            "discount_pct", "discount_amount",
            "tax_rate", "tax_amount",
            "line_total",
            "is_edited", "is_cancelled", "edit_count",
            "created_at",
        )
        read_only_fields = ("id", "created_at")


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = (
            "id", "invoice", "customer",
            "payment_method", "amount",
            "card_last4", "card_auth_code", "card_rrn",
            "wallet_provider", "wallet_phone", "wallet_transaction_id",
            "bank_name", "bank_account_last4", "bank_reference",
            "raast_iban", "raast_transaction_id",
            "cheque_number", "cheque_date", "cheque_status",
            "status", "received_by", "notes",
            "created_at", "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class InvoiceSerializer(serializers.ModelSerializer):
    items = SaleItemSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    # Public share URL for the FBR-validated PDF. Returned only when
    # the invoice has been validated by FBR (i.e. has an FBR invoice
    # number). The URL is HMAC-signed and TTL-limited via
    # apps.sales.services.share_links; anyone with the link can fetch
    # the PDF without auth. Used by SendToBuyer for WhatsApp + email.
    share_url = serializers.SerializerMethodField()
    # The branch's FBR POS ID. Present => this is a POS/SDC tenant, so the UI
    # shows the "Fiscalize with FBR (SDC)" button and hides the DI-API
    # Validate/Submit buttons (which need a tenant token SDC tenants don't have).
    branch_fbr_pos_id = serializers.CharField(
        source="branch.fbr_pos_id", read_only=True, allow_null=True,
    )

    class Meta:
        model = Invoice
        fields = (
            "id", "branch", "branch_fbr_pos_id", "terminal", "cashier",
            "cash_session", "customer",
            "local_invoice_number",
            "fbr_invoice_number", "fbr_qr_payload",
            "fbr_submitted_at", "fbr_validated_at",
            "invoice_type", "invoice_date",
            "reference_invoice",
            "buyer_name", "buyer_ntn_cnic", "buyer_phone",
            "buyer_address", "buyer_province", "buyer_registration_type",
            "subtotal", "discount_total", "tax_total", "grand_total",
            "paid_total", "change_given",
            "status", "edit_deadline_at",
            "client_uuid", "notes", "is_held", "held_label",
            "items", "payments",
            "share_url",
            "created_at", "updated_at",
        )
        read_only_fields = (
            "id", "local_invoice_number",
            "fbr_invoice_number", "fbr_qr_payload",
            "fbr_submitted_at", "fbr_validated_at",
            "subtotal", "discount_total", "tax_total", "grand_total",
            "paid_total", "change_given", "edit_deadline_at",
            "items", "payments", "share_url", "created_at", "updated_at",
        )

    def get_share_url(self, obj):
        from apps.sales.services.share_links import build_share_url
        request = self.context.get("request")
        return build_share_url(obj, request=request)


class CheckoutLineSerializer(serializers.Serializer):
    product = serializers.UUIDField()
    variant = serializers.UUIDField(required=False, allow_null=True)
    batch = serializers.UUIDField(required=False, allow_null=True)
    quantity = serializers.DecimalField(max_digits=14, decimal_places=4)
    unit_price = serializers.DecimalField(max_digits=14, decimal_places=4)
    discount_pct = serializers.DecimalField(
        max_digits=5, decimal_places=2, required=False, default=0,
    )
    discount_amount = serializers.DecimalField(
        max_digits=14, decimal_places=4, required=False, default=0,
    )
    tax_rate = serializers.DecimalField(
        max_digits=5, decimal_places=2, required=False, default=0,
    )
    is_taxable = serializers.BooleanField(default=True)
    # Manual / wholesaler flow lets the user override HS code + UoM per
    # line without editing the catalog. Optional; backend ignores when
    # absent and falls back to the product's catalog values.
    hs_code = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    uom_code = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    # Optional per-line FBR sale-type override. When absent, checkout falls back
    # to the product's sale_type (then the standard-rate default).
    sale_type = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    # Optional per-line SRO override (reduced-rate / 8th-Schedule). Falls back to
    # the product's configured SRO when absent.
    sro_schedule_no = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    sro_item_serial_no = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class CheckoutPaymentSerializer(serializers.Serializer):
    payment_method = serializers.ChoiceField(
        choices=["cash", "card_credit", "card_debit", "easypaisa", "jazzcash",
                 "raast", "bank_transfer", "store_credit", "cheque"],
    )
    amount = serializers.DecimalField(max_digits=14, decimal_places=4)


class CheckoutSerializer(serializers.Serializer):
    """Body of POST /api/sales/invoices/checkout/ and /manual/.

    invoice_type + reference_invoice are honored by /manual/ only —
    the POS terminal's `checkout` flow always creates a sale. They
    enable the debit-note workflow: pass invoice_type='debit_note'
    plus the original invoice id and the API will create a linked
    invoice with the same buyer block, sent to PRAL as a separate
    document referencing the original.

    branch + terminal are OPTIONAL here because office-invoice tenants
    (no branches/terminals modules enabled) can't supply them. The
    /manual/ view falls back to an implicit default branch + terminal
    when missing. The POS /checkout/ flow is gated separately and
    always supplies them (a terminal can't ring up a sale without
    knowing which terminal it is).
    """
    branch = serializers.UUIDField(required=False, allow_null=True)
    terminal = serializers.UUIDField(required=False, allow_null=True)
    # Warehouse to deduct stock from (Digital Invoicing). Optional — omitted by
    # POS checkout, which stays branch-keyed.
    warehouse = serializers.UUIDField(required=False, allow_null=True)
    cash_session = serializers.UUIDField(required=False, allow_null=True)
    customer = serializers.UUIDField(required=False, allow_null=True)
    cart_lines = CheckoutLineSerializer(many=True)
    cart_discount_pct = serializers.DecimalField(
        max_digits=5, decimal_places=2, required=False, default=0,
    )
    payments = CheckoutPaymentSerializer(many=True)
    client_uuid = serializers.UUIDField()
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    # Debit / credit note linkage. Both default to None (sale flow).
    invoice_type = serializers.ChoiceField(
        choices=["sale", "debit_note", "credit_note"],
        required=False, default="sale",
    )
    reference_invoice = serializers.UUIDField(required=False, allow_null=True)
    # Debit-note reason. PRAL DI manual FAQ (page 37): when "others"
    # is the chosen reason, the user must supply free-text remarks
    # explaining the adjustment so the audit trail is meaningful.
    # Accepted reasons mirror PRAL's debit-note reason taxonomy plus
    # an "others" escape hatch.
    DEBIT_NOTE_REASONS = (
        "rate_correction", "quantity_correction", "additional_charges",
        "missed_items", "others",
    )
    reason = serializers.ChoiceField(
        choices=DEBIT_NOTE_REASONS, required=False, allow_null=True,
        allow_blank=True,
    )
    reason_notes = serializers.CharField(
        required=False, allow_null=True, allow_blank=True, max_length=500,
    )

    def validate(self, attrs):
        itype = attrs.get("invoice_type", "sale")
        ref = attrs.get("reference_invoice")
        if itype in ("debit_note", "credit_note") and not ref:
            raise serializers.ValidationError(
                {"reference_invoice": f"{itype} requires a reference_invoice."},
            )
        if itype == "sale" and ref:
            raise serializers.ValidationError(
                {"invoice_type": "Sale invoices cannot reference another invoice."},
            )
        # PRAL FAQ: "others" reason requires explanatory remarks.
        if itype == "debit_note" and attrs.get("reason") == "others":
            notes = (attrs.get("reason_notes") or "").strip()
            if not notes:
                raise serializers.ValidationError({
                    "reason_notes": (
                        "When the debit-note reason is 'others', please "
                        "explain the adjustment in the notes field "
                        "(required by FBR)."
                    ),
                })
        return attrs


class HoldSerializer(serializers.Serializer):
    label = serializers.CharField(max_length=50)


class CancelSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=2, max_length=500)


class EditItemSerializer(serializers.Serializer):
    """Per-line edit within the 72h FBR window.

    All numeric fields are optional so the client can patch one or more
    of quantity / unit_price / tax_rate without touching the others.
    The service layer validates further (whitelist, non-negative).
    """
    reason = serializers.CharField(min_length=2, max_length=500)
    quantity = serializers.DecimalField(
        max_digits=14, decimal_places=4, required=False,
        min_value=Decimal("0"),
    )
    unit_price = serializers.DecimalField(
        max_digits=14, decimal_places=4, required=False,
        min_value=Decimal("0"),
    )
    tax_rate = serializers.DecimalField(
        max_digits=5, decimal_places=2, required=False,
        min_value=Decimal("0"),
    )

    def validate(self, attrs):
        if not any(k in attrs for k in ("quantity", "unit_price", "tax_rate")):
            raise serializers.ValidationError(
                "At least one of quantity / unit_price / tax_rate is required.",
            )
        return attrs


class SessionOpenSerializer(serializers.Serializer):
    branch = serializers.UUIDField()
    terminal = serializers.UUIDField()
    opening_amount = serializers.DecimalField(max_digits=14, decimal_places=4)


class SessionCloseSerializer(serializers.Serializer):
    declared_amount = serializers.DecimalField(max_digits=14, decimal_places=4)
    variance_reason = serializers.CharField(required=False, allow_blank=True, default="")
