"""Stage 5.9 — Arc-Coherence Validator.

Проверяет смысловую связность каждого собранного рилса через LLM Flash Lite.
Нужен после Task #28 (`_pull_closure_from_arc`): composer может подтянуть
payoff из другой части сюжета, и это создаёт рилсы с hook про одно и
payoff про другое — формально валидная, но рваная арка.

Режимы:
* ``off`` — no-op, валидация отключена.
* ``reject`` — рилсы с coherence_score < threshold выбрасываются из
  ``analysis.reels``. Проще и предсказуемее, но сокращает итоговое N.
* ``resort`` — для каждого некогерентного рилса пытаемся заменить payoff на
  top-scored альтернативу из ``ranked`` evidence с тем же motif_id, не
  пересекающуюся с остальными сегментами. Ре-чек. Если не находим замену
  или alternative тоже < threshold — keep original с warning в stats.

stats пополняет:
* ``coherence_checked_count`` — сколько рилсов валидировалось
* ``coherence_accepted_count`` — прошли с первой попытки
* ``coherence_resorted_count`` — пересобрались после замены payoff
* ``coherence_rejected_count`` — выброшены (только в reject mode)
* ``coherence_kept_low_count`` — оставлены ниже threshold (только в resort mode)
* ``coherence_score_mean`` / ``coherence_score_min`` — распределение

Инвариант: rate_limiter общий с closure_validator — не гоняем два конкурирующих
LLM burst'а. Ошибка LLM (timeout/quota) → рилс считаем прошедшим (trust-пасс).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal

from videomaker.core.config import Settings, get_settings
from videomaker.core.logging import get_logger
from videomaker.models.evidence import RankedEvidence, RankedEvidenceItem
from videomaker.models.reel_plan import AnalysisResult, ReelPlan, ReelSegment
from videomaker.services.llm_client import (
    LLMClient,
    LLMError,
    build_llm_for_tier,
    parse_json_response,
)
from videomaker.services.prompt_store import get_prompt
from videomaker.services.prompts import PromptKey, build_system_prompt
from videomaker.services.rate_limiter import RateLimiter, get_gemini_rate_limiter
from videomaker.services.transcribers.base import TranscribedWord

log = get_logger(__name__)

CoherenceMode = Literal["off", "reject", "resort"]

#: Минимальная длительность альтернативного payoff (сек). Меньше — обрывок,
#: не имеет драматургического веса.
_MIN_ALTERNATE_PAYOFF_SEC = 6.0

#: Максимальная длительность альтернативного payoff (сек). Больше — меняет
#: баланс рилса, может вытолкнуть его за REEL_MAX.
_MAX_ALTERNATE_PAYOFF_SEC = 22.0

#: Минимальный зазор (сек) между альтернативным payoff и остальными сегментами
#: рилса — защита от повторного overlap.
_PAYOFF_GAP_SEC = 1.0


@dataclass(slots=True, frozen=True)
class CoherenceResult:
    reel_id: str
    score: float
    reasoning: str
    main_weakness: str  # "theme" | "logic" | "tone" | "none"


async def validate_coherence(
    analysis: AnalysisResult,
    words: list[TranscribedWord],
    *,
    source_duration_sec: float,
    mode: CoherenceMode,
    threshold: float,
    ranked: RankedEvidence | None = None,
    settings: Settings | None = None,
    client: LLMClient | None = None,
    rate_limiter: RateLimiter | None = None,
    system_prompt: str | None = None,
    pipeline_provider: str | None = None,
) -> AnalysisResult:
    """In-place coherence валидация рилсов.

    В режиме ``off`` — no-op, только инициализирует stats нулями. В режимах
    ``reject``/``resort`` мутирует ``analysis.reels`` (reject удаляет рилсы,
    resort может заменить payoff-сегмент) и ``stats``.

    `ranked` нужен только для resort — иначе None. Если ranked=None в resort —
    деградируем до behave-as-keep (warning в stats).
    """
    analysis.stats.setdefault("coherence_mode", mode)
    analysis.stats.setdefault("coherence_threshold", threshold)
    analysis.stats.setdefault("coherence_checked_count", 0)
    analysis.stats.setdefault("coherence_accepted_count", 0)
    analysis.stats.setdefault("coherence_resorted_count", 0)
    analysis.stats.setdefault("coherence_rejected_count", 0)
    analysis.stats.setdefault("coherence_kept_low_count", 0)

    if mode == "off" or not analysis.reels or not words:
        return analysis
    if source_duration_sec <= 0:
        return analysis

    cfg = settings or get_settings()
    llm = client or build_llm_for_tier("flash_lite", cfg, provider_override=pipeline_provider)
    limiter = rate_limiter or get_gemini_rate_limiter()
    prompt = (
        system_prompt
        if system_prompt is not None
        else await get_prompt(PromptKey.coherence_check)
    )

    sorted_words = sorted(words, key=lambda w: w.start)

    # Первый проход — параллельный check всех рилсов.
    first_pass_tasks = [
        _check_single_reel(
            reel=reel,
            words=sorted_words,
            llm=llm,
            limiter=limiter,
            system_prompt=prompt,
        )
        for reel in analysis.reels
    ]
    first_results = await asyncio.gather(*first_pass_tasks, return_exceptions=True)

    kept_reels: list[ReelPlan] = []
    scores: list[float] = []
    accepted = 0
    resorted = 0
    rejected = 0
    kept_low = 0

    for reel, raw_result in zip(analysis.reels, first_results, strict=True):
        result = _coerce_result(reel.reel_id, raw_result)
        scores.append(result.score)

        if result.score >= threshold:
            kept_reels.append(reel)
            accepted += 1
            continue

        # Ниже threshold — действуем по режиму.
        if mode == "reject":
            rejected += 1
            log.info(
                "coherence_reel_rejected",
                reel_id=reel.reel_id,
                score=round(result.score, 2),
                reasoning=result.reasoning,
                weakness=result.main_weakness,
            )
            continue

        # mode == "resort": пытаемся найти альтернативный payoff.
        if ranked is None or not ranked.items:
            # Нет пула для resort → keep as-is.
            kept_reels.append(reel)
            kept_low += 1
            log.info(
                "coherence_reel_kept_low_no_ranked",
                reel_id=reel.reel_id,
                score=round(result.score, 2),
            )
            continue

        alternate = _find_alternate_payoff(
            reel, ranked, source_duration_sec=source_duration_sec
        )
        if alternate is None:
            kept_reels.append(reel)
            kept_low += 1
            log.info(
                "coherence_reel_kept_low_no_alt",
                reel_id=reel.reel_id,
                score=round(result.score, 2),
            )
            continue

        rebuilt = _swap_payoff(reel, alternate)
        # Re-check rebuilt reel.
        try:
            recheck_result = await _check_single_reel(
                reel=rebuilt,
                words=sorted_words,
                llm=llm,
                limiter=limiter,
                system_prompt=prompt,
            )
        except LLMError as exc:
            log.warning(
                "coherence_recheck_llm_failed",
                reel_id=reel.reel_id,
                error=str(exc),
            )
            recheck_result = CoherenceResult(reel.reel_id, result.score, "recheck failed", "none")

        if recheck_result.score >= threshold:
            kept_reels.append(rebuilt)
            resorted += 1
            scores.append(recheck_result.score)
            log.info(
                "coherence_reel_resorted",
                reel_id=reel.reel_id,
                old_score=round(result.score, 2),
                new_score=round(recheck_result.score, 2),
            )
        else:
            # Замена не помогла — keep original.
            kept_reels.append(reel)
            kept_low += 1
            log.info(
                "coherence_reel_kept_low_after_resort",
                reel_id=reel.reel_id,
                old_score=round(result.score, 2),
                attempted_score=round(recheck_result.score, 2),
            )

    analysis.reels = kept_reels
    analysis.stats["coherence_checked_count"] = len(first_results)
    analysis.stats["coherence_accepted_count"] = accepted
    analysis.stats["coherence_resorted_count"] = resorted
    analysis.stats["coherence_rejected_count"] = rejected
    analysis.stats["coherence_kept_low_count"] = kept_low
    if scores:
        analysis.stats["coherence_score_mean"] = round(
            sum(scores) / len(scores), 3
        )
        analysis.stats["coherence_score_min"] = round(min(scores), 3)

    log.info(
        "coherence_validation_done",
        mode=mode,
        threshold=threshold,
        checked=len(first_results),
        accepted=accepted,
        resorted=resorted,
        rejected=rejected,
        kept_low=kept_low,
    )
    return analysis


def _coerce_result(
    reel_id: str, raw: object
) -> CoherenceResult:
    """Safely приводит asyncio.gather-результат к CoherenceResult.

    Если воркер упал (LLMError/timeout/parse) — даём рилсу прошедший балл,
    чтобы не штрафовать пайплайн за транзиентные сбои модели.
    """
    if isinstance(raw, BaseException):
        log.warning("coherence_worker_failed", reel_id=reel_id, error=str(raw))
        return CoherenceResult(reel_id, 1.0, "worker failure — trust-pass", "none")
    if isinstance(raw, CoherenceResult):
        return raw
    return CoherenceResult(reel_id, 1.0, "unexpected worker output — trust-pass", "none")


async def _check_single_reel(
    *,
    reel: ReelPlan,
    words: list[TranscribedWord],
    llm: LLMClient,
    limiter: RateLimiter,
    system_prompt: str,
) -> CoherenceResult:
    if not reel.segments:
        return CoherenceResult(reel.reel_id, 1.0, "no segments", "none")

    if len(reel.segments) <= 1:
        return CoherenceResult(
            reel.reel_id,
            1.0,
            "single-segment reel, coherence N/A",
            "none",
        )

    hook_seg = reel.segments[0]
    payoff_seg = reel.segments[-1]
    body_segs = reel.segments[1:-1]

    hook_text = _extract_segment_text(hook_seg, words)
    payoff_text = _extract_segment_text(payoff_seg, words)
    body_text = " ".join(_extract_segment_text(s, words) for s in body_segs).strip()

    if not hook_text or not payoff_text:
        return CoherenceResult(reel.reel_id, 1.0, "insufficient text", "none")

    user_payload = (
        f"HOOK:\n{hook_text}\n\n"
        f"BODY:\n{body_text or '(пусто, рилс без body)'}\n\n"
        f"PAYOFF:\n{payoff_text}"
    )

    async with limiter.acquire():
        try:
            response = await llm.complete_json(
                system=f"{build_system_prompt()}\n\n{system_prompt}",
                user=user_payload,
                temperature=0.1,
                max_tokens=512,
            )
        except LLMError as exc:
            log.warning(
                "coherence_llm_failed", reel_id=reel.reel_id, error=str(exc)
            )
            return CoherenceResult(reel.reel_id, 1.0, "llm failure — trust-pass", "none")

    data = parse_json_response(response.text)
    if not isinstance(data, dict):
        return CoherenceResult(reel.reel_id, 1.0, "parse fail — trust-pass", "none")

    try:
        score = max(0.0, min(1.0, float(data.get("coherence_score", 1.0))))
    except (TypeError, ValueError):
        score = 1.0
    reasoning = str(data.get("reasoning", "")).strip()[:240]
    weakness_raw = str(data.get("main_weakness", "none")).strip().lower()
    weakness = weakness_raw if weakness_raw in {"theme", "logic", "tone", "none"} else "none"

    return CoherenceResult(reel.reel_id, score, reasoning, weakness)


def _extract_segment_text(segment: ReelSegment, words: list[TranscribedWord]) -> str:
    """Восстанавливает текст сегмента из whisper word-timestamps.

    Берём слова чьи start попадают в [source_start, source_end]. Даже если
    границы сегмента чуть шире последнего слова (из-за extend), это корректно.
    """
    parts = [
        w.word
        for w in words
        if segment.source_start <= w.start < segment.source_end
    ]
    return " ".join(parts).strip()


# ---------------------------------------------------------------------------
# Resort: поиск альтернативного payoff
# ---------------------------------------------------------------------------


def _find_alternate_payoff(
    reel: ReelPlan,
    ranked: RankedEvidence,
    *,
    source_duration_sec: float,
) -> RankedEvidenceItem | None:
    """Ищет top-scored payoff-кандидата из ranked, не пересекающегося с
    сегментами рилса. Если у рилса есть hook с известным motif, приоритет —
    кандидатам с тем же motif.

    Возвращает RankedEvidenceItem или None если подходящих нет.
    """
    if not reel.segments or not ranked.items:
        return None

    hook_seg = reel.segments[0]
    # Пытаемся определить motif hook'а по evidence, покрывающему hook-диапазон.
    hook_motif = _infer_motif(hook_seg, ranked)

    occupied = [(s.source_start, s.source_end) for s in reel.segments]

    candidates: list[RankedEvidenceItem] = []
    for item in ranked.items:
        if item.category != "payoff_candidate":
            continue
        length = item.end - item.start
        if length < _MIN_ALTERNATE_PAYOFF_SEC or length > _MAX_ALTERNATE_PAYOFF_SEC:
            continue
        if item.end > source_duration_sec + 0.5:
            continue
        if _overlaps_any(item.start, item.end, occupied, gap=_PAYOFF_GAP_SEC):
            continue
        candidates.append(item)

    if not candidates:
        return None

    # Сортировка: сначала совпадающий motif, затем по composite_score.
    def _sort_key(item: RankedEvidenceItem) -> tuple[int, float]:
        motif_match = 0 if (hook_motif and item.motif_id == hook_motif) else 1
        return (motif_match, -item.composite_score)

    candidates.sort(key=_sort_key)
    return candidates[0]


def _infer_motif(segment: ReelSegment, ranked: RankedEvidence) -> str | None:
    """Находит motif_id evidence, чей диапазон максимально перекрывается с segment."""
    best: RankedEvidenceItem | None = None
    best_overlap = 0.0
    for item in ranked.items:
        inter = min(segment.source_end, item.end) - max(segment.source_start, item.start)
        if inter <= 0:
            continue
        if inter > best_overlap:
            best_overlap = inter
            best = item
    return best.motif_id if best else None


def _overlaps_any(
    start: float, end: float, ranges: list[tuple[float, float]], *, gap: float
) -> bool:
    return any(start < re + gap and end > rs - gap for rs, re in ranges)


def _swap_payoff(
    reel: ReelPlan, alternate: RankedEvidenceItem
) -> ReelPlan:
    """Возвращает копию reel с заменённым последним segment на alternate-payoff."""
    new_segments: list[ReelSegment] = list(reel.segments[:-1])
    new_segments.append(
        ReelSegment(
            source_start=alternate.start,
            source_end=alternate.end,
            reasoning=(
                f"coherence resort → payoff from ranked (motif={alternate.motif_id}, "
                f"score={alternate.composite_score:.2f})"
            ),
            order_role="payoff",
        )
    )
    new_duration = sum(s.source_end - s.source_start for s in new_segments)
    return reel.model_copy(
        update={
            "segments": new_segments,
            "predicted_duration_sec": new_duration,
        }
    )


__all__ = [
    "CoherenceMode",
    "CoherenceResult",
    "validate_coherence",
]
