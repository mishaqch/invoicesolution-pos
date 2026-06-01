"""Signed share links for sending the invoice PDF to a buyer.

WhatsApp's `wa.me` deep-link and `mailto:` URIs cannot attach files —
they only carry text. To let the seller "send the invoice" to a buyer
via either channel, we mint a short-lived, HMAC-signed URL pointing
at the existing PDF endpoint, with auth replaced by signature
verification.

Design notes:

- We use Django's built-in TimestampSigner (HMAC-SHA256 keyed by
  SECRET_KEY). No new dependencies, no token storage. The TTL is
  enforced by `max_age` on unsign, so a leaked link expires on its
  own without us tracking anything server-side.

- The signed payload is just the invoice ID. We deliberately do NOT
  encode the buyer's email/phone in it — the link is "anyone with
  the URL can download", same trust model as Stripe receipts or
  Dropbox share links.

- Defaults to 7 days. Long enough that a buyer opening a WhatsApp
  message days later still gets the PDF; short enough that a leaked
  URL doesn't become a permanent backdoor.

- Only FBR-validated invoices get a share URL. Drafts (pending_sync,
  failed) have nothing useful to share yet — the PDF watermarks itself
  as "not yet FBR-validated" anyway, so suppressing the URL avoids
  confusing the buyer.
"""

from __future__ import annotations

from django.core.signing import BadSignature, SignatureExpired, TimestampSigner

from apps.sales.models import Invoice


_SIGNER_SALT = "sales.share_invoice_pdf"
DEFAULT_TTL_SECONDS = 7 * 24 * 3600  # 7 days


def mint_share_token(invoice_id) -> str:
    """Sign + timestamp the invoice id. Returns the URL-safe token."""
    signer = TimestampSigner(salt=_SIGNER_SALT)
    return signer.sign(str(invoice_id))


def verify_share_token(token: str, max_age: int = DEFAULT_TTL_SECONDS) -> str:
    """Verify a share token. Returns the invoice id (as str).

    Raises:
        SignatureExpired: token older than max_age.
        BadSignature: token forged or tampered.
    """
    signer = TimestampSigner(salt=_SIGNER_SALT)
    return signer.unsign(token, max_age=max_age)


def build_share_url(invoice: Invoice, *, request=None) -> str | None:
    """Mint the public share URL for an invoice, or None if the invoice
    isn't yet shareable (no FBR-validated PDF to send).

    URL resolution priority:
      1. If `request` is provided, use `request.build_absolute_uri()`.
         This is the path the DRF serializer hits and produces the
         right host even behind a reverse proxy.
      2. Otherwise fall back to the `PUBLIC_BASE_URL` setting (read
         from env). Used by Celery tasks / management commands that
         don't have a live request but still need to mint a URL the
         buyer can click.
      3. As a last resort, return a relative path. The frontend will
         render it relative to its own origin — usable inside admin-
         web but NOT for pasting into a WhatsApp/email message.
    """
    if not invoice.fbr_invoice_number:
        return None
    token = mint_share_token(invoice.id)
    path = f"/p/inv/{token}.pdf"
    if request is not None:
        return request.build_absolute_uri(path)
    from django.conf import settings
    base = getattr(settings, "PUBLIC_BASE_URL", "") or ""
    if base:
        return f"{base.rstrip('/')}{path}"
    return path


# Re-export the signing exceptions so callers don't need to know
# they come from django.core.signing.
__all__ = [
    "BadSignature",
    "SignatureExpired",
    "DEFAULT_TTL_SECONDS",
    "build_share_url",
    "mint_share_token",
    "verify_share_token",
]
