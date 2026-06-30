from __future__ import annotations

from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import FolioInvoice, GuestFolio, Room


@admin.register(Room)
class RoomAdmin(ModelAdmin):
    list_display = ("room_number", "room_type", "nightly_base", "nightly_tax", "status", "branch")
    list_filter = ("status", "room_type", "branch")
    search_fields = ("room_number", "room_type")
    ordering = ("display_order", "room_number")


class FolioInvoiceInline(admin.TabularInline):
    model = FolioInvoice
    extra = 0
    fields = ("kind", "charge_date", "invoice")
    readonly_fields = fields


@admin.register(GuestFolio)
class GuestFolioAdmin(ModelAdmin):
    list_display = (
        "folio_number", "guest_name", "guest_phone", "room",
        "check_in", "check_out", "nights", "status",
    )
    list_filter = ("status", "branch")
    search_fields = ("folio_number", "guest_name", "guest_cnic", "guest_phone")
    readonly_fields = ("folio_number", "created_at", "updated_at", "closed_at")
    inlines = [FolioInvoiceInline]
    ordering = ("-created_at",)
