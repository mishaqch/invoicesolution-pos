"""Sales models per DATABASE_SCHEMA.md §7.

Phase 2 lands the structure. Phase 4 fields (FBR identifiers, edit deadline)
are present as nullable from day one to avoid a migration in Phase 4.

Status state machine (Phase 2 only uses pending_sync; Phase 3 introduces
submitted/valid/failed; Phase 4 introduces edited/cancelled lifecycles):
  pending_sync  → submitted → valid
                            → failed
  any           → finalized       (Phase 4: 72h-aged invoices)
  any           → cancelled       (Phase 4: with budget consumption)

`client_uuid` is the idempotency key. Set on the POS at sale time. Server
enforces the UNIQUE constraint so retries are no-ops.
"""

from __future__ import annotations

from django.db import models

from core.models import TenantScopedModel
from core.uuid7 import uuid7


INVOICE_TYPES = (
    ("sale", "Sale"),
    ("debit_note", "Debit note"),
    ("credit_note", "Credit note"),
)

INVOICE_STATUSES = (
    ("pending_sync", "Pending sync"),
    ("submitted", "Submitted"),
    ("valid", "Valid"),
    ("failed", "Failed"),
    ("edited", "Edited"),
    ("partially_edited", "Partially edited"),
    ("cancelled", "Cancelled"),
    ("partially_cancelled", "Partially cancelled"),
    ("partially_edited_and_cancelled", "Partially edited and cancelled"),
    ("finalized", "Finalized"),
)

REGISTRATION_TYPES_DB = (
    ("Registered", "Registered"),
    ("Unregistered", "Unregistered"),
)


class Invoice(TenantScopedModel):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    branch = models.ForeignKey("tenants.Branch", on_delete=models.PROTECT)
    terminal = models.ForeignKey("tenants.Terminal", on_delete=models.PROTECT)
    cashier = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="invoices"
    )
    cash_session = models.ForeignKey(
        "tenants.CashSession", on_delete=models.SET_NULL,
        blank=True, null=True, related_name="invoices",
    )
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.SET_NULL,
        blank=True, null=True, related_name="invoices",
    )

    local_invoice_number = models.CharField(max_length=40)

    # FBR identifiers — Phase 4 populates. Reserved here per the Phase 2
    # plan ("present as nullable, not added later").
    fbr_invoice_number = models.CharField(
        max_length=40, blank=True, null=True, unique=True,
    )
    fbr_qr_payload = models.TextField(blank=True, null=True)
    fbr_submitted_at = models.DateTimeField(blank=True, null=True)
    fbr_validated_at = models.DateTimeField(blank=True, null=True)

    invoice_type = models.CharField(
        max_length=30, choices=INVOICE_TYPES, default="sale"
    )
    invoice_date = models.DateField()

    # Buyer snapshot — populated from the customer, frozen at sale time.
    buyer_name = models.CharField(max_length=255, blank=True, null=True)
    buyer_ntn_cnic = models.CharField(max_length=20, blank=True, null=True)
    buyer_phone = models.CharField(max_length=20, blank=True, null=True)
    buyer_address = models.TextField(blank=True, null=True)
    buyer_province = models.CharField(max_length=20, blank=True, null=True)
    buyer_registration_type = models.CharField(
        max_length=20, choices=REGISTRATION_TYPES_DB, default="Unregistered",
    )

    # Money totals — DECIMAL(14, 4)
    subtotal = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    discount_total = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    tax_total = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    further_tax_total = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    fed_total = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    withholding_tax_total = models.DecimalField(
        max_digits=14, decimal_places=4, default=0,
    )
    rounding_adjustment = models.DecimalField(
        max_digits=14, decimal_places=4, default=0,
    )
    grand_total = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    paid_total = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    change_given = models.DecimalField(max_digits=14, decimal_places=4, default=0)

    status = models.CharField(
        max_length=40, choices=INVOICE_STATUSES, default="pending_sync"
    )

    # Phase 4 — present as nullable.
    edit_deadline_at = models.DateTimeField(blank=True, null=True)

    # Soft-delete for UNSUBMITTED drafts only. A fiscalized invoice (has an FBR
    # number) is NEVER deletable. We soft-delete (not hard) because a draft that
    # was "Validated" already has an append-only fbr_submissions lint row whose
    # FK can't be nulled (UPDATE/DELETE revoked for compliance). Set => hidden
    # from all tenant-facing lists; row + audit/submission logs survive.
    deleted_at = models.DateTimeField(blank=True, null=True)

    reference_invoice = models.ForeignKey(
        "self", on_delete=models.SET_NULL, blank=True, null=True,
        related_name="referencing_invoices",
    )
    reason = models.CharField(max_length=50, blank=True, null=True)
    reason_notes = models.TextField(blank=True, null=True)

    # Idempotency key — generated on the POS at sale time.
    client_uuid = models.UUIDField(unique=True)

    notes = models.TextField(blank=True, null=True)
    is_held = models.BooleanField(default=False)
    held_label = models.CharField(max_length=50, blank=True, null=True)

    # --- Restaurant vertical (all nullable; null for grocery/pharmacy/DI) -----
    # An open table/order is an is_held invoice carrying these. Charge runs the
    # normal checkout (clears is_held → finalize → FBR). These never reach PRAL.
    order_type = models.CharField(
        max_length=12, blank=True, null=True,
        choices=(("dine_in", "Dine-in"), ("takeaway", "Takeaway"), ("delivery", "Delivery")),
    )
    table = models.ForeignKey(
        "restaurant.Table", on_delete=models.SET_NULL, blank=True, null=True,
        related_name="orders",
    )
    covers = models.PositiveSmallIntegerField(blank=True, null=True)  # party size
    order_status = models.CharField(
        max_length=20, blank=True, null=True,
        choices=(
            ("open", "Open"),
            ("sent_to_kitchen", "Sent to kitchen"),
            ("ready", "Ready"),
            ("served", "Served"),
        ),
    )
    kitchen_sent_at = models.DateTimeField(blank=True, null=True)

    # Phase 4 — invoices linked to a submitted Annexure-C cannot be edited.
    # Phase 6 returns logic flips this when a credit note's reference invoice
    # is in a submitted return.
    is_annexure_c_linked = models.BooleanField(default=False)

    class Meta:
        db_table = "invoices"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "local_invoice_number"],
                name="uniq_invoice_tenant_localnum",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "-invoice_date"], name="idx_invoices_tenant_date",
            ),
            models.Index(
                fields=["branch", "-invoice_date"], name="idx_invoices_branch_date",
            ),
            models.Index(
                fields=["customer", "-invoice_date"], name="idx_invoices_customer",
            ),
            models.Index(
                fields=["tenant", "branch"],
                name="idx_invoices_held",
                condition=models.Q(is_held=True),
            ),
        ]

    def __str__(self) -> str:
        return self.local_invoice_number


class SaleItem(models.Model):
    """Snapshot fields are immutable after creation. Edits land in
    sale_item_history and increment edit_count (Phase 4 enforces the max-1
    rule)."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    invoice = models.ForeignKey(
        Invoice, on_delete=models.CASCADE, related_name="items",
    )
    line_number = models.IntegerField()

    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT)
    variant = models.ForeignKey(
        "catalog.ProductVariant", on_delete=models.PROTECT, blank=True, null=True
    )
    batch = models.ForeignKey(
        "catalog.ProductBatch", on_delete=models.SET_NULL, blank=True, null=True
    )

    # Snapshot fields — never updated after creation.
    product_name = models.CharField(max_length=255)
    product_sku = models.CharField(max_length=50)
    hs_code = models.CharField(max_length=15, blank=True, null=True)
    uom_code = models.CharField(max_length=20)
    sale_type = models.CharField(
        max_length=50, default="Goods at standard rate (default)",
    )

    quantity = models.DecimalField(max_digits=14, decimal_places=4)
    unit_price = models.DecimalField(max_digits=14, decimal_places=4)
    cost_price = models.DecimalField(
        max_digits=14, decimal_places=4, blank=True, null=True,
    )

    discount_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=14, decimal_places=4, default=0)

    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    further_tax_amount = models.DecimalField(
        max_digits=14, decimal_places=4, default=0,
    )
    fed_amount = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    st_withheld_amount = models.DecimalField(
        max_digits=14, decimal_places=4, default=0,
    )

    fixed_notified_value = models.DecimalField(
        max_digits=14, decimal_places=4, blank=True, null=True,
    )
    sro_schedule_no = models.CharField(max_length=20, blank=True, null=True)
    sro_item_serial_no = models.CharField(max_length=20, blank=True, null=True)

    line_total = models.DecimalField(max_digits=14, decimal_places=4)

    # --- Restaurant vertical (nullable / empty for other verticals) ----------
    # Snapshot of the modifiers chosen for this line, e.g.
    #   [{"name": "Extra cheese", "price": "50.0000"}, {"name": "Large", "price": "100.0000"}]
    # Their prices are already folded into unit_price/line_total at quote time;
    # this list is kept for the receipt + KOT display. NOT sent to FBR.
    modifiers = models.JSONField(default=list, blank=True)
    # Optional course grouping for kitchen firing (1 = starters, 2 = mains, …).
    course = models.PositiveSmallIntegerField(blank=True, null=True)
    # Free-text kitchen note for this line ("no onions", "well done").
    item_note = models.CharField(max_length=255, blank=True, null=True)
    # Set true once this line has been fired to the kitchen, so re-firing only
    # prints newly-added lines.
    sent_to_kitchen = models.BooleanField(default=False)

    # Edit/cancel tracking — Phase 4 enforces the rules.
    is_edited = models.BooleanField(default=False)
    is_cancelled = models.BooleanField(default=False)
    edited_at = models.DateTimeField(blank=True, null=True)
    cancelled_at = models.DateTimeField(blank=True, null=True)
    edit_count = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "sale_items"
        constraints = [
            models.UniqueConstraint(
                fields=["invoice", "line_number"], name="uniq_saleitem_invoice_line",
            ),
        ]
        indexes = [
            models.Index(fields=["invoice"], name="idx_sale_items_invoice"),
            models.Index(
                fields=["product", "-created_at"],
                name="idx_sale_items_prod_date",
            ),
        ]


class SaleItemHistory(models.Model):
    """Pre-edit snapshots — required by PRAL spec (originals must remain
    viewable). Phase 2 builds the table; Phase 4 starts writing entries."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    sale_item = models.ForeignKey(
        SaleItem, on_delete=models.CASCADE, related_name="history",
    )
    changed_at = models.DateTimeField(auto_now_add=True)
    changed_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, blank=True, null=True,
    )
    change_type = models.CharField(
        max_length=20,
        choices=(("edit", "Edit"), ("cancel", "Cancel")),
    )
    previous_data = models.JSONField()

    class Meta:
        db_table = "sale_item_history"


PAYMENT_METHODS = (
    ("cash", "Cash"),
    ("card_credit", "Card (credit)"),
    ("card_debit", "Card (debit)"),
    ("easypaisa", "EasyPaisa"),
    ("jazzcash", "JazzCash"),
    ("raast", "Raast"),
    ("bank_transfer", "Bank transfer"),
    ("store_credit", "Store credit"),
    ("cheque", "Cheque"),
)

PAYMENT_STATUSES = (
    ("pending", "Pending"),
    ("completed", "Completed"),
    ("failed", "Failed"),
    ("refunded", "Refunded"),
)


class Payment(TenantScopedModel):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    invoice = models.ForeignKey(
        Invoice, on_delete=models.PROTECT, blank=True, null=True,
        related_name="payments",
    )
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.SET_NULL,
        blank=True, null=True, related_name="payments",
    )

    payment_method = models.CharField(max_length=30, choices=PAYMENT_METHODS)
    amount = models.DecimalField(max_digits=14, decimal_places=4)

    # Method-specific fields — all nullable; the row is shaped by payment_method.
    card_last4 = models.CharField(max_length=4, blank=True, null=True)
    card_terminal_id = models.CharField(max_length=50, blank=True, null=True)
    card_auth_code = models.CharField(max_length=20, blank=True, null=True)
    card_rrn = models.CharField(max_length=50, blank=True, null=True)

    wallet_provider = models.CharField(max_length=20, blank=True, null=True)
    wallet_phone = models.CharField(max_length=20, blank=True, null=True)
    wallet_transaction_id = models.CharField(max_length=100, blank=True, null=True)

    bank_name = models.CharField(max_length=50, blank=True, null=True)
    bank_account_last4 = models.CharField(max_length=4, blank=True, null=True)
    bank_reference = models.CharField(max_length=100, blank=True, null=True)

    raast_iban = models.CharField(max_length=34, blank=True, null=True)
    raast_transaction_id = models.CharField(max_length=100, blank=True, null=True)

    cheque_number = models.CharField(max_length=50, blank=True, null=True)
    cheque_date = models.DateField(blank=True, null=True)
    cheque_status = models.CharField(max_length=20, blank=True, null=True)

    status = models.CharField(
        max_length=20, choices=PAYMENT_STATUSES, default="completed",
    )

    received_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, blank=True, null=True,
    )
    notes = models.TextField(blank=True, null=True)

    # Phase 5 — refund framework. Set on a refund row pointing back to the
    # original payment. Phase 6 returns logic populates this; Phase 5 just
    # makes the column available so the refund flow has a place to land.
    refund_of = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="refunds",
    )

    class Meta:
        db_table = "payments"
        indexes = [
            models.Index(fields=["invoice"], name="idx_payments_invoice"),
            models.Index(
                fields=["customer", "-created_at"],
                name="idx_payments_customer_date",
            ),
            models.Index(
                fields=["tenant", "payment_method", "-created_at"],
                name="idx_payments_method_date",
            ),
        ]


class Discount(TenantScopedModel):
    """Promotion catalog. Phase 2 ships the model; the cashier-facing
    discount UX is line-level + cart-level free-form for now."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    name = models.CharField(max_length=100)
    discount_type = models.CharField(
        max_length=20,
        choices=(
            ("percentage", "Percentage"),
            ("fixed", "Fixed"),
            ("buy_x_get_y", "Buy X get Y"),
        ),
    )
    value = models.DecimalField(max_digits=14, decimal_places=4)
    min_purchase_amount = models.DecimalField(
        max_digits=14, decimal_places=4, blank=True, null=True,
    )
    applies_to = models.CharField(
        max_length=20,
        choices=(
            ("all", "All"),
            ("category", "Category"),
            ("product", "Product"),
            ("customer_group", "Customer group"),
        ),
    )
    applies_to_ids = models.JSONField(default=list, blank=True)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField(blank=True, null=True)
    max_uses = models.IntegerField(blank=True, null=True)
    uses_count = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "discounts"
