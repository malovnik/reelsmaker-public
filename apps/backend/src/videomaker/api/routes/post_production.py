"""/api/v1/post_production — управление intro/outro assets и пресетами.

Endpoints:

* POST   /post_production/assets             multipart upload (file + name)
* GET    /post_production/assets             list всех assets (newest first)
* GET    /post_production/assets/{id}        один asset
* GET    /post_production/assets/{id}/thumbnail  PNG превью кадра
* DELETE /post_production/assets/{id}        удалить (запрет если используется)

* GET    /post_production/presets            list всех пресетов с подгрузкой assets
* POST   /post_production/presets            создать пресет
* GET    /post_production/presets/default    default пресет (или 204 если нет)
* GET    /post_production/presets/{id}       один пресет с assets
* PUT    /post_production/presets/{id}       обновить (PATCH-семантика)
* DELETE /post_production/presets/{id}       удалить (запрет если есть active jobs)
"""

from __future__ import annotations

import asyncio
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from pydantic import BaseModel

from videomaker.core.config import Settings, get_settings
from videomaker.core.logging import get_logger
from videomaker.models.post_production import (
    PostProductionPresetCreate,
    PostProductionPresetRead,
    PostProductionPresetUpdate,
    VideoAssetRead,
)
from videomaker.services import asset_store, post_production_store
from videomaker.services.asset_store import (
    AssetInUseError,
    AssetNotFoundError,
    AssetStoreError,
    AssetValidationError,
)
from videomaker.services.post_production_store import (
    AssetReferenceError,
    PresetConflictError,
    PresetInUseError,
    PresetNotFoundError,
)

router = APIRouter(prefix="/post_production", tags=["post_production"])
log = get_logger(__name__)


class AssetImportResponse(BaseModel):
    asset: VideoAssetRead
    created: bool  # False — был дубликат по SHA256


@router.get("/assets", response_model=list[VideoAssetRead])
async def list_assets() -> list[VideoAssetRead]:
    rows = await asset_store.list_assets()
    return [VideoAssetRead.model_validate(row) for row in rows]


@router.get("/assets/{asset_id}", response_model=VideoAssetRead)
async def get_asset(asset_id: int) -> VideoAssetRead:
    try:
        row = await asset_store.get_asset(asset_id)
    except AssetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return VideoAssetRead.model_validate(row)


@router.get("/assets/{asset_id}/thumbnail", response_class=Response)
async def get_asset_thumbnail(
    asset_id: int,
    time_sec: float = 0.0,
) -> Response:
    """Возвращает PNG кадр video-asset'а для превью в UI split-screen редактора.

    Кадр извлекается через ffmpeg image2pipe без сохранения на диск. time_sec
    clamping в [0, duration - 0.1] чтобы не упереться в конец файла.
    """

    try:
        row = await asset_store.get_asset(asset_id)
    except AssetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    clamped_ts = max(0.0, min(time_sec, max(0.0, row.duration_sec - 0.1)))
    argv = [
        "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "error",
        "-ss",
        f"{clamped_ts:.3f}",
        "-i",
        row.file_path,
        "-frames:v",
        "1",
        "-vf",
        "scale=480:-1",
        "-f",
        "image2pipe",
        "-vcodec",
        "png",
        "pipe:1",
    ]
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0 or not stdout:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                f"ffmpeg thumbnail failed: "
                f"{stderr.decode('utf-8', errors='replace')[:200]}"
            ),
        )
    return Response(content=stdout, media_type="image/png")


@router.post(
    "/assets",
    response_model=AssetImportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_asset(
    file: UploadFile = File(..., description="Видео-ассет (intro/outro)"),
    name: str = Form(..., description="Отображаемое имя ассета"),
    settings: Settings = Depends(get_settings),
) -> AssetImportResponse:
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="file.filename is empty",
        )
    if not name.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="name must not be empty",
        )

    settings.ensure_directories()
    temp_dir = settings.app_post_production_assets_dir / "_pending"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / f"{uuid.uuid4().hex}.tmp"

    try:
        await _save_upload(file, temp_path, settings.max_asset_size_bytes)
        row, created = await asset_store.import_asset(
            temp_path=temp_path,
            name=name,
            original_filename=file.filename,
        )
    except AssetValidationError as exc:
        temp_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except AssetStoreError as exc:
        temp_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc

    return AssetImportResponse(
        asset=VideoAssetRead.model_validate(row), created=created
    )


@router.delete("/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(asset_id: int) -> Response:
    try:
        await asset_store.delete_asset(asset_id)
    except AssetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except AssetInUseError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": str(exc),
                "preset_ids": exc.preset_ids,
            },
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/presets", response_model=list[PostProductionPresetRead])
async def list_presets() -> list[PostProductionPresetRead]:
    tuples = await post_production_store.list_presets()
    return [
        post_production_store.to_read_dto(preset, intro, outro, companion)
        for preset, intro, outro, companion in tuples
    ]


@router.get("/presets/default", response_model=PostProductionPresetRead | None)
async def get_default_preset() -> PostProductionPresetRead | None:
    row = await post_production_store.get_default_preset()
    if row is None:
        return None
    _, intro, outro, companion = await post_production_store.get_preset_with_assets(row.id)
    return post_production_store.to_read_dto(row, intro, outro, companion)


@router.get("/presets/{preset_id}", response_model=PostProductionPresetRead)
async def get_preset(preset_id: int) -> PostProductionPresetRead:
    try:
        row, intro, outro, companion = await post_production_store.get_preset_with_assets(preset_id)
    except PresetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return post_production_store.to_read_dto(row, intro, outro, companion)


@router.post(
    "/presets",
    response_model=PostProductionPresetRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_preset(payload: PostProductionPresetCreate) -> PostProductionPresetRead:
    try:
        row = await post_production_store.create_preset(payload)
    except AssetReferenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except PresetConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc

    _, intro, outro, companion = await post_production_store.get_preset_with_assets(row.id)
    return post_production_store.to_read_dto(row, intro, outro, companion)


@router.put("/presets/{preset_id}", response_model=PostProductionPresetRead)
async def update_preset(
    preset_id: int, payload: PostProductionPresetUpdate
) -> PostProductionPresetRead:
    try:
        row = await post_production_store.update_preset(preset_id, payload)
    except PresetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except AssetReferenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except PresetConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc

    _, intro, outro, companion = await post_production_store.get_preset_with_assets(row.id)
    return post_production_store.to_read_dto(row, intro, outro, companion)


@router.delete("/presets/{preset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_preset(preset_id: int) -> Response:
    try:
        await post_production_store.delete_preset(preset_id)
    except PresetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except PresetInUseError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": str(exc),
                "active_job_ids": exc.job_ids,
            },
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _save_upload(file: UploadFile, target: Path, max_bytes: int) -> int:
    """Сохраняет UploadFile в `target`, проверяя лимит размера.

    Дубликат паттерна из routes/jobs.py — оставлен здесь чтобы не делать
    cross-import служебных хелперов.
    """

    total = 0
    chunk_size = 1024 * 1024
    with target.open("wb") as fh:
        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                fh.close()
                target.unlink(missing_ok=True)
                shutil.rmtree(target.parent, ignore_errors=True)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"upload exceeds {max_bytes} bytes",
                )
            fh.write(chunk)
    return total
