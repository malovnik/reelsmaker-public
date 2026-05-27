"""Транскрайберы: mlx-whisper (local) и Deepgram (cloud)."""

from __future__ import annotations

from videomaker.services.transcribers.base import (
    TranscribedSegment,
    TranscribedWord,
    Transcriber,
    TranscriberError,
    TranscriptResult,
    merge_words_into_segments,
)
from videomaker.services.transcribers.deepgram_backend import DeepgramBackend
from videomaker.services.transcribers.factory import build_transcriber

# MlxWhisperBackend/StableTsMlxBackend НЕ импортируются здесь жадно: MLX-пакеты
# доступны только на macOS. Их подтягивает build_transcriber() лениво при выборе
# MLX-бэкенда (только на Apple Silicon). На Win/Linux импорт пакета не нужен.

__all__ = [
    "DeepgramBackend",
    "TranscribedSegment",
    "TranscribedWord",
    "Transcriber",
    "TranscriberError",
    "TranscriptResult",
    "build_transcriber",
    "merge_words_into_segments",
]
