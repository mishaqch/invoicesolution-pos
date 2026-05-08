"""Local invoice number generator.

Format: BRANCH-T#-YYYY-NNNN
  e.g.   DHA-T1-2026-0001234

Monotonic per terminal per year. Resets on January 1.

Concurrency: select_for_update on the terminal row + a sequence counter
stored on Terminal.printer_config (transient field; we just need an
atomic place that's per-terminal). The Phase 2 plan called this out.
"""

from __future__ import annotations

import datetime as dt

from django.db import transaction

from apps.sales.models import Invoice
from apps.tenants.models import Branch, Terminal


@transaction.atomic
def next_invoice_number(*, terminal: Terminal) -> str:
    """Mint the next sequential invoice number for the given terminal.

    select_for_update on the terminal locks out concurrent calls.
    """
    branch: Branch = (
        Branch.objects.select_for_update()
        .get(pk=terminal.branch_id)
    )
    locked_terminal = Terminal.objects.select_for_update().get(pk=terminal.pk)

    today = dt.date.today()
    year = today.year

    # Use the existing invoices count for this terminal in this year as the
    # source of truth — no separate counter table needed at our scale, and
    # it's self-healing if anything ever drifts.
    last = (
        Invoice.objects.filter(
            terminal=locked_terminal, invoice_date__year=year,
        )
        .order_by("-local_invoice_number")
        .values_list("local_invoice_number", flat=True)
        .first()
    )
    seq = _parse_seq(last) + 1 if last else 1

    # Terminal index inferred from the terminal's name (e.g., "Counter 1" -> 1).
    # Falls back to 1 if not parseable; admin should set names like "T1", "T2".
    t_index = _terminal_index(locked_terminal.name)
    return f"{branch.code}-T{t_index}-{year}-{seq:07d}"


def _parse_seq(local_no: str) -> int:
    """Return the trailing NNNNNNN as int."""
    try:
        return int(local_no.rsplit("-", 1)[-1])
    except (ValueError, IndexError):
        return 0


def _terminal_index(name: str) -> int:
    """Pull a leading digit out of a terminal name. Best-effort."""
    digits = "".join(ch for ch in name if ch.isdigit())
    return int(digits) if digits else 1
