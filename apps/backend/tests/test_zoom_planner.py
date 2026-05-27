"""Smoke-tests для dynamic anchor tracking в zoom_planner (v0.6)."""

from __future__ import annotations

from videomaker.models.post_production import PostProductionConfig
from videomaker.services.face_tracker import (
    FaceBBox,
    FaceTrackResult,
    FrameDetection,
)
from videomaker.services.media import ReelSegmentRender
from videomaker.services.zoom_planner import (
    DEAD_ZONE_NORM,
    AnchorKeyframe,
    ZoomCommand,
    ZoomPlane,
    _build_anchor_keyframes,
    _clamp_anchor_for_zoom,
    build_zoom_plan,
)


def _face_at(cx: float, cy: float, size: float = 0.15) -> FaceBBox:
    """Создаёт FaceBBox с центром (cx, cy) и заданным размером."""
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
) -> FaceTrackResult:
    """Строит FaceTrackResult из списка (t_sec, face_cx, face_cy)."""
    detections = [
        FrameDetection(timestamp_sec=t, faces=[_face_at(cx, cy)])
        for t, cx, cy in samples
    ]
    return FaceTrackResult(
        video_path="/fake",
        video_hash="a" * 64,
        sample_interval_sec=sample_interval_sec,
        frame_width=1920,
        frame_height=1080,
        detections=detections,
    )


def _post_prod_zoom(enabled: bool = True) -> PostProductionConfig:
    return PostProductionConfig(
        intro_path=None,
        outro_path=None,
        audio_normalize_enabled=False,
        audio_target_lufs=-14.0,
        zoom_enabled=enabled,
        zoom_close_percent=30,
        zoom_medium_percent=15,
        zoom_wide_percent=0,
        zoom_apply_every_nth_cut=1,
        zoom_min_interval_sec=0.0,
        zoom_long_segment_threshold_sec=30.0,
        zoom_subsegment_min_sec=4.0,
        zoom_subsegment_max_sec=7.0,
        zoom_alternating_planes_enabled=False,
    )


# ─────────────── _build_anchor_keyframes ─────────────────


def test_keyframes_no_face_track_returns_single_default() -> None:
    """Без face_track anchor константный → dead-zone схлопывает в 1 keyframe."""
    kfs = _build_anchor_keyframes(
        face_track=None,
        source_t_start=0.0,
        duration_sec=5.0,
        zoom_percent=30,
    )
    assert len(kfs) == 1
    # DEFAULT_ANCHOR_X=0.5 внутри [0.15, 0.85] — clamp'а нет
    assert abs(kfs[0].anchor_x - 0.5) < 0.01


def test_keyframes_stable_face_collapses_to_one() -> None:
    """Лицо не двигается → EMA стабильно → dead-zone → 1 keyframe."""
    samples = [(i * 0.3, 0.5, 0.4) for i in range(30)]
    track = _make_track(samples=samples)
    kfs = _build_anchor_keyframes(
        face_track=track,
        source_t_start=0.0,
        duration_sec=6.0,
        zoom_percent=30,
    )
    assert len(kfs) == 1
    assert abs(kfs[0].anchor_x - 0.5) < 0.02


def test_keyframes_moving_face_produces_multiple() -> None:
    """Лицо двигается линейно от 0.3 до 0.7 → dynamic tracking даёт ≥2 kf."""
    # 30 samples за 6 сек, x от 0.3 до 0.7
    samples = [
        (i * 0.2, 0.3 + i * (0.4 / 29), 0.4) for i in range(30)
    ]
    track = _make_track(samples=samples, sample_interval_sec=0.2)
    kfs = _build_anchor_keyframes(
        face_track=track,
        source_t_start=0.0,
        duration_sec=5.8,
        zoom_percent=30,
    )
    assert len(kfs) >= 2, "moving face must produce multiple keyframes"
    # Первый keyframe должен быть левее (меньше x), последний правее (больше x).
    assert kfs[0].anchor_x < kfs[-1].anchor_x
    # Первый keyframe всегда на t=0, последний около duration.
    assert kfs[0].t_offset_sec == 0.0
    assert abs(kfs[-1].t_offset_sec - 5.8) < 0.4


def test_keyframes_ema_smoothes_jitter() -> None:
    """Шум ±0.02 вокруг 0.5 должен сглаживаться EMA → 1 keyframe (dead-zone)."""
    import random as _random
    rng = _random.Random(42)
    samples = [
        (i * 0.3, 0.5 + rng.uniform(-0.02, 0.02), 0.4 + rng.uniform(-0.01, 0.01))
        for i in range(20)
    ]
    track = _make_track(samples=samples)
    kfs = _build_anchor_keyframes(
        face_track=track,
        source_t_start=0.0,
        duration_sec=5.7,
        zoom_percent=30,
    )
    # Шум < DEAD_ZONE_NORM → всё схлопнется в 1 keyframe.
    assert len(kfs) == 1


def test_keyframes_all_clamped_within_safe_range() -> None:
    """Лицо у левого края source → anchor проклэмплен в допустимый диапазон."""
    samples = [(i * 0.3, 0.05, 0.1) for i in range(20)]
    track = _make_track(samples=samples)
    kfs = _build_anchor_keyframes(
        face_track=track,
        source_t_start=0.0,
        duration_sec=5.7,
        zoom_percent=30,
    )
    # scale_factor = 0.7, half = 0.35 → x допустим в [0.35, 0.65]
    for kf in kfs:
        assert 0.35 <= kf.anchor_x <= 0.65
        assert 0.35 <= kf.anchor_y <= 0.65


def test_rule_of_thirds_shifts_anchor_y_below_eyes() -> None:
    """Anchor_y должен быть ниже eyes_y для правила третей."""
    # eyes_y в face = cy+h*0.4-h/2... Проще взять face в центре.
    # face cy=0.3 → eyes_y=0.3 + 0.15*0.4*0.5=0.33 (из FaceBBox.eyes_y)
    # С scale_factor=0.7 (zoom=30) → y сдвигается +0.7/6=+0.117 → y_final=0.447
    samples = [(i * 0.3, 0.5, 0.3) for i in range(10)]
    track = _make_track(samples=samples)
    kfs = _build_anchor_keyframes(
        face_track=track,
        source_t_start=0.0,
        duration_sec=2.7,
        zoom_percent=30,
    )
    # Raw eyes_y ≈ 0.33, после rule of thirds ≈ 0.447
    # После clamp'а в [0.35, 0.65] — ожидаем ~0.447.
    assert kfs[0].anchor_y > 0.4, "anchor_y должен быть сдвинут вниз от eyes"


# ─────────────── build_zoom_plan integration ─────────────────


def test_build_zoom_plan_without_face_track_uses_default_anchor() -> None:
    segments = [ReelSegmentRender(source_start=0.0, source_end=10.0)]
    plan = build_zoom_plan(
        reel_id="r1",
        segments=segments,
        face_track=None,
        config=_post_prod_zoom(True),
        frame_width=1080,
        frame_height=1920,
    )
    assert not plan.is_empty
    for cmd in plan.commands:
        assert len(cmd.keyframes) >= 1


def test_build_zoom_plan_disabled_returns_empty() -> None:
    segments = [ReelSegmentRender(source_start=0.0, source_end=10.0)]
    plan = build_zoom_plan(
        reel_id="r1",
        segments=segments,
        face_track=None,
        config=_post_prod_zoom(False),
        frame_width=1080,
        frame_height=1920,
    )
    assert plan.is_empty


def test_zoom_command_requires_keyframes() -> None:
    """ZoomCommand с пустыми keyframes должен падать."""
    import pytest
    with pytest.raises(ValueError, match="at least one keyframe"):
        ZoomCommand(
            reel_segment_idx=0,
            start_offset_sec_in_reel=0.0,
            duration_sec=5.0,
            plane=ZoomPlane.close,
            zoom_percent=30,
            keyframes=(),
        )


def test_zoom_command_is_static_property() -> None:
    """is_static=True когда ровно 1 keyframe."""
    static_cmd = ZoomCommand(
        reel_segment_idx=0,
        start_offset_sec_in_reel=0.0,
        duration_sec=5.0,
        plane=ZoomPlane.close,
        zoom_percent=30,
        keyframes=(AnchorKeyframe(t_offset_sec=0.0, anchor_x=0.5, anchor_y=0.5),),
    )
    assert static_cmd.is_static

    dynamic_cmd = ZoomCommand(
        reel_segment_idx=0,
        start_offset_sec_in_reel=0.0,
        duration_sec=5.0,
        plane=ZoomPlane.close,
        zoom_percent=30,
        keyframes=(
            AnchorKeyframe(t_offset_sec=0.0, anchor_x=0.4, anchor_y=0.4),
            AnchorKeyframe(t_offset_sec=5.0, anchor_x=0.6, anchor_y=0.5),
        ),
    )
    assert not dynamic_cmd.is_static


def test_clamp_anchor_wide_forces_center() -> None:
    """Wide (zoom=0) → anchor в центр независимо от input."""
    x, y = _clamp_anchor_for_zoom(anchor_x=0.1, anchor_y=0.9, zoom_percent=0)
    assert x == 0.5
    assert y == 0.4  # DEFAULT_ANCHOR_Y


def test_dead_zone_constant_reasonable() -> None:
    """DEAD_ZONE_NORM должен быть ~3% чтобы не пропускать реальные движения."""
    assert 0.01 <= DEAD_ZONE_NORM <= 0.05
