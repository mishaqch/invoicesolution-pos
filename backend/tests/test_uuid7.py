"""UUID v7 helper sanity checks."""

from __future__ import annotations

import time
import uuid

from core.uuid7 import uuid7


def test_uuid7_returns_uuid():
    u = uuid7()
    assert isinstance(u, uuid.UUID)


def test_uuid7_version_is_7():
    u = uuid7()
    # Version is the high nibble of the 7th byte (the 'M' field).
    assert (u.int >> 76) & 0xF == 0x7


def test_uuid7_is_time_ordered():
    a = uuid7()
    time.sleep(0.002)
    b = uuid7()
    assert a < b, "uuid7 should be sortable in generation order"


def test_uuid7_uniqueness():
    seen = {uuid7() for _ in range(1000)}
    assert len(seen) == 1000
