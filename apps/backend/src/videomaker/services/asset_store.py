"""Хранилище intro/outro видео-ассетов: ffprobe + SHA256-dedup + копия в data/.

Поток импорта:

1. Роут принимает upload, сохраняет его в `<assets_dir>/_pending/<uuid>.tmp`.
2. Вызывается `import_asset(temp_path, name, original_filename)`.
3. Функция:
   * Считает SHA256 (стрим 1 MiB чанками — не грузит весь файл в память).
   * Проверяет существующий row по hash → если есть, удаляет temp и
     возвращает существующий VideoAssetRow (idempotent повторный импорт).
   * Иначе вызывает ffprobe → MediaInfo, переименовывает temp в
     `<assets_dir>/<sha8>__<safe_name>.<ext>`, создаёт row в БД.
4. На любом сбое после копирования — удаляет файл, чтобы не оставить orphan.

Удаление:

* `delete_asset(id)` отказывается удалять, если на asset ссылается хотя бы
  один пресет (`AssetInUseError`). FK с ON DELETE RESTRICT в БД дублирует
  эту защиту на случай прямых SQL-операций.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from videomaker.core.config import get_settings
from videomaker.core.db import session_scope
from videomaker.core.logging import get_logger
from videomaker.models.post_production import (
    PostProductionPresetRow,
    VideoAssetRow,
)
from videomaker.services.media import FfmpegError, probe

log = get_logger(__name__)

_HASH_CHUNK_BYTES = 1024 * 1024  # 1 MiB
_SAFE_NAME_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")


class AssetStoreError(RuntimeError):
    """Базовый exception модуля."""


class AssetNotFoundError(LookupError):
    pass


class AssetInUseError(AssetStoreError):
    """Удаление невозможно — asset связан с одним или несколькими пресетами."""

    def __init__(self, asset_id: int, preset_ids: list[int]) -> None:
        self.asset_id = asset_id
        self.preset_ids = preset_ids
        super().__init__(
            f"asset {asset_id} is referenced by presets {preset_ids}; "
            "remove the references first"
        )


class AssetValidationError(AssetStoreError):
    """ffprobe не смог распознать файл, либо отсутствует видеопоток."""


async def list_assets() -> list[VideoAssetRow]:
    async with session_scope() as session:
        result = await session.execute(
            select(VideoAssetRow).order_by(VideoAssetRow.created_at.desc())
        )
        return list(result.scalars().all())


async def get_asset(asset_id: int) -> VideoAssetRow:
    async with session_scope() as session:
        row = await session.get(VideoAssetRow, asset_id)
        if row is None:
            raise AssetNotFoundError(f"asset {asset_id} not found")
        return row


async def get_asset_by_hash(file_hash: str) -> VideoAssetRow | None:
    async with session_scope() as session:
        result = await session.execute(
            select(VideoAssetRow).where(VideoAssetRow.file_hash == file_hash)
        )
        return result.scalar_one_or_none()


async def import_asset(
    *,
    temp_path: Path,
    name: str,
    original_filename: str,
) -> tuple[VideoAssetRow, bool]:
    """Импортирует временный файл как VideoAsset.

    Returns:
        (row, created) — `created=True` если новая запись, `False` если
        дубликат по SHA256 (temp_path удалён, возвращён существующий row).

    Raises:
        AssetValidationError: ffprobe не смог распарсить файл.
        AssetStoreError: файловые операции или БД упали.
    """

    if not temp_path.exists():
        raise AssetStoreError(f"temp file {temp_path} not found")

    name_clean = name.strip()
    if not name_clean:
        raise AssetValidationError("name must not be empty")

    file_size = temp_path.stat().st_size
    if file_size == 0:
        temp_path.unlink(missing_ok=True)
        raise AssetValidationError("uploaded file is empty")

    file_hash = await _hash_file_sha256(temp_path)
    existing = await get_asset_by_hash(file_hash)
    if existing is not None:
        # Идемпотент: тот же файл уже импортирован — возвращаем как есть.
        temp_path.unlink(missing_ok=True)
        log.info(
            "asset_import_dedup",
            asset_id=existing.id,
            file_hash=file_hash,
            name=existing.name,
        )
        return existing, False

    try:
        info = await probe(temp_path)
    except FfmpegError as exc:
        temp_path.unlink(missing_ok=True)
        raise AssetValidationError(
            f"ffprobe failed for {original_filename}: {exc}"
        ) from exc

    if info.width <= 0 or info.height <= 0:
        temp_path.unlink(missing_ok=True)
        raise AssetValidationError(
            f"invalid video dimensions: {info.width}x{info.height}"
        )
    if info.duration_sec <= 0:
        temp_path.unlink(missing_ok=True)
        raise AssetValidationError(
            f"invalid duration: {info.duration_sec}"
        )

    settings = get_settings()
    settings.ensure_directories()

    safe_name = _safe_filename(original_filename)
    final_path = settings.app_post_production_assets_dir / f"{file_hash[:16]}__{safe_name}"

    try:
        # На macOS rename внутри одной FS — atomic. Если final_path уже
        # существует (теоретически невозможно после dedup-check, но защита
        # от гонок), Path.replace перезатрёт.
        temp_path.replace(final_path)
    except OSError as exc:
        temp_path.unlink(missing_ok=True)
        raise AssetStoreError(
            f"failed to move temp file to {final_path}: {exc}"
        ) from exc

    row = VideoAssetRow(
        name=name_clean,
        file_path=str(final_path),
        file_hash=file_hash,
        file_size_bytes=file_size,
        duration_sec=info.duration_sec,
        width=info.width,
        height=info.height,
        fps=info.fps,
        video_codec=info.video_codec,
        audio_codec=info.audio_codec,
        sample_rate=info.sample_rate,
        channels=info.channels,
    )

    async with session_scope() as session:
        session.add(row)
        try:
            await session.flush()
        except IntegrityError as exc:
            # Гонка: пока считали hash, другой запрос уже вставил тот же файл.
            # Откатываем — оставляем тот файл, что есть на диске; повторный
            # вызов import_asset просто вернёт уже существующий row.
            await session.rollback()
            final_path.unlink(missing_ok=True)
            existing = await get_asset_by_hash(file_hash)
            if existing is not None:
                return existing, False
            raise AssetStoreError(
                f"concurrent import collision for hash {file_hash}: {exc}"
            ) from exc
        await session.refresh(row)

    log.info(
        "asset_imported",
        asset_id=row.id,
        name=row.name,
        size_mb=round(file_size / (1024 * 1024), 2),
        duration_sec=round(info.duration_sec, 2),
        resolution=f"{info.width}x{info.height}",
    )
    return row, True


async def delete_asset(asset_id: int) -> None:
    """Удаляет asset и его файл с диска.

    Raises:
        AssetNotFoundError: запись не найдена.
        AssetInUseError: на asset ссылается хотя бы один пресет.
    """

    async with session_scope() as session:
        row = await session.get(VideoAssetRow, asset_id)
        if row is None:
            raise AssetNotFoundError(f"asset {asset_id} not found")

        in_use = await session.execute(
            select(PostProductionPresetRow.id).where(
                (PostProductionPresetRow.intro_asset_id == asset_id)
                | (PostProductionPresetRow.outro_asset_id == asset_id)
            )
        )
        preset_ids = list(in_use.scalars().all())
        if preset_ids:
            raise AssetInUseError(asset_id=asset_id, preset_ids=preset_ids)

        file_path = Path(row.file_path)
        await session.delete(row)
        await session.flush()

    # Файл удаляем после коммита БД — если БД успешно зафиксировала
    # удаление, файл не должен оставаться orphan'ом.
    file_path.unlink(missing_ok=True)
    log.info("asset_deleted", asset_id=asset_id, path=str(file_path))


async def _hash_file_sha256(path: Path) -> str:
    """SHA256 потоковым чтением. Не грузит файл целиком в память."""

    import asyncio

    def _compute() -> str:
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            while chunk := fh.read(_HASH_CHUNK_BYTES):
                digest.update(chunk)
        return digest.hexdigest()

    return await asyncio.to_thread(_compute)


def _safe_filename(original: str) -> str:
    """Заменяет нелегальные символы на `_`, обрезает до 200 символов.

    `data/post_production_assets/<hash16>__<safe>` — общая длина под лимитом
    macOS HFS+/APFS (NAME_MAX=255).
    """

    base = Path(original).name
    cleaned = "".join(ch if ch in _SAFE_NAME_CHARS else "_" for ch in base)
    cleaned = cleaned.strip("_")
    if not cleaned:
        cleaned = "asset"
    return cleaned[:200]


__all__ = [
    "AssetInUseError",
    "AssetNotFoundError",
    "AssetStoreError",
    "AssetValidationError",
    "delete_asset",
    "get_asset",
    "get_asset_by_hash",
    "import_asset",
    "list_assets",
]
