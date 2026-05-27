"""T8.2 — классификатор breath events vs pure silence.

Silero VAD не различает вдох и тишину — оба non-speech. Этот детектор
помечает breath events (RMS в среднем диапазоне + broadband noise
100-2000 Hz, длительность 150-600ms). Результат — зоны которые
pause_compression должен оставлять несжатыми.
"""

from __future__ import annotations

from pathlib import Path

from videomaker.core.logging import get_logger

log = get_logger(__name__)


async def detect_breath_events(
    audio_path: Path,
    speech_segments: list[tuple[float, float]],
    sample_rate: int = 16000,
) -> list[tuple[float, float]]:
    """Возвращает [(start, end)] breath events.

    Критерии breath:
    - RMS в диапазоне [10-percentile, 50-percentile] (не тишина, не речь)
    - Вне speech_segments (отданных Silero VAD)
    - Длительность 150-600 ms
    """
    try:
        import librosa
        import numpy as np

        y, sr = librosa.load(str(audio_path), sr=sample_rate, mono=True)
        if len(y) < sr // 5:
            return []
        non_speech_mask = np.ones(len(y), dtype=bool)
        for start, end in speech_segments:
            i0 = max(0, int(start * sr))
            i1 = min(len(y), int(end * sr))
            non_speech_mask[i0:i1] = False

        frame_len = int(0.025 * sr)
        hop = frame_len // 2
        frames = librosa.util.frame(y, frame_length=frame_len, hop_length=hop).T
        rms = np.sqrt((frames**2).mean(axis=1))
        silence_thresh = float(np.percentile(rms, 10))
        breath_thresh = float(np.percentile(rms, 50))
        frame_times = np.arange(len(rms)) * (hop / sr)
        breath_events: list[tuple[float, float]] = []
        in_breath = False
        breath_start = 0.0
        for i, t in enumerate(frame_times):
            is_breath = silence_thresh < rms[i] < breath_thresh
            sample_idx = min(int(t * sr), len(non_speech_mask) - 1)
            is_non_speech = non_speech_mask[sample_idx]
            if is_breath and is_non_speech and not in_breath:
                in_breath = True
                breath_start = float(t)
            elif (not is_breath or not is_non_speech) and in_breath:
                in_breath = False
                dur = float(t) - breath_start
                if 0.15 <= dur <= 0.6:
                    breath_events.append((breath_start, float(t)))
        return breath_events
    except Exception as exc:
        log.warning("breath_detect_failed", error=str(exc))
        return []


__all__ = ["detect_breath_events"]
