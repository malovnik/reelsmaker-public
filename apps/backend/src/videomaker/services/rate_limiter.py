"""Token-bucket rate limiter для Gemini API.

Default: 60 RPM (`gemini_rate_limit_rpm` из Settings). Shared instance между
агентами через `get_gemini_rate_limiter()`. Thread-safe через asyncio.Lock.

Использование:

    limiter = get_gemini_rate_limiter()
    async with limiter.acquire():
        response = await client.complete_json(...)

Token-bucket точнее leaky bucket: разрешает burst'ы до `max_per_minute`
при условии что средняя скорость не превышает квоту.
"""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from functools import lru_cache

from videomaker.core.config import get_settings
from videomaker.core.logging import get_logger

log = get_logger(__name__)


class RateLimiter:
    """Token-bucket с refill rate = max_per_minute / 60 токенов/сек."""

    def __init__(self, max_per_minute: int) -> None:
        if max_per_minute <= 0:
            raise ValueError(
                f"max_per_minute must be > 0, got {max_per_minute}"
            )
        self._max = float(max_per_minute)
        self._refill_rate = max_per_minute / 60.0
        self._tokens = float(max_per_minute)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire_one(self) -> None:
        """Блокирует до появления 1 свободного токена и списывает его."""
        async with self._lock:
            while True:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                needed = 1.0 - self._tokens
                sleep_for = needed / self._refill_rate
                await asyncio.sleep(sleep_for)

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        if elapsed <= 0:
            return
        added = elapsed * self._refill_rate
        self._tokens = min(self._max, self._tokens + added)
        self._last_refill = now

    @property
    def available_tokens(self) -> float:
        self._refill()
        return self._tokens

    @asynccontextmanager
    async def acquire(self):
        await self.acquire_one()
        yield


@lru_cache(maxsize=1)
def get_gemini_rate_limiter() -> RateLimiter:
    settings = get_settings()
    return RateLimiter(max_per_minute=settings.gemini_rate_limit_rpm)


@lru_cache(maxsize=1)
def get_zhipu_rate_limiter() -> RateLimiter:
    """Отдельный лимитер для Zhipu Coding Plan.

    Coding Plan Lite: ~80 prompts / 5h, где 1 prompt = 15-20 model invocations.
    Это ≈ 5 RPM в среднем. Pro и Max — выше, но без документированного RPM.
    Дефолт берётся из `zhipu_rate_limit_rpm` в Settings.
    """

    settings = get_settings()
    return RateLimiter(max_per_minute=settings.zhipu_rate_limit_rpm)


@lru_cache(maxsize=1)
def get_zhipu_concurrency_gate() -> asyncio.Semaphore:
    """Глобальный семафор, ограничивающий число одновременных Zhipu-запросов.

    Coding Plan имеет concurrency=1 (один in-flight запрос) — pipeline
    нужно сериализовать, иначе 429 code 1302. Shared singleton между всеми
    GLMClient instances через ``lru_cache``.
    """

    settings = get_settings()
    return asyncio.Semaphore(settings.zhipu_max_concurrency)
