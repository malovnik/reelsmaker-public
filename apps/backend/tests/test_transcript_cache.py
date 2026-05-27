"""Smoke-тесты transcript cache — hit/miss/force_reingest + transcribe_with_cache."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from videomaker.services.transcribers.base import (
    TranscribedSegment,
    TranscribedWord,
    TranscriptResult,
)
from videomaker.services.transcribers.cache import (
    TranscriptCache,
    compute_video_sha256,
    compute_wpm,
)
from videomaker.services.transcribers.factory import transcribe_with_cache


def _make_result(
    *, backend: str = "mlx_whisper", model: str = "large-v3", words: int = 12
) -> TranscriptResult:
    word_list = [
        TranscribedWord(word=f"w{i}", start=float(i) * 0.5, end=float(i) * 0.5 + 0.4)
        for i in range(words)
    ]
    segment = TranscribedSegment(
        text=" ".join(w.word for w in word_list),
        start=0.0,
        end=word_list[-1].end if word_list else 0.0,
        words=word_list,
    )
    return TranscriptResult(
        transcriber=backend,
        model=model,
        language="ru",
        duration_sec=word_list[-1].end if word_list else 0.0,
        segments=[segment],
        words=word_list,
    )


def _fake_video(tmp_path: Path, content: bytes = b"pretend video bytes") -> Path:
    video = tmp_path / "clip.mp4"
    video.write_bytes(content)
    return video


class _StubTranscriber:
    """Контракт Transcriber без реального STT — считает вызовы."""

    def __init__(self, result: TranscriptResult) -> None:
        self.name = result.transcriber
        self.model = result.model
        self._result = result
        self.call_count = 0

    async def transcribe(
        self, audio_path: Path, *, language: str | None = None
    ) -> TranscriptResult:
        self.call_count += 1
        return self._result


@pytest.mark.asyncio
async def test_cache_lookup_empty_returns_none(tmp_path: Path) -> None:
    video = _fake_video(tmp_path)
    cache = TranscriptCache(tmp_path / "transcripts")
    assert await cache.lookup(video) is None


@pytest.mark.asyncio
async def test_cache_store_then_lookup_returns_result(tmp_path: Path) -> None:
    video = _fake_video(tmp_path)
    cache = TranscriptCache(tmp_path / "transcripts")
    result = _make_result()

    stored = await cache.store(video, result)
    loaded = await cache.lookup(video)

    assert loaded is not None
    assert loaded.video_hash == stored.video_hash
    assert loaded.result.full_text == result.full_text
    assert loaded.meta.backend == "mlx_whisper"
    assert loaded.meta.word_count == len(result.words)
    assert loaded.meta.wpm == compute_wpm(result)


@pytest.mark.asyncio
async def test_cache_invalidate_removes_entry(tmp_path: Path) -> None:
    video = _fake_video(tmp_path)
    cache = TranscriptCache(tmp_path / "transcripts")
    await cache.store(video, _make_result())

    removed = await cache.invalidate(video)
    assert removed is True
    assert await cache.lookup(video) is None


@pytest.mark.asyncio
async def test_cache_sha256_is_stable_per_content(tmp_path: Path) -> None:
    a = tmp_path / "a.mp4"
    a.write_bytes(b"identical content")
    b = tmp_path / "b.mp4"
    b.write_bytes(b"identical content")
    c = tmp_path / "c.mp4"
    c.write_bytes(b"different content")

    ha = await compute_video_sha256(a)
    hb = await compute_video_sha256(b)
    hc = await compute_video_sha256(c)

    assert ha == hb
    assert ha != hc


@pytest.mark.asyncio
async def test_transcribe_with_cache_miss_calls_backend(tmp_path: Path) -> None:
    video = _fake_video(tmp_path)
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"wav")
    cache = TranscriptCache(tmp_path / "transcripts")
    stub = _StubTranscriber(_make_result())

    outcome = await transcribe_with_cache(
        video_path=video,
        audio_path=audio,
        transcriber=stub,  # type: ignore[arg-type]
        cache=cache,
    )

    assert stub.call_count == 1
    assert outcome.cache_hit is False
    assert outcome.result.full_text


@pytest.mark.asyncio
async def test_transcribe_with_cache_hit_skips_backend(tmp_path: Path) -> None:
    video = _fake_video(tmp_path)
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"wav")
    cache = TranscriptCache(tmp_path / "transcripts")
    stub = _StubTranscriber(_make_result())

    first = await transcribe_with_cache(
        video_path=video,
        audio_path=audio,
        transcriber=stub,  # type: ignore[arg-type]
        cache=cache,
    )
    second = await transcribe_with_cache(
        video_path=video,
        audio_path=audio,
        transcriber=stub,  # type: ignore[arg-type]
        cache=cache,
    )

    assert stub.call_count == 1  # второй вызов не дошёл до backend
    assert first.cache_hit is False
    assert second.cache_hit is True
    assert first.video_hash == second.video_hash


@pytest.mark.asyncio
async def test_transcribe_with_cache_force_reingest_rebuilds(tmp_path: Path) -> None:
    video = _fake_video(tmp_path)
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"wav")
    cache = TranscriptCache(tmp_path / "transcripts")
    stub = _StubTranscriber(_make_result())

    await transcribe_with_cache(
        video_path=video,
        audio_path=audio,
        transcriber=stub,  # type: ignore[arg-type]
        cache=cache,
    )
    outcome = await transcribe_with_cache(
        video_path=video,
        audio_path=audio,
        transcriber=stub,  # type: ignore[arg-type]
        cache=cache,
        force_reingest=True,
    )

    assert stub.call_count == 2
    assert outcome.cache_hit is False


@pytest.mark.asyncio
async def test_transcribe_with_cache_backend_mismatch_rebuilds(tmp_path: Path) -> None:
    video = _fake_video(tmp_path)
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"wav")
    cache = TranscriptCache(tmp_path / "transcripts")
    stub_mlx = _StubTranscriber(_make_result(backend="mlx_whisper", model="v1"))
    stub_deepgram = _StubTranscriber(_make_result(backend="deepgram", model="nova-3"))

    await transcribe_with_cache(
        video_path=video,
        audio_path=audio,
        transcriber=stub_mlx,  # type: ignore[arg-type]
        cache=cache,
    )
    outcome = await transcribe_with_cache(
        video_path=video,
        audio_path=audio,
        transcriber=stub_deepgram,  # type: ignore[arg-type]
        cache=cache,
    )

    assert stub_deepgram.call_count == 1
    assert outcome.cache_hit is False
    assert outcome.result.transcriber == "deepgram"


def test_compute_wpm_zero_duration() -> None:
    result = TranscriptResult(
        transcriber="mlx_whisper",
        model="v1",
        language="ru",
        duration_sec=0.0,
        segments=[],
        words=[],
    )
    assert compute_wpm(result) == 0.0


def test_compute_wpm_is_positive(_: Any = None) -> None:
    result = _make_result(words=60)
    wpm = compute_wpm(result)
    assert wpm > 0
