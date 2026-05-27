"""CRUD для ProjectRow + управление привязкой Job → project."""
from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from videomaker.models.job_orm import Job
from videomaker.models.project import ProjectRow


async def list_projects(db: AsyncSession) -> Sequence[ProjectRow]:
    result = await db.execute(
        select(ProjectRow).order_by(ProjectRow.created_at.desc())
    )
    return result.scalars().all()


async def create_project(
    db: AsyncSession,
    *,
    name: str,
    description: str = "",
    color: str = "#6366f1",
) -> ProjectRow:
    row = ProjectRow(name=name, description=description, color=color)
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return row


async def get_project(db: AsyncSession, project_id: int) -> ProjectRow | None:
    return await db.get(ProjectRow, project_id)


async def update_project(
    db: AsyncSession,
    project_id: int,
    *,
    name: str | None = None,
    description: str | None = None,
    color: str | None = None,
) -> ProjectRow | None:
    row = await db.get(ProjectRow, project_id)
    if row is None:
        return None
    if name is not None:
        row.name = name
    if description is not None:
        row.description = description
    if color is not None:
        row.color = color
    await db.flush()
    await db.refresh(row)
    return row


async def delete_project(db: AsyncSession, project_id: int) -> None:
    row = await db.get(ProjectRow, project_id)
    if row is not None:
        await db.delete(row)
        await db.flush()


async def assign_job_to_project(
    db: AsyncSession, *, job_id: str, project_id: int | None
) -> Job | None:
    job = await db.get(Job, job_id)
    if job is None:
        return None
    job.project_id = project_id
    await db.flush()
    await db.refresh(job)
    return job


async def list_jobs_by_project(
    db: AsyncSession, project_id: int
) -> Sequence[Job]:
    result = await db.execute(
        select(Job)
        .where(Job.project_id == project_id)
        .order_by(Job.created_at.desc())
    )
    return result.scalars().all()
