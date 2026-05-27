"""Post-trim Semantic Closure Validator.

После того как ``compose_reels`` собрал план рилсов, этот сервис
проверяет tail каждого рилса через LLM Flash Lite: завершённая мысль
или обрыв посередине? Если обрыв — пытаемся extend end-границу последнего
segment'а к ближайшему ASR sentence boundary в пределах
``MAX_EXTEND_SEC``. Если дотянуться нельзя — инкрементируем
``closure_failed_count`` в stats для диагностики.

OpusClip-параллель: AAAI-2025 paper описывает boundary regression в
transformer decoder, обученную на 120K аннотациях с "satisfying conclusion"
критерием. У нас нет обученной модели — используем LLM как валидатор,
fallback — эвристика по пунктуации последнего слова.

Важно:
- Валидация запускается параллельно для всех рилсов через asyncio.gather.
- rate_limiter общий с другими Kartoziya-стадиями — gemini_rate_limit_rpm.
- Если LLM упал / превышен бюджет — рилс остаётся как есть (без penalty).
- Extend НЕ выходит за границы source_duration.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from videomaker.core.config import Settings, get_settings
from videomaker.core.logging import get_logger
from videomaker.models.canvas import ProjectCanvas
from videomaker.models.reel_plan import AnalysisResult, ReelPlan, ReelSegment
from videomaker.services.canvas_embedder import cosine_similarity, embed_texts
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

#: Длительность tail-окна перед концом рилса, передаваемого LLM.
#: Поднято с 8 до 15s — LLM получает больше контекста чтобы оценить narrative
#: continuation (была проблема: 8s не давали видеть setup+punch).
CLOSURE_CHECK_WINDOW_SEC = 15.0
#: BUG-#K: trim-backward стратегия. Если extension вперёд невозможен,
#: смотрим до ``CLOSURE_TRIM_BACKWARD_SEC`` назад от текущего end_sec
#: на последний sentence terminator и УРЕЗАЕМ сегмент. Лучше обрезать
#: рилс до чистого предложения, чем оставить с обрывом посреди мысли.
CLOSURE_TRIM_BACKWARD_SEC = 10.0

#: Forward-окно: сколько секунд транскрипта ПОСЛЕ конца рилса передаём
#: LLM чтобы тот решил — история продолжается (payoff в next 30s) или
#: это start новой темы. 30s покрывает typical narrative continuation
#: (anecdote punch line, aphorism conclusion).
CLOSURE_FORWARD_CONTEXT_SEC = 30.0

#: Максимальное окно вперёд, в котором ищем ASR sentence boundary для
#: продления end-границы. Поднято с 8 до 30s — конкретный случай r2 job
#: 18721422 требовал +35s до "круглый или квадратный" payoff. 30s cap
#: даёт рилсу вырасти до REEL_MAX=88s в случае pre-composer evidence 30s.
MAX_EXTEND_SEC = 30.0

#: Знаки конца предложения в ASR-токенах.
_SENTENCE_END_PUNCT: frozenset[str] = frozenset({".", "!", "?", "…"})

#: Минимальный confidence для признания рилса обрывом. Ниже — trust-пасс.
_MIN_INCOMPLETE_CONFIDENCE = 0.6

#: T0.1 + T1.1: semantic-aware стратегия. Когда ASR forward/backward
#: поиск не находит терминатор, ищем ближайший `CanvasCandidateMoment`
#: в окне ``[end_sec, end_sec + CLOSURE_SEMANTIC_FORWARD_SEC]`` с
#: embedding близким к closure-query. Cosine ≥ этого порога → используем
#: его ``end`` как новую границу (похоже на estabilshed закрытие мысли).
CLOSURE_SEMANTIC_FORWARD_SEC = 45.0
CLOSURE_SEMANTIC_MIN_COSINE = 0.50

#: Closure-query для semantic retrieval. Описывает drama-profile ясной
#: концовки — terminal tone, resolution, завершённость. Embed'ится один
#: раз до batch-validation всех рилсов.
_CLOSURE_SEMANTIC_QUERY = (
    "Завершённая мысль. Закрытие темы. Точка, вывод, resolution. "
    "Terminal tone. Финальный аккорд, полная смысловая единица."
)


@dataclass(slots=True, frozen=True)
class ClosureResult:
    reel_id: str
    is_complete: bool
    extended_by_sec: float
    reasoning: str


async def validate_closures(
    analysis: AnalysisResult,
    words: list[TranscribedWord],
    *,
    source_duration_sec: float,
    settings: Settings | None = None,
    client: LLMClient | None = None,
    rate_limiter: RateLimiter | None = None,
    system_prompt: str | None = None,
    canvas: ProjectCanvas | None = None,
    pipeline_provider: str | None = None,
) -> AnalysisResult:
    """In-place post-validation рилсов.

    Каждый рилс, у которого last segment имеет tail без semantic closure,
    получает extend по ближайшему ASR sentence boundary. Если ASR-based
    стратегии невозможны, а ``canvas`` передан с embeddings —
    применяется T1.1 semantic retrieval: ищем ближайший CanvasCandidateMoment
    в forward окне с embedding близким к closure-query.

    Мутирует ``analysis.reels[*].segments[-1]`` и ``stats``.
    """

    analysis.stats.setdefault("closure_checked_count", 0)
    analysis.stats.setdefault("closure_extended_count", 0)
    analysis.stats.setdefault("closure_failed_count", 0)
    analysis.stats.setdefault("closure_complete_count", 0)
    analysis.stats.setdefault("closure_semantic_extended_count", 0)

    if not analysis.reels or not words:
        return analysis
    if source_duration_sec <= 0:
        return analysis

    cfg = settings or get_settings()
    llm = client or build_llm_for_tier("flash_lite", cfg, provider_override=pipeline_provider)
    limiter = rate_limiter or get_gemini_rate_limiter()
    prompt = system_prompt if system_prompt is not None else await get_prompt(
        PromptKey.closure_check
    )

    sorted_words = sorted(words, key=lambda w: w.start)

    # T0.1 + T1.1: pre-embed closure-query один раз для всего batch.
    # Если canvas без embeddings или embed API недоступен — закрытие
    # откатывается только на ASR-based стратегии (прежнее поведение).
    closure_query_embedding: list[float] | None = None
    if canvas and any(m.embedding for m in canvas.candidate_moments):
        query_result = await embed_texts([_CLOSURE_SEMANTIC_QUERY], settings=cfg)
        if query_result and query_result[0]:
            closure_query_embedding = query_result[0]
            log.info(
                "closure_semantic_query_embedded",
                candidate_moments_with_embedding=sum(
                    1 for m in canvas.candidate_moments if m.embedding
                ),
            )

    tasks = [
        _validate_single_reel(
            reel=reel,
            words=sorted_words,
            llm=llm,
            limiter=limiter,
            system_prompt=prompt,
            source_duration_sec=source_duration_sec,
            canvas=canvas,
            closure_query_embedding=closure_query_embedding,
        )
        for reel in analysis.reels
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    extended = 0
    complete = 0
    failed = 0
    for reel, result in zip(analysis.reels, results, strict=True):
        if isinstance(result, BaseException):
            log.warning(
                "closure_validator_error",
                reel_id=reel.reel_id,
                error=str(result),
            )
            continue
        # Narrow type for pyright.
        check: ClosureResult = result
        if check.is_complete and check.extended_by_sec <= 0:
            complete += 1
            continue
        if check.extended_by_sec != 0:
            _apply_extension(reel, check.extended_by_sec, source_duration_sec)
            extended += 1
            direction = "extend" if check.extended_by_sec > 0 else "trim"
            log.info(
                "closure_reel_extended",
                reel_id=reel.reel_id,
                direction=direction,
                delta_sec=round(check.extended_by_sec, 2),
                reasoning=check.reasoning,
            )
        else:
            failed += 1
            log.info(
                "closure_reel_incomplete_no_extension",
                reel_id=reel.reel_id,
                reasoning=check.reasoning,
            )

    analysis.stats["closure_checked_count"] = len(analysis.reels)
    analysis.stats["closure_extended_count"] = extended
    analysis.stats["closure_failed_count"] = failed
    analysis.stats["closure_complete_count"] = complete
    log.info(
        "closure_validation_done",
        checked=len(analysis.reels),
        complete=complete,
        extended=extended,
        failed=failed,
    )
    return analysis


async def _validate_single_reel(
    *,
    reel: ReelPlan,
    words: list[TranscribedWord],
    llm: LLMClient,
    limiter: RateLimiter,
    system_prompt: str,
    source_duration_sec: float,
    canvas: ProjectCanvas | None = None,
    closure_query_embedding: list[float] | None = None,
) -> ClosureResult:
    if not reel.segments:
        return ClosureResult(reel.reel_id, True, 0.0, "no segments")

    last_seg = reel.segments[-1]
    end_sec = last_seg.source_end

    tail_start = max(0.0, end_sec - CLOSURE_CHECK_WINDOW_SEC)
    tail_words = [w for w in words if tail_start <= w.start <= end_sec]
    tail_text = " ".join(w.word for w in tail_words).strip()

    if not tail_text:
        return ClosureResult(reel.reel_id, True, 0.0, "no tail text")

    # Быстрая эвристика: ASR-токен сам заканчивается на терминатор → уже
    # завершено, LLM не вызываем.
    if _ends_with_sentence_terminator(tail_words):
        return ClosureResult(reel.reel_id, True, 0.0, "ASR terminator detected")

    forward_words = [
        w for w in words
        if end_sec < w.start <= min(end_sec + MAX_EXTEND_SEC, source_duration_sec)
    ]
    # Forward context для LLM — транскрипт на ``CLOSURE_FORWARD_CONTEXT_SEC``
    # после end. LLM смотрит не только обрыв, но и продолжение; решает
    # "история продолжается payoff'ом" vs "новая тема начинается".
    context_words = [
        w for w in words
        if end_sec < w.start
        <= min(end_sec + CLOSURE_FORWARD_CONTEXT_SEC, source_duration_sec)
    ]
    context_text = " ".join(w.word for w in context_words).strip()

    system = f"{build_system_prompt()}\n\n{system_prompt}"
    user_parts: list[str] = [
        f"Концовка рилса (последние ~{int(CLOSURE_CHECK_WINDOW_SEC)}с, проверяется):",
        "",
        tail_text,
    ]
    if context_text:
        user_parts.extend([
            "",
            f"FORWARD CONTEXT (что идёт дальше в источнике, следующие ~{int(CLOSURE_FORWARD_CONTEXT_SEC)}с):",
            "",
            context_text,
            "",
            "Реши: мысль в рилсе завершена в tail'е — или payoff/резолюция ещё впереди "
            "в forward context? Если payoff впереди и не дальше "
            f"{int(MAX_EXTEND_SEC)}с — укажи натуральную точку остановки "
            "(найди где рассказчик замыкает мысль). Если впереди уже идёт новая тема "
            "и закрытие было в tail'е — is_complete=true.",
        ])
    user = "\n".join(user_parts)

    try:
        async with limiter.acquire():
            response = await llm.complete_json(
                system=system,
                user=user,
                temperature=0.1,
                max_tokens=300,
            )
    except LLMError as exc:
        log.warning(
            "closure_llm_error",
            reel_id=reel.reel_id,
            error=str(exc),
        )
        return ClosureResult(
            reel.reel_id, True, 0.0, f"LLM error: pass-through: {exc}"
        )

    parsed = parse_json_response(response.text)
    if not isinstance(parsed, dict):
        return ClosureResult(reel.reel_id, True, 0.0, "LLM non-dict response")

    is_complete = bool(parsed.get("is_complete", True))
    confidence_raw = parsed.get("confidence", 1.0)
    try:
        confidence = float(confidence_raw)
    except (TypeError, ValueError):
        confidence = 1.0
    reasoning = str(parsed.get("reasoning", "")).strip() or "no reasoning"

    # Pass-through если LLM не уверен в обрыве.
    if is_complete or confidence < _MIN_INCOMPLETE_CONFIDENCE:
        return ClosureResult(reel.reel_id, True, 0.0, reasoning)

    # Стратегия 1: extension ВПЕРЁД к ближайшему sentence boundary.
    extension_end = _find_next_sentence_end(forward_words)
    if extension_end is not None:
        extend_by = extension_end - end_sec
        if 0 < extend_by <= MAX_EXTEND_SEC:
            return ClosureResult(reel.reel_id, True, extend_by, reasoning)

    # Стратегия 2 (BUG-#K): trim НАЗАД к последнему sentence terminator
    # в пределах tail'а. Лучше обрезать рилс до чистого предложения, чем
    # оставить с обрывом посреди мысли. Возвращаем отрицательный
    # extend_by_sec как сигнал trim — apply_extension разберётся.
    trim_target = _find_last_sentence_end_before(
        words, end_sec=end_sec, window_sec=CLOSURE_TRIM_BACKWARD_SEC
    )
    if trim_target is not None and trim_target < end_sec:
        # Минимум 5 секунд рилса должно остаться после trim.
        first_start = reel.segments[0].source_start
        remaining_after_trim = trim_target - first_start
        if remaining_after_trim >= 5.0:
            return ClosureResult(
                reel.reel_id,
                True,
                -(end_sec - trim_target),
                f"{reasoning} | trimmed back to sentence terminator",
            )

    # Стратегия 3 (T0.1 + T1.1): semantic-aware extension через Canvas.
    # ASR-based стратегии провалились (ни forward terminator, ни backward
    # trim). Ищем в forward-window CanvasCandidateMoment с embedding
    # близким к closure-query — если найден и end ≤ source_duration,
    # extend к его end. Семантически-похожий payoff == скорее всего
    # завершённая мысль.
    if canvas is not None and closure_query_embedding is not None:
        semantic_end = _find_semantic_closure_target(
            canvas=canvas,
            start_sec=end_sec,
            max_sec=min(
                end_sec + CLOSURE_SEMANTIC_FORWARD_SEC, source_duration_sec
            ),
            query_embedding=closure_query_embedding,
        )
        if semantic_end is not None:
            extend_by = semantic_end - end_sec
            if 0 < extend_by <= CLOSURE_SEMANTIC_FORWARD_SEC:
                return ClosureResult(
                    reel.reel_id,
                    True,
                    extend_by,
                    f"{reasoning} | extended to semantic closure (Canvas retrieval)",
                )

    return ClosureResult(reel.reel_id, False, 0.0, reasoning)


def _find_semantic_closure_target(
    *,
    canvas: ProjectCanvas,
    start_sec: float,
    max_sec: float,
    query_embedding: list[float],
) -> float | None:
    """Ищет ближайший ``CanvasCandidateMoment`` в окне ``[start_sec, max_sec]``
    с ``cosine(embedding, query_embedding) >= CLOSURE_SEMANTIC_MIN_COSINE``.

    Возвращает ``moment.end`` того, чья cosine максимальна; None если ни
    один не подходит.
    """
    best_end: float | None = None
    best_cosine: float = CLOSURE_SEMANTIC_MIN_COSINE
    for moment in canvas.candidate_moments:
        if moment.embedding is None:
            continue
        # Момент должен начинаться В окне (чтобы его end был вблизи end_sec,
        # не в далёком будущем за горизонтом рилса).
        if moment.start < start_sec or moment.start > max_sec:
            continue
        if moment.end > max_sec:
            continue
        sim = cosine_similarity(query_embedding, moment.embedding)
        if sim >= best_cosine:
            best_cosine = sim
            best_end = moment.end
    return best_end


def _ends_with_sentence_terminator(words: list[TranscribedWord]) -> bool:
    """True если последний word заканчивается на ., !, ?, …"""
    if not words:
        return False
    token = words[-1].word.strip()
    if not token:
        return False
    return token[-1] in _SENTENCE_END_PUNCT


def _find_next_sentence_end(words: list[TranscribedWord]) -> float | None:
    """Возвращает end-timestamp первого слова, оканчивающегося на терминатор."""
    for word in words:
        token = word.word.strip()
        if token and token[-1] in _SENTENCE_END_PUNCT:
            return word.end
    return None


def _find_last_sentence_end_before(
    words: list[TranscribedWord], *, end_sec: float, window_sec: float
) -> float | None:
    """BUG-#K: находит timestamp ПОСЛЕДНЕГО слова-с-терминатором в пределах
    ``[end_sec - window_sec, end_sec - 0.1]``. Используется для trim-backward
    стратегии когда продлить рилс вперёд невозможно.

    Возвращает None если в окне нет предложений с терминатором.
    """

    lo = max(0.0, end_sec - window_sec)
    hi = end_sec - 0.1  # минимум 100мс от текущего конца, иначе нет смысла
    best: float | None = None
    for word in words:
        if word.end < lo:
            continue
        if word.end > hi:
            break
        token = word.word.strip()
        if token and token[-1] in _SENTENCE_END_PUNCT:
            best = word.end
    return best


def _apply_extension(
    reel: ReelPlan,
    extend_by_sec: float,
    source_duration_sec: float,
) -> None:
    """Расширяет ИЛИ урезает source_end последнего segment'а.

    Положительное ``extend_by_sec`` — расширение вперёд к sentence boundary.
    Отрицательное — trim назад (BUG-#K стратегия 2): лучше урезать до
    чистой точки предложения, чем оставить обрыв.

    Мутирует reel.segments[-1] и reel.predicted_duration_sec.
    """
    if extend_by_sec == 0 or not reel.segments:
        return
    last = reel.segments[-1]
    if extend_by_sec > 0:
        new_end = min(last.source_end + extend_by_sec, source_duration_sec)
    else:
        # trim: extend_by_sec < 0 → new_end = last.source_end + extend_by_sec
        new_end = max(last.source_start + 1.0, last.source_end + extend_by_sec)
    delta = new_end - last.source_end
    if abs(delta) < 0.05:
        return
    reel.segments[-1] = ReelSegment(
        source_start=last.source_start,
        source_end=new_end,
        reasoning=last.reasoning,
        order_role=last.order_role,
    )
    reel.predicted_duration_sec = round(
        max(0.0, reel.predicted_duration_sec + delta), 3
    )


__all__ = [
    "CLOSURE_CHECK_WINDOW_SEC",
    "MAX_EXTEND_SEC",
    "ClosureResult",
    "validate_closures",
]
