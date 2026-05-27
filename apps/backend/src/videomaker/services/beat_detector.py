"""T2.5 — Rhythm-aware cutting (librosa beat detection).

Детектирует beat-timestamps в audio-дорожке рилса через librosa и
предоставляет `snap_cuts_to_beats` для прилепливания cut-границ к
ближайшему beat'у (±max_shift_sec). Даёт «музыкально-синхронные»
переклейки — cut'ы попадают в bar/beat, а не посередине фразы.

Полезно для профиля **fashion** (показы, reels с музыкой) и любых
видео где фоновая музыка задаёт ритм. Для чистого talking_head обычно
бесполезно — beat detection на голосе даёт случайные timestamps.

Graceful-degrade: если librosa падает (нестандартный audio format,
очень короткий файл, no percussive content) — возвращаем [] и
snap-функция превращается в no-op. Pipeline продолжает работу без
rhythm-snap.

Ленивый импорт librosa внутри функций — загружается только при
вызове (librosa import тяжёлый ~1s, не хочется на каждом импорте
pipeline.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from videomaker.core.logging import get_logger
from videomaker.services.project_graph import CutSpec

log = get_logger(__name__)


#: Макс. сдвиг cut-границы к beat'у. 150 мс — edge сохраняет слово
#: целиком (stable-ts word-timestamps ±30ms), но находит ближайший
#: ритмический удар. Больше → звучит как «промах» относительно речи.
_DEFAULT_MAX_SHIFT_SEC = 0.15


@dataclass(slots=True, frozen=True)
class BeatSnapStats:
    snapped_starts: int
    snapped_ends: int
    total_beats: int
    max_shift_sec: float

    @property
    def any_snapped(self) -> bool:
        return self.snapped_starts > 0 or self.snapped_ends > 0


async def detect_beats(audio_path: Path) -> list[float]:
    """Возвращает список beat-timestamps (сек) для audio файла.

    Использует librosa.beat.beat_track с default параметрами (sr=22050,
    hop_length=512). Пустой список если:
    * Файл недоступен
    * Librosa падает (нестандартный формат, non-percussive audio)
    * Детектировано < 4 beats (вероятно ложные сработки на голосе)

    Async wrapper чтобы не блокировать event loop — librosa.load может
    идти 200-500ms на среднем рилсе.
    """
    import asyncio

    return await asyncio.to_thread(_detect_beats_sync, audio_path)


def _detect_beats_sync(audio_path: Path) -> list[float]:
    if not audio_path.exists():
        log.warning("beat_detector_missing_audio", path=str(audio_path))
        return []

    try:
        import librosa

        y, sr = librosa.load(str(audio_path), mono=True)
        tempo_arr, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        beat_times = librosa.frames_to_time(beat_frames, sr=sr)
        beat_list = [float(t) for t in beat_times]
        # librosa.beat.beat_track может вернуть numpy или float. Tempo может
        # быть 0-D array или scalar — привести к float для логов.
        try:
            tempo = float(tempo_arr)
        except (TypeError, ValueError):
            tempo = 0.0
    except Exception as exc:
        log.warning(
            "beat_detector_failed_graceful",
            path=str(audio_path),
            error=str(exc),
        )
        return []

    if len(beat_list) < 4:
        log.info(
            "beat_detector_too_few_beats",
            count=len(beat_list),
            hint="audio likely non-musical (talking head) → beat snap skipped",
        )
        return []

    log.info(
        "beat_detector_done",
        beats=len(beat_list),
        tempo_bpm=round(tempo, 1),
        path=str(audio_path),
    )
    return beat_list


def snap_cuts_to_beats(
    cuts: list[CutSpec],
    beats: list[float],
    *,
    max_shift_sec: float = _DEFAULT_MAX_SHIFT_SEC,
) -> tuple[list[CutSpec], BeatSnapStats]:
    """Прилепляет source_start/end каждого cut'а к ближайшему beat'у.

    Только если сдвиг не превышает ``max_shift_sec`` и не ломает
    минимальную длительность cut'а (max(0.1s, 10% исходной длительности)).

    beats=[] или пустой cuts → no-op. Cut'ы возвращаются без изменений,
    BeatSnapStats=zero.

    Важно: ``audio_source_*`` поля (J/L-cut) НЕ трогаем — beat snap
    применяется только к video-границам. Если audio уже смещён, он
    остаётся смещённым относительно новых video-границ.
    """
    if not beats or not cuts:
        return list(cuts), BeatSnapStats(0, 0, 0, 0.0)

    sorted_beats = sorted(beats)
    new_cuts: list[CutSpec] = []
    snapped_starts = 0
    snapped_ends = 0
    max_shift = 0.0

    for cut in cuts:
        new_start = _nearest_beat_within(
            cut.source_start_sec, sorted_beats, max_shift_sec
        )
        new_end = _nearest_beat_within(
            cut.source_end_sec, sorted_beats, max_shift_sec
        )

        if new_start == cut.source_start_sec:
            applied_start = cut.source_start_sec
        else:
            applied_start = new_start
            snapped_starts += 1
            max_shift = max(max_shift, abs(new_start - cut.source_start_sec))

        if new_end == cut.source_end_sec:
            applied_end = cut.source_end_sec
        else:
            applied_end = new_end
            snapped_ends += 1
            max_shift = max(max_shift, abs(new_end - cut.source_end_sec))

        min_duration = max(0.1, (cut.source_end_sec - cut.source_start_sec) * 0.1)
        if applied_end - applied_start < min_duration:
            # Snap сломал бы длительность — откатываемся.
            new_cuts.append(cut)
            continue

        if applied_start == cut.source_start_sec and applied_end == cut.source_end_sec:
            new_cuts.append(cut)
        else:
            new_cuts.append(
                cut.model_copy(
                    update={
                        "source_start_sec": round(applied_start, 3),
                        "source_end_sec": round(applied_end, 3),
                    }
                )
            )

    return (
        new_cuts,
        BeatSnapStats(
            snapped_starts=snapped_starts,
            snapped_ends=snapped_ends,
            total_beats=len(sorted_beats),
            max_shift_sec=round(max_shift, 3),
        ),
    )


def _nearest_beat_within(
    t: float, beats: list[float], max_shift_sec: float
) -> float:
    """Возвращает beat ближайший к `t` если сдвиг ≤ max_shift_sec, иначе `t`."""
    if not beats:
        return t
    # Binary-search ближайшего beat'а.
    lo, hi = 0, len(beats) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if beats[mid] < t:
            lo = mid + 1
        else:
            hi = mid
    # Проверяем mid-1 и mid.
    candidates: list[float] = []
    if lo > 0:
        candidates.append(beats[lo - 1])
    if lo < len(beats):
        candidates.append(beats[lo])
    best = min(candidates, key=lambda b: abs(b - t), default=t)
    if abs(best - t) <= max_shift_sec:
        return best
    return t


async def detect_onsets(audio_path: Path) -> list[float]:
    """T10.2 — речевые onsets для snap'а в talking-head контенте.

    Использует ``librosa.onset.onset_detect`` — находит начало слогов/слов
    по spectral flux. Для talking-head без музыки работает лучше чем
    beat tracking (который там пустой).

    Параметры tight window (pre_max/post_max=0.03, pre_avg/post_avg=0.1)
    отсекают ложные onsets внутри речевого сигнала.

    Возвращает [] если файла нет или librosa падает (graceful degrade).
    """
    import asyncio

    return await asyncio.to_thread(_detect_onsets_sync, audio_path)


def _detect_onsets_sync(audio_path: Path) -> list[float]:
    if not audio_path.exists():
        log.warning("onset_detector_missing_audio", path=str(audio_path))
        return []

    try:
        import librosa
        import numpy as np

        y, sr = librosa.load(str(audio_path), sr=22050, mono=True)
        if len(y) < sr * 2:
            return []
        onset_env = librosa.onset.onset_strength(y=y, sr=sr, aggregate=np.median)
        onsets = librosa.onset.onset_detect(
            onset_envelope=onset_env,
            sr=sr,
            units="time",
            pre_max=0.03,
            post_max=0.03,
            pre_avg=0.1,
            post_avg=0.1,
        )
        onset_list = [float(t) for t in onsets]
    except Exception as exc:
        log.warning(
            "onset_detector_failed_graceful",
            path=str(audio_path),
            error=str(exc),
        )
        return []

    if len(onset_list) < 4:
        log.info(
            "onset_detector_too_few_onsets",
            count=len(onset_list),
            hint="audio likely silent/ambient → onset snap skipped",
        )
        return []

    log.info(
        "onset_detector_done",
        onsets=len(onset_list),
        path=str(audio_path),
    )
    return onset_list


def snap_cuts_to_reference(
    cuts: list[CutSpec],
    reference_times: list[float],
    *,
    max_shift_sec: float = _DEFAULT_MAX_SHIFT_SEC,
) -> tuple[list[CutSpec], BeatSnapStats]:
    """Generalized snap — работает с любыми reference_times (beats ИЛИ onsets).

    Это extraction generalized-логики из ``snap_cuts_to_beats`` без потери
    backward compatibility. Новый код (T10.2) вызывает эту функцию с
    onsets, legacy код с beats.
    """
    return snap_cuts_to_beats(cuts, reference_times, max_shift_sec=max_shift_sec)


__all__ = [
    "BeatSnapStats",
    "detect_beats",
    "detect_onsets",
    "snap_cuts_to_beats",
    "snap_cuts_to_reference",
]
