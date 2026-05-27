"""OpenAI provider factory.

Как и Claude — pipeline на OpenAI сейчас не запускается, но фабрика
отвечает за конструкцию клиента через единый registry. tier_model
возвращает ``openai_default_model`` (плоско — нет tier-матрицы в конфиге).
"""

from __future__ import annotations

from videomaker.core.config import Settings
from videomaker.services.llm_client import LLMClient, LLMError, LLMTier, OpenAIClient


class OpenAIProviderFactory:
    name = "openai"

    def build_client(self, *, settings: Settings, model: str) -> LLMClient:
        if not settings.openai_api_key:
            raise LLMError("OPENAI_API_KEY missing")
        return OpenAIClient(api_key=settings.openai_api_key, model=model)

    def tier_model(self, settings: Settings, tier: LLMTier) -> str:
        _ = tier
        return settings.openai_default_model
