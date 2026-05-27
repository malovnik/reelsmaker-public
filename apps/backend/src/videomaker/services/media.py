"""ffmpeg wrappers: probe, audio extract, HEVC render, concat.

ВАЖНО: все subprocess-вызовы через asyncio.create_subprocess_exec с list[str]
аргументов. Shell НЕ используется, поэтому command injection невозможен.
"""

from __future__ import annotations

import asyncio
import json
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from videomaker.core.logging import get_logger
from videomaker.services.subprocess_utils import (
    DEFAULT_SUBPROCESS_TIMEOUT_SEC,
    PROBE_SUBPROCESS_TIMEOUT_SEC,
    communicate_with_timeout,
)

log = get_logger(__name__)


class FfmpegError(RuntimeError):
    pass


@dataclass(slots=True)
class MediaInfo:
    duration_sec: float
    width: int
    height: int
    fps: float
    video_codec: str
    audio_codec: str | None
    sample_rate: int | None
    channels: int | None
    bit_rate: int | None


async def probe(path: Path) -> MediaInfo:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    data = await _run_and_capture(cmd)
    info: dict[str, Any] = json.loads(data)
    fmt = info.get("format") or {}
    streams = info.get("streams") or []

    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if video is None:
        raise FfmpegError(f"no video stream in {path}")

    duration = float(fmt.get("duration") or video.get("duration") or 0.0)
    return MediaInfo(
        duration_sec=duration,
        width=int(video.get("width") or 0),
        height=int(video.get("height") or 0),
        fps=_parse_fps(video.get("r_frame_rate") or "30/1"),
        video_codec=str(video.get("codec_name") or "unknown"),
        audio_codec=str(audio["codec_name"]) if audio and audio.get("codec_name") else None,
        sample_rate=int(audio["sample_rate"]) if audio and audio.get("sample_rate") else None,
        channels=int(audio["channels"]) if audio and audio.get("channels") else None,
        bit_rate=int(fmt["bit_rate"]) if fmt.get("bit_rate") else None,
    )


async def extract_audio(
    source: Path,
    destination: Path,
    *,
    sample_rate: int = 16000,
    channels: int = 1,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(source),
        "-vn",
        "-ac",
        str(channels),
        "-ar",
        str(sample_rate),
        "-c:a",
        "pcm_s16le",
        str(destination),
    ]
    await _run_and_raise(cmd)
    log.info("audio_extracted", source=str(source), dest=str(destination))


@dataclass(slots=True)
class ReelSegmentRender:
    source_start: float
    source_end: float

    @property
    def duration(self) -> float:
        return max(0.0, self.source_end - self.source_start)


@dataclass(slots=True)
class ExportPreset:
    aspect: str
    width: int
    height: int
    fps: int
    video_codec: str
    video_tag: str
    video_bitrate: str
    video_maxrate: str
    video_bufsize: str
    audio_codec: str
    audio_bitrate: str
    scale_filter: str
    pix_fmt: str


async def _run_and_capture(cmd: list[str]) -> str:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await communicate_with_timeout(
            proc, timeout_sec=PROBE_SUBPROCESS_TIMEOUT_SEC
        )
    except TimeoutError as exc:
        raise FfmpegError(
            f"{shlex.join(cmd[:2])} ... timed out after "
            f"{PROBE_SUBPROCESS_TIMEOUT_SEC:.0f}s, process killed"
        ) from exc
    if proc.returncode != 0:
        raise FfmpegError(
            f"command {shlex.join(cmd)} failed (rc={proc.returncode}): {stderr.decode(errors='replace')[:500]}"
        )
    return stdout.decode("utf-8")


async def _run_and_raise(cmd: list[str]) -> None:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await communicate_with_timeout(
            proc, timeout_sec=DEFAULT_SUBPROCESS_TIMEOUT_SEC
        )
    except TimeoutError as exc:
        raise FfmpegError(
            f"{shlex.join(cmd[:3])} ... timed out after "
            f"{DEFAULT_SUBPROCESS_TIMEOUT_SEC:.0f}s, process killed"
        ) from exc
    if proc.returncode != 0:
        raise FfmpegError(
            f"{shlex.join(cmd[:3])} ... failed (rc={proc.returncode}): "
            f"{stderr.decode(errors='replace')[:800]}"
        )


def _parse_fps(value: str) -> float:
    if "/" in value:
        num, den = value.split("/", 1)
        try:
            return float(num) / float(den) if float(den) else 0.0
        except ValueError:
            return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


def ffmpeg_escape_path(path: Path) -> str:
    """Экранирование пути для lavfi filter_complex (subtitles=..., movie=...).

    ffmpeg filter_complex парсер использует `\\`, `:`, `'` как синтаксис, а
    `[` / `]` как разделители stream-label. Пробелы разделяют опции. Поэтому
    все эти символы экранируются в контексте filter-аргумента.
    """
    raw = str(path)
    raw = raw.replace("\\", "\\\\")
    raw = raw.replace(":", "\\:")
    raw = raw.replace("'", r"\'")
    raw = raw.replace(" ", "\\ ")
    raw = raw.replace("[", "\\[")
    raw = raw.replace("]", "\\]")
    return raw
