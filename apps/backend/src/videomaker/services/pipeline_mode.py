"""Pipeline mode detection — dialogue vs travel.

Вспомогательный модуль для Phase 6: определяет какой ветвью пайплайна
обрабатывать видео — стандартной (dialogue, text-driven) или travel
(caption-first, когда транскрипт минимальный).

Критерии travel mode (любой достаточен):
  * WPM < 30 слов/минуту — видео в основном молчит или только фоновая речь
  * silence ratio > 70% — больше 70% времени без слов
  * word_count < 50 — суммарно почти нет транскрипта

В travel mode Story Doctor получает визуальные captions вместо текстовых
evidence как основной строительный материал. Визуальные мотивы (закат,
горы, рынок, лицо в толпе) становятся beat'ами арки.

Dialogue — default при `vision_disabled` или не-travel метриках. Все
существующие интервью/подкасты попадают сюда.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from videomaker.core.logging import get_logger

log = get_logger(__name__)

PipelineMode = Literal["dialogue", "travel"]


@dataclass(slots=True, frozen=True)
class ModeDetectionResult:
    """Решение о режиме + метрики, на которых оно основано."""

    mode: PipelineMode
    word_count: int
    duration_sec: float
    wpm: float
    silence_ratio: float
    reason: str


def detect_pipeline_mode(
    word_count: int,
    duration_sec: float,
    voiced_duration_sec: float,
    *,
    wpm_threshold: float = 30.0,
    silence_ratio_threshold: float = 0.70,
    min_words_for_dialogue: int = 50,
) -> ModeDetectionResult:
    """Классифицирует видео как dialogue или travel по транскрипту.

    Args:
        word_count: сумма слов во всех сегментах транскрипта.
        duration_sec: полная длительность source видео.
        voiced_duration_sec: сумма time(word_end - word_start) где есть слова.
        wpm_threshold: ниже этого порога → travel (default 30).
        silence_ratio_threshold: выше этого → travel (default 0.70).
        min_words_for_dialogue: минимум слов для dialogue (default 50).

    Returns:
        ModeDetectionResult с mode + метриками + reason.
    """
    if duration_sec <= 0:
        return ModeDetectionResult(
            mode="dialogue",
            word_count=word_count,
            duration_sec=0.0,
            wpm=0.0,
            silence_ratio=0.0,
            reason="zero duration → default dialogue",
        )

    wpm = (word_count / duration_sec) * 60.0 if duration_sec > 0 else 0.0
    silence_ratio = 1.0 - min(1.0, max(0.0, voiced_duration_sec / duration_sec))

    if word_count < min_words_for_dialogue:
        reason = f"word_count={word_count} < {min_words_for_dialogue}"
        mode: PipelineMode = "travel"
    elif wpm < wpm_threshold:
        reason = f"wpm={wpm:.1f} < {wpm_threshold}"
        mode = "travel"
    elif silence_ratio > silence_ratio_threshold:
        reason = f"silence_ratio={silence_ratio:.2f} > {silence_ratio_threshold}"
        mode = "travel"
    else:
        reason = (
            f"wpm={wpm:.1f} silence={silence_ratio:.2f} words={word_count} → dialogue"
        )
        mode = "dialogue"

    log.info(
        "pipeline_mode_detected",
        mode=mode,
        word_count=word_count,
        wpm=round(wpm, 2),
        silence_ratio=round(silence_ratio, 3),
        reason=reason,
    )
    return ModeDetectionResult(
        mode=mode,
        word_count=word_count,
        duration_sec=duration_sec,
        wpm=wpm,
        silence_ratio=silence_ratio,
        reason=reason,
    )
