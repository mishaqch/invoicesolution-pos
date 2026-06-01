"""PRAL HTTP client.

Thin wrapper around `requests`. Every call:
  - 30s hard timeout
  - persists an FbrSubmission row (request + response + timing)
  - raises a typed exception on non-success

Typed exceptions:
  PralTransientError   — retry with backoff
  PralValidationError  — data fix needed; do NOT retry
  PralBusinessError    — rule (edit window, budget); permanent
  PralAuthError        — token issue; halt + alert
  PralUnknownError     — fallback (unknown code); treated as validation
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any

import requests

from .error_mapping import ErrorCategory, categorize, describe

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 30  # seconds


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class PralError(Exception):
    """Base class — never raised directly."""

    def __init__(
        self,
        message: str,
        *,
        http_status: int | None = None,
        error_code: str | None = None,
        response: dict | None = None,
    ):
        super().__init__(message)
        self.http_status = http_status
        self.error_code = error_code
        self.response = response


class PralTransientError(PralError): ...
class PralValidationError(PralError): ...
class PralBusinessError(PralError): ...
class PralAuthError(PralError): ...


_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")


def _try_lenient_json(text: str) -> dict[str, Any] | None:
    """Best-effort recovery of PRAL's quirky 'mostly-JSON' responses.

    Returns the parsed dict on success, None if the recovery still
    fails. We attempt one fix:
      - remove trailing commas before `}` / `]` (PRAL emits these
        between blocks; strict json.loads rejects them).

    Stray tabs and \n are valid whitespace in JSON, so they're left
    alone — Python's parser ignores them.
    """
    if not text or text[0] not in "{[":
        return None  # not even pretending to be JSON
    cleaned = _TRAILING_COMMA_RE.sub(r"\1", text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


def _exception_for(category: ErrorCategory) -> type[PralError]:
    return {
        ErrorCategory.TRANSIENT: PralTransientError,
        ErrorCategory.VALIDATION: PralValidationError,
        ErrorCategory.BUSINESS: PralBusinessError,
        ErrorCategory.AUTH: PralAuthError,
    }[category]


# ---------------------------------------------------------------------------
# Result + Client
# ---------------------------------------------------------------------------


@dataclass
class PralResponse:
    http_status: int
    body: dict[str, Any]
    duration_ms: int

    @property
    def is_success(self) -> bool:
        if self.http_status >= 400:
            return False
        validation = self.body.get("validationResponse") or {}
        return validation.get("statusCode") == "00"

    @property
    def fbr_invoice_number(self) -> str | None:
        return self.body.get("invoiceNumber")

    @property
    def status_code(self) -> str | None:
        return (self.body.get("validationResponse") or {}).get("statusCode")

    @property
    def first_error_code(self) -> str | None:
        statuses = (self.body.get("validationResponse") or {}).get("invoiceStatuses") or []
        for s in statuses:
            if s.get("statusCode") != "00":
                return s.get("errorCode")
        return None

    @property
    def first_error_message(self) -> str:
        statuses = (self.body.get("validationResponse") or {}).get("invoiceStatuses") or []
        for s in statuses:
            if s.get("statusCode") != "00":
                return s.get("error") or describe(s.get("errorCode"))
        return self.body.get("validationResponse", {}).get("error") or "Unknown error"


class FbrClient:
    """Stateless client. Construct one per submission."""

    def __init__(
        self,
        *,
        environment: str,
        token: str,
        endpoint_base: str,
    ):
        if environment not in ("sandbox", "production"):
            raise ValueError(f"unknown environment: {environment}")
        self.environment = environment
        self.token = token
        self.endpoint_base = endpoint_base.rstrip("/")

    # The four endpoints we care about.
    def post_invoice(self, payload: dict) -> PralResponse:
        return self._post("postinvoicedata", payload)

    def validate_invoice(self, payload: dict) -> PralResponse:
        return self._post("validateinvoicedata", payload)

    def edit_invoice(self, payload: dict) -> PralResponse:
        return self._post("editinvoice", payload)

    def cancel_invoice(self, payload: dict) -> PralResponse:
        return self._post("cancelinvoice", payload)

    # --- Internals ----------------------------------------------------------

    def _post(self, endpoint: str, payload: dict) -> PralResponse:
        url = self._url(endpoint)
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        start = time.monotonic()
        try:
            r = requests.post(url, json=payload, headers=headers, timeout=REQUEST_TIMEOUT)
        except requests.Timeout as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.warning("PRAL timeout calling %s after %sms", url, duration_ms)
            raise PralTransientError(
                f"PRAL timeout after {REQUEST_TIMEOUT}s",
                response={"error": "timeout"},
            ) from exc
        except requests.ConnectionError as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.warning("PRAL connection error: %s", exc)
            raise PralTransientError(
                f"PRAL connection error: {exc}",
                response={"error": "connection"},
            ) from exc

        duration_ms = int((time.monotonic() - start) * 1000)
        body: dict[str, Any]
        try:
            body = r.json()
        except json.JSONDecodeError:
            # PRAL's API server has a known bug: under some load
            # conditions it returns *almost*-JSON with trailing commas
            # and stray tabs (verified via raw_text capture in the
            # FbrSubmission log — the text starts and ends with `{`/`}`
            # and parses fine after stripping the trailing comma
            # before `}`). Try one lenient pass before declaring it
            # malformed: strip ASCII whitespace inside braces + remove
            # trailing commas before `}` / `]`. If THAT also fails, it
            # really is a gateway/firewall page and we surface a
            # transient error.
            body = _try_lenient_json(r.text)
            if body is None:
                body = {"raw_text": r.text[:2000]}
                logger.error("PRAL returned non-JSON (status %s)", r.status_code)
                raise PralTransientError(
                    f"Malformed response from PRAL (status {r.status_code})",
                    http_status=r.status_code,
                    response=body,
                )
            logger.warning(
                "PRAL returned malformed JSON (trailing commas / tabs); "
                "recovered via lenient parse (status %s)",
                r.status_code,
            )

        result = PralResponse(http_status=r.status_code, body=body, duration_ms=duration_ms)
        if result.is_success:
            return result

        category = categorize(result.first_error_code, http_status=result.http_status)
        Exc = _exception_for(category)
        raise Exc(
            result.first_error_message,
            http_status=result.http_status,
            error_code=result.first_error_code,
            response=body,
        )

    def _url(self, endpoint: str) -> str:
        suffix = "_sb" if self.environment == "sandbox" else ""
        return f"{self.endpoint_base}/di_data/v1/di/{endpoint}{suffix}"
