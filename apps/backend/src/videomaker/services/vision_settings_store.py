"""Vision runtime settings store — DB-backed VisionRuntimeSettings с cache.

Выделено из runtime_settings_store.py в Phase 5.2.

Стратегия:
* Поля `VisionRuntimeSettings` хранятся в таблице `runtime_settings`
  с prefix'ом `vision_` — это избегает коллизий с PerformanceSettings
  (например, если в будущем появится общее поле `enabled`).
* `get_vision_settings()` — read-through cache (TTL 30s) с merge:
  defaults < env (Settings) < db.
* `set_vision_settings(payload)` — bulk upsert + invalidate cache.
"""

from __future__ import annotations

import json
import time

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from videomaker.core.config import Settings, get_settings
from videomaker.core.db import session_scope
from videomaker.core.logging import get_logger
from videomaker.models.job import RuntimeSettingRow
from videomaker.models.vision_settings import VisionRuntimeSettings

log = get_logger(__name__)

_VISION_TTL_SEC = 30.0
_vision_cache: tuple[float, VisionRuntimeSettings] | None = None

# Prefix для vision-ключей в таблице runtime_settings — избегает коллизий
# с PerformanceSettings-полями (например, если в будущем появится `enabled`).
_VISION_KEY_PREFIX = "vision_"


async def get_vision_settings(
    settings: Settings | None = None, *, force_refresh: bool = False
) -> VisionRuntimeSettings:
    """Возвращает эффективные vision runtime-настройки (env seed < db override)."""
    global _vision_cache
    if not force_refresh and _vision_cache is not None:
        cached_at, cached = _vision_cache
        if time.monotonic() - cached_at < _VISION_TTL_SEC:
            return cached

    cfg = settings or get_settings()
    seed = VisionRuntimeSettings.from_settings(cfg)
    seed_dict = seed.model_dump()

    async with session_scope() as session:
        result = await session.execute(select(RuntimeSettingRow))
        rows = list(result.scalars().all())

    overrides: dict[str, object] = {}
    for row in rows:
        if not row.key.startswith(_VISION_KEY_PREFIX):
            continue
        field_name = row.key[len(_VISION_KEY_PREFIX):]
        if field_name not in seed_dict:
            continue
        try:
            overrides[field_name] = json.loads(row.value_json)
        except json.JSONDecodeError as exc:
            log.warning(
                "runtime_vision_setting_invalid_json",
                key=row.key,
                error=str(exc),
            )

    merged = {**seed_dict, **overrides}
    effective = VisionRuntimeSettings.model_validate(merged)
    _vision_cache = (time.monotonic(), effective)
    return effective


async def set_vision_settings(
    payload: VisionRuntimeSettings,
) -> VisionRuntimeSettings:
    """Bulk upsert всех vision полей (с префиксом) + invalidate кэш."""
    rows: list[dict[str, str]] = [
        {
            "key": f"{_VISION_KEY_PREFIX}{key}",
            "value_json": json.dumps(value),
        }
        for key, value in payload.model_dump().items()
    ]
    async with session_scope() as session:
        if rows:
            stmt = sqlite_insert(RuntimeSettingRow).values(rows)
            stmt = stmt.on_conflict_do_update(
                index_elements=[RuntimeSettingRow.key],
                set_={"value_json": stmt.excluded.value_json},
            )
            await session.execute(stmt)
    invalidate_vision_cache()
    log.info("runtime_vision_settings_updated", n_keys=len(rows))
    return await get_vision_settings(force_refresh=True)


def invalidate_vision_cache() -> None:
    """Сбрасывает vision TTL-cache."""
    global _vision_cache
    _vision_cache = None


__all__ = [
    "get_vision_settings",
    "invalidate_vision_cache",
    "set_vision_settings",
]
