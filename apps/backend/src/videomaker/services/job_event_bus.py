"""In-memory pub/sub шина для SSE-событий прогресса джобы.

Выделено из ``services/jobs.py`` (Phase 5.1) — `JobEventBus` отвечает
только за подписку/публикацию и не требует знаний про CRUD задачи.
"""

from __future__ import annotations

import asyncio
from typing import Any

from videomaker.core.logging import get_logger

log = get_logger(__name__)

SSE_QUEUE_MAX = 256


class JobEventBus:
    """In-memory pub/sub для SSE — один процесс, без Redis."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue[dict[str, Any]]]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, job_id: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=SSE_QUEUE_MAX)
        async with self._lock:
            self._subscribers.setdefault(job_id, []).append(queue)
        return queue

    async def unsubscribe(self, job_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        async with self._lock:
            subs = self._subscribers.get(job_id)
            if subs and queue in subs:
                subs.remove(queue)
                if not subs:
                    self._subscribers.pop(job_id, None)

    async def publish(self, job_id: str, event: dict[str, Any]) -> None:
        async with self._lock:
            subs = list(self._subscribers.get(job_id, []))
        for queue in subs:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                log.warning("sse_queue_full_dropping_event", job_id=job_id)
