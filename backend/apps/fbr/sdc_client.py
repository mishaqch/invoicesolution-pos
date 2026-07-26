"""FBR SDC (Sale Data Controller / IMS Fiscalization Service) client.

WHY THIS EXISTS
---------------
Some FBR POS registrations (POS-DI / "Fiscalization" type, the ones provisioned
via the FBR IMS `setup.exe`) do NOT authenticate to PRAL's Digital-Invoicing
gateway (gw.fbr.gov.pk/di_data) with a Bearer token. Instead the taxpayer runs
the **SDC** — a local .NET/IIS Windows service listening on :8524 — which holds
the POS registration (POS ID + Code), performs the activation handshake, talks
to FBR (esp.fbr.gov.pk), and hands a fiscal invoice number + QR back.

A local SDC is bound to ONE POS registration at install (POS ID + Access Code
entered once, stored locally); the local :8524 POST has no per-request auth, so
one SDC is NOT a multi-tenant router (verified against FBR/PRA specs — see
FISCALIZATION_ARCHITECTURE.md). PREFER THE CLOUD PATH: both authorities expose a
token-based cloud API that needs NO local component —

    FBR: gw.fbr.gov.pk/di_data/v1/di/postinvoicedata  (apps.fbr.client.FbrClient)
    PRA: ims.pral.com.pk/.../Live/PostData            (submit_invoice_cloud below)

This local-SDC client remains only for tenants that genuinely run a reachable
SDC (e.g. a shared branch machine). Contract:

    POST  {FBR_SDC_BASE_URL}/api/IMSFiscal/GetInvoiceNumberByModel
    body: { "POSID": <branch posid>, ...invoice fields... }

CONTRACT STATUS
---------------
The endpoint path + the `POSID` field are confirmed from FBR/community docs, but
the FULL request/response field schema is SDC-version-specific and must be
reconciled against the actual installed SDC (and FBR's official SDC spec). The
field mapping below is intentionally isolated in `build_sdc_payload` /
`parse_sdc_response` so it's the only thing to adjust once we see the real SDC.

Until FBR_SDC_BASE_URL is configured, this client is dormant — submission falls
back to the DI-API path (apps.fbr.client.FbrClient). See tasks.submit_invoice_to_fbr.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 30
SUBMIT_PATH = "/api/IMSFiscal/GetInvoiceNumberByModel"
HEALTH_PATH = "/api/IMSFiscal/get"

# PRA (Punjab Revenue Authority) CLOUD IMS endpoints — same POS-Component invoice
# model + Bearer-token contract as FBR POS, posted from our server (no local
# component). See FISCALIZATION_ARCHITECTURE.md.
#
# ENDPOINT HISTORY (important):
#   • The old PRA manual documented ims.pral.com.pk/ims/{env}/api/Live/PostData.
#     That host is IP-blocked for our server (TLS handshake dropped) — PRA never
#     whitelisted us there.
#   • FBR and PRA e-IMS are UNIFIED behind PRAL's gateway gw.fbr.gov.pk, which
#     our server IS whitelisted for. So we post PRA invoices to the gateway, not
#     the blocked pral.com.pk host.
#   • The correct PRA host is ims.pral.com.pk (per PRAL's "POS Component User
#     Manual" v1.0, §6.4.2) — NOT gw.fbr.gov.pk (that's FBR's federal gateway,
#     a different system). Earlier the pral.com.pk host was TLS-unreachable for
#     us; after PRA whitelisted our IP (email to eims@pra.punjab.gov.pk) it is
#     reachable again.
#   • VERIFIED LIVE 2026-07-26 with BIRYANI MASTER's production token (…5e49d6)
#     from the whitelisted VPS, posting a FULLY-FORMED single invoice:
#       POST https://ims.pral.com.pk/ims/production/api/Live/PostData
#         → HTTP 200 {"Code":"112","Response":"Bulk data upload functionality is
#            no more available"}   (token AUTHENTICATES — not 104 unauthorized —
#            but the Live/PostData OPERATION ITSELF IS RETIRED on the live
#            server; Code 112 regardless of payload).
#       sandbox path → Code 104 (prod token can't use sandbox — expected).
#       Every other candidate op path (Live/PostInvoiceData, Single/PostData,
#         IMSFiscal/PostData, v2/…) → 404 "Runtime Error" (no such API resource).
#     So Live/PostData is the ONLY exposed operation and it is dead. There is NO
#     direct-cloud single-invoice REST endpoint we can call for this token.
#   • The manual's PRIMARY method (§6.4.1) is NOT direct-cloud: it posts to the
#     locally-installed PRA "POS Component" (.msi) at
#       http://localhost:8524/api/IMSFiscal/GetInvoiceNumberByModel
#     which holds the POSID+Token and forwards to PRAL, returning Code 100. PRA
#     POS fiscalization for this taxpayer therefore requires running that local
#     component (the ims_sdc path), NOT our server-side direct cloud post.
#
# Kept for FBR federal POS (which DOES work on gw.fbr.gov.pk/imsp/v1 — see
# FBR_CLOUD_URLS + PEER TRADERS' verified 194444FGQK… number). For PRA, override
# via FBR_PRA_CLOUD_URL only if PRAL later re-exposes a direct single-invoice op.
_PRA_DEFAULT_URL = "https://gw.fbr.gov.pk/imsp/v1/api/Live/PostData"
_pra_url = getattr(settings, "FBR_PRA_CLOUD_URL", "") or _PRA_DEFAULT_URL
PRA_CLOUD_URLS = {
    "sandbox": _pra_url,
    "production": _pra_url,
}

# FBR (federal) CLOUD IMS endpoint — SAME Live/PostData contract as PRA (Bearer
# token + POS-Component payload), but on FBR's gateway. This is the path a
# "POS-DI" / IsCloud=1 FBR registration uses; its token is subscribed to
# imsp/v1 on gw.fbr.gov.pk (NOT the di_data/v1 Digital-Invoicing API).
# VERIFIED LIVE: POST here with PEER TRADERS' token returned
#   {"InvoiceNumber":"194444FGQK...","Code":"100","Response":"Invoice received successfully"}
# FBR does not expose a separate sandbox host on this path; the token's
# environment governs test vs live server-side (same as PRA's routing-by-token).
FBR_CLOUD_URLS = {
    "sandbox": "https://gw.fbr.gov.pk/imsp/v1/api/Live/PostData",
    "production": "https://gw.fbr.gov.pk/imsp/v1/api/Live/PostData",
}

# Authority → URL table, so the one cloud client serves both.
CLOUD_URLS_BY_AUTHORITY = {
    "pra": PRA_CLOUD_URLS,
    "fbr": FBR_CLOUD_URLS,
}


class SdcError(Exception):
    """Base — SDC unreachable or returned an unusable response."""


class SdcTransientError(SdcError):
    """Network / 5xx — safe to retry."""


class SdcRejectedError(SdcError):
    """SDC/FBR rejected the invoice (validation/business). Do not blind-retry."""


@dataclass
class SdcResult:
    fbr_invoice_number: str
    qr_payload: str | None
    raw: dict


def sdc_configured() -> bool:
    return bool(getattr(settings, "FBR_SDC_BASE_URL", "") or "")


def _base() -> str:
    base = (getattr(settings, "FBR_SDC_BASE_URL", "") or "").rstrip("/")
    if not base:
        raise SdcError("FBR_SDC_BASE_URL is not configured.")
    return base


def build_sdc_payload(*, invoice, pos_id: str) -> dict:
    """Map our Invoice → the SDC's GetInvoiceNumberByModel request body.

    This matches the REAL FBR SDC (IMSFiscal) contract — confirmed field names,
    NOT the DI-API shape. Key fields:
      InvoiceNumber="" (empty = new), POSID (int), USIN (unique sale id =
      local_invoice_number), DateTime "YYYY-MM-DD HH:MM:SS", Buyer*, Total*,
      PaymentMode (1=cash), InvoiceType (1=sale), Items[].PCTCode = HS code.
    """
    from decimal import Decimal

    def f(v) -> float:
        try:
            return float(Decimal(str(v or 0)))
        except Exception:
            return 0.0

    items = [it for it in invoice.items.all().order_by("line_number")
             if not getattr(it, "is_cancelled", False)]

    # Payment mode: 1 = cash (default). Map common methods → FBR codes.
    pay = invoice.payments.first() if hasattr(invoice, "payments") else None
    pm_map = {"cash": 1, "card": 2, "credit_card": 2, "debit_card": 2,
              "cheque": 3, "bank": 4, "bank_transfer": 4, "easypaisa": 5,
              "jazzcash": 5, "credit": 6}
    payment_mode = pm_map.get(getattr(pay, "payment_method", "cash"), 1)

    return {
        "InvoiceNumber": "",  # empty → SDC mints a new fiscal number
        "POSID": int(pos_id) if str(pos_id).isdigit() else pos_id,
        "USIN": invoice.local_invoice_number,
        "DateTime": (invoice.created_at or invoice.invoice_date).strftime(
            "%Y-%m-%d %H:%M:%S") if hasattr(invoice.created_at, "strftime")
            else str(invoice.invoice_date),
        "BuyerNTN": invoice.buyer_ntn_cnic or "",
        "BuyerCNIC": invoice.buyer_ntn_cnic or "",
        "BuyerName": invoice.buyer_name or "Walk-in Customer",
        "BuyerPhoneNumber": invoice.buyer_phone or "",
        "TotalBillAmount": f(invoice.grand_total),
        "TotalQuantity": f(sum(Decimal(str(it.quantity)) for it in items)),
        "TotalSaleValue": f(invoice.subtotal),
        "TotalTaxCharged": f(invoice.tax_total),
        "Discount": f(invoice.discount_total),
        "FurtherTax": 0.0,
        "PaymentMode": payment_mode,
        "RefUSIN": None,
        "InvoiceType": 1,  # 1 = sale (credit/debit notes would differ)
        "Items": [
            {
                "ItemCode": it.product_sku or str(it.product_id),
                "ItemName": it.product_name,
                "Quantity": f(it.quantity),
                "PCTCode": (it.hs_code or "").replace(".", "") or "00000000",
                "TaxRate": f(it.tax_rate),
                "SaleValue": f(it.line_total),
                "TotalAmount": f(it.line_total),
                "TaxCharged": f(it.tax_amount),
                "Discount": f(it.discount_amount),
                "FurtherTax": 0.0,
                "InvoiceType": 1,
                "RefUSIN": None,
            }
            for it in items
        ],
    }


def parse_sdc_response(data: dict) -> SdcResult:
    """Extract the fiscal invoice number from the SDC response.

    Real SDC success shape:
      {"InvoiceNumber": "9000...", "Code": "100",
       "Response": "Fiscal Invoice Number generated successfully.", "Errors": null}
    Code "100" = success. Anything else (or Errors set) = rejection. The SDC
    returns no QR; the QR encodes the returned InvoiceNumber, built by the caller.
    """
    code = str(data.get("Code") or "")
    num = (data.get("InvoiceNumber") or "").strip()
    errors = data.get("Errors")

    if code and code != "100":
        raise SdcRejectedError(
            f"SDC rejected (Code {code}): {data.get('Response') or errors or data}"
        )
    if errors:
        raise SdcRejectedError(f"SDC errors: {errors}")
    if not num:
        raise SdcRejectedError(f"SDC returned no invoice number: {str(data)[:300]}")
    # No QR in the SDC response — caller builds it from the number.
    return SdcResult(fbr_invoice_number=num, qr_payload=None, raw=data)


def submit_invoice(*, invoice, pos_id: str) -> SdcResult:
    """POST one invoice to the SDC for the given POS ID; return the fiscal
    number + QR. Raises SdcTransientError (retryable) or SdcRejectedError."""
    url = _base() + SUBMIT_PATH
    payload = build_sdc_payload(invoice=invoice, pos_id=pos_id)
    start = time.monotonic()
    try:
        r = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
    except requests.Timeout as exc:
        raise SdcTransientError(f"SDC timeout: {exc}") from exc
    except requests.RequestException as exc:
        raise SdcTransientError(f"SDC unreachable: {exc}") from exc
    dur = int((time.monotonic() - start) * 1000)

    if r.status_code >= 500:
        raise SdcTransientError(f"SDC {r.status_code} (server error) in {dur}ms")
    if r.status_code >= 400:
        raise SdcRejectedError(f"SDC {r.status_code}: {r.text[:300]}")
    try:
        data = r.json()
    except ValueError as exc:
        raise SdcTransientError(f"SDC non-JSON response: {r.text[:200]}") from exc

    logger.info("SDC fiscalized POSID=%s invoice=%s in %sms", pos_id, invoice.id, dur)
    return parse_sdc_response(data)


def submit_invoice_cloud(
    *, invoice, pos_id: str, token: str, environment: str, authority: str = "pra",
) -> SdcResult:
    """POST one invoice to a CLOUD IMS (PRA's ims.pral.com.pk OR FBR's
    gw.fbr.gov.pk/imsp) with a Bearer token.

    Both authorities expose the identical Live/PostData contract — same
    POS-Component payload + {InvoiceNumber, Code:100} response as the local SDC —
    so one client serves both; only the host differs (authority=). The branch
    POS ID is embedded in the payload. Raises SdcTransientError (retryable, e.g.
    network/5xx/timeout) or SdcRejectedError (validation/business/4xx).

    NOTE: PRA may IP-whitelist the calling server; until then the TLS handshake
    is dropped and surfaces here as a transient (retryable) error. FBR's gateway
    is already reachable from our whitelisted server.
    """
    urls = CLOUD_URLS_BY_AUTHORITY.get(authority)
    if not urls:
        raise SdcRejectedError(f"Unknown cloud authority: {authority!r}")
    url = urls.get(environment)
    if not url:
        raise SdcRejectedError(f"Unknown {authority} cloud environment: {environment!r}")
    payload = build_sdc_payload(invoice=invoice, pos_id=pos_id)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    au = authority.upper()
    start = time.monotonic()
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=REQUEST_TIMEOUT)
    except requests.Timeout as exc:
        raise SdcTransientError(f"{au} cloud timeout: {exc}") from exc
    except requests.RequestException as exc:
        # Includes TLS/SSL errors (e.g. server not yet IP-whitelisted) —
        # treat as transient so the invoice is retried, not hard-failed.
        raise SdcTransientError(f"{au} cloud unreachable: {exc}") from exc
    dur = int((time.monotonic() - start) * 1000)

    if r.status_code == 401 or r.status_code == 403:
        raise SdcRejectedError(f"{au} cloud auth failed ({r.status_code}): check the Bearer token / API subscription. {r.text[:200]}")
    if r.status_code >= 500:
        raise SdcTransientError(f"{au} cloud {r.status_code} (server error) in {dur}ms")
    if r.status_code >= 400:
        raise SdcRejectedError(f"{au} cloud {r.status_code}: {r.text[:300]}")
    try:
        data = r.json()
    except ValueError as exc:
        raise SdcTransientError(f"{au} cloud non-JSON response: {r.text[:200]}") from exc

    logger.info("%s cloud fiscalized POSID=%s invoice=%s env=%s in %sms",
                au, pos_id, invoice.id, environment, dur)
    return parse_sdc_response(data)


def sdc_health() -> tuple[bool, str]:
    """Read-only reachability probe for the SDC (its /get endpoint replies
    'Service is responding'). Used by an admin connectivity check."""
    try:
        r = requests.get(_base() + HEALTH_PATH, timeout=10)
        return (r.ok, f"HTTP {r.status_code}: {r.text[:120]}")
    except requests.RequestException as exc:
        return (False, f"unreachable: {exc}")
