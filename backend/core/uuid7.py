"""UUID v7 generator (time-ordered, sortable).

Single home for the UUIDv7 helper used as the default for primary keys across
the project. Mirrors the wire format of draft-ietf-uuidrev-rfc4122bis. Until
Python's stdlib ships v7, we implement it locally.

Why v7: time-prefixed UUIDs cluster well in Postgres B-trees (sequential
inserts → cheap index updates) while preserving global uniqueness. Plain v4
fragments index pages and hurts insert throughput.

The Postgres-side default for tables is set via migration RunSQL to call
gen_random_uuid() (v4) so direct SQL inserts still work; Django ORM inserts
go through this function and get v7. Mixing is fine — both are 128 bits, both
satisfy UNIQUE, only sort order differs.
"""

from __future__ import annotations

import os
import time
import uuid


def uuid7() -> uuid.UUID:
    """Return a UUID v7 (48-bit unix-millis time prefix + 74 random bits)."""
    ms = int(time.time() * 1000) & 0xFFFFFFFFFFFF  # 48 bits
    rand_a = int.from_bytes(os.urandom(2), "big") & 0x0FFF
    rand_b = int.from_bytes(os.urandom(8), "big") & 0x3FFFFFFFFFFFFFFF

    # Layout per draft-ietf-uuidrev-rfc4122bis §5.7
    int_value = (
        (ms << 80)
        | (0x7 << 76)         # version 7
        | (rand_a << 64)
        | (0b10 << 62)        # variant 10
        | rand_b
    )
    return uuid.UUID(int=int_value)
