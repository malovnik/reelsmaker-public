"""Tier → model mapping resolver с runtime_settings override.

Kartoziya-пайплайн имеет три tier'а: ``pro`` / ``flash`` / ``flash_lite``.
Pipeline-матрица живёт в runtime_settings (``PerformanceSettings.llm_tier_profile``) —
пользователь выбирает из UI между ``fast`` и ``legacy`` без рестарта.

Профиль ``fast`` мапит каждый tier на реальную Gemini-модель его уровня:
pro → Gemini Pro, flash → Gemini Flash, flash_lite → выбранный Lite-вариант.
Pro/Flash — осознанный opt-in через UI; flash_lite остаётся cheapest.

Cold-cache fallback критичен для расходов: если runtime_settings ещё не
загружены (первые 30с после старта сервера), fallback → all-Lite (каждый
tier на Flash-Lite). Так первый pipeline после рестарта не уйдёт на дорогой
Pro, пока не прогрелся runtime_settings cache.
"""

from __future__ import annotations

from typing import Literal

from videomaker.core.config import Settings
from videomaker.core.logging import get_logger

LLMTier = Literal["pro", "flash", "flash_lite"]

log = get_logger(__name__)


_LITE_3_1 = "gemini-3.1-flash-lite-preview"
_LITE_2_5 = "gemini-2.5-flash-lite"


def _tier_profiles(
    cfg: Settings, lite_variant: str
) -> dict[str, dict[LLMTier, str]]:
    """Формирует tier-матрицу.

    ``lite_variant`` — "2_5" или "3_1": какую Flash-Lite модель использовать
    для tier ``flash_lite`` (и для всех tier в ``legacy``).
    Pro/Flash ID берутся из конфигурации (``GEMINI_PRO_MODEL`` /
    ``GEMINI_FLASH_MODEL``).
    """

    lite = _LITE_2_5 if lite_variant == "2_5" else _LITE_3_1
    return {
        "fast": {
            # Реальные модели по уровню tier: Pro — осознанный opt-in.
            "pro": cfg.gemini_pro_model,
            "flash": cfg.gemini_flash_model,
            "flash_lite": lite,
        },
        "legacy": {
            # Классическая одна-модель-везде: фиксированно
            # 3.1-flash-lite-preview вне зависимости от lite_variant
            # (историческая совместимость).
            "pro": _LITE_3_1,
            "flash": _LITE_3_1,
            "flash_lite": _LITE_3_1,
        },
    }


def _cold_cache_fallback(lite_variant: str) -> dict[LLMTier, str]:
    """All-Lite fallback при холодном кэше: каждый tier на Flash-Lite."""

    lite = _LITE_2_5 if lite_variant == "2_5" else _LITE_3_1
    return {"pro": lite, "flash": lite, "flash_lite": lite}


def _resolve_tier_models(cfg: Settings) -> dict[LLMTier, str]:
    """Определяет mapping tier → модель с учётом runtime_settings override.

    Cold-cache fallback идёт на all-Lite (каждый tier на Flash-Lite) —
    защита расходов на старте. Нераспознанный профиль (legacy строки из
    старой БД, удалённые balanced/quality) также коерсится к all-Lite.
    """

    profile, lite_variant = _try_read_tier_profile()
    if profile is None:
        # Cold cache: безопасный all-Lite fallback.
        mapping = _cold_cache_fallback(lite_variant)
        _log_tier_mapping(mapping, profile="cold_cache", lite_variant=lite_variant)
        return mapping

    profiles = _tier_profiles(cfg, lite_variant)
    if profile in profiles:
        mapping = profiles[profile]
        _log_tier_mapping(mapping, profile=profile, lite_variant=lite_variant)
        return mapping

    # Нераспознанный профиль (например legacy "balanced"/"quality" из БД) —
    # безопасный all-Lite fallback.
    mapping = _cold_cache_fallback(lite_variant)
    _log_tier_mapping(mapping, profile=f"unknown:{profile}", lite_variant=lite_variant)
    return mapping


def _log_tier_mapping(
    mapping: dict[LLMTier, str], *, profile: str, lite_variant: str
) -> None:
    """Структурный лог выбранной модели per-tier."""

    log.info(
        "llm_tier_mapping_resolved",
        profile=profile,
        lite_variant=lite_variant,
        pro_model=mapping["pro"],
        flash_model=mapping["flash"],
        flash_lite_model=mapping["flash_lite"],
    )


def _try_read_tier_profile() -> tuple[str | None, str]:
    """Возвращает (profile, lite_variant).

    profile — строка или None (при холодном кэше).
    lite_variant — "2_5" или "3_1" (default "3_1" если не задан).
    """

    try:
        from videomaker.services.runtime_settings_store import (
            get_cached_performance_settings,
        )

        snapshot = get_cached_performance_settings()
        if snapshot is None:
            return None, "3_1"
        variant = getattr(snapshot, "llm_lite_variant", "3_1")
        return snapshot.llm_tier_profile, variant
    except Exception:
        return None, "3_1"
