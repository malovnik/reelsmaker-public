"""Hook Detector — Phase 2 top-down narrative pipeline.

Для каждой Chapter находит top-3 HookCandidate внутри неё. Один Gemini
Flash Lite вызов на главу, параллельно через ``asyncio.gather``.

Research basis: docs/viral-clipper-research-2026-04-21.md
    OpusClip 3.0 architecture: hook detection — per-chapter subtask, не
    global scan. Hook должен быть в первых 40% главы
    (HOOK_POSITION_WINDOW_RATIO=0.4).

Anti-confirmation prompting (борется с bias Flash Lite к "complete"):
    - Prompt явно требует "лучше пустой массив чем 3 средних".
    - Score threshold 0.5 для попадания в output (composer применяет 0.65).
    - Post-filter: пустой output главы → graceful (нет hook'ов = нет
      рилса из этой главы).

Entry: ``detect_hooks(chapters, transcript, *, settings, llm_client=None,
rate_limiter=None, provider_override=None) -> dict[chapter_id, list[HookCandidate]]``

Параллелизм: ``asyncio.gather(*[detect_for_chapter(ch) for ch in chapters])``.
Rate limiter ``get_gemini_rate_limiter()`` делит пропускную способность
между chapter'ами (Gemini soft RPM 60/min на Flash Lite).
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Literal

from videomaker.core.config import Settings, get_settings
from videomaker.core.logging import get_logger
from videomaker.models.narrative import Chapter, HookCandidate
from videomaker.services.llm_client import (
    LLMClient,
    LLMError,
    build_llm_for_tier,
    parse_json_response,
)
from videomaker.services.narrative.constants import (
    HOOK_MAX_DURATION_SEC,
    HOOK_MIN_DURATION_SEC,
    HOOK_POSITION_WINDOW_RATIO,
)
from videomaker.services.prompts import (
    HOOK_DETECTOR_PROMPT,
    build_context_header,
    build_system_prompt,
)
from videomaker.services.rate_limiter import RateLimiter, get_gemini_rate_limiter
from videomaker.services.transcribers.base import TranscriptResult

log = get_logger(__name__)

_HookKind = Literal[
    "question",
    "bold_claim",
    "counter_intuitive",
    "emotional_trigger",
    "pattern_break",
    "stat_shock",
]
_VALID_HOOK_KINDS: frozenset[str] = frozenset(
    (
        "question",
        "bold_claim",
        "counter_intuitive",
        "emotional_trigger",
        "pattern_break",
        "stat_shock",
    )
)

#: Минимальный score для попадания hook'а в output.
#: Composer применит более жёсткий cut-off (0.65), но мы пускаем 0.5+
#: чтобы arc_finder имел возможность переоценить hook в контексте arc'а.
HOOK_MIN_SCORE: float = 0.5

#: Soft cap расширенной зоны hook'а: если в первых 40% нет сильного hook'а,
#: разрешаем расширить до 60% с штрафом -0.1 к score. За пределами 60% главы
#: — это уже не hook, это highlight (обработается arc_finder как payoff).
HOOK_SOFT_WINDOW_RATIO: float = 0.6
HOOK_LATE_PENALTY: float = 0.1

#: Максимум hook'ов на главу в output.
HOOK_TOP_K: int = 3


@dataclass(slots=True, frozen=True)
class _HookContext:
    """Контекст вызова для одной главы."""

    chapter: Chapter
    transcript_slice_text: str


async def detect_hooks(
    chapters: list[Chapter],
    transcript: TranscriptResult,
    *,
    settings: Settings | None = None,
    llm_client: LLMClient | None = None,
    rate_limiter: RateLimiter | None = None,
    provider_override: str | None = None,
) -> dict[str, list[HookCandidate]]:
    """Находит top-3 hook-кандидата в каждой главе.

    Возвращает ``dict[chapter_id → list[HookCandidate]]``. Если в главе
    нет hook'а (LLM вернул пустой массив или confidence < 0.5) —
    ``result[chapter_id] = []``. Caller решает что делать с пустыми
    (downstream ranker их пропустит).

    Параллелизм: asyncio.gather для всех глав одновременно; rate_limiter
    сериализует LLM calls (Gemini RPM quota).
    """

    if not chapters:
        return {}

    cfg = settings or get_settings()
    llm = llm_client or build_llm_for_tier(
        "flash_lite", cfg, provider_override=provider_override
    )
    limiter = rate_limiter or get_gemini_rate_limiter()

    contexts = [
        _HookContext(chapter=ch, transcript_slice_text=_slice_text(transcript, ch))
        for ch in chapters
    ]

    tasks = [
        _detect_for_chapter(
            ctx,
            transcript=transcript,
            llm=llm,
            limiter=limiter,
        )
        for ctx in contexts
    ]
    chapter_results = await asyncio.gather(*tasks, return_exceptions=True)

    result: dict[str, list[HookCandidate]] = {}
    for ctx, res in zip(contexts, chapter_results, strict=True):
        if isinstance(res, BaseException):
            log.warning(
                "hook_detector_chapter_failed",
                chapter_id=ctx.chapter.id,
                error=str(res),
            )
            result[ctx.chapter.id] = []
            continue
        result[ctx.chapter.id] = res

    total_hooks = sum(len(v) for v in result.values())
    log.info(
        "hook_detector_done",
        chapters=len(chapters),
        hooks_total=total_hooks,
        chapters_with_hooks=sum(1 for v in result.values() if v),
        chapters_empty=sum(1 for v in result.values() if not v),
    )
    return result


async def _detect_for_chapter(
    ctx: _HookContext,
    *,
    transcript: TranscriptResult,
    llm: LLMClient,
    limiter: RateLimiter,
) -> list[HookCandidate]:
    """Один Flash Lite call на главу. Возвращает отфильтрованные hooks."""

    if ctx.chapter.duration_sec() < HOOK_MIN_DURATION_SEC * 2:
        # Глава слишком короткая для hook'а — редкий случай после
        # chapter_builder post-processing, но защита от сбоев.
        return []

    context_header = build_context_header(
        source_duration_sec=transcript.duration_sec,
        transcriber=transcript.transcriber,
        llm_model=llm.model,
        language=transcript.language,
    )
    system = f"{build_system_prompt()}\n\n{context_header}\n\n{HOOK_DETECTOR_PROMPT}"
    user_payload = _build_user_payload(ctx)

    async with limiter.acquire():
        response = await llm.complete_json(
            system=system,
            user=user_payload,
            temperature=0.35,
            max_tokens=1600,
        )

    try:
        parsed = parse_json_response(response.text)
    except LLMError as exc:
        log.warning(
            "hook_detector_parse_failed",
            chapter_id=ctx.chapter.id,
            error=str(exc),
        )
        return []

    if not isinstance(parsed, dict):
        log.warning(
            "hook_detector_bad_shape",
            chapter_id=ctx.chapter.id,
            type=type(parsed).__name__,
        )
        return []

    raw_hooks = parsed.get("hooks")
    if not isinstance(raw_hooks, list):
        log.warning(
            "hook_detector_hooks_not_list",
            chapter_id=ctx.chapter.id,
            type=type(raw_hooks).__name__,
        )
        return []

    candidates = _parse_hook_items(raw_hooks, ctx.chapter)
    filtered = _apply_quality_filters(candidates, ctx.chapter)
    return filtered[:HOOK_TOP_K]


def _build_user_payload(ctx: _HookContext) -> str:
    """Prompt с chapter meta + transcript slice."""

    chapter = ctx.chapter
    hook_window_end = chapter.start_sec + chapter.duration_sec() * HOOK_POSITION_WINDOW_RATIO
    hook_soft_end = chapter.start_sec + chapter.duration_sec() * HOOK_SOFT_WINDOW_RATIO

    meta = {
        "chapter_id": chapter.id,
        "chapter_start_sec": round(chapter.start_sec, 2),
        "chapter_end_sec": round(chapter.end_sec, 2),
        "chapter_duration_sec": round(chapter.duration_sec(), 2),
        "topic_label": chapter.topic_label,
        "key_claims": chapter.key_claims,
        "hook_window_end_sec": round(hook_window_end, 2),
        "hook_soft_window_end_sec": round(hook_soft_end, 2),
        "hook_min_duration_sec": HOOK_MIN_DURATION_SEC,
        "hook_max_duration_sec": HOOK_MAX_DURATION_SEC,
    }

    parts = [
        "Контекст главы (JSON):",
        json.dumps(meta, ensure_ascii=False, indent=2),
        "",
        "Транскрипт главы:",
        ctx.transcript_slice_text or "(пусто)",
        "",
        (
            f"Найди до {HOOK_TOP_K} hook-кандидатов внутри главы. "
            "Hook должен быть 2-8s, в первых 40% главы (soft — до 60% "
            f"со штрафом -{HOOK_LATE_PENALTY:.2f}). Пустой массив hooks "
            "лучше чем слабые кандидаты."
        ),
    ]
    return "\n".join(parts)


def _slice_text(transcript: TranscriptResult, chapter: Chapter) -> str:
    """Текст транскрипта в диапазоне главы."""

    start, end = chapter.start_sec, chapter.end_sec
    if transcript.segments:
        parts: list[str] = []
        for seg in transcript.segments:
            if seg.end < start:
                continue
            if seg.start >= end:
                break
            text = (seg.text or "").strip()
            if not text:
                continue
            # Встраиваем timestamp чтобы LLM мог ссылаться на real timings.
            parts.append(f"[{_fmt_ts(seg.start)}] {text}")
        return "\n".join(parts)

    if transcript.words:
        tokens: list[str] = []
        for w in transcript.words:
            if w.end < start:
                continue
            if w.start >= end:
                break
            token = (w.word or "").strip()
            if token:
                tokens.append(token)
        return " ".join(tokens)

    return ""


def _parse_hook_items(
    raw_hooks: list[object],
    chapter: Chapter,
) -> list[HookCandidate]:
    """Распарсивает raw LLM output в HookCandidate. Невалидные — skip."""

    parsed: list[HookCandidate] = []
    for item in raw_hooks:
        if not isinstance(item, dict):
            continue
        try:
            hook = _parse_single_hook(item, chapter)
        except (ValueError, TypeError) as exc:
            log.debug(
                "hook_detector_parse_item_failed",
                chapter_id=chapter.id,
                error=str(exc),
            )
            continue
        if hook is None:
            continue
        parsed.append(hook)
    return parsed


def _parse_single_hook(
    item: dict[str, object],
    chapter: Chapter,
) -> HookCandidate | None:
    """Строит HookCandidate из одного dict. None если не проходит sanity."""

    hook_start_raw = item.get("hook_start_sec")
    hook_end_raw = item.get("hook_end_sec")
    if not isinstance(hook_start_raw, (int, float)):
        return None
    if not isinstance(hook_end_raw, (int, float)):
        return None

    hook_start = float(hook_start_raw)
    hook_end = float(hook_end_raw)

    # Clamp к границам главы.
    hook_start = max(chapter.start_sec, hook_start)
    hook_end = min(chapter.end_sec, hook_end)

    if hook_end <= hook_start:
        return None

    duration = hook_end - hook_start
    if duration < HOOK_MIN_DURATION_SEC * 0.8:
        # Даём некоторый tolerance (ASR может немного ужимать). < 1.6s — отброс.
        return None
    if duration > HOOK_MAX_DURATION_SEC * 1.2:
        # Слишком длинный hook — тримим до MAX.
        hook_end = hook_start + HOOK_MAX_DURATION_SEC

    text = str(item.get("text") or "").strip()
    if not text:
        return None

    score_raw = item.get("score")
    score = _clamp_float(score_raw, 0.0, 1.0, default=0.0)

    why = str(item.get("why") or "").strip()[:300]

    hook_kind_raw = str(item.get("hook_kind") or "bold_claim").strip().lower()
    hook_kind: _HookKind = "bold_claim"
    if hook_kind_raw in _VALID_HOOK_KINDS:
        hook_kind = _coerce_hook_kind(hook_kind_raw)

    return HookCandidate(
        chapter_id=chapter.id,
        hook_start_sec=hook_start,
        hook_end_sec=hook_end,
        text=text[:500],
        score=score,
        why=why,
        hook_kind=hook_kind,
    )


def _apply_quality_filters(
    hooks: list[HookCandidate],
    chapter: Chapter,
) -> list[HookCandidate]:
    """Apply position-window penalties + min-score filter + dedup overlap."""

    hook_strict_end = chapter.start_sec + chapter.duration_sec() * HOOK_POSITION_WINDOW_RATIO
    hook_soft_end = chapter.start_sec + chapter.duration_sec() * HOOK_SOFT_WINDOW_RATIO

    penalized: list[HookCandidate] = []
    for h in hooks:
        # Position filter: за пределами soft-окна — reject полностью.
        if h.hook_start_sec > hook_soft_end:
            continue

        adjusted_score = h.score
        # Late penalty: в зоне strict..soft — штраф -0.1.
        if h.hook_start_sec > hook_strict_end:
            adjusted_score = max(0.0, h.score - HOOK_LATE_PENALTY)

        if adjusted_score < HOOK_MIN_SCORE:
            continue

        if adjusted_score != h.score:
            # Пересоздаём с обновлённым score.
            penalized.append(
                HookCandidate(
                    chapter_id=h.chapter_id,
                    hook_start_sec=h.hook_start_sec,
                    hook_end_sec=h.hook_end_sec,
                    text=h.text,
                    score=adjusted_score,
                    why=h.why,
                    hook_kind=h.hook_kind,
                )
            )
        else:
            penalized.append(h)

    penalized.sort(key=lambda h: h.score, reverse=True)

    # Dedup by >50% time overlap — оставляем с более высоким score.
    deduped: list[HookCandidate] = []
    for h in penalized:
        overlaps = False
        for accepted in deduped:
            overlap = min(h.hook_end_sec, accepted.hook_end_sec) - max(
                h.hook_start_sec, accepted.hook_start_sec
            )
            if overlap <= 0:
                continue
            shorter = min(h.duration_sec(), accepted.duration_sec())
            if shorter > 0 and (overlap / shorter) > 0.5:
                overlaps = True
                break
        if not overlaps:
            deduped.append(h)

    return deduped


# ─── Utilities ────────────────────────────────────────────────────────────


def _coerce_hook_kind(value: str) -> _HookKind:
    if value == "question":
        return "question"
    if value == "bold_claim":
        return "bold_claim"
    if value == "counter_intuitive":
        return "counter_intuitive"
    if value == "emotional_trigger":
        return "emotional_trigger"
    if value == "pattern_break":
        return "pattern_break"
    if value == "stat_shock":
        return "stat_shock"
    return "bold_claim"


def _clamp_float(
    value: object,
    lo: float,
    hi: float,
    *,
    default: float,
) -> float:
    if isinstance(value, (int, float)):
        return max(lo, min(hi, float(value)))
    return default


def _fmt_ts(sec: float) -> str:
    total = max(0, int(sec))
    m, s = divmod(total, 60)
    return f"{m:02d}:{s:02d}"


__all__ = ["detect_hooks"]
