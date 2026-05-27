"""Chunk Scorer — Phase 8 Map-Reduce pipeline.

Принимает transcript + global_context и параллельно гоняет Gemini Flash Lite
по каждому chunk'у транскрипта, возвращая raw clip candidates. Это MAP
phase. Downstream: temporal/jaccard dedup → clip_reducer (REDUCE phase)
→ boundary_extender → ranker.

Research basis: docs/opusclip-2026-research.md
    - Chunk size 20K chars (runtime-setting) — OpusClip density sweet spot
    - Density-prior 15 clips per chunk (twoOpusClip 30min = 12-18)
    - response_schema enforced (Flash Lite 7x verbosity без него → мусор)
    - Parallel asyncio.gather до narrative_chunk_parallel_max
    - Anti-saturation prompt (не останавливайся на 5 clips)
    - cross_boundary flag для clips на границах chunks

Entry: ``score_chunks(transcript, global_context, *, settings, llm_client=None,
rate_limiter=None, provider_override=None) -> list[RawClipCandidate]``

Graceful degradation:
    - LLM fail on single chunk → empty list for that chunk, остальные продолжают
    - Parse fail → log warning + skip chunk
    - Parallel semaphore защищает от rate limit overflow
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from videomaker.core.config import Settings, get_settings
from videomaker.core.logging import get_logger
from videomaker.services.llm_client import (
    LLMClient,
    LLMError,
    build_llm_for_tier,
    parse_json_response,
)
from videomaker.services.prompts import (
    CHUNK_SCORER_PROMPT,
    build_context_header,
    build_system_prompt,
)
from videomaker.services.rate_limiter import RateLimiter, get_gemini_rate_limiter
from videomaker.services.runtime_settings_store import get_performance_settings
from videomaker.services.transcribers.base import (
    TranscribedSegment,
    TranscriptResult,
    merge_words_into_segments,
)

log = get_logger(__name__)

_HookKind = Literal[
    "question",
    "bold_claim",
    "counter_intuitive",
    "emotional_trigger",
    "pattern_break",
    "stat_shock",
    "story_open",
]
_ClosureType = Literal[
    "conclusion",
    "punchline",
    "revelation",
    "callback",
    "question",
    "emotional",
]

_VALID_HOOK_KINDS: frozenset[str] = frozenset(
    (
        "question",
        "bold_claim",
        "counter_intuitive",
        "emotional_trigger",
        "pattern_break",
        "stat_shock",
        "story_open",
    )
)
_VALID_CLOSURE_TYPES: frozenset[str] = frozenset(
    (
        "conclusion",
        "punchline",
        "revelation",
        "callback",
        "question",
        "emotional",
    )
)


class GlobalContext(BaseModel):
    """Краткий контекст всего видео, передаваемый в каждый chunk scoring call.

    Строится `global_context_builder.py` (Phase 8 Stage 3). Для MVP
    chunk_scorer может принимать минимальный ``GlobalContext(central_theme=...)``
    — полная реализация context builder'а — отдельный stage.
    """

    model_config = ConfigDict(extra="forbid")

    central_theme: str = ""
    key_topics: list[str] = Field(default_factory=list)
    speaker_role: str = ""
    video_structure: str = ""
    language: str = "ru"
    tone: str = ""

    def to_context_block(self) -> str:
        """Human-readable block для injection в prompt."""

        topics_str = ", ".join(self.key_topics[:8]) if self.key_topics else "(не определены)"
        lines = [
            "=== GLOBAL CONTEXT (весь видеоряд) ===",
            f"Central theme: {self.central_theme or '(не определена)'}",
            f"Key topics: {topics_str}",
        ]
        if self.speaker_role:
            lines.append(f"Speaker: {self.speaker_role}")
        if self.video_structure:
            lines.append(f"Structure: {self.video_structure}")
        if self.tone:
            lines.append(f"Tone: {self.tone}")
        lines.append(f"Language: {self.language}")
        return "\n".join(lines)


class RawClipCandidate(BaseModel):
    """Raw output одного clip candidate от chunk_scorer.

    Это не финальный рилс — это input для reducer'а. Валидируется по
    duration bounds и score threshold в `_parse_clip_items`.
    """

    model_config = ConfigDict(extra="forbid")

    chunk_index: int
    start_sec: float = Field(ge=0.0)
    end_sec: float = Field(gt=0.0)
    hook: str = Field(min_length=1, max_length=300)
    payoff: str = Field(max_length=350)
    topic: str = Field(max_length=120)
    score: int = Field(ge=5, le=10)
    hook_kind: _HookKind = "bold_claim"
    closure_type: _ClosureType = "conclusion"
    cross_boundary: bool = False
    why: str = Field(default="", max_length=250)

    def duration_sec(self) -> float:
        return self.end_sec - self.start_sec


@dataclass(slots=True, frozen=True)
class _Chunk:
    """Chunk транскрипта для one LLM call."""

    index: int
    start_sec: float
    end_sec: float
    text_with_timestamps: str
    char_count: int


@dataclass(slots=True, frozen=True)
class ChunkDiagnostic:
    """Per-chunk diagnostics для observability.

    Дампится в artifact (chunk_diagnostics.json) чтобы видеть что именно
    произошло с каждым chunk'ом — сколько raw items вернул LLM, сколько
    прошло validation, были ли exceptions.
    """

    chunk_index: int
    start_sec: float
    end_sec: float
    char_count: int
    raw_items: int
    valid_items: int
    error: str | None
    raw_scores: list[int]

    def to_dict(self) -> dict[str, object]:
        return {
            "chunk_index": self.chunk_index,
            "start_sec": round(self.start_sec, 1),
            "end_sec": round(self.end_sec, 1),
            "char_count": self.char_count,
            "raw_items": self.raw_items,
            "valid_items": self.valid_items,
            "error": self.error,
            "raw_scores": self.raw_scores,
        }


async def score_chunks(
    transcript: TranscriptResult,
    global_context: GlobalContext,
    *,
    settings: Settings | None = None,
    llm_client: LLMClient | None = None,
    rate_limiter: RateLimiter | None = None,
    provider_override: str | None = None,
) -> tuple[list[RawClipCandidate], list[ChunkDiagnostic]]:
    """MAP phase: parallel chunk scoring.

    Возвращает ``(candidates, diagnostics)`` — plain список candidates плюс
    per-chunk diagnostics для observability.
    """

    if transcript.duration_sec <= 0:
        log.warning("chunk_scorer_empty_transcript")
        return [], []

    cfg = settings or get_settings()
    perf = await get_performance_settings(cfg)

    chunk_size = perf.narrative_chunk_size_chars
    overlap = perf.narrative_chunk_overlap_chars
    target_per_chunk = perf.narrative_clips_per_chunk_target
    parallel_max = perf.narrative_chunk_parallel_max

    chunks = _build_chunks(transcript, chunk_size=chunk_size, overlap=overlap)
    if not chunks:
        log.warning("chunk_scorer_no_chunks_built")
        return [], []

    log.info(
        "chunk_scorer_start",
        chunks=len(chunks),
        target_per_chunk=target_per_chunk,
        parallel_max=parallel_max,
        total_duration_sec=round(transcript.duration_sec, 1),
        chunks_bounds=[(round(c.start_sec, 1), round(c.end_sec, 1)) for c in chunks],
    )

    llm = llm_client or build_llm_for_tier(
        "flash_lite", cfg, provider_override=provider_override
    )
    limiter = rate_limiter or get_gemini_rate_limiter()

    # Semaphore защищает от parallel overflow rate limits.
    semaphore = asyncio.Semaphore(parallel_max)

    async def _bounded_score(
        chunk: _Chunk,
    ) -> tuple[list[RawClipCandidate], ChunkDiagnostic]:
        async with semaphore:
            return await _score_single_chunk(
                chunk=chunk,
                global_context=global_context,
                target_per_chunk=target_per_chunk,
                transcript=transcript,
                llm=llm,
                limiter=limiter,
            )

    tasks = [_bounded_score(ch) for ch in chunks]
    per_chunk_results = await asyncio.gather(*tasks, return_exceptions=True)

    all_candidates: list[RawClipCandidate] = []
    diagnostics: list[ChunkDiagnostic] = []
    failed_chunks = 0

    for idx, result in enumerate(per_chunk_results):
        chunk = chunks[idx]
        if isinstance(result, BaseException):
            failed_chunks += 1
            err_str = f"{type(result).__name__}: {result}"
            log.warning(
                "chunk_scorer_chunk_failed",
                chunk_index=idx,
                error=err_str,
            )
            diagnostics.append(
                ChunkDiagnostic(
                    chunk_index=chunk.index,
                    start_sec=chunk.start_sec,
                    end_sec=chunk.end_sec,
                    char_count=chunk.char_count,
                    raw_items=0,
                    valid_items=0,
                    error=err_str,
                    raw_scores=[],
                )
            )
            continue
        candidates, diagnostic = result
        all_candidates.extend(candidates)
        diagnostics.append(diagnostic)

    log.info(
        "chunk_scorer_done",
        chunks=len(chunks),
        raw_candidates=len(all_candidates),
        failed_chunks=failed_chunks,
        avg_per_chunk=round(len(all_candidates) / max(1, len(chunks) - failed_chunks), 1),
        per_chunk_valid=[d.valid_items for d in diagnostics],
        per_chunk_raw=[d.raw_items for d in diagnostics],
    )
    return all_candidates, diagnostics


# ─── Chunk building ──────────────────────────────────────────────────────


#: Максимум chars для одного segment (ASR sanity).
#: Нормальная русская речь даёт segments 50-500 chars. Монстры 5000+ —
#: ASR hallucination (Whisper loop на повторе слога). Truncate.
_MAX_SEGMENT_TEXT_CHARS: int = 1000

#: Если в одном слове >= этого количества chars — это ASR gluing.
#: Нормальные русские слова 2-25 chars. 60+ — merged garbage.
_MAX_WORD_CHARS: int = 60


def _build_chunks(
    transcript: TranscriptResult,
    *,
    chunk_size: int,
    overlap: int,
) -> list[_Chunk]:
    """Разбивает транскрипт на chunks по character count с overlap.

    Формат text_with_timestamps:
        [MM:SS] <segment text>
        [MM:SS] <segment text>
        ...

    Overlap реализован на уровне chars — последние N chars предыдущего chunk'а
    копируются в начало следующего.

    ASR sanity: segments с text > _MAX_SEGMENT_TEXT_CHARS (monster hallucination
    как Whisper loop "КАНВАЛАВАНИДЖАНИДЖ..." × 19K chars в 0.1s) — skip полностью
    с warning log. Иначе один broken segment ломает весь chunking budget.
    """

    segments = _collect_segments(transcript)
    if not segments:
        return []

    # Рендерим полный timestamped текст с ASR sanitization.
    rendered_segments = []
    skipped_asr_hallucinations = 0
    for seg in segments:
        text = (seg.text or "").strip()
        if not text:
            continue
        # ASR hallucination detection: monster segment с огромным text.
        if len(text) > _MAX_SEGMENT_TEXT_CHARS:
            log.warning(
                "chunk_scorer_skip_asr_hallucination_segment",
                start_sec=round(seg.start, 1),
                end_sec=round(seg.end, 1),
                text_chars=len(text),
                text_preview=text[:120],
            )
            skipped_asr_hallucinations += 1
            continue
        # Дополнительная защита: если любое слово в segment'е слишком длинное —
        # тоже ASR gluing. Truncate text до последнего нормального слова.
        if any(len(w) > _MAX_WORD_CHARS for w in text.split()):
            sanitized_words = [w for w in text.split() if len(w) <= _MAX_WORD_CHARS]
            text = " ".join(sanitized_words)
            if not text:
                log.warning(
                    "chunk_scorer_skip_asr_full_glued_segment",
                    start_sec=round(seg.start, 1),
                    end_sec=round(seg.end, 1),
                )
                skipped_asr_hallucinations += 1
                continue
        rendered_segments.append({
            "text": text,
            "start": seg.start,
            "end": seg.end,
            "formatted": f"[{_fmt_ts(seg.start)}] {text}",
        })

    if skipped_asr_hallucinations > 0:
        log.info(
            "chunk_scorer_asr_sanitization_summary",
            skipped_hallucinations=skipped_asr_hallucinations,
            kept_segments=len(rendered_segments),
        )

    if not rendered_segments:
        return []

    # Теперь идём по segments накапливая chunks по char budget.
    chunks: list[_Chunk] = []
    current_segs: list[dict[str, Any]] = []
    current_chars = 0
    chunk_index = 0

    for rs in rendered_segments:
        segment_len = len(rs["formatted"]) + 1  # +1 за newline separator
        if current_chars + segment_len > chunk_size and current_segs:
            # Закрываем текущий chunk.
            chunks.append(_make_chunk(chunk_index, current_segs))
            chunk_index += 1

            # Overlap: берём последние N chars предыдущего chunk'а как начало следующего.
            overlap_segs = _take_overlap_tail(current_segs, overlap)
            current_segs = list(overlap_segs)
            current_chars = sum(len(s["formatted"]) + 1 for s in current_segs)

        current_segs.append(rs)
        current_chars += segment_len

    # Закрываем последний chunk.
    if current_segs:
        chunks.append(_make_chunk(chunk_index, current_segs))

    return chunks


def _take_overlap_tail(
    segments: list[dict[str, Any]],
    overlap_chars: int,
) -> list[dict[str, Any]]:
    """Возвращает последние segments, суммарно покрывающие overlap_chars."""

    if overlap_chars <= 0 or not segments:
        return []

    tail: list[dict[str, Any]] = []
    chars_used = 0
    for seg in reversed(segments):
        seg_len = len(seg["formatted"]) + 1
        if chars_used + seg_len > overlap_chars and tail:
            break
        tail.append(seg)
        chars_used += seg_len
    tail.reverse()
    return tail


def _make_chunk(index: int, segs: list[dict[str, Any]]) -> _Chunk:
    text = "\n".join(s["formatted"] for s in segs)
    return _Chunk(
        index=index,
        start_sec=float(segs[0]["start"]),
        end_sec=float(segs[-1]["end"]),
        text_with_timestamps=text,
        char_count=len(text),
    )


def _collect_segments(transcript: TranscriptResult) -> list[TranscribedSegment]:
    if transcript.segments:
        return list(transcript.segments)
    if transcript.words:
        return merge_words_into_segments(transcript.words)
    return []


# ─── Single chunk scoring ────────────────────────────────────────────────


async def _score_single_chunk(
    *,
    chunk: _Chunk,
    global_context: GlobalContext,
    target_per_chunk: int,
    transcript: TranscriptResult,
    llm: LLMClient,
    limiter: RateLimiter,
) -> tuple[list[RawClipCandidate], ChunkDiagnostic]:
    """Один LLM call на chunk. Возвращает (candidates, diagnostic)."""

    empty_diag = ChunkDiagnostic(
        chunk_index=chunk.index,
        start_sec=chunk.start_sec,
        end_sec=chunk.end_sec,
        char_count=chunk.char_count,
        raw_items=0,
        valid_items=0,
        error=None,
        raw_scores=[],
    )

    context_header = build_context_header(
        source_duration_sec=transcript.duration_sec,
        transcriber=transcript.transcriber,
        llm_model=llm.model,
        language=global_context.language,
    )
    system = f"{build_system_prompt()}\n\n{context_header}\n\n{CHUNK_SCORER_PROMPT}"
    user_payload = _build_user_payload(chunk, global_context, target_per_chunk)

    # IMPORTANT: не передаём response_schema для chunk_scorer.
    # Причина: Gemini FSM-constraint ранним exit'ом array приводит к
    # satisficing (1-2 clips вместо 12-18). Нам нужна verbose generation
    # с потенциально большим output'ом. Парсим через parse_json_response
    # (умеет срезать markdown wrapper). Validation через Pydantic в
    # _parse_clip_items.
    try:
        async with limiter.acquire():
            response = await llm.complete_json(
                system=system,
                user=user_payload,
                temperature=0.5,  # Higher variance = больше candidate diversity.
                max_tokens=16_000,  # Hard ceiling на verbose output.
            )
    except Exception as exc:
        log.warning(
            "chunk_scorer_llm_call_failed",
            chunk_index=chunk.index,
            error=f"{type(exc).__name__}: {exc}",
        )
        return [], ChunkDiagnostic(
            chunk_index=chunk.index,
            start_sec=chunk.start_sec,
            end_sec=chunk.end_sec,
            char_count=chunk.char_count,
            raw_items=0,
            valid_items=0,
            error=f"llm_call_failed: {type(exc).__name__}: {exc}",
            raw_scores=[],
        )

    try:
        parsed = parse_json_response(response.text)
    except LLMError as exc:
        log.warning(
            "chunk_scorer_parse_failed",
            chunk_index=chunk.index,
            error=str(exc),
            response_head=response.text[:300] if response.text else "",
        )
        return [], ChunkDiagnostic(
            chunk_index=chunk.index,
            start_sec=chunk.start_sec,
            end_sec=chunk.end_sec,
            char_count=chunk.char_count,
            raw_items=0,
            valid_items=0,
            error=f"parse_json_failed: {exc}",
            raw_scores=[],
        )

    if not isinstance(parsed, dict):
        log.warning(
            "chunk_scorer_bad_shape",
            chunk_index=chunk.index,
            type=type(parsed).__name__,
        )
        return [], ChunkDiagnostic(
            chunk_index=chunk.index,
            start_sec=chunk.start_sec,
            end_sec=chunk.end_sec,
            char_count=chunk.char_count,
            raw_items=0,
            valid_items=0,
            error=f"bad_shape: {type(parsed).__name__}",
            raw_scores=[],
        )

    raw_clips = parsed.get("clips")
    if not isinstance(raw_clips, list):
        log.warning(
            "chunk_scorer_clips_not_list",
            chunk_index=chunk.index,
            type=type(raw_clips).__name__,
        )
        return [], ChunkDiagnostic(
            chunk_index=chunk.index,
            start_sec=chunk.start_sec,
            end_sec=chunk.end_sec,
            char_count=chunk.char_count,
            raw_items=0,
            valid_items=0,
            error=f"clips_not_list: {type(raw_clips).__name__}",
            raw_scores=[],
        )

    parsed_clips = _parse_clip_items(raw_clips, chunk)
    raw_scores_typed: list[int] = []
    for item in raw_clips:
        if isinstance(item, dict):
            sc = item.get("score")
            if isinstance(sc, (int, float)):
                raw_scores_typed.append(int(sc))
    # Для диагностики: когда valid << raw, логируем первые 2 raw items
    # чтобы видеть LLM output format (timestamps relative vs absolute).
    if len(parsed_clips) < len(raw_clips) // 2 and raw_clips:
        sample_items = [
            {
                "start_sec": x.get("start_sec") if isinstance(x, dict) else None,
                "end_sec": x.get("end_sec") if isinstance(x, dict) else None,
            }
            for x in raw_clips[:3]
        ]
        log.warning(
            "chunk_scorer_high_reject_rate",
            chunk_index=chunk.index,
            raw=len(raw_clips),
            valid=len(parsed_clips),
            chunk_abs_bounds=(round(chunk.start_sec, 1), round(chunk.end_sec, 1)),
            sample_raw_timestamps=sample_items,
        )
    log.info(
        "chunk_scorer_chunk_done",
        chunk_index=chunk.index,
        chunk_start=round(chunk.start_sec, 1),
        chunk_end=round(chunk.end_sec, 1),
        chunk_chars=chunk.char_count,
        raw_items=len(raw_clips),
        valid_items=len(parsed_clips),
        raw_scores=raw_scores_typed,
        target_density=target_per_chunk,
    )
    diagnostic = ChunkDiagnostic(
        chunk_index=chunk.index,
        start_sec=chunk.start_sec,
        end_sec=chunk.end_sec,
        char_count=chunk.char_count,
        raw_items=len(raw_clips),
        valid_items=len(parsed_clips),
        error=None,
        raw_scores=raw_scores_typed,
    )
    # empty_diag был подготовлен для раннего возврата — не нужен здесь.
    _ = empty_diag
    return parsed_clips, diagnostic


def _build_user_payload(
    chunk: _Chunk,
    global_context: GlobalContext,
    target_per_chunk: int,
) -> str:
    """Собирает user-prompt с global context + chunk text + density prior."""

    # Минимум clips: 1 на 1.5 минуты контента (проксирует OpusClip density).
    duration_min = (chunk.end_sec - chunk.start_sec) / 60.0
    min_expected = max(3, round(duration_min / 1.5))
    # Верхняя граница poshire чем density_prior (не ограничивай):
    upper_hint = max(target_per_chunk + 5, min_expected + 5)

    parts = [
        global_context.to_context_block(),
        "",
        "=== CHUNK ДЛЯ СКАНА ===",
        f"Index: {chunk.index + 1}",
        f"Временной диапазон: {_fmt_ts(chunk.start_sec)} – {_fmt_ts(chunk.end_sec)} "
        f"(~{duration_min:.1f} мин контента)",
        f"Длина: {chunk.char_count} символов",
        "",
        "=== КРИТИЧНО — ФОРМАТ TIMESTAMP'ов ===",
        (
            f"Timestamps в транскрипте ([MM:SS]) — **АБСОЛЮТНЫЕ** секунды "
            f"от начала всего видео. Этот chunk охватывает диапазон "
            f"{chunk.start_sec:.1f} – {chunk.end_sec:.1f} секунд (абсолютно). "
            f"Когда ты возвращаешь clip'ы, start_sec и end_sec ДОЛЖНЫ быть "
            f"абсолютные seconds в диапазоне [{chunk.start_sec:.0f}, "
            f"{chunk.end_sec:.0f}]. НЕ возвращай timestamps от начала chunk'а."
        ),
        "",
        "=== КРИТИЧНО — ДЛИТЕЛЬНОСТЬ CLIP'ОВ ===",
        (
            "Каждый clip = минимум 28 секунд, максимум 75 секунд. "
            "**Clips короче 28 секунд — АВТОМАТИЧЕСКИ ОТБРАСЫВАЮТСЯ моим кодом.** "
            "Если видишь hook фразу 3-5 секунд — НЕ возвращай клип 3-5 секунд! "
            "Расширь окно: включи 2-3 предложения контекста ДО hook'а И 3-5 "
            "предложений development + payoff ПОСЛЕ. Целевая длина 40-55 секунд."
        ),
        (
            "Правильно: hook 5s + development 20s + payoff 15s = 40s клип. "
            "Неправильно: hook 5s + punchline 5s = 10s клип (БУДЕТ REJECTED)."
        ),
        "",
        "=== ВАЖНО: ОЖИДАНИЕ ПО КОЛИЧЕСТВУ ===",
        f"**МИНИМУМ {min_expected} clips** ожидаются в этом chunk'е (density "
        f"1 clip / 1.5 мин контента). Target {target_per_chunk}. Верхняя "
        f"граница не фиксирована — если видишь {upper_hint}+ моментов, "
        f"возвращай все.",
        "",
        (
            f"Если ты вернёшь 1-2 clips когда в chunk'е {min_expected}+ "
            "hook-моментов — это FAILURE моего downstream pipeline'а. "
            "Lo-score clips (5, 6) отдавай тоже — reducer их отсеет. "
            "Твоя работа — максимальная recall, не precision."
        ),
        "",
        "=== TRANSCRIPT CHUNK ===",
        chunk.text_with_timestamps,
        "",
        "=== ЗАДАЧА ===",
        (
            f"Верни {{\"clips\": [...]}} с МИНИМУМ {min_expected} clips "
            "(обычно больше). Не markdown, pure JSON. Каждый clip: "
            "start_sec, end_sec, hook, payoff, topic, score (5-10), "
            "hook_kind, closure_type, cross_boundary, why. Timestamps — "
            "float с одной десятой секунды."
        ),
    ]
    return "\n".join(parts)


# ─── Parsing + validation ────────────────────────────────────────────────


def _parse_clip_items(
    raw_items: list[Any],
    chunk: _Chunk,
) -> list[RawClipCandidate]:
    """Распарсивает raw LLM output в RawClipCandidate. Невалидные — skip."""

    candidates: list[RawClipCandidate] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        try:
            candidate = _parse_single_clip(item, chunk)
        except (ValueError, TypeError) as exc:
            log.debug(
                "chunk_scorer_parse_item_failed",
                chunk_index=chunk.index,
                error=str(exc),
            )
            continue
        if candidate is None:
            continue
        candidates.append(candidate)
    return candidates


def _parse_single_clip(
    item: dict[str, Any],
    chunk: _Chunk,
) -> RawClipCandidate | None:
    """Строит RawClipCandidate из LLM dict. None если не проходит sanity.

    Relative→absolute timestamp auto-conversion:
        Некоторые LLM возвращают timestamps относительно chunk'а (0-chunk_dur),
        не абсолютные seconds. Detect: если ОБА timestamps < chunk.start_sec
        (т.е. явно не могут быть абсолютными в этом chunk'е), интерпретируем
        как relative и конвертим: absolute = relative + chunk.start_sec.
    """

    start_raw = item.get("start_sec")
    end_raw = item.get("end_sec")
    if not isinstance(start_raw, (int, float)):
        return None
    if not isinstance(end_raw, (int, float)):
        return None

    start_sec = float(start_raw)
    end_sec = float(end_raw)

    # Detect relative timestamps: both ниже chunk.start_sec → LLM думает chunk-relative.
    # Работает для chunks != 0 (chunk 0 has start_sec=0 поэтому trick не нужен).
    chunk_duration = chunk.end_sec - chunk.start_sec
    if chunk.start_sec > 1.0 and end_sec < chunk.start_sec and end_sec <= chunk_duration + 5.0:
        # Relative interpretation: shift на chunk.start_sec.
        start_sec += chunk.start_sec
        end_sec += chunk.start_sec

    # Clamp к границам chunk'а (с учётом slack для overlap zones).
    slack = 3.0
    start_sec = max(max(0.0, chunk.start_sec - slack), start_sec)
    end_sec = min(chunk.end_sec + slack, end_sec)

    if end_sec <= start_sec:
        return None

    duration = end_sec - start_sec
    # Hard enforcement REEL_MIN / REEL_MAX из constants.
    # 28s нижний bound — render stage (`min_reel_duration_sec=31`) отсечёт
    # всё короче. 75s верхний — платформа completion rate падает.
    # Если LLM даёт короткий clip, попытка расширить через sentence-end
    # lookahead — работа boundary_extender (downstream), но чтобы он имел
    # с чем работать, нужен хотя бы минимальный clip.
    if duration < 28.0 or duration > 90.0:
        return None

    hook = str(item.get("hook") or "").strip()
    if not hook:
        return None
    hook = hook[:300]

    payoff = str(item.get("payoff") or "").strip()[:350]
    topic = str(item.get("topic") or "").strip()[:120]

    score_raw = item.get("score", 0)
    if isinstance(score_raw, float):
        score = int(score_raw)
    elif isinstance(score_raw, int):
        score = score_raw
    else:
        try:
            score = int(str(score_raw))
        except (ValueError, TypeError):
            return None
    score = max(5, min(10, score))
    if score < 5:
        return None

    hook_kind_raw = str(item.get("hook_kind") or "bold_claim").strip().lower()
    hook_kind: _HookKind = (
        _coerce_hook_kind(hook_kind_raw) if hook_kind_raw in _VALID_HOOK_KINDS else "bold_claim"
    )

    closure_type_raw = str(item.get("closure_type") or "conclusion").strip().lower()
    closure_type: _ClosureType = (
        _coerce_closure_type(closure_type_raw)
        if closure_type_raw in _VALID_CLOSURE_TYPES
        else "conclusion"
    )

    cross_boundary_raw = item.get("cross_boundary", False)
    cross_boundary = bool(cross_boundary_raw) if isinstance(cross_boundary_raw, bool) else False

    why = str(item.get("why") or "").strip()[:250]

    return RawClipCandidate(
        chunk_index=chunk.index,
        start_sec=start_sec,
        end_sec=end_sec,
        hook=hook,
        payoff=payoff,
        topic=topic,
        score=score,
        hook_kind=hook_kind,
        closure_type=closure_type,
        cross_boundary=cross_boundary,
        why=why,
    )


# ─── Coercion helpers ─────────────────────────────────────────────────────


def _coerce_hook_kind(value: str) -> _HookKind:
    mapping: dict[str, _HookKind] = {
        "question": "question",
        "bold_claim": "bold_claim",
        "counter_intuitive": "counter_intuitive",
        "emotional_trigger": "emotional_trigger",
        "pattern_break": "pattern_break",
        "stat_shock": "stat_shock",
        "story_open": "story_open",
    }
    return mapping.get(value, "bold_claim")


def _coerce_closure_type(value: str) -> _ClosureType:
    mapping: dict[str, _ClosureType] = {
        "conclusion": "conclusion",
        "punchline": "punchline",
        "revelation": "revelation",
        "callback": "callback",
        "question": "question",
        "emotional": "emotional",
    }
    return mapping.get(value, "conclusion")


def _fmt_ts(sec: float) -> str:
    total = max(0, int(sec))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


__all__ = [
    "GlobalContext",
    "RawClipCandidate",
    "score_chunks",
]
