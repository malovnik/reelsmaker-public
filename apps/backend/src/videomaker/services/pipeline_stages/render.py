"""Render phase — stage 6: финальная сборка MP4 через ProjectGraph + ffmpeg.

Принимает ``PipelineContext`` с заполненными полями analysis/media_info/
cleaned_transcript/transcript_path/cleaned_path/reel_plan_path/
analysis_summary_path/profile_mask. Выполняет render и finalize фазы,
заполняет ``ctx.rendered`` (list[RenderedReel]) и пишет manifest.json.

Извлечено из ``pipeline._run_pipeline_impl`` в Phase 2.4.
Внутренняя разбивка ``_run_render_stage_via_project_graph`` на 7 focused
functions — Task 6.3 (deferred, под human supervision).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from videomaker.core.artifacts import ArtifactsManager
from videomaker.core.config import Settings
from videomaker.core.logging import get_logger
from videomaker.models.job import (
    ArtifactKind,
    JobStage,
    SubtitleStyleConfig,
    VisionProfile,
)
from videomaker.models.post_production import PostProductionConfig
from videomaker.models.reel_plan import ReelPlan
from videomaker.services.audio_normalizer import measure_source_loudness
from videomaker.services.face_tracker import FaceTrackerError, FaceTrackResult, track_faces
from videomaker.services.filler_removal import remove_fillers_from_cuts
from videomaker.services.jl_cut_planner import plan_jl_cuts
from videomaker.services.jobs import JobService
from videomaker.services.media import ExportPreset, MediaInfo, extract_audio, probe
from videomaker.services.pause_compression import compress_pauses_in_cuts
from videomaker.services.pipeline_context import PipelineContext
from videomaker.services.profile_masks import ProfileMask
from videomaker.services.project_graph import (
    BaseCropCommandSpec,
    BaseCropPlanSpec,
    CutSpec,
    ProjectGraph,
    build_project_graph,
)
from videomaker.services.project_renderer import (
    ProjectRenderer,
    ProjectRendererError,
    RenderProgress,
)
from videomaker.services.renderer import (
    PresetVariants,
    RenderSettings,
    coerce_segments,
    load_presets,
    select_preset,
    truncate_to_max_duration,
)
from videomaker.services.runtime_settings_store import get_performance_settings
from videomaker.services.split_screen import (
    SplitScreenError,
    render_split_single_pass,
)
from videomaker.services.subtitle_styles import resolve_style
from videomaker.services.subtitles import (
    SubtitleReelSpec,
    SubtitleStyle,
    write_ass,
)
from videomaker.services.transcribers.base import TranscribedWord
from videomaker.services.vad import detect_speech_segments
from videomaker.services.zoom_planner import build_base_crop_plan, build_zoom_plan

if TYPE_CHECKING:
    from videomaker.models.runtime_settings import PerformanceSettings
    from videomaker.services.pipeline import RenderedReel

log = get_logger(__name__)


@dataclass(slots=True)
class _RenderSetup:
    """Статический контекст стадии render — пресеты, face-трек, probe."""

    preset: ExportPreset
    render_settings: RenderSettings
    subtitle_style: SubtitleStyle
    legacy_margin_v: int
    face_track: FaceTrackResult | None
    source_width: int
    source_height: int
    target_aspect_ratio: float
    perf_preview: PerformanceSettings
    needs_mutation_safe_resync: bool
    split_enabled: bool


@dataclass(slots=True)
class _InitialGraphs:
    """Результат первичной сборки графов: собственно graphs + per-reel maps."""

    graphs: list[ProjectGraph]
    subtitle_paths_by_reel: dict[str, Path] = field(default_factory=dict)
    durations_by_reel: dict[str, float] = field(default_factory=dict)
    role_segments_by_reel: dict[str, list[tuple[float, float, str]]] = field(
        default_factory=dict
    )
    scoring_by_reel: dict[str, dict[str, float | None]] = field(default_factory=dict)


async def run_render_stage(ctx: PipelineContext) -> PipelineContext:
    """Render phase — финальная сборка MP4.

    Обогащает контекст ``ctx.rendered`` (list[RenderedReel]); пишет
    manifest.json и помечает job как завершённый.
    """
    from videomaker.services.pipeline import _advance

    service = ctx.service
    art = ctx.artifacts
    cfg = ctx.settings
    job_id = ctx.job_id
    source_path = ctx.source_path

    media_info = ctx.media_info
    assert media_info is not None, "render stage: media_info не заполнен"
    media_path_for_decode = ctx.media_path_for_decode or source_path
    cleaned = ctx.cleaned_transcript
    assert cleaned is not None, "render stage: cleaned_transcript не заполнен"
    transcript_path = ctx.transcript_path
    assert transcript_path is not None, "render stage: transcript_path не заполнен"
    cleaned_path = ctx.cleaned_path
    assert cleaned_path is not None, "render stage: cleaned_path не заполнен"
    analysis = ctx.analysis
    assert analysis is not None, "render stage: analysis не заполнен"
    profile_mask = ctx.profile_mask
    assert profile_mask is not None, "render stage: profile_mask не заполнен"
    reel_plan_path = ctx.reel_plan_path
    assert reel_plan_path is not None, "render stage: reel_plan_path не заполнен"

    await _advance(service, job_id, JobStage.render, 0, "рендер: Project Graph → HEVC")
    reels_dir = art.job_dir(job_id) / "reels"
    subs_dir = art.job_dir(job_id) / "subs"
    reels_dir.mkdir(parents=True, exist_ok=True)
    subs_dir.mkdir(parents=True, exist_ok=True)

    render_source = source_path if ctx.use_source_for_render else media_path_for_decode
    rendered = await _run_render_stage_via_project_graph(
        job_id=job_id,
        source_path=render_source,
        face_track_source_path=media_path_for_decode,
        analysis_reels=analysis.reels,
        words=cleaned.words,
        reels_dir=reels_dir,
        subs_dir=subs_dir,
        target_aspect=ctx.target_aspect,
        fit_mode=ctx.fit_mode,
        subtitle_style_config=ctx.subtitle_style,
        source_media_info=media_info,
        post_production_config=ctx.post_production_config,
        profile_mask=profile_mask,
        settings=cfg,
        service=service,
        art=art,
    )

    # finalize стадия осталась в enum для backward compat: становится no-op
    # (вся пост-продакшн поглощена в render через ProjectGraph). Сразу 100%.
    if ctx.post_production_config is not None and rendered:
        await _advance(
            service, job_id, JobStage.finalize, 100, "пост-продакшн поглощён в render"
        )
    await _advance(
        service,
        job_id,
        JobStage.render,
        100,
        f"готово: {len(rendered)} рилсов",
    )

    # Save bundle manifest JSON for quick UI consumption.
    manifest_path = art.write_json(
        job_id,
        "manifest.json",
        {
            "reels": [
                {
                    "reel_id": r.reel_id,
                    "output": str(r.output_path.relative_to(art.job_dir(job_id))),
                    "subtitle": str(r.subtitle_path.relative_to(art.job_dir(job_id))),
                    "duration_sec": r.duration_sec,
                }
                for r in rendered
            ],
            "transcript": str(transcript_path.relative_to(art.job_dir(job_id))),
            "cleaned_transcript": str(cleaned_path.relative_to(art.job_dir(job_id))),
            "reel_plan": str(reel_plan_path.relative_to(art.job_dir(job_id))),
        },
    )

    done_extra: dict[str, Any] = {
        "reel_count": len(rendered),
        "manifest": str(manifest_path.name),
    }
    avg_score = analysis.stats.get("avg_composite_score")
    if avg_score is not None:
        done_extra["avg_composite_score"] = avg_score
    await service.mark_done(
        job_id,
        message=f"{len(rendered)} рилсов готовы",
        extra=done_extra,
    )

    ctx.rendered = list(rendered)
    return ctx


async def _run_render_stage_via_project_graph(
    *,
    job_id: str,
    source_path: Path,
    face_track_source_path: Path,
    analysis_reels: list[ReelPlan],
    words: list[TranscribedWord],
    reels_dir: Path,
    subs_dir: Path,
    target_aspect: str,
    fit_mode: str,
    subtitle_style_config: SubtitleStyleConfig | None,
    source_media_info: MediaInfo,
    post_production_config: PostProductionConfig | None,
    profile_mask: ProfileMask,
    settings: Settings,
    service: JobService,
    art: ArtifactsManager,
) -> list[RenderedReel]:
    """Cycle 3: ОДИН ffmpeg на reel через декларативный ProjectGraph.

    Phase 6.3: разбит на 7 focused подфункций — orchestrator сам тонкий.

    1. ``_resolve_render_presets`` — presets, subtitle style, fps detection.
    2. ``_prepare_face_tracking`` — track_faces один раз на всю стадию.
    3. ``_build_initial_graphs`` — per-reel ProjectGraph с zoom/base_crop/subs.
    4. ``_apply_graph_transforms`` — pause/breath/filler/cut_snap/rhythm/jl_cut.
    5. ``_apply_zoom_layer`` — screencast zoom, deictic, emphasis motion.
    6. ``_finalize_graphs`` — two-pass loudnorm + subtitle resync + artifact.
    7. ``_render_and_persist_reels`` — render_many + split-screen + reel_output.

    Возвращает список ``RenderedReel`` (только успешные), сохраняя порядок
    ``analysis_reels``.
    """
    setup = await _resolve_render_presets(
        job_id=job_id,
        source_path=source_path,
        target_aspect=target_aspect,
        fit_mode=fit_mode,
        subtitle_style_config=subtitle_style_config,
        source_media_info=source_media_info,
        post_production_config=post_production_config,
        settings=settings,
    )
    # Phase 9 (2026-04-22): face_track_enabled toggle. Hardcode "v0.7 всегда"
    # заменён на opt-in. Default=False: 95% случаев не нуждаются в face
    # keyframes (letterbox / manual / split+main_transform работают без них).
    # Риск зависания mediapipe на Apple Silicon M-series подтверждён job
    # 8a418e9b — worker CPU=0% после face_track_start.
    perf_face_track = await get_performance_settings(settings)
    if perf_face_track.face_tracker_enabled:
        setup.face_track = await _prepare_face_tracking(
            job_id=job_id,
            face_track_source_path=face_track_source_path,
            settings=settings,
        )
    else:
        log.info(
            "face_track_skipped",
            job_id=job_id,
            reason="face_tracker_enabled=False в PerformanceSettings",
        )
        setup.face_track = None

    initial = _build_initial_graphs(
        job_id=job_id,
        source_path=source_path,
        analysis_reels=analysis_reels,
        words=words,
        reels_dir=reels_dir,
        subs_dir=subs_dir,
        fit_mode=fit_mode,
        post_production_config=post_production_config,
        profile_mask=profile_mask,
        setup=setup,
    )
    if not initial.graphs:
        log.warning("render_no_graphs_built", job_id=job_id)
        return []

    graphs = await _apply_graph_transforms(
        job_id=job_id,
        graphs=initial.graphs,
        source_path=source_path,
        words=words,
        role_segments_by_reel=initial.role_segments_by_reel,
        art=art,
        perf_preview=setup.perf_preview,
    )
    graphs = await _apply_zoom_layer(
        job_id=job_id,
        graphs=graphs,
        source_path=source_path,
        words=words,
        profile_mask=profile_mask,
        source_width=setup.source_width,
        source_height=setup.source_height,
        art=art,
        perf_preview=setup.perf_preview,
    )
    graphs = await _finalize_graphs(
        job_id=job_id,
        graphs=graphs,
        source_path=source_path,
        subtitle_paths_by_reel=initial.subtitle_paths_by_reel,
        preset=setup.preset,
        subtitle_style=setup.subtitle_style,
        words=words,
        service=service,
        art=art,
    )

    return await _render_and_persist_reels(
        job_id=job_id,
        graphs=graphs,
        initial=initial,
        setup=setup,
        post_production_config=post_production_config,
        settings=settings,
        service=service,
        art=art,
    )


async def _resolve_render_presets(
    *,
    job_id: str,
    source_path: Path,
    target_aspect: str,
    fit_mode: str,
    subtitle_style_config: SubtitleStyleConfig | None,
    source_media_info: MediaInfo,
    post_production_config: PostProductionConfig | None,
    settings: Settings,
) -> _RenderSetup:
    """Phase 1: presets → subtitle style → probe render input → perf snapshot.

    ВАЖНО: BaseCropPlan.source_{w,h} ОБЯЗАНЫ совпадать с размерами файла,
    который подаётся в `-i source_path` ffmpeg. Поэтому тут делаем probe
    именно render-input'а (может отличаться от source_media_info, если
    рендерится через proxy).
    """
    presets, render_settings = load_presets()
    preset_variants: PresetVariants = select_preset(presets, target_aspect)
    preset, legacy_margin_v = preset_variants.for_mode(fit_mode)

    if subtitle_style_config is not None:
        resolved = resolve_style(
            subtitle_style_config,
            preset_width=preset.width,
            preset_height=preset.height,
            fit_mode=fit_mode,
            source_info=source_media_info,
        )
        subtitle_style = resolved.ass_style
    else:
        subtitle_style = SubtitleStyle(
            font=render_settings.subtitle_style.font,
            size=render_settings.subtitle_style.size,
            primary_colour=render_settings.subtitle_style.primary_colour,
            outline_colour=render_settings.subtitle_style.outline_colour,
            back_colour=render_settings.subtitle_style.back_colour,
            outline=render_settings.subtitle_style.outline,
            shadow=render_settings.subtitle_style.shadow,
            margin_v=legacy_margin_v,
            alignment=render_settings.subtitle_style.alignment,
        )

    target_aspect_ratio = preset.width / preset.height
    render_input_info = await probe(source_path)
    source_width = render_input_info.width
    source_height = render_input_info.height
    log.info(
        "render_base_crop_input_probed",
        job_id=job_id,
        source_path=str(source_path),
        width=source_width,
        height=source_height,
        target_aspect_ratio=round(target_aspect_ratio, 4),
    )

    perf_preview = await get_performance_settings(settings)
    # Hotfix 2026-04-19 (Phase 1 tech-debt): ранняя write_ass на основе исходных
    # LLM-сегментов имеет смысл только если cuts НЕ будут мутировать ниже по
    # stage'ам. Любой из перечисленных toggles меняет cuts → resync перезапишет
    # ASS. Guard закрывает окно «дрейфующих субтитров» если stage упадёт между
    # ранней генерацией и resync.
    needs_mutation_safe_resync = (
        perf_preview.punchline_pause_enabled
        or perf_preview.pause_compression_enabled
        or perf_preview.filler_removal_enabled
        or perf_preview.cut_snap_enabled
        or perf_preview.rhythm_aware_cuts_enabled
        or perf_preview.snap_strategy != "off"
    )

    # Split-screen включён → intro/outro НЕ попадают в ProjectGraph (иначе они
    # окажутся в верхней половине split-canvas'а). После рендера intro/outro
    # приклеиваются отдельным concat pass'ом.
    split_enabled: bool = (
        post_production_config is not None
        and post_production_config.split_screen.enabled
        and post_production_config.split_screen.companion_path is not None
    )

    return _RenderSetup(
        preset=preset,
        render_settings=render_settings,
        subtitle_style=subtitle_style,
        legacy_margin_v=legacy_margin_v,
        face_track=None,
        source_width=source_width,
        source_height=source_height,
        target_aspect_ratio=target_aspect_ratio,
        perf_preview=perf_preview,
        needs_mutation_safe_resync=needs_mutation_safe_resync,
        split_enabled=split_enabled,
    )


async def _prepare_face_tracking(
    *,
    job_id: str,
    face_track_source_path: Path,
    settings: Settings,
) -> FaceTrackResult | None:
    """Phase 2: face tracking (dense sampling, кэшируется).

    Phase 9 (2026-04-22): выполняется ТОЛЬКО при
    ``PerformanceSettings.face_tracker_enabled=True``. Default False —
    ручной opt-in. Сбой face_tracker → fallback на статичный центр-crop.
    Caller должен сам проверить флаг перед вызовом; эта функция предполагает
    что face tracking нужен и не делает дополнительных проверок.
    """
    try:
        face_track = await track_faces(
            video_path=face_track_source_path,
            # Dense sampling (default 0.3s = 3.3Hz). Кэшируется на диске
            # (data/face_cache/<sha>__<interval>s.json).
            sample_interval_sec=settings.face_tracker_sample_interval_sec,
            cache_dir=settings.app_face_cache_dir,
            models_dir=settings.app_models_dir,
            min_confidence=settings.face_tracker_min_confidence,
        )
        log.info(
            "render_face_track_ready",
            job_id=job_id,
            detections=len(face_track.detections),
            with_face=sum(1 for d in face_track.detections if d.faces),
        )
        return face_track
    except FaceTrackerError as exc:
        log.warning("render_face_track_failed", job_id=job_id, error=str(exc))
        return None


def _build_initial_graphs(
    *,
    job_id: str,
    source_path: Path,
    analysis_reels: list[ReelPlan],
    words: list[TranscribedWord],
    reels_dir: Path,
    subs_dir: Path,
    fit_mode: str,
    post_production_config: PostProductionConfig | None,
    profile_mask: ProfileMask,
    setup: _RenderSetup,
) -> _InitialGraphs:
    """Phase 3: per-reel сборка ProjectGraph из ReelPlan.

    Для каждого плана: coerce_segments → truncate_to_max_duration → раннее
    write_ass (если не mutation path) → build_zoom_plan → build_base_crop_plan
    → build_project_graph. Параллельно собираются per-reel maps для
    downstream stages.
    """
    preset = setup.preset
    render_settings = setup.render_settings
    subtitle_style = setup.subtitle_style
    face_track = setup.face_track
    source_width = setup.source_width
    source_height = setup.source_height
    target_aspect_ratio = setup.target_aspect_ratio
    needs_mutation_safe_resync = setup.needs_mutation_safe_resync
    split_enabled = setup.split_enabled

    result = _InitialGraphs(graphs=[])
    for plan in analysis_reels:
        segments = coerce_segments(plan, render_settings)
        if not segments:
            log.warning("reel_skipped_empty", reel_id=plan.reel_id)
            continue
        duration = sum(s.duration for s in segments)
        if duration < render_settings.min_reel_duration_sec:
            log.warning(
                "reel_skipped_too_short",
                reel_id=plan.reel_id,
                duration=round(duration, 2),
                min=render_settings.min_reel_duration_sec,
            )
            continue
        if duration > render_settings.max_reel_duration_sec:
            log.warning(
                "reel_truncated",
                reel_id=plan.reel_id,
                duration=round(duration, 2),
                max=render_settings.max_reel_duration_sec,
            )
            segments = truncate_to_max_duration(
                segments, render_settings.max_reel_duration_sec
            )
            duration = sum(s.duration for s in segments)

        sub_spec = SubtitleReelSpec(
            reel_id=plan.reel_id,
            segments=[(s.source_start, s.source_end) for s in segments],
            words=words,
            play_resx=preset.width,
            play_resy=preset.height,
            style=subtitle_style,
        )
        sub_path = subs_dir / f"{plan.reel_id}.ass"
        if not needs_mutation_safe_resync:
            write_ass(sub_spec, sub_path)

        # Split: юзер задаёт рамку main panel через main_transform в
        # SplitScreenPreviewEditor. Editor отрисовывает ИСТОЧНИК как есть
        # (object-fit:contain). Render должен делать то же: source →
        # letterbox/scale в main_rect БЕЗ предварительного face-crop'а и
        # zoom'а. Иначе: base_crop уже обрезал до 9:16 face-centered →
        # main_transform оперирует уже-cropped body → лицо дважды zoomed.
        # Расхождение preview vs render. Fix 2026-04-22.
        # Применяем для ВСЕГО split_enabled (не только manual): при fit/fill
        # main_transform определяет position panel, а fit_mode — scale
        # поведение содержимого внутри rect. base_crop + zoom в обоих
        # случаях избыточны.
        split_skip_base_crop = (
            split_enabled and post_production_config is not None
        )

        zoom_plan = None
        if (
            post_production_config is not None
            and post_production_config.zoom_enabled
            and not split_skip_base_crop
        ):
            composition = profile_mask.composition
            zoom_plan = build_zoom_plan(
                reel_id=plan.reel_id,
                segments=segments,
                face_track=face_track,
                config=post_production_config,
                frame_width=preset.width,
                frame_height=preset.height,
                dead_zone_norm=composition.dead_zone_norm,
                ema_alpha=composition.ema_alpha,
                rule_of_thirds_y_shift=composition.rule_of_thirds_y_shift,
            )

        # v0.7: face-aware base crop только для fit=fill. fit=letterbox —
        # кадр целиком с чёрными полосами, face-centering недоступен.
        # Split: base_crop skip независимо от fit_mode — main_transform
        # задаёт rect на source (см. split_skip_base_crop выше).
        base_crop_plan = None
        if split_skip_base_crop:
            log.info(
                "base_crop_skipped_split",
                reel_id=plan.reel_id,
                hint="split_enabled: source идёт raw, main_transform + main_fit_mode управляют кадрированием",
            )
        elif fit_mode == "fill" and source_width > 0 and source_height > 0:
            base_crop_plan = build_base_crop_plan(
                segments=segments,
                face_track=face_track,
                source_width=source_width,
                source_height=source_height,
                target_aspect_ratio=target_aspect_ratio,
            )
        elif fit_mode == "fit" and source_width > 0 and source_height > 0:
            log.info(
                "base_crop_skipped_letterbox",
                reel_id=plan.reel_id,
                hint="fit_mode=fit → letterbox, crop пропущен. Для face-центрирования используй fit_mode=fill.",
            )

        out_path = reels_dir / f"{plan.reel_id}.mp4"
        graph = build_project_graph(
            reel_id=plan.reel_id,
            source_path=source_path,
            output_path=out_path,
            segments=segments,
            zoom_plan=zoom_plan,
            subtitle_path=sub_path,
            post_production_config=post_production_config,
            preset=preset,
            base_crop_plan=base_crop_plan,
            # Single-pass split (fix 2026-04-22): при split_enabled граф
            # строится BODY-ONLY — exclude_post_production=True убирает
            # intro/outro из graph (Stage F concat не триггерится внутри
            # build_filter_graph), exclude_subtitles=True убирает subtitle
            # burn-in (Stage C не триггерится). intro/outro и субтитры
            # приходят в render_split_single_pass как отдельные аргументы
            # и применяются ПОСЛЕ vstack body+companion: intro/outro
            # полноэкранные 1080×1920 (не split с companion), subtitles
            # поверх всего canvas (правильная center-позиция).
            #
            # Non-split: exclude_post_production=False, exclude_subtitles=False
            # — всё в одном filter_complex через обычный ProjectRenderer.
            exclude_post_production=split_enabled,
            exclude_subtitles=split_enabled,
            # Split branch: body должно выходить в source aspect (не в
            # canvas 9:16), чтобы split panel letterbox'ил source напрямую
            # → editor object-fit:contain = render 1:1.
            preserve_source_res=split_enabled,
        )
        result.graphs.append(graph)
        result.subtitle_paths_by_reel[plan.reel_id] = sub_path
        result.durations_by_reel[plan.reel_id] = round(duration, 2)
        result.role_segments_by_reel[plan.reel_id] = [
            (
                round(s.source_start, 3),
                round(s.source_end, 3),
                getattr(s, "order_role", "development") or "development",
            )
            for s in segments
        ]
        result.scoring_by_reel[plan.reel_id] = {
            "rhythm_score": plan.rhythm_score,
            "visual_score": plan.visual_score,
            "narrative_score": plan.narrative_score,
            "composite_score": plan.composite_score,
            "cross_context_risk": plan.cross_context_risk,
        }
    log.debug(
        "render_initial_graphs_built", job_id=job_id, reels=len(result.graphs)
    )
    return result


async def _apply_pause_compression(
    *,
    job_id: str,
    graphs: list[ProjectGraph],
    source_path: Path,
    words: list[TranscribedWord],
    art: ArtifactsManager,
    perf_preview: PerformanceSettings,
) -> list[ProjectGraph]:
    """Phase 4.1: micro-pause compression с punchline/breath extensions.

    TIER2-#14: Silero VAD находит паузы в речи, длиннее
    ``pause_compression_threshold_sec`` укорачиваются до
    ``pause_compression_keep_sec``. Один VAD-прогон на source audio,
    результат шарится между всеми cuts всех reels.

    Побочные effects:
    - T10.1 punchline preservation: расширяем speech-сегменты около punchline.
    - T8.2 breath classifier: добавляет breath events как speech (не
      сжимаются).
    - T8.1 mouth sounds (DORMANT): только log, mute_zones API не готов.
    """
    if not perf_preview.pause_compression_enabled:
        return graphs
    try:
        audio_for_vad = art.path_for(job_id, "audio", "source.wav")
        if not audio_for_vad.exists():
            log.info(
                "render_pause_compression_extract_audio",
                job_id=job_id,
                dest=str(audio_for_vad),
            )
            await extract_audio(source_path, audio_for_vad)
        speech = await detect_speech_segments(audio_for_vad)

        # T10.1 Punchline pause preservation: расширяем speech segments
        # которые заканчиваются возле punchline moment'а.
        if speech and perf_preview.punchline_pause_enabled:
            try:
                from videomaker.services.punchline_detector import (
                    detect_punchline_moments,
                )

                punchline_segments = [
                    (s.start_sec, s.end_sec) for s in speech
                ]
                punchline_moments = await detect_punchline_moments(
                    audio_for_vad,
                    punchline_segments,
                    pitch_drop_hz=perf_preview.punchline_pitch_drop_hz,
                    hold_sec=perf_preview.punchline_hold_after_sec,
                )
                if punchline_moments:
                    from videomaker.services.vad import SpeechSegment

                    extended_speech: list[SpeechSegment] = []
                    for seg in speech:
                        extension = 0.0
                        for pm in punchline_moments:
                            if abs(pm.time_sec - seg.end_sec) < 0.2:
                                extension = max(extension, pm.hold_sec)
                        if extension > 0:
                            extended_speech.append(
                                SpeechSegment(
                                    start_sec=seg.start_sec,
                                    end_sec=seg.end_sec + extension,
                                )
                            )
                        else:
                            extended_speech.append(seg)
                    speech = extended_speech
                    log.info(
                        "render_punchline_pause_applied",
                        job_id=job_id,
                        moments=len(punchline_moments),
                        hold_sec=perf_preview.punchline_hold_after_sec,
                    )
            except Exception as exc:
                log.warning(
                    "render_punchline_detection_failed",
                    job_id=job_id,
                    error=str(exc),
                )

        # T8.2: breath events — помечаем не-сжимаемые зоны.
        if perf_preview.breath_classifier_enabled and speech:
            from videomaker.services.breath_classifier import (
                detect_breath_events,
            )
            from videomaker.services.vad import SpeechSegment

            try:
                speech_tuples = [(s.start_sec, s.end_sec) for s in speech]
                breath_events = await detect_breath_events(
                    audio_for_vad, speech_tuples
                )
                if breath_events:
                    log.info(
                        "render_breath_events_found",
                        job_id=job_id,
                        count=len(breath_events),
                    )
                    extended = list(speech)
                    for b_start, b_end in breath_events:
                        extended.append(
                            SpeechSegment(start_sec=b_start, end_sec=b_end)
                        )
                    extended.sort(key=lambda s: s.start_sec)
                    speech = extended
            except Exception as exc:
                log.warning(
                    "render_breath_classifier_failed",
                    job_id=job_id,
                    error=str(exc),
                )

        # T8.1: mouth sounds detection. DORMANT (UI toggle disabled).
        if perf_preview.mouth_sound_removal_enabled:
            log.warning(
                "mouth_sound_removal_dormant",
                job_id=job_id,
                message=(
                    "Feature is dormant and has no effect on output — "
                    "detector runs but ProjectGraph mute_zones API "
                    "пока не реализован. UI toggle disabled."
                ),
            )
            from videomaker.services.mouth_sound_detector import (
                detect_mouth_sounds,
            )

            try:
                defects = await detect_mouth_sounds(audio_for_vad)
                if defects:
                    log.info(
                        "render_mouth_sound_defects_found",
                        job_id=job_id,
                        count=len(defects),
                    )
            except Exception as exc:
                log.warning(
                    "render_mouth_sound_removal_failed",
                    job_id=job_id,
                    error=str(exc),
                )

        if speech:
            total_saved = 0.0

            def _compress_pauses(g: ProjectGraph) -> tuple[list[CutSpec], bool]:
                nonlocal total_saved
                new_cuts, stats = compress_pauses_in_cuts(
                    list(g.cuts),
                    speech,
                    min_pause_sec=perf_preview.pause_compression_threshold_sec,
                    keep_sec=perf_preview.pause_compression_keep_sec,
                    context_aware_keep_sec=perf_preview.context_aware_keep_sec_enabled,
                    words=words if perf_preview.context_aware_keep_sec_enabled else None,
                )
                total_saved += stats.time_saved_sec
                return new_cuts, stats.pauses_compressed > 0

            graphs = _apply_cut_mutation(graphs, transform=_compress_pauses)
            log.info(
                "render_pause_compression_done",
                job_id=job_id,
                total_saved_sec=round(total_saved, 2),
                reels=len(graphs),
            )
    except Exception as exc:
        log.warning(
            "render_pause_compression_failed",
            job_id=job_id,
            error=str(exc),
        )
    return graphs


async def _apply_graph_transforms(
    *,
    job_id: str,
    graphs: list[ProjectGraph],
    source_path: Path,
    words: list[TranscribedWord],
    role_segments_by_reel: dict[str, list[tuple[float, float, str]]],
    art: ArtifactsManager,
    perf_preview: PerformanceSettings,
) -> list[ProjectGraph]:
    """Phase 4: последовательные cut-мутации через ``_apply_cut_mutation``.

    Порядок stages: pause_compression → breath_compression → filler_removal →
    cut_snap → rhythm_snap (beat/onset) → jl_cut. Каждая опциональна через
    perf_preview toggle. Любая ошибка внутри блока лог'ается warning'ом и
    stage пропускается — pipeline не падает.
    """
    graphs = await _apply_pause_compression(
        job_id=job_id,
        graphs=graphs,
        source_path=source_path,
        words=words,
        art=art,
        perf_preview=perf_preview,
    )

    # T2.7: Breath compression — второй pass после pause_compression.
    # Агрессивнее (min_pause 0.25s, keep 0.08s). Только если pause_compression
    # включён, иначе параметры слишком агрессивны для длинных пауз.
    if perf_preview.breath_compression_enabled and perf_preview.pause_compression_enabled:
        try:
            audio_for_vad = art.path_for(job_id, "audio", "source.wav")
            if audio_for_vad.exists():
                from videomaker.services.vad import detect_speech_segments as _detect_breath
                breath_speech = await _detect_breath(audio_for_vad)
                if breath_speech:
                    total_breath_saved = 0.0
                    total_breath_pauses = 0

                    def _compress_breath(g: ProjectGraph) -> tuple[list[CutSpec], bool]:
                        nonlocal total_breath_saved, total_breath_pauses
                        new_cuts, b_stats = compress_pauses_in_cuts(
                            list(g.cuts),
                            breath_speech,
                            min_pause_sec=perf_preview.breath_compression_threshold_sec,
                            keep_sec=perf_preview.breath_compression_keep_sec,
                            context_aware_keep_sec=perf_preview.context_aware_keep_sec_enabled,
                            words=words if perf_preview.context_aware_keep_sec_enabled else None,
                        )
                        total_breath_saved += b_stats.time_saved_sec
                        total_breath_pauses += b_stats.pauses_compressed
                        return new_cuts, b_stats.pauses_compressed > 0

                    graphs = _apply_cut_mutation(graphs, transform=_compress_breath)
                    log.info(
                        "render_breath_compression_done",
                        job_id=job_id,
                        pauses=total_breath_pauses,
                        total_saved_sec=round(total_breath_saved, 2),
                    )
        except Exception as exc:
            log.warning(
                "render_breath_compression_failed",
                job_id=job_id,
                error=str(exc),
            )

    # TIER2-#13: Russian filler removal. Вырезает слова помеченные
    # `is_filler=True` (TIER1-#3 лексикон) ±30ms буфер.
    if perf_preview.filler_removal_enabled and words:
        try:
            total_filler_saved = 0.0
            total_fillers = 0

            def _remove_fillers(g: ProjectGraph) -> tuple[list[CutSpec], bool]:
                nonlocal total_filler_saved, total_fillers
                new_cuts, f_stats = remove_fillers_from_cuts(
                    list(g.cuts),
                    words,
                    aggressive=perf_preview.filler_removal_aggressive,
                    confidence_threshold=perf_preview.filler_confidence_threshold,
                    edge_buffer_sec=perf_preview.filler_edge_buffer_sec,
                )
                total_filler_saved += f_stats.time_saved_sec
                total_fillers += f_stats.fillers_removed
                return new_cuts, f_stats.fillers_removed > 0

            graphs = _apply_cut_mutation(graphs, transform=_remove_fillers)
            log.info(
                "render_filler_removal_done",
                job_id=job_id,
                fillers_removed=total_fillers,
                total_saved_sec=round(total_filler_saved, 2),
                aggressive=perf_preview.filler_removal_aggressive,
            )
        except Exception as exc:
            log.warning(
                "render_filler_removal_failed", job_id=job_id, error=str(exc)
            )

    # FEAT-#E: word-aware cut snapping. Прилепляет границы cut'ов к
    # ближайшему word boundary (±30мс). Убирает click-артефакты на срезах
    # из середины слова.
    if perf_preview.cut_snap_enabled and words:
        try:
            from videomaker.services.cut_snapper import snap_cuts_to_words

            total_snapped = 0
            max_shift = 0.0

            def _snap_cuts(g: ProjectGraph) -> tuple[list[CutSpec], bool]:
                nonlocal total_snapped, max_shift
                new_cuts, snap_stats = snap_cuts_to_words(
                    list(g.cuts),
                    words,
                    snap_window_sec=perf_preview.cut_snap_window_sec,
                )
                total_snapped += snap_stats.snapped_starts + snap_stats.snapped_ends
                max_shift = max(max_shift, snap_stats.max_shift_sec)
                return new_cuts, snap_stats.any_snapped

            graphs = _apply_cut_mutation(graphs, transform=_snap_cuts)
            log.info(
                "render_cut_snap_done",
                job_id=job_id,
                boundaries_snapped=total_snapped,
                max_shift_sec=round(max_shift, 3),
            )
        except Exception as exc:
            log.warning("render_cut_snap_failed", job_id=job_id, error=str(exc))

    # T10.2 + T2.5: snap strategy dispatcher.
    # - "beat" (legacy T2.5): beat_track → для видео с музыкой.
    # - "onset" (T10.2): onset_detect → для talking-head.
    # - "both": onset приоритетно, beat fallback.
    # - "off": без snap.
    effective_snap_strategy = perf_preview.snap_strategy
    if perf_preview.rhythm_aware_cuts_enabled and effective_snap_strategy == "off":
        effective_snap_strategy = "beat"

    if effective_snap_strategy != "off":
        try:
            from videomaker.services.beat_detector import (
                detect_beats,
                detect_onsets,
                snap_cuts_to_reference,
            )

            snap_audio = art.path_for(job_id, "audio", "source.wav")
            if not snap_audio.exists():
                await extract_audio(source_path, snap_audio)

            reference_times: list[float] = []
            reference_label = effective_snap_strategy
            shift_sec = perf_preview.rhythm_aware_max_shift_sec

            if effective_snap_strategy == "beat":
                reference_times = await detect_beats(snap_audio)
            elif effective_snap_strategy == "onset":
                reference_times = await detect_onsets(snap_audio)
                shift_sec = perf_preview.onset_snap_max_shift_sec
            elif effective_snap_strategy == "both":
                onsets = await detect_onsets(snap_audio)
                if onsets:
                    reference_times = onsets
                    reference_label = "onset"
                    shift_sec = perf_preview.onset_snap_max_shift_sec
                else:
                    reference_times = await detect_beats(snap_audio)
                    reference_label = "beat"

            if reference_times:
                total_rhythm_snaps = 0
                rhythm_max_shift = 0.0

                def _snap_rhythm(g: ProjectGraph) -> tuple[list[CutSpec], bool]:
                    nonlocal total_rhythm_snaps, rhythm_max_shift
                    new_cuts, r_stats = snap_cuts_to_reference(
                        list(g.cuts),
                        reference_times,
                        max_shift_sec=shift_sec,
                    )
                    total_rhythm_snaps += (
                        r_stats.snapped_starts + r_stats.snapped_ends
                    )
                    rhythm_max_shift = max(rhythm_max_shift, r_stats.max_shift_sec)
                    return new_cuts, r_stats.any_snapped

                graphs = _apply_cut_mutation(graphs, transform=_snap_rhythm)
                log.info(
                    "render_rhythm_snap_done",
                    job_id=job_id,
                    strategy=reference_label,
                    references=len(reference_times),
                    boundaries_snapped=total_rhythm_snaps,
                    max_shift_sec=round(rhythm_max_shift, 3),
                )
        except Exception as exc:
            log.warning(
                "render_rhythm_snap_failed", job_id=job_id, error=str(exc)
            )

    # TIER2-#15: J/L-cut planner. Сглаживает переходы на ролевых границах
    # через опережение/продолжение аудио соседней сцены.
    if perf_preview.jl_cut_enabled:
        try:
            source_duration_sec: float | None = None
            try:
                media_info_local = await probe(source_path)
                source_duration_sec = media_info_local.duration_sec
            except Exception as exc:
                log.warning(
                    "jl_cut_source_probe_failed",
                    job_id=job_id,
                    error=str(exc)[:200],
                )
                source_duration_sec = None

            total_j = 0
            total_l = 0

            def _apply_jl(g: ProjectGraph) -> tuple[list[CutSpec], bool]:
                nonlocal total_j, total_l
                role_segs = role_segments_by_reel.get(g.reel_id, [])
                roles_per_cut = _assign_roles_to_cuts(list(g.cuts), role_segs)
                new_cuts, jl_stats = plan_jl_cuts(
                    list(g.cuts),
                    segment_roles=roles_per_cut,
                    source_duration_sec=source_duration_sec,
                    max_offset_sec=perf_preview.jl_cut_max_offset_sec,
                    mode=perf_preview.jl_cut_mode,
                )
                total_j += jl_stats.j_cuts_applied
                total_l += jl_stats.l_cuts_applied
                return new_cuts, jl_stats.any_applied

            graphs = _apply_cut_mutation(
                graphs, transform=_apply_jl, realign_base_crop=False
            )
            log.info(
                "render_jl_cut_done",
                job_id=job_id,
                j_cuts=total_j,
                l_cuts=total_l,
                mode=perf_preview.jl_cut_mode,
                max_offset_sec=perf_preview.jl_cut_max_offset_sec,
            )
        except Exception as exc:
            log.warning("render_jl_cut_failed", job_id=job_id, error=str(exc))

    return graphs


async def _apply_zoom_layer(
    *,
    job_id: str,
    graphs: list[ProjectGraph],
    source_path: Path,
    words: list[TranscribedWord],
    profile_mask: ProfileMask,
    source_width: int,
    source_height: int,
    art: ArtifactsManager,
    perf_preview: PerformanceSettings,
) -> list[ProjectGraph]:
    """Phase 5: motion/zoom layer.

    Порядок: screencast cursor zoom (DORMANT) → deictic zoom (DORMANT) →
    emphasis motion (punch-in + Ken Burns). Первые два детектят/планируют,
    но не применяются (ZoomPlan merge API не готов). Третий пишет
    ``motion_filter_expr`` в graph → renderer применит.
    """
    # T2.8 Screencast cursor zoom — только для profile=screencast. DORMANT:
    # detector/planner самодостаточны, фактический merge ZoomKeyframe в
    # ZoomPlan (ZoomCommand/AnchorKeyframe) потребует расширения zoom_planner
    # API и откладывается на follow-up спринт. Сейчас — log-only.
    if (
        profile_mask.profile == VisionProfile.screencast
        and perf_preview.screencast_cursor_zoom_enabled
    ):
        log.warning(
            "screencast_cursor_zoom_dormant",
            job_id=job_id,
            message=(
                "Feature is dormant and has no effect on output — keyframes "
                "computed but ZoomPlan merge API не реализован. "
                "UI toggle disabled."
            ),
        )
        try:
            from videomaker.services.cursor_detector import (
                detect_cursor_events,
            )
            from videomaker.services.spring_zoom_planner import (
                plan_screencast_zoom,
            )

            cursor_events = await detect_cursor_events(source_path)
            if cursor_events and source_width > 0 and source_height > 0:
                sc_keyframes = plan_screencast_zoom(
                    cursor_events,
                    video_width=source_width,
                    video_height=source_height,
                    profile=perf_preview.screencast_damping_profile,
                    max_zoom_factor=perf_preview.screencast_zoom_max_factor,
                )
                log.info(
                    "screencast_zoom_computed",
                    job_id=job_id,
                    cursor_events=len(cursor_events),
                    keyframes=len(sc_keyframes),
                    applier="deferred",
                )
            else:
                log.info(
                    "screencast_zoom_skipped",
                    job_id=job_id,
                    reason="no_cursor_events",
                )
        except Exception as exc:
            log.warning(
                "screencast_zoom_failed", job_id=job_id, error=str(exc)
            )

    # T2.8 Deictic zoom layer — любой профиль. Триггерит zoom-in на словах-
    # указателях ("вот", "смотри", "здесь"). Merge в ZoomPlan deferred.
    if perf_preview.deictic_zoom_enabled and words:
        log.warning(
            "deictic_zoom_dormant",
            job_id=job_id,
            message=(
                "Feature is dormant and has no effect on output — triggers "
                "computed but ZoomPlan merge API не реализован. "
                "UI toggle disabled."
            ),
        )
        try:
            from videomaker.services.deictic_zoom import (
                inject_deictic_zoom_triggers,
            )

            deictic_kfs = inject_deictic_zoom_triggers(words, [])
            log.info(
                "deictic_zoom_computed",
                job_id=job_id,
                triggers=len(deictic_kfs),
                applier="deferred",
            )
        except Exception as exc:
            log.warning(
                "deictic_zoom_failed", job_id=job_id, error=str(exc)
            )

    # T10.3 + T10.7 — Emphasis motion (punch-in zoom) + Ken Burns drift.
    # Применяется ПОСЛЕ всех cut/snap мутаций, перед loudnorm и render.
    # Строим FFmpeg zoompan expression для каждого graph, записываем в
    # motion_filter_expr. filter_graph_builder применит его между Stage B
    # (face-tracking zoom) и Stage C (subtitles).
    if (
        perf_preview.punch_in_zoom_enabled
        or perf_preview.ken_burns_drift_enabled
    ):
        try:
            from videomaker.services.emphasis_motion import (
                build_ffmpeg_motion_expr,
                detect_emphasis_moments,
                plan_ken_burns_drift,
                plan_punch_in_keyframes,
            )

            emphasis_audio = art.path_for(job_id, "audio", "source.wav")
            if not emphasis_audio.exists():
                await extract_audio(source_path, emphasis_audio)

            emphasis_moments = []
            if perf_preview.punch_in_zoom_enabled:
                emphasis_moments = await detect_emphasis_moments(emphasis_audio)

            motion_graphs: list[ProjectGraph] = []
            total_punch = 0
            total_kb = 0
            for g in graphs:
                reel_dur = sum(c.duration_sec for c in g.cuts)
                if reel_dur <= 0:
                    motion_graphs.append(g)
                    continue

                reel_emphasis = [
                    m for m in emphasis_moments if 0 <= m.time_sec <= reel_dur
                ]
                punch_kfs = []
                if perf_preview.punch_in_zoom_enabled and reel_emphasis:
                    punch_kfs = plan_punch_in_keyframes(
                        reel_emphasis,
                        reel_duration_sec=reel_dur,
                        fps=g.export_preset.fps,
                        probability=perf_preview.punch_in_zoom_probability,
                        zoom_scale=perf_preview.punch_in_zoom_scale,
                        hold_ms=perf_preview.punch_in_zoom_hold_ms,
                        seed=hash(g.reel_id) & 0xFFFFFFFF,
                    )

                kb_plan = None
                if perf_preview.ken_burns_drift_enabled:
                    kb_plan = plan_ken_burns_drift(
                        reel_duration_sec=reel_dur,
                        fps=g.export_preset.fps,
                        scale_per_sec=perf_preview.ken_burns_scale_per_sec,
                        max_scale=perf_preview.ken_burns_max_scale,
                    )

                expr = build_ffmpeg_motion_expr(
                    keyframes=punch_kfs or None,
                    ken_burns=kb_plan,
                    fps=g.export_preset.fps,
                    frame_width=g.export_preset.width,
                    frame_height=g.export_preset.height,
                )
                if expr:
                    total_punch += len(punch_kfs)
                    if kb_plan:
                        total_kb += 1
                    motion_graphs.append(
                        g.model_copy(update={"motion_filter_expr": expr})
                    )
                else:
                    motion_graphs.append(g)
            graphs = motion_graphs
            log.info(
                "render_motion_effects_applied",
                job_id=job_id,
                punch_in_total=total_punch,
                ken_burns_reels=total_kb,
                reels=len(graphs),
            )
        except Exception as exc:
            log.warning(
                "render_motion_effects_failed", job_id=job_id, error=str(exc)
            )

    return graphs


async def _finalize_graphs(
    *,
    job_id: str,
    graphs: list[ProjectGraph],
    source_path: Path,
    subtitle_paths_by_reel: dict[str, Path],
    preset: ExportPreset,
    subtitle_style: SubtitleStyle,
    words: list[TranscribedWord],
    service: JobService,
    art: ArtifactsManager,
) -> list[ProjectGraph]:
    """Phase 6: two-pass loudnorm + subtitle resync + project_graph artifact.

    ASS субтитры после всех cut-мутаций дрейфуют относительно исходных LLM
    сегментов → перезаписываем из финальных ``graph.cuts``. Параллельно
    выполняем two-pass loudnorm (один раз на source_path, результат
    прокидываем во все графы). Финально — сохраняем project_graphs.json
    как artifact.
    """
    # Two-pass loudnorm: меряем loudness source_path ОДИН раз → прокидываем
    # measured_* во все графы, где two_pass включён. Точность ±1 LU vs ±2 LU
    # single-pass. TIER1-#6, платформенный spec -14 LUFS TikTok/Reels.
    spec0 = graphs[0].audio_normalize
    if spec0.enabled and spec0.two_pass and not spec0.has_measurement:
        measured = await measure_source_loudness(
            source_path,
            target_lufs=spec0.target_lufs,
            true_peak_dbtp=spec0.true_peak_dbtp,
            lra=spec0.lra,
        )
        if measured is not None:
            graphs = [
                g.model_copy(
                    update={
                        "audio_normalize": g.audio_normalize.model_copy(
                            update={
                                "measured_i": measured.input_i,
                                "measured_tp": measured.input_tp,
                                "measured_lra": measured.input_lra,
                                "measured_thresh": measured.input_thresh,
                                "measured_offset": measured.target_offset,
                            }
                        )
                    }
                )
                for g in graphs
            ]
            log.info(
                "render_two_pass_loudnorm_enabled",
                job_id=job_id,
                reel_count=len(graphs),
                input_i=measured.input_i,
                target_lufs=spec0.target_lufs,
                offset=measured.target_offset,
            )
        else:
            log.info(
                "render_two_pass_loudnorm_fallback_single",
                job_id=job_id,
                reason="measurement_pass_failed",
            )

    # Subtitle resync. ASS генерируется рано из исходных LLM-сегментов, но
    # cuts мутируют: pause_compression → filler_removal → cut_snap → jl_cuts.
    # К моменту рендера исходные segments != финальные cuts, и субтитры
    # дрейфуют к середине рилса. Перезаписываем ASS из финальных graph.cuts
    # по тому же пути, который уже проставлен в graph.subtitle_path.
    # Используем audio_start/end (не source_*) чтобы J/L-cut offset попал в
    # фильтр слов и локальный тайминг.
    if subtitle_paths_by_reel:
        resynced = 0
        for g in graphs:
            sub_path = subtitle_paths_by_reel.get(g.reel_id)
            if sub_path is None:
                continue
            final_segments = [
                (c.audio_start_sec, c.audio_end_sec) for c in g.cuts
            ]
            resync_spec = SubtitleReelSpec(
                reel_id=g.reel_id,
                segments=final_segments,
                words=words,
                play_resx=preset.width,
                play_resy=preset.height,
                style=subtitle_style,
            )
            write_ass(resync_spec, sub_path)
            resynced += 1
        log.info("render_subtitles_resynced", job_id=job_id, reels=resynced)

    # Сохраняем массив графов как артефакт для reproducibility / debug.
    graphs_dump = [g.model_dump(mode="json") for g in graphs]
    graphs_path = art.write_json(job_id, "project_graphs.json", {"reels": graphs_dump})
    await service.add_artifact(
        job_id,
        kind=ArtifactKind.project_graph,
        path=str(graphs_path.relative_to(art.job_dir(job_id))),
        meta={"reel_count": len(graphs)},
    )

    return graphs


async def _render_and_persist_reels(
    *,
    job_id: str,
    graphs: list[ProjectGraph],
    initial: _InitialGraphs,
    setup: _RenderSetup,
    post_production_config: PostProductionConfig | None,
    settings: Settings,
    service: JobService,
    art: ArtifactsManager,
) -> list[RenderedReel]:
    """Phase 7: ProjectRenderer.render_many + split-screen + add_artifact.

    ODIN ffmpeg на reel через ``ProjectRenderer``, progress events
    транслируются в JobStage.render (inside 0..100). Если включён
    split-screen — идём через ``render_split_single_pass`` (один ffmpeg
    из source → final), минуя ProjectRenderer полностью. Успешные
    рилсы регистрируются как ``ArtifactKind.reel_output``.
    """
    from videomaker.services.pipeline import RenderedReel, _advance

    split_enabled = setup.split_enabled
    subtitle_paths_by_reel = initial.subtitle_paths_by_reel
    durations_by_reel = initial.durations_by_reel
    scoring_by_reel = initial.scoring_by_reel

    total_reels = len(graphs)
    completed = {"n": 0}

    async def on_progress(snap: RenderProgress) -> None:
        if not snap.finished:
            return
        completed["n"] += 1
        # render stage внутри _STAGE_RANGES = (80, 90). Двигаем 0..100 inside_percent.
        inside = int(completed["n"] / total_reels * 100)
        await _advance(
            service,
            job_id,
            JobStage.render,
            inside,
            f"рендер {completed['n']}/{total_reels}: {snap.reel_id}",
        )

    perf = await get_performance_settings(settings)
    rendered: list[RenderedReel] = []

    # Single-pass split-screen (2026-04-22): при split_enabled=True ВСЕ reels
    # одного job идут через render_split_single_pass (один ffmpeg из source
    # → final). ProjectRenderer.render_many НЕ вызывается — иначе body
    # рендерился бы впустую перед перезаписью split single-pass'ом (2x
    # ffmpeg время). split_enabled — это job-level флаг (резолвится в
    # setup), так что партиционирование сводится к ранней ветке.
    if split_enabled:
        assert post_production_config is not None
        assert post_production_config.split_screen.companion_path is not None
        companion_path = Path(post_production_config.split_screen.companion_path)
        # intro/outro приходят отдельно (body-only graph не содержит их).
        # render_split_single_pass применит их fullscreen ПОСЛЕ vstack.
        split_intro_raw = post_production_config.intro_path
        split_outro_raw = post_production_config.outro_path
        split_intro_path = Path(split_intro_raw) if split_intro_raw else None
        split_outro_path = Path(split_outro_raw) if split_outro_raw else None

        for graph in graphs:
            sub_path_for_split = subtitle_paths_by_reel.get(graph.reel_id)
            subtitle_ass_path = (
                sub_path_for_split
                if sub_path_for_split is not None and sub_path_for_split.exists()
                else None
            )
            try:
                await render_split_single_pass(
                    graph=graph,
                    companion_path=companion_path,
                    split_config=post_production_config.split_screen,
                    intro_path=split_intro_path,
                    outro_path=split_outro_path,
                    subtitle_ass_path=subtitle_ass_path,
                )
            except SplitScreenError as err:
                log.error(
                    "split_screen_failed",
                    job_id=job_id,
                    reel_id=graph.reel_id,
                    error=str(err),
                )
                # Cleanup partial output: single-pass мог записать частичный
                # mp4 до ошибки. Оставлять orphan на диске нельзя — job
                # workspace должен содержать только валидные артефакты.
                partial = Path(graph.output_path)
                if partial.exists():
                    partial.unlink(missing_ok=True)
                continue

            reel_mp4 = Path(graph.output_path)
            file_size = reel_mp4.stat().st_size
            completed["n"] += 1
            inside = int(completed["n"] / total_reels * 100)
            await _advance(
                service,
                job_id,
                JobStage.render,
                inside,
                f"рендер {completed['n']}/{total_reels}: {graph.reel_id} (split)",
            )
            log.info(
                "split_screen_single_pass_applied",
                job_id=job_id,
                reel_id=graph.reel_id,
                new_size=file_size,
                has_intro=graph.intro_path is not None,
                has_outro=graph.outro_path is not None,
            )

            sub_path_for_reel = subtitle_paths_by_reel[graph.reel_id]
            duration_for_reel = durations_by_reel[graph.reel_id]
            rendered.append(
                RenderedReel(
                    reel_id=graph.reel_id,
                    output_path=reel_mp4,
                    subtitle_path=sub_path_for_reel,
                    duration_sec=duration_for_reel,
                    # Single-pass не измеряет wall_time / loudnorm — для
                    # split-режима эти метрики не нужны (loudnorm применяется
                    # к audio внутри graph filter), 0.0 маркер "не измерялось".
                    wall_time_sec=0.0,
                    file_size_bytes=file_size,
                    achieved_lufs=None,
                    within_loudnorm_tolerance=None,
                )
            )
            reel_scoring = scoring_by_reel.get(graph.reel_id, {})
            await service.add_artifact(
                job_id,
                kind=ArtifactKind.reel_output,
                path=str(reel_mp4.relative_to(art.job_dir(job_id))),
                meta={
                    "reel_id": graph.reel_id,
                    "duration_sec": duration_for_reel,
                    "subtitle_path": str(
                        sub_path_for_reel.relative_to(art.job_dir(job_id))
                    ),
                    "wall_time_sec": 0.0,
                    "file_size_bytes": file_size,
                    "bitrate_bps": None,
                    "achieved_lufs": None,
                    # FEAT-#C: scoring данные для UI virality display.
                    "rhythm_score": reel_scoring.get("rhythm_score"),
                    "visual_score": reel_scoring.get("visual_score"),
                    "narrative_score": reel_scoring.get("narrative_score"),
                    "composite_score": reel_scoring.get("composite_score"),
                    # T9 — cross-context risk: ReelCard показывает amber badge при
                    # risk > 0.6 — рилс собран из несвязанных по времени кусков.
                    "cross_context_risk": reel_scoring.get("cross_context_risk"),
                },
            )

        return rendered

    # Non-split path: ProjectRenderer.render_many + zip loop (unchanged).
    renderer = ProjectRenderer()
    results = await renderer.render_many(
        graphs, concurrency=perf.render_concurrency, on_progress=on_progress
    )

    for graph, result in zip(graphs, results, strict=True):
        if isinstance(result, ProjectRendererError):
            log.error(
                "project_render_failed",
                job_id=job_id,
                reel_id=graph.reel_id,
                error=str(result),
                stderr_tail=result.stderr_tail[-500:],
            )
            continue
        if isinstance(result, BaseException):
            import traceback

            tb_lines = traceback.format_exception(
                type(result), result, result.__traceback__
            )
            log.error(
                "project_render_exception",
                job_id=job_id,
                reel_id=graph.reel_id,
                error=str(result),
                traceback="".join(tb_lines)[-2000:],
            )
            continue
        sub_path_for_reel = subtitle_paths_by_reel[graph.reel_id]
        duration_for_reel = durations_by_reel[graph.reel_id]
        rendered.append(
            RenderedReel(
                reel_id=graph.reel_id,
                output_path=result.output_path,
                subtitle_path=sub_path_for_reel,
                duration_sec=duration_for_reel,
                wall_time_sec=result.wall_time_sec,
                file_size_bytes=result.file_size_bytes,
                achieved_lufs=(
                    result.loudnorm.output_integrated_lufs
                    if result.loudnorm
                    else None
                ),
                within_loudnorm_tolerance=(
                    result.loudnorm.is_within_tolerance if result.loudnorm else None
                ),
            )
        )
        reel_scoring = scoring_by_reel.get(result.reel_id, {})
        await service.add_artifact(
            job_id,
            kind=ArtifactKind.reel_output,
            path=str(result.output_path.relative_to(art.job_dir(job_id))),
            meta={
                "reel_id": result.reel_id,
                "duration_sec": duration_for_reel,
                "subtitle_path": str(
                    sub_path_for_reel.relative_to(art.job_dir(job_id))
                ),
                "wall_time_sec": result.wall_time_sec,
                "file_size_bytes": result.file_size_bytes,
                "bitrate_bps": result.bitrate_bps,
                "achieved_lufs": (
                    result.loudnorm.output_integrated_lufs if result.loudnorm else None
                ),
                # FEAT-#C: scoring данные для UI virality display.
                "rhythm_score": reel_scoring.get("rhythm_score"),
                "visual_score": reel_scoring.get("visual_score"),
                "narrative_score": reel_scoring.get("narrative_score"),
                "composite_score": reel_scoring.get("composite_score"),
                # T9 — cross-context risk: ReelCard показывает amber badge при
                # risk > 0.6 — рилс собран из несвязанных по времени кусков.
                "cross_context_risk": reel_scoring.get("cross_context_risk"),
            },
        )

    return rendered


def _apply_cut_mutation(
    graphs: list[ProjectGraph],
    *,
    transform: Callable[[ProjectGraph], tuple[list[CutSpec], bool]],
    realign_base_crop: bool = True,
) -> list[ProjectGraph]:
    """Общий адаптер для stage-мутаций, переписывающих ``graph.cuts``.

    6 стадий pause/breath/filler/cut_snap/rhythm_snap/jl_cut делят один и
    тот же паттерн: прогнать каждый граф через функцию, которая возвращает
    ``(new_cuts, applied)``, если ``applied`` — пересобрать граф через
    ``model_copy(cuts=...)`` плюс (опционально) пересчитать ``base_crop_plan``.

    Вынесено в Phase 6.1 — убирает 5-7-кратное дублирование
    ``compressed_graphs.append(g.model_copy(...))`` в `_run_render_stage_via_project_graph`.

    Args:
        graphs: входной список project-графов.
        transform: синхронная функция, которая для графа возвращает пару
            ``(new_cuts, applied)``. ``applied=False`` → граф остаётся без
            изменений. ``applied=True`` → ``cuts`` (и ``base_crop_plan``)
            перезаписываются по ``new_cuts``.
        realign_base_crop: обновлять ли ``base_crop_plan`` через
            :func:`_realign_base_crop_for_cuts`. jl_cut не мутирует crop,
            поэтому передаёт ``False``.

    Returns:
        Новый список графов той же длины и порядка.
    """

    updated: list[ProjectGraph] = []
    for g in graphs:
        new_cuts, applied = transform(g)
        if applied and new_cuts:
            update: dict[str, Any] = {"cuts": tuple(new_cuts)}
            if realign_base_crop:
                update["base_crop_plan"] = _realign_base_crop_for_cuts(new_cuts, g)
            updated.append(g.model_copy(update=update))
        else:
            updated.append(g)
    return updated


def _realign_base_crop_for_cuts(
    new_cuts: list[CutSpec],
    old_graph: ProjectGraph,
) -> BaseCropPlanSpec | None:
    """Пересоздаёт `base_crop_plan` для нового списка cuts.

    Нужен когда pause_compression / filler_removal / jl_cut разбивают один
    cut на N под-cut'ов. ``base_crop.commands`` привязан 1:1 к ``cuts``
    (см. ProjectGraph._validate_cuts_not_empty), и без пересборки на
    split'е длины расходятся → IndexError на filter_graph.

    Все под-cuts одного исходного cut наследуют один crop command
    (face/composition не меняется внутри одной фразы). Parent находится
    по пересечению source-time диапазонов.

    Возвращает новый ``BaseCropPlanSpec`` с commands длиной == len(new_cuts),
    либо None если у old_graph не было base_crop_plan.
    """

    if old_graph.base_crop_plan is None:
        return None

    old_commands = old_graph.base_crop_plan.commands
    old_cuts = old_graph.cuts
    if len(old_commands) != len(old_cuts):
        # Рассинхрон уже случился раньше — пересоздать ничего не можем,
        # возвращаем как есть, build_filter_graph всё равно упадёт.
        return old_graph.base_crop_plan

    new_commands: list[BaseCropCommandSpec] = []
    for new_cut in new_cuts:
        mid = (new_cut.source_start_sec + new_cut.source_end_sec) / 2
        parent_idx = 0
        for i, old_cut in enumerate(old_cuts):
            if old_cut.source_start_sec - 1e-3 <= mid <= old_cut.source_end_sec + 1e-3:
                parent_idx = i
                break
        new_commands.append(old_commands[parent_idx])

    return old_graph.base_crop_plan.model_copy(
        update={"commands": tuple(new_commands)}
    )


def _assign_roles_to_cuts(
    cuts: list[CutSpec],
    role_segments: list[tuple[float, float, str]],
) -> list[str]:
    """Для каждого cut ищет источник-сегмент по пересечению source_start и
    возвращает его роль. Нужен J/L-cut planner'у после pause/filler, где один
    plan segment может быть разбит на несколько cut'ов (тогда роль наследуется).

    Если совпадения нет (неожиданный сдвиг границ) — роль ``"development"``.
    """

    roles: list[str] = []
    for c in cuts:
        assigned = "development"
        # cut.source_start_sec — поле Pydantic CutSpec
        cs = getattr(c, "source_start_sec", 0.0)
        ce = getattr(c, "source_end_sec", 0.0)
        mid = (cs + ce) / 2
        for seg_start, seg_end, seg_role in role_segments:
            if seg_start - 0.05 <= mid <= seg_end + 0.05:
                assigned = seg_role
                break
        roles.append(assigned)
    return roles
