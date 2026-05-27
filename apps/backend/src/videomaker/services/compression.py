"""Kartoziya Stage 5.1 — Compression (параллельные Flash Lite summaries per chunk).

Вход: список `TranscriptChunk` (после RAG-chunking через chunker.py).
Выход: `CompressionResult` с `list[CompressedChunk]` — сжатые 500-1500 слов summary
с ключевыми цитатами и эмоциональными пиками.

Пайплайн:
1. Асинхронно запускаем N вызовов Flash Lite с semaphore (llm_max_concurrency).
2. Каждый вызов получает KARTOZIYA_SYSTEM_PROMPT + COMPRESSION_PROMPT + chunk content.
3. Парсим JSON → `CompressedChunk`.
4. Сохраняем сортировку по `chunk_index` после asyncio.gather.
5. При ошибке на chunk — возвращаем fallback с raw-текстом (не теряем данные).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol

from videomaker.core.config import get_settings
from videomaker.core.logging import get_logger
from videomaker.models.canvas import (
    CompressedChunk,
    EmotionalPeak,
    NotableQuote,
)
from videomaker.services.chunker import TranscriptChunk
from videomaker.services.llm_client import (
    LLMClient,
    LLMError,
    build_llm_for_tier,
    parse_json_response,
)
from videomaker.services.prompts import (
    COMPRESSION_PROMPT,
    build_system_prompt,
)
from videomaker.services.rate_limiter import RateLimiter, get_gemini_rate_limiter

log = get_logger(__name__)


@dataclass(slots=True)
class CompressionResult:
    chunks: list[CompressedChunk]
    total_input_tokens: int = 0
    total_output_tokens: int = 0

    def to_synopsis(self) -> str:
        """Собирает все chunks в единый синопсис для Canvas Builder'а."""
        return "\n\n".join(c.to_synopsis_fragment() for c in self.chunks)


class CompressionProgress(Protocol):
    """Optional hook для SSE progress reporting из pipeline.py."""

    async def __call__(self, *, done: int, total: int, chunk_index: int) -> None: ...


async def compress_chunks(
    chunks: list[TranscriptChunk],
    *,
    client: LLMClient | None = None,
    rate_limiter: RateLimiter | None = None,
    concurrency: int | None = None,
    progress: CompressionProgress | None = None,
    pipeline_provider: str | None = None,
) -> CompressionResult:
    """Параллельно сжимает каждый chunk через Flash Lite."""
    if not chunks:
        return CompressionResult(chunks=[])

    cfg = get_settings()
    llm = client or build_llm_for_tier("flash_lite", cfg, provider_override=pipeline_provider)
    limiter = rate_limiter or get_gemini_rate_limiter()
    sem = asyncio.Semaphore(concurrency or cfg.llm_max_concurrency)
    total = len(chunks)
    done_counter = {"n": 0}

    async def _compress_one(chunk: TranscriptChunk) -> CompressedChunk:
        async with sem, limiter.acquire():
            user_content = chunk.render_for_llm()
            full_system = f"{build_system_prompt()}\n\n{COMPRESSION_PROMPT}"
            try:
                response = await llm.complete_json(
                    system=full_system,
                    user=user_content,
                    temperature=0.1,
                    max_tokens=6000,
                )
                parsed = parse_json_response(response.text)
                compressed = _parse_compressed_output(parsed, chunk)
            except LLMError as exc:
                log.warning(
                    "compression_chunk_failed",
                    chunk_index=chunk.index,
                    error=str(exc),
                )
                compressed = _fallback_chunk(chunk)
            done_counter["n"] += 1
            if progress:
                await progress(
                    done=done_counter["n"],
                    total=total,
                    chunk_index=chunk.index,
                )
            return compressed

    results = await asyncio.gather(*(_compress_one(c) for c in chunks))
    results_sorted = sorted(results, key=lambda c: c.chunk_index)
    log.info("compression_done", chunks=len(results_sorted))
    return CompressionResult(chunks=results_sorted)


_VALID_PEAK_KINDS = {
    "surprise",
    "laughter",
    "confession",
    "anger",
    "triumph",
    "tension",
}


def _parse_compressed_output(data: object, chunk: TranscriptChunk) -> CompressedChunk:
    if not isinstance(data, dict):
        raise LLMError(f"expected dict in compression output, got {type(data).__name__}")

    summary = str(data.get("summary", "")).strip()
    if not summary:
        raise LLMError("compression response missing 'summary'")

    time_range = data.get("time_range_sec")
    if isinstance(time_range, list) and len(time_range) == 2:
        tr = (float(time_range[0]), float(time_range[1]))
    else:
        tr = (chunk.start_sec, chunk.end_sec)

    quotes = [
        NotableQuote(
            quote=str(q.get("quote", "")).strip(),
            sec=float(q.get("sec", chunk.start_sec)),
            speaker=q.get("speaker"),
        )
        for q in (data.get("notable_quotes") or [])
        if isinstance(q, dict) and q.get("quote")
    ]

    peaks: list[EmotionalPeak] = []
    for p in data.get("emotional_peaks") or []:
        if not isinstance(p, dict):
            continue
        kind = p.get("kind", "surprise")
        if kind not in _VALID_PEAK_KINDS:
            kind = "surprise"
        peaks.append(
            EmotionalPeak(
                sec=float(p.get("sec", chunk.start_sec)),
                kind=kind,
                note=str(p.get("note", "")),
            )
        )

    speakers = [str(s) for s in data.get("key_speakers") or [] if isinstance(s, str)]

    return CompressedChunk(
        chunk_index=int(data.get("chunk_index", chunk.index)),
        time_range_sec=tr,
        summary=summary,
        key_speakers=speakers,
        notable_quotes=quotes,
        emotional_peaks=peaks,
    )


def _fallback_chunk(chunk: TranscriptChunk) -> CompressedChunk:
    """Если LLM упал — raw-chunk с пометкой. Canvas Builder обработает.

    videomaker-транскрайберы не возвращают speaker-лейблы на уровне
    TranscribedSegment (дифференциация speaker'ов делается LLM'ом при
    компрессии). В fallback'e оставляем пустой key_speakers — LLM
    определит их на следующих стадиях через текст.
    """
    raw_text = " ".join(seg.text for seg in chunk.segments if seg.text)[:3000]
    return CompressedChunk(
        chunk_index=chunk.index,
        time_range_sec=(chunk.start_sec, chunk.end_sec),
        summary=f"[compression failed — raw transcript fallback] {raw_text}",
        key_speakers=[],
    )
