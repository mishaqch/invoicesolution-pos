"""Hotel / resort domain — rooms + multi-day guest folios.

A GuestFolio is a guest's stay: opened at check-in with guest details + a room,
it groups MANY daily charge-invoices (the room-night charge + each day's
restaurant/misc charges). At checkout the folio produces ONE consolidated bill.

Charges themselves are normal sales.Invoice rows (reusing the proven offline
sync + checkout machinery); FolioInvoice links each one to its folio. This lets
a folio span days without inventing a new offline-sync entity.

Room nightly tax is a FIXED AMOUNT per night (per TDCP's tariff), NOT a percent;
restaurant items keep their own percentage tax. All tenant-scoped; user-facing
rows soft-delete per the audit-don't-delete invariant.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.db import models, transaction

from core.models import TenantScopedModel
from core.uuid7 import uuid7

ROOM_STATUSES = (
    ("available", "Available"),
    ("occupied", "Occupied"),
    ("maintenance", "Maintenance"),
)

FOLIO_STATUSES = (
    ("open", "Open"),          # guest checked in, accruing charges
    ("closed", "Closed"),      # checked out + settled
    ("cancelled", "Cancelled"),
)

CHARGE_KINDS = (
    ("room", "Room"),
    ("restaurant", "Restaurant"),
    ("misc", "Miscellaneous"),
)


class Room(TenantScopedModel):
    """A physical, bookable room. nightly_base + nightly_tax (FIXED amount) make
    up the per-night total a guest pays; both scale by nights × this room."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    branch = models.ForeignKey(
        "tenants.Branch", on_delete=models.CASCADE, related_name="rooms",
    )
    room_number = models.CharField(max_length=20)          # "VIP-1", "STD-3"
    room_type = models.CharField(max_length=40)            # "VIP", "Deluxe", "Standard"
    # Per-night economics. nightly_tax is an ABSOLUTE amount (e.g. 1680), not %.
    nightly_base = models.DecimalField(max_digits=14, decimal_places=4)
    nightly_tax = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    # Link to the catalog Product representing this room type (for the sale line
    # + stock-free invoicing). Nullable so rooms can exist before the product.
    product = models.ForeignKey(
        "catalog.Product", on_delete=models.SET_NULL, blank=True, null=True,
        related_name="rooms",
    )
    display_order = models.PositiveIntegerField(default=0)

    status = models.CharField(max_length=15, choices=ROOM_STATUSES, default="available")
    is_active = models.BooleanField(default=True)
    deleted_at = models.DateTimeField(blank=True, null=True)

    # created_at / updated_at come from TenantScopedModel (TimestampedModel).

    class Meta:
        db_table = "hotel_rooms"
        ordering = ["display_order", "room_number"]
        indexes = [
            models.Index(fields=["tenant", "branch"]),
            models.Index(fields=["tenant", "branch", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "branch", "room_number"],
                condition=models.Q(deleted_at__isnull=True),
                name="uniq_room_tenant_branch_number",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.room_number} ({self.room_type})"

    @property
    def nightly_total(self) -> Decimal:
        return (self.nightly_base or Decimal("0")) + (self.nightly_tax or Decimal("0"))


class GuestFolio(TenantScopedModel):
    """A guest's stay — the running tab. Groups daily charge-invoices and
    produces one consolidated bill at checkout."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    branch = models.ForeignKey(
        "tenants.Branch", on_delete=models.PROTECT, related_name="folios",
    )
    folio_number = models.CharField(max_length=40)          # KK-F-2026-0001

    # Guest identity (required: name, cnic, phone; optional: email, address).
    guest_name = models.CharField(max_length=255)
    guest_cnic = models.CharField(max_length=20)
    guest_phone = models.CharField(max_length=20)
    guest_email = models.EmailField(max_length=254, blank=True)
    guest_address = models.TextField(blank=True)

    # Accompanying partner (e.g. a couple checking in). Optional — recorded at
    # reception when a second person shares the stay. Not billed separately; the
    # folio stays a single guest bill.
    partner_name = models.CharField(max_length=255, blank=True)
    partner_cnic = models.CharField(max_length=20, blank=True)

    # Primary room (first/main room). A folio can hold SEVERAL rooms under the
    # same guest via FolioRoom (below) — one guest, many rooms, one bill. This
    # FK is kept for the primary room + backward compatibility.
    room = models.ForeignKey(
        Room, on_delete=models.PROTECT, blank=True, null=True, related_name="folios",
    )

    check_in = models.DateTimeField()
    check_out = models.DateTimeField(blank=True, null=True)   # set at checkout
    expected_check_out = models.DateTimeField(blank=True, null=True)
    nights = models.PositiveIntegerField(default=1)          # billed nights

    status = models.CharField(max_length=15, choices=FOLIO_STATUSES, default="open")

    opened_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, blank=True, null=True,
        related_name="opened_folios",
    )
    closed_at = models.DateTimeField(blank=True, null=True)
    notes = models.TextField(blank=True)

    # created_at / updated_at come from TenantScopedModel.

    class Meta:
        db_table = "hotel_guest_folios"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "branch", "status"]),
            models.Index(fields=["tenant", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "folio_number"],
                name="uniq_folio_number_per_tenant",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.folio_number} — {self.guest_name}"

    @staticmethod
    @transaction.atomic
    def next_number(*, tenant_id, branch) -> str:
        """Mint a per-branch-per-year folio number: <BRANCH>-F-YYYY-NNNN."""
        year = dt.date.today().year
        prefix = f"{branch.code}-F-{year}-"
        last = (
            GuestFolio.objects.select_for_update()
            .filter(tenant_id=tenant_id, branch=branch, folio_number__startswith=prefix)
            .order_by("-folio_number")
            .values_list("folio_number", flat=True)
            .first()
        )
        seq = (int(last.rsplit("-", 1)[-1]) + 1) if last else 1
        return f"{prefix}{seq:04d}"


class FolioInvoice(TenantScopedModel):
    """Links one charge-invoice to a folio. Each row is a charge entry (the room
    night, or one day's restaurant order) appended to the running stay."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    folio = models.ForeignKey(
        GuestFolio, on_delete=models.CASCADE, related_name="charges",
    )
    invoice = models.OneToOneField(
        "sales.Invoice", on_delete=models.PROTECT, related_name="folio_link",
    )
    kind = models.CharField(max_length=15, choices=CHARGE_KINDS, default="restaurant")
    charge_date = models.DateField(default=dt.date.today)
    # Which room this charge is for (multi-room folios). NULL = general/whole
    # stay (not tied to a specific room). Room-night charges always set this.
    room = models.ForeignKey(
        Room, on_delete=models.SET_NULL, blank=True, null=True, related_name="folio_charges",
    )

    # created_at / updated_at come from TenantScopedModel.

    class Meta:
        db_table = "hotel_folio_invoices"
        ordering = ["charge_date", "created_at"]
        indexes = [models.Index(fields=["tenant", "folio"])]

    def __str__(self) -> str:
        return f"{self.folio.folio_number} · {self.kind} · {self.charge_date}"


class FolioRoom(TenantScopedModel):
    """A room booked on a folio. One guest (one folio) can book several rooms,
    each with its own nights. The room-night charge is auto-posted per room."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    folio = models.ForeignKey(
        GuestFolio, on_delete=models.CASCADE, related_name="rooms_booked",
    )
    room = models.ForeignKey(Room, on_delete=models.PROTECT, related_name="folio_rooms")
    nights = models.PositiveIntegerField(default=1)
    check_in = models.DateTimeField()
    expected_check_out = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "hotel_folio_rooms"
        indexes = [models.Index(fields=["tenant", "folio"])]
        constraints = [
            models.UniqueConstraint(
                fields=["folio", "room"], name="uniq_folioroom_folio_room",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.folio.folio_number} · {self.room.room_number}"
