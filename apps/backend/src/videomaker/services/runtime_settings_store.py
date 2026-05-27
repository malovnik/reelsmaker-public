"""Runtime settings store — facade для обратной совместимости.

Реальная логика в:
- ``services/performance_settings_store.py`` — PerformanceSettings
- ``services/vision_settings_store.py`` — VisionRuntimeSettings

Этот файл только re-export'ирует публичный API. Существующие импорты
``from videomaker.services.runtime_settings_store import ...`` продолжают
работать без изменений в callers.
"""

from __future__ import annotations

from videomaker.services.performance_settings_store import (
    get_cached_performance_settings,
    get_performance_settings,
    invalidate_performance_cache,
    job_settings_override,
    set_performance_settings,
)
from videomaker.services.vision_settings_store import (
    get_vision_settings,
    invalidate_vision_cache,
    set_vision_settings,
)


def invalidate_cache() -> None:
    """Сбрасывает оба TTL-cache (performance + vision).

    Backward-compat alias для старой единой функции. Новый код должен
    вызывать конкретный invalidator из соответствующего модуля.
    """
    invalidate_performance_cache()
    invalidate_vision_cache()


__all__ = [
    "get_cached_performance_settings",
    "get_performance_settings",
    "get_vision_settings",
    "invalidate_cache",
    "invalidate_performance_cache",
    "invalidate_vision_cache",
    "job_settings_override",
    "set_performance_settings",
    "set_vision_settings",
]
