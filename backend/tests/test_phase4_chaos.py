"""Phase 4 chaos / error-handling tests.

  - PRAL returns malformed JSON → no crash, treated as transient.
  - PRAL returns 200 but statusCode='01' → marked failed, not valid.
  - error_mapping categorize() handles unknown codes safely.
"""

from __future__ import annotations

import pytest
import requests
from unittest.mock import patch

from apps.fbr.client import (
    FbrClient,
    PralBusinessError,
    PralTransientError,
    PralValidationError,
)
from apps.fbr.error_mapping import ErrorCategory, categorize


# ---------------------------------------------------------------------------
# error_mapping.categorize
# ---------------------------------------------------------------------------


def test_categorize_known_code():
    assert categorize("0053") == ErrorCategory.VALIDATION
    assert categorize("0401") == ErrorCategory.AUTH
    assert categorize("0500") == ErrorCategory.TRANSIENT
    assert categorize("0100") == ErrorCategory.BUSINESS


def test_categorize_unknown_code_defaults_to_validation():
    """Unknown codes default to validation — safer than retry."""
    assert categorize("9999") == ErrorCategory.VALIDATION


def test_categorize_5xx_is_transient_when_no_code():
    assert categorize(None, http_status=502) == ErrorCategory.TRANSIENT
    assert categorize(None, http_status=503) == ErrorCategory.TRANSIENT


def test_categorize_401_403_are_auth():
    assert categorize(None, http_status=401) == ErrorCategory.AUTH
    assert categorize(None, http_status=403) == ErrorCategory.AUTH


# ---------------------------------------------------------------------------
# FbrClient — chaos
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, *, status_code, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data
        self.text = text

    def json(self):
        if self._json is None:
            import json as _json
            raise _json.JSONDecodeError("not json", self.text or "", 0)
        return self._json


def test_client_malformed_json_is_transient():
    """PRAL gateway returning HTML or other non-JSON → transient."""
    with patch.object(requests, "post",
                       return_value=_FakeResponse(status_code=502, text="<html>bad gateway</html>")):
        client = FbrClient(
            environment="sandbox", token="t",
            endpoint_base="https://gw.fbr.gov.pk",
        )
        with pytest.raises(PralTransientError):
            client.post_invoice({})


def test_client_200_with_status_code_01_is_failed_not_valid():
    """The classic gotcha: 200 OK doesn't mean validation passed.

    PRAL returns HTTP 200 with validationResponse.statusCode='01' to mean
    the request was well-formed but the data is invalid. This must be
    treated as a validation failure, NOT marked valid.
    """
    body = {
        "validationResponse": {
            "statusCode": "01",
            "status": "Invalid",
            "invoiceStatuses": [
                {"itemSNo": "1", "statusCode": "01",
                 "errorCode": "0053",
                 "error": "Provided Registration type does not match buyer's profile"},
            ],
        },
    }
    with patch.object(requests, "post",
                       return_value=_FakeResponse(status_code=200, json_data=body)):
        client = FbrClient(
            environment="sandbox", token="t",
            endpoint_base="https://gw.fbr.gov.pk",
        )
        with pytest.raises(PralValidationError) as exc:
            client.post_invoice({})
        assert exc.value.error_code == "0053"


def test_client_business_rule_error_is_typed():
    body = {
        "validationResponse": {
            "statusCode": "01",
            "status": "Invalid",
            "invoiceStatuses": [
                {"itemSNo": "1", "statusCode": "01",
                 "errorCode": "0100",
                 "error": "Edit window has passed"},
            ],
        },
    }
    with patch.object(requests, "post",
                       return_value=_FakeResponse(status_code=200, json_data=body)):
        client = FbrClient(environment="production", token="t",
                            endpoint_base="https://gw.fbr.gov.pk")
        with pytest.raises(PralBusinessError):
            client.post_invoice({})


def test_client_timeout_is_transient():
    with patch.object(requests, "post", side_effect=requests.Timeout("timed out")):
        client = FbrClient(environment="sandbox", token="t",
                            endpoint_base="https://gw.fbr.gov.pk")
        with pytest.raises(PralTransientError):
            client.post_invoice({})


def test_client_connection_error_is_transient():
    with patch.object(requests, "post",
                       side_effect=requests.ConnectionError("DNS lookup failed")):
        client = FbrClient(environment="sandbox", token="t",
                            endpoint_base="https://gw.fbr.gov.pk")
        with pytest.raises(PralTransientError):
            client.post_invoice({})


def test_client_uses_sandbox_suffix_url():
    """Sandbox URL gets the _sb suffix on the endpoint."""
    captured = {}
    def fake_post(url, **kw):
        captured["url"] = url
        return _FakeResponse(status_code=200, json_data={
            "invoiceNumber": "X", "validationResponse": {"statusCode": "00"},
        })
    with patch.object(requests, "post", side_effect=fake_post):
        client = FbrClient(environment="sandbox", token="t",
                            endpoint_base="https://gw.fbr.gov.pk")
        client.post_invoice({})
    assert captured["url"].endswith("/postinvoicedata_sb")


def test_client_uses_production_url_no_suffix():
    captured = {}
    def fake_post(url, **kw):
        captured["url"] = url
        return _FakeResponse(status_code=200, json_data={
            "invoiceNumber": "X", "validationResponse": {"statusCode": "00"},
        })
    with patch.object(requests, "post", side_effect=fake_post):
        client = FbrClient(environment="production", token="t",
                            endpoint_base="https://gw.fbr.gov.pk")
        client.post_invoice({})
    assert captured["url"].endswith("/postinvoicedata")
    assert "_sb" not in captured["url"]
