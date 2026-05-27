"""LLM providers — hot-plug точка под новые LLM backends.

Регистрация провайдеров — явный side-effect при импорте пакета. Factory
классы лежат в соседних модулях, регистрация — здесь, в одной точке
(как в ``services/vision/__init__.py``): упрощает grep и исключает
гонки порядка импортов.

Использование: ``services.llm_client.build_llm(provider, model)`` и
``build_llm_for_tier(tier, cfg, provider_override)`` читают из
``PROVIDER_REGISTRY``.
"""

from videomaker.services.llm_providers.claude_factory import ClaudeProviderFactory
from videomaker.services.llm_providers.gemini_factory import GeminiProviderFactory
from videomaker.services.llm_providers.openai_factory import OpenAIProviderFactory
from videomaker.services.llm_providers.registry import (
    PROVIDER_REGISTRY,
    LLMProviderFactory,
    get_llm_provider,
    register_llm_provider,
)
from videomaker.services.llm_providers.zhipu_factory import ZhipuProviderFactory

# Регистрация встроенных провайдеров. Делается здесь единственной точкой —
# тот же паттерн что в services/vision/__init__.py.
register_llm_provider(GeminiProviderFactory())
register_llm_provider(ClaudeProviderFactory())
register_llm_provider(OpenAIProviderFactory())
register_llm_provider(ZhipuProviderFactory())


__all__ = [
    "PROVIDER_REGISTRY",
    "ClaudeProviderFactory",
    "GeminiProviderFactory",
    "LLMProviderFactory",
    "OpenAIProviderFactory",
    "ZhipuProviderFactory",
    "get_llm_provider",
    "register_llm_provider",
]
