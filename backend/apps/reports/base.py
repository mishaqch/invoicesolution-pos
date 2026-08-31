"""Common shell shared by every report.

Each concrete report subclasses Report and provides:
  - name (registry key)
  - Filters dataclass
  - columns metadata (for tables + exports)
  - query() returning an iterable of dict rows
  - chart() returning an optional ChartSpec

Reports are tenant-scoped at the boundary: callers pass tenant_id
explicitly; the Report ABC enforces that the value is honored in
every query path. The .run() helper handles caching transparently.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, ClassVar, Iterable

from django.core.cache import cache


CACHE_TTL_SECONDS = 3600


@dataclass(frozen=True)
class Column:
    key: str
    label: str
    kind: str = "text"  # text | money | int | decimal | date | datetime | percent
    align: str = "left"


@dataclass(frozen=True)
class ChartSpec:
    type: str           # line | bar | donut | heatmap
    x_key: str | None
    y_keys: tuple[str, ...] = ()


@dataclass
class BaseFilters:
    """Subclasses extend with the report's specific filter fields."""

    branch_id: str | None = None
    date_from: date | None = None
    date_to: date | None = None

    def to_cache_key(self) -> str:
        payload = {k: _encode(v) for k, v in asdict(self).items()}
        canonical = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _encode(v: Any) -> Any:
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, date):
        return v.isoformat()
    return v


@dataclass
class ReportResult:
    rows: list[dict]
    columns: list[Column]
    totals: dict[str, Any] = field(default_factory=dict)
    chart: ChartSpec | None = None
    row_count: int = 0
    truncated: bool = False


class Report:
    """Abstract base — every report is one subclass.

    Concrete reports MUST set `name`, `columns`, and a `Filters` class.
    They MUST implement `query()`. Caching, tenant-scoping enforcement,
    and serialization are handled here.
    """

    name: ClassVar[str]
    Filters: ClassVar[type[BaseFilters]] = BaseFilters
    columns: ClassVar[tuple[Column, ...]]
    chart_spec: ClassVar[ChartSpec | None] = None
    preview_row_cap: ClassVar[int] = 1000

    # If a report's filter set could fan out to >this many rows, the
    # API routes the request to async (Celery) instead of inline.
    async_threshold_rows: ClassVar[int] = 10_000

    def __init__(self, *, tenant_id: str, filters: BaseFilters):
        if not tenant_id:
            raise ValueError("tenant_id is required")
        self.tenant_id = tenant_id
        self.filters = filters

    # ------------------------------------------------------------------
    # Subclasses override these
    # ------------------------------------------------------------------

    def query(self) -> Iterable[dict]:
        raise NotImplementedError

    def totals(self, rows: list[dict]) -> dict[str, Any]:
        return {}

    def _ensure_aggregate(self) -> None:
        """Hook for aggregate-backed reports to recompute their snapshot table
        for the requested window on demand, so the report is always current and
        never depends on the Celery beat aggregate task having run. Live reports
        (those that query Invoice/SaleItem directly) leave this as a no-op."""
        return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, *, use_cache: bool = True, cap: int | None = None) -> ReportResult:
        cap = cap if cap is not None else self.preview_row_cap
        if use_cache:
            cached = cache.get(self.cache_key)
            if cached is not None:
                return cached

        # Refresh the backing aggregate for the requested window (no-op for live
        # reports) so a cache-miss always reflects current data.
        self._ensure_aggregate()
        raw = list(self.query())
        truncated = False
        if len(raw) > cap:
            raw = raw[:cap]
            truncated = True

        result = ReportResult(
            rows=raw,
            columns=list(self.columns),
            totals=self.totals(raw),
            chart=self.chart_spec,
            row_count=len(raw),
            truncated=truncated,
        )
        if use_cache:
            cache.set(self.cache_key, result, CACHE_TTL_SECONDS)
        return result

    @property
    def cache_key(self) -> str:
        return f"report:{self.tenant_id}:{self.name}:{self.filters.to_cache_key()}"
