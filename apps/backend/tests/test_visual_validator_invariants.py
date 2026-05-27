"""Invariant-тесты visual_validator (PHASE 4.4).

Фиксируют главный инвариант: vision disabled → пайплайн работает как раньше.
"""

from __future__ import annotations

import typing
from pathlib import Path

import pytest

from videomaker.models.story_script import (
    SegmentRole,
    StoryScript,
    StorySegment,
    VisualFlag,
)
from videomaker.services.visual_validator import validate_arc


def _mk_segment(
    *,
    role: SegmentRole = "hook",
    start: float = 0.0,
    end: float = 3.0,
) -> StorySegment:
    return StorySegment(
        role=role,
        evidence_id=f"ev_{int(start)}",
        source_start_sec=start,
        source_end_sec=end,
        text_preview="test",
        emotional_beat="neutral",
    )


def _mk_script(segments: list[StorySegment]) -> StoryScript:
    return StoryScript(central_theme="test", arc=segments)


@pytest.mark.asyncio
async def test_validate_arc_with_none_client_returns_unchanged_script() -> None:
    """ИНВАРИАНТ: vision disabled (client=None) → script immutable.

    Это главный safety-net. Любое изменение этого поведения должно быть
    сознательным — фиксируем тестом, чтобы случайный refactor не сломал
    backward compatibility.
    """
    script = _mk_script(
        [
            _mk_segment(role="hook", start=0.0, end=3.0),
            _mk_segment(role="development", start=10.0, end=15.0),
            _mk_segment(role="payoff", start=30.0, end=33.0),
        ]
    )
    original_segments = list(script.arc)
    original_scores = [s.visual_score for s in original_segments]
    original_centering = [s.face_centering_score for s in original_segments]
    original_flags = [list(s.visual_flags) for s in original_segments]

    result = await validate_arc(
        script,
        video_path=Path("/tmp/nonexistent.mp4"),
        video_hash="fake_hash",
        client=None,
        extractor=None,  # type: ignore[arg-type]
        cache=None,  # type: ignore[arg-type]
        limiter=None,  # type: ignore[arg-type]
    )

    assert result is script or len(result.arc) == len(original_segments)
    for seg, orig_score, orig_cent, orig_flags in zip(
        result.arc, original_scores, original_centering, original_flags
    ):
        assert seg.visual_score == orig_score
        assert seg.face_centering_score == orig_cent
        assert seg.visual_flags == orig_flags


@pytest.mark.asyncio
async def test_validate_arc_with_empty_arc_returns_immediately() -> None:
    """Пустой arc не валится. Защищает от early-cases в pipeline."""
    script = StoryScript(central_theme="test", arc=[])
    result = await validate_arc(
        script,
        video_path=Path("/tmp/nonexistent.mp4"),
        video_hash="fake_hash",
        client=None,
        extractor=None,  # type: ignore[arg-type]
        cache=None,  # type: ignore[arg-type]
        limiter=None,  # type: ignore[arg-type]
    )
    assert result.arc == []


def test_off_center_flag_is_a_valid_visual_flag_literal() -> None:
    """Гарантирует что новый off_center flag прошёл в Literal VisualFlag."""
    allowed = typing.get_args(VisualFlag)
    assert "off_center" in allowed


def test_story_segment_default_face_centering_score_is_one() -> None:
    """Default=1.0: segments без vision-validation не штрафуются."""
    seg = _mk_segment()
    assert seg.face_centering_score == 1.0
