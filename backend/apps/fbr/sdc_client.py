"""FBR SDC (Sale Data Controller / IMS Fiscalization Service) client.

WHY THIS EXISTS
---------------
Some FBR POS registrations (POS-DI / "Fiscalization" type, the ones provisioned
via the FBR IMS `setup.exe`) do NOT authenticate to PRAL's Digital-Invoicing
gateway (gw.fbr.gov.pk/di_data) with a Bearer token. Instead the taxpayer runs
the **SDC** — a local .NET/IIS Windows service listening on :8524 — which holds
the POS registration (POS ID + Code), performs the activation handshake, talks
to FBR (esp.fbr.gov.pk), and hands a fiscal invoice number + QR back.

The SDC can be installed ONCE on a central (Windows) server and serve MANY POS
IDs: the POS ID is a field in each request, so one SDC fiscalizes invoices for
every branch, each under its own registered POS ID. Our Linux app server can't
host the SDC itself, so it POSTs invoices to the SDC over the network:

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


def sdc_health() -> tuple[bool, str]:
    """Read-only reachability probe for the SDC (its /get endpoint replies
    'Service is responding'). Used by an admin connectivity check."""
    try:
        r = requests.get(_base() + HEALTH_PATH, timeout=10)
        return (r.ok, f"HTTP {r.status_code}: {r.text[:120]}")
    except requests.RequestException as exc:
        return (False, f"unreachable: {exc}")
