"""Runtime-детект доступных ffmpeg-видеоэнкодеров + портируемый фолбэк.

Хардкод `hevc_videotoolbox`/`h264_videotoolbox` ломается на Linux (Railway),
где Apple VideoToolbox отсутствует. Этот хелпер один раз спрашивает у ffmpeg
список энкодеров (`-encoders`) и резолвит запрошенный кодек в доступный:
VideoToolbox при наличии, иначе software-фолбэк (libx264/libx265).

Паттерн заимствован из ``services/publer/media_uploader.py`` (детект VT),
вынесен сюда чтобы переиспользовать и в основном рендере, и в export-transcode.
"""
from __future__ import annotations

import shutil
import subprocess
from functools import lru_cache

# VideoToolbox-кодек → software-фолбэк (равноценный по контейнеру/тегу).
_SOFTWARE_FALLBACK: dict[str, str] = {
    "hevc_videotoolbox": "libx265",
    "h264_videotoolbox": "libx264",
}

# Кодек → правильный stream tag для MP4-контейнера.
_CODEC_TAG: dict[str, str] = {
    "hevc_videotoolbox": "hvc1",
    "libx265": "hvc1",
    "h264_videotoolbox": "avc1",
    "libx264": "avc1",
}


@lru_cache(maxsize=1)
def _ffmpeg_path() -> str:
    return shutil.which("ffmpeg") or "ffmpeg"


@lru_cache(maxsize=1)
def _available_encoders() -> frozenset[str]:
    """Множество имён энкодеров, поддержанных текущим ffmpeg.

    Кешируется: набор энкодеров не меняется в рантайме процесса. При сбое
    запуска ffmpeg возвращает пустое множество → резолв уйдёт в software.
    """
    try:
        proc = subprocess.run(
            [_ffmpeg_path(), "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return frozenset()
    names: set[str] = set()
    for line in proc.stdout.splitlines():
        parts = line.split()
        # Формат строки: " V..... libx264   H.264 ..."
        if len(parts) >= 2 and parts[0] and parts[0][0] in {"V", "A", "S"}:
            names.add(parts[1])
    return frozenset(names)


def resolve_video_codec(preferred: str) -> str:
    """Возвращает доступный видеокодек: ``preferred`` если ffmpeg его держит,
    иначе портируемый software-фолбэк. Неизвестные кодеки возвращаются как есть.
    """
    encoders = _available_encoders()
    if preferred in encoders:
        return preferred
    fallback = _SOFTWARE_FALLBACK.get(preferred)
    if fallback is not None and fallback in encoders:
        return fallback
    if fallback is not None:
        return fallback
    return preferred


def codec_stream_tag(codec: str, default: str) -> str:
    """Возвращает корректный MP4 stream tag для кодека (``-tag:v``)."""
    return _CODEC_TAG.get(codec, default)


__all__ = ["codec_stream_tag", "resolve_video_codec"]
