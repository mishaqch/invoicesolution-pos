"""Local mock of the PRAL Digital Invoicing gateway.

WHY THIS EXISTS
---------------
The real PRAL sandbox at https://gw.fbr.gov.pk/di_data/v1/di/* requires:
  - A taxpayer NTN registered in IRIS
  - A long-lived bearer token issued by PRAL after the IP-whitelist step
  - Outbound network access whitelisted to specific static IPs

For dev / CI / demo we want to exercise the FBR submission code path
(payload build → POST → response parse → invoice state machine) without
any of that. This mock returns PRAL-shaped JSON responses that the
`apps.fbr.client.PralResponse` parser understands.

To use it, point a tenant's `FbrToken.api_endpoint` at this server's
base URL (e.g. http://localhost:8000) and call PRAL endpoints as
normal. The Celery task already accepts whatever endpoint the token
record carries; nothing else changes.

WHAT IT VALIDATES (per PRAL DI User Manual v1.6 + INTEGRATIONS.md §1)
---------------------------------------------------------------------
  1. Authorization header present (any non-empty Bearer token accepted).
  2. JSON body parseable.
  3. Required top-level keys: invoiceType, invoiceDate, sellerNTNCNIC,
     sellerBusinessName, sellerProvince, sellerAddress, buyerNTNCNIC,
     buyerBusinessName, buyerRegistrationType, scenarioId, items.
  4. invoiceDate is YYYY-MM-DD and not >3 days in the past, not future.
  5. items[] has at least one entry, each with: hsCode, productDescription,
     rate (string like "18%"), uoM, quantity, totalValues, etc.
  6. buyerNTNCNIC is "0000000000000" for Unregistered, 7-13 digits otherwise.
  7. scenarioId is present (sandbox only).

On success it returns a synthetic 18-digit FBR invoice number and a
validationResponse with statusCode "00". On failure it returns the
same shape PRAL uses for rejections so the parser exercises the
unhappy paths too.

NOT FOR PRODUCTION USE — this view is wired into urls.py only when
settings.DEBUG=True.
"""

from __future__ import annotations

import json
import random
import re
import string
from datetime import date, datetime, timedelta

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods


REQUIRED_TOP_LEVEL = (
    "invoiceType",
    "invoiceDate",
    "sellerNTNCNIC",
    "sellerBusinessName",
    "sellerProvince",
    "sellerAddress",
    "buyerNTNCNIC",
    "buyerBusinessName",
    "buyerRegistrationType",
    "items",
)

REQUIRED_ITEM_KEYS = (
    "hsCode",
    "productDescription",
    "rate",
    "uoM",
    "quantity",
    "totalValues",
    "valueSalesExcludingST",
    "salesTaxApplicable",
    "saleType",
)


def _err(error: str, error_code: str = "0001", item_no: int = 1) -> JsonResponse:
    """PRAL-shaped rejection payload."""
    return JsonResponse({
        "invoiceNumber": "",
        "dated": "",
        "validationResponse": {
            "statusCode": "01",
            "status": "Invalid",
            "error": error,
            "errorCode": error_code,
            "invoiceStatuses": [
                {
                    "itemSNo": str(item_no),
                    "statusCode": "01",
                    "status": "Invalid",
                    "invoiceNo": None,
                    "errorCode": error_code,
                    "error": error,
                },
            ],
        },
    }, status=200)


def _ok(fbr_invoice_number: str) -> JsonResponse:
    """PRAL-shaped success payload."""
    return JsonResponse({
        "invoiceNumber": fbr_invoice_number,
        "dated": datetime.utcnow().isoformat(timespec="seconds"),
        "validationResponse": {
            "statusCode": "00",
            "status": "Valid",
            "error": "",
            "errorCode": "",
            "invoiceStatuses": [],
        },
    }, status=200)


def _gen_fbr_invoice_number(seller_ntn: str) -> str:
    """18-digit number similar in shape to what PRAL returns.

    Real PRAL uses 7+13 = 20-character alphanumeric refs; we keep it
    digits-only and 18 chars so the existing format checks (which are
    permissive) accept it.
    """
    prefix = (seller_ntn or "").rjust(13, "0")[:13]
    rand = "".join(random.choices(string.digits, k=5))
    return f"7{prefix}{rand}"[:18]


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_NTN_RE = re.compile(r"^\d{7,13}$")
_RATE_RE = re.compile(r"^\d{1,2}(\.\d+)?%$|^Exempt$|^0%$")


def _validate_payload(payload: dict) -> tuple[bool, str, str]:
    """Run the same shape checks PRAL would do.

    Returns (ok, error_message, error_code). On success ('', '') the
    caller proceeds; on failure we send the rejection back.
    """
    if not isinstance(payload, dict):
        return False, "Payload must be a JSON object.", "0002"

    # Top-level keys
    missing = [k for k in REQUIRED_TOP_LEVEL if k not in payload]
    if missing:
        return False, f"Missing required fields: {', '.join(missing)}", "0003"

    # invoiceDate format + window
    invoice_date_str = payload.get("invoiceDate") or ""
    if not _DATE_RE.match(invoice_date_str):
        return False, "invoiceDate must be YYYY-MM-DD.", "0004"
    try:
        invoice_date = date.fromisoformat(invoice_date_str)
    except ValueError:
        return False, "invoiceDate is not a real date.", "0004"
    today = date.today()
    if invoice_date > today:
        return False, "invoiceDate cannot be in the future.", "0005"
    if (today - invoice_date) > timedelta(days=3):
        return False, (
            "invoiceDate cannot be more than 3 days in the past."
        ), "0006"

    # Seller / buyer NTNs
    seller_ntn = payload.get("sellerNTNCNIC") or ""
    if not _NTN_RE.match(seller_ntn):
        return False, "sellerNTNCNIC must be 7-13 digits.", "0007"

    buyer_ntn = payload.get("buyerNTNCNIC") or ""
    reg_type = payload.get("buyerRegistrationType") or ""
    if reg_type == "Unregistered":
        if buyer_ntn != "0000000000000":
            return False, (
                "Unregistered buyer must have buyerNTNCNIC='0000000000000'."
            ), "0008"
    else:
        if not _NTN_RE.match(buyer_ntn):
            return False, (
                "Registered buyer requires a 7-13 digit buyerNTNCNIC."
            ), "0009"

    # scenarioId is required during sandbox testing per the manual.
    # The mock always behaves like sandbox.
    if not payload.get("scenarioId"):
        return False, "scenarioId is required during sandbox testing.", "0010"

    # Items
    items = payload.get("items") or []
    if not isinstance(items, list) or not items:
        return False, "Invoice must contain at least one item.", "0011"
    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            return False, f"Item #{idx} is not an object.", "0012"
        item_missing = [k for k in REQUIRED_ITEM_KEYS if k not in item]
        if item_missing:
            return False, (
                f"Item #{idx} missing: {', '.join(item_missing)}"
            ), "0013"
        rate = item.get("rate") or ""
        if not isinstance(rate, str) or not _RATE_RE.match(rate):
            return False, (
                f"Item #{idx} 'rate' must be a string like '18%' or '0%' "
                f"or 'Exempt', got {rate!r}."
            ), "0014"

    return True, "", ""


def _read_payload(request):
    try:
        return json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def _check_auth(request) -> bool:
    auth = request.headers.get("Authorization", "")
    return auth.startswith("Bearer ") and len(auth) > len("Bearer ")


@csrf_exempt
@require_http_methods(["POST"])
def post_invoice(request):
    """Mock for postinvoicedata_sb (sandbox) / postinvoicedata (prod).

    Validates payload shape and returns a synthetic FBR invoice number
    on success, or a PRAL-shaped rejection on failure.
    """
    if not _check_auth(request):
        return _err("Authorization header missing or malformed.", "0401")
    payload = _read_payload(request)
    if payload is None:
        return _err("Could not parse JSON body.", "0400")
    ok, msg, code = _validate_payload(payload)
    if not ok:
        return _err(msg, code)
    return _ok(_gen_fbr_invoice_number(payload.get("sellerNTNCNIC", "")))


@csrf_exempt
@require_http_methods(["POST"])
def validate_invoice(request):
    """Mock for validateinvoicedata_sb / validateinvoicedata.

    Same checks as post_invoice but without minting an FBR number —
    used for dry-run validation. We still return an invoiceNumber
    field (empty) so the parser doesn't choke.
    """
    if not _check_auth(request):
        return _err("Authorization header missing or malformed.", "0401")
    payload = _read_payload(request)
    if payload is None:
        return _err("Could not parse JSON body.", "0400")
    ok, msg, code = _validate_payload(payload)
    if not ok:
        return _err(msg, code)
    # Validate returns success without minting a real number.
    return JsonResponse({
        "invoiceNumber": "",
        "dated": "",
        "validationResponse": {
            "statusCode": "00",
            "status": "Valid",
            "error": "",
            "errorCode": "",
            "invoiceStatuses": [],
        },
    }, status=200)


@csrf_exempt
@require_http_methods(["POST"])
def cancel_invoice(request):
    """Mock for cancelinvoice_sb / cancelinvoice.

    Real PRAL cancellation requires the original invoice number +
    a reason; we accept any well-formed payload with `invoiceNumber`
    and `reason` and respond success.
    """
    if not _check_auth(request):
        return _err("Authorization header missing or malformed.", "0401")
    payload = _read_payload(request)
    if payload is None:
        return _err("Could not parse JSON body.", "0400")
    if not payload.get("invoiceNumber"):
        return _err("invoiceNumber is required for cancellation.", "0020")
    if not (payload.get("reason") or "").strip():
        return _err("reason is required for cancellation.", "0021")
    return _ok(payload["invoiceNumber"])


@csrf_exempt
@require_http_methods(["POST"])
def edit_invoice(request):
    """Mock for editinvoice_sb / editinvoice."""
    if not _check_auth(request):
        return _err("Authorization header missing or malformed.", "0401")
    payload = _read_payload(request)
    if payload is None:
        return _err("Could not parse JSON body.", "0400")
    ok, msg, code = _validate_payload(payload)
    if not ok:
        return _err(msg, code)
    return _ok(_gen_fbr_invoice_number(payload.get("sellerNTNCNIC", "")))


@csrf_exempt
@require_http_methods(["GET"])
def uom(request):
    """Mock for /pdi/v1/uom — the read-only reference endpoint the
    'Test connection' button probes. Real PRAL returns a JSON array of
    units of measure; we return a small representative list so the button
    succeeds against the mock (no live PRAL, no IP whitelist needed).

    Requires a Bearer header like the real endpoint, so the probe still
    exercises the auth path. 401 when missing (mirrors PRAL)."""
    if not _check_auth(request):
        return JsonResponse(
            {"detail": "Authorization header missing or malformed."},
            status=401,
        )
    return JsonResponse(
        [
            {"uoM_ID": 1, "description": "Numbers, pieces, units"},
            {"uoM_ID": 2, "description": "KG"},
            {"uoM_ID": 3, "description": "Liter"},
            {"uoM_ID": 4, "description": "Meter"},
        ],
        safe=False,
        status=200,
    )
