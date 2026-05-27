"""FastAPI приложение videomaker. Lifespan адаптирован из universal-rag main.py:24-70."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import update

from videomaker import __version__
from videomaker.api.routes import api_router
from videomaker.core.config import get_settings
from videomaker.core.db import Base, dispose_engine, get_engine, get_sessionmaker
from videomaker.core.logging import configure_logging, get_logger
from videomaker.models.scheduler import AssignmentStatus, ScheduleAssignmentRow
from videomaker.services.font_scanner import ensure_cache_warm
from videomaker.services.jobs import get_job_service
from videomaker.services.prompt_store import seed_default_prompts
from videomaker.services.publer.worker import PublerWorker
from videomaker.services.subtitle_store import seed_builtin_if_needed


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    import asyncio
    import contextlib

    settings = get_settings()
    configure_logging(settings.app_log_level)
    log = get_logger(__name__)
    settings.ensure_directories()

    log.info(
        "startup",
        version=__version__,
        llm_providers=settings.available_llm_providers,
        transcribers=settings.available_transcribers,
        db_path=str(settings.app_db_path),
    )

    # Idempotent DDL bootstrap — добавляет новые таблицы (runtime_settings и пр.)
    # без миграций. CREATE TABLE IF NOT EXISTS под капотом.
    engine = get_engine()
    # Принудительный импорт всех модулей с моделями, чтобы Base.metadata
    # содержала все таблицы перед create_all.
    from videomaker.models import job, post_production, scheduler  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    seed_result = await seed_default_prompts()
    if seed_result.added or seed_result.migrated or seed_result.preserved_user_edits:
        log.info(
            "default_prompts_ready",
            added=seed_result.added,
            migrated=seed_result.migrated,
            preserved_user_edits=seed_result.preserved_user_edits,
        )

    subtitles_seeded = await seed_builtin_if_needed()
    if subtitles_seeded:
        log.info("default_subtitle_presets_ready", added=subtitles_seeded)

    # Применяем сохранённые в UI API-ключи на singleton Settings, чтобы все
    # читатели settings.<key> видели runtime-значение (а не только .env).
    from videomaker.services.api_keys_store import apply_api_keys_to_settings

    await apply_api_keys_to_settings(settings)

    # Прогрев кеша шрифтов — 6 секунд system_profiler в фоне, не
    # блокирует uvicorn startup. Пользователь получит полный список
    # при втором открытии страницы, первый запрос — fallback из SYSTEM_FONTS.
    fonts_warmup_task = asyncio.create_task(
        ensure_cache_warm(settings.app_fonts_cache_path),
        name="fonts_cache_warmup",
    )

    service = get_job_service()
    stale_count = await service.reset_stale_running_jobs()
    if stale_count:
        log.warning("stale_jobs_reset_on_startup", count=stale_count)

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as db:
        result = await db.execute(
            update(ScheduleAssignmentRow)
            .where(ScheduleAssignmentRow.status == AssignmentStatus.uploading.value)
            .values(status=AssignmentStatus.queued.value)
        )
        await db.commit()
        rowcount = getattr(result, "rowcount", 0) or 0
        if rowcount:
            log.info("publer_uploading_reset", count=rowcount)

    publer_worker = PublerWorker(settings)
    await publer_worker.start()

    try:
        yield
    finally:
        await publer_worker.stop()
        if not fonts_warmup_task.done():
            fonts_warmup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await fonts_warmup_task
        await service.flush_all()
        await dispose_engine()
        log.info("shutdown_complete")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="videomaker",
        version=__version__,
        description="Локальный нарезчик длинных видео на рилсы через multi-pass LLM.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Type", "Cache-Control"],
    )
    app.include_router(api_router)

    @app.get("/", tags=["root"])
    async def root() -> dict[str, str]:
        return {
            "name": "videomaker",
            "version": __version__,
            "docs": "/docs",
            "health": "/api/v1/health",
        }

    return app


app = create_app()
