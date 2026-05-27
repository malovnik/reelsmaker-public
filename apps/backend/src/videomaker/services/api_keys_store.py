"""Runtime-хранилище API-ключей (Gemini / Deepgram / Publer).

Ключи можно задать из UI (PUT /settings/api-keys) без правки ``.env`` — для
пользователей, которые не лезут в конфиги. Значения хранятся в той же таблице
``runtime_settings`` под namespaced-ключами ``secret__*`` (PerformanceSettings-
стор их игнорит, т.к. их нет в его seed_dict), а при сохранении и на старте
приложения применяются на singleton ``Settings`` (``get_settings()``). Поэтому
ВСЕ существующие читатели ``settings.<key>`` прозрачно получают runtime-значение
без правок. Runtime перекрывает env; пустая строка очищает (возврат к env).
"""

from __future__ import annotations

import json

from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from videomaker.core.config import Settings, get_settings
from videomaker.core.db import session_scope
from videomaker.core.logging import get_logger
from videomaker.models.job import RuntimeSettingRow

log = get_logger(__name__)

_PREFIX = "secret__"

#: Поля Settings, которыми управляет UI-форма ключей. Имя поля = атрибут Settings.
API_KEY_FIELDS: tuple[str, ...] = (
    "gemini_api_key",
    "deepgram_api_key",
    "publer_api_key",
    "publer_workspace_id",
)

#: Снимок env-значений ДО первой мутации singleton'а. Нужен, чтобы очистка
#: runtime-ключа возвращала исходное env-значение, а не оставляла старое.
_env_baseline: dict[str, str] | None = None


async def get_stored_api_keys() -> dict[str, str]:
    """Непустые runtime-ключи из БД (без env). Ключ → значение."""

    storage_to_name = {f"{_PREFIX}{name}": name for name in API_KEY_FIELDS}
    async with session_scope() as session:
        result = await session.execute(
            select(RuntimeSettingRow).where(
                RuntimeSettingRow.key.in_(storage_to_name.keys())
            )
        )
        rows = list(result.scalars().all())

    out: dict[str, str] = {}
    for row in rows:
        name = storage_to_name.get(row.key)
        if name is None:
            continue
        try:
            value = json.loads(row.value_json)
        except json.JSONDecodeError:
            continue
        if isinstance(value, str) and value:
            out[name] = value
    return out


async def set_api_keys(updates: dict[str, str | None]) -> None:
    """Сохраняет переданные ключи. Значение "" / None → удаление (возврат к env).

    Обновляются только переданные поля (PATCH-семантика на стороне caller'а).
    """

    to_upsert: list[dict[str, str]] = []
    to_delete: list[str] = []
    for name, value in updates.items():
        if name not in API_KEY_FIELDS:
            continue
        storage_key = f"{_PREFIX}{name}"
        if value is None or value.strip() == "":
            to_delete.append(storage_key)
        else:
            to_upsert.append(
                {"key": storage_key, "value_json": json.dumps(value.strip())}
            )

    async with session_scope() as session:
        if to_upsert:
            stmt = sqlite_insert(RuntimeSettingRow).values(to_upsert)
            stmt = stmt.on_conflict_do_update(
                index_elements=[RuntimeSettingRow.key],
                set_={"value_json": stmt.excluded.value_json},
            )
            await session.execute(stmt)
        if to_delete:
            await session.execute(
                delete(RuntimeSettingRow).where(
                    RuntimeSettingRow.key.in_(to_delete)
                )
            )

    await apply_api_keys_to_settings()
    # Значения НЕ логируем — только счётчики.
    log.info("api_keys_updated", upserted=len(to_upsert), cleared=len(to_delete))


async def apply_api_keys_to_settings(settings: Settings | None = None) -> None:
    """Применяет сохранённые runtime-ключи на singleton Settings.

    Эффективное значение = runtime (из БД) ИЛИ исходное env-значение.
    """

    global _env_baseline
    cfg = settings or get_settings()
    if _env_baseline is None:
        # Первый вызов (старт приложения) — singleton ещё держит чистые env-
        # значения. Снимаем baseline до любых мутаций.
        _env_baseline = {
            name: (getattr(cfg, name, "") or "") for name in API_KEY_FIELDS
        }

    stored = await get_stored_api_keys()
    for name in API_KEY_FIELDS:
        effective = stored.get(name) or _env_baseline.get(name, "")
        setattr(cfg, name, effective)


async def api_keys_status() -> dict[str, bool]:
    """Маскированный статус: какие ключи реально заданы (runtime ИЛИ env)."""

    await apply_api_keys_to_settings()
    cfg = get_settings()
    return {name: bool(getattr(cfg, name, "") or "") for name in API_KEY_FIELDS}


__all__ = [
    "API_KEY_FIELDS",
    "api_keys_status",
    "apply_api_keys_to_settings",
    "get_stored_api_keys",
    "set_api_keys",
]
