"""Unit-тесты story-script и variants pydantic-моделей."""

from __future__ import annotations

from videomaker.models.story_script import (
    StoryScript,
    StorySegment,
    StoryVariant,
    StoryVariants,
)


def _segment(
    *, role: str = "hook", start: float = 0.0, end: float = 6.0,
) -> StorySegment:
    return StorySegment(
        role=role,  # type: ignore[arg-type]
        evidence_id=f"e-{role}-{int(start)}",
        source_start_sec=start,
        source_end_sec=end,
    )


def test_segment_duration_positive() -> None:
    assert _segment(start=10, end=25).duration_sec == 15.0


def test_segment_duration_never_negative() -> None:
    seg = StorySegment(
        role="setup", evidence_id="e1",
        source_start_sec=20.0, source_end_sec=20.0,
    )
    assert seg.duration_sec == 0.0


def test_story_script_segments_by_role() -> None:
    script = StoryScript(
        central_theme="t",
        arc=[
            _segment(role="hook", start=0, end=6),
            _segment(role="development", start=10, end=30),
            _segment(role="development", start=40, end=60),
            _segment(role="payoff", start=80, end=90),
        ],
    )
    devs = script.segments_by_role("development")
    assert len(devs) == 2
    assert script.segments_by_role("peak") == []


def test_story_variants_by_kind() -> None:
    variants = StoryVariants(
        variants=[
            StoryVariant(
                id="v1", kind="punchy_summary", label="punchy",
                target_duration_sec=90, predicted_duration_sec=88,
                central_theme="t",
            ),
            StoryVariant(
                id="v2", kind="deep_dive", label="deep",
                target_duration_sec=1200, predicted_duration_sec=1150,
                central_theme="t",
            ),
        ]
    )
    assert variants.by_kind("punchy_summary") is not None
    assert variants.by_kind("punchy_summary").id == "v1"  # type: ignore[union-attr]
    assert variants.by_kind("long_philosophical") is None
