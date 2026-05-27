"""Unit-тесты ASS subtitle generator."""

from __future__ import annotations

from videomaker.services.subtitles import (
    SubtitleReelSpec,
    SubtitleStyle,
    _fmt_time,
    build_ass_for_reel,
)
from videomaker.services.transcribers.base import TranscribedWord


def test_fmt_time_rounds_down_correctly() -> None:
    assert _fmt_time(0) == "0:00:00.00"
    assert _fmt_time(61.25) == "0:01:01.25"
    assert _fmt_time(3600 + 125.5) == "1:02:05.50"


def test_build_ass_includes_header_and_styles() -> None:
    words = [
        TranscribedWord(word="Привет", start=0.1, end=0.5),
        TranscribedWord(word="друзья", start=0.55, end=1.0),
        TranscribedWord(word="важное", start=5.0, end=5.6),
    ]
    spec = SubtitleReelSpec(
        reel_id="r1",
        segments=[(0.0, 1.2), (4.8, 5.8)],
        words=words,
        style=SubtitleStyle(size=48, outline=2),
    )
    ass = build_ass_for_reel(spec)
    assert "[Script Info]" in ass
    assert "[V4+ Styles]" in ass
    assert "[Events]" in ass
    assert "Dialogue:" in ass
    assert "Привет друзья" in ass or "Привет" in ass
    assert "важное" in ass


def test_build_ass_maps_timestamps_to_reel_local_time() -> None:
    words = [
        TranscribedWord(word="первое", start=10.0, end=10.5),
        TranscribedWord(word="второе", start=25.0, end=25.5),
    ]
    spec = SubtitleReelSpec(
        reel_id="r1",
        segments=[(10.0, 11.0), (25.0, 26.0)],
        words=words,
    )
    ass = build_ass_for_reel(spec)
    lines = [line for line in ass.splitlines() if line.startswith("Dialogue:")]
    assert len(lines) == 2
    # Первая реплика начинается в ~0.0, вторая — в ~1.0 (после первого сегмента)
    assert "0:00:00.00" in lines[0]
    assert "0:00:01" in lines[1]


def test_empty_spec_still_valid_ass() -> None:
    spec = SubtitleReelSpec(reel_id="r0", segments=[], words=[])
    ass = build_ass_for_reel(spec)
    assert "[Events]" in ass
    assert "Dialogue:" not in ass
