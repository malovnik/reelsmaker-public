"""Unit-тесты compression.py с мок-LLM (без реальных API вызовов)."""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from videomaker.services.chunker import TranscriptChunk
from videomaker.services.compression import compress_chunks
from videomaker.services.llm_client import LLMError, LLMResponse
from videomaker.services.rate_limiter import RateLimiter
from videomaker.services.transcribers.base import TranscribedSegment


@dataclass
class MockLLMResponse:
    """Mock-клиент: отдаёт заранее заданные responses по очереди."""

    responses: list[str] | None = None
    responses_cycle: list[str] | None = None
    exception: Exception | None = None
    provider: str = "mock"
    model: str = "mock-model"

    def __post_init__(self) -> None:
        self._call_count = 0

    async def complete_json(
        self, *, system: str, user: str,
        temperature: float = 0.3, max_tokens: int = 8000,
    ) -> LLMResponse:
        if self.exception:
            raise self.exception
        if self.responses_cycle:
            text = self.responses_cycle[self._call_count % len(self.responses_cycle)]
        elif self.responses:
            text = self.responses[self._call_count]
        else:
            text = '{"summary":"mock"}'
        self._call_count += 1
        return LLMResponse(
            text=text,
            input_tokens=100,
            output_tokens=50,
            cache_read_tokens=None,
            cache_creation_tokens=None,
            provider=self.provider,
            model=self.model,
        )


def _mock_chunk(
    index: int, start: float, end: float, text: str = "sample"
) -> TranscriptChunk:
    return TranscriptChunk(
        index=index,
        start_sec=start,
        end_sec=end,
        text=f"[chunk {index}]",
        segments=[TranscribedSegment(text=text, start=start, end=end)],
        token_count=50,
    )


@pytest.mark.asyncio
async def test_compress_empty_list() -> None:
    assert (await compress_chunks([])).chunks == []


@pytest.mark.asyncio
async def test_compress_single_chunk_with_mock() -> None:
    mock_response = json.dumps({
        "chunk_index": 0,
        "time_range_sec": [0.0, 60.0],
        "summary": "Speaker 0 рассказывает историю о потере",
        "key_speakers": ["speaker_0"],
        "notable_quotes": [
            {"quote": "Всё было зря", "sec": 30.0, "speaker": "speaker_0"}
        ],
        "emotional_peaks": [
            {"sec": 45.0, "kind": "confession", "note": "переломный момент"}
        ],
    })
    client = MockLLMResponse(responses=[mock_response])
    limiter = RateLimiter(max_per_minute=600)

    result = await compress_chunks(
        [_mock_chunk(0, 0.0, 60.0)],
        client=client,  # type: ignore[arg-type]
        rate_limiter=limiter,
    )

    assert len(result.chunks) == 1
    c = result.chunks[0]
    assert c.summary == "Speaker 0 рассказывает историю о потере"
    assert c.key_speakers == ["speaker_0"]
    assert len(c.notable_quotes) == 1
    assert c.notable_quotes[0].quote == "Всё было зря"
    assert len(c.emotional_peaks) == 1
    assert c.emotional_peaks[0].kind == "confession"


@pytest.mark.asyncio
async def test_compress_multiple_chunks_preserves_order() -> None:
    responses = [
        json.dumps({
            "chunk_index": i,
            "time_range_sec": [i * 60, (i + 1) * 60],
            "summary": f"chunk {i} summary",
            "key_speakers": [],
        })
        for i in range(3)
    ]
    client = MockLLMResponse(responses=responses)
    limiter = RateLimiter(max_per_minute=600)

    chunks = [_mock_chunk(i, i * 60.0, (i + 1) * 60.0) for i in range(3)]
    result = await compress_chunks(
        chunks, client=client, rate_limiter=limiter,  # type: ignore[arg-type]
    )

    assert [c.chunk_index for c in result.chunks] == [0, 1, 2]


@pytest.mark.asyncio
async def test_compress_fallback_on_llm_error() -> None:
    """Если LLM падает, отдаём fallback с raw текстом."""
    client = MockLLMResponse(exception=LLMError("test error"))
    limiter = RateLimiter(max_per_minute=600)

    chunks = [_mock_chunk(0, 0.0, 60.0, text="important raw speech")]
    result = await compress_chunks(
        chunks, client=client, rate_limiter=limiter,  # type: ignore[arg-type]
    )

    assert len(result.chunks) == 1
    assert "compression failed" in result.chunks[0].summary
    assert "important raw speech" in result.chunks[0].summary
    assert result.chunks[0].key_speakers == []


@pytest.mark.asyncio
async def test_compress_fallback_on_invalid_json() -> None:
    client = MockLLMResponse(responses=["this is not json at all"])
    limiter = RateLimiter(max_per_minute=600)

    result = await compress_chunks(
        [_mock_chunk(0, 0.0, 60.0)],
        client=client,  # type: ignore[arg-type]
        rate_limiter=limiter,
    )
    assert "compression failed" in result.chunks[0].summary


@pytest.mark.asyncio
async def test_compress_progress_callback() -> None:
    responses_cycle = [
        json.dumps({"chunk_index": 0, "time_range_sec": [0, 60],
                    "summary": "s1", "key_speakers": []}),
        json.dumps({"chunk_index": 1, "time_range_sec": [60, 120],
                    "summary": "s2", "key_speakers": []}),
    ]
    client = MockLLMResponse(responses_cycle=responses_cycle)
    limiter = RateLimiter(max_per_minute=600)

    progress_calls: list[dict] = []

    async def record_progress(
        *, done: int, total: int, chunk_index: int
    ) -> None:
        progress_calls.append(
            {"done": done, "total": total, "chunk_index": chunk_index}
        )

    chunks = [_mock_chunk(i, i * 60.0, (i + 1) * 60.0) for i in range(2)]
    await compress_chunks(
        chunks,
        client=client,  # type: ignore[arg-type]
        rate_limiter=limiter,
        progress=record_progress,
    )

    assert len(progress_calls) == 2
    assert all(p["total"] == 2 for p in progress_calls)


@pytest.mark.asyncio
async def test_compression_to_synopsis() -> None:
    responses = [
        json.dumps({"chunk_index": 0, "time_range_sec": [0, 60],
                    "summary": "AAA", "key_speakers": ["speaker_0"]}),
        json.dumps({"chunk_index": 1, "time_range_sec": [60, 120],
                    "summary": "BBB", "key_speakers": ["speaker_0"]}),
    ]
    client = MockLLMResponse(responses=responses)
    limiter = RateLimiter(max_per_minute=600)

    chunks = [_mock_chunk(i, i * 60.0, (i + 1) * 60.0) for i in range(2)]
    result = await compress_chunks(
        chunks, client=client, rate_limiter=limiter,  # type: ignore[arg-type]
    )

    synopsis = result.to_synopsis()
    assert "AAA" in synopsis
    assert "BBB" in synopsis
    assert "Chunk 0" in synopsis
    assert "Chunk 1" in synopsis


@pytest.mark.asyncio
async def test_compress_rejects_invalid_peak_kind() -> None:
    """Kind='WEIRD_KIND' должен нормализоваться в 'surprise'."""
    response = json.dumps({
        "chunk_index": 0,
        "time_range_sec": [0, 60],
        "summary": "ok",
        "key_speakers": [],
        "emotional_peaks": [
            {"sec": 30.0, "kind": "WEIRD_KIND", "note": "x"}
        ],
    })
    client = MockLLMResponse(responses=[response])
    limiter = RateLimiter(max_per_minute=600)

    result = await compress_chunks(
        [_mock_chunk(0, 0.0, 60.0)],
        client=client,  # type: ignore[arg-type]
        rate_limiter=limiter,
    )
    assert result.chunks[0].emotional_peaks[0].kind == "surprise"
