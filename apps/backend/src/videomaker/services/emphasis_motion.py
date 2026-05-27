"""T10.3 + T10.7 — emphasis motion planner (punch-in zoom + Ken Burns).

Генерирует список motion-keyframes которые render-стадия применяет через
FFmpeg ``zoompan`` filter. Планирует ДВА типа motion effects:

T10.3 Punch-in zoom (эмоциональные акценты):
    На stressed syllables (Parselmouth intensity peaks выше mean+0.5*std)
    вставляет цикл: 1.00x → 1.06x за 5 кадров (167мс @ 30fps, ease-out) →
    hold 500мс → 1.06x → 1.00x за 10 кадров (333мс ease-in). Вероятность
    применения настраивается (default 30% stressed moments).

T10.7 Ken Burns drift (статичные шоты):
    Медленный zoom 0.3% per second (default), max 1.025x за длинный шот.
    Для статики без punch-in — создаёт ощущение что камера «дышит».
    Центрирование на существующем crop center (T2.1 face tracking).

Интерфейс:
    moments = await detect_emphasis_moments(audio_path, window_segments=[...])
    # → list[EmphasisMoment] с intensity peak timestamps

    plan = plan_punch_in_keyframes(
        emphasis_moments,
        reel_duration_sec=30,
        fps=30,
        probability=0.3,
        zoom_scale=1.06,
        hold_ms=500,
    )
    # → list[ZoomKeyframe] для FFmpeg zoompan expression

    drift = plan_ken_burns_drift(
        reel_duration_sec=8.0,
        fps=30,
        scale_per_sec=0.003,
        max_scale=1.025,
    )
    # → (start_scale, end_scale, duration_frames)

Graceful degrade: Parselmouth отсутствует → emphasis moments=[] →
punch-in возвращает []. Ken Burns — pure math, никогда не падает.
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from pathlib import Path

from videomaker.core.logging import get_logger

log = get_logger(__name__)


@dataclass(slots=True, frozen=True)
class EmphasisMoment:
    """Timestamp в аудио с acoustic emphasis (stressed syllable)."""

    time_sec: float
    """Абсолютная позиция пика."""

    intensity_db: float
    """Acoustic intensity (RMS, dB FS)."""

    prominence: float
    """0..1 насколько выделяется над mean+std окружения."""


@dataclass(slots=True, frozen=True)
class ZoomKeyframe:
    """Инструкция для FFmpeg zoompan filter — один цикл zoom-in/hold/zoom-out."""

    start_frame: int
    """Frame номер где начинается zoom-in (абсолютный в рилсе)."""

    zoom_in_frames: int
    """Число кадров зумирования внутрь."""

    peak_zoom: float
    """Пиковое значение scale (1.06 = 6% zoom)."""

    hold_frames: int
    """Число кадров удержания пика."""

    zoom_out_frames: int
    """Число кадров возврата к 1.0x."""

    center_x: float
    """Относительное x центра zoom'а (0..1)."""

    center_y: float
    """Относительное y центра zoom'а (0..1)."""


@dataclass(slots=True, frozen=True)
class KenBurnsPlan:
    """Slow-drift zoom для статичного шота (T10.7)."""

    start_scale: float
    end_scale: float
    duration_frames: int
    center_x: float
    center_y: float


async def detect_emphasis_moments(
    audio_path: Path,
    *,
    min_segment_sec: float = 3.0,
    max_segment_sec: float | None = None,
) -> list[EmphasisMoment]:
    """T10.3 — находит intensity peaks (stressed syllables) через Parselmouth.

    Peak = intensity > mean + 0.5 * std в окне аудио. Используется для
    планирования punch-in zoom эффектов.

    Graceful: Parselmouth недоступен → []. Аудио короче min_segment_sec → [].
    """
    return await asyncio.to_thread(
        _detect_emphasis_sync, audio_path, min_segment_sec, max_segment_sec
    )


def _detect_emphasis_sync(
    audio_path: Path,
    min_segment_sec: float,
    max_segment_sec: float | None,
) -> list[EmphasisMoment]:
    if not audio_path.exists():
        return []
    try:
        import numpy as np
        import parselmouth
        from parselmouth.praat import call
    except ImportError:
        return []

    try:
        sound = parselmouth.Sound(str(audio_path))
    except Exception as exc:
        log.debug("emphasis_audio_load_failed", error=str(exc))
        return []

    duration = sound.get_total_duration()
    if duration < min_segment_sec:
        return []

    try:
        intensity = call(sound, "To Intensity", 100, 0.0, "yes")
        values = intensity.values[0]
        xs = intensity.xs()
    except Exception as exc:
        log.debug("emphasis_intensity_failed", error=str(exc))
        return []

    if len(values) < 10:
        return []

    mean_i = float(np.mean(values))
    std_i = float(np.std(values))
    threshold = mean_i + 0.5 * std_i

    moments: list[EmphasisMoment] = []
    i = 1
    while i < len(values) - 1:
        v = float(values[i])
        if v > threshold and v > values[i - 1] and v > values[i + 1]:
            if max_segment_sec is not None and xs[i] > max_segment_sec:
                break
            prominence = min(1.0, (v - threshold) / max(std_i, 1.0))
            moments.append(
                EmphasisMoment(
                    time_sec=float(xs[i]),
                    intensity_db=v,
                    prominence=round(prominence, 3),
                )
            )
            i += 5
        else:
            i += 1

    log.info(
        "emphasis_detector_done",
        peaks=len(moments),
        duration_sec=round(duration, 2),
        path=str(audio_path),
    )
    return moments


def plan_punch_in_keyframes(
    emphasis_moments: list[EmphasisMoment],
    *,
    reel_duration_sec: float,
    fps: int = 30,
    probability: float = 0.3,
    zoom_scale: float = 1.06,
    hold_ms: int = 500,
    center_x: float = 0.5,
    center_y: float = 0.5,
    seed: int | None = None,
) -> list[ZoomKeyframe]:
    """T10.3 — планирует punch-in zoom keyframes из emphasis moments.

    Структура каждого keyframe: zoom_in 5 frames → hold hold_ms → zoom_out
    10 frames. Timing инвариантен к fps — 5 frames = 167мс @ 30fps,
    167мс @ 60fps. Подбирается через fps параметр.

    ``probability`` — доля emphasis moments которые получают zoom (избегаем
    zoom'а на каждом слове — становится cartoonish). Research: 30% default.

    ``seed`` — для детерминированности (тесты). None = случайная выборка.
    """
    if not emphasis_moments or reel_duration_sec <= 0:
        return []

    rng = random.Random(seed)
    # Зажать timings под fps.
    zoom_in_frames = max(1, round(fps * (167 / 1000)))  # ~167мс
    zoom_out_frames = max(1, round(fps * (333 / 1000)))  # ~333мс
    hold_frames = max(1, round(fps * (hold_ms / 1000)))

    total_frames = round(reel_duration_sec * fps)

    keyframes: list[ZoomKeyframe] = []
    for moment in emphasis_moments:
        if rng.random() > probability:
            continue
        start_frame = round(moment.time_sec * fps)
        cycle_frames = zoom_in_frames + hold_frames + zoom_out_frames
        if start_frame < 0 or start_frame + cycle_frames > total_frames:
            continue
        keyframes.append(
            ZoomKeyframe(
                start_frame=start_frame,
                zoom_in_frames=zoom_in_frames,
                peak_zoom=zoom_scale,
                hold_frames=hold_frames,
                zoom_out_frames=zoom_out_frames,
                center_x=center_x,
                center_y=center_y,
            )
        )

    # Сортируем по времени + гарантируем непересечение (cut поздний если
    # наползает на ранний).
    keyframes.sort(key=lambda k: k.start_frame)
    non_overlapping: list[ZoomKeyframe] = []
    for kf in keyframes:
        if non_overlapping:
            prev = non_overlapping[-1]
            prev_end = prev.start_frame + prev.zoom_in_frames + prev.hold_frames + prev.zoom_out_frames
            if kf.start_frame < prev_end:
                continue
        non_overlapping.append(kf)

    log.info(
        "punch_in_plan_done",
        keyframes=len(non_overlapping),
        from_moments=len(emphasis_moments),
        probability=probability,
    )
    return non_overlapping


def plan_ken_burns_drift(
    *,
    reel_duration_sec: float,
    fps: int = 30,
    scale_per_sec: float = 0.003,
    max_scale: float = 1.025,
    center_x: float = 0.5,
    center_y: float = 0.5,
) -> KenBurnsPlan | None:
    """T10.7 — планирует slow-drift zoom для длинного статичного шота.

    Возвращает None для шотов короче 3 сек (drift незаметен).

    Формула: end_scale = min(1 + duration * scale_per_sec, max_scale).
    Research defaults: 0.3% per second, max 2.5% zoom за 8+ сек шота.
    """
    if reel_duration_sec < 3.0:
        return None
    end_scale = min(1.0 + reel_duration_sec * scale_per_sec, max_scale)
    duration_frames = round(reel_duration_sec * fps)
    return KenBurnsPlan(
        start_scale=1.0,
        end_scale=round(end_scale, 4),
        duration_frames=duration_frames,
        center_x=center_x,
        center_y=center_y,
    )


def build_ffmpeg_motion_expr(
    keyframes: list[ZoomKeyframe] | None = None,
    ken_burns: KenBurnsPlan | None = None,
    *,
    fps: int = 30,
    frame_width: int = 1080,
    frame_height: int = 1920,
) -> str | None:
    """T10.3 + T10.7 — FFmpeg zoompan expression для motion effects.

    Строит единый ``zoompan=z='<expr>':d=1:fps=<fps>:x=...:y=...:s=WxH``
    который применяется в filter_graph_builder Stage B+ поверх уже
    zoom'нутого кадра (face-tracking).

    Punch-in keyframes: при t внутри [start, start+cycle] — piecewise-linear
    zoom 1.0 → peak_zoom (zoom_in) → hold → peak_zoom → 1.0 (zoom_out).
    Ken Burns: continuous linear zoom от start_scale к end_scale за весь
    шот.

    Возвращает None если нет ни keyframes ни ken_burns (ничего не делать).

    Важно: zoompan с d=1 в таком режиме работает как per-frame evaluator —
    каждый входной кадр даёт один выходной. Без d=1 frame rate удвоится.
    """
    has_kf = bool(keyframes)
    has_kb = ken_burns is not None

    if not has_kf and not has_kb:
        return None

    # on = frame number, zoom expression piecewise
    segments: list[str] = []

    if has_kf:
        assert keyframes is not None
        for kf in keyframes:
            start = kf.start_frame
            zoom_in_end = start + kf.zoom_in_frames
            hold_end = zoom_in_end + kf.hold_frames
            zoom_out_end = hold_end + kf.zoom_out_frames
            peak = kf.peak_zoom

            # zoom_in: 1 → peak linear
            segments.append(
                f"if(between(on,{start},{zoom_in_end - 1}),"
                f"1+(on-{start})*{(peak - 1) / kf.zoom_in_frames:.6f},"
            )
            # hold: peak
            segments.append(
                f"if(between(on,{zoom_in_end},{hold_end - 1}),{peak},"
            )
            # zoom_out: peak → 1 linear
            segments.append(
                f"if(between(on,{hold_end},{zoom_out_end - 1}),"
                f"{peak}-(on-{hold_end})*{(peak - 1) / kf.zoom_out_frames:.6f},"
            )

    # Base value (Ken Burns drift или 1.0)
    if has_kb:
        assert ken_burns is not None
        total = ken_burns.duration_frames
        start_scale = ken_burns.start_scale
        end_scale = ken_burns.end_scale
        if total > 0:
            base_expr = (
                f"{start_scale}+(on/{total})*{end_scale - start_scale:.6f}"
            )
        else:
            base_expr = "1.0"
    else:
        base_expr = "1.0"

    expr = "".join(segments) + base_expr + ")" * (len(segments) // 1 if has_kf else 0)

    # Center (используем center_x/center_y первого keyframe или kf center)
    if has_kf and keyframes:
        cx = keyframes[0].center_x
        cy = keyframes[0].center_y
    elif has_kb and ken_burns is not None:
        cx = ken_burns.center_x
        cy = ken_burns.center_y
    else:
        cx = cy = 0.5

    # zoompan: x = iw/2 - iw/(2*zoom) * (1 - 2*cx), но с center=0.5 → iw/2-iw/zoom/2
    x_expr = f"iw*{cx:.4f}-iw/zoom/2"
    y_expr = f"ih*{cy:.4f}-ih/zoom/2"

    return (
        f"zoompan=z='{expr}':d=1:"
        f"x='{x_expr}':y='{y_expr}':"
        f"fps={fps}:s={frame_width}x{frame_height}"
    )


__all__ = [
    "EmphasisMoment",
    "KenBurnsPlan",
    "ZoomKeyframe",
    "build_ffmpeg_motion_expr",
    "detect_emphasis_moments",
    "plan_ken_burns_drift",
    "plan_punch_in_keyframes",
]
