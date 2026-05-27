"""/api/v1/health — health check + feature availability."""

from __future__ import annotations

import asyncio
import shutil
from functools import lru_cache

from fastapi import APIRouter

from videomaker import __version__
from videomaker.core.config import Settings, get_settings
from videomaker.services.subprocess_utils import (
    PROBE_SUBPROCESS_TIMEOUT_SEC,
    communicate_with_timeout,
)

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health() -> dict[str, object]:
    settings: Settings = get_settings()
    ffmpeg_info = await _detect_ffmpeg()
    return {
        "status": "ok",
        "version": __version__,
        "llm_providers": settings.available_llm_providers,
        "transcribers": settings.available_transcribers,
        "ffmpeg": ffmpeg_info,
        "defaults": {
            "gemini_model": settings.gemini_default_model,
            "anthropic_model": settings.anthropic_default_model,
            "openai_model": settings.openai_default_model,
            "mlx_whisper_model": settings.mlx_whisper_model,
            "deepgram_model": settings.deepgram_model,
        },
        "chunking": {
            "threshold": settings.chunk_token_threshold,
            "window": settings.chunk_window_tokens,
            "overlap": settings.chunk_overlap_tokens,
            "max_concurrency": settings.llm_max_concurrency,
        },
    }


@lru_cache(maxsize=1)
def _cached_ffmpeg_path() -> str | None:
    return shutil.which("ffmpeg")


async def _detect_ffmpeg() -> dict[str, object]:
    path = _cached_ffmpeg_path()
    if path is None:
        return {
            "available": False,
            "path": None,
            "videotoolbox_hevc": False,
            "version": None,
        }
    version_output = await _run_and_capture_stdout([path, "-version"])
    first_line = version_output.splitlines()[0] if version_output else ""
    encoders = await _run_and_capture_stdout([path, "-hide_banner", "-encoders"])
    has_videotoolbox = "hevc_videotoolbox" in encoders
    return {
        "available": True,
        "path": path,
        "videotoolbox_hevc": has_videotoolbox,
        "version": first_line[:120],
    }


async def _run_and_capture_stdout(cmd: list[str]) -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await communicate_with_timeout(
            proc, timeout_sec=PROBE_SUBPROCESS_TIMEOUT_SEC
        )
        return stdout.decode("utf-8", errors="replace")
    except (FileNotFoundError, PermissionError, TimeoutError):
        return ""
