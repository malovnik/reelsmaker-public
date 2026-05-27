"""Агрегатор всех API-роутеров."""

from __future__ import annotations

from fastapi import APIRouter

from videomaker.api.routes.files import router as files_router
from videomaker.api.routes.health import router as health_router
from videomaker.api.routes.jobs import router as jobs_router
from videomaker.api.routes.post_production import router as post_production_router
from videomaker.api.routes.projects import (
    jobs_router as projects_jobs_router,
)
from videomaker.api.routes.projects import (
    router as projects_router,
)
from videomaker.api.routes.proxies import router as proxies_router
from videomaker.api.routes.scheduler import router as scheduler_router
from videomaker.api.routes.settings import router as settings_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router)
api_router.include_router(jobs_router)
api_router.include_router(projects_jobs_router)
api_router.include_router(projects_router)
api_router.include_router(scheduler_router)
api_router.include_router(settings_router)
api_router.include_router(post_production_router)
api_router.include_router(proxies_router)
api_router.include_router(files_router)
