"""Rate limiter для vision inference.

Отдельный от Gemini limiter — разные ограничения:
* Gemini: rate limit по QPS (облако)
* Moondream Local: GPU serialization (Metal single-threaded), semaphore
  ограничивает concurrent inference calls. Default max_concurrent=2 позволяет
  перекрывать I/O (ffmpeg frame extract) и inference.

API совместимо с `llama_rate_limiter.acquire()` — `async with limiter.acquire():`.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from videomaker.core.config import Settings, get_settings
from videomaker.core.logging import get_logger

log = get_logger(__name__)


class VisionRateLimiter:
    """Async semaphore-based limiter для vision inference.

    Не реализует token-bucket или QPS throttling — только параллелизм, т.к.
    local inference не rate-limited со стороны провайдера.
    """

    def __init__(self, max_concurrent: int) -> None:
        if max_concurrent < 1:
            raise ValueError(f"max_concurrent must be >= 1, got {max_concurrent}")
        self._sem = asyncio.Semaphore(max_concurrent)
        self._max_concurrent = max_concurrent

    @property
    def max_concurrent(self) -> int:
        return self._max_concurrent

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[None]:
        await self._sem.acquire()
        try:
            yield
        finally:
            self._sem.release()


_vision_limiter: VisionRateLimiter | None = None


def get_vision_rate_limiter(settings: Settings | None = None) -> VisionRateLimiter:
    """Process-wide singleton. Создаётся при первом вызове по cfg.vision_max_concurrency."""
    global _vision_limiter
    if _vision_limiter is None:
        cfg = settings or get_settings()
        _vision_limiter = VisionRateLimiter(cfg.vision_max_concurrency)
        log.info(
            "vision_rate_limiter_initialized",
            max_concurrent=cfg.vision_max_concurrency,
        )
    return _vision_limiter


def reset_vision_rate_limiter() -> None:
    """Для тестов — сбрасывает singleton."""
    global _vision_limiter
    _vision_limiter = None
