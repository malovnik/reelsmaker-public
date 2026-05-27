"""/api/v1/projects — CRUD проектов + привязка Job ↔ Project.

Проект — логическая группа джобов (папка). Scheduler использует project_id
как source для pool'а лайкнутых рилсов при создании кампаний.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from videomaker.core.db import session_scope
from videomaker.services import projects_store

router = APIRouter(prefix="/projects", tags=["projects"])

# Второй роутер для /jobs/{job_id}/project — prefix /jobs совпадает с jobs.py,
# но FastAPI допускает включение нескольких router'ов с одним prefix.
jobs_router = APIRouter(prefix="/jobs", tags=["projects"])


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    color: str
    created_at: datetime
    updated_at: datetime


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=256)
    description: str = ""
    color: str = "#6366f1"


class ProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=256)
    description: str | None = None
    color: str | None = None


class JobBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str
    display_name: str | None = None
    source_filename: str
    source_duration_sec: float | None = None
    created_at: datetime
    finished_at: datetime | None = None


class ProjectDetail(ProjectRead):
    jobs: list[JobBrief] = Field(default_factory=list)


class JobProjectAssign(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: int | None = None


class JobProjectAssignResponse(BaseModel):
    job_id: str
    project_id: int | None


@router.get("", response_model=list[ProjectRead])
async def list_projects_endpoint() -> list[ProjectRead]:
    async with session_scope() as db:
        rows = await projects_store.list_projects(db)
        return [ProjectRead.model_validate(row) for row in rows]


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project_endpoint(payload: ProjectCreate) -> ProjectRead:
    async with session_scope() as db:
        row = await projects_store.create_project(
            db,
            name=payload.name,
            description=payload.description,
            color=payload.color,
        )
        return ProjectRead.model_validate(row)


@router.get("/{project_id}", response_model=ProjectDetail)
async def get_project_endpoint(project_id: int) -> ProjectDetail:
    async with session_scope() as db:
        row = await projects_store.get_project(db, project_id)
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"project {project_id} not found",
            )
        jobs = await projects_store.list_jobs_by_project(db, project_id)
        return ProjectDetail(
            id=row.id,
            name=row.name,
            description=row.description,
            color=row.color,
            created_at=row.created_at,
            updated_at=row.updated_at,
            jobs=[
                JobBrief(
                    id=job.id,
                    status=job.status.value if hasattr(job.status, "value") else str(job.status),
                    display_name=job.display_name,
                    source_filename=job.source_filename,
                    source_duration_sec=job.source_duration_sec,
                    created_at=job.created_at,
                    finished_at=job.finished_at,
                )
                for job in jobs
            ],
        )


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project_endpoint(
    project_id: int, payload: ProjectUpdate
) -> ProjectRead:
    async with session_scope() as db:
        row = await projects_store.update_project(
            db,
            project_id,
            name=payload.name,
            description=payload.description,
            color=payload.color,
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"project {project_id} not found",
            )
        return ProjectRead.model_validate(row)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project_endpoint(project_id: int) -> None:
    async with session_scope() as db:
        await projects_store.delete_project(db, project_id)


@jobs_router.patch(
    "/{job_id}/project", response_model=JobProjectAssignResponse
)
async def assign_job_to_project_endpoint(
    job_id: str, payload: JobProjectAssign
) -> JobProjectAssignResponse:
    """Привязать/отвязать job к/от проекта."""
    async with session_scope() as db:
        if payload.project_id is not None:
            project = await projects_store.get_project(db, payload.project_id)
            if project is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"project {payload.project_id} not found",
                )
        job = await projects_store.assign_job_to_project(
            db, job_id=job_id, project_id=payload.project_id
        )
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"job {job_id} not found",
            )
        return JobProjectAssignResponse(
            job_id=job.id, project_id=job.project_id
        )
