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
    #
    # Exclude credit-note / return-reference rows (suffix like '-CN' or
    # an 'R' prefix on the sequence). They share the terminal+year scope
    # but use their own numbering namespace ('R0000001-CN'), which would
    # otherwise confuse the trailing-digit parse and cause sequence
    # collisions.
    # Only COMPLETED (charged, not-held) invoices advance the sequence, so the
    # invoice number is minted only at charge time — an open/held order or a
    # voided draft never consumes a number. This keeps completed-invoice numbers
    # gapless per terminal per day (the reported "closed at 0032, reopened at
    # 0036" gaps came from held/voided orders burning numbers).
    last = (
        Invoice.objects.filter(
            terminal=locked_terminal, invoice_date__year=year, is_held=False,
        )
        .exclude(invoice_type__in=("credit_note", "debit_note"))
        .order_by("-local_invoice_number")
        .values_list("local_invoice_number", flat=True)
        .first()
    )
    seq = _parse_seq(last) + 1 if last else 1

    # Terminal index: the STABLE per-branch ordinal assigned at creation
    # (terminal_index). This guarantees two terminals in the same branch get
    # distinct number namespaces (…-T1-… vs …-T2-…) and never collide on the
    # (tenant, local_invoice_number) unique constraint. Fall back to a
    # name-derived digit only for any legacy row that somehow lacks an index.
    t_index = locked_terminal.terminal_index or _terminal_index(locked_terminal.name)
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
