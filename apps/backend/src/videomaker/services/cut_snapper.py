"""FEAT-#E: Word-aware cut boundary snapping.

На стыках cuts часто слышны click-артефакты — даже 25ms adaptive crossfade
не всегда их убирает, если срез попадает в середину слова (особенно на
согласных с/ш/ч/т). Решение: прилепить границы cut'а к ближайшему
word boundary из stable-ts word-timestamps (точность ±20-30мс).

Правила:
* snap `source_start_sec` к началу ближайшего слова в окне ±``snap_window_sec``
  (по умолчанию 30мс)
* snap `source_end_sec` к концу ближайшего слова в том же окне
* Если в окне нет ни одного слова — оставляем границу как есть (тишина)
* Аналогично для audio-window (J/L-cuts) — не трогаем если он отличается
  от video-окна

Применяется в pipeline после pause_compression/filler_removal и ДО
jl_cut_planner, чтобы granularity границ была максимально clean.

Не пишем unit-тесты (user rule feedback_no_extra_tests).
"""

from __future__ import annotations

from dataclasses import dataclass

from videomaker.core.logging import get_logger
from videomaker.services.project_graph import CutSpec
from videomaker.services.transcribers.base import TranscribedWord

log = get_logger(__name__)


@dataclass(frozen=True)
class CutSnapStats:
    """Статистика snap-операций на одном рилсе."""

    total_boundaries: int
    snapped_starts: int
    snapped_ends: int
    max_shift_sec: float

    @property
    def any_snapped(self) -> bool:
        return self.snapped_starts + self.snapped_ends > 0


def snap_cuts_to_words(
    cuts: list[CutSpec],
    words: list[TranscribedWord],
    *,
    snap_window_sec: float = 0.03,
) -> tuple[list[CutSpec], CutSnapStats]:
    """Возвращает новые cuts с границами, прилепленными к word boundaries.

    Args:
        cuts: текущие cuts рилса.
        words: все word-timestamps транскрипта (отсортированы по start).
        snap_window_sec: полуокно поиска ближайшего слова (± сек).
    """

    if not cuts or not words:
        return cuts, CutSnapStats(0, 0, 0, 0.0)

    sorted_words = sorted(words, key=lambda w: w.start)
    starts = [w.start for w in sorted_words]
    ends = [w.end for w in sorted_words]

    new_cuts: list[CutSpec] = []
    snapped_starts = 0
    snapped_ends = 0
    max_shift = 0.0

    for cut in cuts:
        new_start = _snap_to_nearest(
            cut.source_start_sec, starts, snap_window_sec
        )
        new_end = _snap_to_nearest(
            cut.source_end_sec, ends, snap_window_sec
        )

        # Инвариант: start < end. Если snap нарушил — откатываемся.
        if new_end <= new_start + 0.1:
            new_cuts.append(cut)
            continue

        start_shift = abs(new_start - cut.source_start_sec)
        end_shift = abs(new_end - cut.source_end_sec)
        if start_shift > 1e-4:
            snapped_starts += 1
            max_shift = max(max_shift, start_shift)
        if end_shift > 1e-4:
            snapped_ends += 1
            max_shift = max(max_shift, end_shift)

        new_cuts.append(
            CutSpec(
                source_start_sec=round(new_start, 3),
                source_end_sec=round(new_end, 3),
                audio_source_start_sec=cut.audio_source_start_sec,
                audio_source_end_sec=cut.audio_source_end_sec,
            )
        )

    stats = CutSnapStats(
        total_boundaries=2 * len(cuts),
        snapped_starts=snapped_starts,
        snapped_ends=snapped_ends,
        max_shift_sec=round(max_shift, 3),
    )
    return new_cuts, stats


def _snap_to_nearest(
    target_sec: float, anchors: list[float], window_sec: float
) -> float:
    """Находит ближайший anchor в пределах ``[target - w, target + w]``.

    Linear scan — O(N) на вызов. Для большого количества слов (сотни-тысячи)
    на 40 рилсов это всё равно millisecond-level. Binary search можно
    добавить если профилировка покажет узкое место.
    """

    best = target_sec
    best_delta = window_sec + 1e-9
    for a in anchors:
        if a < target_sec - window_sec:
            continue
        if a > target_sec + window_sec:
            break
        delta = abs(a - target_sec)
        if delta < best_delta:
            best = a
            best_delta = delta
    return best
