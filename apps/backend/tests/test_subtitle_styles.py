"""Unit-тесты для преобразования SubtitleStyleConfig → ASS-параметры."""

from __future__ import annotations

import pytest

from videomaker.models.job import (
    FontWeight,
    SubtitleAnchor,
    SubtitleStyleConfig,
)
from videomaker.services.media import MediaInfo
from videomaker.services.subtitle_styles import (
    BUILTIN_PRESETS,
    SYSTEM_FONTS,
    ass_color,
    compute_letterbox,
    compute_margin_v,
    resolve_style,
)


def test_ass_color_opaque_white() -> None:
    # #FFFFFF + 100% = &H00FFFFFF& (alpha=00, BGR=FFFFFF)
    assert ass_color("#FFFFFF", 100) == "&H00FFFFFF&"


def test_ass_color_opaque_gold() -> None:
    # #FFD700 = R=FF G=D7 B=00 → BGR=00D7FF
    assert ass_color("#FFD700", 100) == "&H0000D7FF&"


def test_ass_color_half_transparent() -> None:
    # 50% opacity → alpha ≈ 128 = 0x80
    result = ass_color("#FF0000", 50)
    assert result.startswith("&H80")
    assert result.endswith("0000FF&")


def test_ass_color_fully_transparent() -> None:
    # 0% opacity → alpha = FF (полностью прозрачный)
    assert ass_color("#000000", 0) == "&HFF000000&"


def test_ass_color_clips_opacity() -> None:
    # Клиппинг к [0, 100]
    assert ass_color("#000000", 200) == ass_color("#000000", 100)
    assert ass_color("#000000", -10) == ass_color("#000000", 0)


def test_ass_color_rejects_bad_hex() -> None:
    with pytest.raises(ValueError):
        ass_color("not-a-color", 100)
    with pytest.raises(ValueError):
        ass_color("#12345", 100)  # 5 цифр


def test_compute_letterbox_fill_always_zero() -> None:
    info = MediaInfo(
        duration_sec=60.0,
        width=1920,
        height=1080,
        fps=30.0,
        video_codec="h264",
        audio_codec="aac",
        sample_rate=48000,
        channels=2,
        bit_rate=2_000_000,
    )
    box = compute_letterbox(1080, 1920, "fill", info)
    assert box.letterbox_top == 0
    assert box.letterbox_bottom == 0
    assert box.scaled_width == 1080
    assert box.scaled_height == 1920


def test_compute_letterbox_fit_16_9_into_9_16() -> None:
    # Исходник 16:9 (1920x1080), target 9:16 (1080x1920).
    # min(1080/1920, 1920/1080) = 0.5625 → scaled 1080x607.5
    # letterbox вертикальный (1920-608)/2 ≈ 656
    info = MediaInfo(
        duration_sec=60.0,
        width=1920,
        height=1080,
        fps=30.0,
        video_codec="h264",
        audio_codec=None,
        sample_rate=None,
        channels=None,
        bit_rate=None,
    )
    box = compute_letterbox(1080, 1920, "fit", info)
    assert box.scaled_width == 1080
    assert 600 <= box.scaled_height <= 615
    total_letterbox = box.letterbox_top + box.letterbox_bottom
    assert abs(total_letterbox - (1920 - box.scaled_height)) <= 1


def test_compute_letterbox_fit_no_source_info_fallback() -> None:
    box = compute_letterbox(1080, 1920, "fit", None)
    # Без source_info — считаем что letterbox=0 (рендер не упадёт)
    assert box.letterbox_top == 0
    assert box.letterbox_bottom == 0


def test_compute_margin_v_fill_bottom_is_offset() -> None:
    cfg = SubtitleStyleConfig(
        anchor=SubtitleAnchor.bottom,
        offset_px=120,
    )
    box = compute_letterbox(1080, 1920, "fill", None)
    alignment, margin_v = compute_margin_v(cfg, 1920, "fill", box)
    assert alignment == 2
    assert margin_v == 120


def test_compute_margin_v_fill_top_is_offset() -> None:
    cfg = SubtitleStyleConfig(
        anchor=SubtitleAnchor.top,
        offset_px=80,
    )
    box = compute_letterbox(1080, 1920, "fill", None)
    alignment, margin_v = compute_margin_v(cfg, 1920, "fill", box)
    assert alignment == 8
    assert margin_v == 80


def test_compute_margin_v_fit_bottom_subtracts_letterbox() -> None:
    # letterbox_bottom = 656, offset=10 → margin_v = 646
    info = MediaInfo(
        duration_sec=60.0, width=1920, height=1080, fps=30.0,
        video_codec="h264", audio_codec=None, sample_rate=None,
        channels=None, bit_rate=None,
    )
    box = compute_letterbox(1080, 1920, "fit", info)
    cfg = SubtitleStyleConfig(
        anchor=SubtitleAnchor.bottom,
        offset_px=10,
    )
    alignment, margin_v = compute_margin_v(cfg, 1920, "fit", box)
    assert alignment == 2
    assert margin_v == box.letterbox_bottom - 10


def test_compute_margin_v_fit_top_subtracts_letterbox() -> None:
    info = MediaInfo(
        duration_sec=60.0, width=1920, height=1080, fps=30.0,
        video_codec="h264", audio_codec=None, sample_rate=None,
        channels=None, bit_rate=None,
    )
    box = compute_letterbox(1080, 1920, "fit", info)
    cfg = SubtitleStyleConfig(anchor=SubtitleAnchor.top, offset_px=15)
    alignment, margin_v = compute_margin_v(cfg, 1920, "fit", box)
    assert alignment == 8
    assert margin_v == box.letterbox_top - 15


def test_compute_margin_v_fit_bottom_offset_too_large_clips_to_zero() -> None:
    # Если offset больше letterbox — clipping к 0 (текст попадает на границу видео)
    info = MediaInfo(
        duration_sec=60.0, width=1080, height=1920, fps=30.0,
        video_codec="h264", audio_codec=None, sample_rate=None,
        channels=None, bit_rate=None,
    )
    # Source уже 9:16 → в fit letterbox=0
    box = compute_letterbox(1080, 1920, "fit", info)
    assert box.letterbox_bottom == 0
    cfg = SubtitleStyleConfig(anchor=SubtitleAnchor.bottom, offset_px=50)
    _, margin_v = compute_margin_v(cfg, 1920, "fit", box)
    assert margin_v == 0


def test_compute_margin_v_center_fill_zero_offset_uses_alignment_5() -> None:
    cfg = SubtitleStyleConfig(anchor=SubtitleAnchor.center, offset_px=0)
    box = compute_letterbox(1080, 1920, "fill", None)
    alignment, margin_v = compute_margin_v(cfg, 1920, "fill", box)
    assert alignment == 5
    assert margin_v == 0


def test_compute_margin_v_center_fill_nonzero_offset_falls_back_to_top() -> None:
    # alignment=5 игнорирует MarginV → сдвигаем на alignment=8 с
    # margin_v = preset_height/2 + offset
    cfg = SubtitleStyleConfig(anchor=SubtitleAnchor.center, offset_px=50)
    box = compute_letterbox(1080, 1920, "fill", None)
    alignment, margin_v = compute_margin_v(cfg, 1920, "fill", box)
    assert alignment == 8
    assert margin_v == 1920 // 2 + 50


def test_compute_margin_v_center_fit_always_ignores_offset() -> None:
    cfg = SubtitleStyleConfig(anchor=SubtitleAnchor.center, offset_px=30)
    info = MediaInfo(
        duration_sec=60.0, width=1920, height=1080, fps=30.0,
        video_codec="h264", audio_codec=None, sample_rate=None,
        channels=None, bit_rate=None,
    )
    box = compute_letterbox(1080, 1920, "fit", info)
    alignment, margin_v = compute_margin_v(cfg, 1920, "fit", box)
    assert alignment == 5
    assert margin_v == 0


def test_resolve_style_without_background_uses_border_style_1() -> None:
    cfg = SubtitleStyleConfig(background=False)
    result = resolve_style(
        cfg, preset_width=1080, preset_height=1920, fit_mode="fill", source_info=None
    )
    assert result.border_style == 1
    assert result.ass_style.border_style == 1


def test_resolve_style_with_background_uses_border_style_3() -> None:
    cfg = SubtitleStyleConfig(
        background=True,
        background_color="#112233",
        background_opacity=80,
    )
    result = resolve_style(
        cfg, preset_width=1080, preset_height=1920, fit_mode="fill", source_info=None
    )
    assert result.border_style == 3
    assert result.ass_style.border_style == 3
    # background_color = #112233 → R=11 G=22 B=33 → BGR=332211, alpha=80% ≈ 0x33
    assert "332211" in result.ass_style.back_colour.upper()


def test_resolve_style_without_background_uses_shadow_color_as_back() -> None:
    cfg = SubtitleStyleConfig(
        background=False,
        shadow_color="#AABBCC",
        shadow_opacity=100,
    )
    result = resolve_style(
        cfg, preset_width=1080, preset_height=1920, fit_mode="fill", source_info=None
    )
    # shadow_color=#AABBCC → BGR=CCBBAA
    assert "CCBBAA" in result.ass_style.back_colour.upper()


def test_resolve_style_bold_italic_flags() -> None:
    bold_cfg = SubtitleStyleConfig(weight=FontWeight.bold, italic=True)
    regular_cfg = SubtitleStyleConfig(weight=FontWeight.regular, italic=False)
    a = resolve_style(
        bold_cfg, preset_width=1080, preset_height=1920, fit_mode="fill", source_info=None
    )
    b = resolve_style(
        regular_cfg, preset_width=1080, preset_height=1920, fit_mode="fill", source_info=None
    )
    assert a.ass_style.bold == -1
    assert a.ass_style.italic == 1
    assert b.ass_style.bold == 0
    assert b.ass_style.italic == 0


def test_builtin_presets_pass_pydantic_validation() -> None:
    for name, _, cfg in BUILTIN_PRESETS:
        assert cfg.font
        # round-trip через JSON: pydantic validation + ass_color не падает
        raw = cfg.model_dump(mode="json")
        rebuilt = SubtitleStyleConfig.model_validate(raw)
        resolve_style(
            rebuilt,
            preset_width=1080,
            preset_height=1920,
            fit_mode="fill",
            source_info=None,
        )
        assert name  # не пустое имя


def test_exactly_one_builtin_preset_marked_default() -> None:
    default_count = sum(1 for _, is_default, _ in BUILTIN_PRESETS if is_default)
    assert default_count == 1


def test_system_fonts_includes_arial() -> None:
    assert "Arial" in SYSTEM_FONTS
    assert len(SYSTEM_FONTS) >= 10


def test_subtitle_style_config_rejects_bad_hex() -> None:
    with pytest.raises(ValueError):
        SubtitleStyleConfig(primary_color="red")
    with pytest.raises(ValueError):
        SubtitleStyleConfig(outline_color="#xyz")


def test_subtitle_style_config_rejects_out_of_range() -> None:
    with pytest.raises(ValueError):
        SubtitleStyleConfig(size=10)  # size < 24
    with pytest.raises(ValueError):
        SubtitleStyleConfig(size=999)  # size > 128
    with pytest.raises(ValueError):
        SubtitleStyleConfig(offset_px=1000)
    with pytest.raises(ValueError):
        SubtitleStyleConfig(text_opacity=101)
