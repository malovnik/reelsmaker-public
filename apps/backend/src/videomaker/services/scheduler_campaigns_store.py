"""CRUD для schedule_campaigns + schedule_assignments."""
from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from videomaker.models.scheduler import (
    AssignmentStatus,
    ScheduleAssignmentRow,
    ScheduleCampaignRow,
)

_MUTABLE_ASSIGNMENT_FIELDS = frozenset({
    "status",
    "publer_media_id",
    "publer_job_id",
    "publer_post_id",
    "publer_post_url",
    "error_message",
    "attempts",
    "last_attempt_at",
    "caption",
    "title",
    "hashtags_json",
    "scheduled_at_utc",
})


async def create_campaign(
    db: AsyncSession,
    *,
    name: str,
    tz: str,
    time_of_day: str,
    dates: list[str],
    status: str = "draft",
) -> ScheduleCampaignRow:
    row = ScheduleCampaignRow(
        name=name,
        tz=tz,
        time_of_day=time_of_day,
        dates_json=dates,
        status=status,
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return row


async def list_campaigns(
    db: AsyncSession,
    *,
    status: str | None = None,
    limit: int = 50,
) -> Sequence[ScheduleCampaignRow]:
    stmt = (
        select(ScheduleCampaignRow)
        .order_by(ScheduleCampaignRow.created_at.desc())
        .limit(limit)
    )
    if status is not None:
        stmt = stmt.where(ScheduleCampaignRow.status == status)
    result = await db.execute(stmt)
    return result.scalars().all()


async def get_campaign(
    db: AsyncSession, campaign_id: int
) -> ScheduleCampaignRow | None:
    return await db.get(ScheduleCampaignRow, campaign_id)


async def update_campaign_status(
    db: AsyncSession, campaign_id: int, *, status: str
) -> ScheduleCampaignRow | None:
    row = await db.get(ScheduleCampaignRow, campaign_id)
    if row is None:
        return None
    row.status = status
    await db.flush()
    await db.refresh(row)
    return row


async def delete_campaign(db: AsyncSession, campaign_id: int) -> None:
    row = await db.get(ScheduleCampaignRow, campaign_id)
    if row is not None:
        await db.delete(row)
        await db.flush()


async def create_assignment(
    db: AsyncSession,
    *,
    campaign_id: int,
    job_id: str,
    reel_artifact_id: int,
    publer_account_id: str,
    network: str,
    title: str,
    caption: str,
    hashtags: list[str],
    applied_preset_ids: list[int],
    scheduled_at_utc: datetime,
    status: str = AssignmentStatus.draft.value,
) -> ScheduleAssignmentRow:
    row = ScheduleAssignmentRow(
        campaign_id=campaign_id,
        job_id=job_id,
        reel_artifact_id=reel_artifact_id,
        publer_account_id=publer_account_id,
        network=network,
        title=title,
        caption=caption,
        hashtags_json=hashtags,
        applied_preset_ids_json=applied_preset_ids,
        scheduled_at_utc=scheduled_at_utc,
        status=status,
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return row


async def list_assignments(
    db: AsyncSession,
    *,
    campaign_id: int | None = None,
    status: str | None = None,
) -> Sequence[ScheduleAssignmentRow]:
    stmt = select(ScheduleAssignmentRow).order_by(
        ScheduleAssignmentRow.scheduled_at_utc
    )
    filters = []
    if campaign_id is not None:
        filters.append(ScheduleAssignmentRow.campaign_id == campaign_id)
    if status is not None:
        filters.append(ScheduleAssignmentRow.status == status)
    if filters:
        stmt = stmt.where(and_(*filters))
    result = await db.execute(stmt)
    return result.scalars().all()


async def get_assignment(
    db: AsyncSession, assignment_id: int
) -> ScheduleAssignmentRow | None:
    return await db.get(ScheduleAssignmentRow, assignment_id)


async def update_assignment(
    db: AsyncSession, assignment_id: int, **fields: Any
) -> ScheduleAssignmentRow | None:
    row = await db.get(ScheduleAssignmentRow, assignment_id)
    if row is None:
        return None
    for key, value in fields.items():
        if key in _MUTABLE_ASSIGNMENT_FIELDS:
            setattr(row, key, value)
    await db.flush()
    await db.refresh(row)
    return row


async def list_pending_due(
    db: AsyncSession, *, limit: int = 50
) -> Sequence[ScheduleAssignmentRow]:
    """queued assignments — готовые к доставке в Publer.

    Publer — сам планировщик: принимает scheduled_at в будущем и хранит
    план. Наша задача — доставить в Publer как можно раньше, не ждать.
    Worker забирает по `limit` за tick (rate limit защита).
    """
    stmt = (
        select(ScheduleAssignmentRow)
        .where(ScheduleAssignmentRow.status == AssignmentStatus.queued.value)
        .order_by(ScheduleAssignmentRow.scheduled_at_utc)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return result.scalars().all()
