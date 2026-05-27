"""Factory — `build_vision_client(cfg, provider)` возвращает VisionClient или None.

Логика:
* Если `cfg.vision_enabled=False` → None. Пайплайн обязан корректно работать
  с None клиентом (fallback = pipeline байтово идентичен pre-vision).
* Если `vision_enabled=True` → инстанцируется клиент по имени провайдера через
  `VISION_REGISTRY`. Default = `"moondream_local"` (локальная Moondream 2 GGUF).
  Будущие облачные провайдеры (Gemini Vision, OpenAI Vision) регистрируются
  в том же реестре без изменений этого модуля.

Singleton pattern: клиент кэшируется process-wide по имени провайдера.
llama.cpp instance тяжёлый (~5GB RAM), не хотим дублировать. Если caller
запросил другого провайдера чем закэширован — старый закрывается, новый
поднимается.
"""

from __future__ import annotations

from videomaker.core.config import Settings, get_settings
from videomaker.core.logging import get_logger
from videomaker.services.vision.base import VisionClient
from videomaker.services.vision.registry import get_vision_provider

log = get_logger(__name__)

DEFAULT_VISION_PROVIDER: str = "moondream_local"

_vision_client: VisionClient | None = None
_vision_client_provider: str | None = None


def build_vision_client(
    settings: Settings | None = None,
    provider: str = DEFAULT_VISION_PROVIDER,
) -> VisionClient | None:
    """Возвращает vision-клиент выбранного провайдера или None.

    Аргументы:
        settings: `Settings` (default = `get_settings()`).
        provider: имя зарегистрированного провайдера в `VISION_REGISTRY`.
            Default — `moondream_local` (обратная совместимость).

    Клиент кэшируется process-wide. Для пересоздания (например, после смены
    `vision_enabled` или переключения провайдера через runtime settings) —
    вызывать `reset_vision_client()`.
    """
    cfg = settings or get_settings()
    if not cfg.vision_enabled:
        return None

    global _vision_client, _vision_client_provider
    if _vision_client is not None and _vision_client_provider == provider:
        return _vision_client

    factory = get_vision_provider(provider)
    client = factory.build(cfg)
    _vision_client = client
    _vision_client_provider = provider
    log.info(
        "vision_client_built",
        provider=provider,
        repo=cfg.vision_gguf_repo,
        n_gpu_layers=cfg.vision_n_gpu_layers,
        n_ctx=cfg.vision_n_ctx,
    )
    return client


async def reset_vision_client() -> None:
    """Закрывает singleton и сбрасывает кэш. Для runtime-toggle через API."""
    global _vision_client, _vision_client_provider
    if _vision_client is None:
        return
    client = _vision_client
    _vision_client = None
    _vision_client_provider = None
    await client.close()
    log.info("vision_client_reset")
