"""Settings service — domain-level операции над prompt overrides.

Выделено из ``api/routes/settings.py`` в Phase 4.3: route больше не обращается
к БД напрямую, SQL сосредоточен в services/ — чистое разделение слоёв
API → service → storage.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from videomaker.core.db import session_scope
from videomaker.models.job import PromptSetting


@dataclass(frozen=True, slots=True)
class PromptRecord:
    """Плоский DTO для route — чтобы не тащить ORM-объект за границу сессии."""

    key: str
    content: str


async def list_prompt_overrides() -> list[PromptRecord]:
    """Все prompt overrides отсортированные по key."""

    async with session_scope() as session:
        result = await session.execute(
            select(PromptSetting).order_by(PromptSetting.key)
        )
        rows = list(result.scalars().all())
    return [PromptRecord(key=row.key, content=row.content) for row in rows]


async def get_prompt_override(key: str) -> PromptRecord | None:
    """Возвращает override по ключу или ``None`` если не задан."""

    async with session_scope() as session:
        row = await session.get(PromptSetting, key)
        if row is None:
            return None
        return PromptRecord(key=row.key, content=row.content)


async def upsert_prompt_override(*, key: str, content: str) -> PromptRecord:
    """Insert или update override. Возвращает актуальную запись."""

    async with session_scope() as session:
        row = await session.get(PromptSetting, key)
        if row is None:
            row = PromptSetting(key=key, content=content)
            session.add(row)
        else:
            row.content = content
        await session.flush()
        return PromptRecord(key=row.key, content=row.content)
