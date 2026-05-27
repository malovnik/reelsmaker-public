"""Unit-тесты RAG chunker."""

from __future__ import annotations

import pytest

from videomaker.services.chunker import (
    ChunkingPolicy,
    chunk_transcript,
    count_tokens,
    merge_overlapping_timestamps,
)
from videomaker.services.transcribers.base import (
    TranscribedWord,
    TranscriptResult,
    merge_words_into_segments,
)


def _make_transcript(word_count: int, duration_per_word: float = 0.5) -> TranscriptResult:
    words = [
        TranscribedWord(
            word=f"слово{i}",
            start=i * duration_per_word,
            end=(i + 1) * duration_per_word - 0.05,
        )
        for i in range(word_count)
    ]
    segments = merge_words_into_segments(words, max_gap_sec=2.0, max_segment_sec=30.0)
    return TranscriptResult(
        transcriber="test",
        model="test",
        language="ru",
        duration_sec=word_count * duration_per_word,
        segments=segments,
        words=words,
    )


def test_count_tokens_basic() -> None:
    assert count_tokens("") == 0
    assert count_tokens("hello world") > 0
    assert count_tokens("Привет мир") > count_tokens("Hi")


def test_small_transcript_stays_single_chunk() -> None:
    transcript = _make_transcript(50)
    policy = ChunkingPolicy(threshold_tokens=20000, window_tokens=15000, overlap_tokens=1500)
    chunks = chunk_transcript(transcript, policy)
    assert len(chunks) == 1
    assert chunks[0].start_sec == 0.0
    assert chunks[0].end_sec == transcript.duration_sec - 0.05


def test_long_transcript_splits_with_overlap() -> None:
    transcript = _make_transcript(400)
    policy = ChunkingPolicy(threshold_tokens=400, window_tokens=300, overlap_tokens=80)
    chunks = chunk_transcript(transcript, policy)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert chunk.token_count <= 350
        assert chunk.end_sec > chunk.start_sec


def test_empty_transcript_returns_empty() -> None:
    transcript = TranscriptResult(
        transcriber="t", model="m", language="ru", duration_sec=0.0, segments=[], words=[]
    )
    policy = ChunkingPolicy(threshold_tokens=200, window_tokens=100, overlap_tokens=20)
    assert chunk_transcript(transcript, policy) == []


def test_policy_validation() -> None:
    bad = ChunkingPolicy(threshold_tokens=50, window_tokens=100, overlap_tokens=20)
    with pytest.raises(ValueError):
        bad.validate()
    bad2 = ChunkingPolicy(threshold_tokens=100, window_tokens=50, overlap_tokens=60)
    with pytest.raises(ValueError):
        bad2.validate()


def test_merge_overlapping_timestamps_dedups_close_starts() -> None:
    items = [
        {"start": 5.0, "end": 10.0, "id": "a"},
        {"start": 5.3, "end": 12.0, "id": "b"},
        {"start": 20.0, "end": 25.0, "id": "c"},
    ]
    merged = merge_overlapping_timestamps(items, start_key="start", tolerance_sec=1.0)
    assert len(merged) == 2
    ids = [item["id"] for item in merged]
    assert ids == ["a", "c"]
