"""Analysis phase — Kartoziya 5.1-5.10: compression → canvas → extraction →
reduce → story → rhythm → variants → reels → coherence → closure.

Принимает PipelineContext с заполненными ingest полями (cleaned_transcript,
transcript, media_info). Возвращает с заполненным ``ctx.analysis`` —
финальным AnalysisResult (list[ReelPlan] + stats + vision-enriched
артефакты). В ``ctx.reel_plan_path`` и ``ctx.analysis_summary_path``
сохраняются пути к JSON-артефактам.

Внутренние артефакты (chunks, compression, canvas, extraction_result,
reduce_result, story_script, rhythm_report, variants) сохраняются в
context для observability (можно прочитать в случае сбоя render).
Downstream render stage читает только ``ctx.analysis`` + ``ctx.profile_mask``
+ ``ctx.vision_runtime``.

Извлечено из ``pipeline._run_pipeline_impl`` в Phase 2.3.
"""

from __future__ import annotations

import asyncio
import collections
from pathlib import Path

from videomaker.core.config import Settings, get_settings
from videomaker.core.logging import get_logger
from videomaker.models.canvas import ProjectCanvas
from videomaker.models.evidence import RankedEvidence
from videomaker.models.job import (
    TARGET_LANGUAGE,
    ArtifactKind,
    JobStage,
    VisionProfile,
)
from videomaker.models.reel_plan import AnalysisResult, ReelPlan
from videomaker.models.story_script import RhythmReport, StoryScript
from videomaker.models.vision_settings import VisionRuntimeSettings
from videomaker.services.agents.orchestrator import (
    ExtractionResult,
    orchestrate_extraction,
)
from videomaker.services.canvas_builder import build_canvas
from videomaker.services.canvas_embedder import embed_canvas_moments
from videomaker.services.chunker import ChunkingPolicy, chunk_transcript
from videomaker.services.closure_validator import validate_closures
from videomaker.services.coherence_validator import validate_coherence
from videomaker.services.compression import compress_chunks
from videomaker.services.cover_selector import select_cover
from videomaker.services.cross_chunk_reducer import apply_cross_chunk_coherence
from videomaker.services.face_tracker import FaceTrackerError, track_faces
from videomaker.services.jobs import JobService
from videomaker.services.llm_client import build_llm_for_tier
from videomaker.services.narrative.map_reduce_orchestrator import (
    orchestrate_map_reduce,
)
from videomaker.services.narrative.orchestrator import orchestrate_top_down
from videomaker.services.pipeline_context import PipelineContext
from videomaker.services.pipeline_mode import detect_pipeline_mode
from videomaker.services.preference_memory import (
    load_liked_anchors_text,
    mean_embedding,
)
from videomaker.services.profile_masks import (
    ProfileMask,
    apply_profile_weights,
    get_effective_profile_mask,
    get_enabled_agents_for_mask,
)
from videomaker.services.reducer import reduce_and_rank
from videomaker.services.reels_composer import compose_reels
from videomaker.services.rhythm_check import check_rhythm
from videomaker.services.runtime_settings_store import (
    get_performance_settings,
    get_vision_settings,
)
from videomaker.services.semantic_chunker import (
    SemanticChunkingPolicy,
    semantic_chunk_transcript,
)
from videomaker.services.silence_cutter import CleanedTranscript
from videomaker.services.story_doctor import compose_story_script
from videomaker.services.transcribers.base import (
    TranscriptResult,
    merge_words_into_segments,
)
from videomaker.services.trend_lexicons import compute_trend_score
from videomaker.services.variants_generator import generate_variants
from videomaker.services.vision import (
    FrameExtractor,
    VisionResultCache,
    build_vision_client,
    compute_video_sha256,
    get_vision_rate_limiter,
)
from videomaker.services.visual_evidence_agent import (
    VisualEvidenceResult,
    run_visual_evidence_agent,
)
from videomaker.services.visual_validator import validate_arc

log = get_logger(__name__)


#: T1.3 — пороги critique loop'а.
#: Ниже ``_RHYTHM_MIN_ACCEPTABLE`` → переделываем arc с injected critique.
#: Max 2 итерации (3-я обычно хуже из-за Gemini дрейфа: не улучшает, а
#: начинает «откатывать» к первоначальной версии).
_RHYTHM_MIN_ACCEPTABLE = 0.60
_RHYTHM_MAX_ITERATIONS = 2


def _pro_model_for_messaging(cfg: Settings, provider: str | None) -> str:
    """Возвращает текущую Pro-tier модель для SSE-сообщений пользователю.

    build_llm_for_tier("pro", ...) резолвит через runtime_settings: при
    tier_profile=fast получит Lite; при quality — Flash; при balanced — Flash.
    Ошибка резолва → "pro model" (graceful-degrade, не ломаем SSE).
    """
    try:
        return build_llm_for_tier("pro", cfg, provider_override=provider).model
    except Exception:
        return "pro model"


def _viral_model_for_messaging(cfg: Settings, provider: str | None) -> str:
    """Возвращает фактическую flash_lite-модель, используемую viral_2026.

    viral_arc_builder резолвит ``build_llm_for_tier("flash_lite", ...)`` —
    артефакт/SSE должны отражать ту же модель и провайдера, а не хардкод.
    Ошибка резолва → ``"flash_lite model"`` (graceful-degrade).
    """
    try:
        return build_llm_for_tier(
            "flash_lite", cfg, provider_override=provider
        ).model
    except Exception:
        return "flash_lite model"


async def run_analysis_stage(ctx: PipelineContext) -> PipelineContext:
    """Analysis phase — Kartoziya 5.1-5.10.

    Обогащает context intermediate артефактами (chunks, compression, canvas,
    extraction_result, reduce_result, story_script, rhythm_report, variants),
    финальным ``analysis`` (AnalysisResult), ``profile_mask``,
    ``vision_runtime``, ``reel_plan_path``, ``analysis_summary_path``.
    """
    # Локальный импорт чтобы избежать циклической зависимости с pipeline.py.
    from videomaker.services.pipeline import _advance

    job_id = ctx.job_id
    source_path = ctx.source_path
    service = ctx.service
    art = ctx.artifacts
    cfg = ctx.settings
    transcriber_name = ctx.transcriber_name
    llm_provider = ctx.llm_provider
    llm_model = ctx.llm_model
    vision_profile = ctx.vision_profile
    target_reel_count = ctx.target_reel_count

    media_info = ctx.media_info
    assert media_info is not None, "analysis stage: media_info не заполнен"
    transcript = ctx.transcript
    assert transcript is not None, "analysis stage: transcript не заполнен"
    cleaned = ctx.cleaned_transcript
    assert cleaned is not None, "analysis stage: cleaned_transcript не заполнен"
    detected_lang = ctx.detected_language or "und"
    needs_translation = ctx.needs_translation

    # ===== Stage 5: analyze (Kartoziya 8-stage pipeline) =====
    # llm_provider/llm_model — UI-выбор, используется ТОЛЬКО в stage translate.
    # Kartoziya работает на Gemini Pro/Flash/Flash-Lite согласно tier-mapping
    # в llm_client.build_llm_for_tier. Одна видео-нарезка = ~40-60 LLM-вызовов
    # (6 агентов × N chunks + canvas + reduce + doctor + rhythm + variants).
    cleaned_transcript = _transcript_from_cleaned(cleaned, transcript)
    fallback_policy = ChunkingPolicy(
        threshold_tokens=cfg.chunk_token_threshold,
        window_tokens=cfg.chunk_window_tokens,
        overlap_tokens=cfg.chunk_overlap_tokens,
    )
    # TIER2-#11: Semantic chunking — границы по эмбеддингам вместо токенов.
    # Если выключено или embed-вызов падает — используется token-based sliding window.
    perf_chunking = await get_performance_settings(cfg)
    if perf_chunking.semantic_chunking_enabled:
        chunks = await semantic_chunk_transcript(
            cleaned_transcript,
            SemanticChunkingPolicy(
                target_duration_sec=perf_chunking.semantic_chunk_target_duration_sec,
                min_duration_sec=perf_chunking.semantic_chunk_min_duration_sec,
                similarity_threshold=perf_chunking.semantic_chunk_similarity_threshold,
                fallback_policy=fallback_policy,
            ),
            settings=cfg,
        )
    else:
        chunks = chunk_transcript(cleaned_transcript, fallback_policy)
    ctx.chunks = list(chunks)
    analysis_language = detected_lang if not needs_translation else TARGET_LANGUAGE

    # Получаем pipeline_provider один раз — пробрасываем во все LLM-вызовы.
    # Дефолт "gemini" — защита от регрессии при откате через PerformanceSettings.
    perf_for_llm = await get_performance_settings(cfg)
    pipeline_provider = perf_for_llm.pipeline_llm_provider

    await _advance(
        service, job_id, JobStage.analyze, 5,
        f"compression: {len(chunks)} chunks через Flash Lite",
    )
    compression = await compress_chunks(chunks, pipeline_provider=pipeline_provider)
    ctx.compression = compression

    _pro_llm = build_llm_for_tier("pro", cfg, provider_override=pipeline_provider)
    await _advance(
        service, job_id, JobStage.analyze, 20,
        f"Project Canvas ({_pro_llm.model})",
    )
    canvas = await build_canvas(
        compression,
        source_duration_sec=media_info.duration_sec,
        transcriber_name=transcriber_name,
        language=analysis_language,
        pipeline_provider=pipeline_provider,
        client=_pro_llm,
    )

    # T1.1 Stage 5.2.5: семантические embeddings на candidate_moments.
    # Gemini-embedding-001 → 256-dim per moment. Downstream использует для
    # semantic dedup (Reducer), retrieval (Story Doctor), cross-reel
    # diversity filter. Graceful-degrade: при падении embed API Canvas
    # возвращается без embeddings, downstream работает по legacy-путям.
    canvas = await embed_canvas_moments(canvas, cleaned.words, settings=cfg)
    ctx.canvas = canvas
    art.write_json(job_id, "canvas_full.json", canvas.model_dump(mode="json"))
    log.info(
        "canvas_snapshot_saved",
        themes=len(canvas.themes),
        motifs=len(canvas.motifs),
        candidate_moments=len(canvas.candidate_moments),
        tone_map=len(canvas.tone_map),
        central_theme_len=len(canvas.central_theme or ""),
    )

    vision_runtime = await get_vision_settings(cfg)
    profile_mask = await get_effective_profile_mask(vision_profile)
    ctx.vision_runtime = vision_runtime
    ctx.profile_mask = profile_mask

    # ─── Top-down narrative branch (Phase 6, 2026-04-21) ──────────────────
    # Feature flag narrative_mode переключает pipeline между legacy
    # bottom-up (extraction→reducer→story_doctor→variants→composer с padding)
    # и top-down (chapter_builder→hook_detector→arc_finder→boundary_extender
    # →cross_chapter_ranker, длительность рилса = payoff, не padding).
    # Default: bottom_up — zero regression. Включается через UI
    # /settings/performance или PUT /api/v1/settings/performance.
    perf_narrative = await get_performance_settings(cfg)
    if perf_narrative.narrative_mode in {"chaptered", "map_reduce"}:
        return await _run_top_down_branch(
            ctx=ctx,
            canvas=canvas,
            cleaned_transcript=cleaned_transcript,
            vision_runtime=vision_runtime,
            pipeline_provider=pipeline_provider,
            pro_llm_model=_pro_llm.model,
            llm_provider=llm_provider,
            llm_model=llm_model,
            target_reel_count=target_reel_count,
            vision_profile=vision_profile,
            narrative_mode=perf_narrative.narrative_mode,
        )

    # ─── Viral 2026 branch (Phase 9, 2026-04-22) ──────────────────────────
    # Простой OpusClip-style pipeline: один LLM call per chunk 20К знаков
    # эмиттит готовые рилсы по 5-block структуре + манифест Живого Кадра.
    # ~10-15 LLM calls на 90 мин видео vs 80-120 у Kartoziya.
    # Skipped vs bottom-up: extraction, reducer, story_doctor, variants,
    # composer, coherence_validator, closure_validator.
    # Kept: compression, canvas (уже построен выше — используется только для
    # cover selector), cover_selector, artifacts.
    if perf_narrative.narrative_mode == "viral_2026":
        return await _run_viral_2026_branch(
            ctx=ctx,
            canvas=canvas,
            cleaned_transcript=cleaned_transcript,
            vision_runtime=vision_runtime,
            pipeline_provider=pipeline_provider,
            llm_provider=llm_provider,
            llm_model=llm_model,
            vision_profile=vision_profile,
        )

    # T2.2/T6.1 Cross-session preference memory: лайкнутые рилсы из предыдущих
    # job'ов становятся few-shot anchors для extraction. Пустая строка если
    # лайков нет. Стоимость — только чтение БД + reel_plan.json файлов
    # (0 LLM calls на retrieval; embeddings считались при лайке).
    # Mode переключается через PerformanceSettings.preference_retrieval_mode:
    #   cosine — топ-5 семантически ближайших к текущему Canvas (query =
    #     centroid эмбеддингов candidate moments),
    #   top_by_date — legacy топ-8 свежих.
    perf_for_preference = await get_performance_settings(cfg)
    preference_mode = perf_for_preference.preference_retrieval_mode
    query_embedding: list[float] | None = None
    if preference_mode == "cosine":
        query_embedding = mean_embedding(
            [m.embedding for m in canvas.candidate_moments]
        )

    try:
        preference_anchors = await load_liked_anchors_text(
            artifact_store=art,
            current_job_id=job_id,
            retrieval_mode=preference_mode,
            query_embedding=query_embedding,
        )
    except Exception as exc:
        log.warning("preference_memory_load_failed", error=str(exc))
        preference_anchors = ""
    log.info(
        "preference_memory_loaded",
        mode=preference_mode,
        query_embedding_ready=query_embedding is not None,
        anchors_chars=len(preference_anchors),
        has_anchors=bool(preference_anchors),
    )

    await _advance(
        service, job_id, JobStage.analyze, 35,
        f"6 extraction-агентов × {len(chunks)} chunks"
        + (" + визуал (7-й параллельный)" if vision_runtime.enabled else ""),
    )
    extraction, visual_evidence = await _run_extraction_with_vision(
        chunks,
        canvas,
        source_path=source_path,
        source_duration_sec=media_info.duration_sec,
        vision_runtime=vision_runtime,
        profile_mask=profile_mask,
        cfg=cfg,
        preference_anchors=preference_anchors or None,
        pipeline_provider=pipeline_provider,
    )
    ctx.extraction_result = extraction
    art.write_json(
        job_id,
        "extraction_full.json",
        {
            "evidence_count": len(extraction.evidence),
            "failed_runs": extraction.failed_count,
            "by_agent": dict(
                collections.Counter(e.source_agent for e in extraction.evidence)
            ),
            "sample": [e.model_dump(mode="json") for e in extraction.evidence[:20]],
        },
    )

    await _advance(
        service, job_id, JobStage.analyze, 60,
        f"reduce + rank ({len(extraction.evidence)} evidence)",
    )
    # TIER2-#12: ensemble судей (1=off, 2-5=N параллельных + median + veto).
    perf_for_reduce = await get_performance_settings(cfg)
    reduce_result = await reduce_and_rank(
        extraction,
        canvas,
        source_duration_sec=media_info.duration_sec,
        ensemble_size=perf_for_reduce.reducer_ensemble_size,
        ensemble_veto_threshold=perf_for_reduce.reducer_ensemble_veto,
        pipeline_provider=pipeline_provider,
    )
    if visual_evidence.items:
        _enrich_ranked_with_visuals(reduce_result.ranked, visual_evidence)
    # Per-profile re-weighting: fashion/travel поднимают visual evidence,
    # talking_head — text. Инвариант: talking_head + vision_disabled →
    # baseline 0.7/0.3 → минимальное влияние на score relative to ranker.
    reduce_result.ranked.items = apply_profile_weights(
        reduce_result.ranked.items, profile_mask
    )

    # TIER2-#16: cross-chunk coherence reducer. Ищем противоречия между
    # кандидатами из разных chunks (факты/атрибуты/тезисы) и вырезаем их
    # одним доп. вызовом Flash Lite. Fallback — без фильтрации.
    if perf_for_reduce.cross_chunk_reducer_enabled and reduce_result.ranked.items:
        filtered_ranked, coherence_stats = await apply_cross_chunk_coherence(
            reduce_result.ranked,
            canvas,
            strictness=perf_for_reduce.cross_chunk_reducer_strictness,
            pipeline_provider=pipeline_provider,
        )
        if coherence_stats.saved:
            log.info(
                "cross_chunk_reducer_filtered",
                job_id=job_id,
                before=coherence_stats.before_count,
                after=coherence_stats.after_count,
                removed=coherence_stats.removed_count,
                strictness=perf_for_reduce.cross_chunk_reducer_strictness,
            )
            reduce_result = reduce_result.__class__(
                ranked=filtered_ranked,
                pre_dedup_count=reduce_result.pre_dedup_count,
                post_dedup_count=reduce_result.post_dedup_count,
            )
    ctx.reduce_result = reduce_result

    mode_result = detect_pipeline_mode(
        word_count=len(cleaned.words),
        duration_sec=media_info.duration_sec,
        voiced_duration_sec=sum(
            max(0.0, w.end - w.start) for w in cleaned.words
        ),
    )
    story_mode = mode_result.mode if vision_runtime.enabled else "dialogue"

    await _advance(
        service, job_id, JobStage.analyze, 72,
        f"3-act arc + book-end symmetry ({_pro_llm.model}, mode={story_mode})",
    )
    perf_for_toggles = await get_performance_settings(cfg)
    story_script, rhythm_report = await _compose_with_rhythm_loop(
        canvas=canvas,
        ranked=reduce_result.ranked,
        story_mode=story_mode,
        service=service,
        job_id=job_id,
        pipeline_provider=pipeline_provider,
        critique_loop_enabled=perf_for_toggles.rhythm_critique_loop_enabled,
    )

    # Stage 5.5.5 — visual validator (opt-in). Когда vision_enabled=False,
    # validate_arc() возвращает script без изменений (все visual_score=1.0).
    if vision_runtime.enabled:
        await _advance(
            service, job_id, JobStage.analyze, 84,
            "визуальная валидация arc (Moondream)",
        )
        story_script = await _apply_visual_validator(
            story_script,
            source_path=source_path,
            cfg=cfg,
            vision_profile=vision_profile,
        )
    ctx.story_script = story_script
    ctx.rhythm_report = rhythm_report
    art.write_json(
        job_id, "story_script.json", story_script.model_dump(mode="json")
    )
    log.info(
        "story_script_snapshot_saved",
        arc_len=len(story_script.arc),
        roles=dict(
            collections.Counter(s.role for s in story_script.arc)
        ),
        durations=[round(s.duration_sec, 1) for s in story_script.arc],
        total_duration_sec=round(
            sum(s.duration_sec for s in story_script.arc), 1
        ),
        bookend=bool(story_script.bookend_motif_id),
        alternates=len(story_script.alternates),
    )

    if perf_for_toggles.variants_generator_enabled:
        await _advance(
            service, job_id, JobStage.analyze, 88,
            f"генерация 4 форматов ({_pro_model_for_messaging(cfg, pipeline_provider)})",
        )
        variants = await generate_variants(
            canvas, reduce_result.ranked, story_script,
            pipeline_provider=pipeline_provider,
        )
    else:
        # Fix 5 — variants generator disabled: собираем single fallback
        # (long_philosophical копия base arc). Composer работает с этим
        # вариантом так же как с полноценной 4-форматной раскладкой.
        await _advance(
            service, job_id, JobStage.analyze, 88,
            "variants генерация пропущена (toggle off)",
        )
        from videomaker.services.variants_generator import _fallback_variants

        variants = _fallback_variants(story_script)
    ctx.variants = variants

    # T10.5 — pacing profile preference: если в runtime_settings задан
    # pacing_profile (через Auto Mode или manual override), передаём его в
    # composer для scoring bias.
    perf_for_composer = await get_performance_settings(cfg)
    composer_pacing_profile: str | None = None
    if hasattr(perf_for_composer, "pacing_profile"):
        composer_pacing_profile = getattr(
            perf_for_composer, "pacing_profile", None
        )

    # Multi-arc variant A: per-canvas-moment arcs (feature-flagged, default off).
    # Когда multi_arc_enabled=True — для каждого candidate_moment строится
    # отдельный StoryScript. Composer подхватывает их как candidate source
    # вместо legacy arc/variants путей (см. reels_composer._candidates_from_per_moment_arcs).
    # Flag off → per_moment_arcs=None → zero regression.
    per_moment_arcs: list[StoryScript] | None = None
    if perf_for_composer.multi_arc_enabled:
        await _advance(
            service, job_id, JobStage.analyze, 91,
            f"строим arc per moment ({len(canvas.candidate_moments)} штук)",
        )
        from videomaker.services.multi_arc_builder import build_arcs_per_moment
        # Multi-angle overproduction для long-form (>40 мин): 1 moment → 2 arcs
        # с разными window scales (1.0x узкий фокус + 2.0x расширенный контекст).
        # LLM даёт diverse arcs из разного evidence subset → композер получает
        # больше уникальных кандидатов. Короткие видео остаются single-angle,
        # чтобы не дублировать одни и те же моменты. Cap снят — композер
        # имеет свой max_count и pass-through для multi_arc режима.
        # Iteration 2026-04-22 (fix 1/4): расширенный разброс scales для
        # реальной angle-diversity. Было (1.0, 2.0) — слишком близко,
        # LLM получал почти одинаковый evidence subset и возвращал
        # идентичные arcs (дубли 4x в job f28943fb). Новые (0.7, 1.5):
        # узкое окно 0.7× видит только peak evidence → tight punchy arc
        # (25-40s), широкое 1.5× видит exposition context → longer arc
        # (50-70s). Min разброс scales = 2.14× → LLM не может совпасть.
        multi_angle_threshold_min = 40.0
        use_multi_angle = media_info.duration_sec / 60.0 > multi_angle_threshold_min
        window_scales = (0.7, 1.5) if use_multi_angle else (1.0,)
        per_moment_arcs = await build_arcs_per_moment(
            canvas=canvas,
            ranked=reduce_result.ranked,
            pipeline_provider=pipeline_provider,
            window_sec=perf_for_composer.multi_arc_window_sec,
            window_fallback_sec=perf_for_composer.multi_arc_window_fallback_sec,
            min_evidence=perf_for_composer.multi_arc_min_evidence_per_moment,
            max_arcs=None if use_multi_angle else target_reel_count,
            window_scales=window_scales,
        )
        log.info(
            "multi_arc_builder_complete",
            moments_count=len(canvas.candidate_moments),
            arcs_built=len(per_moment_arcs),
            target_reel_count=target_reel_count,
        )
        art.write_json(
            job_id,
            "per_moment_arcs.json",
            {
                "count": len(per_moment_arcs),
                "arcs": [arc.model_dump(mode="json") for arc in per_moment_arcs],
            },
        )

    analysis: AnalysisResult = compose_reels(
        canvas,
        reduce_result.ranked,
        story_script,
        variants,
        source_duration_sec=media_info.duration_sec,
        llm_model=_pro_model_for_messaging(cfg, pipeline_provider),
        provider="gemini",
        user_target_count=target_reel_count,
        pacing_profile_name=composer_pacing_profile,
        cross_context_penalty_enabled=True,
        reel_count_enforce_floor_ceiling=perf_for_composer.reel_count_enforce_floor_ceiling,
        reel_count_dedup_jaccard_threshold=perf_for_composer.reel_count_dedup_jaccard_threshold,
        per_moment_arcs=per_moment_arcs,
        cleaned_words=cleaned.words,
    )

    # Stage 5.9 — Arc-Coherence Validator. Проверяет что hook/body/payoff
    # рилса — одна связная мысль. Режимы off/reject/resort задаются через
    # /settings/performance. Нужен для Task #28 cross-group pull — без него
    # possible рилсы где payoff из другой части сюжета.
    perf = await get_performance_settings(cfg)
    if perf.coherence_mode != "off":
        await _advance(
            service, job_id, JobStage.analyze, 94,
            f"проверка связности рилсов (mode={perf.coherence_mode})",
        )
        analysis = await validate_coherence(
            analysis,
            cleaned.words,
            source_duration_sec=media_info.duration_sec,
            mode=perf.coherence_mode,
            threshold=perf.coherence_threshold,
            ranked=reduce_result.ranked,
            settings=cfg,
            pipeline_provider=pipeline_provider,
        )

    # Post-trim semantic closure validation: LLM Flash Lite проверяет
    # tail каждого рилса; обрывы мысли → extend к ближайшему ASR sentence
    # boundary (в пределах +5s). Счётчики closure_* попадают в stats.
    await _advance(
        service, job_id, JobStage.analyze, 95,
        "closure validation (semantic tail check)",
    )
    analysis = await validate_closures(
        analysis,
        cleaned.words,
        source_duration_sec=media_info.duration_sec,
        settings=cfg,
        canvas=canvas,
        pipeline_provider=pipeline_provider,
    )

    if vision_runtime.enabled:
        await _advance(
            service, job_id, JobStage.analyze, 97,
            "выбор thumbnail обложек (Moondream)",
        )
        analysis = await _apply_cover_selector(
            analysis,
            source_path=source_path,
            cfg=cfg,
        )

    # FEAT-#C: per-reel scoring — считаем rhythm/visual/narrative/composite
    # для каждого рилса, кладём в analysis_meta для последующего показа в UI.
    _populate_reel_scoring(
        analysis=analysis,
        rhythm_report=rhythm_report,
        story_script=story_script,
        has_bookend=bool(story_script.bookend_motif_id),
        vision_profile=vision_profile,
    )

    # T2.4: агрегат avg_composite_score через analysis.stats → прокидывается
    # в Job.options при mark_done и hoist'ится в JobRead (frontend показывает
    # настоящий средний балл в DashboardHero вместо placeholder 82).
    scores_for_avg = [
        r.composite_score for r in analysis.reels
        if r.composite_score is not None
    ]
    if scores_for_avg:
        analysis.stats["avg_composite_score"] = round(
            sum(scores_for_avg) / len(scores_for_avg), 1
        )

    analysis.stats.update({
        "evidence_pre_dedup": reduce_result.pre_dedup_count,
        "evidence_post_dedup": reduce_result.post_dedup_count,
        "rhythm_score": rhythm_report.overall_rhythm_score,
        "rhythm_pacing": rhythm_report.pacing_summary,
        "middle_sag_detected": rhythm_report.middle_sag_detected,
        "variants_kinds": ",".join(v.kind for v in variants.variants) or None,
        "failed_agent_runs": extraction.failed_count,
        "user_requested_llm": f"{llm_provider}:{llm_model}",
    })

    reel_plan_path = art.write_json(
        job_id,
        "reel_plan.json",
        {"reels": [reel.model_dump() for reel in analysis.reels]},
    )
    analysis_summary_path = art.write_json(
        job_id,
        "analysis_summary.json",
        {
            "stats": analysis.stats,
            "reel_count": len(analysis.reels),
            "llm_model": analysis.llm_model,
            "provider": analysis.provider,
            "canvas": {
                "central_theme": canvas.central_theme,
                "themes_count": len(canvas.themes),
                "motifs_count": len(canvas.motifs),
                "candidate_moments_count": len(canvas.candidate_moments),
                "bookend_motif_id": story_script.bookend_motif_id,
            },
            "rhythm": {
                "score": rhythm_report.overall_rhythm_score,
                "pacing": rhythm_report.pacing_summary,
                "middle_sag": rhythm_report.middle_sag_detected,
                "issues": len(rhythm_report.issues),
            },
        },
    )
    await service.add_artifact(
        job_id,
        kind=ArtifactKind.reel_plan,
        path=str(reel_plan_path.relative_to(art.job_dir(job_id))),
        meta={"reel_count": len(analysis.reels)},
    )
    await _advance(
        service,
        job_id,
        JobStage.analyze,
        100,
        f"план готов: {len(analysis.reels)} рилсов",
    )

    ctx.analysis = analysis
    ctx.analysis_reels = list(analysis.reels)
    ctx.reel_plan_path = reel_plan_path
    ctx.analysis_summary_path = analysis_summary_path

    return ctx


async def _run_top_down_branch(
    *,
    ctx: PipelineContext,
    canvas: ProjectCanvas,
    cleaned_transcript: TranscriptResult,
    vision_runtime: VisionRuntimeSettings,
    pipeline_provider: str,
    pro_llm_model: str,
    llm_provider: str,
    llm_model: str,
    target_reel_count: int | None,
    vision_profile: VisionProfile,
    narrative_mode: str = "chaptered",
) -> PipelineContext:
    """Top-down narrative pipeline (Phase 6+8 роутинг).

    narrative_mode:
      - "chaptered" (Phase 1-6) — chapter_builder → hook_detector → arc_finder.
        Сохраняется для отката.
      - "map_reduce" (Phase 8) — OpusClip-parity: global_context → parallel
        chunk_scorer → clip_reducer → boundary_extender. Production target.

    Skipped vs bottom-up (обоих режимов): extraction, reducer, story_doctor,
    variants, composer, coherence_validator, closure_validator.

    Kept: compression, canvas, cover_selector, scoring, stats, artifacts.
    """

    from videomaker.services.pipeline import _advance

    job_id = ctx.job_id
    source_path = ctx.source_path
    service = ctx.service
    art = ctx.artifacts
    cfg = ctx.settings

    assert ctx.media_info is not None, "top_down branch: media_info не заполнен"
    source_duration_sec = ctx.media_info.duration_sec

    if narrative_mode == "map_reduce":
        stage_msg = (
            f"map-reduce narrative: global ctx → parallel chunks → "
            f"reducer ({pro_llm_model})"
        )
        # map_reduce orchestrator сам рассчитает density-based target если 0.
        effective_target = target_reel_count or 0
    else:
        stage_msg = (
            f"chaptered narrative: chaptering → hooks → arcs ({pro_llm_model})"
        )
        effective_target = (
            target_reel_count if target_reel_count and target_reel_count > 0 else 15
        )

    await _advance(service, job_id, JobStage.analyze, 40, stage_msg)

    if narrative_mode == "map_reduce":
        analysis = await orchestrate_map_reduce(
            transcript=cleaned_transcript,
            canvas=canvas,
            source_duration_sec=source_duration_sec,
            target_count=effective_target,
            settings=cfg,
            pipeline_provider=pipeline_provider,
            artifact_store=art,
            job_id=job_id,
            llm_pro_model=pro_llm_model,
        )
    else:
        analysis = await orchestrate_top_down(
            transcript=cleaned_transcript,
            canvas=canvas,
            source_duration_sec=source_duration_sec,
            target_count=effective_target,
            settings=cfg,
            pipeline_provider=pipeline_provider,
            artifact_store=art,
            job_id=job_id,
            llm_pro_model=pro_llm_model,
        )

    # Cover selector (если vision enabled) — universal post-processor.
    if vision_runtime.enabled and analysis.reels:
        await _advance(
            service, job_id, JobStage.analyze, 92,
            "выбор thumbnail обложек (Moondream)",
        )
        analysis = await _apply_cover_selector(
            analysis,
            source_path=source_path,
            cfg=cfg,
        )

    # Scoring (simplified для top-down: narrative_score от ranker,
    # rhythm/visual пропускаем — not applicable к natural arcs).
    for reel in analysis.reels:
        if reel.narrative_score is not None and reel.composite_score is None:
            reel.composite_score = round(reel.narrative_score * 100, 1)

    # Stats enrichment (совместимо с bottom-up).
    scores_for_avg = [
        r.composite_score for r in analysis.reels if r.composite_score is not None
    ]
    if scores_for_avg:
        analysis.stats["avg_composite_score"] = round(
            sum(scores_for_avg) / len(scores_for_avg), 1
        )

    analysis.stats["user_requested_llm"] = f"{llm_provider}:{llm_model}"
    analysis.stats["vision_enabled"] = str(bool(vision_runtime.enabled))
    analysis.stats["profile_detected"] = str(vision_profile.value)

    # Final artifacts (bottom-up совместимые имена файлов).
    reel_plan_path = art.write_json(
        job_id,
        "reel_plan.json",
        {"reels": [reel.model_dump() for reel in analysis.reels]},
    )
    analysis_summary_path = art.write_json(
        job_id,
        "analysis_summary.json",
        {
            "stats": analysis.stats,
            "reel_count": len(analysis.reels),
            "llm_model": analysis.llm_model,
            "provider": analysis.provider,
            "narrative_mode": "top_down",
            "canvas": {
                "central_theme": canvas.central_theme,
                "themes_count": len(canvas.themes),
                "motifs_count": len(canvas.motifs),
                "candidate_moments_count": len(canvas.candidate_moments),
            },
        },
    )
    await service.add_artifact(
        job_id,
        kind=ArtifactKind.reel_plan,
        path=str(reel_plan_path.relative_to(art.job_dir(job_id))),
        meta={"reel_count": len(analysis.reels), "narrative_mode": "top_down"},
    )

    await _advance(
        service, job_id, JobStage.analyze, 100,
        f"top-down план готов: {len(analysis.reels)} рилсов",
    )

    ctx.analysis = analysis
    ctx.analysis_reels = list(analysis.reels)
    ctx.reel_plan_path = reel_plan_path
    ctx.analysis_summary_path = analysis_summary_path

    return ctx


async def _run_viral_2026_branch(
    *,
    ctx: PipelineContext,
    canvas: ProjectCanvas,
    cleaned_transcript: TranscriptResult,
    vision_runtime: VisionRuntimeSettings,
    pipeline_provider: str | None,
    llm_provider: str,
    llm_model: str,
    vision_profile: VisionProfile,
) -> PipelineContext:
    """Viral 2026 simple pipeline (Phase 9).

    Bypass Kartoziya 9-stage. Один LLM call per chunk 20К знаков эмиттит
    готовые рилсы по 5-block структуре + манифест Живого Кадра.

    Skipped vs bottom-up: extraction, reducer, story_doctor, variants,
    composer, coherence_validator, closure_validator.
    Kept: compression, canvas (только для cover_selector), cover_selector,
    artifacts (bottom-up совместимые).
    """
    from videomaker.services.pipeline import _advance
    from videomaker.services.viral_arc_builder import build_viral_arcs

    job_id = ctx.job_id
    source_path = ctx.source_path
    service = ctx.service
    art = ctx.artifacts
    cfg = ctx.settings

    # Резолвим фактического провайдера/модель ОДИН раз — артефакт должен
    # отражать реальный рантайм, а не хардкод gemini (см. bottom-up).
    resolved_provider = pipeline_provider or "gemini"
    resolved_model = _viral_model_for_messaging(cfg, pipeline_provider)

    await _advance(
        service, job_id, JobStage.analyze, 40,
        f"viral 2026: chunked LLM build ({resolved_provider})",
    )

    reels = await build_viral_arcs(
        cleaned_transcript, cfg=cfg, pipeline_provider=pipeline_provider
    )

    analysis = AnalysisResult(
        reels=reels,
        llm_model=resolved_model,
        provider=resolved_provider,
        stats={
            "narrative_mode": "viral_2026",
            "reel_count": len(reels),
        },
    )

    if vision_runtime.enabled and analysis.reels:
        await _advance(
            service, job_id, JobStage.analyze, 92,
            "выбор thumbnail обложек (Moondream)",
        )
        analysis = await _apply_cover_selector(
            analysis,
            source_path=source_path,
            cfg=cfg,
        )

    scores_for_avg = [
        r.composite_score for r in analysis.reels if r.composite_score is not None
    ]
    if scores_for_avg:
        analysis.stats["avg_composite_score"] = round(
            sum(scores_for_avg) / len(scores_for_avg), 1
        )

    analysis.stats["user_requested_llm"] = f"{llm_provider}:{llm_model}"
    analysis.stats["vision_enabled"] = str(bool(vision_runtime.enabled))
    analysis.stats["profile_detected"] = str(vision_profile.value)

    reel_plan_path = art.write_json(
        job_id,
        "reel_plan.json",
        {"reels": [reel.model_dump() for reel in analysis.reels]},
    )
    analysis_summary_path = art.write_json(
        job_id,
        "analysis_summary.json",
        {
            "stats": analysis.stats,
            "reel_count": len(analysis.reels),
            "llm_model": analysis.llm_model,
            "provider": analysis.provider,
            "narrative_mode": "viral_2026",
            "canvas": {
                "central_theme": canvas.central_theme,
                "themes_count": len(canvas.themes),
                "motifs_count": len(canvas.motifs),
                "candidate_moments_count": len(canvas.candidate_moments),
            },
        },
    )
    await service.add_artifact(
        job_id,
        kind=ArtifactKind.reel_plan,
        path=str(reel_plan_path.relative_to(art.job_dir(job_id))),
        meta={"reel_count": len(analysis.reels), "narrative_mode": "viral_2026"},
    )

    await _advance(
        service, job_id, JobStage.analyze, 100,
        f"viral 2026 план готов: {len(analysis.reels)} рилсов",
    )

    ctx.analysis = analysis
    ctx.analysis_reels = list(analysis.reels)
    ctx.reel_plan_path = reel_plan_path
    ctx.analysis_summary_path = analysis_summary_path

    return ctx


async def _run_extraction_with_vision(
    chunks: list,  # TranscriptChunk list
    canvas: ProjectCanvas,
    *,
    source_path: Path,
    source_duration_sec: float,
    vision_runtime: VisionRuntimeSettings,
    profile_mask: ProfileMask,
    cfg: Settings,
    preference_anchors: str | None = None,
    pipeline_provider: str | None = None,
) -> tuple[ExtractionResult, VisualEvidenceResult]:
    """Запускает text-агентов (subset по profile mask) и визуального
    агента параллельно через gather.

    `profile_mask` уже содержит пользовательские override'ы (resolved через
    `get_effective_profile_mask`). Если ``vision_enabled=False`` — маска
    игнорируется и запускаются все 6 агентов (инвариант: без визуального
    пути нельзя урезать text-анализ, иначе fashion без vision = ничего не
    находит).

    При vision disabled возвращает (extraction, empty VisualEvidenceResult).
    Ошибка визуального пути не ломает extraction — vision ветка catch-all →
    empty result.
    """
    enabled_agents = get_enabled_agents_for_mask(
        profile_mask, vision_enabled=vision_runtime.enabled
    )

    if not vision_runtime.enabled:
        extraction = await orchestrate_extraction(
            chunks,
            canvas,
            enabled_agents=enabled_agents,
            preference_anchors=preference_anchors,
            pipeline_provider=pipeline_provider,
        )
        return extraction, VisualEvidenceResult()

    async def _run_vision() -> VisualEvidenceResult:
        try:
            client = build_vision_client(cfg, provider=vision_runtime.provider)
            if client is None:
                return VisualEvidenceResult()
            video_hash = await compute_video_sha256(source_path)
            extractor = FrameExtractor(cfg.vision_cache_dir)
            cache = VisionResultCache(cfg.vision_cache_dir)
            limiter = get_vision_rate_limiter(cfg)
            return await run_visual_evidence_agent(
                source_path,
                source_duration_sec,
                video_hash,
                client=client,
                extractor=extractor,
                cache=cache,
                limiter=limiter,
                sample_rate_sec=vision_runtime.frame_sample_rate_sec,
            )
        except Exception as exc:
            log.warning("visual_evidence_agent_skipped", error=str(exc))
            return VisualEvidenceResult()

    extraction, visual_evidence = await asyncio.gather(
        orchestrate_extraction(
            chunks,
            canvas,
            enabled_agents=enabled_agents,
            preference_anchors=preference_anchors,
            pipeline_provider=pipeline_provider,
        ),
        _run_vision(),
    )
    return extraction, visual_evidence


def _enrich_ranked_with_visuals(
    ranked: RankedEvidence,
    visual_evidence: VisualEvidenceResult,
    *,
    tolerance_sec: float = 3.0,
) -> None:
    """Mutates ranked.items: добавляет visual_caption + visual_tags от
    ближайшего VisualEvidenceItem в пределах tolerance.

    In-place mutation оправдана: RankedEvidence — dataclass-like Pydantic с
    list items. Rewrite всего RankedEvidence в этом месте неэффективно.
    """
    if not visual_evidence.items or not ranked.items:
        return

    enriched = 0
    new_items: list = []
    for item in ranked.items:
        midpoint = (item.start + item.end) / 2.0
        closest = visual_evidence.at(midpoint, tolerance=tolerance_sec)
        if closest is None:
            new_items.append(item)
            continue
        tags: list[str] = []
        if closest.has_person:
            tags.append("has_person")
        if closest.person_position:
            tags.append(f"person_{closest.person_position}")
        if closest.main_object:
            tags.append(f"object_{closest.main_object}")
        new_items.append(
            item.model_copy(
                update={
                    "visual_caption": closest.caption,
                    "visual_tags": tags,
                }
            )
        )
        enriched += 1
    ranked.items = new_items
    log.info(
        "visual_evidence_merged_to_ranked",
        ranked_total=len(new_items),
        enriched=enriched,
        visual_observations=len(visual_evidence.items),
    )


async def _apply_cover_selector(
    analysis: AnalysisResult,
    *,
    source_path: Path,
    cfg: Settings,
) -> AnalysisResult:
    """Запускает cover_selector.select_cover() для каждого reel.

    Берёт reel_start_sec как source_start первого segment'а. При любой ошибке
    инициализации vision-слоя возвращает analysis без изменений (fallback =
    renderer использует first-frame как раньше).
    """
    try:
        client = build_vision_client(cfg)
        if client is None:
            return analysis
        video_hash = await compute_video_sha256(source_path)
        extractor = FrameExtractor(cfg.vision_cache_dir)
        limiter = get_vision_rate_limiter(cfg)
    except Exception as exc:
        log.warning("cover_selector_init_failed", error=str(exc))
        return analysis

    async def _cover_for_reel(reel: ReelPlan) -> ReelPlan:
        if not reel.segments:
            return reel
        reel_start = min(s.source_start for s in reel.segments)
        try:
            result = await select_cover(
                reel.reel_id,
                source_path,
                video_hash,
                reel_start,
                client=client,
                extractor=extractor,
                limiter=limiter,
            )
        except Exception as exc:
            log.warning("cover_selector_failed", reel_id=reel.reel_id, error=str(exc))
            return reel
        if not result.is_selected or result.frame_path is None:
            return reel
        return reel.model_copy(
            update={
                "cover_timestamp_sec": result.timestamp_sec,
                "cover_path": str(result.frame_path),
                "cover_score": round(result.score, 3),
            }
        )

    updated_reels = await asyncio.gather(
        *(_cover_for_reel(r) for r in analysis.reels)
    )
    return analysis.model_copy(update={"reels": list(updated_reels)})


async def _apply_visual_validator(
    story_script: StoryScript,
    *,
    source_path: Path,
    cfg: Settings,
    vision_profile: VisionProfile = VisionProfile.talking_head,
) -> StoryScript:
    """Обёртка над validate_arc: собирает все зависимости vision-слоя.

    При любой ошибке vision-инициализации возвращает script без изменений —
    фаза визуальной валидации не должна ломать основной пайплайн.

    Для ``vision_profile=talking_head`` дополнительно вычисляется
    geometric face_centering_score через face_tracker (кэшируется на
    диске по SHA256, render stage переиспользует). Для других профилей
    face_centering_score вычисляется но без penalty.
    """
    try:
        client = build_vision_client(cfg)
        if client is None:
            return story_script
        video_hash = await compute_video_sha256(source_path)
        extractor = FrameExtractor(cfg.vision_cache_dir)
        cache = VisionResultCache(cfg.vision_cache_dir)
        limiter = get_vision_rate_limiter(cfg)
        # Face tracking для geometric centering score (shared с render stage
        # через disk cache по SHA256 — повторный track_faces идемпотентен).
        face_track = None
        try:
            face_track = await track_faces(
                video_path=source_path,
                sample_interval_sec=cfg.face_tracker_sample_interval_sec,
                cache_dir=cfg.app_face_cache_dir,
                models_dir=cfg.app_models_dir,
                min_confidence=cfg.face_tracker_min_confidence,
            )
        except FaceTrackerError as ft_exc:
            log.warning(
                "visual_validator_face_track_failed",
                error=str(ft_exc),
            )
        apply_penalty = vision_profile == VisionProfile.talking_head
        return await validate_arc(
            story_script,
            video_path=source_path,
            video_hash=video_hash,
            client=client,
            extractor=extractor,
            cache=cache,
            limiter=limiter,
            face_track=face_track,
            apply_centering_penalty=apply_penalty,
        )
    except Exception as exc:
        log.warning("visual_validator_skipped", error=str(exc))
        return story_script


def _transcript_from_cleaned(
    cleaned: CleanedTranscript,
    original: TranscriptResult,
) -> TranscriptResult:
    """Собирает «урезанный» TranscriptResult из cleaned.words, чтобы analyzer
    работал поверх отфильтрованных слов. Сегменты пересчитываются группировкой.
    """

    segments = merge_words_into_segments(cleaned.words)
    return TranscriptResult(
        transcriber=original.transcriber,
        model=original.model,
        language=original.language,
        duration_sec=cleaned.source_duration_sec,
        segments=segments,
        words=cleaned.words,
        raw_metadata={**original.raw_metadata, "cleaned": True, **cleaned.stats},
    )


def _populate_reel_scoring(
    *,
    analysis: AnalysisResult,
    rhythm_report: RhythmReport,
    story_script: StoryScript | None,
    has_bookend: bool,
    vision_profile: VisionProfile | None = None,
) -> None:
    """FEAT-#C: заполняет rhythm_score/visual_score/narrative_score/composite_score
    для каждого рилса в analysis.reels. Мутирует reel'ы напрямую.

    Формула composite (0-100):
      - duration_fit  — 35%  (optimal 30-60s, drop-off за пределами)
      - rhythm_score  — 25%  (overall_rhythm_score × 100)
      - visual_score  — 20%  (average по сегментам рилса)
      - narrative     — 15%  (closure + bookend)
      - trend_score   — 5%   (T2.4: per-profile trend_lexicons × hook + reasoning)
    """
    rhythm_global = max(0.0, min(1.0, rhythm_report.overall_rhythm_score))
    # Visual-score per reel: матчим сегменты рилса с story_script.acts по времени.
    # Legacy: в старых ревизиях StoryScript было поле `acts: list[Act]`; сейчас
    # — `arc: list[StorySegment]`. Блок остаётся как защитный fallback на случай
    # десериализации старых JSON-артефактов — reflection через getattr.
    visual_by_reel: dict[str, float] = {}
    legacy_acts = getattr(story_script, "acts", None) if story_script is not None else None
    if legacy_acts:
        for reel in analysis.reels:
            scores: list[float] = []
            if not reel.segments:
                continue
            reel_start = min(s.source_start for s in reel.segments)
            reel_end = max(s.source_end for s in reel.segments)
            for act in legacy_acts:
                for seg in getattr(act, "segments", []):
                    seg_start = getattr(seg, "source_start", None)
                    seg_end = getattr(seg, "source_end", None)
                    seg_vs = getattr(seg, "visual_score", None)
                    if seg_start is None or seg_end is None or seg_vs is None:
                        continue
                    if seg_end >= reel_start and seg_start <= reel_end:
                        scores.append(max(0.0, min(1.0, float(seg_vs))))
            if scores:
                visual_by_reel[reel.reel_id] = sum(scores) / len(scores)

    for reel in analysis.reels:
        reel.rhythm_score = rhythm_global
        reel.visual_score = visual_by_reel.get(reel.reel_id)
        # Narrative: 0.7 baseline + 0.2 если bookend + 0.1 если duration fit
        narrative = 0.7
        if has_bookend:
            narrative += 0.2
        duration = reel.predicted_duration_sec
        if 25.0 <= duration <= 75.0:
            narrative += 0.1
        reel.narrative_score = min(1.0, narrative)

        # Composite 0-100
        duration_fit = _duration_fit_score(duration)
        rhythm_pct = rhythm_global * 100
        visual_pct = (reel.visual_score if reel.visual_score is not None else 0.7) * 100
        narrative_pct = reel.narrative_score * 100
        # T2.4: trend_score — hit-rate по per-profile лексикону на hook +
        # reasoning всех сегментов. Без LLM, O(слова × лексикон).
        # Custom профиль или пустой текст → baseline 0.5.
        trend_text = reel.hook or ""
        if reel.segments:
            trend_text += " " + " ".join(
                getattr(s, "reasoning", "") for s in reel.segments
            )
        trend_pct = (
            compute_trend_score(trend_text, vision_profile) * 100
            if vision_profile is not None
            else 70.0
        )
        composite = (
            0.35 * duration_fit
            + 0.25 * rhythm_pct
            + 0.20 * visual_pct
            + 0.15 * narrative_pct
            + 0.05 * trend_pct
        )
        reel.composite_score = round(max(0.0, min(100.0, composite)), 1)


def _duration_fit_score(sec: float) -> float:
    """Оптимум 30-60 сек для Reels/Shorts. Drop-off за пределами."""

    if sec < 10:
        return 55.0
    if sec < 20:
        return 78.0
    if sec < 30:
        return 92.0
    if sec <= 60:
        return 100.0
    if sec <= 90:
        return 92.0
    if sec <= 120:
        return 80.0
    if sec <= 180:
        return 68.0
    return 55.0


async def _compose_with_rhythm_loop(
    *,
    canvas: ProjectCanvas,
    ranked: RankedEvidence,
    story_mode: str,
    service: JobService,
    job_id: str,
    pipeline_provider: str | None = None,
    critique_loop_enabled: bool = True,
) -> tuple[StoryScript, RhythmReport]:
    """T1.3 Story Doctor ↔ Rhythm critique loop.

    Первая итерация — обычный compose_story_script без critique.
    Rhythm check. Если score < _RHYTHM_MIN_ACCEPTABLE → собираем critique
    из RhythmReport.issues и re-compose с injected critique в user payload.
    Max 2 итерации. Держим best-so-far (по rhythm_score) — если итерация
    2 ухудшила, возвращаем script итерации 1.

    Если ``critique_loop_enabled=False`` (Fix 5 toggle) — отдаём результат
    первого прохода без повторных compose. Это отключает corrective loop
    для экспериментов с вариабельностью и экономии LLM.

    Returns ``(best_script, best_report)``.
    """
    from videomaker.services.pipeline import _advance

    pro_model_label = _pro_model_for_messaging(get_settings(), pipeline_provider)
    await _advance(
        service, job_id, JobStage.analyze, 72,
        f"3-act arc + book-end symmetry ({pro_model_label}, mode={story_mode})",
    )
    script = await compose_story_script(
        canvas, ranked, mode=story_mode, pipeline_provider=pipeline_provider
    )

    await _advance(
        service, job_id, JobStage.analyze, 78, "rhythm check (middle-sag)"
    )
    report = await check_rhythm(script, pipeline_provider=pipeline_provider)

    best_script = script
    best_report = report

    if not critique_loop_enabled:
        log.info(
            "rhythm_critique_loop_disabled",
            reason="toggle_off",
            initial_score=round(best_report.overall_rhythm_score, 3),
        )
        return best_script, best_report

    for iteration in range(1, _RHYTHM_MAX_ITERATIONS + 1):
        if best_report.overall_rhythm_score >= _RHYTHM_MIN_ACCEPTABLE:
            break
        critique = _build_rhythm_critique(best_report, iteration=iteration)
        log.info(
            "rhythm_critique_loop_start",
            iteration=iteration,
            prev_score=round(best_report.overall_rhythm_score, 3),
            issues=len(best_report.issues),
            middle_sag=best_report.middle_sag_detected,
        )
        await _advance(
            service, job_id, JobStage.analyze, 79,
            f"rhythm critique pass #{iteration} (score {best_report.overall_rhythm_score:.2f} < "
            f"{_RHYTHM_MIN_ACCEPTABLE})",
        )
        new_script = await compose_story_script(
            canvas, ranked, mode=story_mode, rhythm_critique=critique,
            pipeline_provider=pipeline_provider,
        )
        new_report = await check_rhythm(new_script, pipeline_provider=pipeline_provider)
        log.info(
            "rhythm_critique_loop_result",
            iteration=iteration,
            new_score=round(new_report.overall_rhythm_score, 3),
            improved=new_report.overall_rhythm_score > best_report.overall_rhythm_score,
        )
        if new_report.overall_rhythm_score > best_report.overall_rhythm_score:
            best_script = new_script
            best_report = new_report
        else:
            # Регрессия — не принимаем, выходим (дальнейшие итерации обычно
            # усугубят; лучше оставить best-so-far).
            break

    if best_report.overall_rhythm_score < _RHYTHM_MIN_ACCEPTABLE:
        log.warning(
            "rhythm_critique_loop_exhausted",
            final_score=round(best_report.overall_rhythm_score, 3),
            threshold=_RHYTHM_MIN_ACCEPTABLE,
        )

    return best_script, best_report


def _build_rhythm_critique(report: RhythmReport, *, iteration: int) -> str:
    """Формирует текст критики для инъекции в повторный compose_story_script.

    Описывает конкретные проблемы из RhythmReport (middle_sag, issues list)
    и даёт указания: не повторять ошибку, использовать `alternates`, сменить
    evidence_id в проблемной позиции.
    """
    lines: list[str] = [
        f"=== РИТМИЧЕСКАЯ КРИТИКА (итерация #{iteration}) ===",
        f"Предыдущая версия арки получила rhythm_score="
        f"{report.overall_rhythm_score:.2f} (порог {_RHYTHM_MIN_ACCEPTABLE}).",
    ]
    if report.middle_sag_detected:
        lines.append(
            "middle_sag_detected=True: середина арки провисает "
            "(повторяющиеся beats, одинаковая интенсивность, затянутые "
            "сегменты). При переделке — поставь контраст beat или "
            "сократи средние сегменты, либо замени их на alternates."
        )
    if report.pacing_summary == "монотонный":
        lines.append(
            "pacing=«монотонный»: все beats одинаковой интенсивности. "
            "Смешай strain/relief/reveal по arc, не держи один тон "
            "3+ сегментов подряд."
        )
    if report.pacing_summary == "рваный":
        lines.append(
            "pacing=«рваный»: переходы слишком резкие. Смягчи beat-транзиции "
            "через setup-сегмент или сглаживающий development."
        )

    issues = list(report.issues)[:5]
    if issues:
        lines.append("")
        lines.append("Конкретные проблемы:")
        for idx, issue in enumerate(issues, start=1):
            lines.append(
                f"  {idx}. region={issue.region} severity={issue.severity}: "
                f"{issue.reason}"
            )
            if issue.recommendation_action != "none":
                hint = issue.recommendation_action
                if issue.alternate_evidence_id:
                    hint += f" → попробуй evidence_id={issue.alternate_evidence_id}"
                lines.append(f"     действие: {hint}")

    lines.append("")
    lines.append(
        "ИНСТРУКЦИЯ: переделай arc учтя критику. НЕ меняй уже корректные "
        "сегменты — фокус на исправлении перечисленных проблем. Используй "
        "alternates из ranked evidence где это возможно. Сохрани central_theme "
        "и bookend_motif_id если они были корректны."
    )
    return "\n".join(lines)
