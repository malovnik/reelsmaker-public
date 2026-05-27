"""Kartoziya Stage 5.2 — Canvas Builder (Gemini Pro, один вызов на весь видеоряд).

Вход: `CompressionResult` из Stage 5.1 (сжатый синопсис всего видео).
Выход: `ProjectCanvas` — scaffold истории (сверхидея, темы, мотивы, спикеры,
candidate_moments, tone_map, chronological_spine).

Canvas становится общим контекстом для всех downstream stages (5.3-5.8).
Используется Pro-модель чтобы качество scaffold'а было максимальным —
ошибка здесь каскадно ломает extraction.
"""

from __future__ import annotations

from typing import Literal, cast

from videomaker.core.config import get_settings
from videomaker.core.logging import get_logger
from videomaker.models.canvas import (
    CanvasCandidateMoment,
    CanvasEpisode,
    CanvasMotif,
    CanvasSpeaker,
    CanvasTheme,
    CanvasToneRange,
    ProjectCanvas,
)
from videomaker.services.compression import CompressionResult
from videomaker.services.llm_client import (
    LLMClient,
    LLMError,
    build_llm_for_tier,
    parse_json_response,
)
from videomaker.services.prompts import (
    CANVAS_BUILDER_PROMPT,
    build_context_header,
    build_system_prompt,
)
from videomaker.services.rate_limiter import RateLimiter, get_gemini_rate_limiter

log = get_logger(__name__)

_VALID_MOODS = {
    "setup",
    "nostalgic",
    "tense",
    "triumphant",
    "contemplative",
    "energetic",
    "melancholic",
    "anxious",
    "joyful",
    "confessional",
}
_VALID_MOMENT_KINDS = {"hook", "peak", "payoff", "setup", "cutaway"}

#: Базовые пороги качества Canvas output для короткого видео (<= 15 мин).
#: Если LLM вернул scaffold с меньшим числом полей — считаем его sparse
#: и синтезируем fallback из CompressionResult. Для длинных видео пороги
#: scale'ятся через ``_quality_thresholds`` — 5 candidate_moments на
#: 96-мин видео = 1 момент на 19 минут, downstream extraction получит
#: мало контекста → реально нужно 15-20+ моментов для длинных.
_MIN_CANVAS_THEMES = 2
_MIN_CANVAS_CANDIDATE_MOMENTS = 5
_MIN_CANVAS_TONE_MAP = 2

#: Лимиты fallback-синтеза для коротких видео. Масштабируются по длительности
#: через ``_fallback_limits`` — см. там.
_FALLBACK_MAX_THEMES = 5
_FALLBACK_MAX_MOMENTS = 15


def _quality_thresholds(source_duration_sec: float) -> tuple[int, int, int]:
    """Scaled минимальные пороги Canvas quality gate.

    Возвращает ``(min_themes, min_candidate_moments, min_tone_map)``.
    Короткое видео требует немного — long-form нужно больше, иначе
    extraction/reducer/composer работают с голодной scaffold'ой.

    Iteration 2026-04-22: верхние тиры подняты для OpusClip-пропорции
    (0.6-0.9 рилсов/мин). На 95-мин видео LLM отдаёт ~40 moments —
    при min=50 canvas помечается как sparse и запускается augmentation
    heuristic moments до ``max_moments`` в ``_fallback_limits``. Это
    **augmentation** (LLM moments сохраняются, добавляются evidence-peaks
    из compression chunks), не replacement.

    Scale:
      *  <=15 мин → (2, 5, 2)    (baseline)
      *  <=40 мин → (3, 8, 3)
      *  <=80 мин → (4, 30, 4)
      *  >80 мин  → (5, 50, 5)
    """
    minutes = source_duration_sec / 60.0
    if minutes <= 15:
        return _MIN_CANVAS_THEMES, _MIN_CANVAS_CANDIDATE_MOMENTS, _MIN_CANVAS_TONE_MAP
    if minutes <= 40:
        return 3, 8, 3
    if minutes <= 80:
        return 4, 30, 4
    return 5, 50, 5


def _fallback_limits(source_duration_sec: float) -> tuple[int, int]:
    """Scaled лимиты fallback-синтеза — max themes, max moments.

    Для длинного видео fallback собирает больше entries, чтобы downstream
    не деградировал. Верхние тиры подняты для OpusClip overproduction
    (0.7 рилсов/мин): 95-мин получает max_moments=70, multi_arc_builder
    строит ~55-60 arcs после отсева moments без evidence.

    Нижний потолок 12 для коротких гарантирует >= 10 candidate_moments
    даже если LLM Canvas Builder был sparse — один из completion criteria.
    """
    minutes = source_duration_sec / 60.0
    if minutes <= 15:
        return _FALLBACK_MAX_THEMES, 12  # ≥10 moments гарантированно
    if minutes <= 40:
        return 7, 20
    if minutes <= 80:
        return 10, 45
    return 12, 70


async def build_canvas(
    compression: CompressionResult,
    *,
    source_duration_sec: float,
    transcriber_name: str,
    language: str = "ru",
    speakers_count: int | None = None,
    client: LLMClient | None = None,
    rate_limiter: RateLimiter | None = None,
    pipeline_provider: str | None = None,
) -> ProjectCanvas:
    """Генерирует Canvas из compressed transcript через Gemini Pro."""
    if not compression.chunks:
        raise ValueError("cannot build canvas from empty compression result")

    cfg = get_settings()
    llm = client or build_llm_for_tier("pro", cfg, provider_override=pipeline_provider)
    limiter = rate_limiter or get_gemini_rate_limiter()

    synopsis = compression.to_synopsis()
    context_header = build_context_header(
        source_duration_sec=source_duration_sec,
        transcriber=transcriber_name,
        llm_model=llm.model,
        language=language,
        speakers_count=speakers_count,
    )

    system = f"{build_system_prompt()}\n\n{context_header}\n\n{CANVAS_BUILDER_PROMPT}"

    log.info(
        "canvas_builder_start",
        chunks_in_synopsis=len(compression.chunks),
        synopsis_chars=len(synopsis),
        model=llm.model,
    )

    async with limiter.acquire():
        response = await llm.complete_json(
            system=system,
            user=synopsis,
            temperature=0.3,
            max_tokens=16000,
        )

    try:
        parsed = parse_json_response(response.text)
    except LLMError as exc:
        log.error("canvas_parse_failed", error=str(exc))
        raise

    if not isinstance(parsed, dict):
        raise LLMError(f"canvas LLM returned {type(parsed).__name__}, expected dict")

    canvas = _parse_canvas_output(parsed)

    # Quality gate: sparse canvas ломает каскад. Пороги scale'ятся по
    # длительности — для 96-мин видео 5 candidate_moments = 1 момент
    # на 19 минут, extraction получит голодный scaffold.
    min_themes, min_moments, min_tone = _quality_thresholds(source_duration_sec)
    sparse = (
        len(canvas.themes) < min_themes
        or len(canvas.candidate_moments) < min_moments
        or len(canvas.tone_map) < min_tone
    )
    if sparse:
        log.warning(
            "canvas_sparse_output",
            themes=len(canvas.themes),
            candidate_moments=len(canvas.candidate_moments),
            tone_map=len(canvas.tone_map),
            min_themes=min_themes,
            min_moments=min_moments,
            min_tone=min_tone,
            duration_min=round(source_duration_sec / 60.0, 1),
            central_theme=canvas.central_theme[:100],
        )
        max_themes, max_moments = _fallback_limits(source_duration_sec)
        canvas = _synthesize_canvas_fallback(
            parsed_canvas=canvas,
            compression=compression,
            source_duration_sec=source_duration_sec,
            max_themes_override=max_themes,
            max_moments_override=max_moments,
            min_themes_trigger=min_themes,
            min_moments_trigger=min_moments,
        )
        log.info(
            "canvas_fallback_synthesized",
            themes=len(canvas.themes),
            candidate_moments=len(canvas.candidate_moments),
            tone_map=len(canvas.tone_map),
        )

    # T2.1 Hierarchical canvas: эвристическая группировка candidate_moments
    # по time-bucket'ам (10 мин). Для коротких видео (< 30 мин) эпизодов
    # будет 1-2, canvas остаётся плоским. Для длинных (1ч+) даёт drill-down
    # структуру для downstream consumers.
    episodes = _build_episodes_heuristic(canvas, source_duration_sec)
    if episodes:
        canvas = canvas.model_copy(update={"episodes": episodes})

    log.info(
        "canvas_built",
        themes=len(canvas.themes),
        motifs=len(canvas.motifs),
        speakers=len(canvas.speakers),
        candidate_moments=len(canvas.candidate_moments),
        episodes=len(canvas.episodes),
    )
    return canvas


def _parse_canvas_output(data: dict) -> ProjectCanvas:
    themes = [
        CanvasTheme(
            id=str(t.get("id", f"t{i}")),
            label=str(t.get("label", "")).strip() or f"theme {i}",
            description=str(t.get("description", "")).strip(),
            strength=_clamp_unit(t.get("strength", 0.5)),
            first_mention_sec=max(0.0, float(t.get("first_mention_sec", 0.0))),
            last_mention_sec=max(0.0, float(t.get("last_mention_sec", 0.0))),
        )
        for i, t in enumerate(data.get("themes") or [])
        if isinstance(t, dict)
    ]

    motifs = [
        CanvasMotif(
            id=str(m.get("id", f"m{i}")),
            label=str(m.get("label", "")).strip() or f"motif {i}",
            occurrences_sec=[
                max(0.0, float(s))
                for s in (m.get("occurrences_sec") or [])
                if isinstance(s, int | float)
            ],
            significance=str(m.get("significance", "")).strip(),
        )
        for i, m in enumerate(data.get("motifs") or [])
        if isinstance(m, dict)
    ]

    speakers = [
        CanvasSpeaker(
            id=str(s.get("id", f"speaker_{i}")),
            role=str(s.get("role", "неизвестно")).strip(),
            importance=_clamp_unit(s.get("importance", 0.5)),
            key_quote_start_sec=_optional_float(s.get("key_quote_start_sec")),
        )
        for i, s in enumerate(data.get("speakers") or [])
        if isinstance(s, dict)
    ]

    candidate_moments = [
        CanvasCandidateMoment(
            id=str(m.get("id", f"mo{i}")),
            speaker=m.get("speaker"),
            start=max(0.0, float(m.get("start", 0.0))),
            end=max(0.0, float(m.get("end", 0.0))),
            one_liner=str(m.get("one_liner", "")).strip()[:500],
            kind=_normalize_moment_kind(m.get("kind")),
            strength=_clamp_unit(m.get("strength", 0.5)),
        )
        for i, m in enumerate(data.get("candidate_moments") or [])
        if isinstance(m, dict)
    ]

    tone_map: list[CanvasToneRange] = []
    for tr in data.get("tone_map") or []:
        if not isinstance(tr, dict):
            continue
        rng = tr.get("sec_range")
        if not (isinstance(rng, list) and len(rng) == 2):
            continue
        try:
            start = max(0.0, float(rng[0]))
            end = max(start, float(rng[1]))
        except (TypeError, ValueError):
            continue
        tone_map.append(
            CanvasToneRange(
                sec_range=(start, end),
                mood=_normalize_mood(tr.get("mood")),
                intensity=_clamp_unit(tr.get("intensity", 0.5)),
            )
        )

    spine = [str(item) for item in data.get("chronological_spine") or [] if item]

    return ProjectCanvas(
        central_theme=str(data.get("central_theme", "")).strip(),
        themes=themes,
        motifs=motifs,
        speakers=speakers,
        candidate_moments=candidate_moments,
        tone_map=tone_map,
        chronological_spine=spine,
    )


def _synthesize_canvas_fallback(
    *,
    parsed_canvas: ProjectCanvas,
    compression: CompressionResult,
    source_duration_sec: float,
    max_themes_override: int | None = None,
    max_moments_override: int | None = None,
    min_themes_trigger: int | None = None,
    min_moments_trigger: int | None = None,
) -> ProjectCanvas:
    """Fallback: если LLM дал сильно sparse canvas, синтезируем из chunks.

    Используется когда Canvas Builder вернул почти пустой scaffold
    (< минимальных порогов). Без scaffold pipeline деградирует до
    single-segment рилсов — худший UX. Лучше неидеальный scaffold
    из compression, чем пустой.

    Стратегия:
    * `central_theme` — если LLM заполнил, оставляем; иначе берём из
      summary первого chunk.
    * `themes` — добираем до ``_FALLBACK_MAX_THEMES`` штук, по одной на
      chunk с summary достаточной длины.
    * `candidate_moments` — собираем из ``notable_quotes`` и
      ``emotional_peaks`` всех chunks (до ``_FALLBACK_MAX_MOMENTS``).
    * `tone_map` — по одному нейтральному range на chunk (setup/0.5).
    * `chronological_spine` — timestamp + summary[:100] для каждого chunk.
    """
    central = parsed_canvas.central_theme.strip()
    if not central and compression.chunks:
        central = compression.chunks[0].summary[:200].strip()

    max_themes = max_themes_override or _FALLBACK_MAX_THEMES
    max_moments = max_moments_override or _FALLBACK_MAX_MOMENTS
    # Триггеры добора — scaled по длительности. Без override — baseline
    # (2 themes / 5 moments). Для 80+ мин видео caller передаёт 5/15 —
    # тогда fallback добирает к max даже если LLM дал 3 themes.
    min_themes_for_fill = min_themes_trigger or _MIN_CANVAS_THEMES
    min_moments_for_fill = min_moments_trigger or _MIN_CANVAS_CANDIDATE_MOMENTS

    themes = list(parsed_canvas.themes)
    if len(themes) < min_themes_for_fill:
        for i, ch in enumerate(compression.chunks):
            if len(themes) >= max_themes:
                break
            summary_preview = ch.summary.strip()[:80]
            if len(summary_preview) < 20:
                continue
            label = summary_preview.split(".")[0][:40].strip() or f"chunk_{i}"
            themes.append(
                CanvasTheme(
                    id=f"t_fallback_{i}",
                    label=label,
                    description=summary_preview,
                    strength=0.5,
                    first_mention_sec=ch.time_range_sec[0],
                    last_mention_sec=ch.time_range_sec[1],
                )
            )

    moments = list(parsed_canvas.candidate_moments)
    if len(moments) < min_moments_for_fill:
        idx = 0
        for ch in compression.chunks:
            if len(moments) >= max_moments:
                break
            for q in ch.notable_quotes:
                if len(moments) >= max_moments:
                    break
                idx += 1
                start = max(0.0, q.sec - 2.0)
                end = min(source_duration_sec, q.sec + 8.0)
                if end <= start:
                    continue
                one_liner = q.quote.strip()[:120]
                if not one_liner:
                    continue
                moments.append(
                    CanvasCandidateMoment(
                        id=f"mo_fallback_{idx}",
                        speaker=q.speaker,
                        start=start,
                        end=end,
                        one_liner=one_liner,
                        kind="peak",
                        strength=0.6,
                    )
                )
            for p in ch.emotional_peaks:
                if len(moments) >= max_moments:
                    break
                idx += 1
                start = max(0.0, p.sec - 3.0)
                end = min(source_duration_sec, p.sec + 10.0)
                if end <= start:
                    continue
                note = p.note.strip()[:120] or f"{p.kind} peak"
                kind: Literal["peak", "setup"] = (
                    "peak" if p.kind in {"surprise", "triumph", "anger"} else "setup"
                )
                moments.append(
                    CanvasCandidateMoment(
                        id=f"mo_peak_{idx}",
                        speaker=None,
                        start=start,
                        end=end,
                        one_liner=note,
                        kind=kind,
                        strength=0.65,
                    )
                )

    tone_map = list(parsed_canvas.tone_map)
    if len(tone_map) < _MIN_CANVAS_TONE_MAP:
        tone_map = []
        for ch in compression.chunks:
            start, end = ch.time_range_sec
            if end <= start:
                continue
            tone_map.append(
                CanvasToneRange(
                    sec_range=(start, end),
                    mood="setup",
                    intensity=0.5,
                )
            )

    spine = list(parsed_canvas.chronological_spine)
    if not spine:
        for ch in compression.chunks:
            ts = int(ch.time_range_sec[0])
            summary_line = ch.summary.strip()[:100]
            if summary_line:
                spine.append(f"{ts}s: {summary_line}")

    return parsed_canvas.model_copy(
        update={
            "central_theme": central or "тема не определена",
            "themes": themes,
            "candidate_moments": moments,
            "tone_map": tone_map,
            "chronological_spine": spine,
        }
    )


#: Длительность одного эпизода в секундах. 10 мин = естественная единица
#: контент-главы (YouTube часто разбивает на такие chapters, GetCourse
#: секция ~ 10-15 мин). Для видео < EPISODE_TARGET_SEC получаем 1 эпизод.
_EPISODE_TARGET_SEC = 600.0
#: Порог срабатывания episode-builder: короткие видео (< 20 мин) не нуждаются
#: в эпизодах — фраза canvas уже локальна. Для них возвращаем [].
_EPISODE_MIN_SOURCE_DURATION_SEC = 1200.0


def _build_episodes_heuristic(
    canvas: ProjectCanvas,
    source_duration_sec: float,
) -> list[CanvasEpisode]:
    """Эвристически строит CanvasEpisode группы из candidate_moments.

    Алгоритм:
    1. Для source_duration < 20 мин → [] (canvas flat, эпизоды не нужны).
    2. Делим источник на bucket'ы по ``_EPISODE_TARGET_SEC`` (10 мин).
    3. Распределяем moments по bucket'ам через start-время.
    4. Для каждого непустого bucket'а собираем top-5 theme_id по count,
       moment_ids и короткий summary (join one_liner первых 3 moments).

    O(N) по moments + O(K) по эпизодам (K = ceil(duration / bucket)).
    """
    if source_duration_sec < _EPISODE_MIN_SOURCE_DURATION_SEC:
        return []
    if not canvas.candidate_moments:
        return []

    episode_count = max(1, int(source_duration_sec / _EPISODE_TARGET_SEC) + 1)
    actual_duration = source_duration_sec / episode_count
    # Иногда лучше округлить до целого размера bucket'а для читаемости.
    # actual_duration пригодится если хотим equal-size buckets.

    buckets: list[list[CanvasCandidateMoment]] = [[] for _ in range(episode_count)]
    for moment in canvas.candidate_moments:
        idx = min(
            episode_count - 1,
            int(moment.start / actual_duration),
        )
        buckets[idx].append(moment)

    # Theme frequency per bucket — вычислим через моменты (их theme_id не
    # всегда заполнен, поэтому fallback на ближайший theme по времени).
    theme_by_id = {t.id: t for t in canvas.themes}

    episodes: list[CanvasEpisode] = []
    for i, bucket_moments in enumerate(buckets):
        if not bucket_moments:
            continue
        start_sec = i * actual_duration
        end_sec = min(source_duration_sec, (i + 1) * actual_duration)

        # Тематики: считаем count theme_id по всем темам canvas где
        # first_mention_sec попадает в диапазон эпизода.
        episode_themes: list[tuple[str, float]] = []
        for t in canvas.themes:
            if t.status == "excluded":
                continue
            if start_sec <= t.first_mention_sec <= end_sec:
                episode_themes.append((t.id, t.strength))
        episode_themes.sort(key=lambda x: x[1], reverse=True)
        theme_ids = [tid for tid, _ in episode_themes[:5]]

        # Summary: топ-3 one_liner от сильнейших moments эпизода.
        strong_moments = sorted(
            bucket_moments, key=lambda m: m.strength, reverse=True
        )[:3]
        summary_parts: list[str] = []
        for m in strong_moments:
            ol = (m.one_liner or "").strip()
            if ol:
                summary_parts.append(ol)
        if not summary_parts and theme_ids:
            label_parts = [
                theme_by_id[tid].label for tid in theme_ids if tid in theme_by_id
            ]
            if label_parts:
                summary_parts.append(", ".join(label_parts[:3]))
        summary = " | ".join(summary_parts)[:400]

        episodes.append(
            CanvasEpisode(
                id=f"ep{i}",
                time_range_sec=(round(start_sec, 1), round(end_sec, 1)),
                theme_ids=theme_ids,
                moment_ids=[m.id for m in bucket_moments],
                summary=summary,
            )
        )
    return episodes


def _clamp_unit(value: object) -> float:
    try:
        f = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, f))


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return max(0.0, float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _normalize_moment_kind(
    value: object,
) -> Literal["hook", "peak", "payoff", "setup", "cutaway"]:
    s = str(value or "").lower()
    if s in _VALID_MOMENT_KINDS:
        return cast(Literal["hook", "peak", "payoff", "setup", "cutaway"], s)
    return "setup"


def _normalize_mood(
    value: object,
) -> Literal[
    "setup", "nostalgic", "tense", "triumphant", "contemplative",
    "energetic", "melancholic", "anxious", "joyful", "confessional",
]:
    s = str(value or "").lower()
    if s in _VALID_MOODS:
        return cast(
            Literal[
                "setup", "nostalgic", "tense", "triumphant", "contemplative",
                "energetic", "melancholic", "anxious", "joyful", "confessional",
            ],
            s,
        )
    return "setup"
