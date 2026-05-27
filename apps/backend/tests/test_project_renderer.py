"""Smoke tests для ProjectRenderer на synthesized ffmpeg testsrc видео.

Тесты пропускаются, если ffmpeg недоступен (CI без ffmpeg).
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import pytest

from videomaker.services.media import ExportPreset, ReelSegmentRender
from videomaker.services.project_graph import build_project_graph
from videomaker.services.project_renderer import (
    DEFAULT_RENDER_CONCURRENCY,
    ProjectRenderer,
    ProjectRendererError,
    RenderProgress,
    RenderResult,
)

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH"
)


def _h264_preset() -> ExportPreset:
    """Лёгкий H.264 для smoke-тестов (HEVC VideoToolbox медленнее на коротких clip-ах)."""

    return ExportPreset(
        aspect="9:16",
        width=540,
        height=960,
        fps=30,
        video_codec="libx264",
        video_tag="avc1",
        video_bitrate="1500k",
        video_maxrate="2000k",
        video_bufsize="3000k",
        audio_codec="aac",
        audio_bitrate="96k",
        scale_filter="scale=-2:960,crop=540:960:(iw-540)/2:0",
        pix_fmt="yuv420p",
    )


async def _make_testsrc(path: Path, *, duration_sec: int = 10) -> None:
    """Создаёт синтетический mp4 testsrc + sine audio через ffmpeg."""

    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=duration={duration_sec}:size=1280x720:rate=30",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=440:duration={duration_sec}",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
        str(path),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        msg = stderr.decode(errors="replace")
        raise RuntimeError(f"testsrc gen failed: {msg}")


@pytest.mark.asyncio
async def test_render_minimal_smoke(tmp_path: Path) -> None:
    source = tmp_path / "src.mp4"
    await _make_testsrc(source, duration_sec=8)

    output = tmp_path / "reel.mp4"
    graph = build_project_graph(
        reel_id="smoke1",
        source_path=source,
        output_path=output,
        segments=[ReelSegmentRender(source_start=1.0, source_end=4.0)],
        zoom_plan=None,
        subtitle_path=None,
        post_production_config=None,
        preset=_h264_preset(),
    )

    progress_events: list[RenderProgress] = []

    async def on_progress(snap: RenderProgress) -> None:
        progress_events.append(snap)

    renderer = ProjectRenderer()
    result = await renderer.render(graph, on_progress=on_progress)

    assert isinstance(result, RenderResult)
    assert result.output_path == output
    assert output.exists()
    assert result.file_size_bytes > 0
    assert result.wall_time_sec > 0
    assert any(ev.finished for ev in progress_events), "progress finished event missing"


@pytest.mark.asyncio
async def test_render_many_concurrency_and_failure_isolation(tmp_path: Path) -> None:
    source = tmp_path / "src.mp4"
    await _make_testsrc(source, duration_sec=6)

    good1 = build_project_graph(
        reel_id="good1",
        source_path=source,
        output_path=tmp_path / "good1.mp4",
        segments=[ReelSegmentRender(source_start=0.5, source_end=2.5)],
        zoom_plan=None,
        subtitle_path=None,
        post_production_config=None,
        preset=_h264_preset(),
    )
    bad = build_project_graph(
        reel_id="bad",
        source_path=tmp_path / "missing.mp4",
        output_path=tmp_path / "bad.mp4",
        segments=[ReelSegmentRender(source_start=0.0, source_end=1.0)],
        zoom_plan=None,
        subtitle_path=None,
        post_production_config=None,
        preset=_h264_preset(),
    )
    good2 = build_project_graph(
        reel_id="good2",
        source_path=source,
        output_path=tmp_path / "good2.mp4",
        segments=[ReelSegmentRender(source_start=2.0, source_end=4.0)],
        zoom_plan=None,
        subtitle_path=None,
        post_production_config=None,
        preset=_h264_preset(),
    )

    renderer = ProjectRenderer()
    results = await renderer.render_many(
        [good1, bad, good2], concurrency=DEFAULT_RENDER_CONCURRENCY
    )

    assert len(results) == 3
    assert isinstance(results[0], RenderResult)
    assert isinstance(results[1], ProjectRendererError)
    assert isinstance(results[2], RenderResult)
    assert (tmp_path / "good1.mp4").exists()
    assert (tmp_path / "good2.mp4").exists()


@pytest.mark.asyncio
async def test_render_invalid_concurrency_raises() -> None:
    renderer = ProjectRenderer()
    with pytest.raises(ValueError, match="concurrency"):
        await renderer.render_many([], concurrency=0)
