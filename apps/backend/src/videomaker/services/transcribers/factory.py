"""Фабрика транскрайберов по имени + проверка доступности.

Также предоставляет ``transcribe_with_cache()`` — helper с интеграцией
``TranscriptCache``. Используется pipeline-ом чтобы не дублировать STT на
повторных прогонах одного и того же файла.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from videomaker.core.config import Settings, get_settings
from videomaker.core.logging import get_logger
from videomaker.services.transcribers.base import (
    Transcriber,
    TranscriberError,
    TranscriptResult,
)
from videomaker.services.transcribers.cache import (
    TranscriptCache,
    compute_video_sha256,
)
from videomaker.services.transcribers.deepgram_backend import DeepgramBackend

log = get_logger(__name__)


def build_transcriber(name: str, settings: Settings | None = None) -> Transcriber:
    cfg = settings or get_settings()
    if name in ("stable_ts_mlx", "stable_ts", "mlx_whisper"):
        # MLX доступен только на macOS/Apple Silicon. Ленивый импорт: на
        # Windows/Linux пакет не установлен, поэтому не тянем его на уровне модуля.
        if sys.platform != "darwin":
            raise TranscriberError(
                f"transcriber {name!r} (MLX) доступен только на macOS/Apple Silicon. "
                "На Windows/Linux используйте 'deepgram' (нужен DEEPGRAM_API_KEY)."
            )
        if name in ("stable_ts_mlx", "stable_ts"):
            from videomaker.services.transcribers.stable_ts_mlx_backend import (
                StableTsMlxBackend,
            )

            return StableTsMlxBackend(model=cfg.mlx_whisper_model)
        from videomaker.services.transcribers.mlx_whisper_backend import (
            MlxWhisperBackend,
        )

        return MlxWhisperBackend(model=cfg.mlx_whisper_model)
    if name == "deepgram":
        if not cfg.deepgram_api_key:
            raise TranscriberError(
                "DEEPGRAM_API_KEY is not set — cannot use deepgram transcriber"
            )
        return DeepgramBackend(api_key=cfg.deepgram_api_key, model=cfg.deepgram_model)
    raise TranscriberError(f"unknown transcriber: {name!r}")


@dataclass(slots=True, frozen=True)
class CachedTranscribeOutcome:
    """Результат ``transcribe_with_cache`` — TranscriptResult + метрика hit."""

    result: TranscriptResult
    video_hash: str
    cache_hit: bool


async def transcribe_with_cache(
    *,
    video_path: Path,
    audio_path: Path,
    transcriber: Transcriber,
    cache: TranscriptCache,
    language: str | None = None,
    force_reingest: bool = False,
) -> CachedTranscribeOutcome:
    """Cache-aware транскрибация.

    Last flow:
    1. SHA256 видеофайла.
    2. Если ``force_reingest`` — инвалидируем и идём в backend.
    3. Иначе lookup: если entry есть и transcriber совпадает (по ``backend`` и
       ``model``), возвращаем сразу. Cache HIT → аудио-экстракт должен быть
       пропущен caller-ом, но даже если уже извлечён — это OK (just wasted).
    4. Miss: вызываем transcriber, сохраняем в cache.
    """

    video_hash = await compute_video_sha256(video_path)

    if force_reingest:
        await cache.invalidate(video_path, video_hash=video_hash)
        log.info(
            "transcript_cache.force_reingest",
            extra={"video_hash": video_hash},
        )

    cached = await cache.lookup(video_path, video_hash=video_hash)
    if cached is not None:
        # Совпадает ли backend+model с запрошенным? Если нет — это НЕ hit,
        # инвалидируем и идём в backend.
        if (
            cached.meta.backend == transcriber.name
            and cached.meta.model == transcriber.model
        ):
            log.info(
                "transcript_cache.hit",
                extra={
                    "video_hash": video_hash,
                    "backend": cached.meta.backend,
                    "model": cached.meta.model,
                    "word_count": cached.meta.word_count,
                    "wpm": round(cached.meta.wpm, 2),
                },
            )
            return CachedTranscribeOutcome(
                result=cached.result,
                video_hash=video_hash,
                cache_hit=True,
            )
        log.info(
            "transcript_cache.backend_mismatch",
            extra={
                "video_hash": video_hash,
                "cached_backend": cached.meta.backend,
                "cached_model": cached.meta.model,
                "requested_backend": transcriber.name,
                "requested_model": transcriber.model,
            },
        )
        await cache.invalidate(video_path, video_hash=video_hash)

    log.info(
        "transcript_cache.miss",
        extra={
            "video_hash": video_hash,
            "backend": transcriber.name,
            "model": transcriber.model,
        },
    )
    result = await transcriber.transcribe(audio_path, language=language)
    await cache.store(video_path, result, video_hash=video_hash)
    return CachedTranscribeOutcome(
        result=result,
        video_hash=video_hash,
        cache_hit=False,
    )
