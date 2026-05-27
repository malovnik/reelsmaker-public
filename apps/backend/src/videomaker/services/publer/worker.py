"""Background worker — забирает queued assignments и немедленно доставляет в Publer.

Publer — сам планировщик: принимает `/posts/schedule` с `scheduled_at` в
будущем и хранит план до публикации. Наш worker не ждёт наступления
scheduled_at: как только assignment approved (status=queued), worker
uploads media + POST /posts/schedule. Publer публикует в указанный момент.

Rate limit protection: `limit=50` на tick (50 assignments × 2 Publer
requests = 100 req — ровно в лимит Publer 100 req/2min).
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from videomaker.core.config import Settings, get_settings
from videomaker.core.db import get_sessionmaker
from videomaker.core.logging import get_logger
from videomaker.models.job import Artifact
from videomaker.models.scheduler import AssignmentStatus, ScheduleAssignmentRow
from videomaker.services.publer.client import PublerClient
from videomaker.services.publer.media_uploader import upload_reel_to_publer
from videomaker.services.publer.post_builder import build_schedule_request
from videomaker.services.publer.schemas import PublerMediaRef
from videomaker.services.scheduler_campaigns_store import (
    list_pending_due,
    update_assignment,
)

log = get_logger(__name__)

POLL_INTERVAL_SEC = 30
MAX_ATTEMPTS = 3


class PublerWorker:
    """Опрашивает очередь ScheduleAssignmentRow и доставляет в Publer.

    Lifecycle: ``await start()`` стартует фоновый asyncio.Task; ``await stop()``
    выставляет stop-event и ждёт завершения. Без ``PUBLER_API_KEY`` — no-op.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        if not self._settings.publer_api_key:
            log.info("publer_worker_disabled_no_api_key")
            return
        if self._task is not None and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="publer-worker")
        log.info(
            "publer_worker_started",
            poll_sec=POLL_INTERVAL_SEC,
            max_attempts=MAX_ATTEMPTS,
        )

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop.set()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None
            log.info("publer_worker_stopped")

    async def _run(self) -> None:
        async with PublerClient(self._settings) as client:
            while not self._stop.is_set():
                try:
                    await self._tick(client)
                except Exception:
                    log.exception("publer_worker_tick_failed")
                try:
                    await asyncio.wait_for(
                        self._stop.wait(), timeout=POLL_INTERVAL_SEC
                    )
                    return
                except TimeoutError:
                    continue

    async def _tick(self, client: PublerClient) -> None:
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as db:
            due = list(await list_pending_due(db))
        if not due:
            return
        log.info("publer_worker_tick_due", count=len(due))
        for assignment in due:
            async with sessionmaker() as db:
                fresh = await db.get(ScheduleAssignmentRow, assignment.id)
                if fresh is None or fresh.status != AssignmentStatus.queued.value:
                    continue
                await self._deliver_one(db, client, fresh)

    async def _deliver_one(
        self,
        db: AsyncSession,
        client: PublerClient,
        assignment: ScheduleAssignmentRow,
    ) -> None:
        new_attempts = assignment.attempts + 1
        await update_assignment(
            db,
            assignment.id,
            status=AssignmentStatus.uploading.value,
            attempts=new_attempts,
            last_attempt_at=datetime.now(UTC),
        )
        await db.commit()

        try:
            if assignment.publer_media_id:
                media_id = assignment.publer_media_id
                log.info(
                    "publer_media_reuse",
                    assignment_id=assignment.id,
                    media_id=media_id,
                )
                reel_path = await self._resolve_reel_path(db, assignment)
            else:
                reel_path = await self._resolve_reel_path(db, assignment)
                media_id = await upload_reel_to_publer(
                    reel_path=reel_path, client=client
                )
                await update_assignment(
                    db,
                    assignment.id,
                    publer_media_id=media_id,
                )
                await db.commit()
            media_ref = PublerMediaRef(
                id=media_id,
                path=str(reel_path),
                type="video",
            )
            payload = build_schedule_request(
                assignments=[assignment],
                media_refs_by_assignment_id={assignment.id: media_ref},
            )
            publer_job_id = await client.schedule_posts(payload)
            await update_assignment(
                db,
                assignment.id,
                status=AssignmentStatus.scheduled.value,
                publer_media_id=media_id,
                publer_job_id=publer_job_id,
                error_message=None,
            )
            await db.commit()
            log.info(
                "publer_delivery_ok",
                assignment_id=assignment.id,
                publer_job_id=publer_job_id,
                attempts=new_attempts,
            )
        except Exception as exc:
            log.exception(
                "publer_delivery_failed",
                assignment_id=assignment.id,
                attempts=new_attempts,
            )
            final_status = (
                AssignmentStatus.failed.value
                if new_attempts >= MAX_ATTEMPTS
                else AssignmentStatus.queued.value
            )
            await update_assignment(
                db,
                assignment.id,
                status=final_status,
                error_message=str(exc)[:1000],
            )
            await db.commit()

    async def _resolve_reel_path(
        self, db: AsyncSession, assignment: ScheduleAssignmentRow
    ) -> Path:
        artifact = await db.get(Artifact, assignment.reel_artifact_id)
        if artifact is None:
            raise FileNotFoundError(
                f"Artifact {assignment.reel_artifact_id} отсутствует"
            )
        if not artifact.path:
            raise FileNotFoundError(f"Artifact {artifact.id} не имеет path")
        candidate = Path(artifact.path)
        if not candidate.is_absolute():
            artifacts_root = Path(self._settings.app_artifacts_dir)
            candidate = artifacts_root / artifact.job_id / artifact.path
        if not candidate.exists():
            raise FileNotFoundError(f"Reel файл отсутствует: {candidate}")
        return candidate

    async def __aenter__(self) -> PublerWorker:
        await self.start()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.stop()
