"""Fernet-based encryption for FBR tokens.

The key lives in env (FBR_FERNET_KEY). For dev/tests where the key is empty,
we derive a deterministic 32-byte key from SECRET_KEY so the test suite
is reproducible without requiring every dev to generate one.

In production, FBR_FERNET_KEY MUST be set to a real `Fernet.generate_key()`
output (urlsafe-base64-encoded 32 random bytes). A migration smoke test
verifies that a `pg_dump` of fbr_tokens contains only ciphertext, never
plaintext tokens.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _resolve_key() -> bytes:
    raw = getattr(settings, "FBR_FERNET_KEY", "") or ""
    if raw:
        return raw.encode() if isinstance(raw, str) else raw
    # Deterministic fallback for dev/tests only. Hashed so we don't expose
    # SECRET_KEY directly into ciphertext.
    digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()  # 32 bytes
    return base64.urlsafe_b64encode(digest)


def _fernet() -> Fernet:
    return Fernet(_resolve_key())


def encrypt(plaintext: str) -> str:
    """Return a urlsafe-base64 ciphertext string."""
    if plaintext is None:
        return ""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    if not ciphertext:
        return ""
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Invalid or tampered FBR token ciphertext.") from exc
