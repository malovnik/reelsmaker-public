"""T10.1 — Punchline pause detection via Parselmouth pitch final lowering.

Находит моменты в аудиосегменте где pitch (F0) падает >= threshold_hz_drop
в последние ~0.3 сек — это акустическая сигнатура punchline / завершённого
тезиса. На таких моментах pipeline удерживает дополнительную паузу
``punchline_hold_after_sec`` перед следующим cut — даёт слушателю «дать
осесть» тезису. Признак ручного монтажа vs алгоритма который сжимает всё.

Интерфейс:
    from videomaker.services.punchline_detector import detect_punchline_moments
    moments = await detect_punchline_moments(
        audio_path,
        segments=[(start_sec, end_sec), ...],
        pitch_drop_hz=20.0,
    )
    # → list[PunchlineMoment(time_sec, hold_sec, pitch_drop_hz, confidence)]

Graceful degrade:
- Parselmouth не установлен → возвращаем []
- Pitch extraction падает → возвращаем []
- Сегмент короче 0.3 сек → пропускаем
- Voiced frames < 3 → пропускаем

Source: research `editing-craft-2026.md` + `automatic-mode-2026.md`:
финальное опускание pitch в конце интонационной единицы — один из
самых стабильных сигналов punchline в спонтанной речи (Parselmouth
Praat wrapper). Порог 20 Hz drop — эмпирический (Walter Murch /
editing community).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from videomaker.core.logging import get_logger

log = get_logger(__name__)


#: Длина окна в конце сегмента, в котором мы ищем pitch drop.
_FINAL_LOWERING_WINDOW_SEC = 0.3

#: Минимальная длительность сегмента чтобы его анализировать.
_MIN_SEGMENT_SEC = 0.5

#: Минимум voiced frames в final window для надёжной детекции.
_MIN_VOICED_FRAMES = 3


@dataclass(slots=True, frozen=True)
class PunchlineMoment:
    """Момент в аудио где детектирован punchline (pitch final lowering)."""

    time_sec: float
    """Абсолютная позиция (конец сегмента)."""

    hold_sec: float
    """Рекомендуемая пауза после этой точки перед следующим cut."""

    pitch_drop_hz: float
    """Сколько Hz упало от начала window к концу."""

    confidence: float
    """0..1 — насколько сильный сигнал (драмop + voiced density)."""


async def detect_punchline_moments(
    audio_path: Path,
    segments: list[tuple[float, float]],
    *,
    pitch_drop_hz: float = 20.0,
    hold_sec: float = 0.45,
) -> list[PunchlineMoment]:
    """Детектирует punchline moments в заданных сегментах.

    ``segments`` — список ``(start_sec, end_sec)`` кортежей. Обычно это
    границы смысловых сегментов от Whisper (transcript segments) или
    chunk'и pipeline.

    ``pitch_drop_hz`` — минимальный drop F0 в Hz за final window.

    ``hold_sec`` — рекомендуемая пауза после punchline.
    """
    if not segments:
        return []

    return await asyncio.to_thread(
        _detect_punchline_sync,
        audio_path,
        segments,
        pitch_drop_hz,
        hold_sec,
    )


def _detect_punchline_sync(
    audio_path: Path,
    segments: list[tuple[float, float]],
    pitch_drop_hz: float,
    hold_sec: float,
) -> list[PunchlineMoment]:
    if not audio_path.exists():
        log.warning(
            "punchline_missing_audio",
            reason="audio file not found; pipeline invoked detector on missing path",
            path=str(audio_path),
            segments=len(segments),
        )
        return []

    try:
        import parselmouth
        from parselmouth.praat import call
    except ImportError:
        # Легитимный degraded mode: optional dep не установлена.
        # Info-log один раз — не warning-worthy spam.
        log.info("punchline_parselmouth_missing", hint="install praat-parselmouth")
        return []

    try:
        sound = parselmouth.Sound(str(audio_path))
    except Exception as exc:
        log.warning(
            "punchline_audio_load_failed",
            reason="parselmouth.Sound raised; audio may be corrupted or unsupported",
            path=str(audio_path),
            error=str(exc)[:200],
        )
        return []

    try:
        pitch = call(sound, "To Pitch", 0.0, 75, 600)
    except Exception as exc:
        log.warning(
            "punchline_pitch_extraction_failed",
            reason="Praat 'To Pitch' call raised",
            path=str(audio_path),
            error=str(exc)[:200],
        )
        return []

    moments: list[PunchlineMoment] = []
    for start_sec, end_sec in segments:
        if end_sec - start_sec < _MIN_SEGMENT_SEC:
            continue
        window_start = max(start_sec, end_sec - _FINAL_LOWERING_WINDOW_SEC)
        moment = _analyze_final_window(
            pitch, window_start, end_sec, pitch_drop_hz, hold_sec
        )
        if moment is not None:
            moments.append(moment)

    if moments:
        log.info(
            "punchline_detector_done",
            moments=len(moments),
            segments=len(segments),
            pitch_drop_hz=pitch_drop_hz,
        )
    return moments


def _analyze_final_window(
    pitch: object,
    window_start: float,
    window_end: float,
    pitch_drop_hz: float,
    hold_sec: float,
) -> PunchlineMoment | None:
    from parselmouth.praat import call as _call

    try:
        # Sampled F0 values across final window.
        # Praat Pitch object: use `Get value at time` for 3 points.
        sample_times = [
            window_start,
            (window_start + window_end) / 2.0,
            window_end - 0.02,
        ]
        values: list[float] = []
        for t in sample_times:
            try:
                v = _call(pitch, "Get value at time", t, "Hertz", "Linear")
            except Exception:
                # Per-sample failure внутри loop — pitch в этой точке
                # невычислим; пропускаем точку, не весь segment. Не логируем
                # (hot path: тысячи сегментов × 3 сэмпла = spam).
                continue
            if isinstance(v, int | float) and v > 0:
                values.append(float(v))
    except Exception as exc:
        # Catastrophic failure построения sample_times (не Praat call).
        # Per-segment — не спамим warning, оставляем debug для forensics.
        log.debug(
            "punchline_window_sampling_failed",
            window_start=window_start,
            window_end=window_end,
            error=str(exc)[:200],
        )
        return None

    if len(values) < _MIN_VOICED_FRAMES:
        # Легитимный: сегмент заканчивается unvoiced tail (пауза, шум).
        return None

    pitch_begin = values[0]
    pitch_end = values[-1]
    drop = pitch_begin - pitch_end

    if drop < pitch_drop_hz:
        # Легитимный: большинство сегментов не заканчиваются punchline.
        return None

    # Confidence растёт с величиной drop'а и плотностью voiced.
    voiced_density = len(values) / len(
        [window_start, (window_start + window_end) / 2.0, window_end - 0.02]
    )
    drop_intensity = min(1.0, drop / (pitch_drop_hz * 2.5))
    confidence = round((voiced_density * 0.5 + drop_intensity * 0.5), 3)

    return PunchlineMoment(
        time_sec=round(window_end, 3),
        hold_sec=round(hold_sec, 3),
        pitch_drop_hz=round(drop, 2),
        confidence=confidence,
    )


__all__ = [
    "PunchlineMoment",
    "detect_punchline_moments",
]
