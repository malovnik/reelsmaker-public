"""Smoke-tests для services/project_graph.py и services/filter_graph_builder.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from videomaker.models.post_production import PostProductionConfig
from videomaker.services.filter_graph_builder import build_filter_graph
from videomaker.services.media import ExportPreset, ReelSegmentRender
from videomaker.services.project_graph import (
    AnchorKeyframeSpec,
    AudioNormalizeSpec,
    BaseCropCommandSpec,
    BaseCropPlanSpec,
    CutSpec,
    ExportPresetSpec,
    ProjectGraph,
    ZoomCommandSpec,
    ZoomPlanSpec,
    build_project_graph,
)
from videomaker.services.zoom_planner import (
    AnchorKeyframe,
    ZoomCommand,
    ZoomPlan,
    ZoomPlane,
)


def _preset_9x16() -> ExportPreset:
    return ExportPreset(
        aspect="9:16",
        width=1080,
        height=1920,
        fps=30,
        video_codec="hevc_videotoolbox",
        video_tag="hvc1",
        video_bitrate="15M",
        video_maxrate="20M",
        video_bufsize="30M",
        audio_codec="aac",
        audio_bitrate="192k",
        scale_filter="scale=-2:1920,crop=1080:1920:(iw-1080)/2:0",
        pix_fmt="yuv420p",
    )


def _segments() -> list[ReelSegmentRender]:
    return [
        ReelSegmentRender(source_start=10.0, source_end=18.5),
        ReelSegmentRender(source_start=42.0, source_end=51.0),
    ]


def _zoom_plan() -> ZoomPlan:
    return ZoomPlan(
        reel_id="r1",
        frame_width=1080,
        frame_height=1920,
        commands=[
            ZoomCommand(
                reel_segment_idx=0,
                start_offset_sec_in_reel=2.0,
                duration_sec=6.0,
                plane=ZoomPlane.close,
                zoom_percent=30,
                keyframes=(
                    AnchorKeyframe(t_offset_sec=0.0, anchor_x=0.5, anchor_y=0.45),
                    AnchorKeyframe(t_offset_sec=3.0, anchor_x=0.55, anchor_y=0.47),
                    AnchorKeyframe(t_offset_sec=6.0, anchor_x=0.52, anchor_y=0.46),
                ),
            ),
            ZoomCommand(
                reel_segment_idx=1,
                start_offset_sec_in_reel=10.0,
                duration_sec=5.0,
                plane=ZoomPlane.medium,
                zoom_percent=15,
                keyframes=(
                    AnchorKeyframe(t_offset_sec=0.0, anchor_x=0.45, anchor_y=0.43),
                ),
            ),
        ],
    )


def _post_prod_config(*, intro: str | None, outro: str | None) -> PostProductionConfig:
    return PostProductionConfig(
        intro_path=intro,
        outro_path=outro,
        audio_normalize_enabled=True,
        audio_target_lufs=-14.0,
        zoom_enabled=True,
    )


# ─────────────── ProjectGraph: round-trip + validation ─────────────────


def test_cutspec_validates_range() -> None:
    with pytest.raises(ValueError):
        CutSpec(source_start_sec=10.0, source_end_sec=10.0)
    with pytest.raises(ValueError):
        CutSpec(source_start_sec=10.0, source_end_sec=5.0)


def test_project_graph_extra_forbid() -> None:
    with pytest.raises(ValueError):
        ZoomCommandSpec(
            start_offset_sec_in_reel=0.0,
            duration_sec=1.0,
            plane="close",
            zoom_percent=30,
            keyframes=(
                AnchorKeyframeSpec(t_offset_sec=0.0, anchor_x=0.5, anchor_y=0.5),
            ),
            extra_field="boom",  # type: ignore[call-arg]
        )


def test_zoom_command_spec_requires_keyframes() -> None:
    with pytest.raises(ValueError, match="at least one keyframe"):
        ZoomCommandSpec(
            start_offset_sec_in_reel=0.0,
            duration_sec=1.0,
            plane="close",
            zoom_percent=30,
            keyframes=(),
        )


def test_zoom_command_spec_keyframes_must_be_sorted() -> None:
    with pytest.raises(ValueError, match="sorted"):
        ZoomCommandSpec(
            start_offset_sec_in_reel=0.0,
            duration_sec=5.0,
            plane="close",
            zoom_percent=30,
            keyframes=(
                AnchorKeyframeSpec(t_offset_sec=2.0, anchor_x=0.5, anchor_y=0.5),
                AnchorKeyframeSpec(t_offset_sec=1.0, anchor_x=0.6, anchor_y=0.5),
            ),
        )


def test_zoom_command_spec_keyframes_within_duration() -> None:
    with pytest.raises(ValueError, match="exceeds duration"):
        ZoomCommandSpec(
            start_offset_sec_in_reel=0.0,
            duration_sec=3.0,
            plane="close",
            zoom_percent=30,
            keyframes=(
                AnchorKeyframeSpec(t_offset_sec=0.0, anchor_x=0.5, anchor_y=0.5),
                AnchorKeyframeSpec(t_offset_sec=5.0, anchor_x=0.6, anchor_y=0.5),
            ),
        )


def test_project_graph_round_trip_json(tmp_path: Path) -> None:
    graph = build_project_graph(
        reel_id="r1",
        source_path=tmp_path / "src.mp4",
        output_path=tmp_path / "out.mp4",
        segments=_segments(),
        zoom_plan=_zoom_plan(),
        subtitle_path=tmp_path / "subs.ass",
        post_production_config=_post_prod_config(
            intro=str(tmp_path / "intro.mp4"),
            outro=str(tmp_path / "outro.mp4"),
        ),
        preset=_preset_9x16(),
    )

    payload = graph.model_dump_json()
    restored = ProjectGraph.model_validate_json(payload)
    assert restored == graph
    assert restored.reel_id == "r1"
    assert len(restored.cuts) == 2
    assert restored.zoom_plan is not None and len(restored.zoom_plan.commands) == 2
    assert restored.intro_path is not None and restored.intro_path.endswith("intro.mp4")
    assert restored.audio_normalize.enabled is True


def test_build_project_graph_no_post_prod(tmp_path: Path) -> None:
    graph = build_project_graph(
        reel_id="r1",
        source_path=tmp_path / "src.mp4",
        output_path=tmp_path / "out.mp4",
        segments=_segments(),
        zoom_plan=None,
        subtitle_path=None,
        post_production_config=None,
        preset=_preset_9x16(),
    )
    assert graph.intro_path is None
    assert graph.outro_path is None
    assert graph.audio_normalize.enabled is False
    assert graph.zoom_plan is None


def test_build_project_graph_drops_short_segments(tmp_path: Path) -> None:
    graph = build_project_graph(
        reel_id="r2",
        source_path=tmp_path / "src.mp4",
        output_path=tmp_path / "out.mp4",
        segments=[
            ReelSegmentRender(source_start=0.0, source_end=0.05),
            ReelSegmentRender(source_start=10.0, source_end=15.0),
        ],
        zoom_plan=None,
        subtitle_path=None,
        post_production_config=None,
        preset=_preset_9x16(),
    )
    assert len(graph.cuts) == 1
    assert graph.cuts[0].source_start_sec == 10.0


# ─────────────── FilterGraphBuilder: structure substring checks ────────


def _minimal_graph(tmp_path: Path) -> ProjectGraph:
    return ProjectGraph(
        reel_id="rmin",
        source_path=str(tmp_path / "src.mp4"),
        output_path=str(tmp_path / "out.mp4"),
        cuts=(CutSpec(source_start_sec=0.0, source_end_sec=5.0),),
        zoom_plan=None,
        subtitle_path=None,
        intro_path=None,
        outro_path=None,
        audio_normalize=AudioNormalizeSpec(enabled=False),
        export_preset=ExportPresetSpec.from_export_preset(_preset_9x16()),
    )


def test_filter_graph_minimal_no_zoom_no_extras(tmp_path: Path) -> None:
    compiled = build_filter_graph(_minimal_graph(tmp_path))
    fc = compiled.filter_complex
    assert "trim=start=0.000:end=5.000" in fc
    assert "concat=n=1:v=1:a=1[v_main][a_main]" in fc
    # Stages B, C, F, G отсутствуют:
    assert "split=" not in fc
    assert "subtitles=" not in fc
    assert "v_concat" not in fc
    assert "loudnorm" not in fc
    assert compiled.output_video_label == "[v_main]"
    assert compiled.output_audio_label == "[a_main]"
    assert len(compiled.inputs) == 1
    # encoder args:
    assert "-c:v" in compiled.extra_args
    assert "hevc_videotoolbox" in compiled.extra_args
    assert "+faststart" in compiled.extra_args


def test_filter_graph_with_zoom_only(tmp_path: Path) -> None:
    base = _minimal_graph(tmp_path)
    with_zoom = base.model_copy(
        update={
            "zoom_plan": ZoomPlanSpec(
                frame_width=1080,
                frame_height=1920,
                commands=(
                    ZoomCommandSpec(
                        start_offset_sec_in_reel=0.0,
                        duration_sec=5.0,
                        plane="close",
                        zoom_percent=30,
                        keyframes=(
                            AnchorKeyframeSpec(
                                t_offset_sec=0.0, anchor_x=0.5, anchor_y=0.4
                            ),
                        ),
                    ),
                ),
            ),
        }
    )
    compiled = build_filter_graph(with_zoom)
    fc = compiled.filter_complex
    assert "split=1[vm0]" in fc
    assert "crop=" in fc
    assert "concat=n=1:v=1:a=0[v_zoomed]" in fc
    assert compiled.output_video_label == "[v_zoomed]"


def test_filter_graph_dynamic_zoom_generates_piecewise_expr(tmp_path: Path) -> None:
    """Для 2+ keyframes crop должен содержать piecewise `if(lt(t,...))`."""

    base = _minimal_graph(tmp_path)
    with_zoom = base.model_copy(
        update={
            "zoom_plan": ZoomPlanSpec(
                frame_width=1080,
                frame_height=1920,
                commands=(
                    ZoomCommandSpec(
                        start_offset_sec_in_reel=0.0,
                        duration_sec=5.0,
                        plane="close",
                        zoom_percent=30,
                        keyframes=(
                            AnchorKeyframeSpec(
                                t_offset_sec=0.0, anchor_x=0.4, anchor_y=0.4
                            ),
                            AnchorKeyframeSpec(
                                t_offset_sec=2.5, anchor_x=0.55, anchor_y=0.45
                            ),
                            AnchorKeyframeSpec(
                                t_offset_sec=5.0, anchor_x=0.5, anchor_y=0.42
                            ),
                        ),
                    ),
                ),
            ),
        }
    )
    compiled = build_filter_graph(with_zoom)
    fc = compiled.filter_complex
    # Запятые внутри expression должны быть escaped для filter_complex.
    assert r"if(lt(t\,2.500)\," in fc
    # Должно быть ДВЕ вложенных if-цепочки (N-1 для 3 keyframes).
    assert fc.count(r"if(lt(t\,") >= 2
    # Линейная интерполяция: должна быть формула v0+(dv)*(t-t0)/(dt).
    assert "(t-0.000)/(2.500)" in fc
    assert "(t-2.500)/(2.500)" in fc
    assert compiled.output_video_label == "[v_zoomed]"


def test_filter_graph_full_with_subs_intro_outro_loudnorm(tmp_path: Path) -> None:
    graph = build_project_graph(
        reel_id="rfull",
        source_path=tmp_path / "src.mp4",
        output_path=tmp_path / "out.mp4",
        segments=_segments(),
        zoom_plan=_zoom_plan(),
        subtitle_path=tmp_path / "subs.ass",
        post_production_config=_post_prod_config(
            intro=str(tmp_path / "intro.mp4"),
            outro=str(tmp_path / "outro.mp4"),
        ),
        preset=_preset_9x16(),
    )
    compiled = build_filter_graph(graph)
    fc = compiled.filter_complex
    # Stage A:
    assert "concat=n=2:v=1:a=1[v_main][a_main]" in fc
    # Stage B:
    assert "split=2[vm0][vm1]" in fc
    assert "concat=n=2:v=1:a=0[v_zoomed]" in fc
    # Stage C:
    assert "subtitles=" in fc
    assert "[v_subbed]" in fc
    # Stage F:
    assert "[v_intro]" in fc
    assert "[v_outro]" in fc
    assert "concat=n=3:v=1:a=1[v_concat][a_concat]" in fc
    # Stage G:
    assert "loudnorm=I=-14" in fc
    assert "[a_final]" in fc
    assert compiled.output_video_label == "[v_concat]"
    assert compiled.output_audio_label == "[a_final]"
    assert len(compiled.inputs) == 3


def test_filter_graph_subtitle_path_escaping(tmp_path: Path) -> None:
    weird = tmp_path / "C:weird's path" / "sub.ass"
    weird.parent.mkdir(parents=True, exist_ok=True)
    weird.write_text("dummy")
    base = _minimal_graph(tmp_path)
    with_subs = base.model_copy(update={"subtitle_path": str(weird)})
    compiled = build_filter_graph(with_subs)
    # Колоны и одинарные кавычки должны быть экранированы:
    assert "\\:" in compiled.filter_complex
    assert "\\'" in compiled.filter_complex


def test_compiled_graph_to_argv_includes_progress_pipe(tmp_path: Path) -> None:
    compiled = build_filter_graph(_minimal_graph(tmp_path))
    argv = compiled.to_argv()
    assert "-progress" in argv
    pipe_idx = argv.index("-progress") + 1
    assert argv[pipe_idx] == "pipe:1"
    assert argv[0] == "ffmpeg"
    assert argv[-1] == str(compiled.output_path)


# ─────────────── BaseCropPlanSpec + Stage A face-aware crop ───────────────


def _base_crop_plan_for_two_cuts() -> BaseCropPlanSpec:
    """BaseCropPlanSpec для 1920x1080 → 9:16 (608x1080), 2 cuts с статичным anchor."""
    return BaseCropPlanSpec(
        source_width=1920,
        source_height=1080,
        crop_width=608,
        crop_height=1080,
        commands=(
            BaseCropCommandSpec(
                duration_sec=8.5,
                keyframes=(
                    AnchorKeyframeSpec(t_offset_sec=0.0, anchor_x=0.45, anchor_y=0.5),
                ),
            ),
            BaseCropCommandSpec(
                duration_sec=9.0,
                keyframes=(
                    AnchorKeyframeSpec(t_offset_sec=0.0, anchor_x=0.7, anchor_y=0.5),
                    AnchorKeyframeSpec(t_offset_sec=9.0, anchor_x=0.75, anchor_y=0.5),
                ),
            ),
        ),
    )


def _graph_with_base_crop(tmp_path: Path) -> ProjectGraph:
    return ProjectGraph(
        reel_id="r1",
        source_path=str(tmp_path / "source.mp4"),
        output_path=str(tmp_path / "out.mp4"),
        cuts=(
            CutSpec(source_start_sec=10.0, source_end_sec=18.5),
            CutSpec(source_start_sec=42.0, source_end_sec=51.0),
        ),
        base_crop_plan=_base_crop_plan_for_two_cuts(),
        zoom_plan=None,
        subtitle_path=None,
        intro_path=None,
        outro_path=None,
        audio_normalize=AudioNormalizeSpec(enabled=False),
        export_preset=ExportPresetSpec.from_export_preset(_preset_9x16()),
    )


def test_base_crop_plan_length_must_match_cuts() -> None:
    """ProjectGraph валидатор: commands.len == cuts.len."""
    plan = BaseCropPlanSpec(
        source_width=1920,
        source_height=1080,
        crop_width=608,
        crop_height=1080,
        commands=(
            BaseCropCommandSpec(
                duration_sec=5.0,
                keyframes=(AnchorKeyframeSpec(t_offset_sec=0.0, anchor_x=0.5, anchor_y=0.5),),
            ),
        ),
    )
    with pytest.raises(ValueError, match="must match cuts length"):
        ProjectGraph(
            reel_id="r1",
            source_path="/src.mp4",
            output_path="/out.mp4",
            cuts=(
                CutSpec(source_start_sec=0.0, source_end_sec=5.0),
                CutSpec(source_start_sec=10.0, source_end_sec=15.0),
            ),
            base_crop_plan=plan,
            export_preset=ExportPresetSpec.from_export_preset(_preset_9x16()),
        )


def test_base_crop_plan_crop_dims_leq_source() -> None:
    with pytest.raises(ValueError, match="crop_width"):
        BaseCropPlanSpec(
            source_width=100,
            source_height=1080,
            crop_width=200,  # > source_width
            crop_height=1080,
            commands=(
                BaseCropCommandSpec(
                    duration_sec=5.0,
                    keyframes=(AnchorKeyframeSpec(t_offset_sec=0.0, anchor_x=0.5, anchor_y=0.5),),
                ),
            ),
        )


def test_filter_graph_with_base_crop_injects_crop_before_scale(tmp_path: Path) -> None:
    """Stage A chain: crop=608:1080:...,scale=1080:1920,..."""
    compiled = build_filter_graph(_graph_with_base_crop(tmp_path))
    fc = compiled.filter_complex
    # Статичный первый cut: anchor_x=0.45 → x = 0.45*1920 - 608/2 = 864 - 304 = 560 (чётное).
    assert "crop=608:1080:560:0" in fc
    assert "scale=1080:1920" in fc
    # Второй cut — dynamic (2 keyframes) → expression с `if(lt(t\\,`.
    assert "crop=608:1080:if(lt(t" in fc
    # Preset scale_filter НЕ используется (содержит "crop=1080:1920").
    assert "crop=1080:1920:(iw-1080)/2:0" not in fc


def test_filter_graph_without_base_crop_uses_preset(tmp_path: Path) -> None:
    compiled = build_filter_graph(_minimal_graph(tmp_path))
    fc = compiled.filter_complex
    # Fallback на preset.scale_filter (legacy поведение).
    assert "scale=-2:1920" in fc or "crop=1080:1920:(iw-1080)/2:0" in fc


def test_filter_graph_base_crop_no_op_skips_dynamic_crop(tmp_path: Path) -> None:
    """Если crop совпадает с source (is_no_op) — используем preset."""
    plan_no_op = BaseCropPlanSpec(
        source_width=1920,
        source_height=1080,
        crop_width=1920,
        crop_height=1080,
        commands=(
            BaseCropCommandSpec(
                duration_sec=8.5,
                keyframes=(AnchorKeyframeSpec(t_offset_sec=0.0, anchor_x=0.5, anchor_y=0.5),),
            ),
            BaseCropCommandSpec(
                duration_sec=9.0,
                keyframes=(AnchorKeyframeSpec(t_offset_sec=0.0, anchor_x=0.5, anchor_y=0.5),),
            ),
        ),
    )
    graph = ProjectGraph(
        reel_id="r1",
        source_path=str(tmp_path / "source.mp4"),
        output_path=str(tmp_path / "out.mp4"),
        cuts=(
            CutSpec(source_start_sec=10.0, source_end_sec=18.5),
            CutSpec(source_start_sec=42.0, source_end_sec=51.0),
        ),
        base_crop_plan=plan_no_op,
        export_preset=ExportPresetSpec.from_export_preset(_preset_9x16()),
    )
    compiled = build_filter_graph(graph)
    # is_no_op → fallback на preset.scale_filter (содержит crop=1080:1920 или scale).
    assert compiled.diagnostics.get("has_base_crop") is False


# ─────────────── Stage D: video effects ───────────────


def test_filter_graph_video_effects_chained_after_subtitles(tmp_path: Path) -> None:
    """Stage D добавляет filter chain с labeled output между subtitles и extras."""
    from videomaker.services.project_graph import VideoEffectSpec

    graph = ProjectGraph(
        reel_id="r1",
        source_path=str(tmp_path / "src.mp4"),
        output_path=str(tmp_path / "out.mp4"),
        cuts=(CutSpec(source_start_sec=0.0, source_end_sec=10.0),),
        video_effects=(
            VideoEffectSpec(effect_id="bw", filter_expr="hue=s=0"),
        ),
        export_preset=ExportPresetSpec.from_export_preset(_preset_9x16()),
    )
    compiled = build_filter_graph(graph)
    fc = compiled.filter_complex
    assert "hue=s=0" in fc
    assert "[v_fx0]" in fc
    assert compiled.diagnostics["video_effects"] == ["bw"]


def test_filter_graph_multiple_effects_apply_in_order(tmp_path: Path) -> None:
    from videomaker.services.project_graph import VideoEffectSpec

    graph = ProjectGraph(
        reel_id="r1",
        source_path=str(tmp_path / "src.mp4"),
        output_path=str(tmp_path / "out.mp4"),
        cuts=(CutSpec(source_start_sec=0.0, source_end_sec=10.0),),
        video_effects=(
            VideoEffectSpec(effect_id="fx_a", filter_expr="eq=contrast=1.1"),
            VideoEffectSpec(effect_id="fx_b", filter_expr="hue=s=0"),
        ),
        export_preset=ExportPresetSpec.from_export_preset(_preset_9x16()),
    )
    compiled = build_filter_graph(graph)
    fc = compiled.filter_complex
    # Chain: ...eq=contrast=1.1[v_fx0];[v_fx0]hue=s=0[v_fx1]
    assert "eq=contrast=1.1[v_fx0]" in fc
    assert "[v_fx0]hue=s=0[v_fx1]" in fc


def test_filter_graph_no_effects_default_empty(tmp_path: Path) -> None:
    compiled = build_filter_graph(_minimal_graph(tmp_path))
    assert compiled.diagnostics["video_effects"] == []


def test_build_project_graph_collects_bw_from_config(tmp_path: Path) -> None:
    """build_project_graph с bw_enabled=True → ProjectGraph.video_effects contains bw."""
    from videomaker.models.post_production import PostProductionConfig
    config = PostProductionConfig(
        bw_enabled=True,
        zoom_enabled=False,
        audio_normalize_enabled=False,
    )
    graph = build_project_graph(
        reel_id="r1",
        source_path=tmp_path / "src.mp4",
        output_path=tmp_path / "out.mp4",
        segments=_segments(),
        zoom_plan=None,
        subtitle_path=None,
        post_production_config=config,
        preset=_preset_9x16(),
    )
    assert len(graph.video_effects) == 1
    assert graph.video_effects[0].effect_id == "bw"
    assert graph.video_effects[0].filter_expr == "hue=s=0"


def test_build_project_graph_no_config_no_effects(tmp_path: Path) -> None:
    graph = build_project_graph(
        reel_id="r1",
        source_path=tmp_path / "src.mp4",
        output_path=tmp_path / "out.mp4",
        segments=_segments(),
        zoom_plan=None,
        subtitle_path=None,
        post_production_config=None,
        preset=_preset_9x16(),
    )
    assert graph.video_effects == ()
