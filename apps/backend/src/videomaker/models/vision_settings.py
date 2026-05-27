"""Runtime-tunable vision layer settings.

Хранится в той же `runtime_settings` таблице что и PerformanceSettings,
но отдельным namespace ключей (`vision_*`). Env-defaults из `core/config.py`
служат seed для первой записи.

Поля:
* `enabled` — главный kill switch. OFF = пайплайн байтово идентичен pre-vision.
* `frame_sample_rate_sec` — интервал между кадрами для агентов визуала
  (0.5-60s). 10s default даёт 180 кадров на 30-мин видео.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from videomaker.core.config import Settings
from videomaker.models.evidence import AgentName
from videomaker.models.job import VisionProfile

#: Hot-plug точка для выбора vision backend'а. Literal расширяется когда
#: добавляется новый провайдер (например, `"gemini_vision"`) и регистрируется
#: соответствующая фабрика в `services/vision/registry.py`. Сейчас единственный
#: поддерживаемый провайдер — локальная Moondream 2 GGUF.
VisionProvider = Literal["moondream_local"]


class VisionRuntimeSettings(BaseModel):
    """Per-installation runtime config для vision layer (Moondream 2 local)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    frame_sample_rate_sec: float = Field(default=10.0, ge=0.5, le=60.0)
    # Архитектурная подготовка под мульти-backend vision. Default —
    # `moondream_local` (текущее поведение). UI-переключатель намеренно
    # не добавляем пока нет второго провайдера.
    provider: VisionProvider = "moondream_local"

    @classmethod
    def from_settings(cls, settings: Settings) -> VisionRuntimeSettings:
        """Конструирует начальные значения из env (seed)."""
        return cls(
            enabled=settings.vision_enabled,
            frame_sample_rate_sec=settings.vision_frame_sample_rate_sec,
        )


ALL_AGENTS: tuple[AgentName, ...] = (
    "hook_hunter",
    "emotional_peak_finder",
    "humor_specialist",
    "dramatic_irony_scanner",
    "thesis_extractor",
    "motif_tracker",
)


class VisionProfileOverride(BaseModel):
    """Пользовательский override параметров конкретного профиля нарезки.

    Хранится в `runtime_settings` под ключом `vision_profile_override_<name>`.
    Отсутствие записи означает — используются hardcoded defaults из
    `services/profile_masks.py`.

    Инвариант: `story_weight + visual_weight == 1.0` (ProfileMask это жёстко
    требует). `enabled_agents` — непустой список из разрешённых имён.
    `dead_zone_norm ∈ (0, 0.5)`, `ema_alpha ∈ (0, 1]`,
    `rule_of_thirds_y_shift ∈ [0, 0.5)`.
    """

    model_config = ConfigDict(extra="forbid")

    enabled_agents: list[AgentName] = Field(min_length=1)
    story_weight: float = Field(ge=0.0, le=1.0)
    visual_weight: float = Field(ge=0.0, le=1.0)
    dead_zone_norm: float = Field(gt=0.0, lt=0.5)
    ema_alpha: float = Field(gt=0.0, le=1.0)
    rule_of_thirds_y_shift: float = Field(ge=0.0, lt=0.5)

    @model_validator(mode="after")
    def _weights_sum_to_one(self) -> VisionProfileOverride:
        total = self.story_weight + self.visual_weight
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                f"story_weight + visual_weight must sum to 1.0, got {total}"
            )
        # Дедуп агентов с сохранением порядка — пользователь может прислать
        # дубли через UI без умысла; не падаем, нормализуем.
        seen: set[str] = set()
        deduped: list[AgentName] = []
        for agent in self.enabled_agents:
            if agent in seen:
                continue
            seen.add(agent)
            deduped.append(agent)
        object.__setattr__(self, "enabled_agents", deduped)
        return self


class ProfileMaskRead(BaseModel):
    """DTO для UI — эффективная маска профиля (default + override)."""

    model_config = ConfigDict(extra="forbid")

    profile: VisionProfile
    enabled_agents: list[AgentName]
    story_weight: float
    visual_weight: float
    dead_zone_norm: float
    ema_alpha: float
    rule_of_thirds_y_shift: float
    is_customized: bool


__all__ = [
    "ALL_AGENTS",
    "ProfileMaskRead",
    "VisionProfileOverride",
    "VisionProvider",
    "VisionRuntimeSettings",
]
