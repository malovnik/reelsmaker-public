"""CRUD над таблицей `post_production_presets`.

Правила:
* Пользователь сам создаёт пресеты — никаких builtin/seed.
* Ровно один пресет может быть `is_default=True`. При установке нового default
  старый автоматически сбрасывается в одной транзакции (`_clear_default`).
* `intro_asset_id`/`outro_asset_id` валидируются: указанный asset должен
  существовать. Если нет — `AssetReferenceError`.
* `delete_preset` запрещён если пресет используется хоть одним job (через
  FK `jobs.post_production_preset_id` — но он SET NULL, так что технически
  удалить можно; запрет здесь — UX-защита, чтобы случайно не потерять
  ссылку для running/done jobs).
"""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from videomaker.core.db import session_scope
from videomaker.core.logging import get_logger
from videomaker.models.job import Job
from videomaker.models.post_production import (
    PostProductionConfig,
    PostProductionPresetCreate,
    PostProductionPresetRead,
    PostProductionPresetRow,
    PostProductionPresetUpdate,
    SplitScreenConfig,
    SplitScreenTransform,
    VideoAssetRow,
    config_to_row_kwargs,
)

log = get_logger(__name__)


class PresetNotFoundError(LookupError):
    pass


class PresetConflictError(RuntimeError):
    """Имя пресета уже занято."""


class DefaultPresetError(RuntimeError):
    """Попытка снять default-флаг с единственного default-пресета без замены."""


class AssetReferenceError(RuntimeError):
    """intro_asset_id, outro_asset_id или companion_asset_id указывает на несуществующий asset."""


class PresetInUseError(RuntimeError):
    """Удаление невозможно — на пресет ссылается активный job."""

    def __init__(self, preset_id: int, job_ids: list[str]) -> None:
        self.preset_id = preset_id
        self.job_ids = job_ids
        super().__init__(
            f"preset {preset_id} is referenced by jobs {job_ids}; "
            "wait for jobs to complete or remove references"
        )


async def list_presets() -> list[tuple[PostProductionPresetRow, VideoAssetRow | None, VideoAssetRow | None, VideoAssetRow | None]]:
    """Возвращает все пресеты вместе с подгруженными intro/outro/companion assets.

    Используется UI для рендера списка с превью в один запрос.
    """

    async with session_scope() as session:
        rows_result = await session.execute(
            select(PostProductionPresetRow).order_by(
                PostProductionPresetRow.is_default.desc(),
                PostProductionPresetRow.name.asc(),
            )
        )
        rows = list(rows_result.scalars().all())

        asset_ids: set[int] = set()
        for row in rows:
            if row.intro_asset_id is not None:
                asset_ids.add(row.intro_asset_id)
            if row.outro_asset_id is not None:
                asset_ids.add(row.outro_asset_id)
            if row.companion_asset_id is not None:
                asset_ids.add(row.companion_asset_id)

        assets_by_id: dict[int, VideoAssetRow] = {}
        if asset_ids:
            assets_result = await session.execute(
                select(VideoAssetRow).where(VideoAssetRow.id.in_(asset_ids))
            )
            assets_by_id = {a.id: a for a in assets_result.scalars()}

        return [
            (
                row,
                assets_by_id.get(row.intro_asset_id) if row.intro_asset_id else None,
                assets_by_id.get(row.outro_asset_id) if row.outro_asset_id else None,
                assets_by_id.get(row.companion_asset_id) if row.companion_asset_id else None,
            )
            for row in rows
        ]


async def get_preset_with_assets(
    preset_id: int,
) -> tuple[PostProductionPresetRow, VideoAssetRow | None, VideoAssetRow | None, VideoAssetRow | None]:
    async with session_scope() as session:
        row = await session.get(PostProductionPresetRow, preset_id)
        if row is None:
            raise PresetNotFoundError(f"preset {preset_id} not found")
        intro = (
            await session.get(VideoAssetRow, row.intro_asset_id)
            if row.intro_asset_id
            else None
        )
        outro = (
            await session.get(VideoAssetRow, row.outro_asset_id)
            if row.outro_asset_id
            else None
        )
        companion = (
            await session.get(VideoAssetRow, row.companion_asset_id)
            if row.companion_asset_id
            else None
        )
        return row, intro, outro, companion


async def get_preset(preset_id: int) -> PostProductionPresetRow:
    async with session_scope() as session:
        row = await session.get(PostProductionPresetRow, preset_id)
        if row is None:
            raise PresetNotFoundError(f"preset {preset_id} not found")
        return row


async def get_default_preset() -> PostProductionPresetRow | None:
    """Возвращает default-пресет, либо None если ни один не помечен."""

    async with session_scope() as session:
        result = await session.execute(
            select(PostProductionPresetRow).where(
                PostProductionPresetRow.is_default.is_(True)
            )
        )
        return result.scalar_one_or_none()


async def create_preset(
    payload: PostProductionPresetCreate,
) -> PostProductionPresetRow:
    async with session_scope() as session:
        await _validate_asset_refs(
            session,
            intro_id=payload.intro_asset_id,
            outro_id=payload.outro_asset_id,
            companion_id=payload.companion_asset_id,
        )

        if payload.is_default:
            await _clear_default(session)

        row = PostProductionPresetRow(
            name=payload.name,
            is_default=payload.is_default,
            intro_asset_id=payload.intro_asset_id,
            outro_asset_id=payload.outro_asset_id,
            companion_asset_id=payload.companion_asset_id,
            **config_to_row_kwargs(payload.config),
        )
        session.add(row)
        try:
            await session.flush()
        except IntegrityError as exc:
            raise PresetConflictError(
                f"preset name {payload.name!r} already exists"
            ) from exc
        await session.refresh(row)

    log.info(
        "post_production_preset_created",
        preset_id=row.id,
        name=row.name,
        is_default=row.is_default,
    )
    return row


async def update_preset(
    preset_id: int, payload: PostProductionPresetUpdate
) -> PostProductionPresetRow:
    async with session_scope() as session:
        row = await session.get(PostProductionPresetRow, preset_id)
        if row is None:
            raise PresetNotFoundError(f"preset {preset_id} not found")

        # Валидация ссылок на assets — даже если пользователь пытается
        # установить null, это валидно (отвязать). Проверяем только не-null.
        await _validate_asset_refs(
            session,
            intro_id=payload.intro_asset_id,
            outro_id=payload.outro_asset_id,
            companion_id=payload.companion_asset_id,
        )

        if payload.name is not None:
            row.name = payload.name

        if payload.intro_asset_id is not None or _explicit_null(
            payload, "intro_asset_id"
        ):
            row.intro_asset_id = payload.intro_asset_id
        if payload.outro_asset_id is not None or _explicit_null(
            payload, "outro_asset_id"
        ):
            row.outro_asset_id = payload.outro_asset_id
        if payload.companion_asset_id is not None or _explicit_null(
            payload, "companion_asset_id"
        ):
            row.companion_asset_id = payload.companion_asset_id

        if payload.config is not None:
            for key, value in config_to_row_kwargs(payload.config).items():
                setattr(row, key, value)

        if payload.is_default is True and not row.is_default:
            await _clear_default(session)
            row.is_default = True
        elif payload.is_default is False and row.is_default:
            # Пользователь явно снимает default — допускаем (default
            # становится «никто», что валидно: сервер тогда не подставит
            # пресет автоматически).
            row.is_default = False

        try:
            await session.flush()
        except IntegrityError as exc:
            raise PresetConflictError(
                f"preset name {payload.name!r} already exists"
            ) from exc
        await session.refresh(row)

    log.info("post_production_preset_updated", preset_id=row.id, name=row.name)
    return row


async def delete_preset(preset_id: int) -> None:
    async with session_scope() as session:
        row = await session.get(PostProductionPresetRow, preset_id)
        if row is None:
            raise PresetNotFoundError(f"preset {preset_id} not found")

        # FK на jobs — SET NULL, так что технически удаление безопасно. Но
        # активные jobs (running/pending) могут потерять конфиг — спросим
        # сначала, есть ли такие, и заблокируем.
        from videomaker.models.job import JobStatus

        active = await session.execute(
            select(Job.id).where(
                (Job.post_production_preset_id == preset_id)
                & (Job.status.in_([JobStatus.pending, JobStatus.running]))
            )
        )
        active_ids = list(active.scalars().all())
        if active_ids:
            raise PresetInUseError(preset_id=preset_id, job_ids=active_ids)

        await session.delete(row)

    log.info("post_production_preset_deleted", preset_id=preset_id)


def build_snapshot(
    preset: PostProductionPresetRow,
    intro: VideoAssetRow | None,
    outro: VideoAssetRow | None,
    companion: VideoAssetRow | None,
) -> PostProductionConfig:
    """Снимок конфига для записи в Job.post_production_config_json.

    Включает абсолютные пути к intro/outro/companion файлам — это критично для
    воспроизводимости: даже если пресет позже отредактируют или asset
    удалят из библиотеки, повторный рендер job возьмёт ту же конфигурацию.
    """

    # Десериализация split_screen transforms из JSON (если они есть).
    transforms_raw = preset.split_screen_transforms_json or {}
    default_main = SplitScreenTransform(
        x_pct=0.0, y_pct=0.0, width_pct=100.0, height_pct=50.0
    )
    default_companion = SplitScreenTransform(
        x_pct=0.0, y_pct=50.0, width_pct=100.0, height_pct=50.0
    )
    main_transform = (
        SplitScreenTransform.model_validate(transforms_raw["main"])
        if "main" in transforms_raw
        else default_main
    )
    companion_transform = (
        SplitScreenTransform.model_validate(transforms_raw["companion"])
        if "companion" in transforms_raw
        else default_companion
    )
    split_screen_cfg = SplitScreenConfig(
        enabled=preset.split_screen_enabled,
        companion_path=companion.file_path if companion else None,
        main_fit_mode=preset.split_screen_main_fit_mode,  # type: ignore[arg-type]
        companion_fit_mode=preset.split_screen_companion_fit_mode,  # type: ignore[arg-type]
        split_ratio=preset.split_screen_ratio,
        main_transform=main_transform,
        companion_transform=companion_transform,
    )

    return PostProductionConfig(
        intro_path=intro.file_path if intro else None,
        outro_path=outro.file_path if outro else None,
        audio_normalize_enabled=preset.audio_normalize_enabled,
        audio_target_lufs=preset.audio_target_lufs,
        zoom_enabled=preset.zoom_enabled,
        zoom_close_percent=preset.zoom_close_percent,
        zoom_medium_percent=preset.zoom_medium_percent,
        zoom_wide_percent=preset.zoom_wide_percent,
        zoom_apply_every_nth_cut=preset.zoom_apply_every_nth_cut,
        zoom_min_interval_sec=preset.zoom_min_interval_sec,
        zoom_long_segment_threshold_sec=preset.zoom_long_segment_threshold_sec,
        zoom_subsegment_min_sec=preset.zoom_subsegment_min_sec,
        zoom_subsegment_max_sec=preset.zoom_subsegment_max_sec,
        zoom_alternating_planes_enabled=preset.zoom_alternating_planes_enabled,
        split_screen=split_screen_cfg,
        bw_enabled=preset.bw_enabled,
    )


def to_read_dto(
    preset: PostProductionPresetRow,
    intro: VideoAssetRow | None,
    outro: VideoAssetRow | None,
    companion: VideoAssetRow | None,
) -> PostProductionPresetRead:
    return PostProductionPresetRead.from_row(
        preset, intro_asset=intro, outro_asset=outro, companion_asset=companion
    )


async def _validate_asset_refs(
    session: AsyncSession, *, intro_id: int | None, outro_id: int | None, companion_id: int | None = None
) -> None:
    ids_to_check = [aid for aid in (intro_id, outro_id, companion_id) if aid is not None]
    if not ids_to_check:
        return
    result = await session.execute(
        select(VideoAssetRow.id).where(VideoAssetRow.id.in_(ids_to_check))
    )
    found = set(result.scalars().all())
    missing = [aid for aid in ids_to_check if aid not in found]
    if missing:
        raise AssetReferenceError(
            f"video asset(s) not found: {missing}"
        )


async def _clear_default(session: AsyncSession) -> None:
    await session.execute(
        update(PostProductionPresetRow)
        .where(PostProductionPresetRow.is_default.is_(True))
        .values(is_default=False)
    )


def _explicit_null(payload: PostProductionPresetUpdate, field: str) -> bool:
    """True если поле было явно передано как null (а не отсутствует в payload).

    Pydantic v2 хранит "не передано" как Unset через `model_fields_set`.
    """

    return field in payload.model_fields_set and getattr(payload, field) is None


__all__ = [
    "AssetReferenceError",
    "DefaultPresetError",
    "PresetConflictError",
    "PresetInUseError",
    "PresetNotFoundError",
    "build_snapshot",
    "create_preset",
    "delete_preset",
    "get_default_preset",
    "get_preset",
    "get_preset_with_assets",
    "list_presets",
    "to_read_dto",
    "update_preset",
]
