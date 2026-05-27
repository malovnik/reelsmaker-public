"""Job models — facade re-export для обратной совместимости.

Реальные модели разделены по concerns (Phase 5.4 refactor):

* ``models/job_constants.py`` — enum-константы (``JobStatus``, ``JobStage``,
  ``ArtifactKind``, ``FitMode``, ``SourceLanguage``, ``SubtitleAnchor``,
  ``FontWeight``, ``VisionProfile``), Literal-алиасы, ``TARGET_LANGUAGE``,
  конфиг ``SubtitleStyleConfig`` и утилита ``utc_now``.
* ``models/job_types.py`` — SQLAlchemy ``TypeDecorator``-ы
  (``_StrEnumColumn`` для StrEnum-колонок).
* ``models/job_orm.py`` — SQLAlchemy ORM (``Job``, ``Artifact``,
  ``PromptSetting``, ``RuntimeSettingRow``, ``SubtitleStylePresetRow``).
* ``models/job_dto.py`` — Pydantic DTO (``JobCreate``, ``JobRead``,
  ``JobUpdate``, ``JobProfileUpdate``, ``ArtifactRead``,
  ``ArtifactLikeUpdate``, ``SavedReelsRequest``, ``SavedReelsResponse``,
  ``SubtitleStylePresetCreate/Update/Read``).

Все существующие импорты ``from videomaker.models.job import X`` работают
без изменений — этот модуль просто переэкспортирует публичные символы.
"""

from __future__ import annotations

from videomaker.models.job_constants import (
    TARGET_LANGUAGE,
    ArtifactKind,
    FitMode,
    FontWeight,
    JobStage,
    JobStatus,
    SourceLanguage,
    SubtitleAnchor,
    SubtitlePositionMode,
    SubtitleStyleConfig,
    SubtitleWrapMode,
    VisionProfile,
    utc_now,
)
from videomaker.models.job_dto import (
    ArtifactLikeUpdate,
    ArtifactRead,
    JobCreate,
    JobProfileUpdate,
    JobRead,
    JobUpdate,
    SavedReelsRequest,
    SavedReelsResponse,
    SubtitleStylePresetCreate,
    SubtitleStylePresetRead,
    SubtitleStylePresetUpdate,
)
from videomaker.models.job_orm import (
    Artifact,
    Job,
    PromptSetting,
    RuntimeSettingRow,
    SubtitleStylePresetRow,
)
from videomaker.models.job_types import _StrEnumColumn

__all__ = [
    "TARGET_LANGUAGE",
    "Artifact",
    "ArtifactKind",
    "ArtifactLikeUpdate",
    "ArtifactRead",
    "FitMode",
    "FontWeight",
    "Job",
    "JobCreate",
    "JobProfileUpdate",
    "JobRead",
    "JobStage",
    "JobStatus",
    "JobUpdate",
    "PromptSetting",
    "RuntimeSettingRow",
    "SavedReelsRequest",
    "SavedReelsResponse",
    "SourceLanguage",
    "SubtitleAnchor",
    "SubtitlePositionMode",
    "SubtitleStyleConfig",
    "SubtitleStylePresetCreate",
    "SubtitleStylePresetRead",
    "SubtitleStylePresetRow",
    "SubtitleStylePresetUpdate",
    "SubtitleWrapMode",
    "VisionProfile",
    "_StrEnumColumn",
    "utc_now",
]
