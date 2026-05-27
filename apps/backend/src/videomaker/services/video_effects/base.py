"""VideoEffect Protocol: плагинный интерфейс для post-crop эффектов.

Каждый эффект — статический класс с:
- ``effect_id: str`` — стабильный идентификатор для артефактов/логов.
- ``label: str`` — человекочитаемое имя для UI.
- ``build_filter_expr(context) -> str | None`` — возвращает ffmpeg filter
  chain (без leading/trailing запятых) или ``None`` если эффект отключён.

Эффекты применяются последовательно в Stage D filter_graph между Stage C
(subtitles) и Stage F (extras). Порядок в ``EFFECTS_REGISTRY`` определяет
порядок применения.

Почему Protocol, а не ABC: позволяет plain-классы без наследования,
упрощает тестирование (можно подменить моком) и делает registry
полностью статичным (type-check без runtime reflection).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from videomaker.models.post_production import PostProductionConfig


@dataclass(slots=True, frozen=True)
class VideoEffectContext:
    """Снимок окружения, передаваемый эффекту при построении filter expr.

    В будущем сюда можно добавить: frame dims, duration_sec, source aspect,
    если какой-то эффект захочет адаптивные параметры. Сейчас содержит
    минимум — только ``post_production_config``.
    """

    post_production_config: PostProductionConfig


@runtime_checkable
class VideoEffect(Protocol):
    effect_id: str
    label: str

    def build_filter_expr(self, context: VideoEffectContext) -> str | None:
        """Возвращает ffmpeg filter chain (например ``hue=s=0``) или None.

        None означает, что эффект не применяется (флаг выключен или контекст
        не подходит). Пустая строка ``""`` — валидный результат «no-op»;
        чтобы пропустить эффект надо вернуть именно None.
        """
        ...
