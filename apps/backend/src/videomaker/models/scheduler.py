"""Publer scheduler ORM models.

Таблицы шедулера Publer-постов:

* ``AccountProfileRow`` (``account_profiles``) — профиль Publer-аккаунта
  (язык, тон, ЦА, дефолтные хештеги, баннед-слова) — контекст для
  caption_generator.
* ``CaptionPresetRow`` (``caption_presets``) — текстовые пресеты,
  добавляемые в начало (prepend) или конец (append) сгенерированного
  caption. Глобальные (account_id IS NULL) либо scoped к одному аккаунту.
* ``ScheduleCampaignRow`` (``schedule_campaigns``) — группа запланированных
  публикаций: источник + назначения + расписание.
* ``ScheduleAssignmentRow`` (``schedule_assignments``) — одна публикация:
  (reel_artifact, account) → дата/время + готовый caption.

Только ORM. Pydantic DTO и бизнес-логика живут в ``services/publer``.
"""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from videomaker.core.db import Base
from videomaker.models.job_constants import utc_now as _utc_now


class PublerNetwork(StrEnum):
    instagram = "instagram"
    youtube = "youtube"


class AssignmentStatus(StrEnum):
    draft = "draft"
    queued = "queued"
    uploading = "uploading"
    scheduled = "scheduled"
    published = "published"
    failed = "failed"
    cancelled = "cancelled"


class CaptionPresetPosition(StrEnum):
    prepend = "prepend"
    append = "append"


class AccountProfileRow(Base):
    """Профиль Publer-аккаунта: язык/тон/ЦА/дефолтные хештеги.

    Используется caption_generator как контекст для уникального текста.
    Primary key — не autoincrement, а publer_account_id (24-hex string).
    """

    __tablename__ = "account_profiles"

    publer_account_id: Mapped[str] = mapped_column(String(24), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    network: Mapped[str] = mapped_column(String(32), nullable=False)

    language: Mapped[str] = mapped_column(String(8), nullable=False, default="ru")
    audience: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tone: Mapped[str] = mapped_column(Text, nullable=False, default="")
    default_hashtags_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    banned_words_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    cta_style: Mapped[str] = mapped_column(Text, nullable=False, default="")
    max_caption_length: Mapped[int] = mapped_column(Integer, nullable=False, default=2200)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now
    )


class CaptionPresetRow(Base):
    """Пресет текста, добавляемого в начало ИЛИ в конец сгенерированного caption.

    Может быть привязан к конкретному account_id (scope) или быть глобальным
    (account_id IS NULL). На один пост — применяется первый глобальный
    prepend + первый scoped prepend + generated + первый scoped append +
    первый глобальный append, если выбраны.
    """

    __tablename__ = "caption_presets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    position: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    account_id: Mapped[str | None] = mapped_column(
        String(24),
        ForeignKey("account_profiles.publer_account_id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now
    )


class ScheduleCampaignRow(Base):
    """Группа запланированных публикаций (источник + назначения + расписание)."""

    __tablename__ = "schedule_campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    tz: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Ho_Chi_Minh")
    time_of_day: Mapped[str] = mapped_column(String(8), nullable=False)
    dates_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now
    )


class ScheduleAssignmentRow(Base):
    """Одна публикация: (reel_artifact, account) → дата/время + готовый caption."""

    __tablename__ = "schedule_assignments"
    __table_args__ = (
        UniqueConstraint(
            "campaign_id",
            "reel_artifact_id",
            "publer_account_id",
            name="uq_assignment_campaign_reel_account",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("schedule_campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reel_artifact_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("artifacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    publer_account_id: Mapped[str] = mapped_column(
        String(24),
        ForeignKey("account_profiles.publer_account_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    network: Mapped[str] = mapped_column(String(32), nullable=False)

    title: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    caption: Mapped[str] = mapped_column(Text, nullable=False)
    hashtags_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    applied_preset_ids_json: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)

    scheduled_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=AssignmentStatus.draft.value, index=True
    )
    publer_media_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    publer_job_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    publer_post_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    publer_post_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now
    )
