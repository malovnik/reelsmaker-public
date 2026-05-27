"""TIER2-#11: Semantic boundary chunking.

Вместо нарезки транскрипта по токенам (sliding window), ищем смысловые
границы через эмбеддинги сегментов и cosine-similarity. Chapter-Llama
(CVPR 2025) показывает +8-12% boundary F1 по сравнению с fixed-window.

Алгоритм:

1. Получаем сегменты транскрипта (как в ``chunker._segments_for_chunking``).
2. Эмбеддим текст каждого сегмента через Gemini ``text-embedding-004``
   (output_dimensionality=256 — хватает для топиковой близости, быстро).
3. Считаем cosine similarity(seg[i], seg[i+1]) для всех i.
4. Ищем "провалы" в similarity: значения ниже ``similarity_threshold``.
   Они — кандидаты на смысловые границы.
5. Проходим по сегментам слева направо, накапливаем длительность в
   текущем chunk'е. Когда длительность ≥ ``min_duration_sec``:
   - если впереди ≤ ``target_duration_sec`` будет граница-кандидат →
     закрываем chunk на ней;
   - иначе если длительность ≥ ``target_duration_sec * 1.5`` → закрываем
     принудительно (чтоб не уходить в гигантский chunk).
6. Возвращаем ``list[TranscriptChunk]`` в формате совместимом с
   существующим LLM-пайплайном.

Fallback: если embed-вызов падает (API недоступен, квоты) — возвращаем
результат ``chunk_transcript`` по исходной token-based политике. Это
гарантирует что включение semantic chunking никогда не ломает пайплайн.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from videomaker.core.config import Settings
from videomaker.core.logging import get_logger
from videomaker.services.chunker import (
    ChunkingPolicy,
    TranscriptChunk,
    _render_segment,
    chunk_transcript,
    count_tokens,
)
from videomaker.services.transcribers.base import (
    TranscribedSegment,
    TranscriptResult,
)

log = get_logger(__name__)


@dataclass(slots=True)
class SemanticChunkingPolicy:
    """Параметры семантической нарезки (задаются из runtime_settings)."""

    target_duration_sec: int
    min_duration_sec: int
    similarity_threshold: float
    fallback_policy: ChunkingPolicy


async def semantic_chunk_transcript(
    transcript: TranscriptResult,
    policy: SemanticChunkingPolicy,
    *,
    settings: Settings,
) -> list[TranscriptChunk]:
    """Семантическая нарезка транскрипта с fallback на токен-based.

    Возвращает тот же тип ``list[TranscriptChunk]`` что и классический
    ``chunk_transcript`` — consumer (pipeline) ничего не знает о разнице.
    """

    segments = _get_segments(transcript)
    if len(segments) < 3:
        # Слишком мало сегментов для детекции границ — сразу fallback.
        return chunk_transcript(transcript, policy.fallback_policy)

    try:
        embeddings = await _embed_segments(segments, settings=settings)
    except Exception as exc:
        log.warning("semantic_chunker_embed_failed_fallback", error=str(exc))
        return chunk_transcript(transcript, policy.fallback_policy)

    if not embeddings or len(embeddings) != len(segments):
        log.warning(
            "semantic_chunker_embed_length_mismatch_fallback",
            expected=len(segments),
            got=len(embeddings) if embeddings else 0,
        )
        return chunk_transcript(transcript, policy.fallback_policy)

    similarities = _compute_adjacent_similarities(embeddings)
    boundaries = _select_boundaries(
        segments,
        similarities,
        policy=policy,
    )
    chunks = _build_chunks(segments, boundaries)

    log.info(
        "semantic_chunker_done",
        segment_count=len(segments),
        boundary_count=len(boundaries),
        chunk_count=len(chunks),
        avg_sim=round(sum(similarities) / max(1, len(similarities)), 3),
    )
    return chunks


def _get_segments(transcript: TranscriptResult) -> list[TranscribedSegment]:
    if transcript.segments:
        return list(transcript.segments)
    if transcript.words:
        from videomaker.services.transcribers.base import merge_words_into_segments

        return merge_words_into_segments(transcript.words)
    return []


async def _embed_segments(
    segments: list[TranscribedSegment],
    *,
    settings: Settings,
) -> list[list[float]]:
    """Эмбеддит текст каждого сегмента. Gemini batch API — ≤100 контентов
    за вызов, поэтому крупные транскрипты режутся на батчи."""

    from google import genai
    from google.genai import types as genai_types

    if not settings.gemini_api_key:
        raise RuntimeError("gemini_api_key not set — cannot use semantic chunking")

    texts = [(seg.text or "").strip() for seg in segments]
    # Пустые сегменты получат нулевые векторы — границы через них не отличат.
    safe_texts = [t if t else "(silence)" for t in texts]

    client = genai.Client(api_key=settings.gemini_api_key)
    # `gemini-embedding-001` — актуальная production-модель Gemini Embeddings
    # (v1beta `text-embedding-004` возвращает 404 на новых API-ключах).
    # Размерность нативная 3072, клампим до 256 для скорости cosine-расчёта.
    model_id = "gemini-embedding-001"

    all_values: list[list[float]] = []
    batch_size = 90
    for start in range(0, len(safe_texts), batch_size):
        batch: list[str | genai_types.PIL_Image | genai_types.File | genai_types.Part] = list(
            safe_texts[start : start + batch_size]
        )
        resp = await client.aio.models.embed_content(
            model=model_id,
            contents=batch,
            config=genai_types.EmbedContentConfig(output_dimensionality=256),
        )
        embeds = resp.embeddings or []
        for e in embeds:
            all_values.append(list(e.values or []))
    return all_values


def _compute_adjacent_similarities(embeddings: list[list[float]]) -> list[float]:
    """Cosine similarity между каждой парой соседних эмбеддингов."""

    sims: list[float] = []
    for i in range(len(embeddings) - 1):
        a = embeddings[i]
        b = embeddings[i + 1]
        sims.append(_cosine(a, b))
    return sims


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 1.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b, strict=True):
        dot += x * y
        na += x * x
        nb += y * y
    denom = math.sqrt(na) * math.sqrt(nb)
    if denom <= 1e-9:
        return 1.0
    return dot / denom


def _select_boundaries(
    segments: list[TranscribedSegment],
    similarities: list[float],
    *,
    policy: SemanticChunkingPolicy,
) -> list[int]:
    """Отбирает индексы сегментов, после которых нужно делать границу chunk'а.

    Критерии:
      * similarity[i] < threshold → кандидат.
      * между двумя соседними границами — не короче ``min_duration_sec``.
      * если за ``target_duration_sec * 1.5`` нет кандидата → делаем принудительный
        split на ближайшем подходящем месте.

    Возвращает список индексов ``i``, означающих "сегмент[i] — последний в
    текущем chunk'е, сегмент[i+1] начинает следующий".
    """

    boundaries: list[int] = []
    current_start = 0
    i = 0
    n = len(segments)
    while i < n - 1:
        chunk_duration = segments[i].end - segments[current_start].start
        threshold_hit = (
            similarities[i] < policy.similarity_threshold
            and chunk_duration >= policy.min_duration_sec
        )
        hard_cap_hit = chunk_duration >= policy.target_duration_sec * 1.5

        if threshold_hit or hard_cap_hit:
            boundaries.append(i)
            current_start = i + 1
        i += 1

    # Последний сегмент всегда завершает хвостовой chunk (не добавляем в boundaries).
    return boundaries


def _build_chunks(
    segments: list[TranscribedSegment],
    boundaries: list[int],
) -> list[TranscriptChunk]:
    """Склеивает сегменты в ``TranscriptChunk`` по границам."""

    chunks: list[TranscriptChunk] = []
    start = 0
    index = 0
    end_indices = [*list(boundaries), len(segments) - 1]
    for end in end_indices:
        if end < start:
            continue
        group = segments[start : end + 1]
        if not group:
            start = end + 1
            continue
        rendered = [_render_segment(s) for s in group]
        text = "\n".join(rendered)
        chunks.append(
            TranscriptChunk(
                index=index,
                start_sec=group[0].start,
                end_sec=group[-1].end,
                text=text,
                segments=list(group),
                token_count=count_tokens(text),
            )
        )
        index += 1
        start = end + 1
    return chunks
