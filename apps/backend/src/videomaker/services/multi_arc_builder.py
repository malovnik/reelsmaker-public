"""Multi-arc builder — variant A of bottom_up pipeline.

Для каждого ``ProjectCanvas.candidate_moments`` строит независимый
``StoryScript`` через reuse ``compose_story_script`` с отфильтрованным
evidence window вокруг центра moment'а. Возвращает list[StoryScript]
для downstream composer (M3+M4 интеграция).

Feature flag: ``PerformanceSettings.multi_arc_enabled``. Когда False —
функция не вызывается, pipeline работает в legacy single-arc mode.

Verified signatures (code read at implementation time, commit 609a6f1):

- ``compose_story_script(canvas: ProjectCanvas, ranked: RankedEvidence, *,
  client: LLMClient | None = None, rate_limiter: RateLimiter | None = None,
  mode: str = "dialogue", rhythm_critique: str | None = None,
  pipeline_provider: str | None = None) -> StoryScript`` — async. НЕ принимает
  ``cfg`` (использует ``get_settings()`` внутри).
- ``ProjectCanvas.candidate_moments: list[CanvasCandidateMoment]``.
- ``CanvasCandidateMoment`` fields: ``id: str``, ``start: float``,
  ``end: float``, ``kind``, ``strength``, ``status``, ``one_liner``,
  ``speaker`` (НЕ ``start_sec``/``end_sec``).
- ``RankedEvidence.items: list[RankedEvidenceItem]``.
- ``RankedEvidenceItem`` time fields: ``start: float``, ``end: float``
  (НЕ ``start_sec``/``end_sec``).
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import TYPE_CHECKING

from videomaker.core.logging import get_logger
from videomaker.models.evidence import RankedEvidence, RankedEvidenceItem
from videomaker.services.story_doctor import compose_story_script

if TYPE_CHECKING:
    from videomaker.models.canvas import CanvasCandidateMoment, ProjectCanvas
    from videomaker.models.story_script import StoryScript

log = get_logger(__name__)

_DEFAULT_PARALLEL_MAX = 10


def _filter_evidence_by_moment(
    ranked: RankedEvidence,
    moment: CanvasCandidateMoment,
    window_sec: float,
) -> RankedEvidence:
    """Возвращает ``RankedEvidence`` из items временно пересекающихся с окном
    ``[moment.start - window_sec, moment.end + window_sec]``.

    Intersection check — стандартный overlap: item.start < window.end AND
    item.end > window.start. Это позволяет moment'у с коротким окном
    подхватить evidence, частично выходящее за границы.

    Метаданные ``deduped_count``/``merged_scene_count`` не переносим — они
    относятся к глобальному reducer pass, а не к subset'у окна.
    """
    window_start = max(0.0, moment.start - window_sec)
    window_end = moment.end + window_sec

    nearby: list[RankedEvidenceItem] = [
        item
        for item in ranked.items
        if item.start < window_end and item.end > window_start
    ]
    return RankedEvidence(items=nearby)


async def _build_single_arc(
    canvas: ProjectCanvas,
    moment: CanvasCandidateMoment,
    ranked: RankedEvidence,
    pipeline_provider: str | None,
    window_sec: float,
    window_fallback_sec: float,
    min_evidence: int,
    semaphore: asyncio.Semaphore,
) -> StoryScript | None:
    """Строит один arc для moment. Возвращает None если evidence insufficient
    или compose_story_script вернул пустую арку.

    Провайдер LLM (Gemini vs Zhipu) пробрасывается через ``pipeline_provider``
    в ``compose_story_script``, который уже содержит логику tier matrix.
    """
    async with semaphore:
        nearby = _filter_evidence_by_moment(ranked, moment, window_sec)
        if len(nearby.items) < min_evidence and window_fallback_sec > window_sec:
            nearby = _filter_evidence_by_moment(ranked, moment, window_fallback_sec)
        # Iteration 2026-04-21 night: soft minimum. Если user поставил
        # min_evidence=5, но в окне 2-3 item — всё равно строим (ранее
        # skip резал 28 из 40 moments). HARD_MIN=2 — ниже смысла нет
        # (story_doctor не построит arc с 0-1 evidence). Это ломает
        # strict behavior ради overproduction: каждый canvas moment
        # получает arc (даже слабый), ranking в composer отберёт сильные.
        hard_min_evidence = 2
        if len(nearby.items) < hard_min_evidence:
            log.warning(
                "multi_arc_skip_moment",
                moment_id=moment.id,
                evidence_count=len(nearby.items),
                hard_min=hard_min_evidence,
                window_sec=window_sec,
                window_fallback_sec=window_fallback_sec,
            )
            return None
        if len(nearby.items) < min_evidence:
            log.info(
                "multi_arc_build_with_low_evidence",
                moment_id=moment.id,
                evidence_count=len(nearby.items),
                user_threshold=min_evidence,
                hard_min=hard_min_evidence,
            )

        try:
            # Multi_arc передаёт loose quality gate (1 seg / 10s вместо
            # default 3 / 20s). Per-moment evidence window узкий — LLM
            # строит короткие валидные арки (2-3 seg / 30-40s), но default
            # threshold триггерил fallback_script который собирает evidence
            # со всего видео (вне moment window) → несвязные тексты рилсов.
            # Loose values: fallback trigger'ится только при full LLM failure
            # (exception path), иначе доверяем LLM output как есть.
            script = await compose_story_script(
                canvas,
                nearby,
                pipeline_provider=pipeline_provider,
                min_arc_segments=1,
                min_arc_duration_sec=10.0,
            )
        except Exception:
            log.exception(
                "multi_arc_build_failed",
                moment_id=moment.id,
            )
            return None

        if not script or not script.arc:
            log.warning(
                "multi_arc_empty_script",
                moment_id=moment.id,
            )
            return None

        log.info(
            "multi_arc_moment_arc_built",
            moment_id=moment.id,
            arc_len=len(script.arc),
            duration_sec=round(script.predicted_duration_sec, 1),
            evidence_count=len(nearby.items),
            window_sec=window_sec,
        )
        return script


async def build_arcs_per_moment(
    canvas: ProjectCanvas,
    ranked: RankedEvidence,
    *,
    pipeline_provider: str | None = None,
    window_sec: float = 60.0,
    window_fallback_sec: float = 120.0,
    min_evidence: int = 5,
    max_arcs: int | None = None,
    parallel_max: int = _DEFAULT_PARALLEL_MAX,
    window_scales: Sequence[float] | None = None,
) -> list[StoryScript]:
    """Для каждого candidate_moment из ``canvas.candidate_moments`` строит
    независимый ``StoryScript``.

    Возвращает list в порядке соответствующем исходным moments, но без
    None-значений (moments у которых не хватило evidence или LLM вернул
    пустую арку — выпадают).

    Параметры:
    - ``window_sec`` — основное полуокно вокруг moment для фильтрации.
    - ``window_fallback_sec`` — расширенное полуокно, применяется если
      в основном окне < ``min_evidence`` items.
    - ``min_evidence`` — порог evidence items в окне чтобы строить arc.
    - ``max_arcs`` — верхняя граница числа moments (None = все).
    - ``parallel_max`` — максимум concurrent LLM calls (rate-limit guard).
    - ``pipeline_provider`` — ``"gemini"`` | ``"zhipu"`` | None.
    - ``window_scales`` — multi-angle overproduction: для каждого moment
      строится по одному arc на каждый scale (window применяется как
      ``window_sec * scale``). ``None`` или ``(1.0,)`` = legacy single-angle.
      Пример ``(1.0, 2.0)`` даёт 2 арки per moment: узкий фокус +
      расширенный контекст. Cap budget применяется к moments, не arcs.

    Если ``canvas.candidate_moments`` пуст — возвращается ``[]`` без LLM вызовов.
    """
    moments = list(canvas.candidate_moments)
    if max_arcs is not None and max_arcs > 0:
        moments = moments[:max_arcs]

    if not moments:
        log.info("multi_arc_no_moments")
        return []

    scales: tuple[float, ...] = tuple(window_scales) if window_scales else (1.0,)
    if not scales:
        scales = (1.0,)

    semaphore = asyncio.Semaphore(max(1, parallel_max))
    tasks = [
        _build_single_arc(
            canvas,
            moment,
            ranked,
            pipeline_provider,
            window_sec * scale,
            window_fallback_sec * scale,
            min_evidence,
            semaphore,
        )
        for moment in moments
        for scale in scales
    ]
    results = await asyncio.gather(*tasks)
    arcs: list[StoryScript] = [r for r in results if r is not None]

    log.info(
        "multi_arc_build_complete",
        moments_count=len(moments),
        angles_per_moment=len(scales),
        arc_candidates=len(tasks),
        arcs_built=len(arcs),
        skipped=len(tasks) - len(arcs),
        window_sec=window_sec,
        window_fallback_sec=window_fallback_sec,
        window_scales=list(scales),
        min_evidence=min_evidence,
        parallel_max=parallel_max,
    )
    return arcs
