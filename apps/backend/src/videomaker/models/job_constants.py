"""Job-related constants, enums и конфиг-модели без зависимостей от ORM.

В этом модуле:

* Enum-константы — ``JobStatus``, ``JobStage``, ``FitMode``, ``SourceLanguage``,
  ``VisionProfile``, ``ArtifactKind``, ``SubtitleAnchor``, ``FontWeight``.
* Literal-алиасы — ``SubtitlePositionMode``, ``SubtitleWrapMode``.
* Конфиг-модель ``SubtitleStyleConfig`` (Pydantic) — хранится в JSON-полях
  ``jobs.subtitle_style_json`` и ``subtitle_style_presets.style_json``.
  Это, по сути, value-object, поэтому живёт рядом с enum'ами.
* Константа ``TARGET_LANGUAGE`` — целевой язык перевода рилсов.
* Утилита ``utc_now`` — used by all ORM-моделей как ``default`` для
  timezone-aware ``DateTime`` колонок. Держим здесь, чтобы
  ``models/job_orm.py`` и другие модели импортировали её без циклов.

Никаких SQLAlchemy/ORM зависимостей — только Pydantic + stdlib. Это позволяет
импортировать константы из любого места (alembic envs, CLI-скрипты, тесты)
без подтягивания тяжёлого ORM-стека.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


class JobStatus(StrEnum):
    pending = "pending"
    running = "running"
    done = "done"
    error = "error"
    cancelled = "cancelled"


class JobStage(StrEnum):
    ingest = "ingest"
    proxy_generate = "proxy_generate"
    transcribe = "transcribe"
    # `translate` клэшит с `str.translate` в mypy-анализе StrEnum — поле
    # остаётся обязательным (стадия pipeline), поэтому игнорируем.
    translate = "translate"  # type: ignore[assignment]
    silence_cut = "silence_cut"
    analyze = "analyze"
    render = "render"
    finalize = "finalize"
    done = "done"


class FitMode(StrEnum):
    fill = "fill"
    fit = "fit"


class SourceLanguage(StrEnum):
    auto = "auto"
    ru = "ru"
    en = "en"
    de = "de"
    es = "es"
    fr = "fr"
    it = "it"
    pt = "pt"
    zh = "zh"
    ja = "ja"
    ko = "ko"


TARGET_LANGUAGE = "ru"


class VisionProfile(StrEnum):
    """Профиль нарезки — определяет приоритеты re-rank и agent mask.

    * ``talking_head`` (default) — текущий сценарий: подкасты, интервью,
      говорящая голова. Приоритет у text-агентов (dramatic_irony, closure).
      При vision_enabled добавляется hard-gate face centering.
    * ``fashion`` — fashion/beauty показы. Низкий WPM, приоритет визуалу.
      Same-person clustering через face embeddings, multi-location склейки,
      composition anchor для плавных переходов.
    * ``travel`` — travel/adventure с минимумом слов. Ставка на визуальные
      события (scene_change, action detection).
    * ``screencast`` — tutorials/tech-демо. Cursor tracking, UI region zoom,
      text-heavy screens.
    * ``custom`` — пользовательская конфигурация (agent mask + weights
      задаются явно через `options`).
    """

    talking_head = "talking_head"
    fashion = "fashion"
    travel = "travel"
    screencast = "screencast"
    custom = "custom"


class ArtifactKind(StrEnum):
    transcript = "transcript"
    cleaned_transcript = "cleaned_transcript"
    reel_plan = "reel_plan"
    reel_output = "reel_output"
    audio_extract = "audio_extract"
    subtitles = "subtitles"
    log = "log"
    project_graph = "project_graph"
    proxy = "proxy"


class SubtitleAnchor(StrEnum):
    top = "top"
    # `center` клэшит с `str.center` — игнорируем, чтобы не ломать БД.
    center = "center"  # type: ignore[assignment]
    bottom = "bottom"


class FontWeight(StrEnum):
    regular = "regular"
    medium = "medium"
    bold = "bold"


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


#: Режим позиционирования субтитра. anchor — через anchor+offset (backward-compat),
#: free — через процентные координаты center-точки (free_x_pct/free_y_pct).
SubtitlePositionMode = Literal["anchor", "free"]

#: Режим разбиения транскрипта на субтитровые блоки.
#: chars — до N знаков в строке, max_lines строк в блоке;
#: sentence — 1 субтитр = 1 предложение (./!/?), разделено по max_lines строк;
#: word    — 1 субтитр = 1 слово (kinetic typography, max_lines=1 принудительно).
SubtitleWrapMode = Literal["chars", "sentence", "word"]


class SubtitleStyleConfig(BaseModel):
    """Полная конфигурация стиля субтитров. Сериализуется в `jobs.subtitle_style_json`
    и `subtitle_style_presets.style_json`.

    Все color-поля — hex `#RRGGBB`. Opacity всегда в процентах 0-100
    (100 = полностью непрозрачный).
    """

    model_config = ConfigDict(frozen=False, extra="forbid")

    # ---------- Позиционирование ----------
    anchor: SubtitleAnchor = SubtitleAnchor.bottom
    # Интерпретируется рендерером с учётом fit_mode:
    #   fill → смещение от выбранного anchor-края (0-300 px)
    #   fit  → смещение от границы видео-области внутрь letterbox (1-150 px)
    # При anchor=center и fit_mode=fill offset сдвигает текст от центра кадра.
    offset_px: int = Field(default=0, ge=0, le=300)

    position_mode: SubtitlePositionMode = "anchor"
    """Режим позиционирования. anchor — классика (anchor+offset_px), free —
    свободная точка в процентах от ширины/высоты кадра (drag-to-position).
    """
    free_x_pct: float = Field(default=50.0, ge=0.0, le=100.0)
    """Горизонтальный центр субтитра в % от ширины кадра. 0=левый край,
    100=правый. Используется только при ``position_mode='free'``."""
    free_y_pct: float = Field(default=85.0, ge=0.0, le=100.0)
    """Вертикальный центр субтитра в % от высоты кадра. 0=верх, 100=низ.
    Дефолт 85 = обычная позиция субтитра в нижней трети кадра."""
    clamp_to_safe_zone: bool = True
    """Если True — при position_mode='free' позиция подрезается так, чтобы
    текст не залез в Instagram safe zones (top=220px, bottom=440px,
    left=64px, right=144px для 9:16 1080x1920). Рендерер применяет clamp.
    """

    # ---------- Лайн-разбиение ----------
    max_lines: int = Field(default=2, ge=1, le=3)
    """Максимум строк в одном субтитровом блоке (1-3). 1 = одна строка,
    всё переносится на следующий блок; 3 = возможно 3 строки при длинной
    реплике. Default 2 — стандарт для Reels."""
    wrap_mode: SubtitleWrapMode = "chars"
    """Режим разбиения. chars — по ``max_chars_per_line`` + max_lines;
    sentence — один субтитр = одно предложение; word — одно слово за раз."""
    max_chars_per_line: int = Field(default=30, ge=10, le=60)
    """Максимум знаков на строку при wrap_mode='chars'. 30 — оптимум для
    9:16, читается без напряжения. Игнорируется при wrap_mode in {sentence, word}."""

    # ---------- Шрифт и цвет ----------
    font: str = Field(default="Arial", min_length=1, max_length=128)
    size: int = Field(default=64, ge=24, le=128)
    weight: FontWeight = FontWeight.bold
    italic: bool = False

    primary_color: str = Field(default="#FFFFFF")
    text_opacity: int = Field(default=100, ge=0, le=100)

    outline_width: float = Field(default=3.0, ge=0.0, le=8.0)
    outline_color: str = Field(default="#000000")

    shadow_width: float = Field(default=1.0, ge=0.0, le=6.0)
    shadow_color: str = Field(default="#000000")
    shadow_opacity: int = Field(default=100, ge=0, le=100)

    background: bool = False
    background_color: str = Field(default="#000000")
    background_opacity: int = Field(default=40, ge=0, le=100)
    background_padding: int = Field(default=8, ge=0, le=64)

    @field_validator("primary_color", "outline_color", "shadow_color", "background_color")
    @classmethod
    def _validate_hex(cls, value: str) -> str:
        if not _HEX_COLOR_RE.match(value):
            raise ValueError(f"color must be #RRGGBB hex, got {value!r}")
        return value.upper()


__all__ = [
    "TARGET_LANGUAGE",
    "ArtifactKind",
    "FitMode",
    "FontWeight",
    "JobStage",
    "JobStatus",
    "SourceLanguage",
    "SubtitleAnchor",
    "SubtitlePositionMode",
    "SubtitleStyleConfig",
    "SubtitleWrapMode",
    "VisionProfile",
    "utc_now",
]
