"""Seed HS codes.

Idempotent. By default loads the bundled compact subset (~120 codes covering
common Pakistani retail categories). Pass --from-fbr to fetch the full FBR
list (not implemented in Phase 1 — placeholder for the integration that
lands when PRAL-side onboarding is in scope).
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalog.models import HsCode, UnitOfMeasure

DATA_FILE = Path(__file__).parent / "data" / "hs_codes_seed.json"


class Command(BaseCommand):
    help = "Seed the HS code catalog from a bundled JSON (default) or FBR (--from-fbr)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--from-fbr",
            action="store_true",
            help="Fetch the full FBR HS code list instead of the bundled subset.",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Wipe the table before seeding.",
        )

    def handle(self, *args, **opts):
        if opts["from_fbr"]:
            raise CommandError(
                "--from-fbr is reserved for the FBR onboarding phase. "
                "For now, run without the flag to seed the bundled subset."
            )

        if not DATA_FILE.exists():
            raise CommandError(f"Seed file not found: {DATA_FILE}")

        rows = json.loads(DATA_FILE.read_text())

        if opts["clear"]:
            HsCode.objects.all().delete()
            self.stdout.write(self.style.WARNING("Cleared hs_codes."))

        # Pre-fetch UoM codes so missing references fail loudly.
        known_uoms = set(UnitOfMeasure.objects.values_list("code", flat=True))
        if not known_uoms:
            raise CommandError(
                "No UnitOfMeasure rows found. Run migrations first to seed UoM."
            )

        created = 0
        updated = 0
        skipped = 0
        with transaction.atomic():
            for row in rows:
                uom_code = row.get("uom_default")
                if uom_code and uom_code not in known_uoms:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  [{row['code']}] unknown uom '{uom_code}' — skipping"
                        )
                    )
                    skipped += 1
                    continue

                obj, was_created = HsCode.objects.update_or_create(
                    code=row["code"],
                    defaults={
                        "description": row["description"],
                        "default_tax_rate": (
                            Decimal(str(row["default_tax_rate"]))
                            if row.get("default_tax_rate") is not None
                            else None
                        ),
                        "uom_default_id": uom_code,
                        "parent_code": row.get("parent_code"),
                    },
                )
                if was_created:
                    created += 1
                else:
                    updated += 1

        self.stdout.write(self.style.SUCCESS(
            f"HS codes seeded: {created} created, {updated} updated, {skipped} skipped."
        ))
