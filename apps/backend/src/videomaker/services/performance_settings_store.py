"""Performance runtime settings store — DB-backed PerformanceSettings с
TTL-cache и per-job ContextVar override'ом.

Выделено из runtime_settings_store.py в Phase 5.2. Facade в
runtime_settings_store.py re-export'ирует публичный API для backward-compat.

Стратегия:
* Все поля `PerformanceSettings` хранятся в таблице `runtime_settings`
  как `key=<field_name> value_json=<json>`.
* `get_performance_settings()` — read-through cache (TTL 30s) с merge:
  defaults < env (Settings) < db < job_override (ContextVar).
* `set_performance_settings(payload)` — bulk upsert + invalidate cache.
* `job_settings_override(overrides)` — context manager для per-job Auto Mode.
  Устанавливает ContextVar на время pipeline выполнения, читается внутри
  `get_performance_settings` и merge'ится на самом высоком уровне.

In-process cache + bump-counter — простой инвариант: после PUT все
параллельные читатели обнаруживают expired entry на следующем чтении.
ContextVar инвариантен к async-concurrency (asyncio.Task каждый раз
получает snapshot контекста).
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from videomaker.core.config import Settings, get_settings
from videomaker.core.db import session_scope
from videomaker.core.logging import get_logger
from videomaker.models.job import RuntimeSettingRow
from videomaker.models.runtime_settings import PerformanceSettings

log = get_logger(__name__)


#: Per-job overrides для Automatic Mode (T11). Устанавливается в
#: `run_pipeline_safe` через `job_settings_override()` и читается в
#: `get_performance_settings` — merge'ится поверх global db settings.
_job_override: ContextVar[dict[str, Any] | None] = ContextVar(
    "videomaker_job_settings_override", default=None
)

_PERF_TTL_SEC = 30.0
_perf_cache: tuple[float, PerformanceSettings] | None = None


async def get_performance_settings(
    settings: Settings | None = None, *, force_refresh: bool = False
) -> PerformanceSettings:
    """Возвращает эффективные runtime-настройки.

    Кэш 30 секунд in-process. После PUT (`set_performance_settings`)
    кэш сбрасывается, и все читатели подгружают новое значение.
    """

    global _perf_cache
    if not force_refresh and _perf_cache is not None:
        cached_at, cached = _perf_cache
        if time.monotonic() - cached_at < _PERF_TTL_SEC:
            return cached

    cfg = settings or get_settings()
    seed = PerformanceSettings.from_settings(cfg)
    seed_dict = seed.model_dump()

    async with session_scope() as session:
        result = await session.execute(select(RuntimeSettingRow))
        rows = list(result.scalars().all())

    overrides: dict[str, object] = {}
    for row in rows:
        if row.key not in seed_dict:
            continue
        try:
            overrides[row.key] = json.loads(row.value_json)
        except json.JSONDecodeError as exc:
            log.warning(
                "runtime_setting_invalid_json", key=row.key, error=str(exc)
            )

    merged = {**seed_dict, **overrides}

    # Phase 8 migration (2026-04-21): legacy narrative_mode values.
    # В БД могли остаться значения "top_down" от Phase 6 (enum был
    # bottom_up|top_down). Теперь enum = bottom_up|chaptered|map_reduce.
    # Мапим legacy → chaptered (это и есть semantically то же самое —
    # Phase 1-6 per-chapter top-down). Miss — оставляем default для
    # validation error чтобы не скрывать реальные баги.
    if merged.get("narrative_mode") == "top_down":
        merged["narrative_mode"] = "chaptered"

    # LLM tier migration (2026-04-21): non-lite профили удалены.
    # В БД могли остаться значения "balanced"/"quality" от старой tier-
    # матрицы, которая использовала gemini-3-flash-preview. Теперь
    # разрешены только "fast" и "legacy" (оба резолвятся в Lite-варианты).
    # Коерсим legacy значения в "fast" чтобы не падать на validation.
    if merged.get("llm_tier_profile") in {"balanced", "quality"}:
        merged["llm_tier_profile"] = "fast"

    # T11: если мы внутри pipeline в Automatic Mode — merge job_override
    # поверх global settings. Это per-task (ContextVar), так что parallel
    # jobs не влияют друг на друга.
    job_override = _job_override.get()
    if job_override:
        # Фильтруем только поля которые реально есть в PerformanceSettings
        valid_keys = set(seed_dict.keys())
        filtered = {
            k: v for k, v in job_override.items() if k in valid_keys
        }
        if filtered:
            merged = {**merged, **filtered}

    effective = PerformanceSettings.model_validate(merged)

    # Кэшируем ТОЛЬКО global path (без job override) — иначе разные jobs
    # будут получать чужой override из cache.
    if not job_override:
        _perf_cache = (time.monotonic(), effective)
    return effective


@asynccontextmanager
async def job_settings_override(
    overrides: dict[str, Any] | None,
) -> AsyncIterator[None]:
    """T11 — Context manager для per-job AutoConfig override.

    Устанавливает ContextVar на время pipeline выполнения. Все вызовы
    `get_performance_settings` внутри этого блока получают merged config.

    Пример использования:
        async with job_settings_override(job.options.get("auto_config")):
            await run_pipeline_stages(job)

    None или пустой dict → noop (Manual mode).
    """
    if not overrides:
        yield
        return

    token = _job_override.set(dict(overrides))
    try:
        yield
    finally:
        _job_override.reset(token)


async def set_performance_settings(
    payload: PerformanceSettings,
) -> PerformanceSettings:
    """Bulk upsert всех полей `payload` + invalidate кэш."""

    rows: list[dict[str, str]] = [
        {"key": key, "value_json": json.dumps(value)}
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
    invalidate_performance_cache()
    log.info("runtime_settings_updated", n_keys=len(rows))
    # Возвращаем то, что сейчас в БД (force_refresh=True гарантирует свежее).
    return await get_performance_settings(force_refresh=True)


def invalidate_performance_cache() -> None:
    """Сбрасывает performance TTL-cache."""
    global _perf_cache
    _perf_cache = None


def get_cached_performance_settings() -> PerformanceSettings | None:
    """Sync-доступ к последнему кэшированному snapshot'у без await.

    Нужен в местах где нельзя выполнить await (build_llm_for_tier
    вызывается и из sync-контекстов). Возвращает None если кэш пуст
    или истёк — тогда caller должен fallback на env-defaults.
    """

    if _perf_cache is None:
        return None
    cached_at, cached = _perf_cache
    if time.monotonic() - cached_at >= _PERF_TTL_SEC:
        return None
    return cached


__all__ = [
    "get_cached_performance_settings",
    "get_performance_settings",
    "invalidate_performance_cache",
    "job_settings_override",
    "set_performance_settings",
]
