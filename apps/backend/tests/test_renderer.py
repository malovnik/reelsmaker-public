"""Unit-тесты renderer: загрузка пресетов, выборка по aspect, coerce segments."""

from __future__ import annotations

import pytest

from videomaker.models.reel_plan import ReelPlan, ReelSegment
from videomaker.services.media import ReelSegmentRender
from videomaker.services.renderer import (
    RenderSettings,
    coerce_segments,
    load_presets,
    select_preset,
    truncate_to_max_duration,
)
from videomaker.services.subtitles import SubtitleStyle


def test_load_presets_returns_all_aspects() -> None:
    presets, _ = load_presets()
    aspects = {variants.fill.aspect for variants in presets.values()}
    assert aspects == {"9:16", "16:9", "1:1", "4:5"}


def test_select_preset_returns_9_16_with_both_modes() -> None:
    presets, _ = load_presets()
    variants = select_preset(presets, "9:16")
    fill, margin_fill = variants.for_mode("fill")
    fit, margin_fit = variants.for_mode("fit")
    assert fill.width == 1080
    assert fit.width == 1080
    assert "crop=" in fill.scale_filter
    assert "pad=" in fit.scale_filter
    assert margin_fit > margin_fill


def test_select_preset_unknown_raises() -> None:
    presets, _ = load_presets()
    with pytest.raises(KeyError):
        select_preset(presets, "21:9")


def test_coerce_segments_drops_tiny_and_zero_duration() -> None:
    plan = ReelPlan(
        reel_id="r1",
        hook="test",
        predicted_duration_sec=10.0,
        segments=[
            ReelSegment(source_start=5.0, source_end=15.0, reasoning="hook", order_role="hook"),
            ReelSegment(source_start=20.0, source_end=20.1, reasoning="tiny", order_role="development"),
            ReelSegment(source_start=30.0, source_end=29.0, reasoning="invalid", order_role="peak"),
            ReelSegment(source_start=40.0, source_end=45.0, reasoning="payoff", order_role="payoff"),
        ],
    )
    settings = RenderSettings(
        min_reel_duration_sec=5.0,
        max_reel_duration_sec=60.0,
        subtitle_style=SubtitleStyle(),
    )
    segments = coerce_segments(plan, settings)
    assert len(segments) == 2  # оставлены только segment 1 и 4


def test_truncate_to_max_duration() -> None:
    segments = [
        ReelSegmentRender(source_start=0, source_end=20),
        ReelSegmentRender(source_start=30, source_end=60),
    ]
    truncated = truncate_to_max_duration(segments, 35.0)
    total = sum(s.duration for s in truncated)
    assert total <= 35.0
    assert truncated[0].duration == 20.0  # первый целиком
    assert truncated[1].duration == 15.0  # второй урезан
