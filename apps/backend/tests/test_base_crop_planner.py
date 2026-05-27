"""Unit-тесты для face-aware первичного crop (``BaseCropPlan``).

Покрывает aspect-preserving расчёт размеров, per-cut keyframe tracking,
no-op случай (source уже в target aspect), fallback без face_track.
"""

from __future__ import annotations

import pytest

from videomaker.services.face_tracker import (
    FaceBBox,
    FaceTrackResult,
    FrameDetection,
)
from videomaker.services.media import ReelSegmentRender
from videomaker.services.zoom_planner import (
    DEFAULT_ANCHOR_X,
    DEFAULT_ANCHOR_Y,
    BaseCropPlan,
    build_base_crop_plan,
    compute_aspect_crop_dims,
)


# ─────────────── compute_aspect_crop_dims ───────────────


def test_crop_dims_landscape_to_vertical() -> None:
    # 1920x1080 (16:9) → target 9:16 (0.5625) → crop 608x1080.
    crop_w, crop_h = compute_aspect_crop_dims(1920, 1080, 9 / 16)
    assert crop_h == 1080
    assert crop_w == 608  # round(1080 * 9/16) = 607.5 → 608 (чётное)


def test_crop_dims_portrait_to_landscape() -> None:
    # 1080x1920 (9:16) → target 16:9 (1.777) → crop 1080x608.
    crop_w, crop_h = compute_aspect_crop_dims(1080, 1920, 16 / 9)
    assert crop_w == 1080
    assert crop_h == 608


def test_crop_dims_same_aspect_no_op() -> None:
    # 1920x1080 16:9 → target 16:9 → возвращаем исходные.
    crop_w, crop_h = compute_aspect_crop_dims(1920, 1080, 16 / 9)
    assert (crop_w, crop_h) == (1920, 1080)


def test_crop_dims_square_to_vertical() -> None:
    crop_w, crop_h = compute_aspect_crop_dims(1080, 1080, 9 / 16)
    assert crop_h == 1080
    assert crop_w == 608


def test_crop_dims_always_even() -> None:
    # 1919x1079 source → обе стороны чётные.
    crop_w, crop_h = compute_aspect_crop_dims(1919, 1079, 9 / 16)
    assert crop_w % 2 == 0
    assert crop_h % 2 == 0


def test_crop_dims_invalid_source_raises() -> None:
    with pytest.raises(ValueError):
        compute_aspect_crop_dims(0, 1080, 9 / 16)
    with pytest.raises(ValueError):
        compute_aspect_crop_dims(1920, 1080, 0)


# ─────────────── build_base_crop_plan ───────────────


def _face_at(cx: float, cy: float, size: float = 0.15) -> FaceBBox:
    return FaceBBox(
        x=cx - size / 2,
        y=cy - size / 2,
        w=size,
        h=size,
        confidence=0.95,
    )


def _make_track(
    *,
    samples: list[tuple[float, float, float]],
    sample_interval_sec: float = 0.3,
    frame_width: int = 1920,
    frame_height: int = 1080,
) -> FaceTrackResult:
    detections = [
        FrameDetection(timestamp_sec=t, faces=[_face_at(cx, cy)])
        for t, cx, cy in samples
    ]
    return FaceTrackResult(
        video_path="/fake",
        video_hash="a" * 64,
        sample_interval_sec=sample_interval_sec,
        frame_width=frame_width,
        frame_height=frame_height,
        detections=detections,
    )


def test_build_plan_single_segment_no_face_fallback_to_center() -> None:
    seg = ReelSegmentRender(source_start=0.0, source_end=5.0)
    plan = build_base_crop_plan(
        segments=[seg],
        face_track=None,
        source_width=1920,
        source_height=1080,
        target_aspect_ratio=9 / 16,
    )
    assert isinstance(plan, BaseCropPlan)
    assert plan.crop_width == 608
    assert plan.crop_height == 1080
    assert len(plan.commands) == 1
    cmd = plan.commands[0]
    assert cmd.duration_sec == pytest.approx(5.0)
    # Без face → anchor = center-clamped (single keyframe).
    assert cmd.is_static
    # Y-axis no crop (scale_y=1.0) → anchor_y = default_center.
    assert cmd.keyframes[0].anchor_y == pytest.approx(DEFAULT_ANCHOR_Y, abs=1e-3)


def test_build_plan_multiple_segments_order_preserved() -> None:
    segs = [
        ReelSegmentRender(source_start=0.0, source_end=3.0),
        ReelSegmentRender(source_start=10.0, source_end=14.0),
        ReelSegmentRender(source_start=50.0, source_end=52.0),
    ]
    plan = build_base_crop_plan(
        segments=segs,
        face_track=None,
        source_width=1920,
        source_height=1080,
        target_aspect_ratio=9 / 16,
    )
    assert len(plan.commands) == 3
    assert plan.commands[0].duration_sec == pytest.approx(3.0)
    assert plan.commands[1].duration_sec == pytest.approx(4.0)
    assert plan.commands[2].duration_sec == pytest.approx(2.0)


def test_build_plan_face_on_right_anchor_follows() -> None:
    """Лицо стабильно справа (cx=0.75) — anchor_x сдвигается вправо, но clamp."""
    # scale_factor_x = 608/1920 ≈ 0.316, half = 0.158. Допустимый x ∈ [0.158, 0.842].
    track = _make_track(samples=[(t * 0.3, 0.75, 0.5) for t in range(20)])
    seg = ReelSegmentRender(source_start=0.0, source_end=5.0)
    plan = build_base_crop_plan(
        segments=[seg],
        face_track=track,
        source_width=1920,
        source_height=1080,
        target_aspect_ratio=9 / 16,
    )
    cmd = plan.commands[0]
    # Anchor должен следовать лицу — 0.75 в пределах clamp.
    for kf in cmd.keyframes:
        assert kf.anchor_x > DEFAULT_ANCHOR_X  # вправо от центра
        assert 0.158 <= kf.anchor_x <= 0.842


def test_build_plan_face_clamped_when_near_edge() -> None:
    """Лицо у правого края (cx=0.95) — anchor прижимается к границе clamp."""
    track = _make_track(samples=[(t * 0.3, 0.95, 0.5) for t in range(20)])
    seg = ReelSegmentRender(source_start=0.0, source_end=5.0)
    plan = build_base_crop_plan(
        segments=[seg],
        face_track=track,
        source_width=1920,
        source_height=1080,
        target_aspect_ratio=9 / 16,
    )
    # half_x = 608/1920/2 ≈ 0.158. Max allowed x = 1 - 0.158 = 0.842.
    for kf in plan.commands[0].keyframes:
        assert kf.anchor_x <= 0.843


def test_build_plan_no_op_same_aspect() -> None:
    """1920x1080 (16:9) → target 16:9 — plan is_no_op = True, anchor force center."""
    seg = ReelSegmentRender(source_start=0.0, source_end=3.0)
    plan = build_base_crop_plan(
        segments=[seg],
        face_track=None,
        source_width=1920,
        source_height=1080,
        target_aspect_ratio=16 / 9,
    )
    assert plan.is_no_op
    assert plan.crop_width == 1920
    assert plan.crop_height == 1080
    # No-op: scale_factor_x/y = 1 → x и y force в default center.
    for kf in plan.commands[0].keyframes:
        assert kf.anchor_x == pytest.approx(DEFAULT_ANCHOR_X)
        assert kf.anchor_y == pytest.approx(DEFAULT_ANCHOR_Y)


def test_crop_dims_odd_source_rounds_down_to_even() -> None:
    """Источник с нечётными размерами — crop чётный (yuv420p требование)."""
    crop_w, crop_h = compute_aspect_crop_dims(1920, 1080, 16 / 9)
    assert crop_w % 2 == 0 and crop_h % 2 == 0


def test_build_plan_empty_segments_raises() -> None:
    with pytest.raises(ValueError, match="at least one segment"):
        build_base_crop_plan(
            segments=[],
            face_track=None,
            source_width=1920,
            source_height=1080,
            target_aspect_ratio=9 / 16,
        )


def test_build_plan_zero_duration_segments_skipped() -> None:
    """Сегменты с нулевой длительностью выбрасываются; остаётся валидный план."""
    segs = [
        ReelSegmentRender(source_start=5.0, source_end=5.0),  # duration=0 → skip
        ReelSegmentRender(source_start=10.0, source_end=15.0),
    ]
    plan = build_base_crop_plan(
        segments=segs,
        face_track=None,
        source_width=1920,
        source_height=1080,
        target_aspect_ratio=9 / 16,
    )
    assert len(plan.commands) == 1


def test_build_plan_keyframes_within_duration_bounds() -> None:
    """t_offset_sec всех keyframes ∈ [0, duration_sec]."""
    track = _make_track(samples=[(t * 0.3, 0.5 + 0.01 * t, 0.5) for t in range(20)])
    seg = ReelSegmentRender(source_start=0.0, source_end=5.0)
    plan = build_base_crop_plan(
        segments=[seg],
        face_track=track,
        source_width=1920,
        source_height=1080,
        target_aspect_ratio=9 / 16,
    )
    cmd = plan.commands[0]
    for kf in cmd.keyframes:
        assert 0.0 <= kf.t_offset_sec <= cmd.duration_sec + 1e-3
