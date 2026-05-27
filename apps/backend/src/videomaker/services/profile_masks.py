"""Per-profile agent masks + re-rank weights.

Определяет какие text-агенты Stage 5.3 запускать и как Story Doctor
взвешивает визуальные/текстовые сигналы на стадии 5.5 re-rank-а.

Инвариант:
* ``talking_head`` = текущее поведение (все 6 агентов + story_weight 0.7).
* Переключение профиля НЕ ломает пайплайн: visual evidence агент всегда
  запускается (независимо от mask), если ``vision_enabled=True``.
* Любой профиль с ``vision_disabled=True`` деградирует до talking_head
  поведения (визуальные веса игнорируются, text-agenтов запускается
  максимум).
* Любой профиль можно переопределить через `runtime_settings` (UI
  `/settings/profiles`) — override хранится как JSON под ключом
  `vision_profile_override_<profile>`. `reset_profile_override` удаляет
  запись, возвращая hardcoded default.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from videomaker.core.db import session_scope
from videomaker.core.logging import get_logger
from videomaker.models.evidence import AgentName, RankedEvidenceItem
from videomaker.models.job import RuntimeSettingRow, VisionProfile
from videomaker.models.vision_settings import (
    ProfileMaskRead,
    VisionProfileOverride,
)

log = get_logger(__name__)

# Все 6 text-агентов (соответствует `evidence.AgentName` Literal).
_ALL_AGENTS: tuple[AgentName, ...] = (
    "hook_hunter",
    "emotional_peak_finder",
    "humor_specialist",
    "dramatic_irony_scanner",
    "thesis_extractor",
    "motif_tracker",
)

# Агенты, которые бессмысленны при минимуме речи — работают только с текстом.
_TEXT_HEAVY_AGENTS: frozenset[AgentName] = frozenset(
    {
        "humor_specialist",  # шутки в речи
        "dramatic_irony_scanner",  # ironic contradictions в тексте
        "thesis_extractor",  # главные тезисы — нет речи, нет тезисов
    }
)


@dataclass(slots=True, frozen=True)
class CompositionTuning:
    """Профильный tuning параметров composition anchor в zoom_planner.

    Значения перекрывают module-level константы (DEAD_ZONE_NORM,
    EMA_ALPHA, RULE_OF_THIRDS_Y_SHIFT) — позволяют fashion профилю иметь
    более "sticky" anchor (плотнее держит композицию кадра при склейках),
    travel — ещё плавнее, talking_head — текущий баланс.
    """

    dead_zone_norm: float = 0.03
    ema_alpha: float = 0.3
    rule_of_thirds_y_shift: float = 1.0 / 6.0

    def __post_init__(self) -> None:
        if not 0.0 < self.dead_zone_norm < 0.5:
            raise ValueError(
                f"dead_zone_norm out of (0, 0.5): {self.dead_zone_norm}"
            )
        if not 0.0 < self.ema_alpha <= 1.0:
            raise ValueError(
                f"ema_alpha out of (0, 1]: {self.ema_alpha}"
            )
        if not 0.0 <= self.rule_of_thirds_y_shift < 0.5:
            raise ValueError(
                f"rule_of_thirds_y_shift out of [0, 0.5): "
                f"{self.rule_of_thirds_y_shift}"
            )


@dataclass(slots=True, frozen=True)
class ProfileMask:
    """Конфигурация для конкретного профиля."""

    profile: VisionProfile
    enabled_agents: tuple[AgentName, ...]
    story_weight: float  # вес text-based evidence в Story Doctor re-rank
    visual_weight: float  # вес visual evidence в Story Doctor re-rank
    composition: CompositionTuning = CompositionTuning()

    def __post_init__(self) -> None:
        if not 0.0 <= self.story_weight <= 1.0:
            raise ValueError(
                f"story_weight out of [0,1]: {self.story_weight}"
            )
        if not 0.0 <= self.visual_weight <= 1.0:
            raise ValueError(
                f"visual_weight out of [0,1]: {self.visual_weight}"
            )
        total = self.story_weight + self.visual_weight
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                f"story_weight + visual_weight must sum to 1.0, got {total}"
            )


_TALKING_HEAD = ProfileMask(
    profile=VisionProfile.talking_head,
    enabled_agents=_ALL_AGENTS,
    story_weight=0.7,
    visual_weight=0.3,
)

_FASHION = ProfileMask(
    profile=VisionProfile.fashion,
    enabled_agents=tuple(a for a in _ALL_AGENTS if a not in _TEXT_HEAVY_AGENTS),
    story_weight=0.2,
    visual_weight=0.8,
    # Fashion: жёсткая композиция, anchor залипает в одну точку → меньше
    # drift при многоплановых склейках.
    composition=CompositionTuning(
        dead_zone_norm=0.015,
        ema_alpha=0.18,
        rule_of_thirds_y_shift=0.2,
    ),
)

_TRAVEL = ProfileMask(
    profile=VisionProfile.travel,
    enabled_agents=tuple(a for a in _ALL_AGENTS if a not in _TEXT_HEAVY_AGENTS),
    story_weight=0.3,
    visual_weight=0.7,
    # Travel: максимальная плавность (панорамные планы) — низкий EMA.
    composition=CompositionTuning(
        dead_zone_norm=0.02,
        ema_alpha=0.15,
        rule_of_thirds_y_shift=1.0 / 6.0,
    ),
)

_SCREENCAST = ProfileMask(
    profile=VisionProfile.screencast,
    # Скринкасты обычно с пояснениями — text-агенты полезны, но без humor.
    enabled_agents=tuple(a for a in _ALL_AGENTS if a != "humor_specialist"),
    story_weight=0.5,
    visual_weight=0.5,
)

_CUSTOM = ProfileMask(
    profile=VisionProfile.custom,
    # Default идентичен talking_head; пользователь может override через options.
    enabled_agents=_ALL_AGENTS,
    story_weight=0.5,
    visual_weight=0.5,
)

_MASKS: dict[VisionProfile, ProfileMask] = {
    VisionProfile.talking_head: _TALKING_HEAD,
    VisionProfile.fashion: _FASHION,
    VisionProfile.travel: _TRAVEL,
    VisionProfile.screencast: _SCREENCAST,
    VisionProfile.custom: _CUSTOM,
}


def get_profile_mask(profile: VisionProfile) -> ProfileMask:
    """Возвращает hardcoded default ProfileMask для профиля.

    Для runtime-эффективной маски (с учётом пользовательского override)
    используй `get_effective_profile_mask`. Эта функция — для тестов и
    seed-defaults API.

    Raises ``KeyError`` если enum расширился без обновления _MASKS — это
    defensive программирование (не падаем молча на unknown профиле).
    """
    mask = _MASKS.get(profile)
    if mask is None:  # pragma: no cover — каждый enum обязан быть в _MASKS
        raise KeyError(f"no ProfileMask configured for {profile}")
    return mask


_OVERRIDE_KEY_PREFIX = "vision_profile_override_"
_OVERRIDE_TTL_SEC = 30.0
_override_cache: tuple[float, dict[VisionProfile, VisionProfileOverride]] | None = None


def _override_key(profile: VisionProfile) -> str:
    return f"{_OVERRIDE_KEY_PREFIX}{profile.value}"


async def _load_overrides() -> dict[VisionProfile, VisionProfileOverride]:
    """Читает все profile overrides из runtime_settings (cached 30s).

    Невалидные записи (неверный JSON, схема изменилась) пропускаются с
    warning — профиль в этом случае работает на hardcoded default.
    """
    global _override_cache
    if _override_cache is not None:
        cached_at, cached = _override_cache
        if time.monotonic() - cached_at < _OVERRIDE_TTL_SEC:
            return cached

    async with session_scope() as session:
        result = await session.execute(
            select(RuntimeSettingRow).where(
                RuntimeSettingRow.key.startswith(_OVERRIDE_KEY_PREFIX)
            )
        )
        rows = list(result.scalars().all())

    overrides: dict[VisionProfile, VisionProfileOverride] = {}
    for row in rows:
        profile_name = row.key[len(_OVERRIDE_KEY_PREFIX) :]
        try:
            profile = VisionProfile(profile_name)
        except ValueError:
            log.warning("profile_override_unknown_profile", key=row.key)
            continue
        try:
            data = json.loads(row.value_json)
            overrides[profile] = VisionProfileOverride.model_validate(data)
        except (json.JSONDecodeError, ValueError) as exc:
            log.warning(
                "profile_override_invalid", profile=profile_name, error=str(exc)
            )
            continue

    _override_cache = (time.monotonic(), overrides)
    return overrides


def _invalidate_override_cache() -> None:
    global _override_cache
    _override_cache = None


def _merge_override(base: ProfileMask, override: VisionProfileOverride) -> ProfileMask:
    return ProfileMask(
        profile=base.profile,
        enabled_agents=tuple(override.enabled_agents),
        story_weight=override.story_weight,
        visual_weight=override.visual_weight,
        composition=CompositionTuning(
            dead_zone_norm=override.dead_zone_norm,
            ema_alpha=override.ema_alpha,
            rule_of_thirds_y_shift=override.rule_of_thirds_y_shift,
        ),
    )


async def get_effective_profile_mask(profile: VisionProfile) -> ProfileMask:
    """Возвращает эффективную маску: override из БД поверх hardcoded default.

    Если override невалиден или отсутствует — используется hardcoded default.
    Используется pipeline'ом вместо `get_profile_mask`.
    """
    base = get_profile_mask(profile)
    overrides = await _load_overrides()
    override = overrides.get(profile)
    if override is None:
        return base
    return _merge_override(base, override)


async def list_effective_masks() -> list[ProfileMaskRead]:
    """Список всех профилей с эффективной маской + is_customized флаг (для UI)."""
    overrides = await _load_overrides()
    result: list[ProfileMaskRead] = []
    for profile in VisionProfile:
        base = get_profile_mask(profile)
        override = overrides.get(profile)
        effective = _merge_override(base, override) if override else base
        result.append(
            ProfileMaskRead(
                profile=profile,
                enabled_agents=list(effective.enabled_agents),
                story_weight=effective.story_weight,
                visual_weight=effective.visual_weight,
                dead_zone_norm=effective.composition.dead_zone_norm,
                ema_alpha=effective.composition.ema_alpha,
                rule_of_thirds_y_shift=effective.composition.rule_of_thirds_y_shift,
                is_customized=override is not None,
            )
        )
    return result


async def get_effective_mask_read(profile: VisionProfile) -> ProfileMaskRead:
    """Одна запись с is_customized флагом — для GET /settings/profiles/{p}."""
    overrides = await _load_overrides()
    base = get_profile_mask(profile)
    override = overrides.get(profile)
    effective = _merge_override(base, override) if override else base
    return ProfileMaskRead(
        profile=profile,
        enabled_agents=list(effective.enabled_agents),
        story_weight=effective.story_weight,
        visual_weight=effective.visual_weight,
        dead_zone_norm=effective.composition.dead_zone_norm,
        ema_alpha=effective.composition.ema_alpha,
        rule_of_thirds_y_shift=effective.composition.rule_of_thirds_y_shift,
        is_customized=override is not None,
    )


async def upsert_profile_override(
    profile: VisionProfile, payload: VisionProfileOverride
) -> ProfileMaskRead:
    """Сохраняет override для профиля (JSON в runtime_settings). Инвалидирует кэш."""
    row_values = {
        "key": _override_key(profile),
        "value_json": json.dumps(payload.model_dump()),
    }
    async with session_scope() as session:
        stmt = sqlite_insert(RuntimeSettingRow).values(**row_values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[RuntimeSettingRow.key],
            set_={"value_json": stmt.excluded.value_json},
        )
        await session.execute(stmt)
    _invalidate_override_cache()
    log.info("profile_override_upserted", profile=profile.value)
    return await get_effective_mask_read(profile)


async def reset_profile_override(profile: VisionProfile) -> ProfileMaskRead:
    """Удаляет override для профиля — возврат к hardcoded default."""
    async with session_scope() as session:
        await session.execute(
            delete(RuntimeSettingRow).where(
                RuntimeSettingRow.key == _override_key(profile)
            )
        )
    _invalidate_override_cache()
    log.info("profile_override_reset", profile=profile.value)
    return await get_effective_mask_read(profile)


def get_enabled_agents_for_profile(
    profile: VisionProfile, *, vision_enabled: bool
) -> list[AgentName]:
    """Возвращает список агентов для Stage 5.3 (hardcoded defaults).

    Для pipeline используй `get_enabled_agents_for_mask(mask, vision_enabled)`
    с pre-resolved ProfileMask (учитывает пользовательские override).
    """
    if not vision_enabled:
        return list(_ALL_AGENTS)
    return list(get_profile_mask(profile).enabled_agents)


def get_enabled_agents_for_mask(
    mask: ProfileMask, *, vision_enabled: bool
) -> list[AgentName]:
    """Вариант `get_enabled_agents_for_profile` поверх готовой маски.

    Инвариант: когда ``vision_enabled=False`` — возвращаем ВСЕ 6 агентов,
    потому что визуального агента не будет и нужно компенсировать полным
    text-анализом (иначе fashion без vision = ничего не находит).
    """
    if not vision_enabled:
        return list(_ALL_AGENTS)
    return list(mask.enabled_agents)


def apply_profile_weights(
    items: list[RankedEvidenceItem], mask: ProfileMask
) -> list[RankedEvidenceItem]:
    """Пере-взвешивает composite_score каждого evidence по профильным весам.

    Принцип:
    * Evidence с visual_caption/visual_tags считается "визуально подкреплённым"
      → множится на `1 + (visual_weight - 0.5)`. Baseline 0.5 = no-op.
    * Остальные (pure text) множатся на `1 + (story_weight - 0.5)`.
    * Score clamped в [0, 1]. Список возвращается пересортированным desc.

    Инвариант: для любого профиля с weights sum=1.0 метрики остаются в [0, 1],
    так как каждый вес ∈ [0, 1] → множитель ∈ [0.5, 1.5].
    """
    reweighted: list[RankedEvidenceItem] = []
    for item in items:
        has_visual = bool(item.visual_caption or item.visual_tags)
        weight = mask.visual_weight if has_visual else mask.story_weight
        multiplier = 1.0 + (weight - 0.5)
        new_score = max(0.0, min(1.0, item.composite_score * multiplier))
        reweighted.append(item.model_copy(update={"composite_score": new_score}))

    reweighted.sort(key=lambda i: i.composite_score, reverse=True)
    return reweighted


__all__ = [
    "ALL_AGENTS",
    "CompositionTuning",
    "ProfileMask",
    "apply_profile_weights",
    "get_effective_mask_read",
    "get_effective_profile_mask",
    "get_enabled_agents_for_mask",
    "get_enabled_agents_for_profile",
    "get_profile_mask",
    "list_effective_masks",
    "reset_profile_override",
    "upsert_profile_override",
]


ALL_AGENTS = _ALL_AGENTS
