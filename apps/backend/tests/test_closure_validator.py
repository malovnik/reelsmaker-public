"""Unit-тесты post-trim semantic closure validator."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from videomaker.models.reel_plan import AnalysisResult, ReelPlan, ReelSegment
from videomaker.services.closure_validator import (
    ClosureResult,
    _apply_extension,
    _ends_with_sentence_terminator,
    _find_next_sentence_end,
    validate_closures,
)
from videomaker.services.llm_client import LLMResponse
from videomaker.services.rate_limiter import RateLimiter
from videomaker.services.transcribers.base import TranscribedWord

# ---------------------------------------------------------------------------
# _ends_with_sentence_terminator
# ---------------------------------------------------------------------------


def _word(text: str, start: float, end: float) -> TranscribedWord:
    return TranscribedWord(word=text, start=start, end=end, confidence=0.95)


def test_ends_with_terminator_true_period() -> None:
    words = [_word("Hello", 0, 0.5), _word("world.", 0.5, 1.0)]
    assert _ends_with_sentence_terminator(words)


def test_ends_with_terminator_false_mid_sentence() -> None:
    words = [_word("Hello", 0, 0.5), _word("world", 0.5, 1.0)]
    assert not _ends_with_sentence_terminator(words)


def test_ends_with_terminator_empty_returns_false() -> None:
    assert not _ends_with_sentence_terminator([])


def test_ends_with_terminator_question() -> None:
    words = [_word("Why?", 0, 0.5)]
    assert _ends_with_sentence_terminator(words)


def test_ends_with_terminator_ellipsis() -> None:
    words = [_word("и…", 0, 0.5)]
    assert _ends_with_sentence_terminator(words)


# ---------------------------------------------------------------------------
# _find_next_sentence_end
# ---------------------------------------------------------------------------


def test_find_next_sentence_end_finds_first_terminator() -> None:
    words = [
        _word("and", 1.0, 1.2),
        _word("then", 1.3, 1.5),
        _word("done.", 1.6, 2.0),
        _word("Next", 2.1, 2.3),
    ]
    # first terminator = done. at end=2.0
    assert _find_next_sentence_end(words) == 2.0


def test_find_next_sentence_end_no_terminator_returns_none() -> None:
    words = [_word("and", 1.0, 1.2), _word("then", 1.3, 1.5)]
    assert _find_next_sentence_end(words) is None


def test_find_next_sentence_end_empty() -> None:
    assert _find_next_sentence_end([]) is None


# ---------------------------------------------------------------------------
# _apply_extension (mutation)
# ---------------------------------------------------------------------------


def _make_reel(reel_id: str = "r1", end: float = 50.0) -> ReelPlan:
    return ReelPlan(
        reel_id=reel_id,
        hook="hook text",
        predicted_duration_sec=40.0,
        target_audience="",
        segments=[
            ReelSegment(
                source_start=10.0,
                source_end=end,
                reasoning="test",
                order_role="hook",
            ),
        ],
    )


def test_apply_extension_extends_last_segment_and_duration() -> None:
    reel = _make_reel(end=50.0)
    _apply_extension(reel, extend_by_sec=3.0, source_duration_sec=600.0)
    assert reel.segments[-1].source_end == pytest.approx(53.0)
    assert reel.predicted_duration_sec == pytest.approx(43.0)


def test_apply_extension_clamps_to_source_duration() -> None:
    reel = _make_reel(end=598.0)
    _apply_extension(reel, extend_by_sec=5.0, source_duration_sec=600.0)
    # Упёрлись в 600 — фактически расширили на 2, не на 5.
    assert reel.segments[-1].source_end == pytest.approx(600.0)
    assert reel.predicted_duration_sec == pytest.approx(42.0)


def test_apply_extension_no_op_zero_extension() -> None:
    reel = _make_reel(end=50.0)
    _apply_extension(reel, extend_by_sec=0.0, source_duration_sec=600.0)
    assert reel.segments[-1].source_end == 50.0


# ---------------------------------------------------------------------------
# validate_closures (integration с моком LLM)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _MockLLM:
    """Мок LLMClient, возвращает фиксированный JSON."""

    response_text: str
    provider: str = "gemini"
    model: str = "test"

    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.3,
        max_tokens: int = 8000,
    ) -> LLMResponse:
        return LLMResponse(
            text=self.response_text,
            input_tokens=100,
            output_tokens=20,
            cache_read_tokens=None,
            cache_creation_tokens=None,
            provider=self.provider,
            model=self.model,
        )


def _analysis_with_one_reel(end: float = 50.0) -> AnalysisResult:
    return AnalysisResult(
        reels=[_make_reel("r1", end=end)],
        llm_model="gemini-3.1-flash-lite-preview",
        provider="gemini",
        stats={},
    )


@pytest.mark.asyncio
async def test_validate_closures_asr_terminator_skips_llm() -> None:
    """ASR-токен оканчивается точкой → LLM не вызывается, is_complete=true."""
    words = [
        _word("Всё", 48.0, 48.3),
        _word("понятно.", 48.4, 49.5),
    ]
    llm = _MockLLM(response_text='{"is_complete": false, "confidence": 0.9}')
    limiter = RateLimiter(max_per_minute=60)
    fake_prompt = "Test closure check prompt"
    result = await validate_closures(
        _analysis_with_one_reel(end=50.0),
        words,
        source_duration_sec=600.0,
        client=llm,  # type: ignore[arg-type]
        rate_limiter=limiter,
        system_prompt=fake_prompt,
    )
    assert result.stats["closure_complete_count"] == 1
    assert result.stats["closure_extended_count"] == 0
    # LLM НЕ вызывался → reel end не изменился.
    assert result.reels[0].segments[-1].source_end == 50.0


@pytest.mark.asyncio
async def test_validate_closures_llm_says_incomplete_extends_to_boundary() -> None:
    """LLM решает что обрыв → ищем sentence boundary впереди."""
    words = [
        _word("а", 48.0, 48.3),
        _word("потом", 48.4, 49.0),
        _word("я", 49.1, 49.3),
        _word("понял", 49.4, 50.0),
        # Forward words (после end=50):
        _word("что", 50.5, 50.8),
        _word("это", 51.0, 51.3),
        _word("работает.", 51.4, 52.0),
    ]
    llm = _MockLLM(
        response_text='{"is_complete": false, "confidence": 0.9, "reasoning": "dangling conjunction"}'
    )
    limiter = RateLimiter(max_per_minute=60)
    fake_prompt = "Test closure check prompt"
    result = await validate_closures(
        _analysis_with_one_reel(end=50.0),
        words,
        source_duration_sec=600.0,
        client=llm,  # type: ignore[arg-type]
        rate_limiter=limiter,
        system_prompt=fake_prompt,
    )
    # Найден terminator "работает." end=52.0 → extend_by=2.0.
    assert result.stats["closure_extended_count"] == 1
    assert result.reels[0].segments[-1].source_end == pytest.approx(52.0)


@pytest.mark.asyncio
async def test_validate_closures_no_boundary_available_failed_counter() -> None:
    """LLM говорит обрыв, но впереди нет sentence boundary → counter failed."""
    words = [
        _word("а", 48.0, 48.3),
        _word("потом", 48.4, 49.0),
        _word("я", 49.1, 49.3),
        _word("понял", 49.4, 50.0),
        # Forward words без sentence end (только лишние токены без точки):
        _word("что", 50.5, 50.8),
        _word("это", 51.0, 51.3),
    ]
    llm = _MockLLM(
        response_text='{"is_complete": false, "confidence": 0.85, "reasoning": "dangling"}'
    )
    limiter = RateLimiter(max_per_minute=60)
    fake_prompt = "Test closure check prompt"
    result = await validate_closures(
        _analysis_with_one_reel(end=50.0),
        words,
        source_duration_sec=600.0,
        client=llm,  # type: ignore[arg-type]
        rate_limiter=limiter,
        system_prompt=fake_prompt,
    )
    assert result.stats["closure_failed_count"] == 1
    assert result.stats["closure_extended_count"] == 0
    assert result.reels[0].segments[-1].source_end == 50.0


@pytest.mark.asyncio
async def test_validate_closures_low_confidence_pass_through() -> None:
    """LLM is_complete=false но confidence<_MIN → trust-pass, не трогаем."""
    words = [
        _word("мысль", 48.0, 48.5),
        _word("продолжается", 48.6, 50.0),
    ]
    llm = _MockLLM(
        response_text='{"is_complete": false, "confidence": 0.4, "reasoning": "uncertain"}'
    )
    limiter = RateLimiter(max_per_minute=60)
    fake_prompt = "Test closure check prompt"
    result = await validate_closures(
        _analysis_with_one_reel(end=50.0),
        words,
        source_duration_sec=600.0,
        client=llm,  # type: ignore[arg-type]
        rate_limiter=limiter,
        system_prompt=fake_prompt,
    )
    assert result.stats["closure_complete_count"] == 1
    assert result.stats["closure_failed_count"] == 0


@pytest.mark.asyncio
async def test_validate_closures_empty_reels_noop() -> None:
    analysis = AnalysisResult(reels=[], llm_model="x", provider="gemini", stats={})
    result = await validate_closures(
        analysis,
        [],
        source_duration_sec=100.0,
    )
    assert result.stats["closure_checked_count"] == 0


@pytest.mark.asyncio
async def test_validate_closures_parallel_processes_multiple() -> None:
    """Несколько рилсов обрабатываются параллельно через asyncio.gather."""
    words = [
        _word("всё.", 0, 1),  # terminator для r1-r3
    ]
    analysis = AnalysisResult(
        reels=[
            _make_reel("r1", end=2.0),
            _make_reel("r2", end=2.0),
            _make_reel("r3", end=2.0),
        ],
        llm_model="x",
        provider="gemini",
        stats={},
    )
    llm = _MockLLM(response_text='{"is_complete": true}')
    limiter = RateLimiter(max_per_minute=60)
    fake_prompt = "Test closure check prompt"
    result = await validate_closures(
        analysis,
        words,
        source_duration_sec=100.0,
        client=llm,  # type: ignore[arg-type]
        rate_limiter=limiter,
        system_prompt=fake_prompt,
    )
    assert result.stats["closure_checked_count"] == 3
    assert result.stats["closure_complete_count"] == 3


# ---------------------------------------------------------------------------
# ClosureResult dataclass (sanity)
# ---------------------------------------------------------------------------


def test_closure_result_is_frozen() -> None:
    r = ClosureResult(reel_id="r1", is_complete=True, extended_by_sec=0.0, reasoning="ok")
    with pytest.raises(AttributeError):
        r.is_complete = False  # type: ignore[misc]
