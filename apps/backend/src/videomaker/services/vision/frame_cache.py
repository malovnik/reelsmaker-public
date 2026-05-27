"""Frame extraction + vision result cache — disk-persisted, SHA256-keyed.

Стратегия идентична `face_tracker.py` (паттерн — не shared функция чтобы не
делать рискованный рефакторинг чужих тестов):

* SHA256 видеофайла → `data/vision_cache/<hash>/` — общий ключ для одного видео.
* Кадр извлекается через ffmpeg subprocess (argv list — без shell, безопасно
  против command injection). Повторный вызов — no-op.
* `VisionResultCache` — JSON line-based append-only storage в
  `data/vision_cache/<hash>/results.jsonl`, in-memory dict по старту.
  Ключ = `f"{op}:{ts:.3f}:{params_hash}"`, значение — сериализованный Pydantic
  результат. Подходит для ~10k записей на видео без оптимизации индексации.

Thread-safety: `asyncio.Lock` на write в JSONL + in-memory dict. Запуск ffmpeg
через argv-list subprocess — event loop не блокируется. Concurrent запросы на
один и тот же frame дедуплицируются через lock: повторный вызов ждёт первого
и возвращает из кэша.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from videomaker.core.logging import get_logger

log = get_logger(__name__)

_HASH_CHUNK_BYTES = 1024 * 1024


@dataclass(slots=True, frozen=True)
class CachedFrame:
    """Результат `extract_frame_at` — путь до JPEG + был ли cache hit."""

    video_hash: str
    timestamp_sec: float
    frame_path: Path
    from_cache: bool


async def compute_video_sha256(video_path: Path) -> str:
    """SHA256 файла. Async — читает большие файлы в thread-pool."""

    def _compute() -> str:
        digest = hashlib.sha256()
        with video_path.open("rb") as fh:
            while chunk := fh.read(_HASH_CHUNK_BYTES):
                digest.update(chunk)
        return digest.hexdigest()

    return await asyncio.to_thread(_compute)


class FrameExtractor:
    """Извлекает отдельные кадры из видео через ffmpeg, кэширует на диск.

    Каждому видео соответствует папка `<cache_root>/<sha256>/frames/`. Повторная
    экстракция по (видео, timestamp) — no-op.
    """

    def __init__(self, cache_root: Path) -> None:
        self._cache_root = cache_root
        self._extract_locks: dict[str, asyncio.Lock] = {}
        self._locks_lock = asyncio.Lock()

    def _frame_path(self, video_hash: str, timestamp_sec: float) -> Path:
        return (
            self._cache_root
            / video_hash
            / "frames"
            / f"{timestamp_sec:.3f}.jpg"
        )

    async def _get_lock(self, key: str) -> asyncio.Lock:
        async with self._locks_lock:
            lock = self._extract_locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._extract_locks[key] = lock
            return lock

    async def extract(
        self, video_path: Path, video_hash: str, timestamp_sec: float
    ) -> CachedFrame:
        """Возвращает путь до JPEG-кадра. Извлекает через ffmpeg если нет в кэше."""
        if timestamp_sec < 0:
            raise ValueError(f"timestamp_sec must be non-negative, got {timestamp_sec}")

        frame_path = self._frame_path(video_hash, timestamp_sec)
        if frame_path.exists() and frame_path.stat().st_size > 0:
            return CachedFrame(
                video_hash=video_hash,
                timestamp_sec=timestamp_sec,
                frame_path=frame_path,
                from_cache=True,
            )

        lock_key = f"{video_hash}:{timestamp_sec:.3f}"
        lock = await self._get_lock(lock_key)
        async with lock:
            if frame_path.exists() and frame_path.stat().st_size > 0:
                return CachedFrame(
                    video_hash=video_hash,
                    timestamp_sec=timestamp_sec,
                    frame_path=frame_path,
                    from_cache=True,
                )
            frame_path.parent.mkdir(parents=True, exist_ok=True)
            await self._run_ffmpeg_extract(video_path, frame_path, timestamp_sec)
            if not frame_path.exists() or frame_path.stat().st_size == 0:
                raise RuntimeError(
                    f"ffmpeg extracted empty frame at {timestamp_sec}s from {video_path}"
                )
            return CachedFrame(
                video_hash=video_hash,
                timestamp_sec=timestamp_sec,
                frame_path=frame_path,
                from_cache=False,
            )

    @staticmethod
    async def _run_ffmpeg_extract(
        video_path: Path, output_path: Path, timestamp_sec: float
    ) -> None:
        """ffmpeg fast seek + single frame через argv-list (без shell)."""
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            f"{timestamp_sec:.3f}",
            "-i",
            str(video_path),
            "-vframes",
            "1",
            "-q:v",
            "2",
            "-loglevel",
            "error",
            str(output_path),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"ffmpeg frame extract failed (rc={proc.returncode}): "
                f"{stderr.decode('utf-8', errors='replace')}"
            )


class VisionResultCache:
    """Кэш результатов vision-запросов — JSONL на диск + in-memory lookup.

    Ключ: (video_hash, timestamp, op, params_hash). Каждое видео имеет свой
    `results.jsonl`. При старте один раз читается весь файл в память (dict),
    далее lookup O(1) + append-only запись.

    Параметры op: 'query', 'caption', 'detect'. `params` сериализуется через
    canonical JSON и хэшируется — изменение промпта/параметров = новый ключ.
    """

    def __init__(self, cache_root: Path) -> None:
        self._cache_root = cache_root
        self._memory: dict[str, dict[str, dict[str, Any]]] = {}
        self._loaded: set[str] = set()
        self._write_locks: dict[str, asyncio.Lock] = {}
        self._locks_lock = asyncio.Lock()

    @staticmethod
    def _params_hash(params: dict[str, Any]) -> str:
        canonical = json.dumps(params, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _make_key(op: str, timestamp_sec: float, params_hash: str) -> str:
        return f"{op}:{timestamp_sec:.3f}:{params_hash}"

    def _results_path(self, video_hash: str) -> Path:
        return self._cache_root / video_hash / "results.jsonl"

    async def _ensure_loaded(self, video_hash: str) -> None:
        if video_hash in self._loaded:
            return
        self._memory.setdefault(video_hash, {})
        results_path = self._results_path(video_hash)
        if not results_path.exists():
            self._loaded.add(video_hash)
            return

        def _read_jsonl() -> list[dict[str, Any]]:
            rows: list[dict[str, Any]] = []
            with results_path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        rows.append(json.loads(stripped))
                    except json.JSONDecodeError:
                        continue
            return rows

        rows = await asyncio.to_thread(_read_jsonl)
        for row in rows:
            key = row.get("key")
            if isinstance(key, str):
                self._memory[video_hash][key] = row.get("value", {})
        self._loaded.add(video_hash)

    async def _get_lock(self, video_hash: str) -> asyncio.Lock:
        async with self._locks_lock:
            lock = self._write_locks.get(video_hash)
            if lock is None:
                lock = asyncio.Lock()
                self._write_locks[video_hash] = lock
            return lock

    async def get(
        self,
        video_hash: str,
        op: str,
        timestamp_sec: float,
        params: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Возвращает ранее сохранённый результат или None."""
        await self._ensure_loaded(video_hash)
        key = self._make_key(op, timestamp_sec, self._params_hash(params))
        return self._memory.get(video_hash, {}).get(key)

    async def put(
        self,
        video_hash: str,
        op: str,
        timestamp_sec: float,
        params: dict[str, Any],
        value: dict[str, Any],
    ) -> None:
        """Сохраняет результат. Idempotent — повторный put с тем же ключом перезапишет."""
        await self._ensure_loaded(video_hash)
        key = self._make_key(op, timestamp_sec, self._params_hash(params))
        self._memory.setdefault(video_hash, {})[key] = value

        lock = await self._get_lock(video_hash)
        async with lock:
            results_path = self._results_path(video_hash)
            results_path.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(
                {"key": key, "value": value},
                ensure_ascii=False,
                separators=(",", ":"),
            )

            def _append() -> None:
                with results_path.open("a", encoding="utf-8") as fh:
                    fh.write(payload + "\n")

            await asyncio.to_thread(_append)
