"""Video pipeline orchestrator.

Связывает все стадии:
  1. probe исходника (длительность)
  2. extract audio WAV 16kHz mono
  3. transcribe (mlx-whisper или Deepgram)
  4. translate (EN→RU адаптивно, если detected != ru)
  5. silence_cut + filler filter
  6. analyze — Kartoziya 8-sub-stage pipeline:
     6.1 compression (Flash Lite per-chunk)
     6.2 canvas_builder (Pro, один вызов)
     6.3 orchestrate_extraction (6 агентов × N chunks, Flash Lite)
     6.4 reduce_and_rank (Flash + Jaccard dedup)
     6.5 compose_story_script (Pro + 3-act arc)
     6.6 check_rhythm (Flash + heuristic middle-sag)
     6.7 generate_variants (Pro, 4 формата)
     6.8 compose_reels (sync, target N + uniqueness filter)
  7. render — финальные рилсы MP4 + ASS субтитры
  8. update job.artifacts + mark_done

Прогресс маппится в 0–100 по стадиям (см. _STAGE_RANGES).
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from videomaker.core.artifacts import ArtifactsManager
from videomaker.core.config import Settings, get_settings
from videomaker.core.logging import get_logger
from videomaker.models.job import (
    JobStage,
    SubtitleStyleConfig,
    VisionProfile,
)
from videomaker.models.post_production import PostProductionConfig
from videomaker.services.jobs import JobService
from videomaker.services.media import FfmpegError
from videomaker.services.pipeline_context import PipelineContext
from videomaker.services.pipeline_stages import (
    run_analysis_stage,
    run_ingest_stage,
    run_render_stage,
)
from videomaker.services.prompts import use_custom_system_prompt
from videomaker.services.runtime_settings_store import (
    get_performance_settings,
)

log = get_logger(__name__)


_STAGE_RANGES: dict[JobStage, tuple[int, int]] = {
    JobStage.ingest: (0, 5),
    JobStage.proxy_generate: (5, 15),
    JobStage.transcribe: (15, 40),
    JobStage.translate: (40, 50),
    JobStage.silence_cut: (50, 60),
    JobStage.analyze: (60, 80),
    JobStage.render: (80, 95),
    JobStage.finalize: (95, 99),
    JobStage.done: (100, 100),
}


@dataclass(slots=True)
class RenderedReel:
    """Финальный результат одного рилса после ProjectRenderer.

    Зеркалит публичный контракт renderer.RenderedReel (которая удалится в Cycle 5),
    но дополнительно несёт wall_time_sec / loudnorm / file_size_bytes для метрик.
    """

    reel_id: str
    output_path: Path
    subtitle_path: Path
    duration_sec: float
    wall_time_sec: float
    file_size_bytes: int
    achieved_lufs: float | None
    within_loudnorm_tolerance: bool | None


@dataclass(slots=True)
class PipelineResult:
    duration_sec: float
    transcript_path: Path
    cleaned_path: Path
    reel_plan_path: Path
    analysis_summary_path: Path
    rendered: list[RenderedReel]


async def run_pipeline(
    *,
    job_id: str,
    source_path: Path,
    transcriber_name: str,
    llm_provider: str,
    llm_model: str,
    target_aspect: str,
    fit_mode: str = "fill",
    source_language: str = "auto",
    subtitle_style: SubtitleStyleConfig | None = None,
    post_production_config: PostProductionConfig | None = None,
    use_proxy: bool = True,
    use_source_for_render: bool = False,
    target_reel_count: int | None = None,
    force_reingest: bool = False,
    vision_profile: VisionProfile = VisionProfile.talking_head,
    custom_system_prompt: str | None = None,
    service: JobService,
    artifacts: ArtifactsManager | None = None,
    settings: Settings | None = None,
) -> PipelineResult:
    """Запускает полный конвейер для одного job. Бросает исключение — вызывающий код
    должен обернуть и вызвать `service.mark_error` при неудаче.

    ``custom_system_prompt`` — опциональный текст, задаваемый пользователем в
    UploadWizard. Если указан и непустой — дословно прикрепляется в самое
    начало system-prompt всех LLM-вызовов (через prompts.build_system_prompt).
    Нужен для таргетинга темы / тонких правок TOV без переписывания манифеста.
    """

    with use_custom_system_prompt(custom_system_prompt):
        return await _run_pipeline_impl(
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
            service=service,
            artifacts=artifacts,
            settings=settings,
        )


async def _run_pipeline_impl(
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
    service: JobService,
    artifacts: ArtifactsManager | None,
    settings: Settings | None,
) -> PipelineResult:
    """Внутренняя реализация — оборачивается в use_custom_system_prompt
    через публичный ``run_pipeline``. Сохраняет все существующие инварианты.
    """

    cfg = settings or get_settings()
    art = artifacts or ArtifactsManager(cfg.app_artifacts_dir)
    art.ensure_layout(job_id)

    source_path = source_path.resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"source not found: {source_path}")

    # BUG-#F sanity-check: snapshot job'а мог быть сохранён с выключенной
    # нормализацией громкости (старая сессия, случайный toggle в UI). Если
    # это так — предупреждаем в логах; рилсы выйдут с неровной громкостью.
    if (
        post_production_config is not None
        and not post_production_config.audio_normalize_enabled
    ):
        log.warning(
            "audio_normalize_disabled_in_snapshot",
            job_id=job_id,
            hint=(
                "preset в момент создания job имел audio_normalize_enabled=false; "
                "обнови preset и пересоздай job чтобы применить -14 LUFS"
            ),
        )

    # ===== Stages 1-4: ingest phase (probe → proxy → transcribe → translate → silence_cut) =====
    # Извлечено в ``services.pipeline_stages.ingest::run_ingest_stage`` в Phase 2.2.
    perf = await get_performance_settings(cfg)
    ctx = PipelineContext(
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
        service=service,
        artifacts=art,
        settings=cfg,
        perf=perf,
    )
    ctx = await run_ingest_stage(ctx)

    # ===== Stage 5: analyze (Kartoziya 5.1-5.10) =====
    # Извлечено в ``services.pipeline_stages.analysis::run_analysis_stage``
    # в Phase 2.3. Блок обогащает ctx финальным ``analysis``, ``profile_mask``,
    # ``vision_runtime``, ``reel_plan_path``, ``analysis_summary_path``.
    ctx = await run_analysis_stage(ctx)

    # ===== Stage 6: render (Project Graph + одиночный ffmpeg на reel) =====
    # Извлечено в ``services.pipeline_stages.render::run_render_stage`` в
    # Phase 2.4. Стадия заполняет ``ctx.rendered``, пишет manifest.json,
    # помечает job как mark_done.
    ctx = await run_render_stage(ctx)

    return ctx.to_pipeline_result()


async def run_pipeline_safe(
    *,
    job_id: str,
    source_path: Path,
    transcriber_name: str,
    llm_provider: str,
    llm_model: str,
    target_aspect: str,
    fit_mode: str = "fill",
    source_language: str = "auto",
    subtitle_style: SubtitleStyleConfig | None = None,
    post_production_config: PostProductionConfig | None = None,
    use_proxy: bool = True,
    use_source_for_render: bool = False,
    target_reel_count: int | None = None,
    force_reingest: bool = False,
    vision_profile: VisionProfile = VisionProfile.talking_head,
    custom_system_prompt: str | None = None,
    service: JobService,
    artifacts: ArtifactsManager | None = None,
    settings: Settings | None = None,
) -> None:
    """Обёртка для background task: ловит любое исключение и помечает job как error.

    T11 Automatic Mode: если job.options содержит ``auto_config`` с
    ``pipeline_mode == 'automatic'``, оборачивает весь pipeline в
    ``job_settings_override`` — все вызовы ``get_performance_settings``
    внутри получают merged auto-config.
    """
    from videomaker.services.runtime_settings_store import job_settings_override

    try:
        job = await service.get(job_id)
        auto_overrides: dict[str, object] | None = None
        if job is not None and isinstance(job.options, dict):
            ac = job.options.get("auto_config")
            if (
                isinstance(ac, dict)
                and ac.get("pipeline_mode", "manual") == "automatic"
            ):
                # Фильтруем только PerformanceSettings поля
                auto_overrides = {
                    k: v for k, v in ac.items() if k != "pipeline_mode"
                }
            # T9 — composer_strategy_override из UploadWizard. Переопределяет
            # advisor-решение (если Auto mode) или просто сохраняется в
            # auto_overrides для downstream consumer'ов. Валидация уже
            # сделана в create_job endpoint.
            composer_override = job.options.get("composer_strategy_override")
            if composer_override in {"tight_context", "balanced", "thematic_free"}:
                if auto_overrides is None:
                    auto_overrides = {}
                auto_overrides["composer_strategy"] = composer_override
                log.info(
                    "composer_strategy_override_applied",
                    job_id=job_id,
                    value=composer_override,
                )

        async with job_settings_override(auto_overrides):
            await run_pipeline(
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
            )
    except FileNotFoundError as exc:
        log.exception("pipeline_missing_file", job_id=job_id)
        await service.mark_error(job_id, error=f"missing file: {exc}")
    except FfmpegError as exc:
        log.exception("pipeline_ffmpeg_failed", job_id=job_id)
        await service.mark_error(job_id, error=f"ffmpeg: {exc}")
    except Exception as exc:
        log.exception("pipeline_failed", job_id=job_id)
        await service.mark_error(job_id, error=str(exc))


async def _advance(
    service: JobService,
    job_id: str,
    stage: JobStage,
    inside_percent: int,
    message: str,
    *,
    extra: dict[str, object] | None = None,
) -> None:
    low, high = _STAGE_RANGES[stage]
    span = max(1, high - low)
    progress = low + round(inside_percent / 100.0 * span)
    await service.mark_stage(
        job_id, stage=stage, progress=progress, message=message, extra=extra
    )


def cleanup_job_upload(job_id: str, settings: Settings | None = None) -> None:
    """Удаляет исходный upload, если пользователь захочет освободить место после успешного job."""

    cfg = settings or get_settings()
    target = cfg.app_upload_dir / job_id
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)


__all__ = [
    "PipelineResult",
    "cleanup_job_upload",
    "run_pipeline",
    "run_pipeline_safe",
]
