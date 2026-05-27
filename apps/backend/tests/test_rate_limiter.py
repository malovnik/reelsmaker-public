"""Unit-тесты RateLimiter (token-bucket)."""

from __future__ import annotations

import asyncio
import time

import pytest

from videomaker.services.rate_limiter import RateLimiter


def test_init_valid() -> None:
    rl = RateLimiter(max_per_minute=60)
    assert rl.available_tokens == pytest.approx(60.0, abs=0.1)


def test_init_invalid_raises() -> None:
    with pytest.raises(ValueError, match="max_per_minute"):
        RateLimiter(max_per_minute=0)


@pytest.mark.asyncio
async def test_acquire_one_immediate_when_bucket_full() -> None:
    rl = RateLimiter(max_per_minute=60)
    start = time.monotonic()
    await rl.acquire_one()
    elapsed = time.monotonic() - start
    assert elapsed < 0.05


@pytest.mark.asyncio
async def test_acquire_drains_bucket() -> None:
    rl = RateLimiter(max_per_minute=60)
    for _ in range(10):
        await rl.acquire_one()
    assert 49 < rl.available_tokens < 51


@pytest.mark.asyncio
async def test_acquire_context_manager_works() -> None:
    rl = RateLimiter(max_per_minute=60)
    async with rl.acquire():
        pass
    assert 58 < rl.available_tokens < 60


@pytest.mark.asyncio
async def test_refill_over_time() -> None:
    """max=3600 (60/сек refill): после 0.1 сек пустой бакет отдаст ~6 токенов."""
    rl = RateLimiter(max_per_minute=3600)
    rl._tokens = 0  # type: ignore[attr-defined]
    rl._last_refill = time.monotonic()  # type: ignore[attr-defined]
    await asyncio.sleep(0.1)
    tokens = rl.available_tokens
    assert 4 <= tokens <= 10, f"expected ~6 tokens after 0.1s at 3600 rpm, got {tokens}"


@pytest.mark.asyncio
async def test_acquire_waits_when_empty() -> None:
    """Пустой бакет заставляет acquire ждать refill."""
    rl = RateLimiter(max_per_minute=600)  # 10 токенов/сек
    rl._tokens = 0  # type: ignore[attr-defined]
    rl._last_refill = time.monotonic()  # type: ignore[attr-defined]

    start = time.monotonic()
    await rl.acquire_one()
    elapsed = time.monotonic() - start
    assert 0.08 < elapsed < 0.25


@pytest.mark.asyncio
async def test_concurrent_acquires_serialise() -> None:
    """Параллельные acquire не приводят к underflow."""
    rl = RateLimiter(max_per_minute=600)
    rl._tokens = 5  # type: ignore[attr-defined]

    async def acquire_task() -> None:
        await rl.acquire_one()

    start = time.monotonic()
    await asyncio.gather(*(acquire_task() for _ in range(5)))
    elapsed = time.monotonic() - start
    assert elapsed < 0.3
