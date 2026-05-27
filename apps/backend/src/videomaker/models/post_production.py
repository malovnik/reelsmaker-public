"""Модели пост-продакшена: видео-ассеты (intro/outro) + пресеты эффектов.

Архитектура:
* `VideoAsset` — файл в `data/post_production_assets/`, импортированный
  пользователем (intro/outro). Хранит ffprobe-метаданные + SHA256-хэш для
  дедупликации (тот же файл не копируется дважды).
* `PostProductionPreset` — именованный конфиг финальной обработки рилса:
  intro/outro asset_id, audio loudnorm, zoom-эффекты по плану/частоте.
* В `Job` сохраняется snapshot конфига (`post_production_config_json`) —
  при повторном рендере используется именно та конфигурация, даже если
  пресет в БД был изменён или удалён.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from videomaker.core.db import Base
from videomaker.models.job import utc_now

# Split-screen panel fit modes — независимо применяются к каждой панели
# (main и companion). "manual" — старое "custom": юзер руками задаёт transform.
SplitScreenPanelFitMode = Literal["fill", "fit", "manual"]


class SplitScreenTransform(BaseModel):
    """Transform одного слоя split-screen: позиция (верхний-левый угол) и размеры
    области в процентах от canvas'а 1080×1920. Используется только когда
    соответствующий panel fit_mode == 'manual'.
    """

    model_config = ConfigDict(extra="forbid")

    x_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    y_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    width_pct: float = Field(default=100.0, ge=5.0, le=100.0)
    height_pct: float = Field(default=50.0, ge=5.0, le=100.0)


class SplitScreenConfig(BaseModel):
    """Конфигурация вертикального split-screen 9:16. Верх — рилс из pipeline,
    низ — companion из пресета. Companion loop'ится если короче, обрезается если
    длиннее. Audio — только с рилса.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    companion_path: str | None = None
    # Default "fit" (letterbox) — matches SplitScreenPreviewEditor object-fit:contain.
    # Fix 2026-04-22: editor показывает source как есть с чёрными полосами,
    # а render при "fill" делал cover-crop → лицо zoomed, editor ≠ render.
    # "fit" даёт editor=render 1:1. Юзер может явно переключить на "fill" если
    # хочет cover-crop или "manual" если нужен нестандартный scale.
    main_fit_mode: SplitScreenPanelFitMode = "fit"
    companion_fit_mode: SplitScreenPanelFitMode = "fit"
    split_ratio: float = Field(default=50.0, ge=20.0, le=80.0)
    main_transform: SplitScreenTransform = Field(
        default_factory=lambda: SplitScreenTransform(
            x_pct=0.0, y_pct=0.0, width_pct=100.0, height_pct=50.0
        )
    )
    companion_transform: SplitScreenTransform = Field(
        default_factory=lambda: SplitScreenTransform(
            x_pct=0.0, y_pct=50.0, width_pct=100.0, height_pct=50.0
        )
    )


class VideoAssetRow(Base):
    """Импортированный видеоасет (intro / outro). Файл скопирован в
    `data/post_production_assets/` под именем `<id>__<original_name>`.

    SHA256-хэш гарантирует дедупликацию: при попытке импорта файла с
    идентичным содержимым возвращается существующий asset.
    """

    __tablename__ = "video_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)

    duration_sec: Mapped[float] = mapped_column(Float, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    fps: Mapped[float] = mapped_column(Float, nullable=False)
    video_codec: Mapped[str] = mapped_column(String(32), nullable=False)
    audio_codec: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sample_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channels: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    __table_args__ = (UniqueConstraint("file_hash", name="uq_video_assets_file_hash"),)


class PostProductionPresetRow(Base):
    """Пользовательский пресет финальной обработки рилса.

    Все builtin-поля (sw_default Boolean) намеренно отсутствуют — пользователь
    создаёт пресеты сам, никаких системных умолчаний.

    `is_default=True` подсказывает UI, какой пресет преселектить в dropdown.
    Гарантия "ровно один default" обеспечивается на уровне сервиса
    (`post_production_store`), не на уровне БД (SQLite не имеет partial
    unique index).
    """

    __tablename__ = "post_production_presets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    intro_asset_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("video_assets.id", ondelete="RESTRICT"),
        nullable=True,
    )
    outro_asset_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("video_assets.id", ondelete="RESTRICT"),
        nullable=True,
    )
    companion_asset_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("video_assets.id", ondelete="RESTRICT"),
        nullable=True,
    )
    split_screen_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    split_screen_main_fit_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="fill", server_default="fill"
    )
    split_screen_companion_fit_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="fill", server_default="fill"
    )
    split_screen_ratio: Mapped[float] = mapped_column(
        Float, nullable=False, default=50.0, server_default="50.0"
    )
    split_screen_transforms_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )

    audio_normalize_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    audio_target_lufs: Mapped[float] = mapped_column(
        Float, nullable=False, default=-14.0
    )

    zoom_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    zoom_close_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    zoom_medium_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    zoom_wide_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    zoom_apply_every_nth_cut: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )
    zoom_min_interval_sec: Mapped[float] = mapped_column(
        Float, nullable=False, default=5.0
    )
    zoom_long_segment_threshold_sec: Mapped[float] = mapped_column(
        Float, nullable=False, default=6.0
    )
    zoom_subsegment_min_sec: Mapped[float] = mapped_column(
        Float, nullable=False, default=4.0
    )
    zoom_subsegment_max_sec: Mapped[float] = mapped_column(
        Float, nullable=False, default=7.0
    )
    zoom_alternating_planes_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )

    # Video effects — add columns сюда по мере роста registry.
    bw_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    __table_args__ = (
        UniqueConstraint("name", name="uq_post_production_presets_name"),
    )


class VideoAssetRead(BaseModel):
    """DTO для GET /post_production/assets."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    file_path: str
    file_size_bytes: int
    duration_sec: float
    width: int
    height: int
    fps: float
    video_codec: str
    audio_codec: str | None
    sample_rate: int | None
    channels: int | None
    created_at: datetime


class PostProductionConfig(BaseModel):
    """Снимок конфигурации пост-продакшена.

    Используется в двух местах:
    * Поле `style` в Pydantic DTO для CRUD пресетов (без id/имени/timestamps).
    * Snapshot в `Job.post_production_config_json` — позволяет повторно
      отрендерить рилс с теми же настройками, даже если пресет был изменён.

    Поля `intro_path` / `outro_path` хранят абсолютные пути к файлам в
    `data/post_production_assets/`. Это критично: если пользователь удалит
    asset из библиотеки, существующие jobs продолжат работать, пока сами
    файлы не удалены вручную.
    """

    model_config = ConfigDict(extra="forbid")

    intro_path: str | None = None
    outro_path: str | None = None

    audio_normalize_enabled: bool = True
    audio_target_lufs: float = Field(default=-14.0, ge=-30.0, le=-5.0)

    zoom_enabled: bool = False
    zoom_close_percent: int = Field(default=30, ge=0, le=80)
    zoom_medium_percent: int = Field(default=15, ge=0, le=80)
    zoom_wide_percent: int = Field(default=0, ge=0, le=80)
    zoom_apply_every_nth_cut: int = Field(default=1, ge=1, le=20)
    zoom_min_interval_sec: float = Field(default=5.0, ge=0.0, le=60.0)
    zoom_long_segment_threshold_sec: float = Field(default=6.0, ge=2.0, le=30.0)
    zoom_subsegment_min_sec: float = Field(default=4.0, ge=1.0, le=30.0)
    zoom_subsegment_max_sec: float = Field(default=7.0, ge=1.0, le=30.0)
    zoom_alternating_planes_enabled: bool = True

    # Split-screen — вертикальный 9:16 реакшн-формат.
    # enabled=False → обычный рендер.
    split_screen: SplitScreenConfig = Field(default_factory=SplitScreenConfig)

    # Video effects (plugin-registered in services/video_effects/).
    # Per-effect boolean флаги; сам filter_chain строится через registry.
    bw_enabled: bool = False

    @model_validator(mode="after")
    def _validate_subsegment_range(self) -> PostProductionConfig:
        if self.zoom_subsegment_min_sec > self.zoom_subsegment_max_sec:
            raise ValueError(
                "zoom_subsegment_min_sec must be <= zoom_subsegment_max_sec"
            )
        return self


class PostProductionPresetCreate(BaseModel):
    """Payload для POST /post_production/presets."""

    name: str = Field(min_length=1, max_length=128)
    is_default: bool = False
    intro_asset_id: int | None = None
    outro_asset_id: int | None = None
    companion_asset_id: int | None = None
    config: PostProductionConfig = Field(default_factory=PostProductionConfig)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("name must not be empty after strip")
        return stripped


class PostProductionPresetUpdate(BaseModel):
    """Payload для PUT /post_production/presets/{id}.

    Все поля опциональны — обновляется только то, что передано (PATCH-семантика
    под видом PUT, как и для subtitle preset).
    """

    name: str | None = Field(default=None, min_length=1, max_length=128)
    is_default: bool | None = None
    intro_asset_id: int | None = None
    outro_asset_id: int | None = None
    companion_asset_id: int | None = None
    config: PostProductionConfig | None = None

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("name must not be empty after strip")
        return stripped


class PostProductionPresetRead(BaseModel):
    """DTO для GET /post_production/presets/{id}.

    Возвращает плоский конфиг (не вложенный) и опциональные read-only снимки
    привязанных assets для UI без дополнительного запроса.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    is_default: bool
    intro_asset_id: int | None
    outro_asset_id: int | None
    companion_asset_id: int | None
    intro_asset: VideoAssetRead | None
    outro_asset: VideoAssetRead | None
    companion_asset: VideoAssetRead | None
    config: PostProductionConfig
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(
        cls,
        row: PostProductionPresetRow,
        *,
        intro_asset: VideoAssetRow | None,
        outro_asset: VideoAssetRow | None,
        companion_asset: VideoAssetRow | None,
    ) -> PostProductionPresetRead:
        # Deserialize transforms from JSON, or use defaults if None
        transforms_raw = row.split_screen_transforms_json or {}
        main_transform = (
            SplitScreenTransform.model_validate(transforms_raw["main"])
            if "main" in transforms_raw
            else SplitScreenTransform(
                x_pct=0.0, y_pct=0.0, width_pct=100.0, height_pct=50.0
            )
        )
        companion_transform = (
            SplitScreenTransform.model_validate(transforms_raw["companion"])
            if "companion" in transforms_raw
            else SplitScreenTransform(
                x_pct=0.0, y_pct=50.0, width_pct=100.0, height_pct=50.0
            )
        )
        split_screen_cfg = SplitScreenConfig(
            enabled=row.split_screen_enabled,
            companion_path=companion_asset.file_path if companion_asset else None,
            main_fit_mode=row.split_screen_main_fit_mode,  # type: ignore[arg-type]
            companion_fit_mode=row.split_screen_companion_fit_mode,  # type: ignore[arg-type]
            split_ratio=row.split_screen_ratio,
            main_transform=main_transform,
            companion_transform=companion_transform,
        )
        cfg = PostProductionConfig(
            intro_path=intro_asset.file_path if intro_asset else None,
            outro_path=outro_asset.file_path if outro_asset else None,
            audio_normalize_enabled=row.audio_normalize_enabled,
            audio_target_lufs=row.audio_target_lufs,
            zoom_enabled=row.zoom_enabled,
            zoom_close_percent=row.zoom_close_percent,
            zoom_medium_percent=row.zoom_medium_percent,
            zoom_wide_percent=row.zoom_wide_percent,
            zoom_apply_every_nth_cut=row.zoom_apply_every_nth_cut,
            zoom_min_interval_sec=row.zoom_min_interval_sec,
            zoom_long_segment_threshold_sec=row.zoom_long_segment_threshold_sec,
            zoom_subsegment_min_sec=row.zoom_subsegment_min_sec,
            zoom_subsegment_max_sec=row.zoom_subsegment_max_sec,
            zoom_alternating_planes_enabled=row.zoom_alternating_planes_enabled,
            split_screen=split_screen_cfg,
            bw_enabled=row.bw_enabled,
        )
        return cls(
            id=row.id,
            name=row.name,
            is_default=row.is_default,
            intro_asset_id=row.intro_asset_id,
            outro_asset_id=row.outro_asset_id,
            companion_asset_id=row.companion_asset_id,
            intro_asset=(
                VideoAssetRead.model_validate(intro_asset) if intro_asset else None
            ),
            outro_asset=(
                VideoAssetRead.model_validate(outro_asset) if outro_asset else None
            ),
            companion_asset=(
                VideoAssetRead.model_validate(companion_asset)
                if companion_asset
                else None
            ),
            config=cfg,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


def config_to_row_kwargs(
    config: PostProductionConfig,
) -> dict[str, Any]:
    """Конвертирует Pydantic-конфиг в kwargs для конструктора SQLAlchemy-row.

    Поля `intro_path` / `outro_path` исключены — пути живут в snapshot'е
    (Job.post_production_config_json), а связь с ассетами в БД идёт через FK
    `intro_asset_id` / `outro_asset_id` (передаются отдельно).

    Transforms сохраняются как JSON blob только если они отличаются от дефолтов,
    иначе None (экономия места, sensible fallback при десериализации).
    """

    # Default transforms
    default_main = SplitScreenTransform(
        x_pct=0.0, y_pct=0.0, width_pct=100.0, height_pct=50.0
    )
    default_companion = SplitScreenTransform(
        x_pct=0.0, y_pct=50.0, width_pct=100.0, height_pct=50.0
    )

    # Serialize transforms only if they differ from defaults
    transforms_json: dict[str, Any] | None = None
    if (
        config.split_screen.main_transform != default_main
        or config.split_screen.companion_transform != default_companion
    ):
        transforms_json = {
            "main": config.split_screen.main_transform.model_dump(),
            "companion": config.split_screen.companion_transform.model_dump(),
        }

    return {
        "audio_normalize_enabled": config.audio_normalize_enabled,
        "audio_target_lufs": config.audio_target_lufs,
        "zoom_enabled": config.zoom_enabled,
        "zoom_close_percent": config.zoom_close_percent,
        "zoom_medium_percent": config.zoom_medium_percent,
        "zoom_wide_percent": config.zoom_wide_percent,
        "zoom_apply_every_nth_cut": config.zoom_apply_every_nth_cut,
        "zoom_min_interval_sec": config.zoom_min_interval_sec,
        "zoom_long_segment_threshold_sec": config.zoom_long_segment_threshold_sec,
        "zoom_subsegment_min_sec": config.zoom_subsegment_min_sec,
        "zoom_subsegment_max_sec": config.zoom_subsegment_max_sec,
        "zoom_alternating_planes_enabled": config.zoom_alternating_planes_enabled,
        "split_screen_enabled": config.split_screen.enabled,
        "split_screen_main_fit_mode": config.split_screen.main_fit_mode,
        "split_screen_companion_fit_mode": config.split_screen.companion_fit_mode,
        "split_screen_ratio": config.split_screen.split_ratio,
        "split_screen_transforms_json": transforms_json,
        "bw_enabled": config.bw_enabled,
    }
