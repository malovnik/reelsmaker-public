"""Unit-тесты построения Kartoziya-промптов."""

from __future__ import annotations

from videomaker.services.prompts import (
    CANVAS_BUILDER_PROMPT,
    DEFAULT_PROMPTS,
    DRAMATIC_IRONY_SCANNER_PROMPT,
    HOOK_HUNTER_PROMPT,
    KARTOZIYA_SYSTEM_PROMPT,
    LEGACY_PROMPT_KEYS,
    REDUCE_RANK_PROMPT,
    STORY_DOCTOR_PROMPT,
    PromptKey,
    build_context_header,
)


def test_kartoziya_system_prompt_non_empty() -> None:
    assert KARTOZIYA_SYSTEM_PROMPT
    assert "Картозии" in KARTOZIYA_SYSTEM_PROMPT
    assert "book-end" in KARTOZIYA_SYSTEM_PROMPT
    assert "JSON" in KARTOZIYA_SYSTEM_PROMPT


def test_context_header_legacy_compat_includes_aspect() -> None:
    """target_aspect остался опциональным для обратной совместимости."""
    header = build_context_header(
        source_duration_sec=125.5,
        target_aspect="9:16",
        transcriber="mlx_whisper",
        llm_model="gemini-2.5-flash",
    )
    assert "2 мин" in header
    assert "9:16" in header
    assert "mlx_whisper" in header


def test_context_header_kartoziya_omits_aspect_adds_speakers() -> None:
    header = build_context_header(
        source_duration_sec=3600.0,
        transcriber="deepgram",
        llm_model="gemini-2.5-pro",
        speakers_count=3,
        language="ru",
    )
    assert "Целевой формат" not in header
    assert "Спикеров: 3" in header
    assert "Язык: ru" in header


def test_context_header_kartoziya_no_speakers_marks_unknown() -> None:
    header = build_context_header(
        source_duration_sec=600.0,
        transcriber="mlx_whisper",
        llm_model="gemini-2.5-flash",
    )
    assert "Спикеров: не определено" in header


def test_default_prompts_cover_kartoziya_keys() -> None:
    required = {
        PromptKey.translate_adaptive_ru,
        PromptKey.canvas_builder,
        PromptKey.compression,
        PromptKey.hook_hunter,
        PromptKey.emotional_peak_finder,
        PromptKey.humor_specialist,
        PromptKey.dramatic_irony_scanner,
        PromptKey.thesis_extractor,
        PromptKey.motif_tracker,
        PromptKey.reduce_rank,
        PromptKey.story_doctor,
        PromptKey.story_doctor_travel,
        PromptKey.rhythm_check,
        PromptKey.variants_generator,
        PromptKey.closure_check,
    }
    assert required == set(DEFAULT_PROMPTS.keys())


def test_all_prompts_are_non_empty_strings() -> None:
    for key, content in DEFAULT_PROMPTS.items():
        assert isinstance(content, str), f"{key} is not str"
        assert content.strip(), f"{key} is blank"


def test_canvas_builder_prompt_declares_schema() -> None:
    assert "central_theme" in CANVAS_BUILDER_PROMPT
    assert "candidate_moments" in CANVAS_BUILDER_PROMPT
    assert "chronological_spine" in CANVAS_BUILDER_PROMPT


def test_hook_hunter_prompt_defines_hook_types() -> None:
    assert "paradox" in HOOK_HUNTER_PROMPT
    assert "shock_fact" in HOOK_HUNTER_PROMPT


def test_dramatic_irony_scanner_mentions_foreshadowing() -> None:
    assert "foreshadowing" in DRAMATIC_IRONY_SCANNER_PROMPT


def test_reduce_rank_defines_categories() -> None:
    for cat in [
        "hook_candidate", "peak_candidate", "payoff_candidate",
        "development_material", "cutaway_material",
    ]:
        assert cat in REDUCE_RANK_PROMPT


def test_story_doctor_mentions_bookend() -> None:
    assert "bookend" in STORY_DOCTOR_PROMPT.lower()
    assert "hook" in STORY_DOCTOR_PROMPT.lower()
    assert "payoff" in STORY_DOCTOR_PROMPT.lower()


def test_prompt_key_enum_values_are_unique() -> None:
    values = [member.value for member in PromptKey]
    assert len(values) == len(set(values))


def test_legacy_prompt_keys_expose_removed() -> None:
    """Канарейка для prompt_store cleanup — ключи перечислены явно."""
    assert "pass1_explicit" in LEGACY_PROMPT_KEYS
    assert "pass2_implicit" in LEGACY_PROMPT_KEYS
    assert "pass3_virtual_cut" in LEGACY_PROMPT_KEYS
    assert "pass1_reduce" in LEGACY_PROMPT_KEYS
    assert "pass2_reduce" in LEGACY_PROMPT_KEYS
    # Удалённые ключи не должны присутствовать в активных.
    active = {m.value for m in PromptKey}
    assert LEGACY_PROMPT_KEYS.isdisjoint(active)
