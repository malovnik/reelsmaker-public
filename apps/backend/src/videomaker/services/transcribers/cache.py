"""Transcript cache — SHA256-keyed disk-persisted TranscriptResult storage.

Паттерн зеркалит ``services/vision/frame_cache.py`` (VisionResultCache):

* SHA256 по содержимому видеофайла — единственный ключ. Изменение имени/пути
  не инвалидирует кэш.
* Layout::

      data/transcripts/<sha256>/
          result.json   # сериализованный TranscriptResult
          meta.json     # { backend, model, language, duration, wpm,
                         #   video_mtime_ns, cached_at, video_size }

* Повторный вызов ``lookup(video_path)`` возвращает TranscriptResult без
  повторной транскрибации. Integration в transcriber_factory — следующая
  микрозадача (1.2).
* Invalidation: ``invalidate(video_path)`` — явное удаление директории.
  Soft-invalidation по mtime — опциональна, делается в caller-е.

Thread-safety: ``asyncio.Lock`` на ключ video_hash для операций записи.
SHA256 считается через streaming chunk (1MB) в thread-pool, чтобы не грузить
RAM и не блокировать event loop на больших файлах.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from videomaker.core.logging import get_logger
from videomaker.services.transcribers.base import TranscriptResult
from videomaker.services.vision.frame_cache import (
    compute_video_sha256 as _compute_video_sha256,
)

log = get_logger(__name__)


async def compute_video_sha256(video_path: Path) -> str:
    """SHA256 файла — реэкспорт из vision для единого ключа кэшей."""
    return await _compute_video_sha256(video_path)


class TranscriptCacheMeta(BaseModel):
    """Метаданные кэшированного транскрипта — отдельный meta.json."""

    backend: str
    model: str
    language: str
    duration_sec: float = Field(ge=0.0)
    word_count: int = Field(ge=0)
    wpm: float = Field(ge=0.0)
    video_mtime_ns: int = Field(ge=0)
    video_size_bytes: int = Field(ge=0)
    cached_at: str  # ISO 8601 UTC


@dataclass(slots=True, frozen=True)
class TranscriptCacheEntry:
    """Результат ``lookup()`` — TranscriptResult + метаданные."""

    video_hash: str
    result: TranscriptResult
    meta: TranscriptCacheMeta


def compute_wpm(result: TranscriptResult) -> float:
    """Слов в минуту — используется profile auto-detect-ом (PHASE 2)."""
    if result.duration_sec <= 0:
        return 0.0
    word_count = len(result.words) if result.words else sum(
        len(seg.words) if seg.words else len(seg.text.split())
        for seg in result.segments
    )
    return float(word_count) * 60.0 / float(result.duration_sec)


def _word_count(result: TranscriptResult) -> int:
    if result.words:
        return len(result.words)
    return sum(
        len(seg.words) if seg.words else len(seg.text.split())
        for seg in result.segments
    )


class TranscriptCache:
    """Disk-persisted SHA256-keyed кэш TranscriptResult."""

    def __init__(self, cache_root: Path) -> None:
        self._cache_root = cache_root
        self._write_locks: dict[str, asyncio.Lock] = {}
        self._locks_lock = asyncio.Lock()

    def _entry_dir(self, video_hash: str) -> Path:
        return self._cache_root / video_hash

    def _result_path(self, video_hash: str) -> Path:
        return self._entry_dir(video_hash) / "result.json"

    def _meta_path(self, video_hash: str) -> Path:
        return self._entry_dir(video_hash) / "meta.json"

    async def _get_lock(self, video_hash: str) -> asyncio.Lock:
        async with self._locks_lock:
            lock = self._write_locks.get(video_hash)
            if lock is None:
                lock = asyncio.Lock()
                self._write_locks[video_hash] = lock
            return lock

    async def lookup(
        self, video_path: Path, *, video_hash: str | None = None
    ) -> TranscriptCacheEntry | None:
        """Возвращает кэшированный транскрипт или None.

        Если ``video_hash`` передан — пропускает вычисление SHA256.
        """
        if video_hash is None:
            video_hash = await compute_video_sha256(video_path)

        result_path = self._result_path(video_hash)
        meta_path = self._meta_path(video_hash)
        if not result_path.exists() or not meta_path.exists():
            return None

        def _read() -> tuple[str, str] | None:
            try:
                return (
                    result_path.read_text(encoding="utf-8"),
                    meta_path.read_text(encoding="utf-8"),
                )
            except OSError as exc:
                log.warning(
                    "transcript_cache.read_failed",
                    extra={"video_hash": video_hash, "error": str(exc)},
                )
                return None

        payload = await asyncio.to_thread(_read)
        if payload is None:
            return None

        result_json, meta_json = payload
        try:
            result = TranscriptResult.model_validate_json(result_json)
            meta = TranscriptCacheMeta.model_validate_json(meta_json)
        except ValidationError as exc:
            log.warning(
                "transcript_cache.corrupt",
                extra={"video_hash": video_hash, "error": str(exc)},
            )
            return None

        return TranscriptCacheEntry(
            video_hash=video_hash,
            result=result,
            meta=meta,
        )

    async def store(
        self,
        video_path: Path,
        result: TranscriptResult,
        *,
        video_hash: str | None = None,
    ) -> TranscriptCacheEntry:
        """Сохраняет TranscriptResult + meta.json. Atomic replace через .tmp."""
        if video_hash is None:
            video_hash = await compute_video_sha256(video_path)

        stat = video_path.stat()
        word_count = _word_count(result)
        meta = TranscriptCacheMeta(
            backend=result.transcriber,
            model=result.model,
            language=result.language,
            duration_sec=result.duration_sec,
            word_count=word_count,
            wpm=compute_wpm(result),
            video_mtime_ns=stat.st_mtime_ns,
            video_size_bytes=stat.st_size,
            cached_at=datetime.now(UTC).isoformat(),
        )

        entry_dir = self._entry_dir(video_hash)
        result_path = self._result_path(video_hash)
        meta_path = self._meta_path(video_hash)
        result_json = result.model_dump_json()
        meta_json = meta.model_dump_json()

        lock = await self._get_lock(video_hash)
        async with lock:
            def _write() -> None:
                entry_dir.mkdir(parents=True, exist_ok=True)
                result_tmp = result_path.with_suffix(".json.tmp")
                meta_tmp = meta_path.with_suffix(".json.tmp")
                result_tmp.write_text(result_json, encoding="utf-8")
                meta_tmp.write_text(meta_json, encoding="utf-8")
                result_tmp.replace(result_path)
                meta_tmp.replace(meta_path)

            await asyncio.to_thread(_write)

        log.info(
            "transcript_cache.stored",
            extra={
                "video_hash": video_hash,
                "backend": meta.backend,
                "duration_sec": meta.duration_sec,
                "wpm": round(meta.wpm, 2),
                "word_count": meta.word_count,
            },
        )
        return TranscriptCacheEntry(
            video_hash=video_hash,
            result=result,
            meta=meta,
        )

    async def invalidate(
        self, video_path: Path, *, video_hash: str | None = None
    ) -> bool:
        """Удаляет запись. Возвращает True если что-то удалили."""
        if video_hash is None:
            video_hash = await compute_video_sha256(video_path)

        entry_dir = self._entry_dir(video_hash)
        if not entry_dir.exists():
            return False

        lock = await self._get_lock(video_hash)
        async with lock:
            def _rm() -> bool:
                removed = False
                for path in (
                    self._result_path(video_hash),
                    self._meta_path(video_hash),
                ):
                    if path.exists():
                        path.unlink()
                        removed = True
                # Директория не пуста — не трогаем (возможно там thumbnails)
                with contextlib.suppress(OSError):
                    entry_dir.rmdir()
                return removed

            removed = await asyncio.to_thread(_rm)

        if removed:
            log.info(
                "transcript_cache.invalidated",
                extra={"video_hash": video_hash},
            )
        return removed

    def is_mtime_stale(
        self, entry: TranscriptCacheEntry, video_path: Path
    ) -> bool:
        """Soft-check: изменился ли файл с момента кэширования.

        Используется caller-ом для опциональной инвалидации. Cache сам по себе
        mtime НЕ проверяет (SHA256 — primary источник правды).
        """
        try:
            current_mtime = video_path.stat().st_mtime_ns
        except OSError:
            return False
        return current_mtime != entry.meta.video_mtime_ns
