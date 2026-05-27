"""Chapter Builder — Phase 1 top-down narrative pipeline.

Строит естественные тематические главы из транскрипта. Hybrid подход:
embedding-based candidate boundaries (cosine similarity local minima) +
LLM topic-shift verify через Gemini Flash Lite batch.

Алгоритм (research: Chapter-Llama CVPR 2025, ARC-Chapter Tencent 2025):

    1. Группируем ``TranscribedSegment`` в окна ~45s (WINDOW_DURATION_SEC).
    2. Эмбеддим каждое окно через ``gemini-embedding-001`` (256-dim).
    3. Считаем cosine similarity между соседними окнами.
    4. Кандидаты на границу = local minima в sliding window 3 + значение
       ниже CHAPTER_BUILDER_SIMILARITY_THRESHOLD.
    5. LLM Flash Lite batch call: для каждого кандидата передаём prev 90s
       + next 90s текста → ``is_boundary + topic_label + confidence``.
    6. Отфильтровываем кандидаты где LLM confirms и confidence ≥ 0.5.
    7. Post-processing: merge chapters < MIN_CHAPTER_DURATION_SEC (60s),
       split chapters > MAX_CHAPTER_DURATION_SEC (300s) по internal local min.
    8. Extract key_claims (2-5 первых sentence от каждой главы).

Graceful degradation:

    - Empty transcript → ``ValueError`` (caller must handle).
    - Total duration < 2 × MIN_CHAPTER_DURATION_SEC → single chapter,
      source="fallback".
    - Embedding API fails → fixed-window fallback (split every
      ~180s = (MIN+MAX)/2 chapter), source="fallback".
    - LLM fails → semantic-only boundaries without topic_label verification,
      source="semantic".

Entry point: ``build_chapters(transcript, *, settings, llm_client=None,
rate_limiter=None, provider_override=None) -> list[Chapter]``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from videomaker.core.config import Settings, get_settings
from videomaker.core.logging import get_logger
from videomaker.models.narrative import Chapter
from videomaker.services.llm_client import (
    LLMClient,
    LLMError,
    build_llm_for_tier,
    parse_json_response,
)
from videomaker.services.narrative.constants import (
    CHAPTER_BUILDER_LLM_WINDOW_SEC,
    CHAPTER_BUILDER_SIMILARITY_THRESHOLD,
    MAX_CHAPTER_DURATION_SEC,
    MIN_CHAPTER_DURATION_SEC,
)
from videomaker.services.prompts import (
    CHAPTER_BOUNDARY_SCORER_PROMPT,
    build_context_header,
    build_system_prompt,
)
from videomaker.services.rate_limiter import RateLimiter, get_gemini_rate_limiter
from videomaker.services.transcribers.base import (
    TranscribedSegment,
    TranscriptResult,
    merge_words_into_segments,
)

_ChapterSource = Literal["semantic", "llm", "hybrid", "fallback"]

log = get_logger(__name__)


#: Длительность одного окна для embedding-based chaptering.
#: Баланс: слишком маленькое окно (15s) → шум в similarity; слишком большое
#: (90s) → пропуск мелких границ. 45s — compromise подтверждённый
#: Chapter-Llama (CVPR 2025) на talking-head датасетах.
WINDOW_DURATION_SEC: float = 45.0

#: Максимум кандидатов на LLM batch. Ограничитель стоимости: 30 кандидатов
#: × (prev 90s + next 90s) × 15 слов/с = ~81000 входных слов = ~100K токенов.
#: Для 3-часового видео хватит с запасом (в среднем 10-15 границ).
MAX_LLM_CANDIDATES: int = 30

#: Минимальный confidence LLM для принятия границы. 0.5 = "LLM склоняется
#: к boundary, но не уверен". Выше — теряем валидные границы. Ниже — шум.
LLM_BOUNDARY_MIN_CONFIDENCE: float = 0.5

#: Количество key_claims извлекаемых в главу. 2-5 — достаточно для
#: downstream hook_detector/arc_finder без раздувания контекста.
CHAPTER_KEY_CLAIMS_MIN: int = 2
CHAPTER_KEY_CLAIMS_MAX: int = 5


@dataclass(slots=True, frozen=True)
class _Window:
    """Временное окно агрегированных segment'ов для embedding-based boundary detect."""

    index: int
    start_sec: float
    end_sec: float
    text: str
    segments: tuple[TranscribedSegment, ...]


@dataclass(slots=True, frozen=True)
class _BoundaryCandidate:
    """Кандидат на chapter boundary: similarity dip между окнами i и i+1."""

    window_left_index: int
    boundary_sec: float
    similarity: float
    candidate_id: str


async def build_chapters(
    transcript: TranscriptResult,
    *,
    settings: Settings | None = None,
    llm_client: LLMClient | None = None,
    rate_limiter: RateLimiter | None = None,
    provider_override: str | None = None,
) -> list[Chapter]:
    """Строит список глав из транскрипта.

    Возвращает непрерывные главы от 0 до transcript.duration_sec.
    Первая глава start_sec=0; последняя end_sec=duration_sec; главы
    идут в хронологическом порядке без перекрытий.
    """

    if transcript.duration_sec <= 0:
        raise ValueError("transcript.duration_sec must be > 0 for chaptering")

    segments = _collect_segments(transcript)
    if not segments:
        raise ValueError("transcript has no segments or words for chaptering")

    cfg = settings or get_settings()
    total_duration = transcript.duration_sec

    # Короткий транскрипт — одна глава (нет смысла дробить < 2 × MIN).
    if total_duration < 2 * MIN_CHAPTER_DURATION_SEC:
        log.info(
            "chapter_builder_single_chapter_short",
            duration_sec=round(total_duration, 1),
            min_required=2 * MIN_CHAPTER_DURATION_SEC,
        )
        return [
            _build_single_chapter(
                start_sec=0.0,
                end_sec=total_duration,
                segments=segments,
                topic_label=_fallback_topic_label(segments),
                source="fallback",
                confidence=1.0,
            )
        ]

    windows = _build_windows(segments, WINDOW_DURATION_SEC)
    if len(windows) < 3:
        # Недостаточно окон для adjacency similarity — single chapter.
        log.info(
            "chapter_builder_single_chapter_few_windows",
            windows=len(windows),
        )
        return [
            _build_single_chapter(
                start_sec=0.0,
                end_sec=total_duration,
                segments=segments,
                topic_label=_fallback_topic_label(segments),
                source="fallback",
                confidence=1.0,
            )
        ]

    try:
        embeddings = await _embed_windows(windows, settings=cfg)
    except Exception as exc:
        log.warning(
            "chapter_builder_embed_failed_fallback",
            error=str(exc),
            windows=len(windows),
        )
        return _fixed_window_fallback(total_duration, segments)

    if len(embeddings) != len(windows):
        log.warning(
            "chapter_builder_embed_length_mismatch_fallback",
            expected=len(windows),
            got=len(embeddings),
        )
        return _fixed_window_fallback(total_duration, segments)

    similarities = _compute_adjacent_similarities(embeddings)
    candidates = _detect_candidate_boundaries(windows, similarities)

    if not candidates:
        # Видео однородное — одна глава.
        log.info(
            "chapter_builder_no_candidates",
            avg_sim=round(sum(similarities) / len(similarities), 3),
        )
        return [
            _build_single_chapter(
                start_sec=0.0,
                end_sec=total_duration,
                segments=segments,
                topic_label=_fallback_topic_label(segments),
                source="semantic",
                confidence=0.7,
            )
        ]

    # Cap кандидатов перед LLM — стоимость.
    if len(candidates) > MAX_LLM_CANDIDATES:
        # Оставляем кандидатов с наименьшим similarity (сильнейшие dips).
        candidates = sorted(candidates, key=lambda c: c.similarity)[:MAX_LLM_CANDIDATES]
        candidates = sorted(candidates, key=lambda c: c.window_left_index)
        log.info("chapter_builder_candidates_capped", kept=MAX_LLM_CANDIDATES)

    try:
        llm_decisions = await _llm_verify_boundaries(
            candidates,
            transcript,
            settings=cfg,
            llm_client=llm_client,
            rate_limiter=rate_limiter,
            provider_override=provider_override,
        )
    except Exception as exc:
        log.warning(
            "chapter_builder_llm_failed_semantic_only",
            error=str(exc),
            candidates=len(candidates),
        )
        llm_decisions = {}

    confirmed_boundaries = _filter_confirmed(candidates, llm_decisions)

    log.info(
        "chapter_builder_boundaries_done",
        candidates=len(candidates),
        llm_confirmed=sum(
            1 for d in llm_decisions.values() if d.get("is_boundary")
        ),
        confirmed_final=len(confirmed_boundaries),
    )

    raw_chapters = _boundaries_to_chapters(
        confirmed_boundaries,
        total_duration,
        segments,
        llm_decisions,
    )
    chapters = _post_process(raw_chapters, segments, total_duration)
    return chapters


# ─── Segment → Window aggregation ────────────────────────────────────────


def _collect_segments(transcript: TranscriptResult) -> list[TranscribedSegment]:
    if transcript.segments:
        return list(transcript.segments)
    if transcript.words:
        return merge_words_into_segments(transcript.words)
    return []


def _build_windows(
    segments: list[TranscribedSegment],
    window_duration_sec: float,
) -> list[_Window]:
    """Группирует segment'ы в окна ~window_duration_sec.

    Window закрывается когда накопленная длительность ≥ window_duration_sec
    ИЛИ когда следующий segment начинается далеко (gap > 2s) — естественный
    break.
    """

    windows: list[_Window] = []
    if not segments:
        return windows

    current: list[TranscribedSegment] = [segments[0]]
    current_start = segments[0].start
    idx = 0

    for seg in segments[1:]:
        duration_so_far = seg.start - current_start
        gap_from_prev = seg.start - current[-1].end
        should_close = duration_so_far >= window_duration_sec or gap_from_prev > 2.0

        if should_close and current:
            windows.append(_make_window(idx, current))
            idx += 1
            current = [seg]
            current_start = seg.start
        else:
            current.append(seg)

    if current:
        windows.append(_make_window(idx, current))

    return windows


def _make_window(index: int, segments: list[TranscribedSegment]) -> _Window:
    text_parts = [(s.text or "").strip() for s in segments if (s.text or "").strip()]
    text = " ".join(text_parts)
    return _Window(
        index=index,
        start_sec=segments[0].start,
        end_sec=segments[-1].end,
        text=text,
        segments=tuple(segments),
    )


# ─── Embeddings + similarity ─────────────────────────────────────────────


async def _embed_windows(
    windows: list[_Window],
    *,
    settings: Settings,
) -> list[list[float]]:
    """Эмбеддит текст каждого окна через Gemini embeddings 256-dim."""

    from google import genai
    from google.genai import types as genai_types

    if not settings.gemini_api_key:
        raise RuntimeError("gemini_api_key not set — chapter_builder requires it")

    texts = [w.text if w.text else "(silence)" for w in windows]

    client = genai.Client(api_key=settings.gemini_api_key)
    model_id = "gemini-embedding-001"

    all_values: list[list[float]] = []
    batch_size = 90
    for start in range(0, len(texts), batch_size):
        batch: list[
            str | genai_types.PIL_Image | genai_types.File | genai_types.Part
        ] = list(texts[start : start + batch_size])
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
    sims: list[float] = []
    for i in range(len(embeddings) - 1):
        sims.append(_cosine(embeddings[i], embeddings[i + 1]))
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


# ─── Candidate boundary detection ────────────────────────────────────────


def _detect_candidate_boundaries(
    windows: list[_Window],
    similarities: list[float],
) -> list[_BoundaryCandidate]:
    """Находит кандидатов на границу.

    Условия:
    1. similarity[i] < CHAPTER_BUILDER_SIMILARITY_THRESHOLD (0.35).
    2. similarity[i] является local minimum в sliding window 3 (т.е.
       similarity[i] < similarity[i-1] и similarity[i] < similarity[i+1]).
       Для крайних позиций — локально-относительное условие (< соседа).

    Первые и последние 15 секунд видео пропускаем: граница там лишена
    смысла (глава меньше MIN).
    """

    if len(similarities) < 2 or len(windows) < 3:
        return []

    total_duration = windows[-1].end_sec
    min_boundary_sec = min(MIN_CHAPTER_DURATION_SEC * 0.5, 15.0)
    max_boundary_sec = total_duration - min_boundary_sec

    candidates: list[_BoundaryCandidate] = []
    for i, sim in enumerate(similarities):
        if sim >= CHAPTER_BUILDER_SIMILARITY_THRESHOLD:
            continue
        # Local minimum check.
        prev_sim = similarities[i - 1] if i > 0 else 1.0
        next_sim = similarities[i + 1] if i + 1 < len(similarities) else 1.0
        is_local_min = sim <= prev_sim and sim <= next_sim
        if not is_local_min:
            continue

        boundary_sec = windows[i].end_sec
        if boundary_sec < min_boundary_sec or boundary_sec > max_boundary_sec:
            continue

        candidates.append(
            _BoundaryCandidate(
                window_left_index=i,
                boundary_sec=boundary_sec,
                similarity=sim,
                candidate_id=f"cand_{i:03d}",
            )
        )

    return candidates


# ─── LLM verification ────────────────────────────────────────────────────


async def _llm_verify_boundaries(
    candidates: list[_BoundaryCandidate],
    transcript: TranscriptResult,
    *,
    settings: Settings,
    llm_client: LLMClient | None,
    rate_limiter: RateLimiter | None,
    provider_override: str | None,
) -> dict[str, dict[str, object]]:
    """Один LLM call (batch) на все кандидаты.

    Возвращает dict ``candidate_id → {is_boundary, confidence, topic_label, reasoning}``.
    """

    if not candidates:
        return {}

    llm = llm_client or build_llm_for_tier(
        "flash_lite",
        settings,
        provider_override=provider_override,
    )
    limiter = rate_limiter or get_gemini_rate_limiter()

    context_header = build_context_header(
        source_duration_sec=transcript.duration_sec,
        transcriber=transcript.transcriber,
        llm_model=llm.model,
        language=transcript.language,
    )
    system = (
        f"{build_system_prompt()}\n\n{context_header}\n\n{CHAPTER_BOUNDARY_SCORER_PROMPT}"
    )

    user_payload = _build_candidates_payload(candidates, transcript)

    async with limiter.acquire():
        response = await llm.complete_json(
            system=system,
            user=user_payload,
            temperature=0.2,
            max_tokens=4000,
        )

    try:
        parsed = parse_json_response(response.text)
    except LLMError as exc:
        log.error("chapter_builder_llm_parse_failed", error=str(exc))
        raise

    if not isinstance(parsed, dict) or "candidates" not in parsed:
        raise LLMError(
            f"chapter_builder LLM returned {type(parsed).__name__}, "
            "expected dict with 'candidates' key"
        )

    raw_list = parsed.get("candidates")
    if not isinstance(raw_list, list):
        raise LLMError("chapter_builder LLM 'candidates' is not a list")

    decisions: dict[str, dict[str, object]] = {}
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        cand_id = str(item.get("candidate_id") or "").strip()
        if not cand_id:
            continue
        decisions[cand_id] = {
            "is_boundary": bool(item.get("is_boundary", False)),
            "confidence": _clamp_float(item.get("confidence"), 0.0, 1.0, default=0.5),
            "topic_label": str(item.get("topic_label") or "").strip()[:120],
            "reasoning": str(item.get("reasoning") or "").strip()[:300],
        }
    return decisions


def _build_candidates_payload(
    candidates: list[_BoundaryCandidate],
    transcript: TranscriptResult,
) -> str:
    """Готовит user-prompt с prev 90s + next 90s текста вокруг каждого candidate."""

    parts: list[str] = [
        f"Длительность видео: {_fmt_duration(transcript.duration_sec)}.",
        f"Кандидатов границ: {len(candidates)}.",
        "",
        "Для каждого candidate_id решить: boundary или continuation. "
        "Вернуть JSON со списком 'candidates'. См. OUTPUT SCHEMA.",
        "",
    ]

    for cand in candidates:
        prev_text = _text_in_range(
            transcript,
            cand.boundary_sec - CHAPTER_BUILDER_LLM_WINDOW_SEC,
            cand.boundary_sec,
        )
        next_text = _text_in_range(
            transcript,
            cand.boundary_sec,
            cand.boundary_sec + CHAPTER_BUILDER_LLM_WINDOW_SEC,
        )
        parts.append(f"─── candidate_id={cand.candidate_id} ───")
        parts.append(f"Позиция в видео: {_fmt_duration(cand.boundary_sec)}")
        parts.append(f"Semantic similarity (prev↔next): {cand.similarity:.3f}")
        parts.append("")
        parts.append(f"[prev_window ~{int(CHAPTER_BUILDER_LLM_WINDOW_SEC)}s]:")
        parts.append(prev_text or "(нет текста)")
        parts.append("")
        parts.append(f"[next_window ~{int(CHAPTER_BUILDER_LLM_WINDOW_SEC)}s]:")
        parts.append(next_text or "(нет текста)")
        parts.append("")

    return "\n".join(parts)


def _text_in_range(
    transcript: TranscriptResult,
    start_sec: float,
    end_sec: float,
) -> str:
    """Возвращает склеенный текст сегментов/слов в [start_sec, end_sec)."""

    lo = max(0.0, start_sec)
    hi = max(lo, end_sec)

    if transcript.segments:
        words: list[str] = []
        for seg in transcript.segments:
            if seg.end < lo:
                continue
            if seg.start >= hi:
                break
            text = (seg.text or "").strip()
            if text:
                words.append(text)
        return " ".join(words)

    if transcript.words:
        tokens: list[str] = []
        for w in transcript.words:
            if w.end < lo:
                continue
            if w.start >= hi:
                break
            token = (w.word or "").strip()
            if token:
                tokens.append(token)
        return " ".join(tokens)

    return ""


# ─── Boundaries → Chapters ───────────────────────────────────────────────


def _filter_confirmed(
    candidates: list[_BoundaryCandidate],
    llm_decisions: dict[str, dict[str, object]],
) -> list[_BoundaryCandidate]:
    """Фильтрует candidates — оставляет только те, где LLM подтвердил границу.

    Если LLM не вернул решение для candidate (или decisions пустой — сбой) —
    используем semantic-only: принимаем candidate если similarity очень
    низкая (< threshold × 0.7, сильный dip).
    """

    confirmed: list[_BoundaryCandidate] = []
    for cand in candidates:
        decision = llm_decisions.get(cand.candidate_id)
        if decision is None:
            # Semantic-only fallback: сильный dip = принимаем.
            if cand.similarity < CHAPTER_BUILDER_SIMILARITY_THRESHOLD * 0.7:
                confirmed.append(cand)
            continue
        if not decision.get("is_boundary"):
            continue
        confidence_raw = decision.get("confidence", 0.0)
        confidence = float(confidence_raw) if isinstance(confidence_raw, (int, float)) else 0.0
        if confidence < LLM_BOUNDARY_MIN_CONFIDENCE:
            continue
        confirmed.append(cand)
    return confirmed


def _boundaries_to_chapters(
    boundaries: list[_BoundaryCandidate],
    total_duration: float,
    segments: list[TranscribedSegment],
    llm_decisions: dict[str, dict[str, object]],
) -> list[Chapter]:
    """Собирает chapters из confirmed boundary list."""

    if not boundaries:
        return [
            _build_single_chapter(
                start_sec=0.0,
                end_sec=total_duration,
                segments=segments,
                topic_label=_fallback_topic_label(segments),
                source="semantic",
                confidence=0.7,
            )
        ]

    chapters: list[Chapter] = []
    prev_end = 0.0
    for idx, bound in enumerate(boundaries):
        decision = llm_decisions.get(bound.candidate_id, {})
        topic_label_raw = decision.get("topic_label") if decision else ""
        topic_label_str = str(topic_label_raw) if topic_label_raw else ""
        topic_label = topic_label_str or _fallback_topic_label_range(
            segments, prev_end, bound.boundary_sec
        )
        confidence_raw = decision.get("confidence") if decision else None
        confidence = (
            float(confidence_raw)
            if isinstance(confidence_raw, (int, float))
            else 0.6
        )
        source = "hybrid" if decision else "semantic"

        chapters.append(
            _build_chapter(
                chapter_index=idx,
                start_sec=prev_end,
                end_sec=bound.boundary_sec,
                segments=segments,
                topic_label=topic_label,
                source=source,
                confidence=confidence,
            )
        )
        prev_end = bound.boundary_sec

    # Хвостовая глава.
    last_topic = _fallback_topic_label_range(segments, prev_end, total_duration)
    chapters.append(
        _build_chapter(
            chapter_index=len(chapters),
            start_sec=prev_end,
            end_sec=total_duration,
            segments=segments,
            topic_label=last_topic,
            source="semantic",
            confidence=0.6,
        )
    )
    return chapters


# ─── Post-processing (merge small, split huge) ────────────────────────────


def _post_process(
    chapters: list[Chapter],
    segments: list[TranscribedSegment],
    total_duration: float,
) -> list[Chapter]:
    """Мерджит главы < MIN_CHAPTER_DURATION, сплиттит > MAX_CHAPTER_DURATION.

    Merge direction: маленькую главу склеиваем с соседом у которого ниже
    confidence (более слабая граница → легче отказаться).
    """

    merged = _merge_short(chapters)
    split_done = _split_long(merged, segments, total_duration)
    return _renumber_and_validate(split_done, total_duration)


def _merge_short(chapters: list[Chapter]) -> list[Chapter]:
    if len(chapters) <= 1:
        return chapters

    result: list[Chapter] = []
    i = 0
    while i < len(chapters):
        ch = chapters[i]
        if ch.duration_sec() >= MIN_CHAPTER_DURATION_SEC or (
            not result and i == len(chapters) - 1
        ):
            result.append(ch)
            i += 1
            continue

        # Короткая глава — мержим с соседом у которого ниже confidence.
        left_neighbor = result[-1] if result else None
        right_neighbor = chapters[i + 1] if i + 1 < len(chapters) else None

        merge_with_left = False
        if left_neighbor is not None and right_neighbor is not None:
            merge_with_left = left_neighbor.confidence <= right_neighbor.confidence
        elif left_neighbor is not None:
            merge_with_left = True

        if merge_with_left and left_neighbor is not None:
            merged = _merge_two(left_neighbor, ch)
            result[-1] = merged
            i += 1
        elif right_neighbor is not None:
            merged = _merge_two(ch, right_neighbor)
            result.append(merged)
            i += 2
        else:
            # Некуда мержить — оставляем как есть.
            result.append(ch)
            i += 1

    return result


def _merge_two(left: Chapter, right: Chapter) -> Chapter:
    """Склеивает две главы — берёт topic_label от более уверенной."""

    better = left if left.confidence >= right.confidence else right
    combined_claims = list(left.key_claims)
    for claim in right.key_claims:
        if claim not in combined_claims and len(combined_claims) < CHAPTER_KEY_CLAIMS_MAX:
            combined_claims.append(claim)

    return Chapter(
        id=left.id,  # id left — id финальной главы, перепишется _renumber.
        start_sec=left.start_sec,
        end_sec=right.end_sec,
        topic_label=better.topic_label,
        key_claims=combined_claims[:CHAPTER_KEY_CLAIMS_MAX],
        confidence=min(left.confidence, right.confidence),
        source="hybrid" if (left.source == "hybrid" or right.source == "hybrid") else left.source,
    )


def _split_long(
    chapters: list[Chapter],
    segments: list[TranscribedSegment],
    total_duration: float,
) -> list[Chapter]:
    """Сплиттит главы > MAX_CHAPTER_DURATION.

    Content-aware split: ищем середину главы и делим в первой natural
    sentence boundary (segment end в пределах ±15s от mid).
    """

    del total_duration  # сохранён для будущей логики, сейчас не используется.

    result: list[Chapter] = []
    for ch in chapters:
        if ch.duration_sec() <= MAX_CHAPTER_DURATION_SEC:
            result.append(ch)
            continue

        # Множественный split если глава очень длинная.
        parts = _split_chapter_recursive(ch, segments)
        result.extend(parts)
    return result


def _split_chapter_recursive(
    ch: Chapter,
    segments: list[TranscribedSegment],
) -> list[Chapter]:
    if ch.duration_sec() <= MAX_CHAPTER_DURATION_SEC:
        return [ch]

    mid = (ch.start_sec + ch.end_sec) / 2
    split_at = _find_segment_boundary_near(segments, mid, tolerance_sec=15.0)
    if split_at is None or split_at <= ch.start_sec or split_at >= ch.end_sec:
        # Не нашли boundary — грубый split в mid.
        split_at = mid

    left = Chapter(
        id=ch.id,
        start_sec=ch.start_sec,
        end_sec=split_at,
        topic_label=ch.topic_label,
        key_claims=ch.key_claims[: max(1, len(ch.key_claims) // 2)],
        confidence=ch.confidence * 0.9,
        source=ch.source,
    )
    right_topic = ch.topic_label + " (продолжение)"
    right = Chapter(
        id=ch.id + "_b",
        start_sec=split_at,
        end_sec=ch.end_sec,
        topic_label=right_topic[:120],
        key_claims=ch.key_claims[max(1, len(ch.key_claims) // 2) :],
        confidence=ch.confidence * 0.9,
        source=ch.source,
    )
    return _split_chapter_recursive(left, segments) + _split_chapter_recursive(right, segments)


def _find_segment_boundary_near(
    segments: list[TranscribedSegment],
    target_sec: float,
    *,
    tolerance_sec: float,
) -> float | None:
    """Находит ближайший segment.end к target в пределах tolerance."""

    best_diff = tolerance_sec + 1.0
    best_end: float | None = None
    for seg in segments:
        diff = abs(seg.end - target_sec)
        if diff < best_diff:
            best_diff = diff
            best_end = seg.end
    return best_end if best_diff <= tolerance_sec else None


# ─── Renumber + validation ───────────────────────────────────────────────


def _renumber_and_validate(
    chapters: list[Chapter],
    total_duration: float,
) -> list[Chapter]:
    """Перенумерует id, гарантирует непрерывность [0, total_duration)."""

    if not chapters:
        raise RuntimeError("chapter_builder produced empty chapters list")

    fixed: list[Chapter] = []
    prev_end = 0.0
    for idx, ch in enumerate(chapters):
        start = max(ch.start_sec, prev_end)
        end = max(start + 0.01, ch.end_sec)
        fixed.append(
            Chapter(
                id=f"ch_{idx + 1:03d}",
                start_sec=start,
                end_sec=end,
                topic_label=ch.topic_label or f"Глава {idx + 1}",
                key_claims=ch.key_claims,
                confidence=ch.confidence,
                source=ch.source,
            )
        )
        prev_end = end

    # Финальная глава должна покрывать до total_duration.
    last = fixed[-1]
    if last.end_sec < total_duration - 0.1:
        fixed[-1] = Chapter(
            id=last.id,
            start_sec=last.start_sec,
            end_sec=total_duration,
            topic_label=last.topic_label,
            key_claims=last.key_claims,
            confidence=last.confidence,
            source=last.source,
        )
    return fixed


# ─── Chapter construction helpers ────────────────────────────────────────


def _build_chapter(
    *,
    chapter_index: int,
    start_sec: float,
    end_sec: float,
    segments: list[TranscribedSegment],
    topic_label: str,
    source: str,
    confidence: float,
) -> Chapter:
    key_claims = _extract_key_claims(segments, start_sec, end_sec)
    return Chapter(
        id=f"ch_{chapter_index + 1:03d}",
        start_sec=start_sec,
        end_sec=end_sec,
        topic_label=topic_label or f"Глава {chapter_index + 1}",
        key_claims=key_claims,
        confidence=max(0.0, min(1.0, confidence)),
        source=_coerce_source(source),
    )


def _build_single_chapter(
    *,
    start_sec: float,
    end_sec: float,
    segments: list[TranscribedSegment],
    topic_label: str,
    source: str,
    confidence: float,
) -> Chapter:
    return _build_chapter(
        chapter_index=0,
        start_sec=start_sec,
        end_sec=end_sec,
        segments=segments,
        topic_label=topic_label,
        source=source,
        confidence=confidence,
    )


def _coerce_source(source: str) -> _ChapterSource:
    if source == "semantic":
        return "semantic"
    if source == "llm":
        return "llm"
    if source == "fallback":
        return "fallback"
    return "hybrid"


def _extract_key_claims(
    segments: list[TranscribedSegment],
    start_sec: float,
    end_sec: float,
) -> list[str]:
    """Извлекает 2-5 sentence-level utterances из диапазона.

    Эвристика: берём первые sentence'ы в диапазоне (обычно речь начинается
    с topic-setup), отсекаем дубли, длиной 30-200 символов.
    """

    claims: list[str] = []
    seen: set[str] = set()
    for seg in segments:
        if seg.end < start_sec:
            continue
        if seg.start >= end_sec:
            break
        text = (seg.text or "").strip()
        if len(text) < 30 or len(text) > 220:
            continue
        normalized = text.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        claims.append(text)
        if len(claims) >= CHAPTER_KEY_CLAIMS_MAX:
            break
    # Если недобрали CHAPTER_KEY_CLAIMS_MIN — дополняем короткими sentence'ами.
    if len(claims) < CHAPTER_KEY_CLAIMS_MIN:
        for seg in segments:
            if seg.end < start_sec:
                continue
            if seg.start >= end_sec:
                break
            text = (seg.text or "").strip()
            if not text or text.lower() in seen:
                continue
            seen.add(text.lower())
            claims.append(text[:200])
            if len(claims) >= CHAPTER_KEY_CLAIMS_MIN:
                break
    return claims[:CHAPTER_KEY_CLAIMS_MAX]


def _fallback_topic_label(segments: list[TranscribedSegment]) -> str:
    """Topic label из первого содержательного segment'а (деградационный fallback)."""

    for seg in segments:
        text = (seg.text or "").strip()
        if len(text) >= 20:
            words = text.split()[:6]
            return " ".join(words)[:120]
    return "Глава"


def _fallback_topic_label_range(
    segments: list[TranscribedSegment],
    start_sec: float,
    end_sec: float,
) -> str:
    for seg in segments:
        if seg.end < start_sec:
            continue
        if seg.start >= end_sec:
            break
        text = (seg.text or "").strip()
        if len(text) >= 20:
            words = text.split()[:6]
            return " ".join(words)[:120]
    return "Глава"


# ─── Fallback: fixed-window chaptering ────────────────────────────────────


def _fixed_window_fallback(
    total_duration: float,
    segments: list[TranscribedSegment],
) -> list[Chapter]:
    """Когда embeddings/LLM недоступны — равномерно делим на chapter'ы."""

    chapter_duration = (MIN_CHAPTER_DURATION_SEC + MAX_CHAPTER_DURATION_SEC) / 2
    n_chapters = max(1, round(total_duration / chapter_duration))
    actual_duration = total_duration / n_chapters
    chapters: list[Chapter] = []
    for i in range(n_chapters):
        start = i * actual_duration
        end = (i + 1) * actual_duration if i < n_chapters - 1 else total_duration
        chapters.append(
            _build_chapter(
                chapter_index=i,
                start_sec=start,
                end_sec=end,
                segments=segments,
                topic_label=_fallback_topic_label_range(segments, start, end),
                source="fallback",
                confidence=0.4,
            )
        )
    return chapters


# ─── Utilities ────────────────────────────────────────────────────────────


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


def _fmt_duration(sec: float) -> str:
    total = max(0, int(sec))
    m, s = divmod(total, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:d}:{s:02d}"


__all__ = ["build_chapters"]
