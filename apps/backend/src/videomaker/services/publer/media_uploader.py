"""Upload рилса → Publer media + кешируемый media_id."""
from __future__ import annotations

import asyncio
import contextlib
import os
import tempfile
from pathlib import Path

from videomaker.core.logging import get_logger
from videomaker.services.publer.client import PublerClient

log = get_logger(__name__)

_MAX_DIRECT_UPLOAD_BYTES = 200 * 1024 * 1024  # 200 MB — Publer API лимит
_REENCODE_THRESHOLD_BYTES = 180 * 1024 * 1024  # 180 MB — запас под skew
_TARGET_SIZE_BYTES = 150 * 1024 * 1024  # Целевой размер после re-encode
_REENCODE_AUDIO_BPS = 128_000


async def upload_reel_to_publer(
    *,
    reel_path: Path,
    client: PublerClient,
) -> str:
    """Возвращает media_id. Если size > 180 MB, делает on-the-fly re-encode
    в H.264 с target ≈150 MB. Если после re-encode всё ещё > 200 MB →
    raises ValueError (такое невозможно для 90-секундных рилсов 9:16).
    """
    size = reel_path.stat().st_size

    if size <= _REENCODE_THRESHOLD_BYTES:
        media_id = await client.upload_media_file(
            file_path=str(reel_path),
            filename=reel_path.name,
            content_type="video/mp4",
        )
        log.info(
            "publer_reel_uploaded",
            reel=reel_path.name,
            media_id=media_id,
            size_bytes=size,
        )
        return media_id

    log.info(
        "publer_reel_reencode_start",
        reel=reel_path.name,
        size_bytes=size,
        threshold=_REENCODE_THRESHOLD_BYTES,
    )
    compressed = await _reencode_to_h264(reel_path)
    try:
        comp_size = compressed.stat().st_size
        if comp_size > _MAX_DIRECT_UPLOAD_BYTES:
            raise ValueError(
                f"Reel {reel_path.name}: после re-encode всё ещё {comp_size} bytes "
                f"> {_MAX_DIRECT_UPLOAD_BYTES}. URL-flow пока не реализован."
            )
        media_id = await client.upload_media_file(
            file_path=str(compressed),
            filename=reel_path.name,
            content_type="video/mp4",
        )
        log.info(
            "publer_reel_uploaded",
            reel=reel_path.name,
            media_id=media_id,
            size_bytes=comp_size,
            reencoded=True,
        )
        return media_id
    finally:
        with contextlib.suppress(FileNotFoundError):
            compressed.unlink()


async def _reencode_to_h264(source: Path) -> Path:
    """ffmpeg one-pass H.264 videotoolbox с target bitrate для ≈150 MB.

    Формула: target_bitrate_bps = target_size_bytes × 8 / duration_sec - audio_bps.
    Длительность резолвим через ffprobe. Для 90-сек рилса 9:16 даёт ~12 Mbps
    видео, что с vbv-bufsize даёт высокое качество.
    """
    duration_sec = await _probe_duration_sec(source)
    video_bitrate_bps = max(
        1_000_000,
        int(_TARGET_SIZE_BYTES * 8 / max(duration_sec, 1.0)) - _REENCODE_AUDIO_BPS,
    )

    # Tempfile в том же каталоге что и source (диск обычно один — быстрый atomic move)
    out_fd, out_str = tempfile.mkstemp(
        suffix=".mp4", prefix=f"{source.stem}.compressed.", dir=str(source.parent)
    )
    os.close(out_fd)
    out_path = Path(out_str)

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(source),
        "-c:v",
        "h264_videotoolbox",
        "-b:v",
        str(video_bitrate_bps),
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        str(_REENCODE_AUDIO_BPS),
        "-movflags",
        "+faststart",
        str(out_path),
    ]
    log.info("publer_reel_ffmpeg_start", cmd_tail=" ".join(cmd[-5:]))
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        out_path.unlink(missing_ok=True)
        raise ValueError(
            f"ffmpeg re-encode failed rc={proc.returncode}: {stderr.decode('utf-8', 'ignore')[-500:]}"
        )
    return out_path


async def _probe_duration_sec(path: Path) -> float:
    proc = await asyncio.create_subprocess_exec(
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await proc.communicate()
    try:
        return float(stdout.decode("utf-8", "ignore").strip())
    except (ValueError, AttributeError):
        return 90.0  # conservative fallback — для 90-сек рилсов sane default
