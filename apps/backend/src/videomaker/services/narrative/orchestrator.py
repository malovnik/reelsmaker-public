"""Top-Down Narrative Orchestrator — Phase 6.

Координирует pipeline top-down narrative mode: chapters → hooks →
arcs → extended → ranked → ReelPlan'ы. Замена cross-stage assembly
bottom-up (extraction → reducer → story_doctor → variants → composer).

Этот модуль ИЗОЛИРУЕТ pipeline_stages/analysis.py от деталей narrative.
analysis.py просто вызывает ``orchestrate_top_down(...)`` и получает
``AnalysisResult``, совместимый с existing render stage.

Graceful degradation:
    - Если chapter_builder возвращает 1 главу — pipeline продолжает работать
      (будет 1-3 ReelCandidate от той главы).
    - Если hook_detector вернул empty dict — return empty AnalysisResult
      (нет рилсов, не падаем).
    - Если arc_finder вернул empty — same.
    - Если embeddings API down — cross_chapter_ranker fallback на Jaccard.
"""

from __future__ import annotations

import collections
from pathlib import Path

from videomaker.core.artifacts import ArtifactsManager
from videomaker.core.config import Settings
from videomaker.core.logging import get_logger
from videomaker.models.canvas import ProjectCanvas
from videomaker.models.narrative import (
    Chapter,
    ExtendedArc,
    HookCandidate,
    NarrativeArc,
    ReelCandidate,
)
from videomaker.models.reel_plan import AnalysisResult, ReelPlan, ReelSegment
from videomaker.services.narrative.arc_finder import find_arcs
from videomaker.services.narrative.boundary_extender import extend_boundaries
from videomaker.services.narrative.chapter_builder import build_chapters
from videomaker.services.narrative.cross_chapter_ranker import rank_and_select
from videomaker.services.narrative.hook_detector import detect_hooks
from videomaker.services.transcribers.base import TranscriptResult

log = get_logger(__name__)


async def orchestrate_top_down(
    *,
    transcript: TranscriptResult,
    canvas: ProjectCanvas,
    source_duration_sec: float,
    target_count: int,
    settings: Settings,
    pipeline_provider: str,
    artifact_store: ArtifactsManager,
    job_id: str,
    llm_pro_model: str,
) -> AnalysisResult:
    """Запускает top-down narrative pipeline.

    Args:
        transcript: TranscriptResult с segments и words.
        canvas: ProjectCanvas (используется только для observability в stats).
        source_duration_sec: длительность source видео.
        target_count: желаемое число рилсов.
        settings: Settings.
        pipeline_provider: LLM provider (gemini / zhipu).
        artifact_store: для dump промежуточных артефактов.
        job_id: job identifier.
        llm_pro_model: имя Pro модели (для stats messaging).

    Returns:
        AnalysisResult с reels, llm_model, provider, stats.
    """

    log.info(
        "top_down_orchestrator_start",
        job_id=job_id,
        source_duration_sec=round(source_duration_sec, 1),
        target_count=target_count,
        provider=pipeline_provider,
    )

    # Stage 1: Chaptering.
    chapters = await build_chapters(
        transcript,
        settings=settings,
        provider_override=pipeline_provider,
    )
    _dump_chapters(artifact_store, job_id, chapters)
    log.info(
        "top_down_chapters_built",
        job_id=job_id,
        count=len(chapters),
        sources=dict(collections.Counter(c.source for c in chapters)),
        durations=[round(c.duration_sec(), 1) for c in chapters],
    )

    if not chapters:
        log.warning("top_down_no_chapters_empty_result", job_id=job_id)
        return _empty_analysis(llm_pro_model, pipeline_provider, {
            "narrative_mode": "top_down",
            "reason": "no_chapters_built",
        })

    # Stage 2: Hook Detection (parallel per chapter).
    hooks_by_chapter = await detect_hooks(
        chapters,
        transcript,
        settings=settings,
        provider_override=pipeline_provider,
    )
    _dump_hooks(artifact_store, job_id, hooks_by_chapter)
    total_hooks = sum(len(v) for v in hooks_by_chapter.values())
    log.info(
        "top_down_hooks_detected",
        job_id=job_id,
        total_hooks=total_hooks,
        chapters_with_hooks=sum(1 for v in hooks_by_chapter.values() if v),
    )

    if total_hooks == 0:
        log.warning("top_down_no_hooks_empty_result", job_id=job_id)
        return _empty_analysis(llm_pro_model, pipeline_provider, {
            "narrative_mode": "top_down",
            "reason": "no_hooks_detected",
            "chapter_count": len(chapters),
        })

    # Stage 3: Narrative Arc Finder (Flash per chapter with Pro fallback).
    arcs = await find_arcs(
        chapters,
        hooks_by_chapter,
        transcript,
        settings=settings,
        provider_override=pipeline_provider,
    )
    log.info("top_down_arcs_found", job_id=job_id, count=len(arcs))

    if not arcs:
        log.warning("top_down_no_arcs_empty_result", job_id=job_id)
        return _empty_analysis(llm_pro_model, pipeline_provider, {
            "narrative_mode": "top_down",
            "reason": "no_arcs_found",
            "chapter_count": len(chapters),
            "total_hooks": total_hooks,
        })

    # Stage 4: Boundary Extender (deterministic).
    extended = extend_boundaries(arcs, transcript)
    log.info(
        "top_down_boundaries_extended",
        job_id=job_id,
        count=len(extended),
        avg_duration=round(
            sum(e.duration_sec() for e in extended) / max(1, len(extended)), 1
        ),
    )
    _dump_arcs(artifact_store, job_id, extended)

    # Stage 5: Cross-Chapter Ranker (greedy + diversity + novelty).
    candidates = await rank_and_select(
        extended,
        target_count=target_count,
        settings=settings,
    )
    _dump_reel_candidates(artifact_store, job_id, candidates)

    if not candidates:
        log.warning("top_down_no_candidates_empty_result", job_id=job_id)
        return _empty_analysis(llm_pro_model, pipeline_provider, {
            "narrative_mode": "top_down",
            "reason": "no_candidates_selected",
            "chapter_count": len(chapters),
            "total_hooks": total_hooks,
            "arc_count": len(arcs),
        })

    # Stage 6: ReelCandidate → ReelPlan (1-to-1 без padding).
    reels = [_candidate_to_reel_plan(c) for c in candidates]

    stats = _build_stats(
        chapters=chapters,
        arcs=arcs,
        extended=extended,
        candidates=candidates,
        hooks_by_chapter=hooks_by_chapter,
        target_count=target_count,
        canvas=canvas,
    )

    log.info(
        "top_down_orchestrator_done",
        job_id=job_id,
        reels_out=len(reels),
        median_duration=_median([r.predicted_duration_sec for r in reels]),
    )

    return AnalysisResult(
        reels=reels,
        llm_model=llm_pro_model,
        provider=pipeline_provider,
        stats=stats,
    )


# ─── ReelCandidate → ReelPlan conversion ─────────────────────────────────


def _candidate_to_reel_plan(candidate: ReelCandidate) -> ReelPlan:
    """1-to-1 конвертация без padding. Single segment на весь arc.

    В bottom-up композер создавал 2-5 segments per reel (package_of_shorts,
    thematic_cluster). В top-down arc — это единый nativeconnec narrative,
    который не должен резаться на части. Single ReelSegment покрывает
    весь arc от adjusted_start до adjusted_end.
    """

    ext = candidate.source_arc
    arc = ext.arc
    hook_text = arc.hook.text

    segment = ReelSegment(
        source_start=ext.adjusted_start_sec,
        source_end=ext.adjusted_end_sec,
        reasoning=(
            f"top_down arc: hook_kind={arc.hook.hook_kind}, "
            f"closure_type={arc.closure_type}, "
            f"coherence={arc.coherence_score:.2f}, "
            f"arc_score={arc.arc_score:.2f}"
        )[:500],
        order_role="hook",
    )

    hook_display = (hook_text or arc.payoff_text or f"Рилс {candidate.rank}")[:240]
    return ReelPlan(
        reel_id=candidate.id,
        hook=hook_display,
        predicted_duration_sec=ext.duration_sec(),
        target_audience="",
        segments=[segment],
        rhythm_score=None,
        visual_score=None,
        narrative_score=candidate.final_score,
        composite_score=round(candidate.final_score * 100, 1),
        cross_context_risk=None,
    )


# ─── Observability dumps ─────────────────────────────────────────────────


def _dump_chapters(
    art: ArtifactsManager,
    job_id: str,
    chapters: list[Chapter],
) -> Path:
    return art.write_json(
        job_id,
        "chapters.json",
        {"chapters": [c.model_dump(mode="json") for c in chapters]},
    )


def _dump_hooks(
    art: ArtifactsManager,
    job_id: str,
    hooks_by_chapter: dict[str, list[HookCandidate]],
) -> Path:
    payload = {
        "hooks_by_chapter": {
            ch_id: [h.model_dump(mode="json") for h in hooks]
            for ch_id, hooks in hooks_by_chapter.items()
        },
        "total_hooks": sum(len(v) for v in hooks_by_chapter.values()),
    }
    return art.write_json(job_id, "narrative_hooks.json", payload)


def _dump_arcs(
    art: ArtifactsManager,
    job_id: str,
    extended: list[ExtendedArc],
) -> Path:
    return art.write_json(
        job_id,
        "narrative_arcs.json",
        {
            "arcs": [e.model_dump(mode="json") for e in extended],
            "total": len(extended),
        },
    )


def _dump_reel_candidates(
    art: ArtifactsManager,
    job_id: str,
    candidates: list[ReelCandidate],
) -> Path:
    return art.write_json(
        job_id,
        "reel_candidates.json",
        {"candidates": [c.model_dump(mode="json") for c in candidates]},
    )


# ─── Stats + empty ─────────────────────────────────────────────────────────


def _build_stats(
    *,
    chapters: list[Chapter],
    arcs: list[NarrativeArc],
    extended: list[ExtendedArc],
    candidates: list[ReelCandidate],
    hooks_by_chapter: dict[str, list[HookCandidate]],
    target_count: int,
    canvas: ProjectCanvas,
) -> dict[str, int | float | str | None]:
    durations = [c.source_arc.duration_sec() for c in candidates]
    closure_distribution: collections.Counter[str] = collections.Counter(
        c.source_arc.arc.closure_type for c in candidates
    )
    return {
        "narrative_mode": "top_down",
        "chapter_count": len(chapters),
        "hook_candidates_total": sum(len(v) for v in hooks_by_chapter.values()),
        "arc_found": len(arcs),
        "extended_arcs": len(extended),
        "reel_candidates": len(candidates),
        "target_count": target_count,
        "median_duration_sec": _median(durations),
        "min_duration_sec": round(min(durations), 1) if durations else 0.0,
        "max_duration_sec": round(max(durations), 1) if durations else 0.0,
        "closure_distribution": ",".join(
            f"{k}:{v}" for k, v in closure_distribution.most_common()
        ),
        "canvas_themes_count": len(canvas.themes),
        "canvas_motifs_count": len(canvas.motifs),
    }


def _empty_analysis(
    llm_model: str,
    provider: str,
    stats: dict[str, int | float | str | None],
) -> AnalysisResult:
    return AnalysisResult(
        reels=[],
        llm_model=llm_model,
        provider=provider,
        stats=stats,
    )


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    mid = n // 2
    if n % 2 == 1:
        return round(sorted_vals[mid], 1)
    return round((sorted_vals[mid - 1] + sorted_vals[mid]) / 2, 1)


__all__ = ["orchestrate_top_down"]
