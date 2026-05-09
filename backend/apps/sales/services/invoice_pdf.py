"""Render an invoice as a PDF, FBR-compliant layout.

Mirrors the layout from the PRAL Digital Invoicing User Manual page 24:

  ┌──────────────────────────────────────────────────────────────────┐
  │ <Tenant logo>   Tenant business name      [FBR DI logo] [QR png] │
  ├──────────────────────────────────────────────────────────────────┤
  │ Seller Information   │ Buyer Information   │ Invoice Summary    │
  ├──────────────────────────────────────────────────────────────────┤
  │ Sr  HS Code  Description  Sale Type  Qty  UoM  Rate  Sales      │
  │     Value  Retail Price  Sales Tax  Extra Tax  Further Tax  FED │
  │     ST WHT  Discount  SRO No  SRO Item  Status                  │
  ├──────────────────────────────────────────────────────────────────┤
  │     Total: ...                                                   │
  └──────────────────────────────────────────────────────────────────┘
  In the above invoices, "E" denotes... "C" indicates...
  Page X of Y

Status column shows "C" for cancelled lines, "E" for edited lines (the
PRAL convention from the manual). The QR code is the FBR-issued payload
when present, otherwise omitted (no fake QR — auditors verify QRs by
scanning them against the FBR portal).

Tenant + FBR logos: looked up from settings; falls back to text-only
header if either is missing on disk.
"""

from __future__ import annotations

import base64
import io
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer,
    Table, TableStyle,
)

from apps.fbr.qr import build_qr_payload, render_png_b64
from apps.sales.models import Invoice


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _money(value) -> str:
    if value is None:
        return "0.00"
    d = value if isinstance(value, Decimal) else Decimal(str(value))
    return f"{d:,.2f}"


def _b64_to_image(b64: str, *, width_mm: float, height_mm: float) -> Image:
    # render_png_b64 returns a `data:image/png;base64,...` data URI;
    # strip the prefix if present.
    if b64.startswith("data:"):
        b64 = b64.split(",", 1)[1]
    raw = base64.b64decode(b64)
    return Image(io.BytesIO(raw), width=width_mm * mm, height=height_mm * mm)


def _file_image(path: Path | str, *, width_mm: float, height_mm: float) -> Image | None:
    p = Path(path)
    if not p.exists():
        return None
    return Image(str(p), width=width_mm * mm, height=height_mm * mm)


def _line_status_marker(item) -> str:
    """The PRAL convention from manual page 24: C for cancelled, E for edited."""
    if getattr(item, "is_cancelled", False):
        return "C"
    if getattr(item, "is_edited", False):
        return "E"
    return ""


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def render_invoice_pdf(invoice: Invoice) -> bytes:
    """Render the invoice as a single-document PDF and return the bytes."""
    tenant = invoice.tenant
    items = list(
        invoice.items.select_related("product").order_by("line_number")
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=10 * mm,
        rightMargin=10 * mm,
        topMargin=10 * mm,
        bottomMargin=14 * mm,
        title=f"Invoice {invoice.local_invoice_number}",
        author=tenant.business_name,
    )

    styles = getSampleStyleSheet()
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=7, leading=9)
    label = ParagraphStyle("label", parent=styles["Normal"], fontSize=7,
                           leading=9, textColor=colors.HexColor("#6b7280"))
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=14, leading=16)

    story = []

    # ----- Header (3 columns: tenant logo+name | spacer | FBR DI logo + QR) -----
    tenant_logo = None
    if getattr(tenant, "logo_url", None):
        # logo_url may be local path or remote URL. Best-effort local lookup.
        tenant_logo = _file_image(
            Path(settings.MEDIA_ROOT) / "tenants" / f"{tenant.id}-logo.png",
            width_mm=18, height_mm=18,
        )

    fbr_logo_path = Path(settings.BASE_DIR) / "apps" / "sales" / "assets" / "fbr_di_logo.png"
    fbr_logo = _file_image(fbr_logo_path, width_mm=22, height_mm=18)

    qr_image = None
    qr_payload = invoice.fbr_qr_payload
    if not qr_payload and invoice.fbr_invoice_number:
        # If the invoice has an FBR number but the persisted QR payload is
        # missing (older sandbox runs), build one on the fly.
        qr_payload = build_qr_payload(
            fbr_invoice_number=invoice.fbr_invoice_number,
            validated_at=invoice.updated_at,
            amount=invoice.grand_total,
            seller_ntn=tenant.ntn,
        )
    if qr_payload:
        qr_image = _b64_to_image(render_png_b64(qr_payload), width_mm=22, height_mm=22)

    left_cell = []
    if tenant_logo:
        left_cell.append(tenant_logo)
    left_cell.append(Paragraph(f"<b>{tenant.business_name}</b>", h1))
    if tenant.address:
        left_cell.append(Paragraph(tenant.address, small))

    right_cell = []
    if fbr_logo:
        right_cell.append(fbr_logo)
    if qr_image:
        right_cell.append(qr_image)
        right_cell.append(Paragraph("Scan to verify on FBR", small))
    elif invoice.status not in ("valid", "edited", "partially_cancelled"):
        right_cell.append(Paragraph(
            "<font color='#b45309'><b>NOT YET FBR-VALIDATED</b></font><br/>"
            "<font size='6'>This invoice has not been confirmed by PRAL. "
            "Awaiting submission or retry.</font>",
            small,
        ))

    header_table = Table(
        [[left_cell, "", right_cell]],
        colWidths=[100 * mm, 5 * mm, 70 * mm],
    )
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (2, 0), (2, 0), "RIGHT"),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 4))

    # ----- Three info blocks: Seller / Buyer / Summary -----
    seller_block = [
        Paragraph("<b>Seller Information</b>", small),
        Paragraph(f"<b>Business Name:</b> {tenant.business_name}", small),
        Paragraph(f"<b>NTN:</b> {tenant.ntn}", small),
        Paragraph(f"<b>STRN:</b> {tenant.strn or '—'}", small),
        Paragraph(f"<b>Province:</b> {tenant.province}", small),
        Paragraph(
            f"<b>Branch:</b> {invoice.branch.name} "
            f"({invoice.branch.code})", small,
        ),
        Paragraph(f"<b>Source Invoice No:</b> {invoice.local_invoice_number}", small),
    ]
    buyer_block = [
        Paragraph("<b>Buyer Information</b>", small),
        Paragraph(
            f"<b>Buyer Name:</b> {invoice.buyer_name or '—'}", small,
        ),
        Paragraph(
            f"<b>Registration No:</b> "
            f"{invoice.buyer_ntn_cnic or '—'}", small,
        ),
        Paragraph(
            f"<b>Registration Type:</b> "
            f"{invoice.buyer_registration_type or '—'}", small,
        ),
        Paragraph(f"<b>Province:</b> {invoice.buyer_province or '—'}", small),
        Paragraph(f"<b>Address:</b> {invoice.buyer_address or '—'}", small),
        Paragraph(f"<b>Phone:</b> {invoice.buyer_phone or '—'}", small),
    ]
    summary_block = [
        Paragraph("<b>Invoice Summary</b>", small),
        Paragraph(
            f"<b>FBR Invoice No:</b> {invoice.fbr_invoice_number or '—'}", small,
        ),
        Paragraph(
            f"<b>Invoice Date:</b> {invoice.invoice_date}", small,
        ),
        Paragraph(f"<b>Invoice Type:</b> {invoice.invoice_type}", small),
        Paragraph(
            f"<b>Tax Period:</b> "
            f"{invoice.invoice_date.strftime('%Y%m')}", small,
        ),
        Paragraph(
            f"<b>Status:</b> "
            f"{invoice.status.replace('_', ' ').title()}", small,
        ),
    ]

    info_table = Table(
        [[seller_block, buyer_block, summary_block]],
        colWidths=[60 * mm, 60 * mm, 70 * mm],
    )
    info_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e5e7eb")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 6))

    # ----- Line items table (PRAL columns) -----
    # Use shorter labels than the manual to keep the row narrow on A4.
    head = [
        "Sr",
        "HS Code",
        "Description",
        "Sale Type",
        "Qty",
        "UoM",
        "Rate %",
        "Sales Value",
        "Sales Tax",
        "Extra Tax",
        "Further",
        "FED",
        "Discount",
        "Total",
        "St",
    ]
    body_rows: list[list] = []
    for it in items:
        # SaleItem doesn't store subtotal separately; compute the
        # "Sales Value" (taxable base) explicitly.
        qty = Decimal(str(it.quantity or 0))
        unit_price = Decimal(str(it.unit_price or 0))
        line_disc = Decimal(str(it.discount_amount or 0))
        sales_value = qty * unit_price - line_disc

        body_rows.append([
            str(it.line_number),
            it.hs_code or "",
            Paragraph(
                f"<b>{getattr(it, 'product_name', '')}</b><br/>"
                f"<font size='6'>{getattr(it, 'product_sku', '')}</font>",
                small,
            ),
            (it.sale_type or "Goods at Standard Rate"),
            f"{it.quantity}",
            it.uom_code or "",
            f"{it.tax_rate}",
            _money(sales_value),
            _money(it.tax_amount),
            _money(getattr(it, "further_tax_amount", 0) or 0),
            "0.00",
            _money(getattr(it, "fed_amount", 0) or 0),
            _money(getattr(it, "discount_amount", 0) or 0),
            _money(it.line_total),
            _line_status_marker(it),
        ])

    # Totals row.
    totals_row = [
        "", "", "", "Total", "", "", "",
        _money(invoice.subtotal),
        _money(invoice.tax_total),
        _money(getattr(invoice, "further_tax_total", 0) or 0),
        "0.00",
        _money(getattr(invoice, "fed_total", 0) or 0),
        _money(invoice.discount_total),
        _money(invoice.grand_total),
        "",
    ]
    body_rows.append(totals_row)

    items_table = Table(
        [head] + body_rows,
        colWidths=[
            6 * mm,  14 * mm, 32 * mm, 22 * mm, 10 * mm,
            10 * mm, 10 * mm, 18 * mm, 16 * mm, 14 * mm,
            13 * mm, 12 * mm, 14 * mm, 16 * mm, 5 * mm,
        ],
        repeatRows=1,
    )
    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (4, 0), (-2, -1), "RIGHT"),
        ("ALIGN", (-1, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e5e7eb")),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f3f4f6")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2),
         [colors.white, colors.HexColor("#fafafa")]),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 6))

    # ----- Footer note (matches PRAL manual page 24) -----
    story.append(Paragraph(
        '<font size="7">In the above invoices, '
        '<b>"E"</b> denotes that the invoice item has been edited, '
        'whereas <b>"C"</b> indicates that the invoice item has been cancelled.</font>',
        small,
    ))
    story.append(Spacer(1, 4))

    if not invoice.fbr_invoice_number:
        story.append(KeepTogether([Paragraph(
            "<font size='8' color='#b45309'><b>Note:</b> This invoice has not yet "
            "received an FBR validation number. The QR code above is intentionally "
            "absent until PRAL confirms the submission. Once submitted successfully, "
            "this PDF will include a scannable FBR QR.</font>",
            small,
        )]))

    doc.build(story)
    return buf.getvalue()
