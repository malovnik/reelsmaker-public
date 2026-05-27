"""Tier → model mapping resolver с runtime_settings override.

Kartoziya-пайплайн имеет три tier'а: ``pro`` / ``flash`` / ``flash_lite``.
Pipeline-матрица живёт в runtime_settings (``PerformanceSettings.llm_tier_profile``) —
пользователь выбирает из UI между ``fast`` и ``legacy`` без рестарта.

Жёсткий constraint: разрешены только Flash-Lite варианты. Любые более
дорогие Gemini-модели (Flash, Pro, non-lite preview) физически не
резолвятся этим модулем — профили balanced/quality удалены.

Cold-cache fallback критичен для расходов: если runtime_settings ещё не
загружены (первые 30с после старта сервера), fallback → ``fast`` профиль
(всё на Lite). Env-defaults не используются.
"""

from __future__ import annotations

from typing import Literal

from videomaker.core.config import Settings

LLMTier = Literal["pro", "flash", "flash_lite"]


_LITE_3_1 = "gemini-3.1-flash-lite-preview"
_LITE_2_5 = "gemini-2.5-flash-lite"


def _tier_profiles(lite_variant: str) -> dict[str, dict[LLMTier, str]]:
    """Формирует tier-матрицу на основе выбранного Lite-варианта.

    ``lite_variant`` — "2_5" или "3_1". Позволяет ``fast`` работать на
    одной из двух cheapest моделей (user choice через UI).
    """

    lite = _LITE_2_5 if lite_variant == "2_5" else _LITE_3_1
    return {
        "fast": {
            # Всё на выбранном Lite-варианте: самый дешёвый прогон.
            "pro": lite,
            "flash": lite,
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


def _resolve_tier_models(cfg: Settings) -> dict[LLMTier, str]:
    """Определяет mapping tier → модель с учётом runtime_settings override.

    Cold-cache fallback — критичный момент для расходов. Fallback идёт на
    ``fast`` профиль (все три tier на Lite). Env-defaults не используются:
    при рестарте сервера первый pipeline работает на cheapest-моделях,
    пока не прогрелся runtime_settings cache.

    Любое некорректное значение профиля (legacy строки из старой БД,
    нераспознанные ключи) коерсится к ``fast`` — гарантируется, что
    pipeline никогда не уйдёт за пределы Lite-вариантов.
    """

    # cfg принимается для совместимости с сигнатурой и будущих нужд;
    # сейчас mapping полностью определяется tier-profile из runtime settings.
    _ = cfg

    profile, lite_variant = _try_read_tier_profile()
    profiles = _tier_profiles(lite_variant)
    if profile is None:
        # Cold cache: безопасный all-Lite fallback.
        return profiles["fast"]
    if profile in profiles:
        return profiles[profile]
    # Нераспознанный профиль (например legacy "balanced"/"quality" из БД) —
    # безопасный fallback на fast.
    return profiles["fast"]


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
