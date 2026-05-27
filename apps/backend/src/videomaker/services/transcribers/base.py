"""Protocol для транскрайберов + общие типы результатов.

Все бэкенды (mlx-whisper, Deepgram) возвращают один и тот же
pydantic-моделированный TranscriptResult с word-level timestamps.
"""

from __future__ import annotations

from collections.abc import Sequence
from itertools import pairwise
from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field, field_validator

FILLER_LEXICON: frozenset[str] = frozenset(
    {
        # Русские филлеры и паразиты
        "эм",
        "эмм",
        "эмэ",
        "ам",
        "амм",
        "аа",
        "ээ",
        "мм",
        "ммм",
        "ну",
        "нуу",
        "вот",
        "типа",
        "короче",
        "блин",
        "э",
        "а",
        # Английские filler words (Deepgram detects с filler_words=true)
        "uh",
        "uhh",
        "um",
        "umm",
        "uhm",
        "hm",
        "hmm",
        "mhm",
        "mhmm",
        "mm",
        "mmm",
        "eh",
        "err",
        "erm",
    }
)


def normalise_for_filler_check(word: str) -> str:
    """Нормализация слова для лексической сверки с `FILLER_LEXICON`.

    Снимает пунктуацию по краям и приводит к lower-case, чтобы "эм,"
    и "Эм" оба попадали в проверку.
    """

    return word.strip().strip(".,!?;:…—-\"'«»()[]").lower()


def is_lexical_filler(word: str) -> bool:
    """True если слово из `FILLER_LEXICON` (после нормализации)."""

    return normalise_for_filler_check(word) in FILLER_LEXICON


class TranscribedWord(BaseModel):
    word: str
    start: float = Field(ge=0.0)
    end: float = Field(ge=0.0)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    is_filler: bool = False

    @field_validator("end")
    @classmethod
    def end_after_start(cls, end: float, info: object) -> float:
        values = getattr(info, "data", {}) if info is not None else {}
        start = values.get("start", 0.0)
        if end < start:
            raise ValueError(f"end {end} must be >= start {start}")
        return end


class TranscribedSegment(BaseModel):
    text: str
    start: float = Field(ge=0.0)
    end: float = Field(ge=0.0)
    words: list[TranscribedWord] = Field(default_factory=list)


class TranscriptResult(BaseModel):
    transcriber: str
    model: str
    language: str
    duration_sec: float = Field(ge=0.0)
    segments: list[TranscribedSegment] = Field(default_factory=list)
    words: list[TranscribedWord] = Field(default_factory=list)
    raw_metadata: dict[str, object] = Field(default_factory=dict)

    @property
    def full_text(self) -> str:
        return " ".join(seg.text.strip() for seg in self.segments if seg.text.strip())


@runtime_checkable
class Transcriber(Protocol):
    """Контракт для всех STT-бэкендов.

    `language=None` означает auto-detect — бэкенд обязан определить язык
    и вернуть его в `TranscriptResult.language` (ISO 639-1 код).
    """

    name: str
    model: str

    async def transcribe(
        self,
        audio_path: Path,
        *,
        language: str | None = None,
    ) -> TranscriptResult:
        ...


class TranscriberError(RuntimeError):
    """Базовая ошибка транскрибации (сетевая, формат, авторизация и т.д.)."""


def merge_words_into_segments(
    words: Sequence[TranscribedWord],
    *,
    max_gap_sec: float = 0.75,
    max_segment_sec: float = 20.0,
) -> list[TranscribedSegment]:
    """Группирует слова в сегменты по паузам ≥ max_gap_sec или длине ≥ max_segment_sec.

    Используется только транскрайберами, которые не возвращают сегменты сами.
    """

    if not words:
        return []

    segments: list[TranscribedSegment] = []
    current: list[TranscribedWord] = [words[0]]
    for prev, curr in pairwise(words):
        gap = curr.start - prev.end
        span = curr.end - current[0].start
        if gap >= max_gap_sec or span >= max_segment_sec:
            segments.append(_segment_from_words(current))
            current = [curr]
        else:
            current.append(curr)
    segments.append(_segment_from_words(current))
    return segments


def _segment_from_words(words: Sequence[TranscribedWord]) -> TranscribedSegment:
    text = " ".join(w.word for w in words)
    return TranscribedSegment(
        text=text,
        start=words[0].start,
        end=words[-1].end,
        words=list(words),
    )
