"""Return number generator. Format: BRANCH-T#-YYYY-Rxxxxxxx (R-prefixed).

Uses the same monotonic-per-(terminal,year) pattern as invoice numbering,
but lives on its own counter so return numbers are independent of invoice
numbers.
"""

from __future__ import annotations

import datetime as dt

from django.db import transaction

from apps.returns.models import Return
from apps.tenants.models import Branch, Terminal


@transaction.atomic
def next_return_number(*, terminal: Terminal) -> str:
    branch: Branch = (
        Branch.objects.select_for_update().get(pk=terminal.branch_id)
    )
    locked = Terminal.objects.select_for_update().get(pk=terminal.pk)

    today = dt.date.today()
    year = today.year

    last = (
        Return.objects.filter(terminal=locked, return_date__year=year)
        .order_by("-return_number")
        .values_list("return_number", flat=True)
        .first()
    )
    seq = _parse_seq(last) + 1 if last else 1
    t_index = _terminal_index(locked.name)
    return f"{branch.code}-T{t_index}-{year}-R{seq:07d}"


def _parse_seq(return_no: str) -> int:
    try:
        # …-Rxxxxxxx → strip the 'R'
        return int(return_no.rsplit("-R", 1)[-1])
    except (ValueError, IndexError):
        return 0


def _terminal_index(name: str) -> int:
    digits = "".join(ch for ch in name if ch.isdigit())
    return int(digits) if digits else 1
