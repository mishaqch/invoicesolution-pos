"""Implicit branch + terminal for office-invoice tenants.

Some tenants (wholesalers, service providers, freelancers issuing FBR
digital invoices from a laptop) have no physical store, no cashiers,
no counters. They don't need to think about "branches" or "terminals"
— they just want to mint an FBR-validated invoice.

The Invoice schema requires a branch + terminal foreign key (numbering
and auditing depend on them), so for these tenants we transparently
create a single hidden default branch + terminal the first time they
need one. The values get reused on every subsequent invoice — the
tenant never sees a "branch" or "terminal" concept anywhere in their
UI when the matching modules are disabled.

Idempotent: callable any number of times; only creates rows on the
very first call per tenant.
"""

from __future__ import annotations

from django.db import transaction

from .models import Branch, Terminal, Tenant


# Sentinel codes — let support staff identify auto-created rows when
# they peek into the database. Not exposed to the tenant.
_IMPLICIT_BRANCH_CODE = "HQ"
_IMPLICIT_TERMINAL_NAME = "Office"
_IMPLICIT_DEVICE_FINGERPRINT_PREFIX = "implicit-"


@transaction.atomic
def ensure_implicit_branch_and_terminal(tenant: Tenant) -> tuple[Branch, Terminal]:
    """Return (branch, terminal) for this tenant, creating defaults if
    the tenant has none. Use this on the office-invoice path where the
    caller can't pass an explicit branch/terminal UUID.

    Selection rules:
      - If the tenant already has at least one branch and at least one
        terminal, return the first of each (deterministic ordering by
        creation time + name).
      - Otherwise, create a single "HQ" branch and a single "Office"
        terminal under it.

    The created rows are real DB rows — they participate in stock
    movements, audit trails, FBR submissions just like any explicit
    branch / terminal would. They're just never exposed in the UI for
    tenants whose `branches` / `terminals` modules are disabled.
    """
    branch = (
        Branch.objects.filter(tenant=tenant, deleted_at__isnull=True)
        .order_by("created_at", "name")
        .first()
    )
    if branch is None:
        branch = Branch.objects.create(
            tenant=tenant,
            name="HQ",
            code=_IMPLICIT_BRANCH_CODE,
            address=tenant.address or "",
            city="",
            province=tenant.province or "PUNJAB",
            is_default=True,
            is_active=True,
        )

    terminal = (
        Terminal.objects.filter(tenant=tenant, branch=branch)
        .order_by("created_at", "name")
        .first()
    )
    if terminal is None:
        terminal = Terminal.objects.create(
            tenant=tenant,
            branch=branch,
            name=_IMPLICIT_TERMINAL_NAME,
            device_fingerprint=f"{_IMPLICIT_DEVICE_FINGERPRINT_PREFIX}{tenant.id}",
            is_active=True,
        )

    return branch, terminal
