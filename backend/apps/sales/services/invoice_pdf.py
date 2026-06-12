"""Render an invoice as a polished, FBR-compliant PDF.

Design goals (UX-driven):
- High visual hierarchy: a single bold accent color (FBR teal) carries the
  whole document; everything else is restrained greys + crisp typography.
- Generous whitespace; no edge-to-edge grids.
- Per-section "lozenge" headings rather than busy table chrome.
- Right-rail panel with the FBR seal, QR code, status pill, and grand total
  — the four things a customer or auditor actually looks at first.
- Slim line-items table: only the columns a real product invoice needs.
  Optional columns (HS, discount, status flag) appear only when used.
- The FBR Digital Invoicing seal is drawn natively as ReportLab vector
  graphics so it stays crisp at any zoom; falls back to a placeholder
  PNG asset only if you've explicitly dropped one in apps/sales/assets/.

Compliance points retained from the PRAL manual (page 24):
- C/E status flags on individual lines + legend at the bottom
- "NOT YET FBR-VALIDATED" notice when invoice has no FBR number
- Seller / Buyer / Invoice-summary blocks
- Scannable QR code from fbr_qr_payload
"""

from __future__ import annotations

import base64
import io
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from reportlab.graphics.shapes import Drawing, Path as VPath, String, Rect
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer,
    Table, TableStyle,
)

from apps.fbr.qr import render_png_b64
from apps.sales.models import Invoice


# ---------------------------------------------------------------------------
# Design tokens
# ---------------------------------------------------------------------------

# FBR DI palette — sampled from the official PRAL logo:
ACCENT = HexColor("#0d8c5a")       # leaf green, primary
ACCENT_DARK = HexColor("#0a6d46")  # darker for headers
INK = HexColor("#1f2937")          # body text
INK_SOFT = HexColor("#6b7280")     # secondary text
HAIR = HexColor("#e5e7eb")         # rules / dividers
PANEL = HexColor("#f9fafb")        # subtle fill
PANEL_BORDER = HexColor("#e5e7eb")
SUCCESS_BG = HexColor("#ecfdf5")
SUCCESS_FG = HexColor("#065f46")
WARN_BG = HexColor("#fef3c7")
WARN_FG = HexColor("#92400e")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _money(value) -> str:
    if value is None:
        return "0.00"
    d = value if isinstance(value, Decimal) else Decimal(str(value))
    return f"{d:,.2f}"


def _num(value) -> str:
    """Trim trailing zeros: 1.0000 → '1', 1.5000 → '1.5'."""
    if value is None:
        return "0"
    d = value if isinstance(value, Decimal) else Decimal(str(value))
    if d == d.to_integral_value():
        return f"{int(d)}"
    return format(d.normalize(), "f")


def _percent(value) -> str:
    if value is None:
        return "0%"
    return f"{_num(value)}%"


def _b64_to_image(b64: str, *, width_mm: float, height_mm: float) -> Image:
    if b64.startswith("data:"):
        b64 = b64.split(",", 1)[1]
    raw = base64.b64decode(b64)
    img = Image(io.BytesIO(raw), width=width_mm * mm, height=height_mm * mm)
    img.hAlign = "CENTER"
    return img


def _file_image(path: Path | str, *, width_mm: float, height_mm: float) -> Image | None:
    p = Path(path)
    if not p.exists():
        return None
    img = Image(str(p), width=width_mm * mm, height=height_mm * mm)
    img.hAlign = "LEFT"
    return img


def _line_status_marker(item) -> str:
    if getattr(item, "is_cancelled", False):
        return "C"
    if getattr(item, "is_edited", False):
        return "E"
    return ""


# ---------------------------------------------------------------------------
# FBR Digital Invoicing logo — vector rendering
# ---------------------------------------------------------------------------

def _fbr_logo_drawing(*, height_mm: float = 14) -> Drawing:
    """Render the FBR Digital Invoicing wordmark as native ReportLab vector
    graphics. Modeled on the official PRAL mark: a green leaf/teardrop shape
    forming a "D" silhouette, paired with the "DIGITAL / INVOICING" wordmark
    in dark blue.

    Always crisp regardless of zoom; no PNG assets required.
    """
    h = height_mm * mm
    # Whole drawing is 60mm x 14mm by default; scale proportionally to h.
    scale = h / (14 * mm)
    w = 60 * mm * scale

    d = Drawing(w, h)

    # ---- Mark: leaf-shaped "D" (green) -----------------------------------
    # A teardrop-ish path: vertical stem on the left + a curved blade.
    leaf = VPath(
        fillColor=ACCENT,
        strokeColor=None,
    )
    s = scale  # short alias
    # Move to top-left of the stem
    leaf.moveTo(2 * s, 0.5 * mm)
    leaf.lineTo(2 * s, 13.5 * mm * s)
    # Curve out and around to the bottom (the "D" bowl, leaf-shaped)
    leaf.curveTo(
        18 * mm * s, 13.5 * mm * s,
        20 * mm * s, 7 * mm * s,
        12 * mm * s, 0.5 * mm * s,
    )
    leaf.lineTo(2 * s, 0.5 * mm)
    leaf.closePath()
    d.add(leaf)

    # White inner highlight to suggest the leaf vein / page-fold.
    inner = VPath(fillColor=colors.white, strokeColor=None)
    inner.moveTo(4.5 * mm * s, 2.5 * mm * s)
    inner.lineTo(4.5 * mm * s, 11.5 * mm * s)
    inner.curveTo(
        13 * mm * s, 11.5 * mm * s,
        15 * mm * s, 7 * mm * s,
        10 * mm * s, 2.5 * mm * s,
    )
    inner.lineTo(4.5 * mm * s, 2.5 * mm * s)
    inner.closePath()
    d.add(inner)

    # Small green "page corner" inside the white space, completing the D.
    corner = VPath(fillColor=ACCENT, strokeColor=None)
    corner.moveTo(7 * mm * s, 4 * mm * s)
    corner.lineTo(7 * mm * s, 9 * mm * s)
    corner.lineTo(11 * mm * s, 9 * mm * s)
    corner.curveTo(
        12.5 * mm * s, 7 * mm * s,
        10 * mm * s, 5 * mm * s,
        7 * mm * s, 4 * mm * s,
    )
    corner.closePath()
    d.add(corner)

    # ---- Wordmark: "DIGITAL / INVOICING" ---------------------------------
    nav = HexColor("#1e3a8a")  # navy, classic FBR pairing
    d.add(String(
        24 * mm * s, 8 * mm * s,
        "DIGITAL",
        fontName="Helvetica-Bold", fontSize=10 * s, fillColor=nav,
    ))
    d.add(String(
        24 * mm * s, 2.5 * mm * s,
        "INVOICING",
        fontName="Helvetica-Bold", fontSize=10 * s, fillColor=nav,
    ))
    return d


# ---------------------------------------------------------------------------
# Status pill
# ---------------------------------------------------------------------------


def _status_pill(invoice: Invoice) -> Drawing:
    """Small rounded pill rendering the invoice status with a fitting color."""
    status = invoice.status
    if status == "valid":
        bg, fg, label = SUCCESS_BG, SUCCESS_FG, "FBR VALIDATED"
    elif status in ("pending_sync", "submitted"):
        bg, fg, label = WARN_BG, WARN_FG, "PENDING SUBMISSION"
    elif status == "failed":
        bg, fg, label = HexColor("#fee2e2"), HexColor("#991b1b"), "SUBMISSION FAILED"
    elif status in ("cancelled", "partially_cancelled"):
        bg, fg, label = HexColor("#f3f4f6"), HexColor("#374151"), status.upper().replace("_", " ")
    elif status in ("edited", "partially_edited"):
        bg, fg, label = HexColor("#dbeafe"), HexColor("#1e40af"), status.upper().replace("_", " ")
    else:
        bg, fg, label = HexColor("#f3f4f6"), HexColor("#374151"), status.upper()

    width = max(34 * mm, len(label) * 1.7 * mm + 6 * mm)
    height = 5 * mm
    d = Drawing(width, height)
    d.add(Rect(0, 0, width, height, rx=2.5 * mm, ry=2.5 * mm,
               fillColor=bg, strokeColor=None))
    d.add(String(width / 2, 1.6 * mm, label,
                 fontName="Helvetica-Bold", fontSize=7,
                 fillColor=fg, textAnchor="middle"))
    return d


# ---------------------------------------------------------------------------
# Page header / footer (drawn directly on the canvas via onPage)
# ---------------------------------------------------------------------------


def _draw_page_chrome(canvas: Canvas, doc) -> None:
    """Top accent stripe + bottom thin rule + page number."""
    page_w, page_h = A4

    # Top accent stripe (4mm tall, full bleed).
    canvas.saveState()
    canvas.setFillColor(ACCENT)
    canvas.rect(0, page_h - 4 * mm, page_w, 4 * mm, fill=1, stroke=0)
    # Subtle dark band underneath the stripe for depth.
    canvas.setFillColor(ACCENT_DARK)
    canvas.rect(0, page_h - 4.5 * mm, page_w, 0.5 * mm, fill=1, stroke=0)

    # Footer: hairline + page number + tagline. Two rows so the
    # verification URL stands out without crowding the page-number.
    canvas.setStrokeColor(HAIR)
    canvas.setLineWidth(0.5)
    canvas.line(15 * mm, 16 * mm, page_w - 15 * mm, 16 * mm)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(INK_SOFT)
    canvas.drawString(15 * mm, 11 * mm, "Generated by invoicesolution.pk · FBR Digital Invoicing")
    canvas.drawRightString(
        page_w - 15 * mm, 11 * mm,
        f"Page {canvas.getPageNumber()}",
    )
    # Second row — centred verification hint so any printed-paper reader
    # knows where to authenticate.
    canvas.setFont("Helvetica-Oblique", 6)
    canvas.setFillColor(INK_SOFT)
    canvas.drawCentredString(
        page_w / 2, 6.5 * mm,
        "Verify FBR Invoice Number at e.fbr.gov.pk · Scan QR with the FBR Tax Asaan mobile app",
    )
    canvas.restoreState()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def render_invoice_pdf(invoice: Invoice) -> bytes:
    tenant = invoice.tenant
    items = list(invoice.items.select_related("product").order_by("line_number"))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=14 * mm,
        bottomMargin=18 * mm,
        title=f"Invoice {invoice.local_invoice_number}",
        author=tenant.business_name,
    )

    styles = getSampleStyleSheet()
    base = ParagraphStyle("base", parent=styles["Normal"], fontSize=8.5,
                          leading=11, textColor=INK)
    micro = ParagraphStyle("micro", parent=base, fontSize=7, leading=9,
                           textColor=INK_SOFT)
    label = ParagraphStyle("label", parent=base, fontSize=6.5, leading=8,
                           textColor=INK_SOFT,
                           fontName="Helvetica-Bold")
    section = ParagraphStyle("section", parent=base, fontSize=8,
                             leading=10, textColor=ACCENT_DARK,
                             fontName="Helvetica-Bold",
                             spaceAfter=2)
    biz_title = ParagraphStyle("biz", parent=base, fontSize=18, leading=22,
                               textColor=INK, fontName="Helvetica-Bold")
    big_total = ParagraphStyle("big_total", parent=base, fontSize=22,
                               leading=26, textColor=INK, alignment=2,
                               fontName="Helvetica-Bold")
    invoice_label = ParagraphStyle("invoice_label", parent=base, fontSize=10,
                                   leading=12, textColor=INK_SOFT,
                                   fontName="Helvetica-Bold")
    invoice_no = ParagraphStyle("invoice_no", parent=base, fontSize=14,
                                leading=16, textColor=INK,
                                fontName="Helvetica-Bold")

    story: list = []

    # ======================================================================
    # HEADER:  Tenant brand + Invoice summary (left)   |   FBR logo + QR (right)
    # ======================================================================

    # ---- Resolve assets first (same row heights for FBR seal + QR) ------
    # Prefer the compact, print-sized logo (fbrLogo_pdf.png, ~54KB) so the PDF
    # stays small — the full fbrLogo.png is a 1024px/1.3MB asset that bloated
    # the PDF to ~1.8MB when embedded. The compact one renders identically at
    # the 30mm seal size. Fall back to the full logo / historical name.
    assets_dir = Path(settings.BASE_DIR) / "apps" / "sales" / "assets"
    fbr_logo_path = next(
        (p for p in (
            assets_dir / "fbrLogo_pdf.png",
            assets_dir / "fbrLogo.png",
            assets_dir / "fbr_di_logo.png",
        ) if p.exists()),
        assets_dir / "fbr_di_logo.png",
    )
    # Square logo: render same height/width as the QR for a balanced top-right cluster.
    SEAL_SIZE_MM = 30
    fbr_seal = _file_image(fbr_logo_path, width_mm=SEAL_SIZE_MM, height_mm=SEAL_SIZE_MM) \
        if fbr_logo_path.exists() else _fbr_logo_drawing(height_mm=SEAL_SIZE_MM)

    # The QR must encode EXACTLY the FBR fiscal invoice number string — that's
    # what the FBR Tax Asaan app verifies (scanning the QR == typing the
    # number). Encoding our own JSON blob made Tax Asaan report "invalid".
    # Matches the FBR-approved reference POS (barcode generated from the bare
    # FBR InvoiceNumber). Only render once we actually have the FBR number.
    qr_value = invoice.fbr_invoice_number or None
    qr_img = (
        _b64_to_image(render_png_b64(qr_value),
                      width_mm=SEAL_SIZE_MM, height_mm=SEAL_SIZE_MM)
        if qr_value else None
    )

    # ---- Left column: tenant identity + invoice summary -----------------
    tenant_logo = _file_image(
        Path(settings.MEDIA_ROOT) / "tenants" / f"{tenant.id}-logo.png",
        width_mm=18, height_mm=18,
    )

    contact_bits = [f"NTN <b>{tenant.ntn}</b>"]
    if tenant.strn:
        contact_bits.append(f"STRN <b>{tenant.strn}</b>")
    if tenant.phone:
        contact_bits.append(tenant.phone)
    if tenant.email:
        contact_bits.append(tenant.email)

    # Invoice summary goes inline below the tenant block — labelled
    # key/value pairs in a tight 2-column grid for scannability.
    summary_rows: list[list] = [
        [Paragraph("INVOICE NUMBER", label),
         Paragraph(f"<b>{invoice.local_invoice_number}</b>", base)],
        [Paragraph("INVOICE DATE", label),
         Paragraph(invoice.invoice_date.strftime("%d %b %Y"), base)],
    ]
    if invoice.fbr_invoice_number:
        summary_rows.append([
            Paragraph("FBR INVOICE", label),
            Paragraph(
                f"<font color='#0a6d46'><b>{invoice.fbr_invoice_number}</b></font>",
                base,
            ),
        ])
    summary_rows.append([
        Paragraph("STATUS", label),
        _status_pill(invoice),
    ])

    summary_table = Table(summary_rows, colWidths=[34 * mm, None])
    summary_table.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))

    left_block: list = []
    if tenant_logo:
        # Logo + business name on the same line.
        brand_row = Table(
            [[tenant_logo, Paragraph(tenant.business_name, biz_title)]],
            colWidths=[22 * mm, None],
        )
        brand_row.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        left_block.append(brand_row)
    else:
        left_block.append(Paragraph(tenant.business_name, biz_title))
    if tenant.address:
        left_block.append(Spacer(1, 2))
        left_block.append(Paragraph(tenant.address.replace("\n", "<br/>"), micro))
    left_block.append(Spacer(1, 1))
    left_block.append(Paragraph(" &nbsp;·&nbsp; ".join(contact_bits), micro))
    left_block.append(Spacer(1, 8))
    left_block.append(summary_table)

    # ---- Right column: FBR logo + QR, side by side at equal heights -----
    right_cells: list[list] = []
    if qr_img:
        # Two equal-size squares side by side — clean and balanced.
        right_cells.append([fbr_seal, qr_img])
        right_widths = [SEAL_SIZE_MM * mm + 2 * mm, SEAL_SIZE_MM * mm]
        # Caption row under each (small grey text).
        right_cells.append([
            Paragraph("<font color='#6b7280' size='6'><b>FBR DIGITAL INVOICING</b></font>", micro),
            Paragraph("<font color='#6b7280' size='6'><b>SCAN TO VERIFY</b></font>", micro),
        ])
    else:
        right_cells.append([fbr_seal])
        right_widths = [SEAL_SIZE_MM * mm]
        right_cells.append([
            Paragraph("<font color='#6b7280' size='6'><b>FBR DIGITAL INVOICING</b></font>", micro),
        ])

    right_panel = Table(right_cells, colWidths=right_widths)
    right_panel.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, 0), 0),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
        ("TOPPADDING", (0, 1), (-1, 1), 4),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 0),
        ("VALIGN", (0, 0), (-1, 0), "TOP"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))

    header = Table(
        [[left_block, right_panel]],
        # Right column wide enough for two squares + their captions.
        colWidths=[None, SEAL_SIZE_MM * 2 * mm + 4 * mm],
    )
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(header)
    story.append(Spacer(1, 12))

    # ---- Divider rule below the header ----
    story.append(_horizontal_rule(width_pt=doc.width))
    story.append(Spacer(1, 10))

    # ======================================================================
    # PARTIES — Bill From  |  Bill To  (two cards, side by side)
    # ======================================================================

    seller_kv: list[tuple[str, str]] = [
        ("Branch", f"{invoice.branch.name} ({invoice.branch.code})"),
        ("NTN", tenant.ntn),
        ("STRN", tenant.strn or "—"),
        ("Province", tenant.province),
    ]
    buyer_kv: list[tuple[str, str]] = []
    if invoice.buyer_ntn_cnic:
        buyer_kv.append(("NTN/CNIC", invoice.buyer_ntn_cnic))
    if invoice.buyer_registration_type:
        buyer_kv.append(("Type", invoice.buyer_registration_type))
    if invoice.buyer_province:
        buyer_kv.append(("Province", invoice.buyer_province))
    if invoice.buyer_phone:
        buyer_kv.append(("Phone", invoice.buyer_phone))
    if invoice.buyer_address:
        buyer_kv.append(("Address", invoice.buyer_address))
    if not buyer_kv:
        buyer_kv = [("Type", "Unregistered walk-in")]

    # Pad the shorter list with empty rows so both cards have identical
    # row count (and therefore identical visual height).
    target_rows = max(len(seller_kv), len(buyer_kv))
    while len(seller_kv) < target_rows:
        seller_kv.append(("", ""))
    while len(buyer_kv) < target_rows:
        buyer_kv.append(("", ""))

    seller_card = _party_card(
        title="BILL FROM",
        primary=tenant.business_name,
        rows=seller_kv,
        styles=(label, base),
    )
    buyer_card = _party_card(
        title="BILL TO",
        primary=invoice.buyer_name or "Walk-in customer",
        rows=buyer_kv,
        styles=(label, base),
    )

    parties = Table(
        [[seller_card, buyer_card]],
        colWidths=[doc.width / 2 - 4 * mm, doc.width / 2 - 4 * mm],
    )
    parties.setStyle(TableStyle([
        # CRITICAL: stretch each cell to the full row height so the
        # accent panel BACKGROUND on each card extends visually flush.
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(parties)
    story.append(Spacer(1, 14))

    # ======================================================================
    # LINE ITEMS — slim table, only relevant columns
    # ======================================================================

    has_any_discount = any(
        Decimal(str(getattr(it, "discount_amount", 0) or 0)) > 0 for it in items
    )
    has_any_hs_code = any((it.hs_code or "").strip() for it in items)
    has_any_status = any(_line_status_marker(it) for it in items)

    # ---- Column definitions ---------------------------------------------
    # (header_label, width_mm or None for flex, align "L"|"R"|"C")
    columns: list[tuple[str, float | None, str]] = [("#", 9, "L")]
    if has_any_hs_code:
        columns.append(("HS Code", 22, "L"))
    columns.append(("Item", None, "L"))     # flex
    columns += [
        ("Qty",    14, "R"),
        ("Unit",   14, "C"),
        ("Rate",   22, "R"),
    ]
    if has_any_discount:
        columns.append(("Disc.", 20, "R"))
    columns += [
        ("Tax %",  16, "R"),
        ("Tax",    22, "R"),
        ("Amount", 26, "R"),
    ]
    if has_any_status:
        columns.append(("", 9, "C"))

    fixed_mm = sum(w for _, w, _ in columns if w is not None)
    flex_w = doc.width - fixed_mm * mm
    col_widths = [(w * mm) if w is not None else flex_w for _, w, _ in columns]

    # Item column index — only column whose cell needs Paragraph wrapping
    # (multi-line product name + SKU). Every other column uses a plain
    # string so the table-level ALIGN sets the position exactly.
    item_col = next(i for i, (label, _, _) in enumerate(columns) if label == "Item")

    item_para_style = ParagraphStyle(
        "item_cell", parent=base, fontSize=9, leading=11, alignment=0,
    )

    # ---- Header row (plain strings — table-level ALIGN positions them) --
    head_row = [label for label, _, _ in columns]

    # ---- Body rows ------------------------------------------------------
    body_rows: list[list] = []
    for it in items:
        row: list = [f"{it.line_number:02d}"]
        if has_any_hs_code:
            row.append(it.hs_code or "—")
        row.append(Paragraph(
            f"<b>{getattr(it, 'product_name', '')}</b><br/>"
            f"<font color='#9ca3af' size='7'>{getattr(it, 'product_sku', '')}</font>",
            item_para_style,
        ))
        row += [
            _num(it.quantity),
            it.uom_code or "",
            _money(it.unit_price),
        ]
        if has_any_discount:
            row.append(_money(getattr(it, "discount_amount", 0) or 0))
        row += [
            _percent(it.tax_rate),
            _money(it.tax_amount),
            _money(it.line_total),
        ]
        if has_any_status:
            row.append(_line_status_marker(it))
        body_rows.append(row)

    items_table = Table(
        [head_row] + body_rows,
        colWidths=col_widths,
        repeatRows=1,
    )

    # Build per-column ALIGN ops so header and body align identically.
    align_map = {"L": "LEFT", "R": "RIGHT", "C": "CENTER"}
    align_ops = [
        ("ALIGN", (i, 0), (i, -1), align_map[align])
        for i, (_, _, align) in enumerate(columns)
    ]

    items_table.setStyle(TableStyle([
        # Identical vertical centering.
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        # Header typography: small caps grey on white.
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7),
        ("TEXTCOLOR", (0, 0), (-1, 0), INK_SOFT),
        # Body typography.
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("TEXTCOLOR", (0, 1), (-1, -1), INK),
        # Per-column alignment (header + body, identical).
        *align_ops,
        # Bold the # column lightly + Amount column heavily.
        ("TEXTCOLOR", (0, 1), (0, -1), HexColor("#9ca3af")),
        ("FONTNAME", (len(columns) - (2 if has_any_status else 1), 1),
                       (len(columns) - (2 if has_any_status else 1), -1),
                       "Helvetica-Bold"),
        # Status flag colored.
        *([("TEXTCOLOR", (-1, 1), (-1, -1), HexColor("#dc2626"))]
          if has_any_status else []),
        # Rules: heavier under header, hairline between rows, heavier under last.
        ("LINEBELOW", (0, 0), (-1, 0), 0.7, INK),
        ("LINEBELOW", (0, 1), (-1, -2), 0.25, HAIR),
        ("LINEBELOW", (0, -1), (-1, -1), 0.6, INK),
        # Symmetric padding — same on every cell so columns sit on a grid.
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, 0), 7),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 7),
        ("TOPPADDING", (0, 1), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 8),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 10))

    # ======================================================================
    # TOTALS BOX — right-aligned summary card
    # ======================================================================

    # Build totals_rows with PLAIN STRINGS (not Paragraphs). The table-
    # level ALIGN op then positions them exactly like the items-table
    # cells, which is what makes the numeric column edges line up.
    totals_rows: list[tuple[str, str]] = [("Subtotal", _money(invoice.subtotal))]
    if Decimal(str(invoice.discount_total or 0)) > 0:
        totals_rows.append(("Discount", f"-{_money(invoice.discount_total)}"))
    totals_rows.append(("Sales Tax", _money(invoice.tax_total)))
    if Decimal(str(getattr(invoice, "further_tax_total", 0) or 0)) > 0:
        totals_rows.append(("Further Tax", _money(invoice.further_tax_total)))
    if Decimal(str(getattr(invoice, "fed_total", 0) or 0)) > 0:
        totals_rows.append(("FED", _money(invoice.fed_total)))
    totals_rows.append(("GRAND TOTAL", f"Rs. {_money(invoice.grand_total)}"))

    paid = Decimal(str(invoice.paid_total or 0))
    grand = Decimal(str(invoice.grand_total or 0))
    balance = grand - paid
    if abs(balance) > Decimal("0.01"):
        totals_rows.append(("Paid", _money(paid)))
        totals_rows.append(("Balance", _money(balance)))

    grand_idx = next(
        (i for i, (label, _) in enumerate(totals_rows) if label == "GRAND TOTAL"),
        len(totals_rows) - 1,
    )

    # Build the totals as ONE table spanning the full content width and
    # using the SAME column widths as the items table for the value rail.
    # This guarantees the value column's right edge lands exactly under
    # the items-table Amount column's right edge.
    #
    # Layout: [   spacer   ] [ label ] [ value ]
    # value column width = items table Amount column width (+ status if any)
    # label column width = items table (Tax % + Tax) columns combined
    amount_idx = len(columns) - (2 if has_any_status else 1)
    items_amount_right_edge = col_widths[amount_idx]
    if has_any_status:
        # Status column gets folded in so the totals right edge meets the
        # items-table right edge (not the items-table Amount edge).
        items_amount_right_edge += col_widths[-1]

    # ---- Dynamic value column width ------------------------------------
    # The value column must be wide enough for the longest value text
    # (with breathing room) so big numbers like "Rs. 20,000,000.00"
    # never collide with the label. We measure each value's actual
    # rendered width with the font size that will be used for it.
    body_font = "Helvetica"
    grand_font = "Helvetica-Bold"
    body_font_size = 9
    grand_font_size = 13
    value_padding = 6  # pt on each side of the value column

    longest_value_w = 0.0
    for label_text, value_text in totals_rows:
        font = grand_font if label_text == "GRAND TOTAL" else body_font
        size = grand_font_size if label_text == "GRAND TOTAL" else body_font_size
        w = stringWidth(value_text, font, size)
        longest_value_w = max(longest_value_w, w)

    # Value column width = longest value text + 2× padding, with a sane
    # minimum so short values still get a reasonable column.
    value_w = max(
        items_amount_right_edge,        # never narrower than items Amount col
        longest_value_w + value_padding * 2,
    )

    # Label gap: a fixed visual gap (e.g. 18pt) is enough now that the
    # value column auto-grows when needed.
    label_value_gap = 18  # pt

    # Label column: starts wide enough for the longest label too, then
    # absorbs whatever's left over from the spacer beyond a sensible
    # minimum. The label column right padding gives the visible gap.
    longest_label_w = 0.0
    for label_text, _ in totals_rows:
        font = grand_font if label_text == "GRAND TOTAL" else body_font
        size = grand_font_size if label_text == "GRAND TOTAL" else body_font_size
        w = stringWidth(label_text, font, size)
        longest_label_w = max(longest_label_w, w)

    # Same overall section width as before (~ items table Amount columns
    # plus 30mm of label area) — we just rebalance the internal widths.
    SECTION_WIDTH_EXTRA_MM = 30
    section_w = (
        col_widths[amount_idx - 2] + col_widths[amount_idx - 1]
        + SECTION_WIDTH_EXTRA_MM * mm
        + items_amount_right_edge
    )
    label_w = max(
        section_w - value_w,
        longest_label_w + label_value_gap + value_padding,
    )
    spacer_w = doc.width - value_w - label_w

    totals3: list[list] = [["", label, value] for label, value in totals_rows]

    totals_box = Table(totals3, colWidths=[spacer_w, label_w, value_w])
    totals_box.setStyle(TableStyle([
        # Identical typography baseline so labels and values align.
        ("FONTNAME", (1, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (1, 0), (-1, -1), 9),
        ("TEXTCOLOR", (1, 0), (-1, -1), INK),
        # Label column right-aligned; value column right-aligned to match
        # items-table Amount column (which is also right-aligned).
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("ALIGN", (2, 0), (2, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        # Top/bottom padding consistent with items table.
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        # Spacer column has no content.
        ("LEFTPADDING", (0, 0), (0, -1), 0),
        ("RIGHTPADDING", (0, 0), (0, -1), 0),
        # Label column padding. The right padding IS the visible gap
        # between labels and values — fixed in points so the gap stays
        # consistent across invoices regardless of how big the values get
        # (the value column auto-widens when needed).
        ("LEFTPADDING", (1, 0), (1, -1), 6),
        ("RIGHTPADDING", (1, 0), (1, -1), label_value_gap),
        # Value column: 6pt right padding to MATCH the items-table Amount
        # column's right edge exactly; left padding doesn't matter for
        # right-aligned text.
        ("LEFTPADDING", (2, 0), (2, -1), 6),
        ("RIGHTPADDING", (2, 0), (2, -1), 6),
        # Grand-total row: green accent rules + soft fill, slightly bigger
        # font but NOT so big it overflows the column.
        ("FONTNAME", (1, grand_idx), (2, grand_idx), "Helvetica-Bold"),
        ("FONTSIZE", (1, grand_idx), (1, grand_idx), 9),
        ("FONTSIZE", (2, grand_idx), (2, grand_idx), 13),
        ("TEXTCOLOR", (1, grand_idx), (1, grand_idx), INK),
        ("TEXTCOLOR", (2, grand_idx), (2, grand_idx), ACCENT_DARK),
        ("BACKGROUND", (1, grand_idx), (2, grand_idx), PANEL),
        ("LINEABOVE", (1, grand_idx), (2, grand_idx), 0.6, ACCENT),
        ("LINEBELOW", (1, grand_idx), (2, grand_idx), 0.6, ACCENT),
        ("TOPPADDING", (1, grand_idx), (2, grand_idx), 7),
        ("BOTTOMPADDING", (1, grand_idx), (2, grand_idx), 7),
    ]))
    story.append(totals_box)
    story.append(Spacer(1, 14))

    # ======================================================================
    # NOTES + LEGEND + FBR FOOTER
    # ======================================================================

    if invoice.notes:
        story.append(Paragraph("NOTES", section))
        story.append(Paragraph(invoice.notes.replace("\n", "<br/>"), micro))
        story.append(Spacer(1, 8))

    if has_any_status:
        story.append(Paragraph(
            '<font color="#6b7280" size="7">Status flags: '
            '<font color="#dc2626"><b>C</b></font> = item cancelled · '
            '<font color="#d97706"><b>E</b></font> = item edited.</font>',
            micro,
        ))
        story.append(Spacer(1, 4))

    if not invoice.fbr_invoice_number:
        story.append(KeepTogether([
            Spacer(1, 4),
            Paragraph(
                '<para backColor="#fef3c7" leftIndent="10" rightIndent="10" '
                'spaceBefore="6" spaceAfter="6">'
                '<font color="#92400e" size="8"><b>Not yet FBR-validated.</b> '
                'This invoice has not been confirmed by PRAL and the QR code is '
                'intentionally absent. Once submitted successfully, this PDF will '
                'include a scannable FBR QR code.</font></para>',
                base,
            ),
        ]))

    # ======================================================================
    # AUTHENTICATION + DISCLAIMER (footer block)
    # ======================================================================
    # Short paragraphs the auditor / buyer typically wants to see on a
    # tax-compliant invoice:
    #   1. FBR authentication — how to verify the QR / invoice number
    #   2. Computer-generated disclaimer

    story.append(Spacer(1, 10))

    # FBR authentication block — only when the invoice has a real FBR number.
    if invoice.fbr_invoice_number:
        story.append(Paragraph(
            '<font color="#15803d" size="7"><b>FBR AUTHENTICATION</b></font>',
            micro,
        ))
        story.append(Paragraph(
            '<font color="#374151" size="7">'
            f'This invoice was submitted to FBR Digital Invoicing and validated by '
            f'PRAL on <b>{invoice.fbr_validated_at.strftime("%d %b %Y, %H:%M") if invoice.fbr_validated_at else (invoice.updated_at.strftime("%d %b %Y, %H:%M") if invoice.updated_at else "—")}</b>. '
            f'FBR Invoice Number: '
            f'<font face="Courier"><b>{invoice.fbr_invoice_number}</b></font>. '
            'To verify, scan the QR code with the FBR <b>Tax Asaan</b> app or look the '
            'number up at <b>e.fbr.gov.pk</b>. If the number cannot be verified there, '
            'the invoice is not authentic.'
            '</font>',
            micro,
        ))
        story.append(Spacer(1, 6))

    # Computer-generated disclaimer (always shown).
    story.append(Paragraph(
        '<font color="#9ca3af" size="7">'
        'This is a computer-generated invoice and does not require a physical signature. '
        'Errors and omissions excepted. Goods sold are not returnable except under our '
        'documented returns policy.'
        '</font>',
        micro,
    ))
    story.append(Spacer(1, 2))
    story.append(Paragraph(
        '<font color="#9ca3af" size="6">'
        'Issued via invoicesolution.pk · FBR Digital Invoicing compliant.'
        '</font>',
        micro,
    ))

    doc.build(story, onFirstPage=_draw_page_chrome, onLaterPages=_draw_page_chrome)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Component helpers
# ---------------------------------------------------------------------------


def _two_col_trailer(left, right) -> Table:
    """Two-column compact row used in the header trailer (FBR seal | QR)."""
    t = Table([[left, right]], colWidths=[34 * mm, 30 * mm])
    t.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (0, 0), "LEFT"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
    ]))
    return t


def _horizontal_rule(*, width_pt: float) -> Drawing:
    """A 0.5pt grey hairline."""
    d = Drawing(width_pt, 1)
    d.add(Rect(0, 0, width_pt, 0.5, fillColor=HAIR, strokeColor=None))
    return d


def _party_card(*, title: str, primary: str,
                rows: list[tuple[str, str]],
                styles) -> Table:
    """The "Bill From / Bill To" panel — title pill + primary name + key/value
    list, all inside a soft rounded panel feel (rendered via a single-cell
    table with a left accent border)."""
    label_style, body_style = styles

    inner_rows: list[list] = [
        [Paragraph(f'<font color="#0a6d46"><b>{title}</b></font>', label_style)],
        [Paragraph(f"<b>{primary}</b>", ParagraphStyle(
            "primary", parent=body_style, fontSize=11, leading=14,
        ))],
    ]
    for k, v in rows:
        if not k and not v:
            # Padding row — invisible spacer to equalize card height
            # against the sibling card. Use a thin Spacer-equivalent.
            inner_rows.append([Paragraph("&nbsp;", body_style)])
        else:
            inner_rows.append([Paragraph(
                f'<font color="#9ca3af" size="6.5">{k.upper()}</font> &nbsp; '
                f'<font color="#1f2937" size="9">{v}</font>',
                body_style,
            )])

    card = Table(inner_rows, colWidths=[None])
    card.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, 0), 8),     # title row top padding
        ("BOTTOMPADDING", (0, 1), (-1, 1), 6),  # gap after primary name
        ("BOTTOMPADDING", (0, -1), (-1, -1), 8),
        # Soft panel: left accent stripe + light fill.
        ("BACKGROUND", (0, 0), (-1, -1), PANEL),
        ("LINEBEFORE", (0, 0), (0, -1), 2.5, ACCENT),
    ]))
    return card
