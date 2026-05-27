"""/api/v1/files — выдача артефактов из artifacts-дерева с валидацией путей."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from videomaker.core.artifacts import ArtifactsManager

router = APIRouter(prefix="/files", tags=["files"])


def get_artifacts_manager() -> ArtifactsManager:
    return ArtifactsManager()


@router.get("/{job_id}/{kind}/{name}")
async def download_artifact(
    job_id: str,
    kind: str,
    name: str,
    artifacts: ArtifactsManager = Depends(get_artifacts_manager),
) -> FileResponse:
    try:
        path = artifacts.path_for(job_id, kind, name)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    if not path.exists() or not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"artifact not found: {kind}/{name}",
        )
    return FileResponse(path, filename=name)
