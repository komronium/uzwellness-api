from __future__ import annotations

import logging

import pytest

from app.core import rate_limit
from app.core.rate_limit import RateLimiter


class _BrokenClient:
    """A Redis client that connected fine but now fails mid-life."""

    async def incr(self, key: str) -> int:
        raise ConnectionError("connection reset by peer")

    async def expire(self, key: str, seconds: int) -> None:
        raise AssertionError("unreachable: incr fails before expire")


@pytest.fixture(autouse=True)
def _reset_rate_limit_state():
    rate_limit._memory_counts.clear()
    rate_limit._last_fallback_log = 0.0
    yield
    rate_limit._memory_counts.clear()
    rate_limit._last_fallback_log = 0.0


async def test_increment_falls_back_to_memory_when_redis_has_no_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(rate_limit, "get_redis", _fake_get_redis(None))
    limiter = RateLimiter(prefix="t", limit=5, window_seconds=60)

    count = await limiter._increment("rl:t:ip:1.2.3.4")

    assert count == 1
    assert rate_limit._memory_counts["rl:t:ip:1.2.3.4"][0] == 1


async def test_increment_falls_back_and_recovers_when_redis_errors_mid_life(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(rate_limit, "get_redis", _fake_get_redis(_BrokenClient()))
    closed = {"called": False}

    async def fake_close_redis() -> None:
        closed["called"] = True

    monkeypatch.setattr(rate_limit, "close_redis", fake_close_redis)
    limiter = RateLimiter(prefix="t", limit=5, window_seconds=60)

    count = await limiter._increment("rl:t:ip:5.6.7.8")

    assert count == 1
    assert rate_limit._memory_counts["rl:t:ip:5.6.7.8"][0] == 1
    # The broken client must be dropped so the next request re-validates a
    # fresh connection instead of retrying the same broken one forever.
    assert closed["called"] is True


async def test_fallback_is_logged_but_rate_limited(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(rate_limit, "get_redis", _fake_get_redis(None))
    limiter = RateLimiter(prefix="t", limit=5, window_seconds=60)

    with caplog.at_level(logging.WARNING, logger="app.core.rate_limit"):
        await limiter._increment("rl:t:ip:9.9.9.9")
        await limiter._increment("rl:t:ip:9.9.9.9")

    fallback_logs = [r for r in caplog.records if "falling back" in r.message]
    assert len(fallback_logs) == 1


def _fake_get_redis(value):
    async def _get_redis():
        return value

    return _get_redis
