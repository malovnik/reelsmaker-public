"""SQLAlchemy ``TypeDecorator``-ы для ORM-моделей job.

Здесь лежит ``_StrEnumColumn`` — единственный custom-тип, нужный, чтобы
колонки с ``Mapped[SomeStrEnum]`` читались как Enum, а не как голая
строка (иначе ``.value`` на объекте падает с AttributeError).

Храним отдельно от ORM-моделей, чтобы не плодить циклы, и отдельно от
``job_constants`` — TypeDecorator тянет SQLAlchemy, а в константы хочется
ходить без тяжёлого stack'а.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from sqlalchemy import String
from sqlalchemy.types import TypeDecorator


class _StrEnumColumn(TypeDecorator):  # type: ignore[type-arg]
    """SQLAlchemy column type для `StrEnum` с bind/load coercion.

    Storage остаётся VARCHAR(length) — миграция БД не нужна. Python-side
    оба направления конвертируют str ↔ Enum, чтобы `Mapped[Enum]` annotation
    соответствовала runtime-значению (иначе `.value` падает с AttributeError).
    """

    impl = String
    cache_ok = True

    def __init__(self, enum_cls: type[StrEnum], length: int) -> None:
        super().__init__(length=length)
        self._enum_cls = enum_cls

    def process_bind_param(self, value: Any, dialect: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, self._enum_cls):
            return value.value
        # Совместимость с прямым assign'ом строки (например legacy code).
        return str(value)

    def process_result_value(self, value: Any, dialect: Any) -> StrEnum | None:
        if value is None:
            return None
        if isinstance(value, self._enum_cls):
            return value
        return self._enum_cls(value)


__all__ = ["_StrEnumColumn"]
