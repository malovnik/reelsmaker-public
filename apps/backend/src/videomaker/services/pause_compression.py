"""Pause compression: сжатие пауз внутри cut'а на основе Silero VAD.

TIER2-#14. Паузы длиннее ``threshold_sec`` укорачиваются до ``keep_sec``
(половина до, половина после) за счёт разбиения одного ``CutSpec`` на
несколько под-cut'ов. Итоговый filter_graph concat склеит их — в
перформанс-речи рилса пропадают «медленные» диалоговые паузы.

Зависит от ``services.vad.SpeechSegment`` (TIER1-#8 Silero VAD). VAD
вызывается ОДИН раз на source audio per job, результат шарится между
всеми cuts всех reels — дёшево.

Функция ``compress_pauses_in_cuts`` — pure (без I/O), принимает уже
детектированные speech segments. Тестируется без ffmpeg/VAD.
"""

from __future__ import annotations

from dataclasses import dataclass

from videomaker.core.logging import get_logger
from videomaker.services.project_graph import CutSpec
from videomaker.services.vad import SpeechSegment

log = get_logger(__name__)


@dataclass(slots=True, frozen=True)
class PauseCompressionStats:
    """Статистика сжатия пауз — для логов и reel-meta."""

    cuts_in: int
    cuts_out: int
    pauses_compressed: int
    time_saved_sec: float


def _pauses_in_range(
    speech: list[SpeechSegment],
    cut_start: float,
    cut_end: float,
    min_pause_sec: float,
) -> list[tuple[float, float]]:
    """Возвращает [(pause_start, pause_end), ...] внутри [cut_start, cut_end].

    Gap между speech-сегментами = пауза. Head/tail silence cut'а
    игнорируется — они добавляют дыхание, не затрачивают видео-тайминг.
    """

    pauses: list[tuple[float, float]] = []
    prev_end = cut_start
    for seg in speech:
        if seg.end_sec <= cut_start:
            continue
        if seg.start_sec >= cut_end:
            break
        seg_start = max(seg.start_sec, cut_start)
        seg_end = min(seg.end_sec, cut_end)
        # Gap ДО этого speech-сегмента
        if seg_start - prev_end >= min_pause_sec and prev_end > cut_start + 0.001:
            pauses.append((prev_end, seg_start))
        prev_end = max(prev_end, seg_end)
    return pauses


def _keep_sec_from_context(
    words_before_pause: list,
    default_keep_sec: float,
) -> float:
    """T8.3 — контекст-зависимая длительность сохраняемой паузы.

    - точка/восклицание/многоточие в конце → 0.25s (финал мысли)
    - вопрос ? → 0.35s (риторическая пауза)
    - запятая → 0.12s
    - иначе → default_keep_sec
    """

    if not words_before_pause:
        return default_keep_sec
    last_word = words_before_pause[-1]
    text = getattr(last_word, "text", None)
    if not text:
        text = getattr(last_word, "word", "") or ""
    text = text.strip()
    if text.endswith((".", "!", "…")):
        return 0.25
    if text.endswith("?"):
        return 0.35
    if text.endswith(","):
        return 0.12
    return default_keep_sec


def compress_pauses_in_cuts(
    cuts: list[CutSpec],
    speech: list[SpeechSegment],
    *,
    min_pause_sec: float = 0.4,
    keep_sec: float = 0.2,
    context_aware_keep_sec: bool = False,
    words: list | None = None,
) -> tuple[list[CutSpec], PauseCompressionStats]:
    """Разбивает cuts так, чтобы длинные паузы были укорочены до ``keep_sec``.

    На каждой найденной паузе длительностью > ``min_pause_sec``:
    * cut заканчивается в ``pause_start + keep_sec/2``
    * следующий под-cut начинается в ``pause_end - keep_sec/2``
    * итого между cuts получается silence длиной ``keep_sec`` (по 1/2
      до/после оригинального голосового контента) — речь не звучит
      «обрезанной», дыхание сохраняется.

    Если в cut'e нет пауз > ``min_pause_sec`` — он остаётся неизменным.

    Если ``context_aware_keep_sec=True`` и ``words`` передан — keep_sec
    на каждой паузе вычисляется по пунктуации последнего слова перед
    паузой (см. ``_keep_sec_from_context``). Это даёт «дыхание» после
    точки/вопроса, коротче после запятой — ближе к ручному монтажу.

    Возвращает ``(new_cuts, stats)``. Порядок сохраняется.
    """

    if not cuts:
        return [], PauseCompressionStats(0, 0, 0, 0.0)
    if keep_sec >= min_pause_sec:
        raise ValueError(
            f"keep_sec ({keep_sec}) must be < min_pause_sec ({min_pause_sec})"
        )

    new_cuts: list[CutSpec] = []
    pauses_total = 0
    time_saved = 0.0

    for cut in cuts:
        pauses = _pauses_in_range(
            speech, cut.source_start_sec, cut.source_end_sec, min_pause_sec
        )
        if not pauses:
            new_cuts.append(cut)
            continue

        cursor = cut.source_start_sec
        for pause_start, pause_end in pauses:
            original_pause = pause_end - pause_start
            # Context-aware keep_sec: длительность зависит от пунктуации
            # последнего слова перед паузой.
            if context_aware_keep_sec and words:
                words_before = [
                    w for w in words
                    if getattr(w, "end", 0.0) <= pause_start + 0.02
                ]
                effective_keep = _keep_sec_from_context(words_before, keep_sec)
            else:
                effective_keep = keep_sec
            # Safety: keep < min_pause, иначе создаём негативный интервал.
            if effective_keep >= min_pause_sec:
                effective_keep = keep_sec
            half_keep = effective_keep / 2.0
            new_end = pause_start + half_keep
            next_start = pause_end - half_keep
            # Guard: не создаём невалидные cut'ы
            if new_end <= cursor or next_start <= new_end:
                continue
            new_cuts.append(
                CutSpec(
                    source_start_sec=round(cursor, 3),
                    source_end_sec=round(new_end, 3),
                )
            )
            pauses_total += 1
            time_saved += original_pause - effective_keep
            cursor = next_start
        # Финальный сегмент от последней паузы до end
        if cursor < cut.source_end_sec - 0.01:
            new_cuts.append(
                CutSpec(
                    source_start_sec=round(cursor, 3),
                    source_end_sec=round(cut.source_end_sec, 3),
                )
            )

    stats = PauseCompressionStats(
        cuts_in=len(cuts),
        cuts_out=len(new_cuts),
        pauses_compressed=pauses_total,
        time_saved_sec=round(time_saved, 2),
    )
    log.info(
        "pause_compression_done",
        cuts_in=stats.cuts_in,
        cuts_out=stats.cuts_out,
        pauses=stats.pauses_compressed,
        saved_sec=stats.time_saved_sec,
    )
    return new_cuts, stats


__all__ = [
    "PauseCompressionStats",
    "compress_pauses_in_cuts",
]
