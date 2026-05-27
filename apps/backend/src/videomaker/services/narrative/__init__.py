"""Top-down narrative pipeline.

Replaces legacy bottom-up assembly (extraction agents → reducer →
story_doctor → composer padding) with OpusClip-style architecture:

    chapter_builder → hook_detector → arc_finder → boundary_extender →
    cross_chapter_ranker → ReelCandidate

Включается через ``PerformanceSettings.narrative_mode = "top_down"``.
См. ``docs/top-down-architecture-roadmap.md`` для phased implementation
плана и ``docs/viral-clipper-research-2026-04-21.md`` для research basis.
"""

from __future__ import annotations

from videomaker.services.narrative.constants import (
    ARC_COHERENCE_MIN,
    ARC_DEVELOPMENT_MAX_SENTENCES,
    ARC_DEVELOPMENT_MIN_SENTENCES,
    CHAPTER_BUILDER_LLM_WINDOW_SEC,
    CHAPTER_BUILDER_SIMILARITY_THRESHOLD,
    CLOSURE_TYPE_MAX_PER_RANK,
    DISCOURSE_MARKER_FORWARD_SEC,
    HOOK_MAX_DURATION_SEC,
    HOOK_MIN_DURATION_SEC,
    HOOK_POSITION_WINDOW_RATIO,
    MAX_CHAPTER_DURATION_SEC,
    MAX_CLOSURE_EXTENSION_SEC,
    MIN_CHAPTER_DURATION_SEC,
    NOVELTY_COSINE_THRESHOLD,
    REEL_MAX_DURATION_SEC,
    REEL_MIN_DURATION_SEC,
    REEL_TARGET_DURATION_SEC,
    SILENCE_THRESHOLD_SEC,
)

__all__ = [
    "ARC_COHERENCE_MIN",
    "ARC_DEVELOPMENT_MAX_SENTENCES",
    "ARC_DEVELOPMENT_MIN_SENTENCES",
    "CHAPTER_BUILDER_LLM_WINDOW_SEC",
    "CHAPTER_BUILDER_SIMILARITY_THRESHOLD",
    "CLOSURE_TYPE_MAX_PER_RANK",
    "DISCOURSE_MARKER_FORWARD_SEC",
    "HOOK_MAX_DURATION_SEC",
    "HOOK_MIN_DURATION_SEC",
    "HOOK_POSITION_WINDOW_RATIO",
    "MAX_CHAPTER_DURATION_SEC",
    "MAX_CLOSURE_EXTENSION_SEC",
    "MIN_CHAPTER_DURATION_SEC",
    "NOVELTY_COSINE_THRESHOLD",
    "REEL_MAX_DURATION_SEC",
    "REEL_MIN_DURATION_SEC",
    "REEL_TARGET_DURATION_SEC",
    "SILENCE_THRESHOLD_SEC",
]
