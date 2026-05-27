"""Map-Reduce Narrative Orchestrator — Phase 8.

Заменяет per-chapter top-down (chapter_builder→hook_detector→arc_finder)
на Map-Reduce architecture по research OpusClip 2026:

    transcript → global_context (1 call) → chunks scored in parallel (N calls)
    → deterministic dedup (temporal + Jaccard) → LLM reducer (1 call)
    → boundary_extender → ReelPlan[]

Research basis: docs/opusclip-2026-research.md
    - OpusClip density: 1 clip / 2 min (short chunks) → 1 clip / 4 min (long single-pass)
    - Chunks 20K chars с overlap 2K, parallel asyncio.gather
    - response_schema enforced на каждом LLM call (Flash Lite 7x verbosity)
    - Target count = duration_min / 2 (OpusClip density-based)

Feature flag: ``narrative_mode`` в PerformanceSettings:
    - "bottom_up" — legacy 9-stage extraction pipeline (default)
    - "chaptered" — мой broken per-chapter top-down (Phase 1-6)
    - "map_reduce" — этот оркестратор (Phase 8, OpusClip-parity)

Entry: ``orchestrate_map_reduce(transcript, canvas, *, source_duration_sec,
target_count, settings, pipeline_provider, artifact_store, job_id,
llm_pro_model) -> AnalysisResult``
"""

from __future__ import annotations

import collections
from pathlib import Path
from typing import Literal

from videomaker.core.artifacts import ArtifactsManager
from videomaker.core.config import Settings
from videomaker.core.logging import get_logger
from videomaker.models.canvas import ProjectCanvas
from videomaker.models.narrative import ExtendedArc, HookCandidate, NarrativeArc
from videomaker.models.reel_plan import AnalysisResult, ReelPlan, ReelSegment
from videomaker.services.narrative.boundary_extender import extend_boundaries
from videomaker.services.narrative.chunk_scorer import (
    ChunkDiagnostic,
    GlobalContext,
    RawClipCandidate,
    score_chunks,
)
from videomaker.services.narrative.clip_reducer import reduce_and_rank
from videomaker.services.narrative.global_context_builder import build_global_context
from videomaker.services.transcribers.base import TranscriptResult

log = get_logger(__name__)

#: Density: 1 clip per CLIP_DENSITY_MINUTES of video.
#: OpusClip observed: короткие chunks (30мин) → 1 clip / 2 min.
#: 5h → цель ~150 clips.
_CLIP_DENSITY_MINUTES: float = 2.0

#: Upper safety cap на target count (защита от absurd requests).
_MAX_TARGET_CLIPS: int = 300

#: Lower bound — target не может быть ниже этого (короткие видео).
_MIN_TARGET_CLIPS: int = 3


async def orchestrate_map_reduce(
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
    """Map-Reduce entry для top-down pipeline.

    Args:
        transcript: TranscriptResult с segments/words.
        canvas: ProjectCanvas — используется для stats и central_theme fallback.
        source_duration_sec: длительность source видео.
        target_count: user-requested number of reels. Если ≤ 0 — рассчитывается
            автоматически (duration_min / 2, default OpusClip density).
        settings: Settings.
        pipeline_provider: LLM provider (gemini).
        artifact_store: для dump промежуточных артефактов.
        job_id: job identifier.
        llm_pro_model: имя Pro модели (для stats).

    Returns:
        AnalysisResult с reels, llm_model, provider, stats.
    """

    effective_target = _compute_effective_target(target_count, source_duration_sec)

    log.info(
        "map_reduce_orchestrator_start",
        job_id=job_id,
        source_duration_min=round(source_duration_sec / 60.0, 1),
        user_target=target_count,
        effective_target=effective_target,
        provider=pipeline_provider,
    )

    # Stage 1: Global Context (1 LLM call, Flash Lite).
    global_context = await build_global_context(
        transcript,
        settings=settings,
        provider_override=pipeline_provider,
    )
    if not global_context.central_theme and canvas.central_theme:
        # Fallback: если LLM не вывел central_theme, используем из canvas.
        global_context = GlobalContext(
            central_theme=canvas.central_theme,
            key_topics=[t.label for t in canvas.themes[:8]],
            speaker_role=global_context.speaker_role,
            video_structure=global_context.video_structure,
            language=global_context.language,
            tone=global_context.tone,
        )

    _dump_global_context(artifact_store, job_id, global_context)
    log.info(
        "map_reduce_global_context_done",
        job_id=job_id,
        theme_len=len(global_context.central_theme),
        topics=len(global_context.key_topics),
    )

    # Stage 2: Parallel chunk scoring (MAP phase).
    raw_candidates, chunk_diagnostics = await score_chunks(
        transcript,
        global_context,
        settings=settings,
        provider_override=pipeline_provider,
    )
    _dump_raw_candidates(artifact_store, job_id, raw_candidates)
    _dump_chunk_diagnostics(artifact_store, job_id, chunk_diagnostics)

    if not raw_candidates:
        log.warning("map_reduce_no_raw_candidates", job_id=job_id)
        return _empty_analysis(
            llm_pro_model,
            pipeline_provider,
            {
                "narrative_mode": "map_reduce",
                "reason": "no_raw_candidates",
                "target_count": effective_target,
            },
        )

    # Stage 3: REDUCE phase (dedup + LLM curation + ranking).
    final_candidates = await reduce_and_rank(
        raw_candidates,
        global_context,
        transcript,
        target_count=effective_target,
        settings=settings,
        provider_override=pipeline_provider,
    )
    _dump_final_candidates(artifact_store, job_id, final_candidates)

    if not final_candidates:
        log.warning("map_reduce_no_final_candidates", job_id=job_id)
        return _empty_analysis(
            llm_pro_model,
            pipeline_provider,
            {
                "narrative_mode": "map_reduce",
                "reason": "no_final_candidates_after_reduce",
                "raw_count": len(raw_candidates),
                "target_count": effective_target,
            },
        )

    # Stage 4: Convert RawClipCandidate → NarrativeArc → ExtendedArc.
    arcs = [_raw_to_narrative_arc(c) for c in final_candidates]
    extended_arcs = extend_boundaries(arcs, transcript)
    _dump_extended_arcs(artifact_store, job_id, extended_arcs)

    # Stage 5: ExtendedArc → ReelPlan.
    reels = [
        _extended_to_reel_plan(ext, rank=idx + 1, raw=final_candidates[idx])
        for idx, ext in enumerate(extended_arcs)
    ]

    stats = _build_stats(
        raw_count=len(raw_candidates),
        final_count=len(final_candidates),
        reels_count=len(reels),
        target_count=effective_target,
        user_target=target_count,
        source_duration_sec=source_duration_sec,
        global_context=global_context,
        final_candidates=final_candidates,
    )

    log.info(
        "map_reduce_orchestrator_done",
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


# ─── Target count computation ─────────────────────────────────────────────


def _compute_effective_target(
    user_target: int,
    source_duration_sec: float,
) -> int:
    """Авто-рассчитывает target если user не задал (или задал 0).

    OpusClip density: 1 clip / 2 min → density-based target.
    """

    if user_target and user_target > 0:
        return min(_MAX_TARGET_CLIPS, max(_MIN_TARGET_CLIPS, user_target))

    duration_min = source_duration_sec / 60.0
    density_target = round(duration_min / _CLIP_DENSITY_MINUTES)
    return max(_MIN_TARGET_CLIPS, min(_MAX_TARGET_CLIPS, density_target))


# ─── Conversion: RawClipCandidate → NarrativeArc → ReelPlan ───────────────


def _raw_to_narrative_arc(raw: RawClipCandidate) -> NarrativeArc:
    """Конвертирует RawClipCandidate в NarrativeArc для совместимости с
    existing boundary_extender + ranker.
    """

    chapter_id = f"chunk_{raw.chunk_index:03d}"
    hook = HookCandidate(
        chapter_id=chapter_id,
        hook_start_sec=raw.start_sec,
        hook_end_sec=min(raw.start_sec + 8.0, raw.end_sec),
        text=raw.hook,
        score=raw.score / 10.0,
        why=raw.why,
        hook_kind=_coerce_hook_kind(raw.hook_kind),
    )

    return NarrativeArc(
        chapter_id=chapter_id,
        hook=hook,
        clip_start_sec=raw.start_sec,
        clip_end_sec=raw.end_sec,
        closure_type=raw.closure_type,
        development_sentences=[],
        payoff_text=raw.payoff,
        coherence_score=min(1.0, raw.score / 10.0),
        arc_score=min(1.0, raw.score / 10.0),
    )


_HookKindLiteral = Literal[
    "question",
    "bold_claim",
    "counter_intuitive",
    "emotional_trigger",
    "pattern_break",
    "stat_shock",
]


def _coerce_hook_kind(raw_kind: str) -> _HookKindLiteral:
    """Map RawClipCandidate.hook_kind (7 enum) → HookCandidate.hook_kind (6 enum).

    RawClipCandidate содержит дополнительно "story_open" которого нет в
    HookCandidate. Маппим на семантически ближайший emotional_trigger.
    """

    mapping: dict[str, _HookKindLiteral] = {
        "question": "question",
        "bold_claim": "bold_claim",
        "counter_intuitive": "counter_intuitive",
        "emotional_trigger": "emotional_trigger",
        "pattern_break": "pattern_break",
        "stat_shock": "stat_shock",
        "story_open": "emotional_trigger",  # Алиас — нет в HookCandidate.
    }
    return mapping.get(raw_kind, "bold_claim")


def _extended_to_reel_plan(
    ext: ExtendedArc,
    *,
    rank: int,
    raw: RawClipCandidate,
) -> ReelPlan:
    """ExtendedArc → ReelPlan. Single segment, no padding."""

    segment = ReelSegment(
        source_start=ext.adjusted_start_sec,
        source_end=ext.adjusted_end_sec,
        reasoning=(
            f"map_reduce: hook_kind={raw.hook_kind}, closure={raw.closure_type}, "
            f"score={raw.score}, rank={rank}, topic='{raw.topic[:60]}'"
        )[:500],
        order_role="hook",
    )

    composite_score = raw.score * 10.0  # 0-100 scale

    return ReelPlan(
        reel_id=f"reel_{rank:03d}",
        hook=(raw.hook or raw.topic or f"Рилс {rank}")[:240],
        predicted_duration_sec=ext.duration_sec(),
        target_audience="",
        segments=[segment],
        rhythm_score=None,
        visual_score=None,
        narrative_score=raw.score / 10.0,
        composite_score=composite_score,
        cross_context_risk=None,
    )


# ─── Artifact dumps ───────────────────────────────────────────────────────


def _dump_global_context(
    art: ArtifactsManager,
    job_id: str,
    ctx: GlobalContext,
) -> Path:
    return art.write_json(
        job_id,
        "global_context.json",
        ctx.model_dump(mode="json"),
    )


def _dump_raw_candidates(
    art: ArtifactsManager,
    job_id: str,
    candidates: list[RawClipCandidate],
) -> Path:
    return art.write_json(
        job_id,
        "map_raw_candidates.json",
        {
            "count": len(candidates),
            "candidates": [c.model_dump(mode="json") for c in candidates],
        },
    )


def _dump_chunk_diagnostics(
    art: ArtifactsManager,
    job_id: str,
    diagnostics: list[ChunkDiagnostic],
) -> Path:
    """Dumps per-chunk stats: start/end/chars/raw_items/valid_items/error/scores.

    Критично для debug когда pipeline выдаёт мало clips — показывает в каком
    chunk'е LLM упал, что вернул, что отсеялось при validation.
    """

    return art.write_json(
        job_id,
        "chunk_diagnostics.json",
        {
            "chunk_count": len(diagnostics),
            "total_raw_items": sum(d.raw_items for d in diagnostics),
            "total_valid_items": sum(d.valid_items for d in diagnostics),
            "chunks_with_errors": sum(1 for d in diagnostics if d.error),
            "chunks": [d.to_dict() for d in diagnostics],
        },
    )


def _dump_final_candidates(
    art: ArtifactsManager,
    job_id: str,
    candidates: list[RawClipCandidate],
) -> Path:
    return art.write_json(
        job_id,
        "reduce_final_candidates.json",
        {
            "count": len(candidates),
            "candidates": [c.model_dump(mode="json") for c in candidates],
        },
    )


def _dump_extended_arcs(
    art: ArtifactsManager,
    job_id: str,
    extended: list[ExtendedArc],
) -> Path:
    return art.write_json(
        job_id,
        "map_reduce_arcs.json",
        {
            "count": len(extended),
            "arcs": [e.model_dump(mode="json") for e in extended],
        },
    )


# ─── Stats helpers ────────────────────────────────────────────────────────


def _build_stats(
    *,
    raw_count: int,
    final_count: int,
    reels_count: int,
    target_count: int,
    user_target: int,
    source_duration_sec: float,
    global_context: GlobalContext,
    final_candidates: list[RawClipCandidate],
) -> dict[str, int | float | str | None]:
    durations = [c.duration_sec() for c in final_candidates]
    closure_dist: collections.Counter[str] = collections.Counter(
        c.closure_type for c in final_candidates
    )
    hook_kind_dist: collections.Counter[str] = collections.Counter(
        c.hook_kind for c in final_candidates
    )

    density_per_min = (
        round(reels_count / (source_duration_sec / 60.0), 2)
        if source_duration_sec > 0
        else 0.0
    )

    return {
        "narrative_mode": "map_reduce",
        "raw_candidates": raw_count,
        "final_candidates": final_count,
        "reels_count": reels_count,
        "user_target": user_target,
        "effective_target": target_count,
        "density_clips_per_min": density_per_min,
        "median_duration_sec": _median(durations),
        "min_duration_sec": round(min(durations), 1) if durations else 0.0,
        "max_duration_sec": round(max(durations), 1) if durations else 0.0,
        "closure_distribution": ",".join(
            f"{k}:{v}" for k, v in closure_dist.most_common()
        ),
        "hook_kind_distribution": ",".join(
            f"{k}:{v}" for k, v in hook_kind_dist.most_common()
        ),
        "central_theme": global_context.central_theme[:120],
        "key_topics_count": len(global_context.key_topics),
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
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2 == 1:
        return round(s[mid], 1)
    return round((s[mid - 1] + s[mid]) / 2, 1)


__all__ = ["orchestrate_map_reduce"]
