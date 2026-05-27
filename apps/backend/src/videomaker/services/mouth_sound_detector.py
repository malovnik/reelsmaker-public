"""T8.1 — детектор mouth sounds (lip smacks, clicks, cluck) через librosa.

Эвристика: короткие всплески spectral energy в полосе 2-8kHz при низкой
энергии в speech band (80-300 Hz). Не требует ML-модели — pure signal
processing. Graceful degrade (возвращает []) если librosa fail.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from videomaker.core.logging import get_logger

log = get_logger(__name__)


@dataclass(slots=True)
class AudioDefect:
    """Детектированный mouth sound для mute-zone в render."""

    type: str  # "lip_smack" | "click" | "cluck"
    start_sec: float
    end_sec: float
    confidence: float  # [0, 1]


async def detect_mouth_sounds(
    audio_path: Path,
    sample_rate: int = 16000,
) -> list[AudioDefect]:
    """Находит lip smacks / clicks в аудио.

    Алгоритм: STFT 512 bins hop 256 → spectral energy ratio
    lip_band (2-8kHz) / speech_band (80-300Hz). Peak > 95 percentile →
    candidate. Continuous regions длительностью 20-100ms → defect.

    Returns [] если librosa недоступна или audio невалиден.
    """
    try:
        import librosa
        import numpy as np

        y, sr = librosa.load(str(audio_path), sr=sample_rate, mono=True)
        if len(y) < sr // 10:
            return []
        stft = np.abs(librosa.stft(y, n_fft=512, hop_length=256))
        freqs = librosa.fft_frequencies(sr=sr, n_fft=512)
        speech_mask = (freqs >= 80) & (freqs <= 300)
        lip_mask = (freqs >= 2000) & (freqs <= 8000)
        speech_energy = stft[speech_mask].mean(axis=0)
        lip_energy = stft[lip_mask].mean(axis=0)
        ratio = lip_energy / (speech_energy + 1e-9)
        threshold = float(np.percentile(ratio, 95))
        peak_mask = ratio > threshold
        times = librosa.frames_to_time(
            np.arange(len(ratio)), sr=sr, hop_length=256
        )
        defects: list[AudioDefect] = []
        in_peak = False
        peak_start = 0.0
        for i in range(len(peak_mask)):
            if peak_mask[i] and not in_peak:
                in_peak = True
                peak_start = float(times[i])
            elif not peak_mask[i] and in_peak:
                in_peak = False
                dur = float(times[i]) - peak_start
                if 0.02 <= dur <= 0.1:
                    conf = min(1.0, float(ratio[i]) / threshold)
                    defects.append(
                        AudioDefect(
                            type="lip_smack",
                            start_sec=peak_start,
                            end_sec=float(times[i]),
                            confidence=conf,
                        )
                    )
        return defects
    except Exception as exc:
        log.warning("mouth_sound_detect_failed", error=str(exc))
        return []


__all__ = ["AudioDefect", "detect_mouth_sounds"]
