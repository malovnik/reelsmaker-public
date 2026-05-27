"""Vision layer smoke tests — проверяем что инфра собирается и disabled-режим чист.

Цель: НЕ загрузить Moondream GGUF (~2.5 GB) в CI. Только:
1. Import chain работает.
2. Factory возвращает None при disabled.
3. VisionClient Protocol duck-type проходит.
4. Rate limiter concurrency OK.
5. Frame cache path construction корректна.
6. VisionResultCache round-trip (put → get → reload).
7. VisionRuntimeSettings валидация границ.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from videomaker.core.config import get_settings
from videomaker.models.vision_settings import VisionRuntimeSettings
from videomaker.services.vision import (
    FrameExtractor,
    MoondreamLocalClient,
    VisionClient,
    VisionDetection,
    VisionHealthStatus,
    VisionModelManager,
    VisionQueryResult,
    VisionRateLimiter,
    VisionResultCache,
    build_vision_client,
    compute_video_sha256,
    get_vision_rate_limiter,
    reset_vision_rate_limiter,
)


def test_factory_disabled_returns_none() -> None:
    # Пользовательский .env может иметь VISION_ENABLED=true; конструируем
    # чистые Settings для проверки invariant "disabled → None".
    cfg = get_settings().model_copy(update={"vision_enabled": False})
    assert cfg.vision_enabled is False
    assert build_vision_client(cfg) is None


def test_protocol_duck_type() -> None:
    cfg = get_settings()
    mgr = VisionModelManager(cfg)
    client = MoondreamLocalClient(cfg, mgr)
    assert isinstance(client, VisionClient)


def test_vision_runtime_settings_validation() -> None:
    vs = VisionRuntimeSettings(enabled=True, frame_sample_rate_sec=5.5)
    assert vs.enabled is True
    assert vs.frame_sample_rate_sec == 5.5

    with pytest.raises(ValueError):
        VisionRuntimeSettings(enabled=True, frame_sample_rate_sec=0.1)
    with pytest.raises(ValueError):
        VisionRuntimeSettings(enabled=True, frame_sample_rate_sec=120.0)


def test_query_result_frozen() -> None:
    r = VisionQueryResult(
        answer="yes", raw_response="yes", confidence=0.9, latency_ms=100.0
    )
    with pytest.raises((TypeError, ValueError, Exception)):
        r.answer = "no"  # type: ignore[misc]


def test_detection_center_normalized() -> None:
    d = VisionDetection(
        label="face", bbox_xywh_norm=(0.2, 0.3, 0.4, 0.5), confidence=0.8
    )
    assert d.center_norm == (0.4, 0.55)


def test_rate_limiter_concurrency() -> None:
    reset_vision_rate_limiter()
    cfg = get_settings()
    limiter = get_vision_rate_limiter(cfg)
    assert isinstance(limiter, VisionRateLimiter)
    assert limiter.max_concurrent == cfg.vision_max_concurrency

    with pytest.raises(ValueError):
        VisionRateLimiter(0)


async def test_rate_limiter_acquire_releases() -> None:
    reset_vision_rate_limiter()
    limiter = VisionRateLimiter(max_concurrent=2)
    async with limiter.acquire(), limiter.acquire():
        pass


async def test_sha256_matches_hashlib() -> None:
    import hashlib as _h

    with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as fh:
        fh.write(b"hello vision layer")
        path = Path(fh.name)
    try:
        digest = await compute_video_sha256(path)
        assert digest == _h.sha256(b"hello vision layer").hexdigest()
    finally:
        path.unlink()


async def test_result_cache_roundtrip() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cache = VisionResultCache(Path(tmp))
        params = {"prompt": "Is face?", "max_tokens": 32}
        assert await cache.get("h1", "query", 10.0, params) is None

        await cache.put(
            "h1", "query", 10.0, params, {"answer": "yes", "confidence": 0.9}
        )
        got = await cache.get("h1", "query", 10.0, params)
        assert got == {"answer": "yes", "confidence": 0.9}

        # Разные params → miss
        assert await cache.get("h1", "query", 10.0, {"prompt": "diff"}) is None

        # Перезагрузка из JSONL
        cache2 = VisionResultCache(Path(tmp))
        got2 = await cache2.get("h1", "query", 10.0, params)
        assert got2 == {"answer": "yes", "confidence": 0.9}


def test_frame_extractor_path_construction() -> None:
    fe = FrameExtractor(Path("/tmp/vc"))
    assert fe._frame_path("hash1", 5.5) == Path("/tmp/vc/hash1/frames/5.500.jpg")


def test_moondream_parser_first_word() -> None:
    assert MoondreamLocalClient._parse_yes_no("Yes, it is.") == ("yes", 0.9)
    assert MoondreamLocalClient._parse_yes_no("no") == ("no", 0.9)
    assert MoondreamLocalClient._parse_yes_no("Maybe...") == ("unknown", 0.0)
    assert MoondreamLocalClient._parse_yes_no("") == ("unknown", 0.0)


def test_moondream_parser_hedged() -> None:
    assert MoondreamLocalClient._parse_yes_no("It looks like yes") == ("yes", 0.6)
    assert MoondreamLocalClient._parse_yes_no("I think no") == ("no", 0.6)


async def test_health_without_loaded_model() -> None:
    cfg = get_settings()
    mgr = VisionModelManager(cfg)
    client = MoondreamLocalClient(cfg, mgr)
    h = await client.health()
    assert isinstance(h, VisionHealthStatus)
    assert h.model_loaded is False
    assert h.backend in ("metal", "cpu", "unavailable")
