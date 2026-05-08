"""PRAL error codes → error category map (INTEGRATIONS.md §1.13).

Four categories:
  transient  — retry with backoff (network, gateway, timeout, 5xx).
  validation — data the cashier/admin must fix; do NOT retry.
  business   — rule (edit window, budget, etc.); permanent.
  auth       — token expired/revoked; halt + alert.

The list below is the v1.6 manual's published codes. As we encounter new
ones in production, add them. Unknown codes default to 'validation' so a
human reviews — safer than silent retries.
"""

from __future__ import annotations

from enum import Enum


class ErrorCategory(str, Enum):
    TRANSIENT = "transient"
    VALIDATION = "validation"
    BUSINESS = "business"
    AUTH = "auth"


ERROR_CODE_MAP: dict[str, tuple[ErrorCategory, str]] = {
    # --- Validation (data fixes) ---
    "0053": (ErrorCategory.VALIDATION, "Buyer registration type does not match buyer's profile"),
    "0001": (ErrorCategory.VALIDATION, "Invoice already exists"),
    "0010": (ErrorCategory.VALIDATION, "HS code invalid"),
    "0011": (ErrorCategory.VALIDATION, "Tax rate mismatch"),
    "0020": (ErrorCategory.VALIDATION, "Buyer NTN/CNIC missing"),

    # --- Business rules ---
    "0100": (ErrorCategory.BUSINESS, "Edit window has passed"),
    "0101": (ErrorCategory.BUSINESS, "Cancel budget exceeded"),
    "0102": (ErrorCategory.BUSINESS, "Item already edited (max 1 edit)"),

    # --- Auth ---
    "0401": (ErrorCategory.AUTH, "Authentication token expired"),
    "0403": (ErrorCategory.AUTH, "Forbidden — IP not whitelisted"),

    # --- Transient ---
    "0500": (ErrorCategory.TRANSIENT, "Server unavailable"),
    "0503": (ErrorCategory.TRANSIENT, "Service temporarily unavailable"),
}


def categorize(error_code: str | None, http_status: int | None = None) -> ErrorCategory:
    """Map a PRAL error code (and HTTP status) to a category.

    Precedence: explicit map wins; then HTTP status (5xx → transient,
    401/403 → auth); then default to VALIDATION (safer than retry).
    """
    if error_code and error_code in ERROR_CODE_MAP:
        return ERROR_CODE_MAP[error_code][0]

    if http_status is not None:
        if http_status in (401,):
            return ErrorCategory.AUTH
        if http_status == 403:
            return ErrorCategory.AUTH  # treat as auth — IP not whitelisted
        if 500 <= http_status < 600:
            return ErrorCategory.TRANSIENT

    return ErrorCategory.VALIDATION


def describe(error_code: str | None) -> str:
    if error_code and error_code in ERROR_CODE_MAP:
        return ERROR_CODE_MAP[error_code][1]
    return "Unknown error"
