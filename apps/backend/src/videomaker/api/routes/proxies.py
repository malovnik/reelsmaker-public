"""/api/v1/proxies — управление кэшем proxy-файлов.

GET    /proxies              — список всех proxy в кэше (sha256, profile_id, size, mtime)
DELETE /proxies/cleanup      — LRU-cleanup, оставляет ≤ max_gb (default = settings.app_proxy_cache_max_gb)
DELETE /proxies/{sha256}     — удалить все proxy для конкретного source (любой profile_id)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from videomaker.core.config import Settings, get_settings
from videomaker.core.logging import get_logger
from videomaker.services.proxy import (
    ProxyEntry,
    cleanup_proxies,
    delete_proxy,
    list_proxies,
)

router = APIRouter(prefix="/proxies", tags=["proxies"])
log = get_logger(__name__)


class ProxyEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sha256: str
    profile_id: str
    path: str
    file_size_bytes: int
    file_size_mb: float
    mtime: float
    age_sec: float

    @classmethod
    def from_entry(cls, entry: ProxyEntry) -> ProxyEntryRead:
        return cls(
            sha256=entry.sha256,
            profile_id=entry.profile_id,
            path=str(entry.path),
            file_size_bytes=entry.file_size_bytes,
            file_size_mb=round(entry.file_size_bytes / (1024 * 1024), 2),
            mtime=entry.mtime,
            age_sec=round(entry.age_sec, 1),
        )


class ProxyListResponse(BaseModel):
    items: list[ProxyEntryRead]
    total_count: int
    total_size_bytes: int
    total_size_mb: float


class ProxyCleanupResponse(BaseModel):
    deleted: int
    freed_bytes: int
    freed_mb: float
    requested_max_gb: float


@router.get("", response_model=ProxyListResponse)
async def list_proxy_files(
    settings: Settings = Depends(get_settings),
) -> ProxyListResponse:
    entries = list_proxies(settings.app_proxies_dir)
    items = [ProxyEntryRead.from_entry(e) for e in entries]
    total_size = sum(e.file_size_bytes for e in entries)
    return ProxyListResponse(
        items=items,
        total_count=len(items),
        total_size_bytes=total_size,
        total_size_mb=round(total_size / (1024 * 1024), 2),
    )


@router.delete("/cleanup", response_model=ProxyCleanupResponse)
async def cleanup_proxy_cache(
    max_gb: float = Query(
        default=-1.0,
        description="Максимальный размер кэша в GB после очистки. -1 → берём из settings.",
    ),
    settings: Settings = Depends(get_settings),
) -> ProxyCleanupResponse:
    effective_max_gb = max_gb if max_gb >= 0 else float(settings.app_proxy_cache_max_gb)
    max_bytes = int(effective_max_gb * 1024 * 1024 * 1024)
    deleted, freed = cleanup_proxies(settings.app_proxies_dir, max_size_bytes=max_bytes)
    log.info(
        "proxy_cleanup_done",
        max_gb=effective_max_gb,
        deleted=deleted,
        freed_mb=round(freed / (1024 * 1024), 2),
    )
    return ProxyCleanupResponse(
        deleted=deleted,
        freed_bytes=freed,
        freed_mb=round(freed / (1024 * 1024), 2),
        requested_max_gb=effective_max_gb,
    )


@router.delete("/{sha256}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_proxy_for_source(
    sha256: str,
    settings: Settings = Depends(get_settings),
) -> None:
    try:
        deleted = delete_proxy(settings.app_proxies_dir, sha256)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="sha256 must be a hex string (8-64 chars, full or short hash)",
        ) from None
    if deleted == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no proxy found for sha256 prefix '{sha256[:12]}…'",
        )
    log.info("proxy_deleted_by_sha", sha256_prefix=sha256[:12], deleted=deleted)


# Field оставлен для расширения схем (rate-limit / pagination в будущем).
_ = Field
