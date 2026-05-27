"""Unit-тесты variants_generator.py с mock LLM."""

from __future__ import annotations

import json

import pytest

from videomaker.models.canvas import ProjectCanvas
from videomaker.models.evidence import RankedEvidence, RankedEvidenceItem
from videomaker.models.story_script import StoryScript, StorySegment
from videomaker.services.llm_client import LLMResponse
from videomaker.services.rate_limiter import RateLimiter
from videomaker.services.variants_generator import generate_variants


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
                start=100, end=130, text="Развитие",
                category="development_material", composite_score=0.7,
            ),
            RankedEvidenceItem(
                id="r3", source_agent="motif_tracker",
                start=900, end=920, text="Финал",
                category="payoff_candidate", composite_score=0.85,
            ),
        ],
    )


def _base_script() -> StoryScript:
    return StoryScript(
        central_theme="T",
        arc=[
            StorySegment(
                role="hook", evidence_id="r1",
                source_start_sec=10, source_end_sec=20,
            ),
        ],
    )


@pytest.mark.asyncio
async def test_variants_parses_two_formats() -> None:
    llm_response = json.dumps({
        "variants": [
            {"id": "variant_long_philosophical", "kind": "long_philosophical",
             "label": "Длинное", "target_duration_sec": 900,
             "predicted_duration_sec": 890,
             "central_theme": "T",
             "arc": [
                 {"role": "hook", "evidence_id": "r1",
                  "source_start_sec": 10, "source_end_sec": 20},
             ]},
            {"id": "variant_punchy_summary", "kind": "punchy_summary",
             "label": "Короткий",
             "target_duration_sec": 60, "predicted_duration_sec": 55,
             "central_theme": "T",
             "arc": [
                 {"role": "hook", "evidence_id": "r1",
                  "source_start_sec": 10, "source_end_sec": 20},
             ]},
        ],
    })

    variants = await generate_variants(
        ProjectCanvas(central_theme="T"),
        _ranked_sample(),
        _base_script(),
        client=MockLLM(llm_response),  # type: ignore[arg-type]
        rate_limiter=RateLimiter(max_per_minute=600),
    )
    assert len(variants.variants) == 2
    assert variants.by_kind("long_philosophical") is not None
    assert variants.by_kind("punchy_summary") is not None
    assert variants.by_kind("deep_dive") is None


@pytest.mark.asyncio
async def test_variants_skips_invalid_kinds() -> None:
    llm_response = json.dumps({
        "variants": [
            {"kind": "UNKNOWN_KIND", "label": "x",
             "target_duration_sec": 60, "predicted_duration_sec": 55,
             "arc": [{"role": "hook", "evidence_id": "r1",
                      "source_start_sec": 10, "source_end_sec": 20}]},
        ],
    })
    variants = await generate_variants(
        ProjectCanvas(),
        _ranked_sample(),
        _base_script(),
        client=MockLLM(llm_response),  # type: ignore[arg-type]
        rate_limiter=RateLimiter(max_per_minute=600),
    )
    assert variants.variants == []


@pytest.mark.asyncio
async def test_variants_fallback_on_llm_failure() -> None:
    """Битый JSON → fallback с одним long_philosophical копией base arc."""
    variants = await generate_variants(
        ProjectCanvas(),
        _ranked_sample(),
        _base_script(),
        client=MockLLM("not json at all"),  # type: ignore[arg-type]
        rate_limiter=RateLimiter(max_per_minute=600),
    )
    assert len(variants.variants) == 1
    assert variants.variants[0].kind == "long_philosophical"
    assert "fallback" in variants.variants[0].label.lower()


@pytest.mark.asyncio
async def test_variants_empty_ranked_returns_empty() -> None:
    variants = await generate_variants(
        ProjectCanvas(),
        RankedEvidence(),
        _base_script(),
        client=MockLLM("{}"),  # type: ignore[arg-type]
        rate_limiter=RateLimiter(max_per_minute=600),
    )
    assert variants.variants == []


@pytest.mark.asyncio
async def test_variants_normalises_id_prefix() -> None:
    """Если LLM прислал id='variant_package_of_shorts' без kind — парсим из id."""
    llm_response = json.dumps({
        "variants": [
            {"id": "variant_package_of_shorts",
             "label": "Пакет",
             "target_duration_sec": 120, "predicted_duration_sec": 110,
             "central_theme": "T",
             "arc": [{"role": "hook", "evidence_id": "r1",
                      "source_start_sec": 10, "source_end_sec": 20}]},
        ],
    })
    variants = await generate_variants(
        ProjectCanvas(),
        _ranked_sample(),
        _base_script(),
        client=MockLLM(llm_response),  # type: ignore[arg-type]
        rate_limiter=RateLimiter(max_per_minute=600),
    )
    assert len(variants.variants) == 1
    assert variants.variants[0].kind == "package_of_shorts"
