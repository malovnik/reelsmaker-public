"""TIER2-#16: Cross-chunk coherence reducer.

После :func:`reducer.reduce_and_rank` кандидаты уже отфильтрованы от
ближайших дубликатов и отранжированы по composite_score, но каждый
происходит из своего chunk'а, и LLM-extractor каждого chunk'а не видел
остальных. Отсюда возможны противоречия между chunk'ами:

* Два item'а описывают один факт с разными подробностями (например, «герой
  год назад ушёл из корпорации» vs «герой никогда не работал в корпорации»).
* Один item переворачивает тезис другого («поэтому X работает» vs
  «поэтому X не работает»).
* Логические несостыковки в характеристиках героя (возраст, имя, роль).

Этот модуль делает **ОДИН** дополнительный LLM-вызов (Flash Lite) на
список ranked items. Модель возвращает ID кандидатов, которые нужно
удалить, и glob_context — итоговое согласованное описание мира видео.

Стоимость — ~1 дешёвого вызова на видео (~$0.005), эффект — устранение
явных противоречий в финальном pool'е, что особенно важно при длинных
(1h+) видео с 10+ chunks.

Режимы строгости:

* ``soft`` — удалять только при **уверенности ≥ 0.75**; спорные случаи
  оставляем.
* ``strict`` — удалять всё что помечено как противоречие с уверенностью
  ≥ 0.5.

Fallback: любая ошибка LLM (parse, rate-limit, timeout) → возвращаем
исходный ``RankedEvidence`` без фильтрации. Включение фичи не ломает
пайплайн даже при падении Gemini.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

from videomaker.core.config import get_settings
from videomaker.core.logging import get_logger
from videomaker.models.canvas import ProjectCanvas
from videomaker.models.evidence import RankedEvidence, RankedEvidenceItem
from videomaker.services.llm_client import (
    LLMClient,
    LLMError,
    build_llm_for_tier,
    parse_json_response,
)
from videomaker.services.rate_limiter import RateLimiter, get_gemini_rate_limiter

log = get_logger(__name__)

CoherenceStrictness = Literal["soft", "strict"]

_SYSTEM_PROMPT = """Ты — редактор-координатор, который следит за цельностью
серии коротких вертикальных видео. Тебе дают общий контекст (Project Canvas)
и список кандидатов-рилсов, собранных из разных частей исходника. Каждый
кандидат имеет id, роль (hook/development/peak/payoff), текст и reasoning.

Твоя задача: найти логические противоречия между кандидатами и предложить,
какие из них удалить, чтобы финальный набор рилсов не спорил сам с собой.

Противоречия бывают:
  (1) фактические (два кандидата описывают один факт по-разному);
  (2) атрибутивные (характеристики героя/объекта несовместимы);
  (3) тезисные (один кандидат переворачивает смысл другого).

ВАЖНО: НЕ удаляй кандидатов, у которых просто разный ракурс одного и того
же факта — только явные противоречия. При сомнении — оставь.

Верни СТРОГО JSON-объект:
{
  "removed": [
    {"id": "<id>", "reason": "<краткое обоснование>", "confidence": <0.0-1.0>}
  ],
  "global_context": "<1-2 предложения: согласованная картина мира видео>"
}

Если противоречий нет — "removed": [].
"""


@dataclass(slots=True)
class CoherenceStats:
    """Результат работы cross-chunk reducer'а."""

    enabled: bool
    before_count: int
    after_count: int
    removed_count: int
    global_context: str
    failed: bool
    """True если LLM-вызов упал и был применён fallback."""

    @property
    def saved(self) -> bool:
        return self.removed_count > 0 and not self.failed


async def apply_cross_chunk_coherence(
    ranked: RankedEvidence,
    canvas: ProjectCanvas,
    *,
    strictness: CoherenceStrictness = "soft",
    client: LLMClient | None = None,
    rate_limiter: RateLimiter | None = None,
    pipeline_provider: str | None = None,
) -> tuple[RankedEvidence, CoherenceStats]:
    """Отсеивает item'ы, противоречащие глобальному контексту.

    Не меняет порядок и score оставшихся item'ов — только удаляет
    конфликтующие. Возвращает НОВЫЙ объект ``RankedEvidence`` (оригинал не
    мутируется).
    """

    before = len(ranked.items)
    if before < 2:
        return ranked, CoherenceStats(
            enabled=True,
            before_count=before,
            after_count=before,
            removed_count=0,
            global_context="",
            failed=False,
        )

    cfg = get_settings()
    llm = client or build_llm_for_tier("flash_lite", cfg, provider_override=pipeline_provider)
    limiter = rate_limiter or get_gemini_rate_limiter()

    system_prompt = f"{_SYSTEM_PROMPT}\n\n{canvas.to_llm_context()}"
    user_payload = _render_items_for_llm(ranked.items)

    try:
        async with limiter.acquire():
            response = await llm.complete_json(
                system=system_prompt,
                user=user_payload,
                temperature=0.1,
                max_tokens=4000,
            )
        parsed = parse_json_response(response.text)
    except LLMError as exc:
        log.warning("cross_chunk_reducer_llm_failed", error=str(exc))
        return ranked, CoherenceStats(
            enabled=True,
            before_count=before,
            after_count=before,
            removed_count=0,
            global_context="",
            failed=True,
        )
    except Exception as exc:
        log.warning("cross_chunk_reducer_parse_failed", error=str(exc))
        return ranked, CoherenceStats(
            enabled=True,
            before_count=before,
            after_count=before,
            removed_count=0,
            global_context="",
            failed=True,
        )

    removed_ids = _extract_removed_ids(parsed, strictness=strictness)
    global_context = str(parsed.get("global_context", "") or "")
    if not removed_ids:
        log.info(
            "cross_chunk_reducer_no_conflicts",
            items=before,
            strictness=strictness,
        )
        return ranked, CoherenceStats(
            enabled=True,
            before_count=before,
            after_count=before,
            removed_count=0,
            global_context=global_context,
            failed=False,
        )

    kept = [it for it in ranked.items if it.id not in removed_ids]
    filtered = RankedEvidence(
        deduped_count=ranked.deduped_count,
        merged_scene_count=ranked.merged_scene_count,
        items=kept,
    )
    log.info(
        "cross_chunk_reducer_applied",
        before=before,
        after=len(kept),
        removed=before - len(kept),
        strictness=strictness,
    )
    return filtered, CoherenceStats(
        enabled=True,
        before_count=before,
        after_count=len(kept),
        removed_count=before - len(kept),
        global_context=global_context,
        failed=False,
    )


def _render_items_for_llm(items: list[RankedEvidenceItem]) -> str:
    """Компактный JSON-list для входа LLM."""

    payload = [
        {
            "id": it.id,
            "category": it.category,
            "start_sec": round(it.start, 2),
            "end_sec": round(it.end, 2),
            "speaker": it.speaker or "",
            "theme_id": it.theme_id or "",
            "motif_id": it.motif_id or "",
            "score": round(it.composite_score, 3),
            "text": it.text[:500],
            "reasoning": (it.reasoning or "")[:300],
        }
        for it in items
    ]
    return (
        "=== КАНДИДАТЫ ДЛЯ ПРОВЕРКИ КОНСИСТЕНТНОСТИ ===\n"
        + json.dumps(payload, ensure_ascii=False, indent=1)
    )


def _extract_removed_ids(
    parsed: object, *, strictness: CoherenceStrictness
) -> set[str]:
    """Из LLM-ответа достаёт id'шники к удалению с фильтром по confidence."""

    if not isinstance(parsed, dict):
        return set()
    removed = parsed.get("removed")
    if not isinstance(removed, list):
        return set()

    min_confidence = 0.75 if strictness == "soft" else 0.5
    ids: set[str] = set()
    for entry in removed:
        if not isinstance(entry, dict):
            continue
        item_id = entry.get("id")
        if not isinstance(item_id, str) or not item_id:
            continue
        confidence_raw = entry.get("confidence", 1.0)
        try:
            confidence = float(confidence_raw)
        except (TypeError, ValueError):
            confidence = 1.0
        if confidence < min_confidence:
            continue
        ids.add(item_id)
    return ids
