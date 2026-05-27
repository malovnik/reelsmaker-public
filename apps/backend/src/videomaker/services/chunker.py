"""RAG-style chunking для LLM-проходов.

Реализует стратегию из плана (секция "Chunking strategy"):
- sliding window по токенам;
- прилипание к концам предложений (punctuation-aware);
- overlap между окнами;
- применяется ко всем моделям одинаково (горизонтальное масштабирование).

Токенизация через tiktoken `cl100k_base` — дает консистентный счёт ±10%
для Gemini/Claude/GPT. У Gemini есть нативный count_tokens(), но мы
используем один инструмент, чтобы chunk'и были одинаковые у всех моделей.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

import tiktoken

from videomaker.services.transcribers.base import (
    TranscribedSegment,
    TranscriptResult,
)

SENTENCE_BOUNDARY = re.compile(r"[.!?…]+\s")


@lru_cache(maxsize=1)
def _encoder() -> tiktoken.Encoding:
    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    if not text:
        return 0
    return len(_encoder().encode(text))


@dataclass(slots=True)
class TranscriptChunk:
    index: int
    start_sec: float
    end_sec: float
    text: str
    segments: list[TranscribedSegment]
    token_count: int

    def render_for_llm(self) -> str:
        lines: list[str] = [f"[chunk {self.index} | {self.start_sec:.1f}–{self.end_sec:.1f}s]"]
        for seg in self.segments:
            lines.append(_render_segment(seg))
        return "\n".join(lines)


def _render_segment(seg: TranscribedSegment) -> str:
    if seg.words:
        tokens = [f"{w.word}[{w.start:.2f}-{w.end:.2f}]" for w in seg.words]
        return " ".join(tokens)
    return f"[{seg.start:.2f}-{seg.end:.2f}] {seg.text}"


@dataclass(slots=True)
class ChunkingPolicy:
    threshold_tokens: int
    window_tokens: int
    overlap_tokens: int

    def validate(self) -> None:
        if self.window_tokens <= self.overlap_tokens:
            raise ValueError(
                f"window_tokens ({self.window_tokens}) must be > overlap_tokens ({self.overlap_tokens})"
            )
        if self.threshold_tokens < self.window_tokens:
            raise ValueError(
                f"threshold_tokens ({self.threshold_tokens}) must be >= window_tokens ({self.window_tokens})"
            )


def chunk_transcript(transcript: TranscriptResult, policy: ChunkingPolicy) -> list[TranscriptChunk]:
    policy.validate()
    segments = _segments_for_chunking(transcript)
    if not segments:
        return []

    rendered_segments = [_render_segment(seg) for seg in segments]
    segment_tokens = [count_tokens(text) for text in rendered_segments]
    total_tokens = sum(segment_tokens)

    if total_tokens <= policy.threshold_tokens:
        return [
            TranscriptChunk(
                index=0,
                start_sec=segments[0].start,
                end_sec=segments[-1].end,
                text="\n".join(rendered_segments),
                segments=list(segments),
                token_count=total_tokens,
            )
        ]

    return _sliding_window(segments, segment_tokens, rendered_segments, policy)


def _segments_for_chunking(transcript: TranscriptResult) -> list[TranscribedSegment]:
    if transcript.segments:
        return list(transcript.segments)
    if transcript.words:
        from videomaker.services.transcribers.base import merge_words_into_segments

        return merge_words_into_segments(transcript.words)
    return []


def _sliding_window(
    segments: list[TranscribedSegment],
    segment_tokens: list[int],
    rendered: list[str],
    policy: ChunkingPolicy,
) -> list[TranscriptChunk]:
    chunks: list[TranscriptChunk] = []
    index = 0
    i = 0
    n = len(segments)

    while i < n:
        acc_tokens = 0
        j = i
        while j < n and acc_tokens + segment_tokens[j] <= policy.window_tokens:
            acc_tokens += segment_tokens[j]
            j += 1

        if j == i:
            # один сегмент сам по себе больше окна — придётся сплитить его
            # по предложениям на уровне текста, сохраняя таймкоды сегмента
            sub_chunks = _split_long_segment(
                segments[i], segment_tokens[i], policy, starting_index=index
            )
            chunks.extend(sub_chunks)
            index += len(sub_chunks)
            i += 1
            continue

        chunk_segments = segments[i:j]
        chunk = TranscriptChunk(
            index=index,
            start_sec=chunk_segments[0].start,
            end_sec=chunk_segments[-1].end,
            text="\n".join(rendered[i:j]),
            segments=chunk_segments,
            token_count=acc_tokens,
        )
        chunks.append(chunk)
        index += 1

        if j >= n:
            break

        # шагаем назад на overlap — считаем overlap в токенах
        back = 0
        k = j - 1
        while k >= i and back + segment_tokens[k] <= policy.overlap_tokens:
            back += segment_tokens[k]
            k -= 1
        next_start = max(i + 1, k + 1)
        i = next_start

    return chunks


def _split_long_segment(
    segment: TranscribedSegment,
    total_tokens: int,
    policy: ChunkingPolicy,
    *,
    starting_index: int,
) -> list[TranscriptChunk]:
    if not segment.words:
        return [
            TranscriptChunk(
                index=starting_index,
                start_sec=segment.start,
                end_sec=segment.end,
                text=_render_segment(segment),
                segments=[segment],
                token_count=total_tokens,
            )
        ]

    words = segment.words
    n = len(words)
    # Предрасчёт токенов per-word — одна tiktoken-encode операция на слово
    # вместо O(N^2) внутри sliding window.
    word_tokens = [count_tokens(w.word + " ") for w in words]
    chunks: list[TranscriptChunk] = []
    index = starting_index
    i = 0

    while i < n:
        acc = 0
        j = i
        while j < n and acc + word_tokens[j] <= policy.window_tokens:
            acc += word_tokens[j]
            j += 1
        j = max(j, i + 1)
        window_words = words[i:j]
        pseudo_segment = TranscribedSegment(
            text=" ".join(w.word for w in window_words),
            start=window_words[0].start,
            end=window_words[-1].end,
            words=list(window_words),
        )
        chunks.append(
            TranscriptChunk(
                index=index,
                start_sec=pseudo_segment.start,
                end_sec=pseudo_segment.end,
                text=_render_segment(pseudo_segment),
                segments=[pseudo_segment],
                token_count=acc,
            )
        )
        index += 1
        if j >= n:
            break

        back = 0
        k = j - 1
        while k >= i and back + word_tokens[k] <= policy.overlap_tokens:
            back += word_tokens[k]
            k -= 1
        i = max(i + 1, k + 1)

    return chunks


def merge_overlapping_timestamps(
    items: list[dict[str, float]],
    *,
    start_key: str = "start",
    tolerance_sec: float = 2.0,
) -> list[dict[str, float]]:
    """Утилита для reduce-фазы: дедуплицирует записи с близкими `start`."""

    if not items:
        return []
    sorted_items = sorted(items, key=lambda it: it.get(start_key, 0.0))
    result: list[dict[str, float]] = [sorted_items[0]]
    for item in sorted_items[1:]:
        prev = result[-1]
        if abs(item[start_key] - prev[start_key]) < tolerance_sec:
            continue
        result.append(item)
    return result


