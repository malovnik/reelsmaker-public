"""Unit-тесты silence_cutter."""

from __future__ import annotations

from videomaker.services.silence_cutter import (
    clean_transcript,
    load_config,
)
from videomaker.services.transcribers.base import (
    TranscribedWord,
    TranscriptResult,
)


def _make_transcript(words: list[tuple[str, float, float]], duration: float) -> TranscriptResult:
    tw = [TranscribedWord(word=text, start=start, end=end) for text, start, end in words]
    return TranscriptResult(
        transcriber="t",
        model="m",
        language="ru",
        duration_sec=duration,
        words=tw,
        segments=[],
    )


def test_load_config_parses_fillers() -> None:
    cfg = load_config()
    assert len(cfg.fillers) >= 10
    assert cfg.silence.min_silence_sec > 0
    assert cfg.silence.rms_threshold_db < 0


def test_clean_transcript_removes_silence_gaps() -> None:
    transcript = _make_transcript(
        [
            ("Привет", 0.1, 0.5),
            ("друзья", 0.55, 1.0),
            # длинная пауза — 5 сек
            ("сегодня", 6.0, 6.7),
            ("важное", 6.75, 7.3),
        ],
        duration=8.0,
    )
    cleaned = clean_transcript(transcript)
    silence_ranges = [r for r in cleaned.removed_ranges if r.reason == "silence"]
    # Пауза между "друзья" (end=1.0) и "сегодня" (start=6.0) должна попасть в silence
    assert any(r.start >= 1.0 and r.end <= 6.0 and r.end - r.start >= 4.5 for r in silence_ranges)
    assert len(cleaned.words) == 4


def test_clean_transcript_removes_single_word_fillers() -> None:
    transcript = _make_transcript(
        [
            ("ну", 0.0, 0.3),
            ("вот", 0.4, 0.7),
            ("ээ", 0.8, 1.1),
            ("важное", 1.2, 1.8),
            ("типа", 1.9, 2.2),
            ("этого", 2.3, 2.7),
        ],
        duration=3.0,
    )
    cleaned = clean_transcript(transcript)
    kept_words = [w.word for w in cleaned.words]
    assert "ну" not in kept_words
    assert "ээ" not in kept_words
    assert "типа" not in kept_words
    assert "важное" in kept_words
    assert "этого" in kept_words
    assert cleaned.stats["filler_count"] >= 3


def test_clean_transcript_handles_multi_word_filler() -> None:
    transcript = _make_transcript(
        [
            ("как", 0.0, 0.3),
            ("бы", 0.4, 0.7),
            ("важное", 0.8, 1.4),
        ],
        duration=2.0,
    )
    cleaned = clean_transcript(transcript)
    kept_words = [w.word for w in cleaned.words]
    # multi-word "как бы" должен удалиться вместе
    assert kept_words == ["важное"]


def test_empty_transcript_returns_empty() -> None:
    transcript = TranscriptResult(
        transcriber="t", model="m", language="ru", duration_sec=0.0, words=[], segments=[]
    )
    cleaned = clean_transcript(transcript)
    assert cleaned.words == []
    assert cleaned.removed_ranges == []
    assert cleaned.stats["kept_words"] == 0
