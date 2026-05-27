"""Claude (Anthropic) provider factory.

У Claude нет Kartoziya-tier-матрицы (pipeline официально на Gemini/Zhipu),
но Protocol требует ``tier_model`` — возвращаем ``anthropic_default_model``
для всех трёх tier'ов. Это позволяет явно собрать клиент через
``build_llm_for_tier`` если кто-то в будущем решит гонять pipeline
на Claude (и заодно даёт осмысленный ответ вместо NotImplementedError).
"""

from __future__ import annotations

from videomaker.core.config import Settings
from videomaker.services.llm_client import ClaudeClient, LLMClient, LLMError, LLMTier


class ClaudeProviderFactory:
    name = "anthropic"

    def build_client(self, *, settings: Settings, model: str) -> LLMClient:
        if not settings.anthropic_api_key:
            raise LLMError("ANTHROPIC_API_KEY missing")
        return ClaudeClient(api_key=settings.anthropic_api_key, model=model)

    def tier_model(self, settings: Settings, tier: LLMTier) -> str:
        _ = tier
        return settings.anthropic_default_model
