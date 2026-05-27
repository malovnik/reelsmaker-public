"""/api/v1/jobs — CRUD + SSE progress stream.

SSE-паттерн адаптирован из
universal-rag/packages/backend/app/api/routes/upload.py:468-503.
Формат: `data: {json}\\n\\n`, стадии: created/ingest/transcribe/.../done/error.
Keepalive: один пустой комментарий каждые 15 секунд.
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
from collections.abc import AsyncIterator, Mapping
from pathlib import Path
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from videomaker.core.artifacts import ArtifactsManager
from videomaker.core.config import Settings, get_settings
from videomaker.core.logging import get_logger
from videomaker.models.job import (
    ArtifactLikeUpdate,
    ArtifactRead,
    JobCreate,
    JobProfileUpdate,
    JobRead,
    JobStatus,
    SavedReelsRequest,
    SavedReelsResponse,
    SubtitleStyleConfig,
    VisionProfile,
)
from videomaker.models.post_production import PostProductionConfig
from videomaker.services import post_production_store, subtitle_store
from videomaker.services.jobs import JobService, get_job_service
from videomaker.services.pipeline import run_pipeline_safe
from videomaker.services.post_production_store import PresetNotFoundError
from videomaker.services.profile_detector import (
    ProfileSuggestion,
    detect_profile,
    estimate_face_coverage,
)
from videomaker.services.transcribers.cache import TranscriptCache

router = APIRouter(prefix="/jobs", tags=["jobs"])
log = get_logger(__name__)

KEEPALIVE_INTERVAL_SEC = 15.0


def get_artifacts_manager() -> ArtifactsManager:
    return ArtifactsManager()


@router.get("", response_model=list[JobRead])
async def list_jobs(
    limit: int = 50,
    service: JobService = Depends(get_job_service),
) -> list[JobRead]:
    jobs = await service.list_jobs(limit=limit)
    return [JobRead.model_validate(job) for job in jobs]


SUPPORTED_SOURCE_LANGS = frozenset(
    {"auto", "ru", "en", "de", "es", "fr", "it", "pt", "zh", "ja", "ko"}
)


@router.post("", response_model=JobRead, status_code=status.HTTP_201_CREATED)
async def create_job(
    file: UploadFile = File(..., description="Исходное видео"),
    transcriber: str = Form(default="stable_ts_mlx"),
    llm_provider: str = Form(default="gemini"),
    llm_model: str = Form(default="gemini-3.1-flash-lite-preview"),
    target_aspect: str = Form(default="9:16"),
    fit_mode: str = Form(default="fill"),
    source_language: str = Form(default="auto"),
    subtitle_style_preset_id: int | None = Form(default=None),
    subtitle_style_inline: str | None = Form(
        default=None,
        description="Inline JSON с SubtitleStyleConfig — переопределяет preset_id",
    ),
    post_production_preset_id: int | None = Form(
        default=None,
        description="ID PostProductionPreset. None → пост-продакшн не применяется",
    ),
    post_production_overrides_json: str | None = Form(
        default=None,
        description=(
            "JSON dict с per-job override опций пресета. Ключи: enable_intro, "
            "enable_outro, enable_zoom, enable_loudnorm (все default True). "
            "False = занулить соответствующее поле в snapshot конфига."
        ),
    ),
    use_proxy: bool = Form(
        default=True,
        description=(
            "Если True (default) — pipeline генерирует 1080p H.264 proxy после ingest "
            "и работает с ним для всех downstream stages. False = напрямую с source."
        ),
    ),
    use_source_for_render: bool = Form(
        default=False,
        description=(
            "Если True — финальный render берёт source 4K (медленнее, max качество). "
            "Default False — render использует proxy (быстрее, 1080p достаточно для 9:16)."
        ),
    ),
    target_reel_count: int | None = Form(
        default=None,
        ge=3,
        le=225,
        description=(
            "Override кол-ва рилсов (3-225). None → auto по длительности источника "
            "(12 рилсов на 20 мин видео, tolerance ±3 per 20-min block). "
            "225 соответствует 5-часовому видео на пределе."
        ),
    ),
    force_reingest: bool = Form(
        default=False,
        description=(
            "Если True — игнорировать transcript cache и заново транскрибировать. "
            "По умолчанию False (повторные прогоны того же SHA256 используют кэш)."
        ),
    ),
    vision_profile: VisionProfile = Form(
        default=VisionProfile.talking_head,
        description=(
            "Профиль нарезки: talking_head (default, все text-агенты + face "
            "centering gate), fashion (убирает humor/irony/thesis, приоритет "
            "визуалу), travel, screencast, custom."
        ),
    ),
    composer_strategy_override: str | None = Form(
        default=None,
        description=(
            "T9 — override стратегии композитора: tight_context / balanced / "
            "thematic_free. None (default) → advisor выбирает сам по аудио-"
            "профилю. Сохраняется в job.options['composer_strategy_override'] "
            "и применяется перед запуском pipeline'а."
        ),
    ),
    split_screen_enabled: bool | None = Form(
        default=None,
        description=(
            "Per-job override для split-screen. None — используется значение "
            "из preset; True/False — переопределяет. Не имеет эффекта если "
            "пресет не содержит companion_asset."
        ),
    ),
    custom_system_prompt: str | None = Form(
        default=None,
        description=(
            "Опциональный текст — добавляется в самое начало system-prompt "
            "всех LLM-вызовов этого job'а. Пусто/None → без изменений "
            "(поведение идентично предыдущим job'ам). Обрезается по 8000 знаков."
        ),
        max_length=8000,
    ),
    settings: Settings = Depends(get_settings),
    service: JobService = Depends(get_job_service),
    artifacts: ArtifactsManager = Depends(get_artifacts_manager),
) -> JobRead:
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="file.filename is empty",
        )
    if transcriber not in settings.available_transcribers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"transcriber '{transcriber}' not available. "
                f"Available: {settings.available_transcribers}"
            ),
        )
    if llm_provider not in settings.available_llm_providers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"LLM provider '{llm_provider}' not configured. "
                f"Configured: {settings.available_llm_providers}"
            ),
        )
    if target_aspect not in {"9:16", "16:9", "1:1", "4:5"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unsupported aspect ratio: {target_aspect}",
        )
    if fit_mode not in {"fill", "fit"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unsupported fit_mode: {fit_mode}",
        )
    if source_language not in SUPPORTED_SOURCE_LANGS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unsupported source_language: {source_language}",
        )
    if composer_strategy_override is not None and composer_strategy_override not in {
        "tight_context",
        "balanced",
        "thematic_free",
    }:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"unsupported composer_strategy_override: "
                f"{composer_strategy_override!r} — "
                "allowed: tight_context, balanced, thematic_free"
            ),
        )

    subtitle_style = await _resolve_subtitle_style(
        preset_id=subtitle_style_preset_id,
        inline_json=subtitle_style_inline,
    )

    post_production_config = await _resolve_post_production_config(
        preset_id=post_production_preset_id,
        overrides_json=post_production_overrides_json,
        split_screen_enabled=split_screen_enabled,
    )

    settings.ensure_directories()
    job_id = service.new_id()
    job_upload_dir = settings.app_upload_dir / job_id
    job_upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = _safe_filename(file.filename)
    target_path = job_upload_dir / safe_name
    size_bytes = await _save_upload(file, target_path, settings.max_upload_size_bytes)

    artifacts.ensure_layout(job_id)

    options: dict[str, Any] = {}
    if composer_strategy_override is not None:
        options["composer_strategy_override"] = composer_strategy_override

    normalized_custom_prompt = (
        custom_system_prompt.strip()
        if custom_system_prompt is not None and custom_system_prompt.strip()
        else None
    )

    payload = JobCreate(
        transcriber=transcriber,
        llm_provider=llm_provider,
        llm_model=llm_model,
        target_aspect=target_aspect,
        fit_mode=fit_mode,
        source_language=source_language,
        subtitle_style=subtitle_style,
        post_production_preset_id=post_production_preset_id,
        use_proxy=use_proxy,
        use_source_for_render=use_source_for_render,
        target_reel_count=target_reel_count,
        force_reingest=force_reingest,
        vision_profile=vision_profile,
        custom_system_prompt=normalized_custom_prompt,
        options=options,
    )
    job = await service.create(
        source_path=str(target_path),
        source_filename=safe_name,
        source_size_bytes=size_bytes,
        payload=payload,
        job_id=job_id,
        post_production_config_json=(
            post_production_config.model_dump(mode="json")
            if post_production_config is not None
            else None
        ),
    )
    _schedule_pipeline(
        job_id=job_id,
        source_path=target_path,
        transcriber_name=transcriber,
        llm_provider=llm_provider,
        llm_model=llm_model,
        target_aspect=target_aspect,
        fit_mode=fit_mode,
        source_language=source_language,
        subtitle_style=subtitle_style,
        post_production_config=post_production_config,
        use_proxy=use_proxy,
        use_source_for_render=use_source_for_render,
        target_reel_count=target_reel_count,
        force_reingest=force_reingest,
        vision_profile=vision_profile,
        custom_system_prompt=normalized_custom_prompt,
        service=service,
        artifacts=artifacts,
        settings=settings,
    )
    return JobRead.model_validate(job)


async def _resolve_subtitle_style(
    *, preset_id: int | None, inline_json: str | None
) -> SubtitleStyleConfig | None:
    """Разрешает subtitle_style из формы.

    Приоритет: inline_json > preset_id > default preset > None.
    Валидация значений происходит через Pydantic.
    """

    if inline_json:
        try:
            parsed = json.loads(inline_json)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"subtitle_style_inline is not valid JSON: {exc}",
            ) from exc
        try:
            return SubtitleStyleConfig.model_validate(parsed)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"invalid subtitle style config: {exc}",
            ) from exc

    if preset_id is not None:
        row = await subtitle_store.get_preset(preset_id)
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"subtitle preset {preset_id} not found",
            )
        return SubtitleStyleConfig.model_validate(row.style_json)

    default_row = await subtitle_store.get_default_preset()
    if default_row is None:
        return None
    return SubtitleStyleConfig.model_validate(default_row.style_json)


async def _resolve_post_production_config(
    *,
    preset_id: int | None,
    overrides_json: str | None = None,
    split_screen_enabled: bool | None = None,
) -> PostProductionConfig | None:
    """Строит snapshot PostProductionConfig для указанного preset_id с per-job overrides.

    None → пост-продакшн полностью отключён для этого job.

    overrides_json (JSON dict с ключами enable_intro/enable_outro/enable_zoom/
    enable_loudnorm/enable_bw) применяется к snapshot ПОСЛЕ resolve пресета:
    * enable_intro=False → snapshot.intro_path = None
    * enable_outro=False → snapshot.outro_path = None
    * enable_zoom=False → snapshot.zoom_enabled = False
    * enable_loudnorm=False → snapshot.audio_normalize_enabled = False
    * enable_bw=False → snapshot.bw_enabled = False
    Отсутствующие ключи / overrides_json=None — поведение пресета as-is.

    split_screen_enabled (per-job override): None → as-is из пресета;
    True/False — переопределяет snapshot.split_screen.enabled.
    """

    if preset_id is None:
        return None
    try:
        preset, intro, outro, companion = await post_production_store.get_preset_with_assets(preset_id)
    except PresetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    snapshot = post_production_store.build_snapshot(preset, intro, outro, companion)

    if overrides_json is not None and overrides_json.strip():
        try:
            overrides = json.loads(overrides_json)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"post_production_overrides_json is not valid JSON: {exc}",
            ) from exc
        if not isinstance(overrides, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="post_production_overrides_json must be a JSON object",
            )
        snapshot = _apply_post_production_overrides(snapshot, overrides)

    if split_screen_enabled is not None:
        snapshot = snapshot.model_copy(update={
            "split_screen": snapshot.split_screen.model_copy(
                update={"enabled": split_screen_enabled},
            ),
        })

    return snapshot


def _apply_post_production_overrides(
    snapshot: PostProductionConfig,
    overrides: dict[str, object],
) -> PostProductionConfig:
    """Применяет dict overrides к snapshot конфига. Возвращает НОВЫЙ объект."""

    disabled: list[str] = []
    intro_path = snapshot.intro_path
    outro_path = snapshot.outro_path
    zoom_enabled = snapshot.zoom_enabled
    audio_normalize_enabled = snapshot.audio_normalize_enabled
    bw_enabled = snapshot.bw_enabled

    if overrides.get("enable_intro") is False:
        intro_path = None
        disabled.append("intro")
    if overrides.get("enable_outro") is False:
        outro_path = None
        disabled.append("outro")
    if overrides.get("enable_zoom") is False:
        zoom_enabled = False
        disabled.append("zoom")
    if overrides.get("enable_loudnorm") is False:
        audio_normalize_enabled = False
        disabled.append("loudnorm")
    if overrides.get("enable_bw") is False:
        bw_enabled = False
        disabled.append("bw")

    if not disabled:
        return snapshot

    log.info("post_production_overrides_applied", disabled=disabled)
    return snapshot.model_copy(
        update={
            "intro_path": intro_path,
            "outro_path": outro_path,
            "zoom_enabled": zoom_enabled,
            "audio_normalize_enabled": audio_normalize_enabled,
            "bw_enabled": bw_enabled,
        }
    )


@router.get("/artifacts/liked", response_model=list[ArtifactRead])
async def list_liked_reels(
    project_id: int | None = None,
    job_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    service: JobService = Depends(get_job_service),
) -> list[ArtifactRead]:
    """Все лайкнутые рилсы (``kind='reel_output'`` + ``meta.liked='like'``).

    Фильтры ``project_id`` (через ``Job.project_id``) и ``job_id``. Используется
    scheduler UI для выбора пула рилсов при создании Publer-кампании.

    Роут зарегистрирован ДО ``/{job_id}``-эндпоинтов — иначе FastAPI матчит
    ``artifacts`` как ``job_id`` и возвращает 422.
    """
    rows = await service.list_liked_reels(
        project_id=project_id, job_id=job_id, limit=limit
    )
    return [ArtifactRead.model_validate(r) for r in rows]


@router.get("/{job_id}", response_model=JobRead)
async def get_job(
    job_id: str,
    service: JobService = Depends(get_job_service),
) -> JobRead:
    job = await service.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"job {job_id} not found",
        )
    return JobRead.model_validate(job)


@router.get("/{job_id}/source-thumbnail", response_class=Response)
async def get_source_thumbnail(
    job_id: str,
    settings: Settings = Depends(get_settings),
) -> Response:
    """Возвращает первый кадр source-видео job'а из data/thumbnails/.

    Генерируется на stage 'ingest' (см. pipeline.py). Если job ещё не дошёл
    до ingest — 404.
    """

    thumb_path = settings.app_thumbnails_dir / f"{job_id}.jpg"
    if not thumb_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"thumbnail for job {job_id} not generated yet",
        )
    return Response(
        content=thumb_path.read_bytes(),
        media_type="image/jpeg",
    )


class JobRenamePayload(BaseModel):
    """Payload для PATCH /jobs/{id}/rename — пользовательское имя пакета."""

    display_name: str | None = Field(default=None, max_length=256)


@router.patch("/{job_id}/rename", response_model=JobRead)
async def rename_job(
    job_id: str,
    payload: JobRenamePayload,
    service: JobService = Depends(get_job_service),
) -> JobRead:
    """Переименование пакета нарезок. Пустая строка → сброс к source_filename."""

    job = await service.update_display_name(
        job_id, display_name=payload.display_name
    )
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"job {job_id} not found",
        )
    return JobRead.model_validate(job)


@router.patch("/{job_id}/profile", response_model=JobRead)
async def update_job_profile(
    job_id: str,
    payload: JobProfileUpdate,
    service: JobService = Depends(get_job_service),
) -> JobRead:
    """Смена vision_profile на существующем job.

    Работает на любой стадии — фронт может поменять профиль до старта
    pipeline (например по auto-detect suggestion) или после завершения
    (для отображения). Pipeline НЕ перезапускается автоматически — для
    re-run создаётся новый Job с желаемым профилем.
    """
    job = await service.update_vision_profile(job_id, profile=payload.profile)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"job {job_id} not found",
        )
    return JobRead.model_validate(job)


@router.get("/{job_id}/profile/suggestion", response_model=ProfileSuggestion)
async def get_profile_suggestion(
    job_id: str,
    service: JobService = Depends(get_job_service),
    settings: Settings = Depends(get_settings),
) -> ProfileSuggestion:
    """Рекомендация VisionProfile на основе кэшированного транскрипта и
    (опционально) vision-кэша для того же SHA256.

    Возвращает 409 если транскрипт ещё не готов (Stage 2 не завершена).
    Vision face coverage — опционально: если cache пуст, эвристика работает
    по одному WPM + silence_ratio.
    """
    job = await service.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"job {job_id} not found",
        )
    source_path = Path(job.source_path)
    if not source_path.exists():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="source file missing — cannot compute suggestion",
        )
    cache = TranscriptCache(settings.transcript_cache_dir)
    entry = await cache.lookup(source_path)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "transcript not cached yet — wait for Stage 2 (transcribe) "
                "to complete before requesting profile suggestion"
            ),
        )
    face_estimate = estimate_face_coverage(settings.vision_cache_dir, entry.video_hash)
    return detect_profile(
        entry.result,
        face_coverage=face_estimate.coverage,
        vision_frames_sampled=face_estimate.frames_sampled,
    )


class AutoAnalyzeDecisionResponse(BaseModel):
    """Decision entry для UI Summary Card."""

    parameter: str
    value: Any
    confidence: float
    source: str
    reasoning: str


class AutoAnalyzeResponse(BaseModel):
    """T11.4 — AutoConfigSummary для UI (Auto/Manual toggle + Summary Card)."""

    job_id: str
    pacing_profile: str
    snap_strategy: str
    composer_strategy: str

    pause_compression_enabled: bool
    pause_compression_threshold_sec: float
    pause_compression_keep_sec: float
    breath_compression_enabled: bool
    filler_words_removal_enabled: bool

    punchline_pause_enabled: bool
    punchline_hold_after_sec: float

    punch_in_zoom_enabled: bool
    punch_in_zoom_scale: float
    punch_in_zoom_probability: float

    ken_burns_drift_enabled: bool
    ken_burns_scale_per_sec: float

    coherence_threshold: float
    rhythm_aware_cuts_enabled: bool

    meta_confidence: float
    warnings: list[str]
    decisions: list[AutoAnalyzeDecisionResponse]
    llm_fallback_applied: bool

    audio_features: dict[str, Any]


@router.post("/{job_id}/auto-analyze", response_model=AutoAnalyzeResponse)
async def auto_analyze_job(
    job_id: str,
    service: JobService = Depends(get_job_service),
    settings: Settings = Depends(get_settings),
) -> AutoAnalyzeResponse:
    """T11.4 — Automatic Mode: анализирует audio job'а и возвращает
    предлагаемый AutoConfig для UI AutoConfigSummary card.

    Использует `services/audio_analyzer` для feature extraction +
    `services/auto_config_advisor` для rule tree decisions +
    `services/auto_config_llm_fallback` (при confidence<0.4) для
    LLM-refined narrative decisions.

    Возвращает 409 если аудио ещё не готово (Stage 1 не завершена).
    Результат — это РЕКОМЕНДАЦИЯ, user может принять или переопределить
    параметры вручную (Manual mode toggle).
    """
    from videomaker.services.audio_analyzer import extract_audio_profile
    from videomaker.services.auto_config_advisor import advise_config
    from videomaker.services.auto_config_llm_fallback import llm_narrative_advise

    job = await service.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"job {job_id} not found",
        )

    source_path = Path(job.source_path)
    if not source_path.exists():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="source file missing — cannot auto-analyze",
        )

    cache = TranscriptCache(settings.transcript_cache_dir)
    entry = await cache.lookup(source_path)
    transcript_segments = entry.result.segments if entry is not None else None

    artifacts = ArtifactsManager()
    audio_candidate = artifacts.job_dir(job_id) / "audio" / "source.wav"
    audio_path = audio_candidate if audio_candidate.exists() else source_path

    profile = await extract_audio_profile(
        audio_path,
        transcript_segments=transcript_segments,
        total_duration_sec=None,
        content_type_hint=(job.vision_profile or "unknown"),
    )

    cfg = advise_config(
        profile,
        post_production_config=job.post_production_config_json,
    )
    llm_fallback_applied = False
    if cfg.requires_llm_fallback and entry is not None:
        transcript_summary = " ".join(
            seg.text for seg in transcript_segments[:50] if seg.text
        ) if transcript_segments else ""
        cfg = await llm_narrative_advise(
            rule_config=cfg,
            audio_profile=profile,
            transcript_summary=transcript_summary,
        )
        llm_fallback_applied = not cfg.requires_llm_fallback

    return AutoAnalyzeResponse(
        job_id=job_id,
        pacing_profile=cfg.pacing_profile,
        snap_strategy=cfg.snap_strategy,
        composer_strategy=cfg.composer_strategy,
        pause_compression_enabled=cfg.pause_compression_enabled,
        pause_compression_threshold_sec=cfg.pause_compression_threshold_sec,
        pause_compression_keep_sec=cfg.pause_compression_keep_sec,
        breath_compression_enabled=cfg.breath_compression_enabled,
        filler_words_removal_enabled=cfg.filler_words_removal_enabled,
        punchline_pause_enabled=cfg.punchline_pause_enabled,
        punchline_hold_after_sec=cfg.punchline_hold_after_sec,
        punch_in_zoom_enabled=cfg.punch_in_zoom_enabled,
        punch_in_zoom_scale=cfg.punch_in_zoom_scale,
        punch_in_zoom_probability=cfg.punch_in_zoom_probability,
        ken_burns_drift_enabled=cfg.ken_burns_drift_enabled,
        ken_burns_scale_per_sec=cfg.ken_burns_scale_per_sec,
        coherence_threshold=cfg.coherence_threshold,
        rhythm_aware_cuts_enabled=cfg.rhythm_aware_cuts_enabled,
        meta_confidence=cfg.meta_confidence,
        warnings=cfg.warnings,
        decisions=[
            AutoAnalyzeDecisionResponse(
                parameter=e.parameter,
                value=e.value,
                confidence=e.confidence,
                source=e.source,
                reasoning=e.reasoning,
            )
            for e in cfg.evidence
        ],
        llm_fallback_applied=llm_fallback_applied,
        audio_features={
            "snr_db": round(profile.snr_db, 1),
            "wps": round(profile.wps, 2),
            "pitch_std_hz": round(profile.pitch_std_hz, 1),
            "lra_lu": round(profile.lra_lu, 1),
            "mean_gap_sec": round(profile.mean_gap_sec, 2),
            "gap_kurtosis": round(profile.gap_kurtosis, 2),
            "rhythm_cv": round(profile.rhythm_cv, 3),
            "whisper_confidence": round(profile.whisper_avg_confidence, 2),
            "total_duration_sec": round(profile.total_duration_sec, 1),
            "speech_duration_sec": round(profile.speech_duration_sec, 1),
            "num_words": profile.num_words,
            "extraction_ms": profile.extraction_ms,
            "failures": profile.failures,
        },
    )


class AutoConfigApplyPayload(BaseModel):
    """T11 — Payload для PATCH /auto-config.

    Принимает subset полей из AutoAnalyzeResponse которые надо применить
    к pipeline для этого конкретного job'а. Сохраняется в job.options
    как ``auto_config`` + включает pipeline_mode='automatic'.
    """

    pacing_profile: str | None = None
    snap_strategy: str | None = None
    pause_compression_enabled: bool | None = None
    pause_compression_threshold_sec: float | None = None
    pause_compression_keep_sec: float | None = None
    breath_compression_enabled: bool | None = None
    filler_words_removal_enabled: bool | None = None
    punchline_pause_enabled: bool | None = None
    punchline_hold_after_sec: float | None = None
    punch_in_zoom_enabled: bool | None = None
    punch_in_zoom_scale: float | None = None
    punch_in_zoom_probability: float | None = None
    ken_burns_drift_enabled: bool | None = None
    ken_burns_scale_per_sec: float | None = None
    coherence_threshold: float | None = None
    rhythm_aware_cuts_enabled: bool | None = None
    onset_snap_max_shift_sec: float | None = None


class AutoConfigApplyResponse(BaseModel):
    job_id: str
    pipeline_mode: str
    applied_keys: list[str]


@router.patch("/{job_id}/auto-config", response_model=AutoConfigApplyResponse)
async def apply_auto_config(
    job_id: str,
    payload: AutoConfigApplyPayload,
    service: JobService = Depends(get_job_service),
) -> AutoConfigApplyResponse:
    """T11 — Сохраняет AutoConfig в job.options для применения pipeline'ом.

    При запуске run_pipeline_safe backend проверит job.options["auto_config"]
    + pipeline_mode == 'automatic' и оберёт весь pipeline в
    job_settings_override — новые настройки применятся per-job без
    затрагивания глобального runtime_settings.
    """
    job = await service.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"job {job_id} not found",
        )

    data = payload.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="payload empty — provide at least one auto_config field",
        )

    auto_config = {"pipeline_mode": "automatic", **data}
    await service.update_options(job_id, {"auto_config": auto_config})

    return AutoConfigApplyResponse(
        job_id=job_id,
        pipeline_mode="automatic",
        applied_keys=sorted(data.keys()),
    )


@router.delete("/{job_id}/auto-config", status_code=status.HTTP_200_OK)
async def clear_auto_config(
    job_id: str,
    service: JobService = Depends(get_job_service),
) -> dict[str, str]:
    """Переключает job обратно в Manual mode (удаляет auto_config)."""
    job = await service.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"job {job_id} not found",
        )
    await service.update_options(job_id, {"auto_config": None})
    return {"job_id": job_id, "pipeline_mode": "manual"}


@router.get("/{job_id}/artifacts", response_model=list[ArtifactRead])
async def list_job_artifacts(
    job_id: str,
    service: JobService = Depends(get_job_service),
) -> list[ArtifactRead]:
    job = await service.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"job {job_id} not found",
        )
    artifacts_list = await service.list_artifacts(job_id)
    return [ArtifactRead.model_validate(a) for a in artifacts_list]


@router.patch(
    "/{job_id}/artifacts/{artifact_id}/like",
    response_model=ArtifactRead,
)
async def update_artifact_like(
    job_id: str,
    artifact_id: int,
    payload: ArtifactLikeUpdate,
    service: JobService = Depends(get_job_service),
    settings: Settings = Depends(get_settings),
    artifacts: ArtifactsManager = Depends(get_artifacts_manager),
) -> ArtifactRead:
    """Проставить оценку артефакта (используется для рилсов: ``none``/``like``/``dislike``).

    Оценка хранится в ``Artifact.meta['liked']`` — отдельной колонки нет.

    T6.1: при ``liked == 'like'`` считается 256-dim Gemini embedding hook-фразы
    и сохраняется в ``Artifact.embedding_json``. Это питает cosine retrieval
    в preference_memory. При сбое embedding API запись лайка всё равно
    проходит — fallback на legacy top-by-date работает всегда.
    """
    job = await service.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"job {job_id} not found",
        )
    updated = await service.update_artifact_meta(
        job_id, artifact_id, patch={"liked": payload.liked}
    )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"artifact {artifact_id} not found in job {job_id}",
        )

    if payload.liked == "like":
        await _persist_like_embedding_best_effort(
            service=service,
            artifacts=artifacts,
            settings=settings,
            job_id=job_id,
            artifact_id=artifact_id,
            meta=updated.meta,
        )
        refreshed = await service.get_artifact(job_id, artifact_id)
        if refreshed is not None:
            return ArtifactRead.model_validate(refreshed)

    return ArtifactRead.model_validate(updated)


async def _persist_like_embedding_best_effort(
    *,
    service: JobService,
    artifacts: ArtifactsManager,
    settings: Settings,
    job_id: str,
    artifact_id: int,
    meta: dict[str, Any],
) -> None:
    """Считает Gemini embedding для hook-фразы и сохраняет в artifact.

    Graceful-degrade: любое исключение (нет hook, embed API упал,
    reel_plan.json битый) гасится логом. Like остаётся валидным,
    preference_memory делает fallback на top-by-date.
    """
    from videomaker.services.canvas_embedder import embed_texts

    try:
        hook = _resolve_liked_hook_text(
            artifacts=artifacts, job_id=job_id, meta=meta
        )
        if not hook:
            log.info(
                "like_embedding_skipped_no_hook",
                job_id=job_id,
                artifact_id=artifact_id,
            )
            return
        embeddings = await embed_texts([hook], settings=settings)
        if not embeddings or not embeddings[0]:
            log.warning(
                "like_embedding_empty_result",
                job_id=job_id,
                artifact_id=artifact_id,
            )
            return
        await service.update_artifact_embedding(
            job_id, artifact_id, embedding=embeddings[0]
        )
        log.info(
            "like_embedding_stored",
            job_id=job_id,
            artifact_id=artifact_id,
            dim=len(embeddings[0]),
        )
    except Exception as exc:  # pragma: no cover — best-effort
        log.warning(
            "like_embedding_failed",
            job_id=job_id,
            artifact_id=artifact_id,
            error=str(exc),
        )


def _resolve_liked_hook_text(
    *,
    artifacts: ArtifactsManager,
    job_id: str,
    meta: dict[str, Any],
) -> str | None:
    """Достаёт hook-строку для лайкнутого рилса.

    Порядок: meta['hook'] → reel_plan.json[reel_id].hook. Повторяет
    логику preference_memory._extract_hook_for_liked без импорта private
    API (переиспользование ограничено потому что тот модуль сугубо
    async, а здесь нет нужды).
    """
    direct = meta.get("hook")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    reel_id = meta.get("reel_id")
    if not reel_id:
        return None

    try:
        reel_plan_path = artifacts.job_dir(job_id) / "reel_plan.json"
    except Exception:
        return None
    if not reel_plan_path.exists():
        return None

    try:
        data = json.loads(reel_plan_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    for reel in data.get("reels") or []:
        if not isinstance(reel, dict):
            continue
        if reel.get("reel_id") == reel_id:
            hook = reel.get("hook")
            if isinstance(hook, str) and hook.strip():
                return hook.strip()
            break
    return None



@router.delete(
    "/{job_id}/artifacts/{artifact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_job_artifact(
    job_id: str,
    artifact_id: int,
    service: JobService = Depends(get_job_service),
    artifacts: ArtifactsManager = Depends(get_artifacts_manager),
) -> Response:
    """Удаляет ``reel_output`` артефакт (запись в БД + mp4 + субтитры).

    Защищён `allowed_kinds={reel_output}` — не трогает ``proxy``, ``transcript``
    и прочие артефакты pipeline. Дизайн: удалить рилс не должно инвалидировать
    транскрипт или рабочую копию (их снова использовать при перезапуске).
    """
    job = await service.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"job {job_id} not found",
        )
    try:
        deleted = await service.delete_artifact(
            job_id,
            artifact_id,
            artifacts_manager=artifacts,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"artifact {artifact_id} not found in job {job_id}",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{job_id}", status_code=status.HTTP_200_OK)
async def delete_job(
    job_id: str,
    purge: str = "soft",
    service: JobService = Depends(get_job_service),
    artifacts: ArtifactsManager = Depends(get_artifacts_manager),
) -> dict[str, Any]:
    """Удаляет job.

    * ``purge=soft`` (по умолчанию) — скрывает job из списка, файлы остаются.
    * ``purge=hard`` — скрывает + удаляет mp4 рилсов БЕЗ лайка. Прокси,
      транскрипт и отлайканные рилсы сохраняются всегда.
    * ``purge=nuke`` — полная зачистка: source upload, artifacts-директория,
      job row в БД и все артефакт-записи. Ничего не остаётся (деструктивно).
    """
    job = await service.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"job {job_id} not found",
        )
    try:
        summary = await service.delete_job(
            job_id,
            purge=purge,
            artifacts_manager=artifacts,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return summary


@router.post("/{job_id}/cancel", status_code=status.HTTP_200_OK)
async def cancel_job(
    job_id: str,
    service: JobService = Depends(get_job_service),
) -> dict[str, Any]:
    """Отменяет выполняющийся job: отменяет asyncio-task pipeline и ставит
    статус ``cancelled``.

    Если pipeline уже завершён (done/error/cancelled) — возвращает текущий
    статус без изменений. Если задача ещё выполняется — посылает
    ``Task.cancel()`` (внутри pipeline это пробрасывается как CancelledError
    и НЕ превращается в error) и помечает job cancelled.
    """
    job = await service.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"job {job_id} not found",
        )
    if job.status in (JobStatus.done, JobStatus.error, JobStatus.cancelled):
        return {"job_id": job_id, "status": job.status.value, "cancelled": False}

    task = _find_pipeline_task(job_id)
    if task is not None and not task.done():
        task.cancel()
    await service.mark_cancelled(job_id, message="отменено пользователем")
    return {"job_id": job_id, "status": JobStatus.cancelled.value, "cancelled": True}


@router.post(
    "/{job_id}/saved",
    response_model=SavedReelsResponse,
    status_code=status.HTTP_201_CREATED,
)
async def copy_reels_to_saved(
    job_id: str,
    payload: SavedReelsRequest,
    service: JobService = Depends(get_job_service),
    artifacts: ArtifactsManager = Depends(get_artifacts_manager),
) -> SavedReelsResponse:
    """Копирует отобранные рилсы в ``<job_dir>/saved/<timestamp>_reelsN/``.

    К каждому mp4 добавляется subtitle (если есть в meta) + poster (если есть)
    + общий ``meta.json`` с оценками, caption'ами и реквизитами подборки.
    """
    job = await service.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"job {job_id} not found",
        )
    try:
        summary = await service.copy_reels_to_saved(
            job_id,
            payload.reel_ids,
            artifacts_manager=artifacts,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return SavedReelsResponse(**summary)


@router.get("/{job_id}/thumbnail")
async def get_job_thumbnail(
    job_id: str,
    service: JobService = Depends(get_job_service),
    settings: Settings = Depends(get_settings),
):
    """Возвращает JPEG-превью (первый кадр) видео для dashboard-карточек.

    Кэш keyed by job_id (immutable). При первом запросе ffmpeg извлекает
    один кадр на 0.5 секунде исходника, масштабирует до ширины 480px,
    сохраняет в `data/thumbnails/<job_id>/first.jpg`.
    """
    from fastapi.responses import FileResponse

    job = await service.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"job {job_id} not found",
        )

    source_path = Path(job.source_path)
    if not source_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="source video missing on disk",
        )

    settings.app_thumbnails_dir.mkdir(parents=True, exist_ok=True)
    thumb_dir = settings.app_thumbnails_dir / job_id
    thumb_dir.mkdir(parents=True, exist_ok=True)
    thumb_path = thumb_dir / "first.jpg"

    if not thumb_path.exists():
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            "0.5",
            "-i",
            str(source_path),
            "-frames:v",
            "1",
            "-q:v",
            "3",
            "-vf",
            "scale=480:-1",
            "-y",
            str(thumb_path),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0 or not thumb_path.exists():
            log.warning(
                "thumbnail_ffmpeg_failed",
                job_id=job_id,
                returncode=proc.returncode,
                stderr=stderr.decode(errors="replace")[:500] if stderr else "",
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="thumbnail generation failed",
            )

    return FileResponse(
        thumb_path,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=604800, immutable"},
    )


@router.get("/{job_id}/stream")
async def stream_job_progress(
    job_id: str,
    service: JobService = Depends(get_job_service),
) -> StreamingResponse:
    job = await service.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"job {job_id} not found",
        )

    queue = await service.bus.subscribe(job_id)

    async def event_generator() -> AsyncIterator[bytes]:
        try:
            snapshot = {
                "stage": job.current_stage.value if job.current_stage else "created",
                "progress": job.progress,
                "status": job.status.value,
                "message": job.message,
                "job_id": job.id,
            }
            yield _sse(snapshot)
            if job.status in (JobStatus.done, JobStatus.error, JobStatus.cancelled):
                return

            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_INTERVAL_SEC)
                except TimeoutError:
                    yield b": keepalive\n\n"
                    continue
                yield _sse(event)
                if event.get("status") in {"done", "error", "cancelled"}:
                    return
        finally:
            await service.bus.unsubscribe(job_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


_REEL_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_REEL_ID_MAX_LEN = 128


def _validate_reel_id(reel_id: str) -> str:
    """Валидирует reel_id перед интерполяцией в файловый путь (anti-traversal).

    Реальный формат в проде — ``v{idx}_r{N}``. Разрешаем только
    ``[A-Za-z0-9_-]`` и разумную длину; всё прочее → 400.
    """
    if not reel_id or len(reel_id) > _REEL_ID_MAX_LEN or not _REEL_ID_RE.fullmatch(reel_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"invalid reel_id: {reel_id!r}",
        )
    return reel_id


def _reel_artifact_path(base_dir: Path, reel_id: str, suffix: str) -> Path:
    """Строит путь к артефакту рилса c containment-check внутри base_dir.

    base_dir — поддиректория job_dir (subs/reels). Дополнительная проверка
    resolved-пути защищает от обхода даже если валидатор reel_id обойдён.
    """
    candidate = (base_dir / f"{reel_id}{suffix}").resolve()
    base_resolved = base_dir.resolve()
    if base_resolved not in candidate.parents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="resolved path escapes job dir",
        )
    return candidate


class SubtitleUpdateRequest(BaseModel):
    ass_content: str = Field(..., description="Raw ASS/SSA content для перезаписи")


@router.get("/{job_id}/reels/{reel_id}/subtitles")
async def get_reel_subtitles(
    job_id: str,
    reel_id: str,
    artifacts: ArtifactsManager = Depends(get_artifacts_manager),
) -> Response:
    """Возвращает raw .ass содержимое субтитров рилса (T3.4 captions editor)."""
    _validate_reel_id(reel_id)
    sub_path = _reel_artifact_path(artifacts.job_dir(job_id) / "subs", reel_id, ".ass")
    if not sub_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"subtitles not found for reel {reel_id}",
        )
    return Response(
        content=sub_path.read_text(encoding="utf-8"),
        media_type="text/plain; charset=utf-8",
    )


@router.patch(
    "/{job_id}/reels/{reel_id}/subtitles",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def update_reel_subtitles(
    job_id: str,
    reel_id: str,
    payload: SubtitleUpdateRequest,
    artifacts: ArtifactsManager = Depends(get_artifacts_manager),
) -> Response:
    """Перезаписывает .ass файл рилса (T3.4 inline editor)."""
    _validate_reel_id(reel_id)
    subs_dir = artifacts.job_dir(job_id) / "subs"
    if not subs_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no subs dir for job {job_id}",
        )
    sub_path = _reel_artifact_path(subs_dir, reel_id, ".ass")
    if not sub_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"subtitles not found for reel {reel_id}",
        )
    sub_path.write_text(payload.ass_content, encoding="utf-8")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


EXPORT_PRESETS: dict[str, dict[str, int | float | str]] = {
    "tiktok": {"bitrate_k": 6000, "target_lufs": -14.0, "container": "mp4"},
    "reels": {"bitrate_k": 5000, "target_lufs": -14.0, "container": "mp4"},
    "shorts": {"bitrate_k": 8000, "target_lufs": -14.0, "container": "mp4"},
    "x": {"bitrate_k": 5000, "target_lufs": -14.0, "container": "mp4"},
}


class ExportResponse(BaseModel):
    preset: str
    bitrate_k: int
    target_lufs: float
    download_url: str


@router.post("/{job_id}/reels/{reel_id}/export", response_model=ExportResponse)
async def export_reel_with_preset(
    job_id: str,
    reel_id: str,
    preset: str,
    artifacts: ArtifactsManager = Depends(get_artifacts_manager),
) -> ExportResponse:
    """Экспорт рилса с preset-специфичными encode-параметрами (T3.7).

    MVP: валидирует preset + наличие mp4, возвращает metadata и ссылку на
    существующий файл через /api/v1/files. Full transcode по preset bitrate
    — следующая итерация.
    """
    if preset not in EXPORT_PRESETS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown preset: {preset}",
        )
    _validate_reel_id(reel_id)
    reel_path = _reel_artifact_path(artifacts.job_dir(job_id) / "reels", reel_id, ".mp4")
    if not reel_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"reel mp4 not found for {reel_id}",
        )
    config = EXPORT_PRESETS[preset]
    return ExportResponse(
        preset=preset,
        bitrate_k=int(config["bitrate_k"]),
        target_lufs=float(config["target_lufs"]),
        download_url=f"/api/v1/files/{job_id}/reels/{reel_id}.mp4",
    )


def _sse(payload: Mapping[str, Any]) -> bytes:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()


def _safe_filename(name: str) -> str:
    basename = Path(name).name
    cleaned = "".join(ch if ch.isalnum() or ch in "._- " else "_" for ch in basename).strip()
    if not cleaned:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="filename contains no safe characters",
        )
    return cleaned


_pipeline_tasks: set[asyncio.Task[None]] = set()


def _find_pipeline_task(job_id: str) -> asyncio.Task[None] | None:
    """Находит запущенную pipeline-задачу по job_id (имя ``pipeline:{job_id}``)."""
    target = f"pipeline:{job_id}"
    for task in _pipeline_tasks:
        if task.get_name() == target:
            return task
    return None


def _schedule_pipeline(
    *,
    job_id: str,
    source_path: Path,
    transcriber_name: str,
    llm_provider: str,
    llm_model: str,
    target_aspect: str,
    fit_mode: str,
    source_language: str,
    subtitle_style: SubtitleStyleConfig | None,
    post_production_config: PostProductionConfig | None,
    use_proxy: bool,
    use_source_for_render: bool,
    target_reel_count: int | None,
    force_reingest: bool,
    vision_profile: VisionProfile,
    custom_system_prompt: str | None,
    service: JobService,
    artifacts: ArtifactsManager,
    settings: Settings,
) -> None:
    task = asyncio.create_task(
        run_pipeline_safe(
            job_id=job_id,
            source_path=source_path,
            transcriber_name=transcriber_name,
            llm_provider=llm_provider,
            llm_model=llm_model,
            target_aspect=target_aspect,
            fit_mode=fit_mode,
            source_language=source_language,
            subtitle_style=subtitle_style,
            post_production_config=post_production_config,
            use_proxy=use_proxy,
            use_source_for_render=use_source_for_render,
            target_reel_count=target_reel_count,
            force_reingest=force_reingest,
            vision_profile=vision_profile,
            custom_system_prompt=custom_system_prompt,
            service=service,
            artifacts=artifacts,
            settings=settings,
        ),
        name=f"pipeline:{job_id}",
    )
    _pipeline_tasks.add(task)
    task.add_done_callback(_pipeline_tasks.discard)


async def _save_upload(file: UploadFile, target: Path, max_bytes: int) -> int:
    total = 0
    chunk_size = 1024 * 1024
    with target.open("wb") as fh:
        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                fh.close()
                target.unlink(missing_ok=True)
                shutil.rmtree(target.parent, ignore_errors=True)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"upload exceeds {max_bytes} bytes",
                )
            fh.write(chunk)
    return total
