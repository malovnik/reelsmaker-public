"""Silence + filler detection над TranscriptResult.

Подход:
1. Берём слова из транскрипта с word-level timestamps.
2. Считаем gap между соседними словами — если gap ≥ silence.min_silence_sec,
   это пауза → помечаем range для удаления.
3. Отдельно пробегаем по словам и убираем те, что матчатся как филлеры
   (по паттернам из fillers_ru.yaml).
4. Возвращаем CleanedTranscript с оставшимися словами + список removed_ranges.

Не редактирует аудио — это делается в renderer'е через trim/concat.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from videomaker.core.logging import get_logger
from videomaker.services.transcribers.base import (
    TranscribedWord,
    TranscriptResult,
)

log = get_logger(__name__)

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "fillers_ru.yaml"


class RemovedRange(BaseModel):
    start: float = Field(ge=0.0)
    end: float = Field(ge=0.0)
    reason: str


class CleanedTranscript(BaseModel):
    source_duration_sec: float
    removed_ranges: list[RemovedRange] = Field(default_factory=list)
    words: list[TranscribedWord] = Field(default_factory=list)
    kept_duration_sec: float
    stats: dict[str, int | float] = Field(default_factory=dict)


@dataclass(slots=True)
class FillerRule:
    word: str
    pattern: re.Pattern[str]
    multi_word: bool = False
    word_count: int = 1


@dataclass(slots=True)
class SilenceConfig:
    min_silence_sec: float
    edge_padding_sec: float
    rms_threshold_db: float


@dataclass(slots=True)
class CutterConfig:
    fillers: list[FillerRule]
    silence: SilenceConfig


def load_config(path: Path | None = None) -> CutterConfig:
    target = path or DEFAULT_CONFIG_PATH
    raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    fillers: list[FillerRule] = []
    for item in raw.get("fillers") or []:
        pattern = str(item.get("pattern") or item.get("word") or "").strip()
        if not pattern:
            continue
        multi_word = bool(item.get("multi_word", False))
        # Явный word_count из YAML > эвристика по regex. multi-word правилам
        # с квантификаторами `\s+{2,}` регекс-инференция ломается.
        raw_count = item.get("word_count")
        if isinstance(raw_count, int) and raw_count >= 1:
            word_count = raw_count
        else:
            word_count = max(2, pattern.count("\\s") + 1) if multi_word else 1
        fillers.append(
            FillerRule(
                word=str(item.get("word", "")),
                pattern=re.compile(pattern, re.IGNORECASE | re.UNICODE),
                multi_word=multi_word,
                word_count=word_count,
            )
        )
    silence_cfg = raw.get("silence") or {}
    silence = SilenceConfig(
        min_silence_sec=float(silence_cfg.get("min_silence_sec", 0.6)),
        edge_padding_sec=float(silence_cfg.get("edge_padding_sec", 0.08)),
        rms_threshold_db=float(silence_cfg.get("rms_threshold_db", -40.0)),
    )
    return CutterConfig(fillers=fillers, silence=silence)


def clean_transcript(
    transcript: TranscriptResult,
    config: CutterConfig | None = None,
) -> CleanedTranscript:
    cfg = config or load_config()
    removed: list[RemovedRange] = []
    kept_words: list[TranscribedWord] = []

    words = transcript.words or _derive_words_from_segments(transcript)
    if not words:
        return CleanedTranscript(
            source_duration_sec=transcript.duration_sec,
            removed_ranges=[],
            words=[],
            kept_duration_sec=0.0,
            stats={"silence_count": 0, "filler_count": 0, "kept_words": 0},
        )

    _collect_silence_ranges(words, transcript.duration_sec, cfg.silence, removed)

    filler_count = 0
    skip_indices: set[int] = set()
    _mark_multi_word_fillers(words, cfg.fillers, removed, skip_indices)

    single_word_rules = [rule for rule in cfg.fillers if not rule.multi_word]
    for idx, word in enumerate(words):
        if idx in skip_indices:
            filler_count += 1
            continue
        if _is_single_word_filler(word.word, single_word_rules):
            removed.append(
                RemovedRange(start=word.start, end=word.end, reason=f"filler:{word.word}")
            )
            filler_count += 1
            continue
        kept_words.append(word)

    kept_duration = sum(w.end - w.start for w in kept_words)
    removed_sorted = sorted(removed, key=lambda r: (r.start, r.end))

    log.info(
        "silence_cut_done",
        kept_words=len(kept_words),
        removed=len(removed_sorted),
        filler_count=filler_count,
        kept_duration_sec=round(kept_duration, 2),
    )

    return CleanedTranscript(
        source_duration_sec=transcript.duration_sec,
        removed_ranges=removed_sorted,
        words=kept_words,
        kept_duration_sec=kept_duration,
        stats={
            "silence_count": sum(1 for r in removed_sorted if r.reason == "silence"),
            "filler_count": filler_count,
            "kept_words": len(kept_words),
        },
    )


def _derive_words_from_segments(transcript: TranscriptResult) -> list[TranscribedWord]:
    words: list[TranscribedWord] = []
    for seg in transcript.segments:
        words.extend(seg.words)
    return words


def _collect_silence_ranges(
    words: list[TranscribedWord],
    duration_sec: float,
    config: SilenceConfig,
    into: list[RemovedRange],
) -> None:
    pad = config.edge_padding_sec
    min_silence = config.min_silence_sec

    if words and words[0].start > min_silence:
        into.append(
            RemovedRange(
                start=0.0,
                end=max(0.0, words[0].start - pad),
                reason="silence",
            )
        )
    for i in range(len(words) - 1):
        gap = words[i + 1].start - words[i].end
        if gap >= min_silence:
            start = words[i].end + pad
            end = words[i + 1].start - pad
            if end > start:
                into.append(RemovedRange(start=start, end=end, reason="silence"))
    if words and duration_sec - words[-1].end > min_silence:
        into.append(
            RemovedRange(
                start=min(duration_sec, words[-1].end + pad),
                end=duration_sec,
                reason="silence",
            )
        )


def _is_single_word_filler(text: str, rules: list[FillerRule]) -> bool:
    normalised = text.strip().lower()
    if not normalised:
        return False
    return any(rule.pattern.match(normalised) for rule in rules)


def _mark_multi_word_fillers(
    words: list[TranscribedWord],
    rules: list[FillerRule],
    removed: list[RemovedRange],
    skip_indices: set[int],
) -> None:
    multi_rules = [rule for rule in rules if rule.multi_word]
    if not multi_rules:
        return
    n = len(words)
    for i in range(n):
        if i in skip_indices:
            continue
        for rule in multi_rules:
            expected_word_count = rule.word_count
            if i + expected_word_count > n:
                continue
            candidate_words = words[i : i + expected_word_count]
            phrase = " ".join(w.word for w in candidate_words).strip().lower()
            if rule.pattern.match(phrase):
                removed.append(
                    RemovedRange(
                        start=candidate_words[0].start,
                        end=candidate_words[-1].end,
                        reason=f"filler:{rule.word}",
                    )
                )
                for offset in range(expected_word_count):
                    skip_indices.add(i + offset)
                break


def dump_yaml_config_to_dict() -> dict[str, Any]:
    cfg = load_config()
    return {
        "silence": {
            "min_silence_sec": cfg.silence.min_silence_sec,
            "edge_padding_sec": cfg.silence.edge_padding_sec,
            "rms_threshold_db": cfg.silence.rms_threshold_db,
        },
        "fillers": [
            {"word": rule.word, "pattern": rule.pattern.pattern, "multi_word": rule.multi_word}
            for rule in cfg.fillers
        ],
    }
