"""LLM client facade — re-exports from services/llm_clients/ package.

Legacy-compat: все существующие ``from videomaker.services.llm_client import X``
импорты продолжают работать. Phase 5.3 реальное разделение на
``services/llm_clients/{base,gemini,claude,openai,zhipu,retry,json_parser,
tier_resolver}.py``. Phase 6.2 вытащил общий ``_BaseLLMClient`` с lazy-init
шаблоном — убрал 4× дубликат ``_get_client()``.

``build_llm`` и ``build_llm_for_tier`` остаются здесь: они зависят от
``services.llm_providers`` (PROVIDER_REGISTRY) и держать их тут избегает
циклического импорта llm_clients ↔ llm_providers.
"""

from __future__ import annotations

from videomaker.core.config import Settings, get_settings
from videomaker.services.llm_clients import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    ClaudeClient,
    GeminiClient,
    GLMClient,
    LLMClient,
    LLMError,
    LLMResponse,
    LLMTier,
    OpenAIClient,
    _BaseLLMClient,
    _is_retryable,
    _resolve_tier_models,
    _retry,
    _tier_profiles,
    _try_read_tier_profile,
    parse_json_response,
)


def build_llm(provider: str, model: str, settings: Settings | None = None) -> LLMClient:
    """Возвращает LLM client через PROVIDER_REGISTRY.

    Поддерживаемые provider — смотри ``services.llm_providers.PROVIDER_REGISTRY``.
    Встроенные: ``gemini``, ``anthropic``, ``openai``, ``zhipu``. Новые
    регистрируются через ``register_llm_provider(factory)`` (см.
    ``services/llm_providers/__init__.py``).
    """

    # Side-effect импорта — гарантирует что встроенные провайдеры зарегистрированы.
    from videomaker.services import llm_providers  # noqa: F401
    from videomaker.services.llm_providers.registry import get_llm_provider

    cfg = settings or get_settings()
    try:
        factory = get_llm_provider(provider)
    except ValueError as exc:
        raise LLMError(str(exc)) from exc
    return factory.build_client(settings=cfg, model=model)


def build_llm_for_tier(
    tier: LLMTier,
    settings: Settings | None = None,
    provider_override: str | None = None,
) -> LLMClient:
    """Возвращает LLM client для указанного tier.

    Kartoziya-пайплайн использует три уровня моделей:
      * `pro` — тяжёлая аналитика (Canvas Builder, Story Doctor, Variants).
      * `flash` — средние задачи (Reducer, Rhythm Check, Compression).
      * `flash_lite` — массовые параллельные вызовы (6 extraction-агентов × N chunks).

    Runtime override: PerformanceSettings.llm_tier_profile позволяет пользователю
    без рестарта переключать матрицу fast|legacy (оба профиля используют
    только Flash-Lite варианты — более дорогие модели запрещены по
    user constraint). Если профиль не задан (pending startup / cold cache) —
    резолвер fallback'ится на fast (см. tier_resolver._resolve_tier_models).

    ``provider_override``: если задан — вся tier-матрица идёт через указанного
    провайдера. Дефолт (``None``) резолвится в ``"gemini"``. Для ``"zhipu"``
    все три tier'а мапятся на ``Settings.zhipu_{pro,flash,flash_lite}_model``.
    Hard switch задаётся из UI через ``PerformanceSettings.pipeline_llm_provider``.

    Разрешение tier → model и валидация API-ключа делегированы фабрике
    провайдера (см. ``services/llm_providers/{gemini,zhipu,...}_factory.py``).
    """

    from videomaker.services import llm_providers  # noqa: F401
    from videomaker.services.llm_providers.registry import get_llm_provider

    cfg = settings or get_settings()
    provider_name = provider_override or "gemini"
    try:
        factory = get_llm_provider(provider_name)
    except ValueError as exc:
        raise LLMError(str(exc)) from exc
    model = factory.tier_model(cfg, tier)
    return factory.build_client(settings=cfg, model=model)


__all__ = [
    "DEFAULT_MAX_OUTPUT_TOKENS",
    "ClaudeClient",
    "GLMClient",
    "GeminiClient",
    "LLMClient",
    "LLMError",
    "LLMResponse",
    "LLMTier",
    "OpenAIClient",
    "_BaseLLMClient",
    "_is_retryable",
    "_resolve_tier_models",
    "_retry",
    "_tier_profiles",
    "_try_read_tier_profile",
    "build_llm",
    "build_llm_for_tier",
    "parse_json_response",
]
