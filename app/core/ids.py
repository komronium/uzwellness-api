from __future__ import annotations

import os
import time
import uuid

_stdlib_uuid7 = getattr(uuid, "uuid7", None)

if _stdlib_uuid7 is not None:
    uuid7 = _stdlib_uuid7
else:

    def uuid7() -> uuid.UUID:
        ms = int(time.time() * 1000) & 0xFFFFFFFFFFFF
        rand_a = int.from_bytes(os.urandom(2), "big") & 0x0FFF
        rand_b = int.from_bytes(os.urandom(8), "big") & 0x3FFFFFFFFFFFFFFF
        value = (ms << 80) | (0x7 << 76) | (rand_a << 64) | (0b10 << 62) | rand_b
        return uuid.UUID(int=value)


__all__ = ["uuid7"]
