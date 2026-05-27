"""Generic ExtractionAgent — один класс для всех 6 агентов Stage 5.3.

Все 6 агентов отличаются только промптом и выходной структурой. Вместо 6 копий
класса — один `run_extraction_agent` плюс `AgentConfig` (name, prompt_key,
extra_fields). Orchestrator запускает N_chunks × 6_agents параллельно.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from videomaker.core.logging import get_logger
from videomaker.models.canvas import ProjectCanvas
from videomaker.models.evidence import AgentName, EvidenceItem
from videomaker.services.chunker import TranscriptChunk
from videomaker.services.llm_client import (
    LLMClient,
    LLMError,
    parse_json_response,
)
from videomaker.services.prompts import (
    DEFAULT_PROMPTS,
    PromptKey,
    build_system_prompt,
)
from videomaker.services.rate_limiter import RateLimiter

log = get_logger(__name__)


@dataclass(slots=True, frozen=True)
class AgentConfig:
    """Конфигурация extraction-агента.

    `extra_fields` — список ключей которые агент возвращает в `evidence.extra`
    (hook_type, emotion, humor_type, irony_type, thesis_type, role).
    `min_strength_field` — имя поля силы в output'е агента (strength,
    intensity, funniness, significance).
    `thinking_budget` — если задан, Gemini получает `ThinkingConfig(budget)`.
    Для reasoning-агентов (irony / motif / payoff) 512 токенов заметно
    поднимают качество evidence без роста стоимости (TIER1-#10).
    `wave` — (T1.2) номер волны запуска в orchestrate_extraction. Волна 1
    = reaction-extractors (быстрые, pattern-matching); волна 2 = meaning-
    extractors (reasoning_budget, видят coverage_summary от волны 1).
    При wave=0 — классический полный параллелизм без волн (default для
    совместимости).
    """

    name: AgentName
    prompt_key: PromptKey
    extra_fields: tuple[str, ...] = ()
    min_strength_field: str = "strength"
    fallback_strength: float = 0.5
    thinking_budget: int | None = None
    wave: int = 0


AGENT_REGISTRY: dict[AgentName, AgentConfig] = {
    # Wave 1 — reaction-extractors: быстрые pattern-matching без deep reasoning.
    # Ищут «очевидные» моменты на поверхности chunk'а (зацепки/эмоции/шутки).
    # Запускаются первыми, их evidence становится фундаментом coverage_summary
    # для волны 2.
    "hook_hunter": AgentConfig(
        name="hook_hunter",
        prompt_key=PromptKey.hook_hunter,
        extra_fields=("hook_type",),
        min_strength_field="strength",
        wave=1,
    ),
    "emotional_peak_finder": AgentConfig(
        name="emotional_peak_finder",
        prompt_key=PromptKey.emotional_peak_finder,
        extra_fields=("emotion",),
        min_strength_field="intensity",
        wave=1,
    ),
    "humor_specialist": AgentConfig(
        name="humor_specialist",
        prompt_key=PromptKey.humor_specialist,
        extra_fields=("humor_type",),
        min_strength_field="funniness",
        wave=1,
    ),
    # Wave 2 — meaning-extractors: reasoning_budget для поиска skрытых смыслов
    # (ирония, тезис, мотив). Видят coverage_summary от волны 1 чтобы не
    # дублировать находки и фокусироваться на непокрытых чанках/темах.
    "dramatic_irony_scanner": AgentConfig(
        name="dramatic_irony_scanner",
        prompt_key=PromptKey.dramatic_irony_scanner,
        extra_fields=("irony_type", "pairs_with_theme_id"),
        min_strength_field="significance",
        thinking_budget=512,
        wave=2,
    ),
    "thesis_extractor": AgentConfig(
        name="thesis_extractor",
        prompt_key=PromptKey.thesis_extractor,
        extra_fields=("thesis_type", "summary"),
        min_strength_field="strength",
        thinking_budget=512,
        wave=2,
    ),
    "motif_tracker": AgentConfig(
        name="motif_tracker",
        prompt_key=PromptKey.motif_tracker,
        extra_fields=("role",),
        min_strength_field="significance",
        thinking_budget=512,
        wave=2,
    ),
}


@dataclass(slots=True)
class AgentResult:
    agent: AgentName
    chunk_index: int
    evidence: list[EvidenceItem] = field(default_factory=list)
    failure_reason: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0


async def run_extraction_agent(
    agent_cfg: AgentConfig,
    chunk: TranscriptChunk,
    canvas: ProjectCanvas,
    *,
    client: LLMClient,
    rate_limiter: RateLimiter,
    prompt_override: str | None = None,
    cached_content: str | None = None,
    extra_user_context: str | None = None,
) -> AgentResult:
    """Запускает один агент на одном chunk.

    ``cached_content`` — имя Gemini context cache (TIER1-#1). Когда задан,
    system_instruction уже внутри cache, complete_json не будет его
    отправлять повторно → -75% input cost.

    ``extra_user_context`` (T1.2 slice 2-3) — prepend к user payload до
    рендера chunk'а. Используется для инжекции coverage_summary из волны 1
    в промпты волны 2. При None — user = чистый chunk (прежнее поведение).

    Не бросает исключений — при LLM-сбое или битом JSON возвращает AgentResult
    с failure_reason. Orchestrator толерантен к частичным неудачам.
    """
    prompt_body = prompt_override or DEFAULT_PROMPTS[agent_cfg.prompt_key]
    canvas_context = canvas.to_llm_context()
    system = f"{build_system_prompt()}\n\n{canvas_context}\n\n{prompt_body}"

    chunk_payload = chunk.render_for_llm()
    user_payload = (
        f"{extra_user_context}\n\n{chunk_payload}"
        if extra_user_context
        else chunk_payload
    )

    schema = _build_evidence_schema(agent_cfg)
    async with rate_limiter.acquire():
        try:
            response = await client.complete_json(
                system=system,
                user=user_payload,
                temperature=0.2,
                max_tokens=8000,
                thinking_budget=agent_cfg.thinking_budget,
                response_schema=schema,
                cached_content=cached_content,
            )
        except LLMError as exc:
            log.warning(
                "agent_llm_failed",
                agent=agent_cfg.name,
                chunk=chunk.index,
                error=str(exc),
            )
            return AgentResult(
                agent=agent_cfg.name,
                chunk_index=chunk.index,
                failure_reason=f"llm_error: {exc}",
            )

    try:
        parsed = parse_json_response(response.text)
    except LLMError as exc:
        log.warning(
            "agent_parse_failed",
            agent=agent_cfg.name,
            chunk=chunk.index,
            error=str(exc),
        )
        return AgentResult(
            agent=agent_cfg.name,
            chunk_index=chunk.index,
            failure_reason=f"json_error: {exc}",
            input_tokens=response.input_tokens or 0,
            output_tokens=response.output_tokens or 0,
        )

    if not isinstance(parsed, list):
        log.warning(
            "agent_output_not_array",
            agent=agent_cfg.name,
            chunk=chunk.index,
            type=type(parsed).__name__,
        )
        return AgentResult(
            agent=agent_cfg.name,
            chunk_index=chunk.index,
            failure_reason="output_not_array",
            input_tokens=response.input_tokens or 0,
            output_tokens=response.output_tokens or 0,
        )

    raw_items = (
        _parse_evidence_item(item, agent_cfg, chunk.index)
        for item in parsed
        if isinstance(item, dict)
    )
    evidence = [e for e in raw_items if e is not None]

    log.info(
        "agent_done",
        agent=agent_cfg.name,
        chunk=chunk.index,
        found=len(evidence),
    )
    return AgentResult(
        agent=agent_cfg.name,
        chunk_index=chunk.index,
        evidence=evidence,
        input_tokens=response.input_tokens or 0,
        output_tokens=response.output_tokens or 0,
    )


def _build_evidence_schema(cfg: AgentConfig) -> dict[str, Any]:
    """JSON schema для output'a одного extraction-агента (TIER1-#9).

    Ожидаемый формат: ARRAY из OBJECT'ов с обязательными
    ``start / end / text / <min_strength_field>`` и опциональными
    ``extra_fields`` (строковые метки вроде ``hook_type``, ``irony_type``).

    Gemini при response_schema гарантирует валидный JSON согласно OpenAPI
    3.0 спецификации → убирает parse-fails из json_repair fallback.
    """

    properties: dict[str, dict[str, Any]] = {
        "start": {"type": "NUMBER"},
        "end": {"type": "NUMBER"},
        "text": {"type": "STRING"},
        cfg.min_strength_field: {"type": "NUMBER"},
    }
    for field_name in cfg.extra_fields:
        properties[field_name] = {"type": "STRING"}

    return {
        "type": "ARRAY",
        "items": {
            "type": "OBJECT",
            "properties": properties,
            "required": ["start", "end", "text", cfg.min_strength_field],
        },
    }


def _parse_evidence_item(
    data: dict[str, Any],
    cfg: AgentConfig,
    chunk_index: int,
) -> EvidenceItem | None:
    """Парсит одну запись агента в EvidenceItem. None если malformed."""
    try:
        start = float(data.get("start", 0.0))
        end = float(data.get("end", start))
    except (TypeError, ValueError):
        return None
    if end <= start:
        return None

    text = str(data.get("text", "")).strip()
    if not text:
        return None

    raw_strength = data.get(cfg.min_strength_field, cfg.fallback_strength)
    try:
        strength = max(0.0, min(1.0, float(raw_strength)))
    except (TypeError, ValueError):
        strength = cfg.fallback_strength

    extra: dict[str, Any] = {}
    for field_name in cfg.extra_fields:
        if field_name in data and data[field_name] is not None:
            extra[field_name] = data[field_name]

    return EvidenceItem(
        source_agent=cfg.name,
        chunk_index=int(data.get("chunk_index", chunk_index)),
        start=max(0.0, start),
        end=max(start, end),
        text=text,
        speaker=data.get("speaker"),
        theme_id=data.get("theme_id"),
        motif_id=data.get("motif_id") or data.get("pairs_with_theme_id"),
        strength=strength,
        reasoning=str(data.get("reasoning", "")).strip(),
        extra=extra,
    )
