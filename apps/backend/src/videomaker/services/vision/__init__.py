"""Vision layer — Moondream 2 local inference через llama-cpp-python Metal.

Пакет реализует опциональный мультимодальный слой видеогенератора. Когда
`cfg.vision_enabled=False` — фабрика возвращает `None` и пайплайн работает
байтово идентично audio-only baseline.

Public API:
    * `VisionClient` — Protocol интерфейс (query/caption/detect/health).
    * `MoondreamLocalClient` — llama.cpp-based реализация для Moondream 2 GGUF.
    * `VisionModelManager` — загрузка и кэш GGUF-файлов через huggingface_hub.
    * `build_vision_client(cfg, provider=...)` — factory, создаёт клиент или None.
    * `VISION_REGISTRY`, `register_vision_provider`, `get_vision_provider` —
      hot-plug реестр провайдеров (см. `registry.py`).
    * `VisionQueryResult`, `VisionCaptionResult`, `VisionDetectResult`,
      `VisionHealthStatus` — Pydantic модели результатов.

При импорте пакета автоматически регистрируется дефолтный провайдер
`"moondream_local"`. Новые провайдеры добавляются тем же паттерном:
создать фабрику, вызвать `register_vision_provider(...)` здесь.
"""

from videomaker.services.vision.base import VisionClient
from videomaker.services.vision.factory import (
    DEFAULT_VISION_PROVIDER,
    build_vision_client,
    reset_vision_client,
)
from videomaker.services.vision.frame_cache import (
    CachedFrame,
    FrameExtractor,
    VisionResultCache,
    compute_video_sha256,
)
from videomaker.services.vision.model_manager import VisionModelManager
from videomaker.services.vision.moondream_local import (
    MoondreamLocalClient,
    MoondreamLocalFactory,
)
from videomaker.services.vision.rate_limiter import (
    VisionRateLimiter,
    get_vision_rate_limiter,
    reset_vision_rate_limiter,
)
from videomaker.services.vision.registry import (
    VISION_REGISTRY,
    VisionProviderFactory,
    get_vision_provider,
    register_vision_provider,
)
from videomaker.services.vision.types import (
    VisionCaptionResult,
    VisionDetection,
    VisionDetectResult,
    VisionHealthStatus,
    VisionQueryResult,
)

# Регистрация дефолтного провайдера. Делается здесь (а не в moondream_local.py)
# чтобы точка регистрации была явной и единственной — упрощает поиск и тесты.
register_vision_provider(MoondreamLocalFactory())


__all__ = [
    "DEFAULT_VISION_PROVIDER",
    "VISION_REGISTRY",
    "CachedFrame",
    "FrameExtractor",
    "MoondreamLocalClient",
    "MoondreamLocalFactory",
    "VisionCaptionResult",
    "VisionClient",
    "VisionDetectResult",
    "VisionDetection",
    "VisionHealthStatus",
    "VisionModelManager",
    "VisionProviderFactory",
    "VisionQueryResult",
    "VisionRateLimiter",
    "VisionResultCache",
    "build_vision_client",
    "compute_video_sha256",
    "get_vision_provider",
    "get_vision_rate_limiter",
    "register_vision_provider",
    "reset_vision_client",
    "reset_vision_rate_limiter",
]
