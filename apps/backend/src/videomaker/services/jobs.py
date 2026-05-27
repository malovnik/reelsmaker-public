"""JobService: CRUD + throttled progress updates + event pub/sub для SSE.

Паттерн throttled writes адаптирован из
universal-rag/packages/backend/app/services/process.py:68-103.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import noload

from videomaker.core.db import session_scope
from videomaker.core.logging import get_logger
from videomaker.models.job import (
    Artifact,
    ArtifactKind,
    Job,
    JobCreate,
    JobStage,
    JobStatus,
    VisionProfile,
    utc_now,
)
from videomaker.services.job_event_bus import JobEventBus

log = get_logger(__name__)

FLUSH_INTERVAL_SEC = 3.0

# Re-export для обратной совместимости с внешним кодом,
# который может импортировать JobEventBus из этого модуля.
__all__ = ["JobEventBus", "JobService", "get_job_service"]


class JobService:
    """Управление жизненным циклом Job. Хранит локальный буфер для throttled updates."""

    def __init__(self, bus: JobEventBus | None = None) -> None:
        self.bus = bus or JobEventBus()
        self._pending: dict[str, dict[str, Any]] = {}
        self._last_flush: dict[str, float] = {}
        self._lock = asyncio.Lock()
        # Per-job in-memory stage timing telemetry.
        # `_stage_starts[job_id]`    — {stage_value: monotonic_started_at}
        # `_stage_durations[job_id]` — {stage_value: duration_sec}
        # `_current_stage[job_id]`   — last entered stage (для финализации durations)
        # `_pipeline_start[job_id]`  — monotonic старт пайплайна (для total_generation_sec)
        self._stage_starts: dict[str, dict[str, float]] = {}
        self._stage_durations: dict[str, dict[str, float]] = {}
        self._current_stage: dict[str, str] = {}
        self._pipeline_start: dict[str, float] = {}

    def _enter_stage(self, job_id: str, stage: JobStage) -> None:
        """Фиксирует начало stage + закрывает предыдущую, если она активна.

        Вызывается внутри `mark_stage` автоматически — pipeline-коду ничего
        знать не надо. Хранит timings в in-memory, флашит в DB при mark_done.
        """
        now = time.monotonic()
        stage_value = stage.value

        if job_id not in self._pipeline_start:
            self._pipeline_start[job_id] = now
            self._stage_starts[job_id] = {}
            self._stage_durations[job_id] = {}

        prev_stage = self._current_stage.get(job_id)
        if prev_stage and prev_stage != stage_value:
            prev_started = self._stage_starts[job_id].get(prev_stage)
            if prev_started is not None:
                # Накопительно — для стадий с несколькими заходами (на случай retry).
                prev_duration = now - prev_started
                accum = self._stage_durations[job_id].get(prev_stage, 0.0)
                self._stage_durations[job_id][prev_stage] = accum + prev_duration

        if prev_stage != stage_value:
            self._stage_starts[job_id][stage_value] = now
            self._current_stage[job_id] = stage_value

    async def _finalize_timings(self, job_id: str) -> dict[str, Any]:
        """Закрывает активную stage и возвращает итоговые durations + total.

        Результат вида ``{"stage_durations": {...}, "total_generation_sec": float}``
        — полностью готов для записи в ``Job.options`` и отдачи во фронт.
        """
        now = time.monotonic()
        durations = dict(self._stage_durations.get(job_id, {}))
        current = self._current_stage.get(job_id)
        if current:
            started = self._stage_starts.get(job_id, {}).get(current)
            if started is not None:
                durations[current] = durations.get(current, 0.0) + (now - started)

        pipeline_started = self._pipeline_start.get(job_id)
        total = (now - pipeline_started) if pipeline_started is not None else 0.0

        # Cleanup in-memory state.
        self._stage_starts.pop(job_id, None)
        self._stage_durations.pop(job_id, None)
        self._current_stage.pop(job_id, None)
        self._pipeline_start.pop(job_id, None)

        return {
            "stage_durations": {k: round(v, 2) for k, v in durations.items()},
            "total_generation_sec": round(total, 2),
        }

    @staticmethod
    def new_id() -> str:
        return str(uuid.uuid4())

    async def create(
        self,
        *,
        source_path: str,
        source_filename: str,
        source_size_bytes: int,
        payload: JobCreate,
        job_id: str | None = None,
        post_production_config_json: dict[str, Any] | None = None,
    ) -> Job:
        actual_id = job_id or self.new_id()
        subtitle_style_json = (
            payload.subtitle_style.model_dump(mode="json")
            if payload.subtitle_style is not None
            else None
        )
        async with session_scope() as session:
            job = Job(
                id=actual_id,
                source_path=source_path,
                source_filename=source_filename,
                source_size_bytes=source_size_bytes,
                status=JobStatus.pending,
                progress=0,
                transcriber=payload.transcriber,
                llm_provider=payload.llm_provider,
                llm_model=payload.llm_model,
                target_aspect=payload.target_aspect,
                fit_mode=payload.fit_mode,
                source_language=payload.source_language,
                subtitle_style_json=subtitle_style_json,
                post_production_preset_id=payload.post_production_preset_id,
                post_production_config_json=post_production_config_json,
                target_reel_count=payload.target_reel_count,
                force_reingest=payload.force_reingest,
                vision_profile=payload.vision_profile,
                custom_system_prompt=payload.custom_system_prompt,
                options=dict(payload.options),
            )
            session.add(job)
            await session.flush()
            await session.refresh(job)
        log.info("job_created", job_id=actual_id, filename=source_filename)
        await self.bus.publish(
            actual_id,
            {
                "stage": "created",
                "job_id": actual_id,
                "status": JobStatus.pending.value,
                "progress": 0,
            },
        )
        return job

    async def get(self, job_id: str) -> Job | None:
        async with session_scope() as session:
            return await session.get(Job, job_id)

    async def update_display_name(
        self, job_id: str, *, display_name: str | None
    ) -> Job | None:
        """Переименование пакета. Пустая строка / None → сброс к
        source_filename. Длина ≤256, уже провалидировано Pydantic-ом.
        """
        clean = display_name.strip() if display_name else None
        if clean == "":
            clean = None
        async with session_scope() as session:
            job = await session.get(Job, job_id)
            if job is None:
                return None
            job.display_name = clean
            await session.flush()
            await session.refresh(job)
        log.info("job_display_name_updated", job_id=job_id, display_name=clean)
        return job

    async def update_vision_profile(
        self, job_id: str, *, profile: VisionProfile
    ) -> Job | None:
        """Обновляет `Job.vision_profile`. Возвращает обновлённый Job или None
        если job не найден. Публикует SSE-событие о смене профиля.
        """
        async with session_scope() as session:
            job = await session.get(Job, job_id)
            if job is None:
                return None
            old_profile = job.vision_profile
            if old_profile == profile:
                return job
            job.vision_profile = profile
            await session.flush()
            await session.refresh(job)
        log.info(
            "job_vision_profile_updated",
            job_id=job_id,
            old_profile=old_profile.value,
            new_profile=profile.value,
        )
        await self.bus.publish(
            job_id,
            {
                "stage": "profile_changed",
                "old_profile": old_profile.value,
                "new_profile": profile.value,
            },
        )
        return job

    async def update_options(
        self, job_id: str, patch: dict[str, object]
    ) -> Job | None:
        """T11 — Patch-merge `Job.options` JSON dict.

        Значения из ``patch`` заменяют existing keys; значения ``None``
        **удаляют** key из options (так удобно снимать auto_config). Возвращает
        обновлённый Job или None если не найден.
        """
        async with session_scope() as session:
            job = await session.get(Job, job_id)
            if job is None:
                return None
            current = dict(job.options or {})
            for key, value in patch.items():
                if value is None:
                    current.pop(key, None)
                else:
                    current[key] = value
            job.options = current
            await session.flush()
            await session.refresh(job)
        log.info(
            "job_options_updated",
            job_id=job_id,
            keys=list(patch.keys()),
        )
        return job

    async def list_jobs(
        self,
        *,
        limit: int = 50,
        include_hidden: bool = False,
    ) -> list[Job]:
        """Возвращает список job'ов, по умолчанию без soft-deleted (``options.hidden``)."""
        # noload(Job.artifacts) — Job.artifacts relationship использует selectin
        # (удобно для detail-view), но в list_jobs артефакты не нужны: JobRead
        # их не сериализует. Явный noload экономит N+1 выборку на dashboard'е.
        async with session_scope() as session:
            result = await session.execute(
                select(Job)
                .options(noload(Job.artifacts))
                .order_by(Job.created_at.desc())
                .limit(limit)
            )
            jobs = list(result.scalars().all())
            if include_hidden:
                return jobs
            # options.hidden хранится в JSON-колонке options. Выносим в отдельную
            # индексированную колонку только если list_jobs станет узким местом —
            # при текущих <1000 jobs Python-side фильтрация дешевле миграции.
            # Пересмотреть при росте > 1000 jobs или при перфоманс-жалобах от user'а.
            return [j for j in jobs if not (j.options or {}).get("hidden")]

    async def mark_stage(
        self,
        job_id: str,
        *,
        stage: JobStage,
        progress: int,
        message: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Публикует stage-progress событие.

        `extra` — произвольные meta-поля, которые попадают в SSE событие
        (например ``cache_hit=True``, ``video_hash=...``). НЕ попадают в DB —
        только в SSE-поток для фронта.
        """
        self._enter_stage(job_id, stage)
        async with self._lock:
            self._pending[job_id] = {
                "current_stage": stage,
                "progress": max(0, min(100, progress)),
                "message": message,
                "status": JobStatus.running,
            }
        await self._maybe_flush(job_id)
        await self.bus.publish(
            job_id,
            {
                "stage": stage.value,
                "progress": max(0, min(100, progress)),
                "message": message,
                "status": JobStatus.running.value,
                **(extra or {}),
            },
        )

    async def mark_done(
        self,
        job_id: str,
        *,
        message: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        timings = await self._finalize_timings(job_id)
        async with self._lock:
            self._pending.pop(job_id, None)
            self._last_flush.pop(job_id, None)
        async with session_scope() as session:
            job = await session.get(Job, job_id)
            if job is None:
                raise ValueError(f"job {job_id} not found")
            job.status = JobStatus.done
            job.current_stage = JobStage.done
            job.progress = 100
            job.message = message
            job.finished_at = utc_now()
            _store_timings(job, timings)
        log.info(
            "job_done",
            job_id=job_id,
            total_sec=timings["total_generation_sec"],
        )
        await self.bus.publish(
            job_id,
            {
                "stage": "done",
                "progress": 100,
                "message": message,
                "status": JobStatus.done.value,
                "stage_durations": timings["stage_durations"],
                "total_generation_sec": timings["total_generation_sec"],
                **(extra or {}),
            },
        )

    async def mark_error(self, job_id: str, *, error: str) -> None:
        timings = await self._finalize_timings(job_id)
        async with self._lock:
            self._pending.pop(job_id, None)
            self._last_flush.pop(job_id, None)
        async with session_scope() as session:
            job = await session.get(Job, job_id)
            if job is None:
                raise ValueError(f"job {job_id} not found")
            job.status = JobStatus.error
            job.error = error
            job.finished_at = utc_now()
            _store_timings(job, timings)
        log.error("job_error", job_id=job_id, error=error)
        await self.bus.publish(
            job_id,
            {
                "stage": "error",
                "error": error,
                "status": JobStatus.error.value,
                "stage_durations": timings["stage_durations"],
                "total_generation_sec": timings["total_generation_sec"],
            },
        )

    async def mark_cancelled(
        self, job_id: str, *, message: str | None = None
    ) -> None:
        timings = await self._finalize_timings(job_id)
        async with self._lock:
            self._pending.pop(job_id, None)
            self._last_flush.pop(job_id, None)
        async with session_scope() as session:
            job = await session.get(Job, job_id)
            if job is None:
                raise ValueError(f"job {job_id} not found")
            job.status = JobStatus.cancelled
            job.message = message
            job.finished_at = utc_now()
            _store_timings(job, timings)
        log.info("job_cancelled", job_id=job_id)
        await self.bus.publish(
            job_id,
            {
                "stage": "cancelled",
                "message": message,
                "status": JobStatus.cancelled.value,
                "stage_durations": timings["stage_durations"],
                "total_generation_sec": timings["total_generation_sec"],
            },
        )

    async def _maybe_flush(self, job_id: str) -> None:
        now = time.monotonic()
        async with self._lock:
            last = self._last_flush.get(job_id, 0.0)
            if now - last < FLUSH_INTERVAL_SEC:
                return
            update = self._pending.pop(job_id, None)
            self._last_flush[job_id] = now
        if not update:
            return
        async with session_scope() as session:
            job = await session.get(Job, job_id)
            if job is None:
                return
            for key, value in update.items():
                setattr(job, key, value)

    async def flush_all(self) -> None:
        async with self._lock:
            updates = dict(self._pending)
            self._pending.clear()
        if not updates:
            return
        async with session_scope() as session:
            for job_id, values in updates.items():
                job = await session.get(Job, job_id)
                if job is None:
                    continue
                for key, value in values.items():
                    setattr(job, key, value)

    async def add_artifact(
        self,
        job_id: str,
        *,
        kind: ArtifactKind,
        path: str,
        meta: dict[str, Any] | None = None,
    ) -> Artifact:
        async with session_scope() as session:
            artifact = Artifact(
                job_id=job_id,
                kind=kind,
                path=path,
                meta=dict(meta or {}),
            )
            session.add(artifact)
            await session.flush()
            await session.refresh(artifact)
            return artifact

    async def get_artifact(self, job_id: str, artifact_id: int) -> Artifact | None:
        """Одиночный артефакт в контексте job. ``None`` если не найден / не принадлежит job."""
        async with session_scope() as session:
            artifact = await session.get(Artifact, artifact_id)
            if artifact is None or artifact.job_id != job_id:
                return None
            return artifact

    async def update_artifact_meta(
        self,
        job_id: str,
        artifact_id: int,
        *,
        patch: dict[str, Any],
    ) -> Artifact | None:
        """Мержит ``patch`` в ``Artifact.meta`` и возвращает обновлённую запись.

        Используется для pipeline-агнустичных пометок вроде ``liked`` (лайк рилса)
        без добавления отдельных колонок.
        """
        async with session_scope() as session:
            artifact = await session.get(Artifact, artifact_id)
            if artifact is None or artifact.job_id != job_id:
                return None
            merged = dict(artifact.meta or {})
            merged.update(patch)
            artifact.meta = merged
            await session.flush()
            await session.refresh(artifact)
            return artifact

    async def update_artifact_embedding(
        self,
        job_id: str,
        artifact_id: int,
        *,
        embedding: list[float] | None,
    ) -> Artifact | None:
        """Записывает 256-dim Gemini embedding в ``Artifact.embedding_json``.

        T6.1: вызывается из like-endpoint после embed_texts() чтобы
        preference_memory смог выполнить cosine retrieval. ``None``
        переводит артефакт обратно в «без embedding» состояние
        (preference_memory делает legacy fallback).
        """
        async with session_scope() as session:
            artifact = await session.get(Artifact, artifact_id)
            if artifact is None or artifact.job_id != job_id:
                return None
            artifact.embedding_json = embedding
            await session.flush()
            await session.refresh(artifact)
            return artifact

    async def delete_artifact(
        self,
        job_id: str,
        artifact_id: int,
        *,
        allowed_kinds: frozenset[ArtifactKind] = frozenset({ArtifactKind.reel_output}),
        artifacts_manager: Any | None = None,
    ) -> bool:
        """Удаляет артефакт + его файл на диске (только для `allowed_kinds`).

        Дефолт — ``{reel_output}``: API endpoint для «удалить рилс» не должен
        трогать proxy, транскрипт, план или субтитры. Если артефакт другого
        kind — raise ValueError.

        Возвращает ``True`` если запись реально удалена, ``False`` если не нашли.
        """
        async with session_scope() as session:
            artifact = await session.get(Artifact, artifact_id)
            if artifact is None or artifact.job_id != job_id:
                return False
            if artifact.kind not in allowed_kinds:
                raise ValueError(
                    f"artifact kind {artifact.kind!r} не разрешён к удалению через этот метод"
                )
            relative = artifact.path
            meta = dict(artifact.meta or {})
            await session.delete(artifact)

        # Удаление файла за пределами транзакции — ошибка fs не должна откатывать row.
        if artifacts_manager is not None and relative:
            try:
                target = artifacts_manager.resolve_relative(job_id, relative)
                if target.exists() and target.is_file():
                    target.unlink()
            except (ValueError, OSError) as exc:
                log.warning(
                    "artifact_file_unlink_failed",
                    job_id=job_id,
                    artifact_id=artifact_id,
                    error=str(exc),
                )
            # Попытка удалить сопутствующий subtitle (если записан в meta).
            sub_rel = meta.get("subtitle_path")
            if isinstance(sub_rel, str) and sub_rel:
                try:
                    sub_target = artifacts_manager.resolve_relative(job_id, sub_rel)
                    if sub_target.exists() and sub_target.is_file():
                        sub_target.unlink()
                except (ValueError, OSError):
                    pass
        return True

    async def delete_job(
        self,
        job_id: str,
        *,
        purge: str = "soft",
        artifacts_manager: Any | None = None,
    ) -> dict[str, Any]:
        """Удаляет job по одному из режимов.

        ``soft`` — пометить job как ``options.hidden=True`` (скрытие из списка);
        все файлы остаются в filesystem, статус и данные не трогаются.
        ``hard`` — пометить hidden + удалить все reel_output артефакты БЕЗ лайка
        (liked != "like"). Прокси, транскрипт, план и отлайканные рилсы живут.

        Возвращает summary ``{"purge": str, "deleted_reels": int, "kept_liked": int}``.
        """
        if purge not in {"soft", "hard", "nuke"}:
            raise ValueError(
                f"purge must be 'soft' | 'hard' | 'nuke', got {purge!r}"
            )

        deleted_reels = 0
        kept_liked = 0
        nuked_paths: list[str] = []

        if purge == "nuke":
            # Полная зачистка: сносим upload, artifacts-директорию, все
            # артефакт-записи и сам job row из БД. Ничего не остаётся.
            import shutil

            async with session_scope() as session:
                job = await session.get(Job, job_id)
                if job is None:
                    raise ValueError(f"job {job_id} not found")

                # Удаляем все артефакт-записи БД.
                result = await session.execute(
                    select(Artifact).where(Artifact.job_id == job_id)
                )
                for artifact in result.scalars().all():
                    await session.delete(artifact)

                source_path = Path(job.source_path) if job.source_path else None
                await session.delete(job)

            # Файлы source uploads.
            if source_path is not None:
                try:
                    if source_path.exists() and source_path.is_file():
                        source_path.unlink()
                        nuked_paths.append(str(source_path))
                    parent = source_path.parent
                    if parent.exists() and parent.is_dir() and not any(
                        parent.iterdir()
                    ):
                        parent.rmdir()
                except OSError as exc:
                    log.warning(
                        "job_nuke_source_cleanup_failed",
                        job_id=job_id,
                        path=str(source_path),
                        error=str(exc),
                    )

            # Artifacts директория целиком.
            if artifacts_manager is not None:
                try:
                    art_dir = artifacts_manager.job_dir(job_id)
                    if art_dir.exists() and art_dir.is_dir():
                        shutil.rmtree(art_dir, ignore_errors=True)
                        nuked_paths.append(str(art_dir))
                except Exception as exc:
                    log.warning(
                        "job_nuke_artifacts_cleanup_failed",
                        job_id=job_id,
                        error=str(exc),
                    )

            log.info(
                "job_nuked",
                job_id=job_id,
                removed_paths=nuked_paths,
            )
            return {
                "purge": "nuke",
                "deleted_reels": 0,
                "kept_liked": 0,
                "nuked_paths": nuked_paths,
            }

        if purge == "hard":
            async with session_scope() as session:
                result = await session.execute(
                    select(Artifact).where(
                        Artifact.job_id == job_id,
                        Artifact.kind == ArtifactKind.reel_output,
                    )
                )
                reels = list(result.scalars().all())
                reel_targets: list[tuple[int, str, dict[str, Any]]] = []
                for reel in reels:
                    meta = dict(reel.meta or {})
                    if meta.get("liked") == "like":
                        kept_liked += 1
                        continue
                    reel_targets.append((reel.id, reel.path, meta))
                    await session.delete(reel)

            if artifacts_manager is not None:
                for _reel_id, relative, meta in reel_targets:
                    try:
                        target = artifacts_manager.resolve_relative(job_id, relative)
                        if target.exists() and target.is_file():
                            target.unlink()
                    except (ValueError, OSError) as exc:
                        log.warning(
                            "job_hard_delete_unlink_failed",
                            job_id=job_id,
                            path=relative,
                            error=str(exc),
                        )
                    sub_rel = meta.get("subtitle_path")
                    if isinstance(sub_rel, str) and sub_rel:
                        try:
                            sub_target = artifacts_manager.resolve_relative(job_id, sub_rel)
                            if sub_target.exists() and sub_target.is_file():
                                sub_target.unlink()
                        except (ValueError, OSError):
                            pass
            deleted_reels = len([1 for _, _, _ in reel_targets])

        # Любой режим — помечаем job скрытым.
        async with session_scope() as session:
            job = await session.get(Job, job_id)
            if job is None:
                raise ValueError(f"job {job_id} not found")
            options = dict(job.options or {})
            options["hidden"] = True
            options["hidden_purge"] = purge
            options["hidden_at"] = utc_now().isoformat()
            job.options = options

        log.info(
            "job_deleted",
            job_id=job_id,
            purge=purge,
            deleted_reels=deleted_reels,
            kept_liked=kept_liked,
        )
        return {
            "purge": purge,
            "deleted_reels": deleted_reels,
            "kept_liked": kept_liked,
        }

    async def copy_reels_to_saved(
        self,
        job_id: str,
        reel_ids: list[int],
        *,
        artifacts_manager: Any,
    ) -> dict[str, Any]:
        """Копирует отобранные ``reel_output`` артефакты в ``<job_dir>/saved/<timestamp>/``.

        Копируется mp4-файл + companion ASS-субтитры (если есть в meta) +
        автоматически сгенерированный ``meta.json`` с полным описанием подборки.
        Исходные артефакты не трогаются — это чисто копирование.
        """
        import shutil

        if not reel_ids:
            raise ValueError("reel_ids не может быть пустым")

        async with session_scope() as session:
            job = await session.get(Job, job_id)
            if job is None:
                raise ValueError(f"job {job_id} not found")
            result = await session.execute(
                select(Artifact).where(
                    Artifact.job_id == job_id,
                    Artifact.kind == ArtifactKind.reel_output,
                    Artifact.id.in_(reel_ids),
                )
            )
            artifacts_rows = list(result.scalars().all())
            if not artifacts_rows:
                raise ValueError(
                    f"ни один из reel_ids {reel_ids} не принадлежит job {job_id}"
                )
            source_filename = job.source_filename
            job_profile = job.vision_profile.value if job.vision_profile else None

            payloads: list[dict[str, Any]] = []
            for art in artifacts_rows:
                payloads.append(
                    {
                        "artifact_id": art.id,
                        "path": art.path,
                        "meta": dict(art.meta or {}),
                    }
                )

        now = utc_now()
        folder_name = f"{now.strftime('%Y%m%d-%H%M%S')}_reels{len(payloads)}"
        saved_dir = artifacts_manager.saved_dir(job_id, folder_name)
        saved_dir.mkdir(parents=True, exist_ok=True)

        meta_entries: list[dict[str, Any]] = []
        copied_files = 0

        for payload in payloads:
            meta = payload["meta"]
            relative = payload["path"]
            try:
                src = artifacts_manager.resolve_relative(job_id, relative)
            except ValueError:
                continue
            if not src.is_file():
                continue
            dst = saved_dir / src.name
            shutil.copy2(src, dst)
            copied_files += 1
            entry: dict[str, Any] = {
                "reel_id": meta.get("reel_id") or payload["artifact_id"],
                "file": dst.name,
                "duration_sec": meta.get("duration_sec"),
                "score": meta.get("score") or meta.get("viral_score"),
                "caption": meta.get("caption"),
                "tags": meta.get("tags"),
                "liked": meta.get("liked", "none"),
            }
            subtitle_rel = meta.get("subtitle_path")
            if isinstance(subtitle_rel, str) and subtitle_rel:
                try:
                    sub_src = artifacts_manager.resolve_relative(job_id, subtitle_rel)
                    if sub_src.is_file():
                        sub_dst = saved_dir / sub_src.name
                        shutil.copy2(sub_src, sub_dst)
                        entry["subtitle"] = sub_dst.name
                except (ValueError, OSError):
                    pass
            poster_rel = meta.get("poster_path") or meta.get("cover_path")
            if isinstance(poster_rel, str) and poster_rel:
                try:
                    poster_src = artifacts_manager.resolve_relative(job_id, poster_rel)
                    if poster_src.is_file():
                        poster_dst = saved_dir / poster_src.name
                        shutil.copy2(poster_src, poster_dst)
                        entry["poster"] = poster_dst.name
                except (ValueError, OSError):
                    pass
            meta_entries.append(entry)

        summary = {
            "saved_at": now.isoformat(),
            "job_id": job_id,
            "source_filename": source_filename,
            "profile": job_profile,
            "reels": meta_entries,
        }
        meta_path = saved_dir / "meta.json"
        meta_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        relative_saved = str(saved_dir.relative_to(artifacts_manager.root))
        log.info(
            "reels_saved",
            job_id=job_id,
            folder=folder_name,
            copied=copied_files,
        )
        return {
            "saved_relative": relative_saved,
            "folder": folder_name,
            "copied_files": copied_files,
            "reels": meta_entries,
        }

    async def list_artifacts(self, job_id: str) -> list[Artifact]:
        async with session_scope() as session:
            result = await session.execute(
                select(Artifact)
                .where(Artifact.job_id == job_id)
                .order_by(Artifact.created_at.asc())
            )
            return list(result.scalars().all())

    async def list_liked_reels(
        self,
        *,
        project_id: int | None = None,
        job_id: str | None = None,
        limit: int = 100,
    ) -> list[Artifact]:
        """Артефакты kind='reel_output' где meta.liked='like'.

        Фильтры по project_id (через Job.project_id) и/или job_id. Сортировка
        по created_at desc — свежие лайки первыми. Используется scheduler UI
        для выбора пула рилсов в кампанию.

        Для фильтрации по JSON полю используется индексатор
        ``Artifact.meta["liked"].as_string()`` — SQLAlchemy транслирует в
        ``json_extract`` на SQLite и ``->>`` на Postgres.
        """
        stmt = (
            select(Artifact)
            .join(Job, Artifact.job_id == Job.id)
            .where(
                Artifact.kind == ArtifactKind.reel_output,
                Artifact.meta["liked"].as_string() == "like",
            )
            .order_by(Artifact.created_at.desc())
            .limit(limit)
        )
        if project_id is not None:
            stmt = stmt.where(Job.project_id == project_id)
        if job_id is not None:
            stmt = stmt.where(Artifact.job_id == job_id)

        async with session_scope() as session:
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def set_detected_language(self, job_id: str, lang: str) -> None:
        async with session_scope() as session:
            job = await session.get(Job, job_id)
            if job is None:
                return
            job.detected_language = lang

    async def set_source_duration(self, job_id: str, duration_sec: float) -> None:
        async with session_scope() as session:
            job = await session.get(Job, job_id)
            if job is None:
                return
            job.source_duration_sec = duration_sec

    async def reset_stale_running_jobs(self) -> int:
        """При старте приложения: все Job в статусе running → error.

        Паттерн из universal-rag main.py:24-70 — защита от зависших state после рестарта.
        """
        async with session_scope() as session:
            result = await session.execute(
                select(Job).where(Job.status == JobStatus.running)
            )
            stale_jobs = list(result.scalars().all())
            for job in stale_jobs:
                job.status = JobStatus.error
                job.error = "interrupted by application restart"
                job.finished_at = utc_now()
            count = len(stale_jobs)
        if count:
            log.warning("reset_stale_jobs", count=count)
        return count


def _store_timings(job: Job, timings: dict[str, Any]) -> None:
    """Мержит timing-телеметрию в ``Job.options`` без стирания остальных ключей."""
    current = dict(job.options or {})
    current["stage_durations"] = timings.get("stage_durations") or {}
    current["total_generation_sec"] = timings.get("total_generation_sec") or 0.0
    job.options = current


@asynccontextmanager
async def using_session() -> AsyncIterator[AsyncSession]:
    async with session_scope() as session:
        yield session


_global_service: JobService | None = None


def get_job_service() -> JobService:
    global _global_service
    if _global_service is None:
        _global_service = JobService()
    return _global_service


def serialize_event(event: dict[str, Any]) -> str:
    return json.dumps(event, ensure_ascii=False)
