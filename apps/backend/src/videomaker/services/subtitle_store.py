"""CRUD над таблицей `subtitle_style_presets` + seed builtin'ов.

Правила:

* builtin-пресеты (`is_builtin=True`) нельзя удалить/переименовать/редактировать —
  они гарантируют наличие рабочих шаблонов даже если пользователь потёр всё руками.
* Ровно один пресет может быть `is_default=True`. При установке нового default
  старый автоматически сбрасывается в одной транзакции.
* `seed_builtin_if_needed` — идемпотент: если пресет уже есть (по name), он
  обновляет `style_json` к каноничному built-in значению (чтобы обновления кода
  подхватывались), но сохраняет `is_default` пользовательскую отметку.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from videomaker.core.db import session_scope
from videomaker.core.logging import get_logger
from videomaker.models.job import (
    SubtitleStyleConfig,
    SubtitleStylePresetCreate,
    SubtitleStylePresetRow,
    SubtitleStylePresetUpdate,
)
from videomaker.services.subtitle_styles import BUILTIN_PRESETS

log = get_logger(__name__)


async def list_presets() -> list[SubtitleStylePresetRow]:
    async with session_scope() as session:
        result = await session.execute(
            select(SubtitleStylePresetRow).order_by(
                SubtitleStylePresetRow.is_builtin.desc(),
                SubtitleStylePresetRow.name.asc(),
            )
        )
        return list(result.scalars().all())


async def get_preset(preset_id: int) -> SubtitleStylePresetRow | None:
    async with session_scope() as session:
        return await session.get(SubtitleStylePresetRow, preset_id)


async def get_default_preset() -> SubtitleStylePresetRow | None:
    async with session_scope() as session:
        result = await session.execute(
            select(SubtitleStylePresetRow).where(
                SubtitleStylePresetRow.is_default.is_(True)
            )
        )
        row = result.scalar_one_or_none()
        if row is not None:
            return row
        # Fallback — если никто не default, берём первый builtin.
        result = await session.execute(
            select(SubtitleStylePresetRow)
            .where(SubtitleStylePresetRow.is_builtin.is_(True))
            .order_by(SubtitleStylePresetRow.id.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()


async def create_preset(payload: SubtitleStylePresetCreate) -> SubtitleStylePresetRow:
    async with session_scope() as session:
        if payload.is_default:
            await _clear_default(session)
        row = SubtitleStylePresetRow(
            name=payload.name,
            style_json=payload.style.model_dump(mode="json"),
            is_builtin=False,
            is_default=payload.is_default,
        )
        session.add(row)
        try:
            await session.flush()
        except IntegrityError as exc:
            raise PresetConflictError(
                f"preset name {payload.name!r} already exists"
            ) from exc
        await session.refresh(row)
        return row


async def update_preset(
    preset_id: int, payload: SubtitleStylePresetUpdate
) -> SubtitleStylePresetRow:
    async with session_scope() as session:
        row = await session.get(SubtitleStylePresetRow, preset_id)
        if row is None:
            raise PresetNotFoundError(f"preset {preset_id} not found")
        if row.is_builtin:
            raise BuiltinPresetError(
                f"builtin preset {row.name!r} is not editable"
            )
        if payload.name is not None:
            row.name = payload.name
        if payload.style is not None:
            row.style_json = payload.style.model_dump(mode="json")
        if payload.is_default is True and not row.is_default:
            await _clear_default(session)
            row.is_default = True
        elif payload.is_default is False and row.is_default:
            row.is_default = False
        try:
            await session.flush()
        except IntegrityError as exc:
            raise PresetConflictError(
                f"preset name {payload.name!r} already exists"
            ) from exc
        await session.refresh(row)
        return row


async def delete_preset(preset_id: int) -> None:
    async with session_scope() as session:
        row = await session.get(SubtitleStylePresetRow, preset_id)
        if row is None:
            raise PresetNotFoundError(f"preset {preset_id} not found")
        if row.is_builtin:
            raise BuiltinPresetError(
                f"builtin preset {row.name!r} is not deletable"
            )
        if row.is_default:
            raise DefaultPresetError(
                "cannot delete the default preset — set another preset as default first"
            )
        await session.delete(row)


async def seed_builtin_if_needed() -> int:
    """Создаёт отсутствующие builtin-пресеты. Обновляет `style_json` существующих
    к каноничным значениям (чтобы code changes в `BUILTIN_PRESETS` распространялись),
    но сохраняет пользовательскую отметку `is_default` на user-пресетах.

    Возвращает количество вставленных записей (0 если всё уже было).
    """

    inserted = 0
    async with session_scope() as session:
        existing = await session.execute(select(SubtitleStylePresetRow))
        by_name = {row.name: row for row in existing.scalars()}

        has_any_default = any(r.is_default for r in by_name.values())

        for name, is_default_flag, config in BUILTIN_PRESETS:
            canonical = config.model_dump(mode="json")
            row = by_name.get(name)
            if row is None:
                # Первый builtin-default попадает в БД только если в системе
                # ещё нет ни одного default (включая user-созданных).
                apply_default = is_default_flag and not has_any_default
                if apply_default:
                    has_any_default = True
                session.add(
                    SubtitleStylePresetRow(
                        name=name,
                        style_json=canonical,
                        is_builtin=True,
                        is_default=apply_default,
                    )
                )
                inserted += 1
            else:
                # Обновляем стиль к каноничному, is_default не трогаем —
                # пользователь мог выбрать другой builtin как default через API.
                row.style_json = canonical
                if not row.is_builtin:
                    # Если кто-то вручную создал row с таким именем — делаем
                    # его builtin'ом (защита от ручного редактирования БД).
                    row.is_builtin = True

    if inserted:
        log.info("subtitle_presets_seeded", inserted=inserted)
    return inserted


async def _clear_default(session: AsyncSession) -> None:
    await session.execute(
        update(SubtitleStylePresetRow)
        .where(SubtitleStylePresetRow.is_default.is_(True))
        .values(is_default=False)
    )


def resolve_style_json(raw: dict[str, Any] | None) -> SubtitleStyleConfig | None:
    if raw is None:
        return None
    return SubtitleStyleConfig.model_validate(raw)


class PresetNotFoundError(LookupError):
    pass


class BuiltinPresetError(RuntimeError):
    pass


class DefaultPresetError(RuntimeError):
    pass


class PresetConflictError(RuntimeError):
    pass


__all__ = [
    "BuiltinPresetError",
    "DefaultPresetError",
    "PresetConflictError",
    "PresetNotFoundError",
    "create_preset",
    "delete_preset",
    "get_default_preset",
    "get_preset",
    "list_presets",
    "resolve_style_json",
    "seed_builtin_if_needed",
    "update_preset",
]
