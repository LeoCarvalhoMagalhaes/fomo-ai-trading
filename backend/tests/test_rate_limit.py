import time
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

from app.providers.base import ProviderError, ProviderHealth, RateLimiter, fetch_json


async def test_limiter_spaces_calls():
    lim = RateLimiter(rpm=600)  # uma chamada a cada 0,1 s
    t0 = time.monotonic()
    for _ in range(3):
        await lim.acquire()
    assert time.monotonic() - t0 >= 0.19


def test_backoff_caps_at_300s():
    h = ProviderHealth("x")
    now = datetime(2026, 10, 31, tzinfo=timezone.utc)
    for _ in range(20):
        h.record_failure("erro", now)
    assert h.backoff_until - now == timedelta(seconds=300)
    assert not h.available(now)
    assert h.available(now + timedelta(seconds=301))
    h.record_success(now)
    assert h.consecutive_failures == 0 and h.available(now)


def test_backoff_starts_at_2s():
    h = ProviderHealth("x")
    now = datetime(2026, 10, 31, tzinfo=timezone.utc)
    h.record_failure("erro", now)
    assert h.backoff_until - now == timedelta(seconds=2)


@respx.mock
async def test_fetch_json_429_records_failure():
    respx.get("https://api.test/x").mock(return_value=httpx.Response(429, text="too many"))
    h = ProviderHealth("teste")
    async with httpx.AsyncClient() as client:
        with pytest.raises(ProviderError) as exc:
            await fetch_json(client, "https://api.test/x", None, RateLimiter(6000), h)
    assert exc.value.status == 429
    assert h.consecutive_failures == 1
    assert not h.ok


@respx.mock
async def test_fetch_json_skips_while_backing_off():
    route = respx.get("https://api.test/y").mock(return_value=httpx.Response(200, json={"a": 1}))
    h = ProviderHealth("teste")
    h.record_failure("erro", datetime.now(timezone.utc))
    async with httpx.AsyncClient() as client:
        with pytest.raises(ProviderError):
            await fetch_json(client, "https://api.test/y", None, RateLimiter(6000), h)
    assert route.call_count == 0
