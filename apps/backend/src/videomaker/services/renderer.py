"""High-level renderer: применяет ReelPlan к исходному видео через ffmpeg."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from videomaker.core.logging import get_logger
from videomaker.models.reel_plan import ReelPlan
from videomaker.services.media import (
    ExportPreset,
    ReelSegmentRender,
)
from videomaker.services.subtitles import SubtitleStyle

log = get_logger(__name__)

DEFAULT_PRESETS_PATH = Path(__file__).resolve().parent.parent / "config" / "export_presets.yaml"


@dataclass(slots=True)
class RenderSettings:
    min_reel_duration_sec: float
    max_reel_duration_sec: float
    subtitle_style: SubtitleStyle


@dataclass(slots=True)
class PresetVariants:
    """Набор вариантов одного aspect-пресета: fill (crop) и fit (letterbox)."""

    fill: ExportPreset
    fit: ExportPreset
    subtitle_margin_v_fill: int
    subtitle_margin_v_fit: int

    def for_mode(self, mode: str) -> tuple[ExportPreset, int]:
        if mode == "fit":
            return self.fit, self.subtitle_margin_v_fit
        return self.fill, self.subtitle_margin_v_fill


def load_presets(
    path: Path | None = None,
) -> tuple[dict[str, PresetVariants], RenderSettings]:
    target = path or DEFAULT_PRESETS_PATH
    raw: dict[str, Any] = yaml.safe_load(target.read_text(encoding="utf-8")) or {}

    defaults = raw.get("defaults") or {}
    fps = int(defaults.get("fps", 30))
    video_codec = str(defaults.get("video_codec", "hevc_videotoolbox"))
    video_tag = str(defaults.get("video_tag", "hvc1"))
    audio_codec = str(defaults.get("audio_codec", "aac"))
    audio_bitrate = str(defaults.get("audio_bitrate", "192k"))
    pix_fmt = str(defaults.get("pix_fmt", "yuv420p"))

    def _make(aspect: str, w: int, h: int, br: str, mr: str, buf: str, scale: str) -> ExportPreset:
        return ExportPreset(
            aspect=aspect,
            width=w,
            height=h,
            fps=fps,
            video_codec=video_codec,
            video_tag=video_tag,
            video_bitrate=br,
            video_maxrate=mr,
            video_bufsize=buf,
            audio_codec=audio_codec,
            audio_bitrate=audio_bitrate,
            scale_filter=scale,
            pix_fmt=pix_fmt,
        )

    presets: dict[str, PresetVariants] = {}
    for preset_name, p in (raw.get("presets") or {}).items():
        aspect = str(p["aspect"])
        width = int(p["width"])
        height = int(p["height"])
        br = str(p["video_bitrate"])
        mr = str(p["video_maxrate"])
        buf = str(p["video_bufsize"])
        fill_filter = str(p["fill_filter"])
        fit_filter = str(p["fit_filter"])
        presets[preset_name] = PresetVariants(
            fill=_make(aspect, width, height, br, mr, buf, fill_filter),
            fit=_make(aspect, width, height, br, mr, buf, fit_filter),
            subtitle_margin_v_fill=int(p.get("subtitle_margin_v_fill", 200)),
            subtitle_margin_v_fit=int(p.get("subtitle_margin_v_fit", 400)),
        )

    render_cfg = raw.get("render") or {}
    settings = RenderSettings(
        min_reel_duration_sec=float(render_cfg.get("min_reel_duration_sec", 31.0)),
        max_reel_duration_sec=float(render_cfg.get("max_reel_duration_sec", 89.0)),
        subtitle_style=SubtitleStyle(
            font=str(render_cfg.get("subtitle_font", "Arial")),
            size=int(render_cfg.get("subtitle_size_portrait", 64)),
            outline=float(render_cfg.get("subtitle_outline", 3)),
            shadow=float(render_cfg.get("subtitle_shadow", 1)),
        ),
    )
    return presets, settings


def select_preset(
    presets: dict[str, PresetVariants], aspect: str
) -> PresetVariants:
    by_aspect = {preset.fill.aspect: preset for preset in presets.values()}
    if aspect in by_aspect:
        return by_aspect[aspect]
    raise KeyError(f"no export preset configured for aspect {aspect!r}")


@dataclass(slots=True)
class RenderedReel:
    reel_id: str
    output_path: Path
    subtitle_path: Path
    duration_sec: float


DEFAULT_RENDER_CONCURRENCY = 2
"""Одновременно работающих рендеров. Apple Media Engine на M-series держит
~2-3 HEVC encode сессий без деградации качества/скорости. Больше — отдача
падает, ядра CPU начинают толкаться на libass/scale.
"""

def coerce_segments(plan: ReelPlan, settings: RenderSettings) -> list[ReelSegmentRender]:
    """Конвертирует ReelPlan.segments в ReelSegmentRender, отбрасывая невалидные/слишком короткие."""

    result: list[ReelSegmentRender] = []
    for seg in plan.segments:
        if seg.source_end <= seg.source_start:
            continue
        duration = seg.source_end - seg.source_start
        if duration < 0.25:
            continue
        if duration > settings.max_reel_duration_sec:
            duration = settings.max_reel_duration_sec
            seg_end = seg.source_start + duration
        else:
            seg_end = seg.source_end
        result.append(
            ReelSegmentRender(source_start=float(seg.source_start), source_end=float(seg_end))
        )
    return result


def truncate_to_max_duration(
    segments: list[ReelSegmentRender], max_duration: float
) -> list[ReelSegmentRender]:
    """Урезает список сегментов так, чтобы сумма длительностей <= max_duration."""

    result: list[ReelSegmentRender] = []
    remaining = max_duration
    for seg in segments:
        if remaining <= 0.1:
            break
        take = min(seg.duration, remaining)
        result.append(
            ReelSegmentRender(source_start=seg.source_start, source_end=seg.source_start + take)
        )
        remaining -= take
    return result


__all__ = [
    "DEFAULT_RENDER_CONCURRENCY",
    "PresetVariants",
    "RenderSettings",
    "RenderedReel",
    "coerce_segments",
    "load_presets",
    "select_preset",
    "truncate_to_max_duration",
]
