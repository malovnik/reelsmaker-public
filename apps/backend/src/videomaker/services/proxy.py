"""Proxy pipeline: 1080p H.264 копия source для быстрого decode в downstream stages.

Архитектура кэша:
    data/proxies/<source_sha256>__<profile_id>.mp4

* `source_sha256` — SHA-256 source файла (ipotetically одинаковый source = один proxy
  даже между jobs).
* `profile_id` — короткий sha-256 от tuple(crf, maxrate, audio_bitrate, max_dim).
  При смене encoder-параметров — новый profile_id, старые proxy остаются для
  предыдущих jobs.

Lockfile (`<cache_path>.lock`) защищает от race condition: два job на тот же
source одновременно. `O_CREAT|O_EXCL|O_WRONLY` — atomic create. Orphan locks
(crashed process) cleanup'ятся по `mtime > lock_timeout_sec`.

Atomic write: ffmpeg пишет в `<cache_path>.partial`, при успехе — atomic rename.
Прерванная запись не оставляет битый кэш-файл.

LRU cleanup: при `cleanup_proxies(cache_dir, max_size_bytes)` файлы сортируются
по mtime, удаляются самые старые до тех пор пока total size <= max.
"""

from __future__ import annotations

import asyncio
import errno
import hashlib
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from videomaker.core.logging import get_logger
from videomaker.services.media import FfmpegError, MediaInfo, probe
from videomaker.services.subprocess_utils import (
    DEFAULT_SUBPROCESS_TIMEOUT_SEC,
    communicate_with_timeout,
)

log = get_logger(__name__)

LOCK_SUFFIX = ".lock"
PARTIAL_SUFFIX = ".partial"
SHA_BUFFER_SIZE = 1024 * 1024  # 1 MB chunks для streaming hash


@dataclass(slots=True)
class ProxyProfile:
    """Параметры генерации proxy: encoder + cache invalidation key."""

    max_dim: int
    video_crf: int
    video_maxrate_kbps: int
    audio_bitrate_kbps: int

    def cache_id(self) -> str:
        """Стабильный 12-char hash для использования в имени файла."""

        payload = (
            f"v1|max_dim={self.max_dim}|crf={self.video_crf}"
            f"|mr={self.video_maxrate_kbps}|ab={self.audio_bitrate_kbps}"
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


@dataclass(slots=True)
class ProxyOutcome:
    """Результат `generate_or_get_proxy`. Cache hit → wall_time_sec ≈ 0."""

    path: Path
    sha256: str
    profile_id: str
    cache_hit: bool
    wall_time_sec: float
    file_size_bytes: int


@dataclass(slots=True)
class ProxyEntry:
    """Запись для GET /proxies."""

    sha256: str
    profile_id: str
    path: Path
    file_size_bytes: int
    mtime: float
    age_sec: float = field(init=False)

    def __post_init__(self) -> None:
        self.age_sec = max(0.0, time.time() - self.mtime)


class ProxyError(RuntimeError):
    """Невозможно сгенерировать proxy (ffmpeg fail, lockfile timeout, etc)."""


def should_skip_proxy(
    info: MediaInfo,
    *,
    skip_height_le: int,
    skip_duration_lt_sec: float,
    skip_bitrate_lt_kbps: int,
) -> str | None:
    """Возвращает причину пропуска proxy или None если proxy полезен.

    Эвристика: source ≤1080p H.264 + duration <5min + bitrate <8 Mbps —
    overhead generation > выигрыш decode.
    """

    if (
        info.video_codec.lower() in {"h264", "avc1"}
        and info.height <= skip_height_le
        and info.duration_sec < skip_duration_lt_sec
        and (info.bit_rate or 0) < skip_bitrate_lt_kbps * 1000
    ):
        return (
            f"source already light: codec={info.video_codec} height={info.height}"
            f" duration={info.duration_sec:.1f}s bitrate_kbps={(info.bit_rate or 0) // 1000}"
        )
    return None


async def compute_source_sha256(path: Path) -> str:
    """Streaming SHA-256 source файла (без загрузки всего в память).

    Run в default executor (CPU-bound + disk read).
    """

    def _hash() -> str:
        h = hashlib.sha256()
        with path.open("rb") as fh:
            while True:
                chunk = fh.read(SHA_BUFFER_SIZE)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

    return await asyncio.get_running_loop().run_in_executor(None, _hash)


def cache_key(source_sha256: str, profile: ProxyProfile, cache_dir: Path) -> Path:
    return cache_dir / f"{source_sha256}__{profile.cache_id()}.mp4"


async def generate_or_get_proxy(
    *,
    source_path: Path,
    cache_dir: Path,
    profile: ProxyProfile,
    lock_timeout_sec: float = 1800.0,
    on_progress: object | None = None,
) -> ProxyOutcome:
    """Генерирует proxy если его нет в кэше, иначе сразу возвращает cache hit.

    Lockfile predотвращает дубль-генерацию двух jobs на тот же source.
    """

    if not source_path.exists():
        raise ProxyError(f"source not found: {source_path}")

    cache_dir.mkdir(parents=True, exist_ok=True)
    sha256 = await compute_source_sha256(source_path)
    target = cache_key(sha256, profile, cache_dir)
    partial = target.with_suffix(target.suffix + PARTIAL_SUFFIX)
    lock_path = target.with_suffix(target.suffix + LOCK_SUFFIX)

    if target.exists():
        size = target.stat().st_size
        log.info(
            "proxy_cache_hit",
            source=source_path.name,
            sha256=sha256[:12],
            profile_id=profile.cache_id(),
            file_size_mb=round(size / (1024 * 1024), 2),
        )
        return ProxyOutcome(
            path=target,
            sha256=sha256,
            profile_id=profile.cache_id(),
            cache_hit=True,
            wall_time_sec=0.0,
            file_size_bytes=size,
        )

    # Acquire lock (orphan cleanup if stale).
    await _acquire_lock(lock_path, lock_timeout_sec)

    wall_start = time.monotonic()
    try:
        if target.exists():  # double-check после acquire
            size = target.stat().st_size
            return ProxyOutcome(
                path=target,
                sha256=sha256,
                profile_id=profile.cache_id(),
                cache_hit=True,
                wall_time_sec=0.0,
                file_size_bytes=size,
            )

        log.info(
            "proxy_generate_start",
            source=source_path.name,
            sha256=sha256[:12],
            profile_id=profile.cache_id(),
            target=target.name,
        )
        await _ffmpeg_encode_proxy(
            source=source_path, destination=partial, profile=profile
        )
        # Atomic rename (.partial → final). На Darwin/Linux atomic same-fs.
        partial.replace(target)
        wall = round(time.monotonic() - wall_start, 2)
        size = target.stat().st_size
        log.info(
            "proxy_generate_done",
            source=source_path.name,
            sha256=sha256[:12],
            profile_id=profile.cache_id(),
            wall_time_sec=wall,
            file_size_mb=round(size / (1024 * 1024), 2),
        )
        return ProxyOutcome(
            path=target,
            sha256=sha256,
            profile_id=profile.cache_id(),
            cache_hit=False,
            wall_time_sec=wall,
            file_size_bytes=size,
        )
    finally:
        partial.unlink(missing_ok=True)
        lock_path.unlink(missing_ok=True)


async def _acquire_lock(lock_path: Path, timeout_sec: float) -> None:
    """Atomic O_EXCL lock. Если lock существует но stale (mtime > timeout) — удаляем."""

    deadline = time.monotonic() + max(1.0, timeout_sec)
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            os.close(fd)
            return
        except OSError as exc:
            if exc.errno != errno.EEXIST:
                raise ProxyError(f"lock create failed: {exc}") from exc
            try:
                age = time.time() - lock_path.stat().st_mtime
            except FileNotFoundError:
                continue
            if age > timeout_sec:
                log.warning(
                    "proxy_lock_orphan_cleanup",
                    lock=str(lock_path),
                    age_sec=round(age, 1),
                )
                lock_path.unlink(missing_ok=True)
                continue
            if time.monotonic() > deadline:
                raise ProxyError(
                    f"proxy lock held for >{int(timeout_sec)}s: {lock_path}"
                ) from None
            await asyncio.sleep(2.0)


async def _ffmpeg_encode_proxy(
    *, source: Path, destination: Path, profile: ProxyProfile
) -> None:
    """ffmpeg → 1080p H.264 high@4.0 + AAC stereo + faststart.

    `tune=fastdecode` приоритизирует decode speed над encode quality —
    proxy нужен для повторного decode в downstream stages.
    `g=60` (GOP) → keyframe каждые 2s @ 30fps — быстрый seek.
    """

    destination.parent.mkdir(parents=True, exist_ok=True)
    scale_chain = (
        f"scale=w=min(iw\\,{profile.max_dim}):h=-2:force_original_aspect_ratio=decrease"
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "error",
        "-i",
        str(source),
        "-vf",
        scale_chain,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-tune",
        "fastdecode",
        "-profile:v",
        "high",
        "-level",
        "4.0",
        "-crf",
        str(profile.video_crf),
        "-maxrate",
        f"{profile.video_maxrate_kbps}k",
        "-bufsize",
        f"{profile.video_maxrate_kbps * 2}k",
        "-g",
        "60",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        f"{profile.audio_bitrate_kbps}k",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-movflags",
        "+faststart",
        "-f",
        "mp4",
        str(destination),
    ]
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
            f"proxy ffmpeg timed out after "
            f"{DEFAULT_SUBPROCESS_TIMEOUT_SEC:.0f}s, process killed"
        ) from exc
    if proc.returncode != 0:
        msg = stderr.decode(errors="replace")[-1000:]
        raise FfmpegError(
            f"proxy ffmpeg failed (rc={proc.returncode}): {msg}"
        )


def list_proxies(cache_dir: Path) -> list[ProxyEntry]:
    """Сканирует кэш-директорию, возвращает все *.mp4 (без .partial и .lock)."""

    if not cache_dir.exists():
        return []
    entries: list[ProxyEntry] = []
    for path in cache_dir.glob("*.mp4"):
        if path.name.endswith(PARTIAL_SUFFIX):
            continue
        stem = path.stem
        if "__" not in stem:
            continue
        sha, profile_id = stem.split("__", 1)
        st = path.stat()
        entries.append(
            ProxyEntry(
                sha256=sha,
                profile_id=profile_id,
                path=path,
                file_size_bytes=st.st_size,
                mtime=st.st_mtime,
            )
        )
    entries.sort(key=lambda e: e.mtime, reverse=True)
    return entries


def cleanup_proxies(
    cache_dir: Path, *, max_size_bytes: int
) -> tuple[int, int]:
    """LRU cleanup: удаляет старейшие proxy пока total size > max.

    Возвращает (n_deleted, freed_bytes).
    """

    entries = list_proxies(cache_dir)
    total = sum(e.file_size_bytes for e in entries)
    if total <= max_size_bytes:
        return 0, 0
    # Сортируем по mtime asc — старейшие первые.
    entries.sort(key=lambda e: e.mtime)
    deleted = 0
    freed = 0
    for entry in entries:
        if total <= max_size_bytes:
            break
        try:
            entry.path.unlink()
            total -= entry.file_size_bytes
            freed += entry.file_size_bytes
            deleted += 1
            log.info(
                "proxy_evicted",
                sha256=entry.sha256[:12],
                profile_id=entry.profile_id,
                file_size_mb=round(entry.file_size_bytes / (1024 * 1024), 2),
            )
        except OSError as exc:
            log.warning("proxy_evict_failed", path=str(entry.path), error=str(exc))
    return deleted, freed


_SHA256_RE = re.compile(r"^[0-9a-fA-F]{8,64}$")


def delete_proxy(cache_dir: Path, sha256: str) -> int:
    """Удаляет все proxy для конкретного source (любой profile_id). Возвращает n удалённых."""

    # Защита от glob-инъекции: sha256 = только hex 8-64 символа.
    # Без неё "********" или ".." в параметре сматчили бы/удалили чужие файлы.
    if not _SHA256_RE.match(sha256):
        raise ValueError(f"invalid sha256 identifier: {sha256!r}")

    deleted = 0
    for path in cache_dir.glob(f"{sha256}__*.mp4"):
        try:
            path.unlink()
            deleted += 1
        except OSError as exc:
            log.warning("proxy_delete_failed", path=str(path), error=str(exc))
    return deleted


async def probe_after_proxy(path: Path) -> MediaInfo:
    """Probe сгенерированного proxy для проверки корректности (faststart, audio есть)."""

    return await probe(path)


# Удержим shutil в namespace на случай ручного cleanup в будущем.
_ = shutil
