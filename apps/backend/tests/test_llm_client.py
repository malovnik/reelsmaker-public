"""Unit-тесты LLM client (утилиты, без сетевых вызовов)."""

from __future__ import annotations

import pytest

from videomaker.services.llm_client import LLMError, build_llm, parse_json_response


def test_parse_plain_json() -> None:
    assert parse_json_response('{"a": 1}') == {"a": 1}
    assert parse_json_response("[1, 2, 3]") == [1, 2, 3]


def test_parse_markdown_wrapped_json() -> None:
    wrapped = "Here it is:\n```json\n{\"x\": 42, \"items\": [1,2]}\n```\nDone."
    assert parse_json_response(wrapped) == {"x": 42, "items": [1, 2]}


def test_parse_handles_prefix_suffix_noise() -> None:
    text = "reasoning...\n\n[{\"hook\":\"Тест\"},{\"hook\":\"Второй\"}]\n// end"
    result = parse_json_response(text)
    assert isinstance(result, list)
    assert result[0]["hook"] == "Тест"


def test_parse_repairs_truncated_array() -> None:
    # Обрезано посреди строкового поля — как если Gemini уперся в max_tokens
    truncated = (
        '[\n  {\n    "start": 117.78,\n    "end": 122.9,\n    "text": "Hello world",'
        '\n    "angle": "Восторг от мгновенного и правильного'
    )
    result = parse_json_response(truncated)
    assert isinstance(result, list)
    assert result[0]["start"] == 117.78
    assert result[0]["angle"].startswith("Восторг")


def test_parse_repairs_truncated_object() -> None:
    truncated = (
        '{\n  "reels": [\n    {\n      "reel_id": "r1",\n      "hook": "AI-дизайн",'
        '\n      "predicted_duration_sec": 41.64,\n      "target_audience": "Дизайнеры и разработчики, ищущ'
    )
    result = parse_json_response(truncated)
    assert isinstance(result, dict)
    assert result["reels"][0]["reel_id"] == "r1"


def test_parse_rejects_garbage() -> None:
    with pytest.raises(LLMError):
        parse_json_response("nothing here")


def test_parse_rejects_empty() -> None:
    with pytest.raises(LLMError):
        parse_json_response("   \n  ")


def test_build_llm_fails_without_key() -> None:
    with pytest.raises(LLMError):
        build_llm("gemini", "gemini-2.5-flash")
    with pytest.raises(LLMError):
        build_llm("anthropic", "claude-sonnet-4-5-20250929")
    with pytest.raises(LLMError):
        build_llm("openai", "gpt-5")


def test_build_llm_unknown_provider() -> None:
    with pytest.raises(LLMError):
        build_llm("grok", "any-model")
