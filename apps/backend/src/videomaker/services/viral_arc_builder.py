"""Viral Arc 2026 — простой OpusClip-style pipeline.

Phase 9 (2026-04-22). Архитектура:
    TranscriptResult
        ↓  char-based chunking (20K chars, 2.5K overlap)
    list[_Chunk]
        ↓  parallel Flash Lite LLM call per chunk (Semaphore)
    list[_LLMReel]
        ↓  temporal IoU dedup (>0.70)
    list[_LLMReel] (deduped)
        ↓  _to_reel_plan (role mapping, validation)
    list[ReelPlan]

Контракт ``build_viral_arcs(transcript, *, cfg) -> list[ReelPlan]`` —
совместимо с downstream ``pipeline_stages/render.py`` так же как legacy
bottom_up output.

Feature flag: ``PerformanceSettings.narrative_mode == "viral_2026"``. Когда
другой mode — модуль не импортируется pipeline'ом.

LLM-стек: Gemini Flash Lite (tier ``"flash_lite"``) — единственный call
per chunk, ~10-15 total на 90-мин видео vs 80-120 у Kartoziya.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

from pydantic import BaseModel, Field, ValidationError

from videomaker.core.config import Settings, get_settings
from videomaker.core.logging import get_logger
from videomaker.models.reel_plan import ReelPlan, ReelSegment
from videomaker.services.llm_client import (
    LLMClient,
    LLMError,
    build_llm_for_tier,
    parse_json_response,
)
from videomaker.services.prompts import VIRAL_2026_PROMPT
from videomaker.services.rate_limiter import RateLimiter, get_gemini_rate_limiter
from videomaker.services.transcribers.base import TranscribedSegment, TranscriptResult

log = get_logger(__name__)

_CHUNK_SIZE_CHARS = 20_000
_CHUNK_OVERLAP_CHARS = 2_500
_MAX_CONCURRENCY = 10
_DEDUP_OVERLAP_RATIO = 0.70
_MIN_SEGMENT_DURATION_SEC = 0.5
_MAX_SEGMENTS_PER_REEL = 8
_MAX_SEGMENT_TEXT_CHARS = 2_000  # ASR hallucination guard.
_MAX_REEL_DURATION_SEC = 300.0  # Верхняя граница валидации (5 мин).


# ---------------------------------------------------------------------------
# Models (LLM output schema + internal chunk container)
# ---------------------------------------------------------------------------


class _LLMSegment(BaseModel):
    start: float = Field(ge=0.0)
    end: float = Field(ge=0.0)
    role: str = "development"
    reason: str = ""


class _LLMReel(BaseModel):
    reel_id: str = Field(min_length=1, max_length=32)
    title: str = ""
    hook_type: str = "curiosity"
    segments: list[_LLMSegment] = Field(
        min_length=1, max_length=_MAX_SEGMENTS_PER_REEL
    )
    # Верхняя граница _MAX_REEL_DURATION_SEC: длинные сторителлинги
    # (up to 5 мин) разрешены — pipeline не должен резать их искусственно.
    target_duration_sec: float = Field(ge=5.0, le=_MAX_REEL_DURATION_SEC)
    save_value: str = ""
    viral_score: int = Field(ge=0, le=100)


@dataclass(slots=True, frozen=True)
class _Chunk:
    index: int
    text: str
    start_sec: float
    end_sec: float


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------


def _fmt_segment_line(seg: TranscribedSegment) -> str:
    """Формат строки: ``[SS.ss-EE.ee] текст``. LLM получает абсолютные
    таймкоды от начала видео — это нужно для корректного ``start``/``end``
    в output'е (cross-chunk dedup и render оперируют на source-time).
    """
    text = (seg.text or "").strip()
    return f"[{seg.start:.2f}-{seg.end:.2f}] {text}"


def _build_chunks(transcript: TranscriptResult) -> list[_Chunk]:
    """Char-based chunking с overlap. Один чанк = до 20K знаков, overlap 2.5K.

    ASR hallucination guard: segments > 2K chars (Whisper loop артефакты)
    пропускаются, не ломают chunking budget.
    """
    segments = [s for s in transcript.segments if (s.text or "").strip()]
    if not segments:
        return []

    rendered: list[tuple[float, float, str]] = []
    skipped = 0
    for seg in segments:
        text = (seg.text or "").strip()
        if len(text) > _MAX_SEGMENT_TEXT_CHARS:
            skipped += 1
            continue
        line = _fmt_segment_line(seg)
        rendered.append((seg.start, seg.end, line))

    if skipped:
        log.info("viral_arc_asr_sanitize", skipped=skipped)

    if not rendered:
        return []

    chunks: list[_Chunk] = []
    current: list[tuple[float, float, str]] = []
    current_chars = 0
    chunk_idx = 0

    for item in rendered:
        line_len = len(item[2]) + 1
        if current_chars + line_len > _CHUNK_SIZE_CHARS and current:
            chunks.append(
                _Chunk(
                    index=chunk_idx,
                    text="\n".join(x[2] for x in current),
                    start_sec=current[0][0],
                    end_sec=current[-1][1],
                )
            )
            chunk_idx += 1

            overlap_items: list[tuple[float, float, str]] = []
            overlap_chars = 0
            for prev in reversed(current):
                prev_len = len(prev[2]) + 1
                if overlap_chars + prev_len > _CHUNK_OVERLAP_CHARS:
                    break
                overlap_items.insert(0, prev)
                overlap_chars += prev_len
            current = overlap_items
            current_chars = overlap_chars

        current.append(item)
        current_chars += line_len

    if current:
        chunks.append(
            _Chunk(
                index=chunk_idx,
                text="\n".join(x[2] for x in current),
                start_sec=current[0][0],
                end_sec=current[-1][1],
            )
        )

    return chunks


# ---------------------------------------------------------------------------
# LLM call per chunk
# ---------------------------------------------------------------------------


def _build_user_message(chunk: _Chunk, total_duration_sec: float) -> str:
    """User payload — заголовок контекста + транскрипт + OUTPUT instruction."""
    return (
        f"ВИДЕО: длительность {total_duration_sec:.1f} сек.\n"
        f"CHUNK #{chunk.index}: window "
        f"[{chunk.start_sec:.2f}, {chunk.end_sec:.2f}] сек от начала.\n\n"
        "Таймкоды в формате [SS.ss-EE.ee] — это АБСОЛЮТНЫЕ секунды от "
        "начала видео. Используй их в segments[].start и segments[].end.\n\n"
        "--- TRANSCRIPT START ---\n"
        f"{chunk.text}\n"
        "--- TRANSCRIPT END ---\n\n"
        "Верни JSON согласно OUTPUT SCHEMA. Только JSON. Никакого текста "
        "до или после."
    )


async def _score_chunk(
    chunk: _Chunk,
    *,
    total_duration_sec: float,
    llm: LLMClient,
    limiter: RateLimiter,
    semaphore: asyncio.Semaphore,
) -> list[_LLMReel]:
    """Один LLM-call. Возвращает list[_LLMReel] или [] при ошибке."""
    async with semaphore:
        try:
            async with limiter.acquire():
                response = await llm.complete_json(
                    system=VIRAL_2026_PROMPT,
                    user=_build_user_message(chunk, total_duration_sec),
                    temperature=0.85,
                    # Max output Gemini Flash Lite (2.5: 65_535, 3.1: 65_536).
                    # 65_535 работает на обеих — минимум из двух лимитов.
                    max_tokens=65_535,
                )
        except Exception as exc:
            log.warning(
                "viral_arc_chunk_llm_failed",
                chunk_index=chunk.index,
                error=f"{type(exc).__name__}: {exc}",
            )
            return []

        try:
            parsed = parse_json_response(response.text)
        except LLMError as exc:
            log.warning(
                "viral_arc_chunk_parse_failed",
                chunk_index=chunk.index,
                error=str(exc),
                head=response.text[:200] if response.text else "",
            )
            return []

        if not isinstance(parsed, dict):
            log.warning(
                "viral_arc_chunk_bad_shape",
                chunk_index=chunk.index,
                type_=type(parsed).__name__,
            )
            return []

        # Per-reel validation: один невалидный рилс не роняет весь chunk.
        # Важно когда LLM выдал 5 рилсов и один с out-of-range field — мы
        # сохраняем 4 валидных вместо того чтобы отбросить все.
        raw_reels = parsed.get("reels")
        if not isinstance(raw_reels, list):
            log.warning(
                "viral_arc_chunk_missing_reels_array",
                chunk_index=chunk.index,
                keys=list(parsed.keys()),
            )
            return []

        validated_reels: list[_LLMReel] = []
        invalid = 0
        for raw_reel in raw_reels:
            try:
                validated_reels.append(_LLMReel.model_validate(raw_reel))
            except ValidationError as exc:
                invalid += 1
                log.info(
                    "viral_arc_reel_validation_skipped",
                    chunk_index=chunk.index,
                    errors=str(exc)[:200],
                )

        log.info(
            "viral_arc_chunk_done",
            chunk_index=chunk.index,
            reel_count=len(validated_reels),
            invalid_skipped=invalid,
        )
        return validated_reels


# ---------------------------------------------------------------------------
# Cross-chunk dedup (temporal IoU)
# ---------------------------------------------------------------------------


def _reel_coverage(reel: _LLMReel) -> list[tuple[float, float]]:
    """Валидные сегменты рилса как sorted (start, end) tuples."""
    return sorted(
        (s.start, s.end) for s in reel.segments if s.end > s.start
    )


def _temporal_iou(a: _LLMReel, b: _LLMReel) -> float:
    """Intersection-over-union по временному покрытию.

    Сегменты рилса считаются как один union [a.min_start, a.max_end],
    пересечение — union intervals. Возвращает [0..1]; >0.70 — дубликат.
    """
    a_cov = _reel_coverage(a)
    b_cov = _reel_coverage(b)
    if not a_cov or not b_cov:
        return 0.0

    a_dur = sum(e - s for s, e in a_cov)
    b_dur = sum(e - s for s, e in b_cov)
    if a_dur <= 0 or b_dur <= 0:
        return 0.0

    intersection = 0.0
    for a_s, a_e in a_cov:
        for b_s, b_e in b_cov:
            lo = max(a_s, b_s)
            hi = min(a_e, b_e)
            if hi > lo:
                intersection += hi - lo

    union = a_dur + b_dur - intersection
    return intersection / union if union > 0 else 0.0


def _dedupe(reels: list[_LLMReel]) -> list[_LLMReel]:
    """Greedy dedup по viral_score: высший score выигрывает."""
    if not reels:
        return []
    ordered = sorted(reels, key=lambda r: r.viral_score, reverse=True)
    kept: list[_LLMReel] = []
    for candidate in ordered:
        is_dup = any(
            _temporal_iou(candidate, existing) >= _DEDUP_OVERLAP_RATIO
            for existing in kept
        )
        if not is_dup:
            kept.append(candidate)
    return kept


# ---------------------------------------------------------------------------
# LLM output → ReelPlan conversion
# ---------------------------------------------------------------------------


_ROLE_MAP: dict[str, str] = {
    "flashforward_hook": "hook",
    "hook": "hook",
    "context_development": "development",
    "development": "development",
    "payoff_closure": "payoff",
    "payoff": "payoff",
    "peak": "peak",
}


def _safe_reel_id(raw: str, global_idx: int) -> str:
    """Уникальный глобальный id: `v{global_idx}_{sanitized_llm_id}`.

    LLM нумерует рилсы локально в chunk'е (`r1`, `r2`, `r3`) — на multi-chunk
    видео ID коллизят и render overwrite'ит файлы. Префикс ``v{global_idx}_``
    гарантирует уникальность; LLM label сохраняется для читаемости.
    """
    sanitized = re.sub(r"[^A-Za-z0-9_-]", "_", raw).strip("_")[:16] or "r"
    candidate = f"v{global_idx}_{sanitized}"
    if len(candidate) > 32:
        candidate = candidate[:32]
    return candidate


def _to_reel_plan(llm_reel: _LLMReel, fallback_idx: int) -> ReelPlan | None:
    """Нормализация в ReelPlan-формат. None при невалидном содержимом."""
    normalized: list[ReelSegment] = []
    for seg in llm_reel.segments:
        if seg.end - seg.start < _MIN_SEGMENT_DURATION_SEC:
            continue
        order_role = _ROLE_MAP.get(seg.role, "development")
        reasoning = f"viral_2026 {seg.role}: {seg.reason}".strip()[:500]
        normalized.append(
            ReelSegment(
                source_start=round(seg.start, 3),
                source_end=round(seg.end, 3),
                reasoning=reasoning,
                order_role=order_role,  # type: ignore[arg-type]
            )
        )

    if not normalized:
        return None

    duration = sum(s.source_end - s.source_start for s in normalized)
    hook_text = llm_reel.title or llm_reel.save_value or "Без заголовка"

    return ReelPlan(
        reel_id=_safe_reel_id(llm_reel.reel_id, fallback_idx),
        hook=hook_text[:240],
        predicted_duration_sec=round(duration, 2),
        target_audience="",
        segments=normalized,
        composite_score=float(llm_reel.viral_score),
    )


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------


async def build_viral_arcs(
    transcript: TranscriptResult,
    *,
    cfg: Settings | None = None,
) -> list[ReelPlan]:
    """Entry-point для `narrative_mode=viral_2026`.

    Pipeline: chunking → parallel Flash Lite → dedup → ReelPlan list.
    Возвращает рилсы отсортированные по composite_score desc.
    """
    settings = cfg or get_settings()

    chunks = _build_chunks(transcript)
    if not chunks:
        log.warning("viral_arc_empty_transcript")
        return []

    log.info(
        "viral_arc_build_start",
        chunk_count=len(chunks),
        chunk_size_chars=_CHUNK_SIZE_CHARS,
        overlap_chars=_CHUNK_OVERLAP_CHARS,
        total_duration_sec=round(transcript.duration_sec, 1),
    )

    llm = build_llm_for_tier("flash_lite", settings)
    limiter = get_gemini_rate_limiter()
    semaphore = asyncio.Semaphore(_MAX_CONCURRENCY)

    tasks = [
        _score_chunk(
            chunk,
            total_duration_sec=transcript.duration_sec,
            llm=llm,
            limiter=limiter,
            semaphore=semaphore,
        )
        for chunk in chunks
    ]
    per_chunk_results = await asyncio.gather(*tasks, return_exceptions=False)
    all_reels: list[_LLMReel] = [r for chunk_reels in per_chunk_results for r in chunk_reels]

    if not all_reels:
        log.warning("viral_arc_no_reels")
        return []

    deduped = _dedupe(all_reels)
    log.info(
        "viral_arc_dedup_done",
        raw_count=len(all_reels),
        kept=len(deduped),
        rejected=len(all_reels) - len(deduped),
    )

    reel_plans: list[ReelPlan] = []
    for idx, llm_reel in enumerate(deduped):
        plan = _to_reel_plan(llm_reel, idx)
        if plan is not None:
            reel_plans.append(plan)

    reel_plans.sort(key=lambda p: p.composite_score or 0.0, reverse=True)

    log.info(
        "viral_arc_build_complete",
        final_reel_count=len(reel_plans),
        avg_score=(
            round(sum(p.composite_score or 0 for p in reel_plans) / len(reel_plans), 1)
            if reel_plans
            else 0.0
        ),
    )
    return reel_plans
