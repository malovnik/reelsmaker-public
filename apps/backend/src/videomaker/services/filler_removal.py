"""Filler removal: вырезает filler-слова («эм/ну/вот/um/uh») из cuts.

TIER2-#13. Использует word-level метки `is_filler` (TIER1-#3 лексикон
русских + английских паразитов) и опционально `confidence<threshold`
для агрессивного режима. stable-ts (TIER1-#7) даёт word-timestamps
±20-30ms — граница среза на уровне реального начала/конца звука,
не слога.

Результат: вместо монолитного CutSpec получается список под-cut'ов,
между которыми filler и короткие буферы отсутствуют. filter_graph
concat склеит их с 25ms afade crossfade на стыках (TIER1-#4) →
переход не слышен.
"""

from __future__ import annotations

from dataclasses import dataclass

from videomaker.core.logging import get_logger
from videomaker.services.project_graph import CutSpec
from videomaker.services.transcribers.base import TranscribedWord

log = get_logger(__name__)


@dataclass(slots=True, frozen=True)
class FillerRemovalStats:
    """Статистика filler-removal для логов и reel-meta."""

    cuts_in: int
    cuts_out: int
    fillers_removed: int
    time_saved_sec: float


def _is_filler_word(
    word: TranscribedWord,
    *,
    aggressive: bool,
    confidence_threshold: float,
) -> bool:
    """True если слово подлежит удалению.

    Consensus mode (default): только `is_filler=True` по лексикону —
    безопасно, не ломает legitimate text.
    Aggressive: также ловит `confidence < threshold` — захватывает
    невнятные слова, риск потерять legitimate.
    """

    if word.is_filler:
        return True
    return (
        aggressive
        and word.confidence is not None
        and word.confidence < confidence_threshold
    )


def _fillers_in_cut(
    words: list[TranscribedWord],
    cut_start: float,
    cut_end: float,
    *,
    aggressive: bool,
    confidence_threshold: float,
) -> list[TranscribedWord]:
    """Filler-слова попадающие в [cut_start, cut_end] отсортированные по start."""

    result = [
        w for w in words
        if w.start >= cut_start
        and w.end <= cut_end + 0.001
        and _is_filler_word(
            w, aggressive=aggressive, confidence_threshold=confidence_threshold
        )
    ]
    result.sort(key=lambda w: w.start)
    return result


def remove_fillers_from_cuts(
    cuts: list[CutSpec],
    words: list[TranscribedWord],
    *,
    aggressive: bool = False,
    confidence_threshold: float = 0.35,
    edge_buffer_sec: float = 0.03,
) -> tuple[list[CutSpec], FillerRemovalStats]:
    """Разбивает cuts так, чтобы filler-слова (±буфер) были вырезаны.

    * ``aggressive=False`` — только лексические filler (`is_filler=True`).
    * ``aggressive=True`` — также слова с ``confidence < confidence_threshold``.
    * ``edge_buffer_sec`` — срез слегка раньше и позже filler, чтобы
      убрать «утечку» шипящих / аспираций. 30 мс — компромисс между
      чистотой среза и риском обрезать легитимное слово рядом.
    """

    if not cuts:
        return [], FillerRemovalStats(0, 0, 0, 0.0)

    new_cuts: list[CutSpec] = []
    fillers_total = 0
    time_saved = 0.0

    for cut in cuts:
        fillers = _fillers_in_cut(
            words,
            cut.source_start_sec,
            cut.source_end_sec,
            aggressive=aggressive,
            confidence_threshold=confidence_threshold,
        )
        if not fillers:
            new_cuts.append(cut)
            continue

        cursor = cut.source_start_sec
        for w in fillers:
            seg_end = max(cursor, w.start - edge_buffer_sec)
            if seg_end - cursor > 0.05:
                # Минимум 50ms сегмент — короче не имеет смысла (artefact).
                new_cuts.append(
                    CutSpec(
                        source_start_sec=round(cursor, 3),
                        source_end_sec=round(seg_end, 3),
                    )
                )
            # Удалённый отрезок = filler + буфера с обеих сторон
            deleted = (w.end + edge_buffer_sec) - (w.start - edge_buffer_sec)
            time_saved += max(0.0, deleted)
            cursor = min(cut.source_end_sec, w.end + edge_buffer_sec)
            fillers_total += 1

        # Хвост после последнего filler
        if cursor < cut.source_end_sec - 0.05:
            new_cuts.append(
                CutSpec(
                    source_start_sec=round(cursor, 3),
                    source_end_sec=round(cut.source_end_sec, 3),
                )
            )

    stats = FillerRemovalStats(
        cuts_in=len(cuts),
        cuts_out=len(new_cuts),
        fillers_removed=fillers_total,
        time_saved_sec=round(time_saved, 2),
    )
    log.info(
        "filler_removal_done",
        cuts_in=stats.cuts_in,
        cuts_out=stats.cuts_out,
        fillers=stats.fillers_removed,
        saved_sec=stats.time_saved_sec,
        aggressive=aggressive,
    )
    return new_cuts, stats


__all__ = [
    "FillerRemovalStats",
    "remove_fillers_from_cuts",
]
