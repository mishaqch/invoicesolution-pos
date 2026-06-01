"""Sync the PRAL reference tables (HS codes + UoMs) into our DB.

PRAL exposes the authoritative HS code catalog at
    GET /pdi/v1/itemdesccode
and the canonical Unit-of-Measure list at
    GET /pdi/v1/uom

Both require a PRAL bearer token. The lists are national (not per-
taxpayer), so we cache them in our `hs_codes` and `units_of_measure`
tables and serve them to every tenant from there.

Why a sync command (not a bundled JSON):
  - PRAL HS codes are their own subset of customs HS codes; loading a
    generic 5000-row CSV gives codes PRAL won't accept (we hit this
    on Baba Farid — 1006.0000 in our seed, 1006.3090 in PRAL).
  - PRAL adds new codes when SROs land. A static file goes stale.
  - One token, one network call, done.

Usage:
    python manage.py sync_pral_reference --token <PRAL-sandbox-token>

    # Or pick up the token from any active FbrToken row:
    python manage.py sync_pral_reference --use-tenant-token <NTN>

Idempotent. Existing HsCode rows are updated in place; rows in PRAL
but missing locally are inserted. We do NOT delete rows that have
disappeared from PRAL — they may still be referenced by historical
SaleItem snapshots, and deleting would orphan those FKs.
"""

from __future__ import annotations

import time
from typing import Any

import requests
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import HsCode, UnitOfMeasure
from apps.fbr.models import FbrToken


PRAL_BASE = "https://gw.fbr.gov.pk"
ITEMDESC_PATH = "/pdi/v1/itemdesccode"
UOM_PATH = "/pdi/v1/uom"


class Command(BaseCommand):
    help = (
        "Fetch the authoritative HS code + UoM catalog from PRAL and "
        "upsert into our local tables."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--token",
            help="PRAL bearer token (sandbox or production). Mutually "
                 "exclusive with --use-tenant-token.",
        )
        parser.add_argument(
            "--use-tenant-token",
            metavar="NTN",
            help="Use the active FbrToken belonging to the tenant with this "
                 "NTN. Useful in dev where we have a known sandbox tenant.",
        )
        parser.add_argument(
            "--endpoint-base",
            default=PRAL_BASE,
            help=f"PRAL base URL (default {PRAL_BASE}).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Fetch + print counts but do NOT write to the DB.",
        )

    def handle(self, *args, **opts):
        token = self._resolve_token(opts)
        if not token:
            raise CommandError(
                "No PRAL token. Pass --token <bearer> or --use-tenant-token <NTN>.",
            )
        base = opts["endpoint_base"].rstrip("/")
        dry = bool(opts["dry_run"])

        self.stdout.write(self.style.NOTICE(
            f"Fetching PRAL reference data from {base}..."
        ))

        uoms = self._fetch(f"{base}{UOM_PATH}", token)
        hs_codes = self._fetch(f"{base}{ITEMDESC_PATH}", token)

        self.stdout.write(f"  UoMs fetched     : {len(uoms):>5}")
        self.stdout.write(f"  HS codes fetched : {len(hs_codes):>5}")

        if dry:
            self.stdout.write(self.style.WARNING(
                "--dry-run: nothing written to the DB."
            ))
            self._preview(uoms, hs_codes)
            return

        with transaction.atomic():
            uom_changes = self._upsert_uoms(uoms)
            hs_changes = self._upsert_hs_codes(hs_codes)

        # Stash the sync timestamp in the cache so the catalog meta
        # endpoint can surface 'last synced X minutes ago' in the UI.
        # Cache key matches what catalog.views reads from. Persisted
        # for ~90 days; we don't expire it because a missed re-sync
        # still wants to show the last known good timestamp.
        from django.core.cache import cache
        cache.set(
            "catalog:pral_reference_synced_at",
            timezone.now().isoformat(timespec="seconds"),
            timeout=90 * 24 * 3600,
        )

        self.stdout.write(self.style.SUCCESS(
            f"UoMs        : +{uom_changes['inserted']} new, "
            f"~{uom_changes['updated']} updated"
        ))
        self.stdout.write(self.style.SUCCESS(
            f"HS codes    : +{hs_changes['inserted']} new, "
            f"~{hs_changes['updated']} updated"
        ))
        self.stdout.write(self.style.SUCCESS(
            f"Local totals: {UnitOfMeasure.objects.count()} UoMs, "
            f"{HsCode.objects.count()} HS codes "
            f"as of {timezone.now().isoformat(timespec='seconds')}"
        ))

    # ------------------------------------------------------------------

    def _resolve_token(self, opts) -> str | None:
        if opts.get("token") and opts.get("use_tenant_token"):
            raise CommandError("Pass either --token OR --use-tenant-token, not both.")
        if opts.get("token"):
            return opts["token"]
        ntn = opts.get("use_tenant_token")
        if ntn:
            tok = (
                FbrToken.objects
                .filter(tenant__ntn=ntn, is_active=True)
                .order_by("-environment")  # prefer production over sandbox
                .first()
            )
            if tok is None:
                raise CommandError(
                    f"No active FbrToken for tenant NTN {ntn}.",
                )
            return tok.token
        return None

    def _fetch(self, url: str, token: str) -> list[dict[str, Any]]:
        """GET the PRAL reference endpoint and return the JSON body.

        Retries once on transient failures. Raises CommandError on
        auth failure or unexpected response shape.
        """
        for attempt in (1, 2):
            try:
                r = requests.get(
                    url,
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=30,
                )
            except requests.RequestException as exc:
                if attempt == 1:
                    self.stdout.write(self.style.WARNING(
                        f"  {url} attempt {attempt} failed: {exc}; retrying..."
                    ))
                    time.sleep(2)
                    continue
                raise CommandError(f"PRAL unreachable: {exc}") from exc
            if r.status_code == 401:
                raise CommandError(
                    "PRAL returned 401 — your token is invalid or expired."
                )
            if not r.ok:
                raise CommandError(
                    f"PRAL returned HTTP {r.status_code} for {url}: "
                    f"{r.text[:200]}"
                )
            try:
                data = r.json()
            except ValueError:
                raise CommandError(
                    f"PRAL returned non-JSON for {url}: {r.text[:200]}"
                )
            if not isinstance(data, list):
                raise CommandError(
                    f"PRAL returned non-list for {url}: "
                    f"{str(data)[:200]}"
                )
            return data
        return []  # unreachable, but keeps type-checker happy

    def _preview(self, uoms: list[dict], hs_codes: list[dict]) -> None:
        self.stdout.write("")
        self.stdout.write("First 5 UoMs:")
        for u in uoms[:5]:
            self.stdout.write(f"  {u}")
        self.stdout.write("")
        self.stdout.write("First 5 HS codes:")
        for h in hs_codes[:5]:
            code = h.get("hS_CODE") or h.get("hsCode")
            desc = (h.get("description") or "")[:80]
            self.stdout.write(f"  {code}: {desc}")

    # ---- Upserts -----------------------------------------------------

    # PRAL's display strings → short canonical codes our schema can
    # use as a primary key (max 20 chars, no spaces). When PRAL adds a
    # new UoM not in this map, we generate a code from the description.
    _UOM_DESC_TO_CODE = {
        "KG": "KG",
        "Kilogram": "KG",
        "Gram": "GM",
        "Liter": "LTR",
        "Meter": "METER",
        "Foot": "FT",
        "Square Foot": "SQFT",
        "Square Metre": "SQM",
        "SqY": "SQY",
        "Cubic Metre": "CBM",
        "MT": "MT",
        "40KG": "40KG",
        "Bag": "BAG",
        "Carat": "CARAT",
        "Dozen": "DOZEN",
        "Gallon": "GALLON",
        "Pound": "LB",
        "Pcs": "PCS",
        "Pair": "PAIR",
        "Packs": "PACK",
        "Numbers, pieces, units": "PCS",
        "NO": "NO",
        "Mega Watt": "MW",
        "KWH": "KWH",
        "1000 kWh": "MWH",
        "MMBTU": "MMBTU",
        "Barrels": "BBL",
        "Timber Logs": "LOGS",
        "Bill of lading": "BOL",
        "SET": "SET",
        "Thousand Unit": "1000U",
        "Others": "OTHER",
    }

    def _short_code_for(self, description: str) -> str:
        """Map a PRAL UoM description to a short (<=20-char), stable
        local code. Known descriptions use the curated table above;
        unknown ones get a slugified fallback."""
        if description in self._UOM_DESC_TO_CODE:
            return self._UOM_DESC_TO_CODE[description]
        # Fallback: strip non-alphanumeric, upper, truncate. Stable
        # enough that re-syncs won't churn the code on the same input.
        cleaned = "".join(c for c in description.upper() if c.isalnum())[:20]
        return cleaned or "X"

    def _upsert_uoms(self, payload: list[dict]) -> dict:
        """Insert/update rows in `units_of_measure`. PRAL returns
        {uoM_ID, description}; we map description → short code via
        _UOM_DESC_TO_CODE and store the full description as `name_en`.

        Why: our schema's primary key is `code` CHAR(20). PRAL's
        longest string ('Numbers, pieces, units') is 22 chars; can't
        fit. Short codes (KG, LTR, PCS) also match what other parts
        of the codebase already use (UOM_FBR_MAP in builder.py, the
        bundled seed JSON, etc.).

        Skips empty descriptions and dedupes by short code (PRAL has
        dupes like two 'Meter' rows with different IDs).
        """
        inserted = updated = 0
        seen: set[str] = set()
        for row in payload:
            desc = (row.get("description") or "").strip()
            if not desc:
                continue
            code = self._short_code_for(desc)
            if code in seen:
                continue
            seen.add(code)
            obj, created = UnitOfMeasure.objects.update_or_create(
                code=code,
                defaults={"name_en": desc, "is_decimal_quantity": False},
            )
            if created:
                inserted += 1
            else:
                updated += 1
        return {"inserted": inserted, "updated": updated}

    def _upsert_hs_codes(self, payload: list[dict]) -> dict:
        """Insert/update rows in `hs_codes`.

        PRAL returns objects like {"hS_CODE": "1006.3090", "description": "..."}.
        We never delete a previously-known code (it may be FK'd by
        existing SaleItem rows). Local-only codes (rows we have but
        PRAL doesn't return) are also left alone.
        """
        inserted = updated = 0
        for row in payload:
            code = (row.get("hS_CODE") or row.get("hsCode") or "").strip()
            if not code:
                continue
            description = (row.get("description") or "").strip() or code
            obj, created = HsCode.objects.update_or_create(
                code=code,
                defaults={"description": description},
            )
            if created:
                inserted += 1
            else:
                updated += 1
        return {"inserted": inserted, "updated": updated}
