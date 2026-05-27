"""SQLAlchemy ORM-модели job-домена.

Содержит таблицы:

* ``Job`` (``jobs``) — основная запись обработки видео.
* ``Artifact`` (``artifacts``) — файлы, которые pipeline выдаёт джобе
  (transcript, reel_plan, reel_output, ...).
* ``PromptSetting`` (``prompt_settings``) — версионированные LLM-промпты.
* ``RuntimeSettingRow`` (``runtime_settings``) — per-installation конфиг
  (PerformanceSettings, Vision, profile masks — каждое поле как JSON-строка).
* ``SubtitleStylePresetRow`` (``subtitle_style_presets``) — именованные
  пресеты стиля субтитров.

Только ORM-декларации и relationships. Pydantic DTO (``JobRead``,
``ArtifactRead`` и т.п.) лежат в ``models/job_dto.py``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from videomaker.core.db import Base
from videomaker.models.job_constants import (
    ArtifactKind,
    JobStage,
    JobStatus,
    VisionProfile,
    utc_now,
)
from videomaker.models.job_types import _StrEnumColumn


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    source_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    source_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    # Пользовательское имя пакета. None → UI показывает source_filename.
    # Нужен для тестирования разных pipeline-настроек на одном и том же видео.
    display_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    source_duration_sec: Mapped[float | None] = mapped_column(nullable=True)

    status: Mapped[JobStatus] = mapped_column(
        _StrEnumColumn(JobStatus, 16), nullable=False, default=JobStatus.pending, index=True
    )
    current_stage: Mapped[JobStage | None] = mapped_column(
        _StrEnumColumn(JobStage, 32), nullable=True
    )
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    transcriber: Mapped[str] = mapped_column(String(32), nullable=False)
    llm_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    llm_model: Mapped[str] = mapped_column(String(128), nullable=False)
    target_aspect: Mapped[str] = mapped_column(String(8), nullable=False, default="9:16")
    fit_mode: Mapped[str] = mapped_column(String(8), nullable=False, default="fill")
    source_language: Mapped[str] = mapped_column(String(16), nullable=False, default="auto")
    detected_language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    subtitle_style_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    post_production_preset_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("post_production_presets.id", ondelete="SET NULL"),
        nullable=True,
    )
    post_production_config_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    target_reel_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    """Пользовательский override количества рилсов (3-225). None → auto по длительности.

    225 соответствует 5-часовому видео на пределе формулы 12/20min + tolerance.
    """
    force_reingest: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    """Если True — инвалидировать transcript cache перед Stage 2 и заново STT.

    По умолчанию False (повторные прогоны того же файла используют кэш).
    """
    vision_profile: Mapped[VisionProfile] = mapped_column(
        _StrEnumColumn(VisionProfile, 24),
        nullable=False,
        default=VisionProfile.talking_head,
        server_default=VisionProfile.talking_head.value,
    )
    """Профиль нарезки — talking_head/fashion/travel/screencast/custom.

    Default talking_head сохраняет backward-совместимое поведение. Auto-detect
    (PHASE 2.2) может подсказать fashion/travel по низкому WPM + face coverage.
    """
    options: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    custom_system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Опциональный текст от пользователя, который прикрепляется в самое начало
    system-prompt всех LLM-вызовов job'а. NULL (и пустая строка) → без префикса,
    поведение не меняется. Задаётся в UploadWizard на главной странице.
    """

    project_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    """Опциональная привязка к ``projects.id`` — логическая группа джобов.

    NULL → job не входит в проект (backward-compat). При удалении проекта
    ссылка обнуляется (SET NULL), сами джобы не трогаем.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    artifacts: Mapped[list[Artifact]] = relationship(
        back_populates="job", cascade="all, delete-orphan", lazy="selectin"
    )


class Artifact(Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        Index("ix_artifacts_kind_created_at", "kind", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[ArtifactKind] = mapped_column(String(32), nullable=False)
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    #: T6.1 — 256-dim Gemini embedding лайкнутого рилса (hook-фраза → embedding).
    #: Заполняется при проставлении ``meta['liked'] == 'like'`` через
    #: ``canvas_embedder.embed_texts`` и используется preference_memory
    #: (cosine retrieval режим). None для нелайкнутых артефактов и для
    #: исторических лайков до T6.1 — caller делает fallback на legacy top-by-date.
    embedding_json: Mapped[list[float] | None] = mapped_column(
        JSON, nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    job: Mapped[Job] = relationship(back_populates="artifacts")


class PromptSetting(Base):
    __tablename__ = "prompt_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    default_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    """SHA-256 хеш ``DEFAULT_PROMPTS[key]`` на момент последнего сида.

    Используется ``prompt_store.seed_default_prompts`` для версионированной
    миграции: если дефолт в коде обновился, а DB-content всё ещё равен
    старому дефолту (пользователь не редактировал) — content обновляется
    автоматически. Иначе — edit сохраняется. NULL = legacy row до введения
    версионирования, трактуется как "не модифицирован".
    """
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    __table_args__ = (UniqueConstraint("key", name="uq_prompt_settings_key"),)


class RuntimeSettingRow(Base):
    """Per-installation runtime config (concurrency, proxy params, …).

    Хранит каждое поле `PerformanceSettings` как отдельную JSON-строку
    в `value_json`. UI вызывает PUT /settings/performance — сохраняется
    атомарно через bulk upsert.
    """

    __tablename__ = "runtime_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    __table_args__ = (UniqueConstraint("key", name="uq_runtime_settings_key"),)


class SubtitleStylePresetRow(Base):
    """Сохранённый именованный preset стиля сабов.

    `is_builtin=True` — системный пресет (не редактируется и не удаляется через API).
    `is_default=True` — используется при создании job если явно не указан preset_id.
    Ровно один пресет может быть default (гарантируется в subtitle_store).
    """

    __tablename__ = "subtitle_style_presets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    style_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    __table_args__ = (UniqueConstraint("name", name="uq_subtitle_style_presets_name"),)


__all__ = [
    "Artifact",
    "Job",
    "PromptSetting",
    "RuntimeSettingRow",
    "SubtitleStylePresetRow",
]
