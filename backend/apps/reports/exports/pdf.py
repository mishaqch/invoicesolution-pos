"""PDF export via reportlab.

Layout: tenant header (business name + NTN), report title, generated-at
timestamp, then the data table. ReportLab's SimpleDocTemplate handles
pagination automatically; long reports paginate cleanly.

Note: the spec mentioned WeasyPrint, which would let us style with HTML.
We picked reportlab instead because it has no native deps (no cairo/
pango/gtk required in the docker image), keeping the docker layer
small. The output is still a properly formatted PDF with branding.
"""

from __future__ import annotations

import io
from decimal import Decimal

from django.http import HttpResponse
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from ..base import Column, ReportResult


def _format(value, kind: str) -> str:
    if value is None:
        return ""
    if kind == "money":
        d = value if isinstance(value, Decimal) else Decimal(str(value))
        return f"Rs. {d:,.2f}"
    if kind == "percent":
        d = value if isinstance(value, Decimal) else Decimal(str(value))
        return f"{d:.2f}%"
    return str(value)


def pdf_response(
    result: ReportResult, *,
    filename: str, title: str,
    tenant_business_name: str, tenant_ntn: str,
) -> HttpResponse:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4),
        leftMargin=12 * mm, rightMargin=12 * mm,
        topMargin=12 * mm, bottomMargin=12 * mm,
        title=title,
    )
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph(f"<b>{tenant_business_name}</b>  ·  NTN {tenant_ntn}", styles["Title"]))
    story.append(Paragraph(title, styles["Heading2"]))
    story.append(Paragraph(
        f"Generated {timezone.now().strftime('%Y-%m-%d %H:%M')}",
        styles["Italic"],
    ))
    story.append(Spacer(1, 6))

    header_row = [c.label for c in result.columns]
    body = [
        [_format(row.get(c.key), c.kind) for c in result.columns]
        for row in result.rows
    ]
    table_data = [header_row] + body if body else [header_row, ["(no rows)"] + [""] * (len(header_row) - 1)]

    table = Table(table_data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F2937")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E5E7EB")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
    ]))
    story.append(table)

    doc.build(story)
    buf.seek(0)

    response = HttpResponse(buf.read(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
