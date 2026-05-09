"""Streaming CSV export.

Uses Django's StreamingHttpResponse with a pseudo-file 'echo' writer so
huge reports never buffer fully in memory. Money columns are formatted
'Rs. 1,234.56' per the constraint in CLAUDE_CODE_PROMPTS Phase 7.
"""

from __future__ import annotations

import csv
from decimal import Decimal
from typing import Iterable

from django.http import StreamingHttpResponse

from ..base import Column, ReportResult


class _Echo:
    """File-like object whose write() returns the value, so csv.writer can
    emit one row per next() call to StreamingHttpResponse."""

    def write(self, value):
        return value


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


def _stream_rows(columns: list[Column], rows: Iterable[dict]):
    writer = csv.writer(_Echo())
    yield writer.writerow([c.label for c in columns])
    for row in rows:
        yield writer.writerow([_format(row.get(c.key), c.kind) for c in columns])


def streaming_csv_response(result: ReportResult, *, filename: str) -> StreamingHttpResponse:
    response = StreamingHttpResponse(
        _stream_rows(result.columns, result.rows),
        content_type="text/csv; charset=utf-8",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
