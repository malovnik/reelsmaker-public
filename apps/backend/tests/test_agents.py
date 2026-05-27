"""Unit-тесты extraction-агентов и orchestrator (mock LLM, 0 real API)."""

from __future__ import annotations

import json

import pytest

from videomaker.models.canvas import CanvasTheme, ProjectCanvas
from videomaker.services.agents.base import (
    AGENT_REGISTRY,
    _parse_evidence_item,
    run_extraction_agent,
)
from videomaker.services.agents.orchestrator import orchestrate_extraction
from videomaker.services.chunker import TranscriptChunk
from videomaker.services.llm_client import LLMError, LLMResponse
from videomaker.services.rate_limiter import RateLimiter
from videomaker.services.transcribers.base import TranscribedSegment


class SequentialMockLLM:
    provider = "mock"
    model = "mock"

    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self._n = 0

    async def complete_json(
        self, *, system: str, user: str,
        temperature: float = 0.3, max_tokens: int = 8000,
    ) -> LLMResponse:
        text = self.responses[self._n % len(self.responses)]
        self._n += 1
        return LLMResponse(
            text=text,
            input_tokens=100,
            output_tokens=50,
            cache_read_tokens=None,
            cache_creation_tokens=None,
            provider=self.provider,
            model=self.model,
        )


class FailingMockLLM:
    provider = "mock"
    model = "mock"

    async def complete_json(
        self, *, system: str, user: str,
        temperature: float = 0.3, max_tokens: int = 8000,
    ) -> LLMResponse:
        raise LLMError("boom")


def _chunk(index: int = 0) -> TranscriptChunk:
    return TranscriptChunk(
        index=index,
        start_sec=index * 60.0,
        end_sec=(index + 1) * 60.0,
        text="[chunk]",
        segments=[TranscribedSegment(text="hi", start=0.0, end=1.0)],
        token_count=50,
    )


def _canvas() -> ProjectCanvas:
    return ProjectCanvas(
        central_theme="X",
        themes=[
            CanvasTheme(
                id="t1", label="тема", strength=0.9,
                first_mention_sec=0, last_mention_sec=100,
            ),
        ],
    )


# === AGENT_REGISTRY ===

def test_registry_has_six_agents() -> None:
    assert len(AGENT_REGISTRY) == 6
    expected = {
        "hook_hunter", "emotional_peak_finder", "humor_specialist",
        "dramatic_irony_scanner", "thesis_extractor", "motif_tracker",
    }
    assert set(AGENT_REGISTRY.keys()) == expected


def test_each_agent_has_unique_prompt_key() -> None:
    prompt_keys = [cfg.prompt_key for cfg in AGENT_REGISTRY.values()]
    assert len(set(prompt_keys)) == 6


# === _parse_evidence_item ===

def test_parse_evidence_valid() -> None:
    cfg = AGENT_REGISTRY["hook_hunter"]
    data = {
        "start": 10.5, "end": 25.0, "text": "цитата",
        "speaker": "speaker_0", "theme_id": "t1",
        "strength": 0.85, "reasoning": "potential paradox",
        "hook_type": "paradox",
    }
    item = _parse_evidence_item(data, cfg, chunk_index=2)
    assert item is not None
    assert item.source_agent == "hook_hunter"
    assert item.start == 10.5
    assert item.strength == 0.85
    assert item.extra == {"hook_type": "paradox"}
    assert item.chunk_index == 2


def test_parse_evidence_missing_text_none() -> None:
    cfg = AGENT_REGISTRY["hook_hunter"]
    assert _parse_evidence_item({"start": 0, "end": 1}, cfg, chunk_index=0) is None


def test_parse_evidence_zero_duration_none() -> None:
    cfg = AGENT_REGISTRY["hook_hunter"]
    data = {"start": 5, "end": 5, "text": "x"}
    assert _parse_evidence_item(data, cfg, chunk_index=0) is None


def test_parse_evidence_invalid_start_none() -> None:
    cfg = AGENT_REGISTRY["hook_hunter"]
    data = {"start": "bad", "end": 10, "text": "x"}
    assert _parse_evidence_item(data, cfg, chunk_index=0) is None


def test_parse_evidence_clamps_strength() -> None:
    cfg = AGENT_REGISTRY["hook_hunter"]
    data = {"start": 0, "end": 5, "text": "x", "strength": 5.0}
    item = _parse_evidence_item(data, cfg, chunk_index=0)
    assert item is not None and item.strength == 1.0


def test_parse_evidence_uses_intensity_for_emotional() -> None:
    cfg = AGENT_REGISTRY["emotional_peak_finder"]
    data = {
        "start": 0, "end": 5, "text": "x",
        "intensity": 0.75, "emotion": "confession",
    }
    item = _parse_evidence_item(data, cfg, chunk_index=0)
    assert item is not None
    assert item.strength == 0.75
    assert item.extra == {"emotion": "confession"}


def test_parse_evidence_uses_funniness_for_humor() -> None:
    cfg = AGENT_REGISTRY["humor_specialist"]
    data = {
        "start": 0, "end": 5, "text": "x",
        "funniness": 0.9, "humor_type": "twist_pointe",
    }
    item = _parse_evidence_item(data, cfg, chunk_index=0)
    assert item is not None and item.strength == 0.9


# === run_extraction_agent ===

@pytest.mark.asyncio
async def test_run_agent_returns_evidence() -> None:
    response = json.dumps([
        {
            "chunk_index": 0, "start": 5.0, "end": 15.0,
            "text": "Парадокс", "speaker": "speaker_0",
            "hook_type": "paradox", "strength": 0.8, "theme_id": "t1",
            "reasoning": "test",
        },
    ])
    llm = SequentialMockLLM([response])
    limiter = RateLimiter(max_per_minute=600)

    cfg = AGENT_REGISTRY["hook_hunter"]
    result = await run_extraction_agent(
        cfg, _chunk(0), _canvas(),
        client=llm, rate_limiter=limiter,  # type: ignore[arg-type]
    )
    assert result.failure_reason is None
    assert len(result.evidence) == 1
    assert result.evidence[0].source_agent == "hook_hunter"
    assert result.evidence[0].strength == 0.8


@pytest.mark.asyncio
async def test_run_agent_handles_llm_error() -> None:
    llm = FailingMockLLM()
    limiter = RateLimiter(max_per_minute=600)

    cfg = AGENT_REGISTRY["hook_hunter"]
    result = await run_extraction_agent(
        cfg, _chunk(0), _canvas(),
        client=llm, rate_limiter=limiter,  # type: ignore[arg-type]
    )
    assert result.failure_reason is not None
    assert "llm_error" in result.failure_reason
    assert result.evidence == []


@pytest.mark.asyncio
async def test_run_agent_handles_non_array_output() -> None:
    llm = SequentialMockLLM(['{"not":"array"}'])
    limiter = RateLimiter(max_per_minute=600)

    cfg = AGENT_REGISTRY["hook_hunter"]
    result = await run_extraction_agent(
        cfg, _chunk(0), _canvas(),
        client=llm, rate_limiter=limiter,  # type: ignore[arg-type]
    )
    assert result.failure_reason == "output_not_array"


@pytest.mark.asyncio
async def test_run_agent_empty_array_no_evidence() -> None:
    llm = SequentialMockLLM(["[]"])
    limiter = RateLimiter(max_per_minute=600)

    cfg = AGENT_REGISTRY["hook_hunter"]
    result = await run_extraction_agent(
        cfg, _chunk(0), _canvas(),
        client=llm, rate_limiter=limiter,  # type: ignore[arg-type]
    )
    assert result.failure_reason is None
    assert result.evidence == []


# === orchestrator ===

@pytest.mark.asyncio
async def test_orchestrator_runs_all_agents_on_all_chunks() -> None:
    response = json.dumps([
        {
            "chunk_index": 0, "start": 5.0, "end": 15.0, "text": "x",
            "strength": 0.7, "theme_id": "t1",
        },
    ])
    llm = SequentialMockLLM([response])
    limiter = RateLimiter(max_per_minute=600)

    chunks = [_chunk(0), _chunk(1)]
    result = await orchestrate_extraction(
        chunks, _canvas(),
        client=llm, rate_limiter=limiter,  # type: ignore[arg-type]
    )
    # 6 агентов × 2 chunks = 12 runs = 12 evidence items
    assert len(result.agent_results) == 12
    assert len(result.evidence) == 12
    assert result.failed_count == 0


@pytest.mark.asyncio
async def test_orchestrator_filters_enabled_agents() -> None:
    response = json.dumps([
        {"chunk_index": 0, "start": 5.0, "end": 15.0,
         "text": "x", "strength": 0.7},
    ])
    llm = SequentialMockLLM([response])
    limiter = RateLimiter(max_per_minute=600)

    result = await orchestrate_extraction(
        [_chunk(0)], _canvas(),
        enabled_agents=["hook_hunter", "humor_specialist"],
        client=llm, rate_limiter=limiter,  # type: ignore[arg-type]
    )
    assert len(result.agent_results) == 2
    assert {r.agent for r in result.agent_results} == {
        "hook_hunter", "humor_specialist"
    }


@pytest.mark.asyncio
async def test_orchestrator_empty_chunks_returns_empty() -> None:
    llm = SequentialMockLLM(["[]"])
    limiter = RateLimiter(max_per_minute=600)

    result = await orchestrate_extraction(
        [], _canvas(),
        client=llm, rate_limiter=limiter,  # type: ignore[arg-type]
    )
    assert result.evidence == []
    assert result.agent_results == []


@pytest.mark.asyncio
async def test_orchestrator_continues_on_failures() -> None:
    """Если LLM падает — остальные агенты работают, failed_count растёт."""
    llm = FailingMockLLM()
    limiter = RateLimiter(max_per_minute=600)

    result = await orchestrate_extraction(
        [_chunk(0)], _canvas(),
        client=llm, rate_limiter=limiter,  # type: ignore[arg-type]
    )
    assert len(result.agent_results) == 6
    assert result.failed_count == 6
    assert result.evidence == []


@pytest.mark.asyncio
async def test_orchestrator_progress_callback() -> None:
    response = json.dumps([])
    llm = SequentialMockLLM([response])
    limiter = RateLimiter(max_per_minute=600)

    calls: list[dict] = []

    async def progress(*, agent, chunk_index, done, total) -> None:
        calls.append(
            {"agent": agent, "chunk": chunk_index,
             "done": done, "total": total}
        )

    await orchestrate_extraction(
        [_chunk(0), _chunk(1)], _canvas(),
        enabled_agents=["hook_hunter"],
        client=llm, rate_limiter=limiter, progress=progress,  # type: ignore[arg-type]
    )
    assert len(calls) == 2
    assert all(c["total"] == 2 for c in calls)
