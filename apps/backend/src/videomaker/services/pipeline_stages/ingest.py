"""Ingest phase — stages 1-4: probe, proxy, transcribe, translate, silence_cut.

Принимает ``PipelineContext`` с заполненными входными параметрами (job_id,
source_path, cfg, service, artifacts, perf) и возвращает контекст с
заполненными полями: ``media_info``, ``proxy_path``, ``media_path_for_decode``,
``transcript``, ``transcript_segments``, ``transcript_words``,
``detected_language``, ``needs_translation``, ``cleaned_transcript``,
``cleaned_segments``, ``cleaned_words``, ``transcript_path``, ``cleaned_path``.

Извлечено из ``services.pipeline::_run_pipeline_impl`` в Phase 2.2.
"""

from __future__ import annotations

from videomaker.core.logging import get_logger
from videomaker.models.job import TARGET_LANGUAGE, ArtifactKind, JobStage
from videomaker.services.media import extract_audio, probe
from videomaker.services.pipeline_context import PipelineContext
from videomaker.services.prompt_store import get_prompt
from videomaker.services.prompts import PromptKey
from videomaker.services.proxy import (
    ProxyProfile,
    cleanup_proxies,
    generate_or_get_proxy,
    should_skip_proxy,
)
from videomaker.services.silence_cutter import (
    clean_transcript,
)
from videomaker.services.silence_cutter import (
    load_config as load_silence_config,
)
from videomaker.services.transcribers.base import TranscriptResult
from videomaker.services.transcribers.cache import TranscriptCache
from videomaker.services.transcribers.factory import (
    build_transcriber,
    transcribe_with_cache,
)
from videomaker.services.translator import Translator, TranslatorConfig
from videomaker.services.vision import compute_video_sha256

log = get_logger(__name__)


async def run_ingest_stage(ctx: PipelineContext) -> PipelineContext:
    """Ingest phase — probe → proxy → transcribe → translate → silence_cut.

    Обогащает context media_info, proxy_path, transcript, cleaned segments/words,
    detected_language и пишет артефакты transcript.json, cleaned_transcript.json
    через ``ctx.artifacts``.
    """
    # Локальный импорт чтобы избежать циклической зависимости с pipeline.py.
    from videomaker.services.pipeline import _advance

    job_id = ctx.job_id
    source_path = ctx.source_path
    service = ctx.service
    art = ctx.artifacts
    cfg = ctx.settings
    perf = ctx.perf

    # ===== Stage 1: ingest (probe) =====
    await _advance(service, job_id, JobStage.ingest, 0, "probe исходного видео")
    media_info = await probe(source_path)
    await service.set_source_duration(job_id, media_info.duration_sec)
    await _advance(
        service,
        job_id,
        JobStage.ingest,
        100,
        f"готов: {media_info.duration_sec:.1f}s, {media_info.width}x{media_info.height}",
    )
    ctx.media_info = media_info

    # ===== Stage 1b: proxy_generate (опционально) =====
    media_path_for_decode = source_path
    if ctx.use_proxy and perf.proxy_enabled:
        skip_reason = should_skip_proxy(
            media_info,
            skip_height_le=perf.proxy_skip_height_le,
            skip_duration_lt_sec=perf.proxy_skip_duration_lt_sec,
            skip_bitrate_lt_kbps=perf.proxy_skip_bitrate_lt_kbps,
        )
        if skip_reason is not None:
            log.info("proxy_skipped", job_id=job_id, reason=skip_reason)
            await _advance(
                service, job_id, JobStage.proxy_generate, 100, f"proxy не нужен: {skip_reason}"
            )
        else:
            await _advance(
                service, job_id, JobStage.proxy_generate, 0, "генерация proxy 1080p H.264"
            )
            profile = ProxyProfile(
                max_dim=perf.proxy_max_dim,
                video_crf=perf.proxy_video_crf,
                video_maxrate_kbps=perf.proxy_video_maxrate_kbps,
                audio_bitrate_kbps=perf.proxy_audio_bitrate_kbps,
            )
            outcome = await generate_or_get_proxy(
                source_path=source_path,
                cache_dir=cfg.app_proxies_dir,
                profile=profile,
                lock_timeout_sec=perf.proxy_lock_timeout_sec,
            )
            media_path_for_decode = outcome.path
            await service.add_artifact(
                job_id,
                kind=ArtifactKind.proxy,
                path=str(outcome.path),  # global cache path (вне job_dir), храним как абсолютный
                meta={
                    "sha256": outcome.sha256,
                    "profile_id": outcome.profile_id,
                    "cache_hit": outcome.cache_hit,
                    "wall_time_sec": outcome.wall_time_sec,
                    "file_size_bytes": outcome.file_size_bytes,
                },
            )
            await _advance(
                service,
                job_id,
                JobStage.proxy_generate,
                100,
                f"proxy готов ({'кэш' if outcome.cache_hit else 'свежий'})",
            )
            # Cleanup стареющего кэша после успешной генерации
            cleanup_proxies(
                cfg.app_proxies_dir,
                max_size_bytes=perf.proxy_cache_max_gb * 1024 * 1024 * 1024,
            )
    ctx.media_path_for_decode = media_path_for_decode
    ctx.proxy_path = media_path_for_decode if media_path_for_decode != source_path else None

    # ===== Stage 2: transcribe (с SHA256-keyed кэшем) =====
    transcriber_name = ctx.transcriber_name
    force_reingest = ctx.force_reingest
    source_language = ctx.source_language

    await _advance(
        service, job_id, JobStage.transcribe, 0, f"транскрибация ({transcriber_name})"
    )
    transcript_cache = TranscriptCache(cfg.transcript_cache_dir)
    transcriber = build_transcriber(transcriber_name, cfg)
    language_hint: str | None = None if source_language == "auto" else source_language
    # force_reingest приходит из Job.force_reingest (Phase 1.3 — wired end-to-end)

    # Early lookup — если транскрипт есть и совпадает backend+model,
    # пропускаем дорогую extract_audio + STT полностью.
    source_size_mb = max(1, source_path.stat().st_size // (1024 * 1024))
    await _advance(
        service,
        job_id,
        JobStage.transcribe,
        3,
        f"вычисление SHA256 контента ({source_size_mb} MB)…",
    )
    video_hash = await compute_video_sha256(source_path)
    cached_entry = None
    if not force_reingest:
        await _advance(
            service,
            job_id,
            JobStage.transcribe,
            7,
            f"проверка кэша транскриптов (SHA {video_hash[:10]}…)",
        )
        cached_entry = await transcript_cache.lookup(
            source_path, video_hash=video_hash
        )

    if (
        cached_entry is not None
        and cached_entry.meta.backend == transcriber.name
        and cached_entry.meta.model == transcriber.model
    ):
        transcript: TranscriptResult = cached_entry.result
        cache_hit = True
        await _advance(
            service,
            job_id,
            JobStage.transcribe,
            60,
            f"кэш hit: {cached_entry.meta.word_count} слов (SHA {video_hash[:10]}…)",
            extra={
                "transcript_cache": "hit",
                "video_hash": video_hash,
                "cached_word_count": cached_entry.meta.word_count,
                "cached_wpm": round(cached_entry.meta.wpm, 2),
                "cached_backend": cached_entry.meta.backend,
                "cached_model": cached_entry.meta.model,
                "cached_duration_sec": cached_entry.meta.duration_sec,
            },
        )
    else:
        miss_reason = "force_reingest" if force_reingest else "no_cache"
        await _advance(
            service,
            job_id,
            JobStage.transcribe,
            10,
            f"извлечение аудио из видео ({miss_reason})…",
            extra={
                "transcript_cache": "miss",
                "transcript_cache_reason": miss_reason,
                "video_hash": video_hash,
            },
        )
        audio_path = art.path_for(job_id, "audio", "source.wav")
        await extract_audio(media_path_for_decode, audio_path)
        await _advance(
            service,
            job_id,
            JobStage.transcribe,
            20,
            f"аудио извлечено → запуск {transcriber_name} STT",
            extra={
                "transcript_cache": "miss",
                "transcript_cache_reason": miss_reason,
                "video_hash": video_hash,
            },
        )
        outcome = await transcribe_with_cache(
            video_path=source_path,
            audio_path=audio_path,
            transcriber=transcriber,
            cache=transcript_cache,
            language=language_hint,
            force_reingest=force_reingest,
        )
        transcript = outcome.result
        cache_hit = outcome.cache_hit

    detected_lang = transcript.language or "und"
    await service.set_detected_language(job_id, detected_lang)
    transcript_path = art.write_json(job_id, "transcript.json", transcript.model_dump())
    await service.add_artifact(
        job_id,
        kind=ArtifactKind.transcript,
        path=str(transcript_path.relative_to(art.job_dir(job_id))),
        meta={
            "transcriber": transcript.transcriber,
            "model": transcript.model,
            "words": len(transcript.words),
            "language": detected_lang,
            "source_language_hint": source_language,
            "cache_hit": cache_hit,
            "video_hash": video_hash,
        },
    )
    await _advance(
        service,
        job_id,
        JobStage.transcribe,
        100,
        f"готово: {len(transcript.words)} слов, язык {detected_lang}"
        + (" (кэш)" if cache_hit else ""),
        extra={
            "transcript_cache": "hit" if cache_hit else "miss",
            "video_hash": video_hash,
            "word_count": len(transcript.words),
            "language": detected_lang,
        },
    )

    # ===== Stage 3: translate (адаптивно, только если detected != ru) =====
    needs_translation = not detected_lang.lower().startswith(TARGET_LANGUAGE)
    if needs_translation:
        await _advance(
            service,
            job_id,
            JobStage.translate,
            0,
            f"перевод {detected_lang} → {TARGET_LANGUAGE}",
        )
        translator_prompt = await get_prompt(PromptKey.translate_adaptive_ru)
        translator = Translator(
            TranslatorConfig(
                llm_provider=ctx.llm_provider,
                llm_model=ctx.llm_model,
                source_language=detected_lang,
                target_language=TARGET_LANGUAGE,
            ),
            system_prompt=translator_prompt,
            settings=cfg,
        )
        transcript = await translator.translate(transcript)
        translated_path = art.write_json(
            job_id, "translated_transcript.json", transcript.model_dump()
        )
        await service.add_artifact(
            job_id,
            kind=ArtifactKind.transcript,
            path=str(translated_path.relative_to(art.job_dir(job_id))),
            meta={
                "translated_from": detected_lang,
                "translated_to": TARGET_LANGUAGE,
                "words": len(transcript.words),
            },
        )
        await _advance(
            service,
            job_id,
            JobStage.translate,
            100,
            f"переведено {len(transcript.words)} слов",
        )
    else:
        await _advance(
            service,
            job_id,
            JobStage.translate,
            100,
            f"исходник уже на {TARGET_LANGUAGE} — перевод не требуется",
        )

    ctx.transcript = transcript
    ctx.transcript_segments = list(transcript.segments)
    ctx.transcript_words = list(transcript.words)
    ctx.detected_language = detected_lang
    ctx.needs_translation = needs_translation
    ctx.transcript_path = transcript_path

    # ===== Stage 4: silence_cut =====
    await _advance(service, job_id, JobStage.silence_cut, 0, "удаление тишины и филлеров")
    silence_cfg = load_silence_config()
    cleaned = clean_transcript(transcript, silence_cfg)
    cleaned_path = art.write_json(job_id, "cleaned_transcript.json", cleaned.model_dump())
    await service.add_artifact(
        job_id,
        kind=ArtifactKind.cleaned_transcript,
        path=str(cleaned_path.relative_to(art.job_dir(job_id))),
        meta=dict(cleaned.stats),
    )
    await _advance(
        service,
        job_id,
        JobStage.silence_cut,
        100,
        f"оставлено {cleaned.stats.get('kept_words', 0)} слов, удалено {len(cleaned.removed_ranges)} фрагментов",
    )

    ctx.cleaned_transcript = cleaned
    # CleanedTranscript хранит только words; segments восстанавливаются
    # downstream через merge_words_into_segments в _transcript_from_cleaned.
    ctx.cleaned_words = list(cleaned.words)
    ctx.cleaned_path = cleaned_path

    return ctx
