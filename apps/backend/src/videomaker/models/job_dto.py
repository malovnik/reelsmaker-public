"""Pydantic DTO для job-домена.

Payload/response-модели, которые гуляют между FastAPI-роутами, сервисами
и фронтом:

* ``JobCreate`` / ``JobRead`` / ``JobUpdate`` / ``JobProfileUpdate``
* ``ArtifactRead`` / ``ArtifactLikeUpdate``
* ``SavedReelsRequest`` / ``SavedReelsResponse``
* ``SubtitleStylePresetCreate`` / ``...Update`` / ``...Read``

Здесь же — ``model_validator``-ы, которые подтягивают вложенные JSON-поля
из ORM в плоский API-слой (см. ``JobRead._hoist_timing_from_options``).

Импортирует ORM-ряды только для ``SubtitleStylePresetRead.from_row`` —
никаких раундовых зависимостей.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from videomaker.core.config import DEFAULT_TRANSCRIBER
from videomaker.models.job_constants import (
    ArtifactKind,
    JobStage,
    JobStatus,
    SubtitleStyleConfig,
    VisionProfile,
)
from videomaker.models.job_orm import SubtitleStylePresetRow


class JobCreate(BaseModel):
    # macOS → stable_ts_mlx (локальный), Win/Linux → deepgram (cloud).
    transcriber: str = Field(default=DEFAULT_TRANSCRIBER)
    llm_provider: str = Field(default="gemini")
    llm_model: str = Field(default="gemini-3.1-flash-lite-preview")
    target_aspect: str = Field(default="9:16")
    fit_mode: str = Field(default="fill")
    source_language: str = Field(default="auto")
    subtitle_style: SubtitleStyleConfig | None = None
    post_production_preset_id: int | None = None
    # Per-job overrides на выбранный пресет. Ключи: enable_intro,
    # enable_outro, enable_zoom, enable_loudnorm. Все default True
    # (если ключ отсутствует — поведение пресета сохраняется). False для
    # ключа = занулить соответствующее поле snapshot конфига.
    post_production_overrides: dict[str, bool] | None = None
    # Per-job proxy controls (v0.5)
    use_proxy: bool = True
    """Если False — pipeline работает напрямую с source видео (no proxy)."""
    use_source_for_render: bool = False
    """Если True — финальный render берёт source 4K (медленнее, max качество).
    По умолчанию render использует proxy (быстрее, 1080p — достаточно для 9:16)."""
    target_reel_count: int | None = Field(default=None, ge=3, le=225)
    """Override количества рилсов (3-225). None → auto по длительности.

    225 соответствует 5-часовому видео по формуле 12 рилсов на 20 мин с
    tolerance +45 (см. ``reels_composer._compute_target_range``).
    """
    force_reingest: bool = Field(default=False)
    """Если True — инвалидировать transcript cache и заново транскрибировать."""
    vision_profile: VisionProfile = Field(default=VisionProfile.talking_head)
    """Профиль нарезки. talking_head = default, текущее поведение."""
    custom_system_prompt: str | None = Field(default=None, max_length=8000)
    """Опциональный дополнительный системный промпт — добавляется в самое начало
    system-prompt всех LLM-вызовов этого job'а. Пусто/None → без изменений."""
    options: dict[str, Any] = Field(default_factory=dict)


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_filename: str
    display_name: str | None = None
    source_size_bytes: int
    source_duration_sec: float | None
    status: JobStatus
    current_stage: JobStage | None
    progress: int
    message: str | None
    error: str | None
    transcriber: str
    llm_provider: str
    llm_model: str
    target_aspect: str
    fit_mode: str
    source_language: str
    detected_language: str | None
    subtitle_style_json: dict[str, Any] | None = None
    post_production_preset_id: int | None = None
    post_production_config_json: dict[str, Any] | None = None
    target_reel_count: int | None = None
    force_reingest: bool = False
    vision_profile: VisionProfile = VisionProfile.talking_head
    custom_system_prompt: str | None = None
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None
    # Timing телеметрия из options — per-stage durations + total pipeline time.
    # Заполняется JobService._finalize_timings при mark_done / mark_error.
    stage_durations: dict[str, float] | None = None
    total_generation_sec: float | None = None
    # T2.4: средний composite_score рилсов job'а. Из analysis.stats,
    # прокидывается в Job.options при mark_done. Frontend DashboardHero
    # использует для агрегации avg_score через все завершённые jobs.
    avg_composite_score: float | None = None

    @model_validator(mode="before")
    @classmethod
    def _hoist_timing_from_options(cls, data: Any) -> Any:
        """Пробрасывает ``stage_durations`` / ``total_generation_sec`` из ``Job.options``.

        Pydantic with ``from_attributes=True`` не видит вложенные ключи JSON-колонки,
        поэтому достаём их явно, не добавляя `options` целиком в API-схему.
        """
        if hasattr(data, "options"):
            options = getattr(data, "options", None) or {}
            payload: dict[str, Any] = {}
            for field_name in cls.model_fields:
                if hasattr(data, field_name):
                    payload[field_name] = getattr(data, field_name)
            payload.setdefault("stage_durations", options.get("stage_durations"))
            payload.setdefault("total_generation_sec", options.get("total_generation_sec"))
            payload.setdefault("avg_composite_score", options.get("avg_composite_score"))
            return payload
        return data


class JobProfileUpdate(BaseModel):
    """Payload для PATCH /jobs/{id}/profile — смена профиля нарезки."""

    profile: VisionProfile


class SubtitleStylePresetCreate(BaseModel):
    """Payload для POST /settings/subtitle_presets."""

    name: str = Field(min_length=1, max_length=128)
    style: SubtitleStyleConfig
    is_default: bool = False


class SubtitleStylePresetUpdate(BaseModel):
    """Payload для PUT /settings/subtitle_presets/{id}."""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    style: SubtitleStyleConfig | None = None
    is_default: bool | None = None


class SubtitleStylePresetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    style: SubtitleStyleConfig
    is_builtin: bool
    is_default: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: SubtitleStylePresetRow) -> SubtitleStylePresetRead:
        return cls(
            id=row.id,
            name=row.name,
            style=SubtitleStyleConfig.model_validate(row.style_json),
            is_builtin=row.is_builtin,
            is_default=row.is_default,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class JobUpdate(BaseModel):
    status: JobStatus | None = None
    current_stage: JobStage | None = None
    progress: int | None = None
    message: str | None = None
    error: str | None = None
    source_duration_sec: float | None = None


class ArtifactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: str
    kind: ArtifactKind
    path: str
    meta: dict[str, Any]
    created_at: datetime


class ArtifactLikeUpdate(BaseModel):
    """PATCH payload для проставления оценки рилса (liked)."""

    model_config = ConfigDict(extra="forbid")

    liked: str = Field(..., pattern="^(none|like|dislike)$")


class SavedReelsRequest(BaseModel):
    """POST payload для копирования отобранных рилсов в ``saved/``."""

    model_config = ConfigDict(extra="forbid")

    reel_ids: list[int] = Field(..., min_length=1, max_length=500)


class SavedReelsResponse(BaseModel):
    saved_relative: str
    folder: str
    copied_files: int
    reels: list[dict[str, Any]]


__all__ = [
    "ArtifactLikeUpdate",
    "ArtifactRead",
    "JobCreate",
    "JobProfileUpdate",
    "JobRead",
    "JobUpdate",
    "SavedReelsRequest",
    "SavedReelsResponse",
    "SubtitleStylePresetCreate",
    "SubtitleStylePresetRead",
    "SubtitleStylePresetUpdate",
]
