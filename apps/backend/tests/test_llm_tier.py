"""Тесты build_llm_for_tier — tiered Gemini clients для Kartoziya-пайплайна."""

from __future__ import annotations

import pytest

from videomaker.core.config import Settings
from videomaker.services.llm_client import (
    GeminiClient,
    LLMError,
    build_llm_for_tier,
)


def _settings(api_key: str | None = "test-key") -> Settings:
    return Settings(gemini_api_key=api_key)


def test_build_pro_tier_uses_lite_model() -> None:
    client = build_llm_for_tier("pro", _settings())
    assert isinstance(client, GeminiClient)
    assert "flash-lite" in client.model


def test_build_flash_tier_uses_lite_model() -> None:
    client = build_llm_for_tier("flash", _settings())
    assert isinstance(client, GeminiClient)
    assert "flash-lite" in client.model


def test_build_flash_lite_tier_uses_lite_model() -> None:
    client = build_llm_for_tier("flash_lite", _settings())
    assert isinstance(client, GeminiClient)
    assert "flash-lite" in client.model


def test_build_without_api_key_raises() -> None:
    with pytest.raises(LLMError, match="GEMINI_API_KEY missing"):
        build_llm_for_tier("flash", _settings(api_key=None))
