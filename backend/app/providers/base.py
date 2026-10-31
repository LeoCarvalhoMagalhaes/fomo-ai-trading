"""Infraestrutura comum aos adaptadores: limite de chamadas, saúde do provedor e requisições JSON."""
import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

BACKOFF_START_S = 2
BACKOFF_MAX_S = 300


class ProviderError(Exception):
    def __init__(self, provider: str, status: int | None, message: str):
        super().__init__(f"{provider}: {status} {message}")
        self.provider = provider
        self.status = status
        self.message = message


class RateLimiter:
    """Espaça chamadas uniformemente para nunca passar de `rpm` por minuto."""

    def __init__(self, rpm: int):
        self.interval = 60.0 / rpm
        self._next = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = self._next - now
            if wait > 0:
                await asyncio.sleep(wait)
                now = time.monotonic()
            self._next = max(now, self._next) + self.interval


@dataclass
class ProviderHealth:
    name: str
    ok: bool = True
    last_success: datetime | None = None
    last_error: str | None = None
    last_error_at: datetime | None = None
    consecutive_failures: int = 0
    backoff_until: datetime | None = None
    calls: deque = field(default_factory=lambda: deque(maxlen=2000))

    def record_success(self, now: datetime) -> None:
        self.ok = True
        self.last_success = now
        self.consecutive_failures = 0
        self.backoff_until = None

    def record_failure(self, error: str, now: datetime) -> None:
        self.ok = False
        self.last_error = error
        self.last_error_at = now
        self.consecutive_failures += 1
        delay = min(BACKOFF_START_S * 2 ** (self.consecutive_failures - 1), BACKOFF_MAX_S)
        self.backoff_until = now + timedelta(seconds=delay)

    def available(self, now: datetime) -> bool:
        return self.backoff_until is None or now >= self.backoff_until

    def calls_last_minute(self, now: datetime) -> int:
        cutoff = now - timedelta(minutes=1)
        return sum(1 for t in self.calls if t >= cutoff)

    def as_dict(self, now: datetime) -> dict:
        return {
            "name": self.name,
            "ok": self.ok,
            "last_success": self.last_success,
            "last_error": self.last_error,
            "last_error_at": self.last_error_at,
            "consecutive_failures": self.consecutive_failures,
            "backoff_until": self.backoff_until,
            "calls_last_minute": self.calls_last_minute(now),
        }


async def fetch_json(
    client: httpx.AsyncClient,
    url: str,
    params: dict | None,
    limiter: RateLimiter,
    health: ProviderHealth,
    headers: dict | None = None,
) -> Any:
    now = datetime.now(timezone.utc)
    if not health.available(now):
        raise ProviderError(health.name, None, f"em espera até {health.backoff_until:%H:%M:%S} UTC")
    await limiter.acquire()
    health.calls.append(datetime.now(timezone.utc))
    try:
        resp = await client.get(url, params=params, headers=headers, timeout=20)
    except httpx.HTTPError as exc:
        health.record_failure(f"rede: {exc.__class__.__name__}", datetime.now(timezone.utc))
        raise ProviderError(health.name, None, str(exc)) from exc
    if resp.status_code != 200:
        health.record_failure(f"HTTP {resp.status_code}", datetime.now(timezone.utc))
        raise ProviderError(health.name, resp.status_code, resp.text[:200])
    try:
        data = resp.json()
    except ValueError as exc:
        health.record_failure("JSON inválido", datetime.now(timezone.utc))
        raise ProviderError(health.name, 200, "JSON inválido") from exc
    health.record_success(datetime.now(timezone.utc))
    return data
