"""Vision provider registry — hot-plug точка для новых vision backends.

Каждый провайдер регистрируется через `register_vision_provider(factory)`.
Factory реализует минимальный Protocol: имя + `build(cfg)` функция возвращающая
`VisionClient`.

Default провайдер — "moondream_local" (локальная Moondream 2 GGUF). Будущие
провайдеры (Gemini Vision, OpenAI Vision) регистрируются тем же паттерном
без изменений в `factory.py`.

Архитектурные решения:
* Registry хранит только provider-specific конструкцию — singleton-кэш и
  «вернуть None когда vision_enabled=False» живут в `build_vision_client`,
  т.к. это cross-cutting concerns независящие от бэкенда.
* Регистрация делается явно в `services/vision/__init__.py` (не
  side-effect'ом при импорте модуля провайдера) — чтобы pyright и runtime
  видели одну и ту же точку и не было гонок порядка импортов.
"""

from __future__ import annotations

from typing import Protocol

from videomaker.core.config import Settings
from videomaker.services.vision.base import VisionClient


class VisionProviderFactory(Protocol):
    """Контракт фабрики vision-провайдера.

    `name` — строковый идентификатор, который попадает в runtime_settings
    (`VisionRuntimeSettings.vision_provider`) и используется как ключ в
    `VISION_REGISTRY`.
    """

    name: str

    def build(self, cfg: Settings) -> VisionClient: ...


VISION_REGISTRY: dict[str, VisionProviderFactory] = {}


def register_vision_provider(factory: VisionProviderFactory) -> None:
    """Регистрирует провайдера vision в глобальном реестре.

    Идемпотентна — повторная регистрация с тем же именем перезаписывает
    предыдущую (полезно для тестов, которые подменяют фабрику).
    """
    VISION_REGISTRY[factory.name] = factory


def get_vision_provider(name: str) -> VisionProviderFactory:
    """Возвращает зарегистрированную фабрику или кидает ValueError.

    Сообщение об ошибке перечисляет доступные провайдеры — чтобы caller
    (API-эндпоинт, pipeline) мог подсказать пользователю валидное имя.
    """
    factory = VISION_REGISTRY.get(name)
    if factory is None:
        raise ValueError(
            f"unknown vision provider: {name!r}. "
            f"Registered: {sorted(VISION_REGISTRY)}"
        )
    return factory
