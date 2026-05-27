"""LLM provider registry — hot-plug точка под новые LLM backends.

Каждый провайдер реализует минимальный Protocol: ``name`` + ``build_client``
(для ``build_llm(provider, model)``) + ``tier_model`` (для
``build_llm_for_tier(tier, ..., provider_override)``).

Архитектурные решения повторяют vision/registry.py: registry хранит только
provider-specific конструкцию; cross-cutting логика (cold-cache fallback
tier-профиля, lifecycle Settings) живёт в call-site'ах ``llm_client``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from videomaker.core.config import Settings

if TYPE_CHECKING:
    from videomaker.services.llm_client import LLMClient, LLMTier


@runtime_checkable
class LLMProviderFactory(Protocol):
    """Контракт фабрики LLM-провайдера.

    ``name`` — ключ в ``PROVIDER_REGISTRY`` и значение для
    ``PerformanceSettings.pipeline_llm_provider``.

    ``build_client`` собирает конкретный клиент под заданную модель и
    валидирует наличие API-ключа/прочих обязательных настроек.

    ``tier_model`` маппит ``LLMTier`` → имя модели для данного провайдера.
    Используется в ``build_llm_for_tier`` когда caller не хочет сам
    разрешать tier → model (та самая логика ``_resolve_tier_models``
    для Gemini + плоские ``zhipu_{pro,flash,flash_lite}_model`` для GLM).
    """

    name: str

    def build_client(self, *, settings: Settings, model: str) -> LLMClient: ...

    def tier_model(self, settings: Settings, tier: LLMTier) -> str: ...


PROVIDER_REGISTRY: dict[str, LLMProviderFactory] = {}


def register_llm_provider(factory: LLMProviderFactory) -> None:
    """Регистрирует провайдера в глобальном реестре.

    Идемпотентна — повторная регистрация с тем же именем перезаписывает
    предыдущую (удобно для тестов с моками).
    """

    PROVIDER_REGISTRY[factory.name] = factory


def get_llm_provider(name: str) -> LLMProviderFactory:
    """Возвращает фабрику провайдера или кидает ValueError.

    Сообщение перечисляет зарегистрированные имена — caller (API endpoint,
    pipeline) показывает юзеру валидные варианты без гадания по коду.
    """

    factory = PROVIDER_REGISTRY.get(name)
    if factory is None:
        raise ValueError(
            f"unknown LLM provider: {name!r}. "
            f"Registered: {sorted(PROVIDER_REGISTRY)}"
        )
    return factory
