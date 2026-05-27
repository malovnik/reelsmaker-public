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
from videomaker.services.transcribers.mlx_whisper_backend import MlxWhisperBackend

__all__ = [
    "DeepgramBackend",
    "MlxWhisperBackend",
    "TranscribedSegment",
    "TranscribedWord",
    "Transcriber",
    "TranscriberError",
    "TranscriptResult",
    "build_transcriber",
    "merge_words_into_segments",
]
