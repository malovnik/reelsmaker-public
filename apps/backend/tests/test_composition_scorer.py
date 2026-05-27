"""Smoke-тесты geometric face centering score (PHASE 4.1)."""

from __future__ import annotations

import pytest

from videomaker.services.composition_scorer import (
    MAX_DEVIATION,
    OFF_CENTER_THRESHOLD,
    compute_face_centering_score,
    is_off_center,
)
from videomaker.services.face_tracker import FaceBBox, FaceTrackResult, FrameDetection


def _bbox_at_center(cx: float, cy: float, size: float = 0.2) -> FaceBBox:
    """Helper: bbox с заданным центром."""
    return FaceBBox(
        x=cx - size / 2,
        y=cy - size / 2,
        w=size,
        h=size,
        confidence=0.9,
    )


def _track(detections: list[FrameDetection]) -> FaceTrackResult:
    return FaceTrackResult(
        video_path="/tmp/f.mp4",
        video_hash="h",
        sample_interval_sec=0.5,
        frame_width=1920,
        frame_height=1080,
        detections=detections,
    )


def test_none_track_returns_neutral_one() -> None:
    assert compute_face_centering_score(None, 1.0) == 1.0


def test_empty_track_returns_neutral_one() -> None:
    assert compute_face_centering_score(_track([]), 1.0) == 1.0


def test_perfect_center_returns_one() -> None:
    track = _track(
        [FrameDetection(timestamp_sec=1.0, faces=[_bbox_at_center(0.5, 0.5)])]
    )
    score = compute_face_centering_score(track, 1.0)
    assert score == pytest.approx(1.0, abs=0.01)


def test_corner_face_returns_low_score() -> None:
    track = _track(
        [FrameDetection(timestamp_sec=1.0, faces=[_bbox_at_center(0.1, 0.1)])]
    )
    score = compute_face_centering_score(track, 1.0)
    # deviation = sqrt(0.4^2 + 0.4^2) ≈ 0.566 > MAX_DEVIATION (0.5) → clamp 0
    assert score == 0.0


def test_slight_offset_gives_partial_score() -> None:
    track = _track(
        [FrameDetection(timestamp_sec=1.0, faces=[_bbox_at_center(0.55, 0.55)])]
    )
    score = compute_face_centering_score(track, 1.0)
    # deviation = sqrt(0.05^2 + 0.05^2) ≈ 0.0707 → score = 1 - 0.1414 ≈ 0.859
    assert 0.8 < score < 0.9


def test_score_monotonically_decreases_with_offset() -> None:
    """При увеличении смещения от центра score должен падать."""
    offsets = [0.0, 0.1, 0.2, 0.3, 0.4]
    scores = []
    for off in offsets:
        track = _track(
            [
                FrameDetection(
                    timestamp_sec=1.0,
                    faces=[_bbox_at_center(0.5 + off, 0.5)],
                )
            ]
        )
        scores.append(compute_face_centering_score(track, 1.0))
    for i in range(1, len(scores)):
        assert scores[i] <= scores[i - 1], f"non-monotonic at index {i}: {scores}"


def test_is_off_center_threshold() -> None:
    assert is_off_center(0.0) is True
    assert is_off_center(OFF_CENTER_THRESHOLD - 0.01) is True
    assert is_off_center(OFF_CENTER_THRESHOLD) is False
    assert is_off_center(1.0) is False


def test_no_face_in_frame_returns_neutral_one() -> None:
    """Frame без лица — не штрафуем, возвращаем baseline 1.0."""
    track = _track([FrameDetection(timestamp_sec=1.0, faces=[])])
    score = compute_face_centering_score(track, 1.0)
    assert score == 1.0


def test_max_deviation_constant_is_half() -> None:
    assert MAX_DEVIATION == 0.5
