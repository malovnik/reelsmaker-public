"""Unit-тесты Stage 5.4-5.6: reducer, story_doctor, rhythm_check.

Variants generator тестируется отдельно (см. STEP 6).
"""

from __future__ import annotations

import json

import pytest

from videomaker.models.canvas import ProjectCanvas
from videomaker.models.evidence import (
    EvidenceItem,
    RankedEvidence,
    RankedEvidenceItem,
)
from videomaker.models.story_script import StoryScript, StorySegment
from videomaker.services.agents.orchestrator import ExtractionResult
from videomaker.services.llm_client import LLMResponse
from videomaker.services.rate_limiter import RateLimiter
from videomaker.services.reducer import (
    _dedup_hybrid,
    _text_similarity_rough,
    reduce_and_rank,
)
from videomaker.services.rhythm_check import (
    _heuristic_rhythm_report,
    check_rhythm,
)
from videomaker.services.story_doctor import compose_story_script


class MockLLM:
    provider = "mock"
    model = "mock"

    def __init__(self, text: str) -> None:
        self.text = text

    async def complete_json(
        self, *, system: str, user: str,
        temperature: float = 0.3, max_tokens: int = 8000,
    ) -> LLMResponse:
        return LLMResponse(
            text=self.text,
            input_tokens=100,
            output_tokens=50,
            cache_read_tokens=None,
            cache_creation_tokens=None,
            provider="mock",
            model="mock",
        )


def _evidence(
    start: float, end: float, text: str,
    strength: float = 0.7, agent: str = "hook_hunter",
) -> EvidenceItem:
    return EvidenceItem(
        source_agent=agent,  # type: ignore[arg-type]
        chunk_index=0,
        start=start, end=end,
        text=text, strength=strength,
    )


# === REDUCER: dedup ===

def test_text_similarity_overlapping() -> None:
    assert _text_similarity_rough("hello world", "hello world") == 1.0


def test_text_similarity_no_overlap() -> None:
    assert _text_similarity_rough("aaa bbb", "ccc ddd") == 0.0


def test_text_similarity_partial() -> None:
    # {abc, def} ∪ {abc, ghi} = {abc, def, ghi} = 3; ∩ = {abc} = 1 → 1/3
    assert _text_similarity_rough("abc def", "abc ghi") == pytest.approx(1 / 3)


def test_dedup_removes_near_duplicates() -> None:
    items = [
        _evidence(10.0, 20.0, "это важная мысль", strength=0.6),
        _evidence(11.0, 21.0, "это важная мысль повтор", strength=0.8),
        _evidence(50.0, 60.0, "совсем другая тема"),
    ]
    result = _dedup_hybrid(items)
    assert len(result) == 2
    assert any(e.strength == 0.8 for e in result)


def test_dedup_keeps_distant_items() -> None:
    items = [
        _evidence(10.0, 20.0, "одна тема"),
        _evidence(30.0, 40.0, "одна тема повтор"),
    ]
    result = _dedup_hybrid(items)
    assert len(result) == 2


# === REDUCER: full pipeline ===

@pytest.mark.asyncio
async def test_reduce_with_mock_llm() -> None:
    extraction = ExtractionResult(evidence=[
        _evidence(10.0, 15.0, "пример тезиса"),
        _evidence(100.0, 105.0, "ещё цитата"),
    ])

    llm_response = json.dumps({
        "deduped_count": 2,
        "merged_scene_count": 0,
        "ranked_evidence": [
            {"id": "r1", "source_agent": "hook_hunter",
             "start": 10.0, "end": 15.0, "text": "пример тезиса",
             "category": "hook_candidate", "composite_score": 0.85,
             "reasoning": "test"},
            {"id": "r2", "source_agent": "hook_hunter",
             "start": 100.0, "end": 105.0, "text": "ещё цитата",
             "category": "development_material", "composite_score": 0.6},
        ],
    })
    limiter = RateLimiter(max_per_minute=600)

    result = await reduce_and_rank(
        extraction, ProjectCanvas(),
        client=MockLLM(llm_response),  # type: ignore[arg-type]
        rate_limiter=limiter,
    )
    assert result.ranked.deduped_count == 2
    assert len(result.ranked.items) == 2
    assert (
        result.ranked.items[0].composite_score
        >= result.ranked.items[1].composite_score
    )


@pytest.mark.asyncio
async def test_reduce_empty_extraction() -> None:
    result = await reduce_and_rank(
        ExtractionResult(), ProjectCanvas(),
        client=MockLLM("[]"),  # type: ignore[arg-type]
        rate_limiter=RateLimiter(max_per_minute=600),
    )
    assert result.ranked.items == []


@pytest.mark.asyncio
async def test_reduce_backfills_when_llm_returns_too_few() -> None:
    """LLM вернул 1 item на 50 deduped — backfill дополняет до разумного N.

    Репродукция реального инцидента: 263 deduped → LLM обрезал output → 1 item
    → 1 рилс на 33-минутном видео. Backfill должен добавить из deduped pool.
    """
    # 50 уникальных evidence (разные start'ы, разная strength)
    extraction = ExtractionResult(evidence=[
        _evidence(float(i * 30), float(i * 30 + 10),
                  f"уникальное событие номер {i}", strength=0.9 - i * 0.01)
        for i in range(50)
    ])

    # LLM возвращает только 1 ranked item — симулируем обрезание
    llm_response = json.dumps({
        "deduped_count": 50,
        "merged_scene_count": 0,
        "ranked_evidence": [
            {"id": "r1", "source_agent": "hook_hunter",
             "start": 0.0, "end": 10.0, "text": "уникальное событие номер 0",
             "category": "hook_candidate", "composite_score": 0.95},
        ],
    })
    result = await reduce_and_rank(
        extraction, ProjectCanvas(),
        client=MockLLM(llm_response),  # type: ignore[arg-type]
        rate_limiter=RateLimiter(max_per_minute=600),
    )
    # Backfill должен был дополнить до MIN_RANKED_ITEMS_FROM_LLM (20) и выше.
    assert len(result.ranked.items) >= 20, (
        f"backfill failed: LLM returned 1, got {len(result.ranked.items)}"
    )
    # Включён и исходный LLM-item, и backfill-items.
    assert result.ranked.items[0].composite_score == 0.95


@pytest.mark.asyncio
async def test_reduce_fallback_on_llm_failure() -> None:
    """Если LLM вернул битый JSON — fallback ranking по agent-категориям."""
    extraction = ExtractionResult(evidence=[
        _evidence(10.0, 15.0, "x", strength=0.9, agent="hook_hunter"),
        _evidence(100.0, 105.0, "y", strength=0.5, agent="thesis_extractor"),
    ])
    result = await reduce_and_rank(
        extraction, ProjectCanvas(),
        client=MockLLM("broken not-json"),  # type: ignore[arg-type]
        rate_limiter=RateLimiter(max_per_minute=600),
    )
    assert len(result.ranked.items) == 2
    assert any(i.category == "hook_candidate" for i in result.ranked.items)


# === STORY DOCTOR ===

def _ranked_sample() -> RankedEvidence:
    return RankedEvidence(
        deduped_count=3,
        items=[
            RankedEvidenceItem(
                id="r1", source_agent="hook_hunter",
                start=10, end=20, text="Парадокс",
                category="hook_candidate", composite_score=0.9,
            ),
            RankedEvidenceItem(
                id="r2", source_agent="thesis_extractor",
                start=100, end=130, text="Развитие темы",
                category="development_material", composite_score=0.7,
            ),
            RankedEvidenceItem(
                id="r3", source_agent="motif_tracker",
                start=900, end=920, text="Финал",
                category="payoff_candidate", composite_score=0.85,
                motif_id="m1",
            ),
        ],
    )


@pytest.mark.asyncio
async def test_story_doctor_parses_full_arc() -> None:
    llm_response = json.dumps({
        "central_theme": "Тема",
        "bookend_motif_id": "m1",
        "bookend_reasoning": "замыкание",
        "arc": [
            {"role": "hook", "evidence_id": "r1",
             "source_start_sec": 10.0, "source_end_sec": 20.0,
             "speaker": "speaker_0"},
            {"role": "development", "evidence_id": "r2",
             "source_start_sec": 100.0, "source_end_sec": 130.0,
             "emotional_beat": "strain"},
            {"role": "payoff", "evidence_id": "r3",
             "source_start_sec": 900.0, "source_end_sec": 920.0,
             "emotional_beat": "triumph"},
        ],
        "predicted_duration_sec": 60.0,
        "alternates": [
            {"role_substitute": "setup", "evidence_id": "r2",
             "reason": "backup"},
        ],
    })

    script = await compose_story_script(
        ProjectCanvas(central_theme="Тема"), _ranked_sample(),
        client=MockLLM(llm_response),  # type: ignore[arg-type]
        rate_limiter=RateLimiter(max_per_minute=600),
    )
    assert script.central_theme == "Тема"
    assert script.bookend_motif_id == "m1"
    assert len(script.arc) == 3
    assert script.arc[0].role == "hook"
    assert script.arc[1].emotional_beat == "strain"
    assert len(script.alternates) == 1


@pytest.mark.asyncio
async def test_story_doctor_skips_invalid_role() -> None:
    llm_response = json.dumps({
        "central_theme": "X",
        "arc": [
            {"role": "not_a_valid_role", "evidence_id": "r1",
             "source_start_sec": 10.0, "source_end_sec": 20.0},
            {"role": "hook", "evidence_id": "r1",
             "source_start_sec": 10.0, "source_end_sec": 20.0},
        ],
    })
    script = await compose_story_script(
        ProjectCanvas(), _ranked_sample(),
        client=MockLLM(llm_response),  # type: ignore[arg-type]
        rate_limiter=RateLimiter(max_per_minute=600),
    )
    assert len(script.arc) == 1
    assert script.arc[0].role == "hook"


@pytest.mark.asyncio
async def test_story_doctor_fallback_on_llm_fail() -> None:
    script = await compose_story_script(
        ProjectCanvas(central_theme="X"), _ranked_sample(),
        client=MockLLM("garbage"),  # type: ignore[arg-type]
        rate_limiter=RateLimiter(max_per_minute=600),
    )
    assert script.central_theme == "X"
    assert len(script.arc) >= 1


@pytest.mark.asyncio
async def test_story_doctor_empty_ranked_returns_stub() -> None:
    script = await compose_story_script(
        ProjectCanvas(central_theme="Y"), RankedEvidence(),
        client=MockLLM("{}"),  # type: ignore[arg-type]
        rate_limiter=RateLimiter(max_per_minute=600),
    )
    assert script.central_theme == "Y"
    assert script.arc == []


# === RHYTHM CHECK ===

def _sample_script_long_mono() -> StoryScript:
    """5 подряд segments по 45s одного speaker'а — trigger для heuristic."""
    return StoryScript(
        central_theme="x",
        arc=[
            StorySegment(
                role="hook", evidence_id=f"e{i}",
                source_start_sec=i * 100, source_end_sec=i * 100 + 45,
                speaker="speaker_0", emotional_beat="strain",
            )
            for i in range(5)
        ],
    )


def test_heuristic_detects_consecutive_long_monospeaker() -> None:
    report = _heuristic_rhythm_report(_sample_script_long_mono())
    assert report.middle_sag_detected is True
    assert len(report.issues) >= 1
    assert report.issues[0].recommendation_action == "insert_cutaway"


def test_heuristic_no_sag_short_segments() -> None:
    script = StoryScript(
        central_theme="x",
        arc=[
            StorySegment(
                role="hook", evidence_id="e1",
                source_start_sec=0, source_end_sec=15,
                speaker="speaker_0",
            ),
            StorySegment(
                role="setup", evidence_id="e2",
                source_start_sec=15, source_end_sec=35,
                speaker="speaker_0",
            ),
        ],
    )
    report = _heuristic_rhythm_report(script)
    assert report.middle_sag_detected is False


@pytest.mark.asyncio
async def test_rhythm_check_llm_response() -> None:
    llm_response = json.dumps({
        "middle_sag_detected": True,
        "overall_rhythm_score": 0.6,
        "pacing_summary": "монотонный",
        "issues": [
            {"region": "2-4", "severity": "high", "reason": "mono",
             "recommendation": {
                 "action": "insert_cutaway",
                 "target_position_in_arc": 3,
                 "alternate_evidence_id": "e10",
             }},
        ],
    })
    report = await check_rhythm(
        _sample_script_long_mono(),
        client=MockLLM(llm_response),  # type: ignore[arg-type]
        rate_limiter=RateLimiter(max_per_minute=600),
    )
    assert report.middle_sag_detected is True
    assert report.overall_rhythm_score == 0.6
    assert report.pacing_summary == "монотонный"
    assert len(report.issues) == 1
    assert report.issues[0].recommendation_action == "insert_cutaway"


@pytest.mark.asyncio
async def test_rhythm_check_empty_arc() -> None:
    report = await check_rhythm(
        StoryScript(central_theme="x"),
        client=MockLLM("{}"),  # type: ignore[arg-type]
        rate_limiter=RateLimiter(max_per_minute=600),
    )
    assert report.overall_rhythm_score == 1.0
