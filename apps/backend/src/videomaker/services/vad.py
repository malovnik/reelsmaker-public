"""Silero VAD через ONNX (CoreML execution provider на Apple Silicon).

TIER1-#8: voice activity detection для последующих фич — filler-removal
(TIER 2 #13), micro-pause compression (TIER 2 #14), speech-boundary
cuts. Silero VAD даёт 16kHz sample-precise speech detection с ~10× меньшим
RAM footprint чем pyannote + CoreML inference на M-чипе.

API:
- `detect_speech_segments(audio_path)` → `list[SpeechSegment]` с
  ``start_sec``/``end_sec`` для каждого speech span.

Модель загружается один раз на процесс (`@functools.cache`), все
последующие вызовы переиспользуют её. Silence segments НЕ возвращаются
явно — они выводятся от inverting speech spans на заданный range.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from videomaker.core.logging import get_logger

log = get_logger(__name__)

# Silero VAD работает только на этом sample rate (model-level constraint).
# soundfile / librosa будут ресемплить файл при необходимости.
VAD_SAMPLE_RATE = 16000


@dataclass(slots=True, frozen=True)
class SpeechSegment:
    """Speech span в секундах от начала audio."""

    start_sec: float
    end_sec: float

    @property
    def duration_sec(self) -> float:
        return max(0.0, self.end_sec - self.start_sec)


class VadError(RuntimeError):
    """Любая ошибка VAD (model load / audio load / onnxruntime)."""


@lru_cache(maxsize=1)
def _load_model() -> Any:
    """Lazy-load Silero VAD ONNX модели. Возвращает кешированную instance."""

    from silero_vad import load_silero_vad

    model = load_silero_vad(onnx=True)
    log.info("silero_vad_model_loaded", provider="onnxruntime")
    return model


async def detect_speech_segments(
    audio_path: Path,
    *,
    min_speech_duration_ms: int = 150,
    min_silence_duration_ms: int = 300,
    threshold: float = 0.5,
) -> list[SpeechSegment]:
    """Детектирует speech spans в audio-файле через Silero VAD.

    Args:
        audio_path: путь к WAV / MP3 / etc — librosa ресемплит до 16k.
        min_speech_duration_ms: минимальная длительность speech span
            (короче — отфильтровываются как шум).
        min_silence_duration_ms: минимальный silence gap для split'а двух
            speech spans (меньший gap склеивается в один span).
        threshold: probability threshold модели (default 0.5 — balanced).

    Returns:
        Список `SpeechSegment` отсортированный по start_sec. Пустой список
        если audio молчит или модель/файл не доступны.
    """

    if not audio_path.exists():
        raise VadError(f"audio file not found: {audio_path}")

    try:
        return await asyncio.to_thread(
            _detect_sync,
            audio_path,
            min_speech_duration_ms,
            min_silence_duration_ms,
            threshold,
        )
    except VadError:
        raise
    except Exception as exc:  # pragma: no cover — defensive
        raise VadError(f"vad failed on {audio_path}: {exc}") from exc


def _detect_sync(
    audio_path: Path,
    min_speech_duration_ms: int,
    min_silence_duration_ms: int,
    threshold: float,
) -> list[SpeechSegment]:
    import soundfile as sf
    from silero_vad import get_speech_timestamps

    # soundfile вернёт (samples, sample_rate). Если SR не 16k — ресемплим.
    samples, sr = sf.read(str(audio_path), dtype="float32", always_2d=False)
    if samples.ndim > 1:
        samples = samples.mean(axis=1)  # mono из stereo
    if sr != VAD_SAMPLE_RATE:
        import librosa

        samples = librosa.resample(samples, orig_sr=sr, target_sr=VAD_SAMPLE_RATE)
        sr = VAD_SAMPLE_RATE

    import torch

    tensor = torch.from_numpy(samples)
    model = _load_model()
    raw_timestamps = get_speech_timestamps(
        tensor,
        model,
        sampling_rate=sr,
        threshold=threshold,
        min_speech_duration_ms=min_speech_duration_ms,
        min_silence_duration_ms=min_silence_duration_ms,
        return_seconds=True,
    )
    segments = [
        SpeechSegment(
            start_sec=float(entry["start"]),
            end_sec=float(entry["end"]),
        )
        for entry in raw_timestamps
    ]
    log.info(
        "silero_vad_detect_done",
        audio=str(audio_path),
        segments=len(segments),
        total_speech_sec=round(sum(s.duration_sec for s in segments), 2),
    )
    return segments


def silence_gaps(
    speech: list[SpeechSegment], *, total_duration_sec: float
) -> list[SpeechSegment]:
    """Инвертирует speech spans → возвращает silence gaps (включая head/tail).

    Полезно для pause-compression и cut-on-silence workflow'ов.
    """

    if total_duration_sec <= 0.0:
        return []
    if not speech:
        return [SpeechSegment(start_sec=0.0, end_sec=total_duration_sec)]

    gaps: list[SpeechSegment] = []
    cursor = 0.0
    for seg in speech:
        if seg.start_sec > cursor + 0.001:
            gaps.append(SpeechSegment(start_sec=cursor, end_sec=seg.start_sec))
        cursor = max(cursor, seg.end_sec)
    if cursor < total_duration_sec - 0.001:
        gaps.append(SpeechSegment(start_sec=cursor, end_sec=total_duration_sec))
    return gaps


__all__ = [
    "SpeechSegment",
    "VadError",
    "detect_speech_segments",
    "silence_gaps",
]
