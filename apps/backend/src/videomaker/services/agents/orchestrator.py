"""Stage 5.3 Orchestrator — запускает 6 агентов × N chunks параллельно.

Каждый chunk получает 6 асинхронных extraction-вызовов. Orchestrator собирает
плоский `ExtractionResult` со всеми EvidenceItem'ами. Rate-limiter +
semaphore по `llm_max_concurrency` ограничивают параллелизм.

Настройки:
- `enabled_agents` — subset активных агентов (по умолчанию все 6).
- `concurrency` — total параллельных LLM-вызовов (override Settings).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Protocol

from videomaker.core.config import get_settings
from videomaker.core.logging import get_logger
from videomaker.models.canvas import ProjectCanvas
from videomaker.models.evidence import AgentName, EvidenceItem
from videomaker.services.agents.base import (
    AGENT_REGISTRY,
    AgentConfig,
    AgentResult,
    run_extraction_agent,
)
from videomaker.services.chunker import TranscriptChunk
from videomaker.services.extraction_coverage import build_coverage_summary
from videomaker.services.llm_client import (
    GeminiClient,
    LLMClient,
    build_llm_for_tier,
)
from videomaker.services.prompts import (
    DEFAULT_PROMPTS,
    build_system_prompt,
)
from videomaker.services.rate_limiter import RateLimiter, get_gemini_rate_limiter

log = get_logger(__name__)


class AgentProgress(Protocol):
    async def __call__(
        self, *, agent: AgentName, chunk_index: int, done: int, total: int,
    ) -> None: ...


@dataclass(slots=True)
class ExtractionResult:
    evidence: list[EvidenceItem] = field(default_factory=list)
    agent_results: list[AgentResult] = field(default_factory=list)
    failed_count: int = 0

    @property
    def total_input_tokens(self) -> int:
        return sum(r.input_tokens for r in self.agent_results)

    @property
    def total_output_tokens(self) -> int:
        return sum(r.output_tokens for r in self.agent_results)


async def orchestrate_extraction(
    chunks: list[TranscriptChunk],
    canvas: ProjectCanvas,
    *,
    enabled_agents: list[AgentName] | None = None,
    client: LLMClient | None = None,
    rate_limiter: RateLimiter | None = None,
    concurrency: int | None = None,
    progress: AgentProgress | None = None,
    wave_execution: bool = True,
    preference_anchors: str | None = None,
    pipeline_provider: str | None = None,
) -> ExtractionResult:
    """Запускает агентов × N chunks с опциональной wave-execution.

    При ``wave_execution=True`` (default, T1.2): агенты разделяются по
    ``AgentConfig.wave`` (1 = reaction-extractors, 2 = meaning-extractors).
    Внутри волны параллельный запуск всех (agent × chunk). Между волнами —
    барьер: волна 2 стартует только после завершения волны 1. Это фундамент
    под coverage_summary reducer (следующий slice), который положит между
    волнами агрегацию находок и передаст её волне 2 как контекст.

    При ``wave_execution=False`` — legacy classic: все агенты параллельно
    одной волной (совместимость, A/B для измерения эффекта).
    """
    if not chunks:
        return ExtractionResult()

    cfg = get_settings()
    llm = client or build_llm_for_tier("flash_lite", cfg, provider_override=pipeline_provider)
    limiter = rate_limiter or get_gemini_rate_limiter()
    sem = asyncio.Semaphore(concurrency or cfg.llm_max_concurrency)

    active_agents: list[AgentName] = enabled_agents or list(AGENT_REGISTRY.keys())
    active_configs: list[AgentConfig] = [
        AGENT_REGISTRY[a] for a in active_agents if a in AGENT_REGISTRY
    ]
    total_tasks = len(chunks) * len(active_configs)
    done_counter = {"n": 0}

    cache_names = await _create_agent_caches(
        llm=llm, canvas=canvas, agent_configs=active_configs
    )

    async def _run_one(
        agent_cfg: AgentConfig,
        chunk: TranscriptChunk,
        *,
        extra_user_context: str | None = None,
    ) -> AgentResult:
        async with sem:
            result = await run_extraction_agent(
                agent_cfg, chunk, canvas,
                client=llm, rate_limiter=limiter,
                cached_content=cache_names.get(agent_cfg.name),
                extra_user_context=extra_user_context,
            )
            done_counter["n"] += 1
            if progress:
                await progress(
                    agent=agent_cfg.name,
                    chunk_index=chunk.index,
                    done=done_counter["n"],
                    total=total_tasks,
                )
            return result

    try:
        if wave_execution:
            wave1_configs = [c for c in active_configs if c.wave == 1]
            wave2_configs = [c for c in active_configs if c.wave == 2]
            legacy_configs = [c for c in active_configs if c.wave not in (1, 2)]

            agent_results: list[AgentResult] = []

            # Wave 1 parallel run. Preference anchors (T2.2) доступны
            # и волне 1 — лайкнутые примеры дают весь spectrum (hook
            # воспитывается от лайкнутых hooks, эмоции — от лайкнутых emotions).
            if wave1_configs:
                wave1_tasks = [
                    asyncio.create_task(
                        _run_one(ac, ch, extra_user_context=preference_anchors)
                    )
                    for ac in wave1_configs
                    for ch in chunks
                ]
                wave1_results = await asyncio.gather(*wave1_tasks)
                agent_results.extend(wave1_results)
                log.info(
                    "extraction_wave_complete",
                    wave=1,
                    agents=len(wave1_configs),
                    evidence=sum(len(r.evidence) for r in wave1_results),
                )

            # T1.2 slice 2: coverage_summary детерминистический reducer
            # между волнами. Без LLM — чистая агрегация evidence волны 1
            # (счётчики по чанкам, доминирующие темы, gap-chunks).
            # Волна 2 получает summary в user payload и фокусируется на
            # непокрытом материале / deep-meaning в уже активных фрагментах.
            coverage_context: str | None = None
            if wave1_configs and wave2_configs:
                coverage = build_coverage_summary(
                    [
                        r for r in agent_results
                        if r.agent in {c.name for c in wave1_configs}
                    ],
                    chunks,
                    canvas,
                )
                coverage_context = coverage.to_prompt_text()
                log.info(
                    "extraction_coverage_built",
                    wave1_evidence=coverage.total_wave1_evidence,
                    gap_chunks=len(coverage.gap_chunk_indices),
                    dominant_themes=len(coverage.dominant_themes),
                    summary_chars=len(coverage_context or ""),
                )

            if wave2_configs:
                # Волна 2 получает и coverage_summary, и preference_anchors.
                # Склеиваем, если оба заданы.
                wave2_user_ctx = _combine_contexts(
                    preference_anchors, coverage_context
                )
                wave2_tasks = [
                    asyncio.create_task(
                        _run_one(ac, ch, extra_user_context=wave2_user_ctx)
                    )
                    for ac in wave2_configs
                    for ch in chunks
                ]
                wave2_results = await asyncio.gather(*wave2_tasks)
                agent_results.extend(wave2_results)
                log.info(
                    "extraction_wave_complete",
                    wave=2,
                    agents=len(wave2_configs),
                    evidence=sum(len(r.evidence) for r in wave2_results),
                    coverage_context_attached=coverage_context is not None,
                )

            # Legacy agents (wave=0) — параллельно вне волн.
            if legacy_configs:
                legacy_tasks = [
                    asyncio.create_task(_run_one(ac, ch))
                    for ac in legacy_configs
                    for ch in chunks
                ]
                legacy_results = await asyncio.gather(*legacy_tasks)
                agent_results.extend(legacy_results)
        else:
            # Legacy path: все агенты параллельно (для A/B и backward compat).
            tasks = [
                asyncio.create_task(_run_one(ac, ch))
                for ac in active_configs
                for ch in chunks
            ]
            agent_results = list(await asyncio.gather(*tasks))
    finally:
        await _delete_agent_caches(llm=llm, cache_names=cache_names)

    evidence: list[EvidenceItem] = []
    failed = 0
    for res in agent_results:
        if res.failure_reason:
            failed += 1
        evidence.extend(res.evidence)

    log.info(
        "extraction_done",
        total_evidence=len(evidence),
        agent_runs=len(agent_results),
        failed_runs=failed,
        chunks=len(chunks),
        agents=len(active_agents),
        wave_execution=wave_execution,
    )

    return ExtractionResult(
        evidence=evidence,
        agent_results=list(agent_results),
        failed_count=failed,
    )



def _combine_contexts(*parts: str | None) -> str | None:
    """Склеивает несколько опциональных контекст-блоков в один user-payload
    префикс. None/пустые пропускаем. Если все None — возвращаем None."""
    filled = [p for p in parts if p]
    if not filled:
        return None
    return "\n\n".join(filled)


async def _create_agent_caches(
    *,
    llm: LLMClient,
    canvas: ProjectCanvas,
    agent_configs: list[AgentConfig],
) -> dict[AgentName, str]:
    """Создаёт per-agent Gemini context cache параллельно.

    Работает только для GeminiClient. Для других провайдеров возвращает
    пустой dict (caching у них реализован на уровне complete_json или
    вообще отсутствует). Любая ошибка per-agent → просто отсутствие
    cache для этого агента (fallback на обычный вызов внутри
    run_extraction_agent).
    """

    if not isinstance(llm, GeminiClient):
        return {}

    canvas_context = canvas.to_llm_context()

    async def _one(cfg: AgentConfig) -> tuple[AgentName, str] | None:
        prompt_body = DEFAULT_PROMPTS[cfg.prompt_key]
        system = f"{build_system_prompt()}\n\n{canvas_context}\n\n{prompt_body}"
        cache_name = await llm.create_cache(
            system_instruction=system,
            ttl_seconds=1800,
            display_name=f"videomaker-{cfg.name}",
        )
        if cache_name is None:
            return None
        return cfg.name, cache_name

    pairs = await asyncio.gather(*(_one(cfg) for cfg in agent_configs))
    return {a: c for pair in pairs if pair is not None for (a, c) in [pair]}


async def _delete_agent_caches(
    *,
    llm: LLMClient,
    cache_names: dict[AgentName, str],
) -> None:
    """Параллельно удаляет все cache'и созданные `_create_agent_caches`."""

    if not cache_names or not isinstance(llm, GeminiClient):
        return
    await asyncio.gather(
        *(llm.delete_cache(name) for name in cache_names.values()),
        return_exceptions=True,
    )
