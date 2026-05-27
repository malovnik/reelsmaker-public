"""Smoke-тесты auto-detect VisionProfile."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from videomaker.models.job import VisionProfile
from videomaker.services.profile_detector import (
    compute_silence_ratio,
    detect_profile,
    estimate_face_coverage,
)
from videomaker.services.transcribers.base import (
    TranscribedSegment,
    TranscribedWord,
    TranscriptResult,
)


def _make_transcript(
    *,
    words_per_minute: float,
    duration_sec: float,
    word_len_sec: float = 0.3,
) -> TranscriptResult:
    """Сгенерировать TranscriptResult с заданным WPM. Без word-gap-ов для
    контроля silence: gap = (duration / word_count) - word_len.
    """
    word_count = round(words_per_minute * duration_sec / 60.0)
    if word_count < 1:
        word_count = 1
    gap = (duration_sec - word_count * word_len_sec) / word_count
    words = []
    for i in range(word_count):
        start = i * (word_len_sec + gap)
        words.append(
            TranscribedWord(word=f"w{i}", start=start, end=start + word_len_sec)
        )
    return TranscriptResult(
        transcriber="mlx_whisper",
        model="v1",
        language="en",
        duration_sec=duration_sec,
        segments=[
            TranscribedSegment(
                text=" ".join(w.word for w in words),
                start=0.0,
                end=duration_sec,
                words=words,
            )
        ],
        words=words,
    )


def test_silence_ratio_zero_duration() -> None:
    t = TranscriptResult(
        transcriber="mlx_whisper",
        model="v1",
        language="en",
        duration_sec=0.0,
        segments=[],
        words=[],
    )
    assert compute_silence_ratio(t) == 0.0


def test_silence_ratio_basic() -> None:
    t = _make_transcript(words_per_minute=10, duration_sec=60.0)
    silence = compute_silence_ratio(t)
    # 10 слов × 0.3s = 3s speech / 60s total → 95% silence
    assert silence > 0.9


def test_detect_low_wpm_with_faces_is_fashion() -> None:
    t = _make_transcript(words_per_minute=10, duration_sec=60.0)
    sug = detect_profile(t, face_coverage=0.8, vision_frames_sampled=200)
    assert sug.profile == VisionProfile.fashion
    assert sug.confidence > 0.3
    assert any("лица" in r for r in sug.reasons)


def test_detect_low_wpm_without_faces_is_travel() -> None:
    t = _make_transcript(words_per_minute=10, duration_sec=60.0)
    sug = detect_profile(t, face_coverage=0.1, vision_frames_sampled=200)
    assert sug.profile == VisionProfile.travel


def test_detect_low_wpm_no_vision_is_travel() -> None:
    t = _make_transcript(words_per_minute=10, duration_sec=60.0)
    sug = detect_profile(t, face_coverage=None)
    assert sug.profile == VisionProfile.travel
    assert sug.metrics.face_coverage is None


def test_detect_high_wpm_is_talking_head() -> None:
    t = _make_transcript(words_per_minute=180, duration_sec=60.0, word_len_sec=0.25)
    sug = detect_profile(t, face_coverage=0.8)
    assert sug.profile == VisionProfile.talking_head


def test_detect_middle_wpm_fallback_is_talking_head() -> None:
    t = _make_transcript(words_per_minute=80, duration_sec=60.0)
    sug = detect_profile(t, face_coverage=0.4)
    assert sug.profile == VisionProfile.talking_head
    assert sug.confidence == pytest.approx(0.3, abs=0.01)


def test_estimate_face_coverage_missing_cache(tmp_path: Path) -> None:
    est = estimate_face_coverage(tmp_path, "abc123")
    assert est.coverage is None
    assert est.frames_sampled == 0


def test_estimate_face_coverage_reads_jsonl(tmp_path: Path) -> None:
    vid_dir = tmp_path / "abcdef"
    vid_dir.mkdir()
    rows = [
        {
            "key": "query:1.000:xx",
            "value": {"prompt": "Is a person visible?", "answer": "yes"},
        },
        {
            "key": "query:2.000:xx",
            "value": {"prompt": "Is a person visible?", "answer": "no"},
        },
        {
            "key": "query:3.000:xx",
            "value": {"prompt": "Is a person visible?", "answer": "yes"},
        },
        # Нерелевантные query — должны быть пропущены
        {
            "key": "query:4.000:xx",
            "value": {"prompt": "Что на заднем плане?", "answer": "стена"},
        },
        # caption вместо query — должен быть пропущен
        {"key": "caption:5.000:xx", "value": {"caption": "A person."}},
    ]
    jsonl_path = vid_dir / "results.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")

    est = estimate_face_coverage(tmp_path, "abcdef")
    assert est.frames_sampled == 3
    assert est.coverage == pytest.approx(2 / 3, abs=0.01)


def test_metrics_populated_in_suggestion() -> None:
    t = _make_transcript(words_per_minute=10, duration_sec=60.0)
    sug = detect_profile(t, face_coverage=0.3, vision_frames_sampled=500)
    assert sug.metrics.wpm > 0
    assert sug.metrics.silence_ratio > 0
    assert sug.metrics.face_coverage == 0.3
    assert sug.metrics.vision_frames_sampled == 500
    assert sug.metrics.word_count > 0
