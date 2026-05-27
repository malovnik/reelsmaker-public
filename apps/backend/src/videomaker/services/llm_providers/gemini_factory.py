"""Gemini provider factory — регистрируется в llm_providers/__init__.py.

Tier-матрица для Gemini живёт в ``_resolve_tier_models(cfg)`` —
runtime_settings override (PerformanceSettings.llm_tier_profile)
выбирает fast или legacy (оба — Flash-Lite варианты). Фабрика
просто делегирует туда.
"""

from __future__ import annotations

from videomaker.core.config import Settings
from videomaker.services.llm_client import (
    GeminiClient,
    LLMClient,
    LLMError,
    LLMTier,
    _resolve_tier_models,
)


class GeminiProviderFactory:
    name = "gemini"

    def build_client(self, *, settings: Settings, model: str) -> LLMClient:
        if not settings.gemini_api_key:
            raise LLMError("GEMINI_API_KEY missing")
        return GeminiClient(api_key=settings.gemini_api_key, model=model)

    def tier_model(self, settings: Settings, tier: LLMTier) -> str:
        return _resolve_tier_models(settings)[tier]
