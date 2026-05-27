"""Integration-тесты реального ffmpeg pipeline через ProjectRenderer.

Помечены как integration — запускай через `pytest -m integration`.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from videomaker.services.media import (
    ExportPreset,
    ReelSegmentRender,
    extract_audio,
    probe,
)
from videomaker.services.project_graph import build_project_graph
from videomaker.services.project_renderer import ProjectRenderer
from videomaker.services.renderer import load_presets, select_preset

pytestmark = pytest.mark.integration


async def _generate_test_video(destination: Path, duration_sec: int = 3) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=duration={duration_sec}:size=1280x720:rate=30",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=440:duration={duration_sec}",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-c:a",
        "aac",
        "-shortest",
        str(destination),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        msg = stderr.decode(errors="replace")
        raise RuntimeError(f"test video generation failed: {msg}")


@pytest.fixture(scope="module")
def tmp_workdir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media_int")


@pytest.fixture(scope="module")
def synthetic_video(tmp_workdir: Path) -> Path:
    path = tmp_workdir / "source.mp4"
    asyncio.run(_generate_test_video(path, duration_sec=3))
    return path


async def test_probe_synthetic_video(synthetic_video: Path) -> None:
    info = await probe(synthetic_video)
    assert info.duration_sec == pytest.approx(3.0, abs=0.3)
    assert info.width == 1280
    assert info.height == 720
    assert info.fps == pytest.approx(30.0, abs=0.1)
    assert info.video_codec == "h264"
    assert info.audio_codec == "aac"


async def test_extract_audio_produces_wav(
    synthetic_video: Path, tmp_workdir: Path
) -> None:
    audio_path = tmp_workdir / "source.wav"
    await extract_audio(synthetic_video, audio_path, sample_rate=16000, channels=1)
    assert audio_path.exists()
    assert audio_path.stat().st_size > 1024

    import soundfile

    with soundfile.SoundFile(audio_path) as sf:
        assert sf.samplerate == 16000
        assert sf.channels == 1
        assert sf.frames >= sf.samplerate * 2


async def test_project_renderer_outputs_hevc_with_correct_preset(
    synthetic_video: Path, tmp_workdir: Path
) -> None:
    presets, _ = load_presets()
    preset, _ = select_preset(presets, "9:16").for_mode("fill")

    output = tmp_workdir / "reel.mp4"
    graph = build_project_graph(
        reel_id="r1",
        source_path=synthetic_video,
        output_path=output,
        segments=[ReelSegmentRender(source_start=0.0, source_end=2.5)],
        zoom_plan=None,
        subtitle_path=None,
        post_production_config=None,
        preset=preset,
    )
    renderer = ProjectRenderer()
    result = await renderer.render(graph)
    assert result.output_path.exists()
    info = await probe(result.output_path)
    assert info.video_codec == "hevc"
    assert info.width == 1080
    assert info.height == 1920
    assert info.fps == pytest.approx(30.0, abs=0.2)
    assert info.audio_codec == "aac"
    assert info.duration_sec == pytest.approx(2.5, abs=0.3)


async def test_project_renderer_concat_multiple_segments(
    synthetic_video: Path, tmp_workdir: Path
) -> None:
    presets, _ = load_presets()
    preset, _ = select_preset(presets, "9:16").for_mode("fill")

    output = tmp_workdir / "reel_concat.mp4"
    graph = build_project_graph(
        reel_id="rconcat",
        source_path=synthetic_video,
        output_path=output,
        segments=[
            ReelSegmentRender(source_start=0.0, source_end=1.0),
            ReelSegmentRender(source_start=1.5, source_end=2.5),
        ],
        zoom_plan=None,
        subtitle_path=None,
        post_production_config=None,
        preset=preset,
    )
    await ProjectRenderer().render(graph)
    info = await probe(output)
    assert info.duration_sec == pytest.approx(2.0, abs=0.3)
    assert info.video_codec == "hevc"


async def test_project_renderer_fails_on_missing_source(
    tmp_workdir: Path,
) -> None:
    presets, _ = load_presets()
    preset, _ = select_preset(presets, "9:16").for_mode("fill")
    output = tmp_workdir / "nonexistent.mp4"
    from videomaker.services.project_renderer import ProjectRendererError

    graph = build_project_graph(
        reel_id="rmissing",
        source_path=tmp_workdir / "does_not_exist.mp4",
        output_path=output,
        segments=[ReelSegmentRender(source_start=0.0, source_end=1.0)],
        zoom_plan=None,
        subtitle_path=None,
        post_production_config=None,
        preset=ExportPreset(
            aspect=preset.aspect,
            width=preset.width,
            height=preset.height,
            fps=preset.fps,
            video_codec=preset.video_codec,
            video_tag=preset.video_tag,
            video_bitrate=preset.video_bitrate,
            video_maxrate=preset.video_maxrate,
            video_bufsize=preset.video_bufsize,
            audio_codec=preset.audio_codec,
            audio_bitrate=preset.audio_bitrate,
            scale_filter=preset.scale_filter,
            pix_fmt=preset.pix_fmt,
        ),
    )
    with pytest.raises(ProjectRendererError):
        await ProjectRenderer().render(graph)
