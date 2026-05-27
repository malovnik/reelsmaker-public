"""Unit-тесты Canvas pydantic-моделей + to_llm_context сериализация."""

from __future__ import annotations

from videomaker.models.canvas import (
    CanvasCandidateMoment,
    CanvasMotif,
    CanvasSpeaker,
    CanvasTheme,
    CanvasToneRange,
    CompressedChunk,
    EmotionalPeak,
    NotableQuote,
    ProjectCanvas,
)


def _sample_canvas() -> ProjectCanvas:
    return ProjectCanvas(
        central_theme="Трансформация через потерю",
        themes=[
            CanvasTheme(
                id="t1", label="страх потери", strength=0.9,
                first_mention_sec=10, last_mention_sec=3600,
            ),
            CanvasTheme(
                id="t2", label="возрождение", strength=0.7,
                first_mention_sec=1200, last_mention_sec=3580,
            ),
            CanvasTheme(
                id="t3", label="отвлекающая тема", strength=0.3,
                first_mention_sec=500, last_mention_sec=600,
                status="excluded",
            ),
        ],
        motifs=[
            CanvasMotif(id="m1", label="старый дом", occurrences_sec=[45, 1800, 3500]),
        ],
        speakers=[
            CanvasSpeaker(id="speaker_0", role="ведущий", importance=0.9),
            CanvasSpeaker(
                id="speaker_1", role="гость", importance=0.8, included=False,
            ),
        ],
        candidate_moments=[
            CanvasCandidateMoment(
                id="mo1", start=45, end=72, one_liner="Я не искал любви",
                kind="hook", strength=0.88, status="pinned_required",
            ),
        ],
        tone_map=[
            CanvasToneRange(sec_range=(0, 300), mood="setup", intensity=0.4),
        ],
        chronological_spine=["0-60s: intro", "60-300s: setup"],
    )


def test_starred_theme_ids() -> None:
    canvas = _sample_canvas()
    canvas.themes[0].status = "starred"
    assert canvas.starred_theme_ids == ["t1"]


def test_excluded_theme_ids() -> None:
    assert _sample_canvas().excluded_theme_ids == ["t3"]


def test_excluded_speaker_ids() -> None:
    assert _sample_canvas().excluded_speaker_ids == ["speaker_1"]


def test_pinned_moment_ids() -> None:
    assert _sample_canvas().pinned_moment_ids == ["mo1"]


def test_to_llm_context_includes_central_theme() -> None:
    assert "Трансформация через потерю" in _sample_canvas().to_llm_context()


def test_to_llm_context_omits_excluded_themes() -> None:
    ctx = _sample_canvas().to_llm_context()
    assert "отвлекающая тема" not in ctx
    assert "страх потери" in ctx


def test_to_llm_context_marks_starred_with_star() -> None:
    canvas = _sample_canvas()
    canvas.themes[0].status = "starred"
    assert "★" in canvas.to_llm_context()


def test_to_llm_context_omits_excluded_speakers() -> None:
    ctx = _sample_canvas().to_llm_context()
    assert "speaker_0" in ctx
    assert "speaker_1 (" not in ctx


def test_to_llm_context_shows_pinned_moments() -> None:
    ctx = _sample_canvas().to_llm_context()
    assert "PINNED moments" in ctx
    assert "Я не искал любви" in ctx


def test_canvas_custom_direction_appears_in_context() -> None:
    canvas = _sample_canvas()
    canvas.custom_direction = "Фокус на отношения отца и сына"
    ctx = canvas.to_llm_context()
    assert "User direction" in ctx
    assert "отца и сына" in ctx


def test_empty_canvas_to_llm_context() -> None:
    assert "PROJECT CANVAS" in ProjectCanvas().to_llm_context()


def test_compressed_chunk_synopsis_fragment() -> None:
    chunk = CompressedChunk(
        chunk_index=2,
        time_range_sec=(120.0, 180.0),
        summary="Герой рассказывает о потере.",
        key_speakers=["speaker_0"],
        notable_quotes=[
            NotableQuote(quote="Всё было зря", sec=145.0, speaker="speaker_0"),
        ],
        emotional_peaks=[
            EmotionalPeak(sec=160.0, kind="confession", note="переломный момент"),
        ],
    )
    rendered = chunk.to_synopsis_fragment()
    assert "Chunk 2" in rendered
    assert "120.0" in rendered and "180.0" in rendered
    assert "Герой рассказывает" in rendered
    assert "Всё было зря" in rendered
    assert "confession" in rendered
