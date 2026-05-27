"""Unit-тесты canvas_builder.py с мок-LLM."""

from __future__ import annotations

import json

import pytest

from videomaker.models.canvas import CompressedChunk
from videomaker.services.canvas_builder import build_canvas
from videomaker.services.compression import CompressionResult
from videomaker.services.llm_client import LLMError, LLMResponse
from videomaker.services.rate_limiter import RateLimiter


class MockLLM:
    provider = "mock"
    model = "gemini-2.5-pro"

    def __init__(self, text: str) -> None:
        self.text = text

    async def complete_json(
        self, *, system: str, user: str,
        temperature: float = 0.3, max_tokens: int = 8000,
    ) -> LLMResponse:
        return LLMResponse(
            text=self.text,
            input_tokens=1000,
            output_tokens=500,
            cache_read_tokens=None,
            cache_creation_tokens=None,
            provider=self.provider,
            model=self.model,
        )


def _sample_compression() -> CompressionResult:
    return CompressionResult(
        chunks=[
            CompressedChunk(
                chunk_index=0,
                time_range_sec=(0.0, 600.0),
                summary="Герой рассказывает о детстве и потере отца",
                key_speakers=["speaker_0"],
            ),
            CompressedChunk(
                chunk_index=1,
                time_range_sec=(600.0, 1200.0),
                summary="Речь о восстановлении и новом начале",
                key_speakers=["speaker_0", "speaker_1"],
            ),
        ]
    )


VALID_CANVAS_RESPONSE = json.dumps({
    "central_theme": "Трансформация через потерю",
    "themes": [
        {"id": "t1", "label": "потеря", "description": "тема потери",
         "strength": 0.9, "first_mention_sec": 10, "last_mention_sec": 900},
        {"id": "t2", "label": "возрождение",
         "strength": 0.8, "first_mention_sec": 600, "last_mention_sec": 1180},
    ],
    "motifs": [
        {"id": "m1", "label": "старый дом",
         "occurrences_sec": [45, 800, 1100],
         "significance": "символ прошлого"},
    ],
    "speakers": [
        {"id": "speaker_0", "role": "ведущий", "importance": 0.9,
         "key_quote_start_sec": 34.5},
        {"id": "speaker_1", "role": "гость", "importance": 0.7},
    ],
    "candidate_moments": [
        {"id": "mo1", "speaker": "speaker_0", "start": 45.0, "end": 72.0,
         "one_liner": "я не искал любви", "kind": "hook", "strength": 0.88},
    ],
    "tone_map": [
        {"sec_range": [0, 600], "mood": "nostalgic", "intensity": 0.7},
        {"sec_range": [600, 1200], "mood": "triumphant", "intensity": 0.85},
    ],
    "chronological_spine": [
        "0-300s: детство", "300-600s: потеря", "600-900s: восстановление",
    ],
})


@pytest.mark.asyncio
async def test_build_canvas_happy_path() -> None:
    client = MockLLM(VALID_CANVAS_RESPONSE)
    limiter = RateLimiter(max_per_minute=600)

    canvas = await build_canvas(
        _sample_compression(),
        source_duration_sec=1200.0,
        transcriber_name="deepgram",
        speakers_count=2,
        client=client,  # type: ignore[arg-type]
        rate_limiter=limiter,
    )

    assert canvas.central_theme == "Трансформация через потерю"
    assert len(canvas.themes) == 2
    assert canvas.themes[0].id == "t1"
    assert canvas.themes[0].strength == 0.9
    assert len(canvas.motifs) == 1
    assert canvas.motifs[0].occurrences_sec == [45.0, 800.0, 1100.0]
    assert len(canvas.speakers) == 2
    assert canvas.speakers[0].key_quote_start_sec == 34.5
    assert len(canvas.candidate_moments) == 1
    assert canvas.candidate_moments[0].kind == "hook"
    assert len(canvas.tone_map) == 2
    assert canvas.tone_map[0].mood == "nostalgic"
    assert len(canvas.chronological_spine) == 3


@pytest.mark.asyncio
async def test_build_canvas_empty_compression_raises() -> None:
    client = MockLLM(VALID_CANVAS_RESPONSE)
    limiter = RateLimiter(max_per_minute=600)

    with pytest.raises(ValueError, match="empty compression"):
        await build_canvas(
            CompressionResult(chunks=[]),
            source_duration_sec=100.0,
            transcriber_name="deepgram",
            client=client,  # type: ignore[arg-type]
            rate_limiter=limiter,
        )


@pytest.mark.asyncio
async def test_build_canvas_invalid_json_raises() -> None:
    client = MockLLM("this is not json")
    limiter = RateLimiter(max_per_minute=600)

    with pytest.raises(LLMError):
        await build_canvas(
            _sample_compression(),
            source_duration_sec=1200.0,
            transcriber_name="deepgram",
            client=client,  # type: ignore[arg-type]
            rate_limiter=limiter,
        )


@pytest.mark.asyncio
async def test_build_canvas_clamps_invalid_strength() -> None:
    """Если LLM вернул strength=1.5 или -0.3 — клэмпим в [0, 1]."""
    bad_response = json.dumps({
        "central_theme": "x",
        "themes": [
            {"id": "t1", "label": "a", "strength": 1.5,
             "first_mention_sec": 0, "last_mention_sec": 10},
            {"id": "t2", "label": "b", "strength": -0.3,
             "first_mention_sec": 0, "last_mention_sec": 5},
        ],
    })
    client = MockLLM(bad_response)
    limiter = RateLimiter(max_per_minute=600)

    canvas = await build_canvas(
        _sample_compression(),
        source_duration_sec=100.0,
        transcriber_name="mlx",
        client=client,  # type: ignore[arg-type]
        rate_limiter=limiter,
    )
    assert canvas.themes[0].strength == 1.0
    assert canvas.themes[1].strength == 0.0


@pytest.mark.asyncio
async def test_build_canvas_normalizes_unknown_mood() -> None:
    bad_response = json.dumps({
        "central_theme": "x",
        "tone_map": [
            {"sec_range": [0, 100], "mood": "WEIRD_MOOD", "intensity": 0.5},
        ],
    })
    client = MockLLM(bad_response)
    limiter = RateLimiter(max_per_minute=600)

    canvas = await build_canvas(
        _sample_compression(),
        source_duration_sec=100.0,
        transcriber_name="mlx",
        client=client,  # type: ignore[arg-type]
        rate_limiter=limiter,
    )
    assert canvas.tone_map[0].mood == "setup"


@pytest.mark.asyncio
async def test_build_canvas_minimal_response() -> None:
    """LLM дал sparse output → синтезируем canvas из compression chunks.

    Quality gate активируется когда themes < 2 / moments < 5 / tone_map < 2.
    Fallback достраивает scaffold из ``CompressionResult`` чтобы downstream
    stages не деградировали до single-segment рилсов.
    """
    client = MockLLM(json.dumps({"central_theme": "minimal"}))
    limiter = RateLimiter(max_per_minute=600)

    canvas = await build_canvas(
        _sample_compression(),
        source_duration_sec=60.0,
        transcriber_name="mlx",
        client=client,  # type: ignore[arg-type]
        rate_limiter=limiter,
    )
    # central_theme сохранён из LLM
    assert canvas.central_theme == "minimal"
    # fallback должен был добавить themes/tone_map из compression chunks
    assert len(canvas.themes) >= 1, "sparse canvas must be enriched from chunks"
    assert len(canvas.tone_map) >= 1, "tone_map must be synthesized from chunk time ranges"
