"""Unit-тесты transcribers — только на уровне контракта и merge helper."""

from __future__ import annotations

import pytest

from videomaker.services.transcribers import (
    TranscribedWord,
    Transcriber,
    TranscriberError,
    build_transcriber,
    merge_words_into_segments,
)


def test_factory_mlx_whisper_available() -> None:
    t = build_transcriber("mlx_whisper")
    assert isinstance(t, Transcriber)
    assert t.name == "mlx_whisper"


def test_factory_deepgram_without_key_fails() -> None:
    with pytest.raises(TranscriberError):
        build_transcriber("deepgram")


def test_factory_unknown_name() -> None:
    with pytest.raises(TranscriberError):
        build_transcriber("wav2vec")


def test_merge_words_respects_gap() -> None:
    words = [
        TranscribedWord(word="Привет", start=0.0, end=0.4),
        TranscribedWord(word="друзья", start=0.5, end=1.0),
        TranscribedWord(word="сегодня", start=3.0, end=3.8),
    ]
    segments = merge_words_into_segments(words, max_gap_sec=1.0)
    assert len(segments) == 2
    assert segments[0].text == "Привет друзья"
    assert segments[1].text == "сегодня"


def test_merge_words_respects_max_span() -> None:
    words = [
        TranscribedWord(word=f"слово{i}", start=i * 0.5, end=i * 0.5 + 0.4)
        for i in range(60)
    ]
    segments = merge_words_into_segments(words, max_gap_sec=5.0, max_segment_sec=5.0)
    assert len(segments) > 1
    for seg in segments:
        assert seg.end - seg.start <= 5.5
