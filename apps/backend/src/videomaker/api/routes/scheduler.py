"""/api/v1/scheduler — Publer workspace + account profiles + caption presets +
scheduling campaigns + assignments + manual publish.

Thin REST facade поверх ``services/publer`` (PublerClient, scheduler_service)
и ORM-store'ов (``account_profiles_store``, ``scheduler_campaigns_store``).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from videomaker.core.artifacts import ArtifactsManager
from videomaker.core.config import Settings, get_settings
from videomaker.core.db import session_scope
from videomaker.core.logging import get_logger
from videomaker.models.job import Artifact, ArtifactKind
from videomaker.models.reel_plan import ReelPlan
from videomaker.models.scheduler import (
    AccountProfileRow,
    AssignmentStatus,
    PublerNetwork,
    ScheduleAssignmentRow,
    ScheduleCampaignRow,
)
from videomaker.services import (
    account_profiles_store,
    scheduler_campaigns_store,
)
from videomaker.services.llm_clients import (
    GeminiClient,
    LLMClient,
    _resolve_tier_models,
)
from videomaker.services.publer.caption_generator import generate_caption
from videomaker.services.publer.client import PublerClient, PublerClientError
from videomaker.services.publer.preset_applier import apply_presets
from videomaker.services.publer.scheduler_service import build_campaign_from_pool
from videomaker.services.publer.schemas import PublerAccount

router = APIRouter(prefix="/scheduler", tags=["scheduler"])
log = get_logger(__name__)


# ────────────────────────── DTOs ──────────────────────────


class ConnectionStatus(BaseModel):
    ok: bool
    workspace: str | None
    accounts_count: int | None
    error: str | None = None


class AccountProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    publer_account_id: str
    display_name: str
    network: str
    language: str
    audience: str
    tone: str
    default_hashtags: list[str] = Field(default_factory=list)
    banned_words: list[str] = Field(default_factory=list)
    cta_style: str
    max_caption_length: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: AccountProfileRow) -> AccountProfileRead:
        return cls(
            publer_account_id=row.publer_account_id,
            display_name=row.display_name,
            network=row.network,
            language=row.language,
            audience=row.audience,
            tone=row.tone,
            default_hashtags=list(row.default_hashtags_json or []),
            banned_words=list(row.banned_words_json or []),
            cta_style=row.cta_style,
            max_caption_length=row.max_caption_length,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class AccountProfileUpsert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=256)
    network: str = Field(pattern="^(instagram|youtube)$")
    language: str | None = Field(default=None, max_length=8)
    audience: str | None = None
    tone: str | None = None
    default_hashtags: list[str] | None = None
    banned_words: list[str] | None = None
    cta_style: str | None = None
    max_caption_length: int | None = Field(default=None, ge=1, le=10000)


class CaptionPresetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    position: str
    content: str
    account_id: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CaptionPresetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    position: str = Field(pattern="^(prepend|append)$")
    content: str = Field(min_length=1)
    account_id: str | None = None


class CaptionPresetUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=128)
    position: str | None = Field(default=None, pattern="^(prepend|append)$")
    content: str | None = Field(default=None, min_length=1)
    account_id: str | None = None
    is_active: bool | None = None


class CampaignRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    tz: str
    time_of_day: str
    dates: list[str]
    status: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: ScheduleCampaignRow) -> CampaignRead:
        return cls(
            id=row.id,
            name=row.name,
            tz=row.tz,
            time_of_day=row.time_of_day,
            dates=list(row.dates_json or []),
            status=row.status,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class AssignmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    campaign_id: int
    job_id: str
    reel_artifact_id: int
    publer_account_id: str
    network: str
    title: str
    caption: str
    hashtags: list[str]
    applied_preset_ids: list[int]
    scheduled_at_utc: datetime
    status: str
    publer_media_id: str | None = None
    publer_job_id: str | None = None
    publer_post_id: str | None = None
    publer_post_url: str | None = None
    error_message: str | None = None
    attempts: int
    last_attempt_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: ScheduleAssignmentRow) -> AssignmentRead:
        return cls(
            id=row.id,
            campaign_id=row.campaign_id,
            job_id=row.job_id,
            reel_artifact_id=row.reel_artifact_id,
            publer_account_id=row.publer_account_id,
            network=row.network,
            title=row.title,
            caption=row.caption,
            hashtags=list(row.hashtags_json or []),
            applied_preset_ids=list(row.applied_preset_ids_json or []),
            scheduled_at_utc=row.scheduled_at_utc,
            status=row.status,
            publer_media_id=row.publer_media_id,
            publer_job_id=row.publer_job_id,
            publer_post_id=row.publer_post_id,
            publer_post_url=row.publer_post_url,
            error_message=row.error_message,
            attempts=row.attempts,
            last_attempt_at=row.last_attempt_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class CampaignDetail(CampaignRead):
    assignments: list[AssignmentRead] = Field(default_factory=list)


class CampaignCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=256)
    time_of_day: str = Field(pattern=r"^\d{2}:\d{2}$")
    tz: str = Field(default="Asia/Ho_Chi_Minh")
    reel_artifact_ids: list[int] = Field(min_length=1)
    account_ids: list[str] = Field(min_length=1)
    mode: Literal["per_date", "single_day", "serial"] = "per_date"
    dates: list[str] = Field(default_factory=list)
    single_day_date: str | None = None
    single_day_interval_min: int = Field(default=60, ge=1, le=1440)
    serial_start_date: str | None = None
    serial_interval_days: int = Field(default=1, ge=1, le=365)


class CampaignCreateResponse(BaseModel):
    campaign: CampaignRead
    assignments: list[AssignmentRead]


class CampaignApproveResponse(BaseModel):
    campaign_id: int
    approved_count: int


class AssignmentPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    caption: str | None = None
    title: str | None = None
    hashtags: list[str] | None = None
    scheduled_at_utc: datetime | None = None


class ManualPublishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reel_artifact_id: int
    job_id: str
    publer_account_id: str
    scheduled_at_utc: datetime
    custom_caption: str | None = None
    custom_title: str | None = None


# ────────────────────────── helpers ──────────────────────────


def _build_flash_lite_client(settings: Settings) -> LLMClient:
    """Инстанцирует LLMClient на модели Flash Lite (caption_generator tier)."""
    if not settings.gemini_api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GEMINI_API_KEY not configured — cannot generate captions",
        )
    model = _resolve_tier_models(settings)["flash_lite"]
    return GeminiClient(api_key=settings.gemini_api_key, model=model)


async def _load_reel_plan_for_artifact(
    db: AsyncSession,
    *,
    artifacts: ArtifactsManager,
    artifact_id: int,
) -> tuple[str, ReelPlan, int]:
    """Читает ``reel_plan.json`` из job-директории + находит ReelPlan по reel_id.

    Возвращает ``(job_id, reel_plan, artifact_id)`` — tuple ожидаемый
    ``build_campaign_from_pool``.
    """
    art_row = await db.get(Artifact, artifact_id)
    if art_row is None or art_row.kind != ArtifactKind.reel_output:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"reel artifact {artifact_id} not found",
        )
    reel_id = (art_row.meta or {}).get("reel_id")
    if not reel_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"artifact {artifact_id} has no meta.reel_id",
        )

    job_dir = artifacts.job_dir(art_row.job_id)
    plan_candidates = [
        job_dir / "text" / "reel_plan.json",
        job_dir / "reel_plan.json",
    ]
    plan_path: Path | None = next((p for p in plan_candidates if p.exists()), None)
    if plan_path is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"reel_plan.json not found for job {art_row.job_id}",
        )
    try:
        raw = json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"reel_plan.json parse error for job {art_row.job_id}: {exc}",
        ) from exc

    raw_reels = raw.get("reels") if isinstance(raw, dict) else None
    if not isinstance(raw_reels, list):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"reel_plan.json has no 'reels' list for job {art_row.job_id}",
        )

    for raw_reel in raw_reels:
        if not isinstance(raw_reel, dict) or raw_reel.get("reel_id") != reel_id:
            continue
        try:
            reel = ReelPlan.model_validate(raw_reel)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"reel_plan.json reel '{reel_id}' schema error in job "
                    f"{art_row.job_id}: {exc}"
                ),
            ) from exc
        return art_row.job_id, reel, artifact_id

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=(
            f"reel_id {reel_id} not found in reel_plan.json for job "
            f"{art_row.job_id} (artifact {artifact_id})"
        ),
    )


def _artifact_manager() -> ArtifactsManager:
    return ArtifactsManager()


# ────────────────────────── connection probe ──────────────────────────


@router.get("/connection/status", response_model=ConnectionStatus)
async def connection_status(
    settings: Settings = Depends(get_settings),
) -> ConnectionStatus:
    if not settings.publer_api_key:
        return ConnectionStatus(
            ok=False,
            workspace=None,
            accounts_count=None,
            error="PUBLER_API_KEY not configured",
        )
    try:
        async with PublerClient(settings) as client:
            workspaces = await client.list_workspaces()
            ws_name: str | None = None
            if settings.publer_workspace_id:
                ws_name = next(
                    (w.name for w in workspaces if w.id == settings.publer_workspace_id),
                    None,
                )
            if ws_name is None and workspaces:
                ws_name = workspaces[0].name
            accounts = await client.list_accounts()
            return ConnectionStatus(
                ok=True,
                workspace=ws_name,
                accounts_count=len(accounts),
                error=None,
            )
    except PublerClientError as exc:
        return ConnectionStatus(
            ok=False, workspace=None, accounts_count=None, error=str(exc)
        )
    except Exception as exc:  # безопасный fallback
        log.exception("publer_probe_unexpected")
        return ConnectionStatus(
            ok=False,
            workspace=None,
            accounts_count=None,
            error=f"{type(exc).__name__}: {exc}",
        )


# ────────────────────────── accounts (live Publer) ──────────────────────────


@router.get("/accounts", response_model=list[PublerAccount])
async def list_publer_accounts(
    settings: Settings = Depends(get_settings),
) -> list[PublerAccount]:
    if not settings.publer_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PUBLER_API_KEY not configured",
        )
    try:
        async with PublerClient(settings) as client:
            return await client.list_accounts()
    except PublerClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc


# ────────────────────────── account profiles (local ORM) ──────────────────────────


@router.get("/accounts/profiles", response_model=list[AccountProfileRead])
async def list_account_profiles() -> list[AccountProfileRead]:
    async with session_scope() as db:
        rows = await account_profiles_store.list_profiles(db)
        return [AccountProfileRead.from_row(r) for r in rows]


@router.put(
    "/accounts/profiles/{publer_account_id}", response_model=AccountProfileRead
)
async def upsert_account_profile(
    publer_account_id: str, payload: AccountProfileUpsert
) -> AccountProfileRead:
    fields: dict[str, object] = {}
    if payload.language is not None:
        fields["language"] = payload.language
    if payload.audience is not None:
        fields["audience"] = payload.audience
    if payload.tone is not None:
        fields["tone"] = payload.tone
    if payload.default_hashtags is not None:
        fields["default_hashtags_json"] = payload.default_hashtags
    if payload.banned_words is not None:
        fields["banned_words_json"] = payload.banned_words
    if payload.cta_style is not None:
        fields["cta_style"] = payload.cta_style
    if payload.max_caption_length is not None:
        fields["max_caption_length"] = payload.max_caption_length

    async with session_scope() as db:
        row = await account_profiles_store.upsert_profile(
            db,
            publer_account_id=publer_account_id,
            display_name=payload.display_name,
            network=payload.network,
            **fields,
        )
        return AccountProfileRead.from_row(row)


@router.delete(
    "/accounts/profiles/{publer_account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_account_profile(publer_account_id: str) -> None:
    async with session_scope() as db:
        await account_profiles_store.delete_profile(db, publer_account_id)


# ────────────────────────── caption presets ──────────────────────────


@router.get("/presets", response_model=list[CaptionPresetRead])
async def list_presets(account_id: str | None = None) -> list[CaptionPresetRead]:
    async with session_scope() as db:
        rows = await account_profiles_store.list_all_presets(
            db, account_id=account_id
        )
        return [CaptionPresetRead.model_validate(r) for r in rows]


@router.post(
    "/presets",
    response_model=CaptionPresetRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_preset(payload: CaptionPresetCreate) -> CaptionPresetRead:
    async with session_scope() as db:
        row = await account_profiles_store.create_preset(
            db,
            name=payload.name,
            position=payload.position,
            content=payload.content,
            account_id=payload.account_id,
        )
        return CaptionPresetRead.model_validate(row)


@router.patch("/presets/{preset_id}", response_model=CaptionPresetRead)
async def update_preset(
    preset_id: int, payload: CaptionPresetUpdate
) -> CaptionPresetRead:
    async with session_scope() as db:
        row = await account_profiles_store.update_preset(
            db,
            preset_id,
            name=payload.name,
            position=payload.position,
            content=payload.content,
            account_id=payload.account_id,
            is_active=payload.is_active,
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"preset {preset_id} not found",
            )
        return CaptionPresetRead.model_validate(row)


@router.delete("/presets/{preset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_preset(preset_id: int) -> None:
    async with session_scope() as db:
        await account_profiles_store.delete_preset(db, preset_id)


# ────────────────────────── campaigns ──────────────────────────


@router.get("/campaigns", response_model=list[CampaignRead])
async def list_campaigns(
    status_filter: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
) -> list[CampaignRead]:
    async with session_scope() as db:
        rows = await scheduler_campaigns_store.list_campaigns(
            db, status=status_filter, limit=limit
        )
        return [CampaignRead.from_row(r) for r in rows]


@router.post(
    "/campaigns",
    response_model=CampaignCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_campaign(
    payload: CampaignCreate,
    settings: Settings = Depends(get_settings),
) -> CampaignCreateResponse:
    if payload.mode == "per_date" and not payload.dates:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="dates обязательны для mode=per_date",
        )
    if payload.mode == "single_day" and not payload.single_day_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="single_day_date обязателен для mode=single_day",
        )
    if payload.mode == "serial" and not payload.serial_start_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="serial_start_date обязателен для mode=serial",
        )

    artifacts = _artifact_manager()
    llm = _build_flash_lite_client(settings)

    async with session_scope() as db:
        reels: list[tuple[str, ReelPlan, int]] = []
        for artifact_id in payload.reel_artifact_ids:
            reels.append(
                await _load_reel_plan_for_artifact(
                    db, artifacts=artifacts, artifact_id=artifact_id
                )
            )

        try:
            campaign, assignments = await build_campaign_from_pool(
                db,
                name=payload.name,
                reels=reels,
                account_ids=payload.account_ids,
                time_of_day=payload.time_of_day,
                tz=payload.tz,
                mode=payload.mode,
                dates=payload.dates,
                single_day_date=payload.single_day_date,
                single_day_interval_min=payload.single_day_interval_min,
                serial_start_date=payload.serial_start_date,
                serial_interval_days=payload.serial_interval_days,
                llm=llm,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc

        return CampaignCreateResponse(
            campaign=CampaignRead.from_row(campaign),
            assignments=[AssignmentRead.from_row(a) for a in assignments],
        )


@router.get("/campaigns/{campaign_id}", response_model=CampaignDetail)
async def get_campaign(campaign_id: int) -> CampaignDetail:
    async with session_scope() as db:
        row = await scheduler_campaigns_store.get_campaign(db, campaign_id)
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"campaign {campaign_id} not found",
            )
        assignments = await scheduler_campaigns_store.list_assignments(
            db, campaign_id=campaign_id
        )
        base = CampaignRead.from_row(row)
        return CampaignDetail(
            **base.model_dump(),
            assignments=[AssignmentRead.from_row(a) for a in assignments],
        )


@router.post(
    "/campaigns/{campaign_id}/approve", response_model=CampaignApproveResponse
)
async def approve_campaign(campaign_id: int) -> CampaignApproveResponse:
    """Переводит все ``draft`` assignments кампании в ``queued``.

    Delivery-worker (Task 8) подхватит их и опубликует в Publer согласно
    ``scheduled_at_utc``.
    """
    async with session_scope() as db:
        campaign = await scheduler_campaigns_store.get_campaign(db, campaign_id)
        if campaign is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"campaign {campaign_id} not found",
            )
        stmt = select(ScheduleAssignmentRow).where(
            ScheduleAssignmentRow.campaign_id == campaign_id,
            ScheduleAssignmentRow.status == AssignmentStatus.draft.value,
        )
        result = await db.execute(stmt)
        drafts: Sequence[ScheduleAssignmentRow] = result.scalars().all()
        for row in drafts:
            row.status = AssignmentStatus.queued.value
        campaign.status = "approved"
        await db.flush()
        return CampaignApproveResponse(
            campaign_id=campaign_id, approved_count=len(drafts)
        )


@router.delete(
    "/campaigns/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_campaign(campaign_id: int) -> None:
    async with session_scope() as db:
        await scheduler_campaigns_store.delete_campaign(db, campaign_id)


# ────────────────────────── assignments ──────────────────────────


@router.get("/assignments", response_model=list[AssignmentRead])
async def list_assignments(
    campaign_id: int | None = None, status_filter: str | None = None
) -> list[AssignmentRead]:
    async with session_scope() as db:
        rows = await scheduler_campaigns_store.list_assignments(
            db, campaign_id=campaign_id, status=status_filter
        )
        return [AssignmentRead.from_row(r) for r in rows]


@router.patch("/assignments/{assignment_id}", response_model=AssignmentRead)
async def patch_assignment(
    assignment_id: int, payload: AssignmentPatch
) -> AssignmentRead:
    fields: dict[str, object] = {}
    if payload.caption is not None:
        fields["caption"] = payload.caption
    if payload.title is not None:
        fields["title"] = payload.title
    if payload.hashtags is not None:
        fields["hashtags_json"] = payload.hashtags
    if payload.scheduled_at_utc is not None:
        fields["scheduled_at_utc"] = payload.scheduled_at_utc

    async with session_scope() as db:
        row = await scheduler_campaigns_store.update_assignment(
            db, assignment_id, **fields
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"assignment {assignment_id} not found",
            )
        return AssignmentRead.from_row(row)


@router.post(
    "/assignments/{assignment_id}/cancel", response_model=AssignmentRead
)
async def cancel_assignment(
    assignment_id: int,
    settings: Settings = Depends(get_settings),
) -> AssignmentRead:
    """Отменить assignment с реальным отзывом поста в Publer.

    Поведение по состоянию:
    * ``published`` — пост уже опубликован, отозвать нельзя → честный 409
      ("нельзя отозвать опубликованное"). Локальный статус НЕ меняем.
    * ``cancelled`` — идемпотентно возвращаем как есть.
    * есть ``publer_post_id`` и пост ещё не опубликован → ``DELETE /posts``
      на стороне Publer, затем локальный статус ``cancelled``.
    * только ``publer_job_id`` без ``publer_post_id`` (запланирован, но id
      поста ещё не сверен) → отозвать по документированному API нельзя без
      id поста → честный 409, локальный статус НЕ трогаем.
    * нет publer-id (draft/queued, в Publer не отправлялось) → отзывать
      нечего, просто флипаем локальный статус в ``cancelled``.
    """
    async with session_scope() as db:
        row = await scheduler_campaigns_store.get_assignment(db, assignment_id)
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"assignment {assignment_id} not found",
            )

        if row.status == AssignmentStatus.cancelled.value:
            return AssignmentRead.from_row(row)

        if row.status == AssignmentStatus.published.value:
            log.info(
                "assignment_cancel_refused_published",
                assignment_id=assignment_id,
                publer_post_id=row.publer_post_id,
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="нельзя отозвать опубликованное",
            )

        if row.publer_post_id:
            try:
                async with PublerClient(settings) as client:
                    deleted = await client.delete_posts([row.publer_post_id])
            except PublerClientError as exc:
                log.warning(
                    "assignment_cancel_publer_delete_failed",
                    assignment_id=assignment_id,
                    publer_post_id=row.publer_post_id,
                    error=str(exc),
                )
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=(
                        "не удалось отозвать пост в Publer — статус не изменён, "
                        f"повторите попытку: {exc}"
                    ),
                ) from exc
            log.info(
                "assignment_cancel_publer_deleted",
                assignment_id=assignment_id,
                publer_post_id=row.publer_post_id,
                deleted_ids=deleted,
            )
        elif row.publer_job_id:
            log.info(
                "assignment_cancel_refused_unresolved",
                assignment_id=assignment_id,
                publer_job_id=row.publer_job_id,
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "пост запланирован в Publer, но его id ещё не сверён — "
                    "отозвать сейчас нельзя, повторите позже"
                ),
            )
        else:
            log.info(
                "assignment_cancel_local_only",
                assignment_id=assignment_id,
                prev_status=row.status,
            )

        row.status = AssignmentStatus.cancelled.value
        await db.flush()
        await db.refresh(row)
        return AssignmentRead.from_row(row)


@router.post(
    "/assignments/{assignment_id}/retry", response_model=AssignmentRead
)
async def retry_assignment(assignment_id: int) -> AssignmentRead:
    """Сбросить failed/cancelled assignment в queued (attempts=0).

    Worker подхватит на ближайшем tick и попробует снова. Если
    уже есть ``publer_media_id`` — переиспользуется (media не заливается
    повторно).
    """
    async with session_scope() as db:
        row = await scheduler_campaigns_store.get_assignment(db, assignment_id)
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"assignment {assignment_id} not found",
            )
        if row.status not in {
            AssignmentStatus.failed.value,
            AssignmentStatus.cancelled.value,
        }:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Retry доступен только для failed/cancelled "
                    f"(текущий: {row.status})"
                ),
            )
        updated = await scheduler_campaigns_store.update_assignment(
            db,
            assignment_id,
            status=AssignmentStatus.queued.value,
            attempts=0,
            error_message=None,
        )
        assert updated is not None
        return AssignmentRead.from_row(updated)


# ────────────────────────── manual publish ──────────────────────────


@router.post(
    "/manual/publish-one",
    response_model=AssignmentRead,
    status_code=status.HTTP_201_CREATED,
)
async def manual_publish_one(
    payload: ManualPublishRequest,
    settings: Settings = Depends(get_settings),
) -> AssignmentRead:
    """Быстрая одноразовая публикация одного рилса без мастера кампаний.

    Создаёт однорильсовую ``Campaign`` со статусом ``approved`` + один
    ``Assignment`` сразу в ``queued`` — delivery-worker подхватит по
    ``scheduled_at_utc``. Если передан ``custom_caption`` — используется
    как есть (плюс пресеты); иначе — генерим через ``caption_generator``.
    """
    artifacts = _artifact_manager()
    async with session_scope() as db:
        profile = await account_profiles_store.get_profile(
            db, payload.publer_account_id
        )
        if profile is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"account profile {payload.publer_account_id} not found — "
                    "сначала создайте профиль через PUT /accounts/profiles/{id}"
                ),
            )

        job_id, reel_plan, _ = await _load_reel_plan_for_artifact(
            db, artifacts=artifacts, artifact_id=payload.reel_artifact_id
        )
        if job_id != payload.job_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"reel artifact {payload.reel_artifact_id} принадлежит "
                    f"job {job_id}, а в payload передан {payload.job_id}"
                ),
            )

        if payload.custom_caption:
            caption_text = payload.custom_caption
            title_text = (
                payload.custom_title or ""
                if profile.network == PublerNetwork.youtube.value
                else ""
            )
            hashtags: list[str] = list(profile.default_hashtags_json or [])
        else:
            llm = _build_flash_lite_client(settings)
            generated = await generate_caption(
                reel=reel_plan, profile=profile, llm=llm
            )
            caption_text = generated.caption
            title_text = (
                payload.custom_title
                if payload.custom_title is not None
                else generated.title
                if profile.network == PublerNetwork.youtube.value
                else ""
            )
            hashtags = generated.hashtags

        presets = await account_profiles_store.list_presets_for_scope(
            db, account_id=payload.publer_account_id
        )
        final_caption, applied_ids = apply_presets(
            generated_caption=caption_text, presets=list(presets)
        )

        # Одиночная manual-кампания: сразу approved.
        # Явный UTC — без TZ-зависимости сервера (astimezone() без аргумента
        # берёт локальный TZ env, что портит consistency имён кампаний).
        scheduled_utc = payload.scheduled_at_utc.astimezone(
            ZoneInfo("UTC")
        ).strftime("%Y-%m-%d %H:%M UTC")
        campaign = await scheduler_campaigns_store.create_campaign(
            db,
            name=f"Manual {scheduled_utc}",
            tz="UTC",
            time_of_day=payload.scheduled_at_utc.strftime("%H:%M"),
            dates=[payload.scheduled_at_utc.strftime("%Y-%m-%d")],
            status="approved",
        )
        assignment = await scheduler_campaigns_store.create_assignment(
            db,
            campaign_id=campaign.id,
            job_id=job_id,
            reel_artifact_id=payload.reel_artifact_id,
            publer_account_id=payload.publer_account_id,
            network=profile.network,
            title=title_text,
            caption=final_caption,
            hashtags=hashtags,
            applied_preset_ids=applied_ids,
            scheduled_at_utc=payload.scheduled_at_utc,
            status=AssignmentStatus.queued.value,
        )
        return AssignmentRead.from_row(assignment)


__all__ = ["router"]
