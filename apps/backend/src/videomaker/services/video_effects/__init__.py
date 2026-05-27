"""Video effects plugin registry.

Каждый эффект — отдельный модуль. Регистрация через ``EFFECTS_REGISTRY``
в ``registry.py``. Добавление нового эффекта:

1. Новый файл ``<effect_id>.py``, класс реализует ``VideoEffect`` Protocol.
2. Флаг в ``PostProductionConfig`` (например ``<effect_id>_enabled: bool``).
3. Миграция Alembic для ORM-колонки.
4. Импорт + добавление в ``EFFECTS_REGISTRY``.

Всё остальное (snapshot в ``ProjectGraph``, Stage D в filter_graph_builder,
frontend override checkbox) обновляется само через итерацию по registry.
"""

from videomaker.services.video_effects.base import (
    VideoEffect,
    VideoEffectContext,
)
from videomaker.services.video_effects.bw import BWEffect
from videomaker.services.video_effects.registry import (
    EFFECTS_REGISTRY,
    find_effect,
)

__all__ = [
    "EFFECTS_REGISTRY",
    "BWEffect",
    "VideoEffect",
    "VideoEffectContext",
    "find_effect",
]
