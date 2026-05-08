"""QR code generation for FBR receipts.

Per INTEGRATIONS.md §1.12: PRAL hadn't published the official QR spec as
of v1.6 of the manual. We use a JSON payload of the verifiable fields and
render it as a base64-encoded PNG. When PRAL publishes the spec, swap the
payload encoding here — the rest of the pipeline doesn't need to change.
"""

from __future__ import annotations

import base64
import io
import json
from datetime import datetime
from decimal import Decimal

import qrcode


def build_qr_payload(*, fbr_invoice_number: str, validated_at: datetime,
                     amount: Decimal, seller_ntn: str) -> str:
    """Stable payload string. JSON-encoded for forward-compat."""
    return json.dumps({
        "invoiceNumber": fbr_invoice_number,
        "validatedAt": validated_at.isoformat(),
        "amount": str(amount),
        "sellerNTN": seller_ntn,
    }, sort_keys=True, separators=(",", ":"))


def render_png_b64(payload: str) -> str:
    """Return a `data:image/png;base64,…` URI suitable for HTML or ESC/POS image upload."""
    img = qrcode.make(payload)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"
