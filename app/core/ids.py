"""UUIDv7 generator with a stdlib-first polyfill.

Python 3.14 added :func:`uuid.uuid7`. We prefer the stdlib implementation
when available and fall back to an RFC 9562-compliant pure-Python version
so older interpreters (3.13 in our prod Docker image) keep working.
"""

from __future__ import annotations

import os
import time
import uuid

if hasattr(uuid, "uuid7"):
    uuid7 = uuid.uuid7  # type: ignore[attr-defined]
else:

    def uuid7() -> uuid.UUID:
        ms = int(time.time() * 1000) & 0xFFFFFFFFFFFF
        rand_a = int.from_bytes(os.urandom(2), "big") & 0x0FFF
        rand_b = int.from_bytes(os.urandom(8), "big") & 0x3FFFFFFFFFFFFFFF
        value = (ms << 80) | (0x7 << 76) | (rand_a << 64) | (0b10 << 62) | rand_b
        return uuid.UUID(int=value)


__all__ = ["uuid7"]
