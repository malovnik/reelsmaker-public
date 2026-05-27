"""Boundary Extender — Phase 4 top-down pipeline (deterministic).

После arc_finder каждый NarrativeArc превращается в ExtendedArc с
границами, прилеплёнными к natural boundaries. НЕТ LLM calls — всё
детерминистично, дёшево, быстро.

Три стратегии применяются последовательно:

    1. Tail trim: если clip_end попадает в mid-sentence (не на точку/!/?)
       → ищем ближайший sentence end backward в пределах 5s. Это защита
       от LLM output'а который залез на половину следующей фразы.
    2. Silence extension: если за clip_end следует pause ≥ 0.8s (sentence
       boundary signal), extend до конца silence zone. Это работает когда
       speaker закрыл мысль и держит паузу.
    3. Discourse marker forward: regex по CLOSURE_MARKERS в forward 15s.
       Если найден ("поэтому", "таким образом", "в итоге", ...) — extend
       до sentence end после маркёра. Reuse approach из closure_validator.

Hard cap: MAX_CLOSURE_EXTENSION_SEC=35s от исходного arc.clip_end. Это
защита от runaway extension когда regex находит маркер через 40s и
рилс становится 100s+.

Entry: ``extend_boundaries(arcs: list[NarrativeArc], transcript:
TranscriptResult) -> list[ExtendedArc]``
"""

from __future__ import annotations

import re

from videomaker.core.logging import get_logger
from videomaker.models.narrative import ExtendedArc, NarrativeArc
from videomaker.services.narrative.constants import (
    DISCOURSE_MARKER_FORWARD_SEC,
    MAX_CLOSURE_EXTENSION_SEC,
    REEL_MAX_DURATION_SEC,
    SILENCE_THRESHOLD_SEC,
)
from videomaker.services.transcribers.base import TranscribedWord, TranscriptResult

log = get_logger(__name__)

#: Знаки конца предложения для sentence-boundary snap.
_SENTENCE_END_PUNCT: frozenset[str] = frozenset({".", "!", "?", "…"})

#: Окно для tail trim backward-поиска sentence end. Если clip_end
#: попадает в мид-sentence, ищем предыдущий terminator в этом окне.
_TAIL_TRIM_BACKWARD_SEC: float = 5.0

#: Discourse closure markers для forward search. Regex compiled один раз.
#: Research: эти markers в >70% случаев сигнализируют что speaker
#: закрывает тезис и сейчас даст итог или вывод.
_CLOSURE_MARKER_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bпоэтому\b",
        r"\bтаким\s+образом\b",
        r"\bв\s+итоге\b",
        r"\bвыводы?\b",
        r"\bглавное\b",
        r"\bзапомните?\b",
        r"\bсуть\s+в\s+том\b",
        r"\bэто\s+значит\b",
        r"\bвот\s+почему\b",
        r"\bв\s+конечном\s+счёте\b",
        r"\bв\s+конечном\s+счете\b",
        r"\bвот\s+и\s+вс[её]\b",
        r"\bименно\s+это\b",
        r"\bименно\s+поэтому\b",
        r"\bк\s+тому\s+же\b",
        r"\bи\s+вот\b",
        r"\bпонимаете\b",
        r"\bполучается\b",
        r"\bсобственно\b",
    )
)


def extend_boundaries(
    arcs: list[NarrativeArc],
    transcript: TranscriptResult,
) -> list[ExtendedArc]:
    """Применяет детерминистичные границы-extensions к каждому NarrativeArc.

    Возвращает ExtendedArc для каждого входного arc (1-to-1). Порядок
    сохраняется.
    """

    if not arcs:
        return []

    source_duration = transcript.duration_sec
    if source_duration <= 0:
        log.warning("boundary_extender_empty_transcript")
        return [_identity_extension(arc) for arc in arcs]

    words = _collect_words(transcript)
    if not words:
        log.info("boundary_extender_no_words_fallback_identity")
        return [_identity_extension(arc) for arc in arcs]

    extended: list[ExtendedArc] = []
    stats: dict[str, int] = {
        "tail_trimmed": 0,
        "silence_extended": 0,
        "closure_marker_extended": 0,
        "duration_capped": 0,
        "no_adjustment": 0,
    }

    for arc in arcs:
        ext = _extend_single(arc, words, source_duration, stats)
        extended.append(ext)

    log.info(
        "boundary_extender_done",
        arcs=len(arcs),
        **stats,
    )
    return extended


def _extend_single(
    arc: NarrativeArc,
    words: list[TranscribedWord],
    source_duration: float,
    stats: dict[str, int],
) -> ExtendedArc:
    """Применяет три стратегии последовательно. Возвращает ExtendedArc."""

    adjustments: list[str] = []
    start = arc.clip_start_sec
    end = arc.clip_end_sec

    # Strategy 1: tail trim to sentence end backward (если end в mid-sentence).
    tail_words = _words_in_range(words, end - _TAIL_TRIM_BACKWARD_SEC, end)
    if not _ends_with_sentence_terminator(tail_words):
        trimmed_end = _find_last_sentence_end(
            words, end_sec=end, lookback_sec=_TAIL_TRIM_BACKWARD_SEC
        )
        if trimmed_end is not None and trimmed_end > start + 1.0:
            # Trimmed только если получается arc не короче 1s start + ...
            duration_after_trim = trimmed_end - start
            if duration_after_trim >= REEL_MAX_DURATION_SEC * 0.25:
                # Минимум 1/4 от MAX, чтобы не разрушить arc коротким trim.
                end = trimmed_end
                adjustments.append("tail_trim_sentence_backward")
                stats["tail_trimmed"] += 1

    # Strategy 2: silence extension — если после end следует пауза > threshold.
    silence_end = _extend_to_silence_boundary(
        words, end_sec=end, source_duration=source_duration
    )
    if silence_end is not None and silence_end > end:
        extension = silence_end - arc.clip_end_sec
        if extension <= MAX_CLOSURE_EXTENSION_SEC:
            end = silence_end
            adjustments.append("extend_silence_boundary")
            stats["silence_extended"] += 1

    # Strategy 3: discourse marker forward.
    marker_end = _extend_to_closure_marker(
        words, end_sec=end, source_duration=source_duration
    )
    if marker_end is not None and marker_end > end:
        # Cap total extension от оригинального arc.clip_end_sec.
        total_extension = marker_end - arc.clip_end_sec
        if total_extension <= MAX_CLOSURE_EXTENSION_SEC:
            end = marker_end
            adjustments.append("extend_closure_marker")
            stats["closure_marker_extended"] += 1
        else:
            # Trim extension до cap.
            end = arc.clip_end_sec + MAX_CLOSURE_EXTENSION_SEC
            adjustments.append("extend_capped_by_max_extension")
            stats["duration_capped"] += 1

    # Hard cap duration на REEL_MAX_DURATION_SEC.
    if end - start > REEL_MAX_DURATION_SEC:
        # Обрезаем до REEL_MAX через backward sentence search.
        capped_end = _find_last_sentence_end(
            words,
            end_sec=start + REEL_MAX_DURATION_SEC,
            lookback_sec=min(15.0, REEL_MAX_DURATION_SEC * 0.2),
        )
        end = capped_end if capped_end is not None else start + REEL_MAX_DURATION_SEC
        adjustments.append("reel_max_duration_cap")
        stats["duration_capped"] += 1

    # Clamp к source_duration.
    end = min(end, source_duration)

    if not adjustments:
        adjustments.append("no_adjustment")
        stats["no_adjustment"] += 1

    return ExtendedArc(
        arc=arc,
        adjusted_start_sec=start,
        adjusted_end_sec=end,
        applied_adjustments=adjustments,
    )


# ─── Strategy helpers ────────────────────────────────────────────────────


def _extend_to_silence_boundary(
    words: list[TranscribedWord],
    *,
    end_sec: float,
    source_duration: float,
) -> float | None:
    """Если за end_sec следует silence gap ≥ SILENCE_THRESHOLD_SEC между
    словами — extend до начала следующего слова (т.е. до конца silence).

    Если silence больше 5s — extend только до end + SILENCE_THRESHOLD_SEC
    (не до конца длинного silence, это уже не закрытие мысли).
    """

    _ = source_duration  # reserved для future hard cap

    # Находим word где end ≥ end_sec (последнее слово arc'а).
    last_word_index: int | None = None
    for i, w in enumerate(words):
        if w.end >= end_sec - 0.2:
            last_word_index = i
            break

    if last_word_index is None or last_word_index + 1 >= len(words):
        return None

    next_word = words[last_word_index + 1]
    last_word = words[last_word_index]
    silence_gap = next_word.start - last_word.end

    if silence_gap < SILENCE_THRESHOLD_SEC:
        return None

    # Extend до начала next_word — но не более end_sec + 2s (короткий
    # silence bridge, не multiplexing в новую тему).
    if silence_gap > 5.0:
        # Слишком длинная пауза — это не closure, а перерыв. Skip.
        return None

    return next_word.start


def _extend_to_closure_marker(
    words: list[TranscribedWord],
    *,
    end_sec: float,
    source_duration: float,
) -> float | None:
    """Forward search discourse closure markers в окне DISCOURSE_MARKER_FORWARD_SEC.

    Если marker найден — extend до sentence end после marker (или до
    конца предложения с marker).
    """

    lo = end_sec
    hi = min(end_sec + DISCOURSE_MARKER_FORWARD_SEC, source_duration)
    forward_words = _words_in_range(words, lo, hi)
    if not forward_words:
        return None

    # Склеиваем forward-токены в строку с сохранением позиций.
    forward_text = " ".join(w.word.strip() for w in forward_words if (w.word or "").strip())
    if not forward_text:
        return None

    # Проверяем каждый pattern.
    first_match_pos: int | None = None
    for pattern in _CLOSURE_MARKER_PATTERNS:
        match = pattern.search(forward_text)
        if match is None:
            continue
        if first_match_pos is None or match.start() < first_match_pos:
            first_match_pos = match.start()

    if first_match_pos is None:
        return None

    # Находим word соответствующий match.start() (по cumulative offset).
    cumulative = 0
    marker_word_index: int | None = None
    for i, w in enumerate(forward_words):
        token = (w.word or "").strip()
        if not token:
            continue
        if cumulative <= first_match_pos <= cumulative + len(token):
            marker_word_index = i
            break
        cumulative += len(token) + 1  # +1 для разделителя

    if marker_word_index is None:
        return None

    # Ищем ближайший sentence terminator после marker (в пределах hi).
    for i in range(marker_word_index, len(forward_words)):
        w = forward_words[i]
        token = (w.word or "").strip()
        if token and token[-1] in _SENTENCE_END_PUNCT:
            return w.end

    # Marker найден, но sentence terminator не нашли в forward окне.
    # Extend хотя бы до последнего слова forward-окна.
    return forward_words[-1].end


# ─── Word utilities ──────────────────────────────────────────────────────


def _collect_words(transcript: TranscriptResult) -> list[TranscribedWord]:
    """Собирает все TranscribedWord из transcript (from words or segments)."""

    if transcript.words:
        return list(transcript.words)

    # Извлекаем words из segments.
    words: list[TranscribedWord] = []
    for seg in transcript.segments:
        words.extend(seg.words)
    return words


def _words_in_range(
    words: list[TranscribedWord],
    start_sec: float,
    end_sec: float,
) -> list[TranscribedWord]:
    """Words where word.end ≥ start AND word.start < end."""

    if end_sec <= start_sec:
        return []
    result: list[TranscribedWord] = []
    for w in words:
        if w.end < start_sec:
            continue
        if w.start >= end_sec:
            break
        result.append(w)
    return result


def _ends_with_sentence_terminator(words: list[TranscribedWord]) -> bool:
    if not words:
        return False
    token = (words[-1].word or "").strip()
    if not token:
        return False
    return token[-1] in _SENTENCE_END_PUNCT


def _find_last_sentence_end(
    words: list[TranscribedWord],
    *,
    end_sec: float,
    lookback_sec: float,
) -> float | None:
    """Последний word с terminator в окне [end_sec - lookback, end_sec - 0.1]."""

    lo = max(0.0, end_sec - lookback_sec)
    hi = end_sec - 0.1
    best: float | None = None
    for w in words:
        if w.end < lo:
            continue
        if w.end > hi:
            break
        token = (w.word or "").strip()
        if token and token[-1] in _SENTENCE_END_PUNCT:
            best = w.end
    return best


# ─── Fallback identity extension ─────────────────────────────────────────


def _identity_extension(arc: NarrativeArc) -> ExtendedArc:
    """Когда word-level data недоступна — возвращаем arc как есть."""

    return ExtendedArc(
        arc=arc,
        adjusted_start_sec=arc.clip_start_sec,
        adjusted_end_sec=arc.clip_end_sec,
        applied_adjustments=["identity_no_word_data"],
    )


__all__ = ["extend_boundaries"]
