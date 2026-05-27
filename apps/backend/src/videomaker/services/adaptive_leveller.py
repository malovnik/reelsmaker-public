"""T8.5 — per-segment adaptive loudness leveller.

pyloudnorm измеряет LUFS per-window и локально выравнивает gain, чтобы
тихие участки стали громче, а громкие — чуть тише. Заменяет глобальный
loudnorm (который даёт один gain на весь рилс и оставляет неровности
между сегментами). Результат — ровный loudness ±1 LU по всей длине.

Applier (FFmpeg volume filter с between(t,...)) подключается опционально
в pipeline.py; здесь — только detector + graceful degrade если
pyloudnorm / librosa недоступны.
"""

from __future__ import annotations

from pathlib import Path

from videomaker.core.logging import get_logger

log = get_logger(__name__)


async def compute_adaptive_gains(
    audio_path: Path,
    window_sec: float = 3.0,
    target_lufs: float = -16.0,
    max_gain_db: float = 6.0,
) -> list[tuple[float, float, float]]:
    """Возвращает ``[(start_sec, end_sec, gain_db)]`` per-window.

    FFmpeg применяется через volume filter с выражением::

        volume='if(between(t,s1,e1),g1_linear,if(between(t,s2,e2),g2_linear,...))'

    Graceful degrade: если pyloudnorm / librosa не установлены или
    файл слишком короткий (<2 сек) — вернёт пустой список.

    Args:
        audio_path: путь к WAV/mp3/m4a с дорожкой речи.
        window_sec: длина окна анализа (3.0 = баланс между точностью
            и плавностью; <1.5 начинает скакать, >5 недостаточно
            адаптивно).
        target_lufs: целевой LUFS (-16 для соцсетевого диалога, -14
            для TikTok-громкости, -23 для эфира).
        max_gain_db: ограничение усиления вверх и вниз. Стандарт 6 dB
            чтобы не пересчитать тихий шёпот в грохот.

    Returns:
        Список ``(t_start, t_end, gain_db)``. Пустой при любой ошибке
        или отсутствии deps.
    """
    try:
        import librosa
        import numpy as np
        import pyloudnorm as pyln
    except ImportError:
        log.warning("adaptive_leveller_missing_deps")
        return []

    try:
        y, sr = librosa.load(str(audio_path), sr=16000, mono=True)
    except Exception as exc:
        log.warning("adaptive_leveller_load_failed", error=str(exc))
        return []

    if len(y) < sr * 2:
        return []

    try:
        meter = pyln.Meter(sr)
    except Exception as exc:
        log.warning("adaptive_leveller_meter_init_failed", error=str(exc))
        return []

    window_samples = int(window_sec * sr)
    if window_samples <= 0:
        return []

    gains: list[tuple[float, float, float]] = []
    for start in range(0, len(y) - window_samples, window_samples):
        chunk = y[start : start + window_samples]
        try:
            loudness = meter.integrated_loudness(chunk)
        except Exception:
            continue
        if loudness < -70.0 or loudness != loudness:
            continue
        desired_gain = target_lufs - loudness
        clamped = float(np.clip(desired_gain, -max_gain_db, max_gain_db))
        t_start = start / sr
        t_end = (start + window_samples) / sr
        gains.append((round(t_start, 3), round(t_end, 3), round(clamped, 2)))
    return gains


__all__ = ["compute_adaptive_gains"]
