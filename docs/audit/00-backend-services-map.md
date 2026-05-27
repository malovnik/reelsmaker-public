# 00 — Карта backend-сервисов

> **Артефакт REFACTR-00.** Зона охвата: `apps/backend/src/videomaker/` (код), `apps/backend/alembic/` (миграции — только список).
> **Дата:** 2026-04-24.
> **Автор:** R-AUDITOR (Serena-based reverse engineering).
> **Назначение:** дать R-BACKEND-SURGEON на Этапе 02 точное знание, какой символ в каком файле и какой строке трогать.

---

## 1. Зона охвата (по цифрам)

| Слой | Единицы | Ссылка |
|------|---------|--------|
| Точка входа | `main.py` (FastAPI + lifespan + CORS + router inclusion) | `apps/backend/src/videomaker/main.py:107` |
| API routers | 8 файлов в `api/routes/` | `files.py`, `health.py`, `jobs.py`, `post_production.py`, `projects.py`, `proxies.py`, `scheduler.py`, `settings.py` |
| Domain models (SQLAlchemy + Pydantic) | 17 файлов в `models/` | `audio_profile.py`, `canvas.py`, `evidence.py`, `job.py`, `job_constants.py`, `job_dto.py`, `job_orm.py`, `job_types.py`, `narrative.py`, `post_production.py`, `project.py`, `reel_plan.py`, `runtime_settings.py`, `scheduler.py`, `story_script.py`, `vision_settings.py` |
| Core слой | `core/` (config, db, logging, artifacts, logger helpers) | 8 файлов |
| Services — top-level | 83 `.py` файла (без `__init__`) в `services/` | см. §3 |
| Services — подпакеты | 10 подпакетов: `agents/`, `broll/`, `llm_clients/`, `llm_providers/`, `narrative/`, `pipeline_stages/`, `publer/`, `transcribers/`, `video_effects/`, `vision/` | см. §4 |
| Строк кода в `services/*.py` (только корень) | **24 932** | `wc -l services/*.py` |
| Крупнейший файл | `reels_composer.py` — **2198 строк** | `services/reels_composer.py` |

---

## 2. Точка входа и lifecycle

**`apps/backend/src/videomaker/main.py`**

- `lifespan` (строка 25) выполняет:
  1. `configure_logging` + `settings.ensure_directories` — строки 31-33.
  2. **Idempotent DDL bootstrap** через `Base.metadata.create_all` — строки 45-51. *Миграции Alembic игнорируются при первом запуске — новые таблицы создаются на лету*. Это делает Alembic вторичным, Этап 02 должен учитывать (см. §9 Риски).
  3. `seed_default_prompts` (`prompt_store.py`) — строка 53.
  4. `seed_builtin_if_needed` (`subtitle_store.py`) — строка 62.
  5. Прогрев кеша шрифтов в фоне — `ensure_cache_warm` из `font_scanner.py` — строка 69.
  6. `reset_stale_running_jobs` (recovery после падения) — строка 75.
  7. Сброс `ScheduleAssignmentRow.status=uploading → queued` — строки 79-89.
  8. `PublerWorker.start()` — строка 92. При shutdown — `stop()` (97), `flush_all` у `JobService` (102).

- `create_app` (строка 107) строит FastAPI с CORS (`allow_origins=[settings.frontend_origin]`), подключает `api_router` из `api/routes/__init__.py`, добавляет `GET /` для health-ping.

**Вывод для Этапа 02:** lifespan зависит от `PublerWorker` (всегда стартует, даже если Publer не используется) и от принудительного импорта `models/job`, `models/post_production`, `models/scheduler` внутри контекст-менеджера (строка 48) — добавление новой таблицы `project.settings_snapshot` потребует такого же импорта.

---

## 3. API routers — карта эндпоинтов

| Файл | Префикс | Назначение | Вызываемые services |
|------|---------|------------|---------------------|
| `api/routes/health.py` | `/health` | health-ping | — |
| `api/routes/files.py` | `/files` | отдача артефактов (mp4, srt, json, jpg) | `asset_store`, файловый доступ |
| `api/routes/jobs.py` | `/jobs` | CRUD job'ов, upload video, запуск pipeline, `GET /jobs/{id}/events` (SSE) | `jobs`, `profile_detector`, `pipeline`, `post_production_store`, `subtitle_store`, `settings_service` |
| `api/routes/projects.py` | `/projects` + `/jobs/{id}/project` | CRUD проектов, привязка job↔project | `projects_store` |
| `api/routes/post_production.py` | `/post-production` | CRUD post-production presets (color, sharpen и пр.) | `post_production_store` |
| `api/routes/proxies.py` | `/proxies` | контроль proxy-кеша, бенчи | `proxy` |
| `api/routes/scheduler.py` | `/scheduler` + `/publer` | Publer campaigns, account_profiles, presets, pool лайкнутых рилсов | `scheduler_campaigns_store`, `account_profiles_store`, `publer/*`, `asset_store` |
| `api/routes/settings.py` | `/settings` | `/settings/performance`, `/settings/subtitles`, `/settings/vision`, `/settings/prompts`, `/settings/profiles` (profile_masks) | `runtime_settings_store`, `subtitle_store`, `subtitle_styles`, `vision_settings_store`, `prompt_store`, `profile_masks`, `asset_store`, `font_scanner` |

**Монтирование:** в `api/routes/__init__.py` все 8 router'ов собираются в `api_router` с префиксом `/api/v1`.

**Для Этапа 02:**
- Новые endpoints автосейва (`PUT /projects/{id}/settings`) и restart-from-step (`POST /projects/{id}/restart`) — добавляются в `projects.py`.
- Endpoint copy-from settings — аналогично в `projects.py`.
- Endpoint approve/reject/regenerate идей — новый файл `api/routes/reel_ideas.py` (или внутри `jobs.py`).

---

## 4. Pipeline — граф стадий

**Точка входа:** `services/pipeline.py::run_pipeline_safe` (строка 240). Зовётся из `api/routes/jobs.py`.

Поверх — `run_pipeline` (96) / `_run_pipeline_impl` (150) / `_advance` (332 — helper для SSE-прогресса).

### 4.1. Three-stage decomposition

| Стадия | Файл | Top-level | Progress range |
|--------|------|-----------|----------------|
| **Ingest** | `services/pipeline_stages/ingest.py:45` | `run_ingest_stage` | 0-60 (probe → proxy → transcribe → translate → silence_cut) |
| **Analysis** (Kartoziya 5.1-5.10) | `services/pipeline_stages/analysis.py:125` | `run_analysis_stage` | 60-80 |
| **Render** | `services/pipeline_stages/render.py:112` | `run_render_stage` | 80-99 |

`_STAGE_RANGES` — `pipeline.py:52`. Enum стадий — `models/job.py::JobStage`.

### 4.2. Ingest — цепочка вызовов (ingest.py)

```
run_ingest_stage
  ├─ media.probe          → MediaInfo
  ├─ proxy.generate_or_get_proxy (опционально по use_proxy)
  ├─ transcribers.factory.build_transcriber → mlx_whisper | deepgram | stable_ts_mlx
  ├─ transcribers.cache.transcribe_with_cache
  ├─ translator.Translator (если detected_language != ru)
  └─ silence_cutter.clean_transcript
```

### 4.3. Analysis — три ветки (analysis.py)

Строки 125-677 — основной switch по `narrative_mode` из `PerformanceSettings`:

| `narrative_mode` | Ветка | Вход | Ключевые сервисы |
|------------------|-------|------|------------------|
| `"bottom_up"` (legacy, default) | **main в `run_analysis_stage`** 125-677 | cleaned segments | `compression.compress_chunks` → `canvas_builder.build_canvas` → `agents.orchestrator.orchestrate_extraction` → `reducer.reduce_and_rank` → `story_doctor.compose_story_script` → `rhythm_check.check_rhythm` → `variants_generator.generate_variants` → `reels_composer.compose_reels` → `coherence_validator.validate_coherence` → `closure_validator.validate_closures` |
| `"chaptered"` | `_run_top_down_branch` 678-832 | cleaned segments | `narrative.orchestrator.orchestrate_top_down` (chapter_builder → hook_detector → arc_finder → boundary_extender → cross_chapter_ranker) |
| `"map_reduce"` | `_run_top_down_branch` 678-832 (общий entry, ветка внутри orchestrator) | cleaned segments | `narrative.map_reduce_orchestrator.orchestrate_map_reduce` |
| `"viral_2026"` | `_run_viral_2026_branch` 833-943 | cleaned segments, один LLM-call per chunk | `services.viral_arc_builder` + `services.prompts.VIRAL_2026_PROMPT` |

**Vision overlay:** `_run_extraction_with_vision` (944), `_enrich_ranked_with_visuals` (1019), `_apply_cover_selector` (1067), `_apply_visual_validator` (1123).

### 4.4. Render — (render.py)

```
run_render_stage
  ├─ _resolve_render_presets      # post_production_store, subtitle_store
  ├─ _prepare_face_tracking       # face_tracker (если face_tracker_enabled)
  ├─ _build_initial_graphs        # project_graph + zoom_planner + filter_graph_builder
  ├─ _apply_pause_compression     # pause_compression, vad, breath_classifier
  ├─ _apply_graph_transforms      # profile_masks, emphasis_motion, punchline_detector
  ├─ _apply_zoom_layer            # zoom_planner, spring_zoom_planner, cursor_detector, deictic_zoom
  ├─ _finalize_graphs             # subtitles, subtitle_styles
  └─ _render_and_persist_reels    # project_renderer → FFmpeg hevc_videotoolbox
```

---

## 5. Inventory таблица (all top-level services)

**Условные обозначения:**
- 🟢 **Живой** — импортируется из `api/routes/*`, `pipeline*`, `pipeline_stages/*` или цепочкой из них.
- 🟡 **Локальный узел графа** — используется только другим сервисом, косвенно входит в pipeline.
- 🔴 **Мёртвый** — нет ни одного входящего импорта в коде (ни в routes, ни в pipeline, ни в других services).
- 🟠 **Legacy под удаление** — в коде живой, но по task.md (v2.0-refactor) подлежит удалению (PRO → только Viral 2026 + Chapter Legacy).

### 5.1. Сервисы «ядра pipeline» (живые)

| Сервис (файл) | LoC | Назначение | Ключевой символ |
|---------------|-----|-----------|-----------------|
| `pipeline.py` | 363 | Orchestrator всей нарезки | `run_pipeline_safe:240`, `_advance:332` |
| `pipeline_context.py` | — | DTO-контейнер состояния между stages | `PipelineContext` |
| `pipeline_mode.py` | 110 | Detect dialogue vs travel по WPM+silence | `detect_pipeline_mode:44` |
| `jobs.py` | 926 | `JobService` — CRUD job'ов, stage updates, SSE bus | `JobService`, `get_job_service` |
| `job_event_bus.py` | — | pub/sub для SSE | `JobEventBus` |
| `media.py` | — | ffprobe, extract_audio, ExportPreset, ReelSegmentRender | `probe`, `extract_audio`, `FfmpegError` |
| `prompts.py` | 594 | Manifest 2026 + `PromptKey` enum + `VIRAL_2026_PROMPT` | `PromptKey:40`, `VIRAL_2026_PROMPT:561`, `build_system_prompt` |
| `prompt_store.py` | — | БД-хранилище промптов с версионностью | `seed_default_prompts`, `get_prompt` |
| `llm_client.py` | — | Фасад — `build_llm_for_tier`, `LLMTier`, `LLMError` | `build_llm_for_tier`, `LLMClient` |
| `rate_limiter.py` | — | Rate limit для Gemini | `RateLimiter`, `get_gemini_rate_limiter` |

### 5.2. Analysis pipeline (Kartoziya bottom_up — legacy, но активный по умолчанию)

| Сервис | LoC | Роль в analysis | Вход/Выход |
|--------|-----|-----------------|------------|
| `compression.py` | — | Flash Lite per-chunk — 5.1 | `compress_chunks` → `CompressionResult` |
| `chunker.py` | 257 | Fixed-window разбиение транскрипта | `chunk_transcript`, `TranscriptChunk` |
| `semantic_chunker.py` | 258 | Эмбеддинг-границы (TIER2-#11) | `semantic_chunk` (опционально) |
| `canvas_builder.py` | 603 | 5.2 — Pro один вызов → Canvas | `build_canvas` |
| `canvas_embedder.py` | 243 | Эмбеддинги Canvas moments для preference | `embed_canvas_moments`, `cosine_similarity` |
| `agents/orchestrator.py` | — | 5.3 — 6 агентов × N chunks | `orchestrate_extraction`, `ExtractionResult` |
| `agents/base.py` | — | Базовый класс агентов | `AgentResult` |
| `reducer.py` | 673 | 5.4 — Flash + Jaccard dedup | `reduce_and_rank`, `ReduceResult` |
| `cross_chunk_reducer.py` | 256 | TIER2-#16 cross-chunk coherence | `apply_cross_chunk_coherence` |
| `cross_context_risk.py` | 243 | Risk scoring между chunk'ами | вспомогательный для reducer |
| `preference_memory.py` | 353 | T6.1 cosine retrieval по лайкам | `load_liked_anchors_text` |
| `trend_lexicons.py` | — | T2.4.1 trend score | `compute_trend_score` |
| `story_doctor.py` | 443 | 5.5 — Pro + 3-act arc | `compose_story_script` |
| `rhythm_check.py` | — | 5.6 — критика ритма | `check_rhythm`, `RhythmReport` |
| `variants_generator.py` | — | 5.7 — 4 варианта рилсов | `generate_variants` |
| `reels_composer.py` | **2198** | 5.8 — финальная сборка рилсов, dedup по Jaccard, target count | `compose_reels` |
| `coherence_validator.py` | 447 | 5.9 — арка не распадается | `validate_coherence` |
| `closure_validator.py` | 486 | 5.10 — рилс закрывает петлю | `validate_closures` |
| `extraction_coverage.py` | — | Метрика покрытия | `build_coverage_summary` |
| `composition_scorer.py` | — | Ранжирование | `composition_scorer.*` |

### 5.3. Analysis pipeline — альтернативные ветки

| Сервис | Роль |
|--------|------|
| `narrative/orchestrator.py` | `"chaptered"` (top-down Phase 1-6) — `orchestrate_top_down` |
| `narrative/chapter_builder.py` | Embedding-based главы |
| `narrative/hook_detector.py` | Hook points |
| `narrative/arc_finder.py` | 3-act arc per chapter |
| `narrative/boundary_extender.py` | Расширение границ по payoff |
| `narrative/cross_chapter_ranker.py` | Ранкинг между главами |
| `narrative/map_reduce_orchestrator.py` | `"map_reduce"` (Phase 8) — chunks 20K chars |
| `narrative/chunk_scorer.py` | Scorer для map_reduce |
| `narrative/clip_reducer.py` | Reducer для map_reduce |
| `narrative/global_context_builder.py` | Строит GlobalContext |
| `narrative/constants.py` | Константы narrative |
| `viral_arc_builder.py` | 474 LoC. `"viral_2026"` ветка — `_run_viral_2026_branch` зовёт этот модуль |
| `multi_arc_builder.py` | Multi-arc Variant A |

### 5.4. Ingest / Proxy / Transcription

| Сервис | LoC | Роль |
|--------|-----|------|
| `proxy.py` | 419 | Генерация/кеш proxy через ffmpeg, skip-heuristic |
| `silence_cutter.py` | 256 | VAD + удаление тишины/филлеров, `CleanedTranscript` |
| `filler_removal.py` | — | TIER2-#13 удаление «ну/эм/uh» |
| `pause_compression.py` | — | TIER2-#14 сжатие пауз |
| `vad.py` | — | Silero VAD обёртка |
| `breath_classifier.py` | — | T8.2 distinguish breath vs silence (опционально, активный через флаг) |
| `cut_snapper.py` | — | Word-boundary snap FEAT-#E |
| `beat_detector.py` | 300 | T2.5 librosa beat detection |
| `audio_analyzer.py` | 653 | Parselmouth pitch, intensity |
| `audio_normalizer.py` | — | loudnorm EBU R128 |
| `transcribers/factory.py` | — | `build_transcriber` + `transcribe_with_cache` |
| `transcribers/base.py` | — | `TranscribedWord`, `TranscribedSegment`, `TranscriptResult` |
| `transcribers/cache.py` | — | `TranscriptCache`, `compute_wpm` |
| `transcribers/mlx_whisper_backend.py` | — | Apple Silicon MLX |
| `transcribers/stable_ts_mlx_backend.py` | — | stable-ts MLX |
| `transcribers/deepgram_backend.py` | — | Deepgram cloud fallback |
| `translator.py` | 243 | EN→RU Gemini |

### 5.5. Render / Video

| Сервис | LoC | Роль |
|--------|-----|------|
| `project_graph.py` | 678 | Граф cut→crop→transform→subtitle per reel, `CutSpec`, `ProjectGraph` |
| `project_renderer.py` | 391 | FFmpeg runner с filter_complex, `FILTER_COMPLEX_INLINE_LIMIT` |
| `renderer.py` | — | Legacy renderer (будет удалён в Cycle 5 — комментарий в `pipeline.py`) |
| `filter_graph_builder.py` | 586 | FFmpeg filter graph generation |
| `zoom_planner.py` | 881 | Base crop + zoom keyframes |
| `spring_zoom_planner.py` | — | T2.8 spring-damped zoom для screencast |
| `cursor_detector.py` | — | T2.8 детекция курсора для screencast zoom |
| `deictic_zoom.py` | — | Zoom на deictic words (вот/смотри/здесь) |
| `face_tracker.py` | 495 | MediaPipe face detection, `FaceBBox`, `FaceTrackResult` |
| `object_tracker.py` | 285 | `ObjectTrack` |
| `profile_detector.py` | 252 | Detect profile: talking_head / fashion / screencast / travel |
| `profile_masks.py` | 416 | `ProfileMask` — разные render-правила по profile |
| `pacing_profile.py` | — | `PacingProfileTemplate` |
| `emphasis_motion.py` | 398 | Emphasis на ключевых слов в subtitle |
| `punchline_detector.py` | — | T10.1 punchline pause detection |
| `mouth_sound_detector.py` | — | T8.1 lip smacks / clicks detector |
| `split_screen.py` | 377 | Split screen для двух-person видео |
| `jl_cut_planner.py` | 277 | TIER2-#15 J/L cut smoothing |
| `subtitles.py` | 344 | ASS subtitle generation |
| `subtitle_styles.py` | 440 | Style presets, SYSTEM_FONTS |
| `subtitle_store.py` | — | БД-пресеты стилей субтитров |
| `font_scanner.py` | — | macOS system_profiler fonts кеш |
| `asset_store.py` | 288 | Файлово-ориентированный storage артефактов |
| `video_effects/registry.py` | — | Реестр эффектов |
| `video_effects/base.py` | — | `VideoEffect`, `VideoEffectContext` |
| `video_effects/bw.py` | — | B&W эффект |
| `broll/index.py` | — | Визуальный evidence index |
| `broll/retriever.py` | — | Поиск B-roll по транскрипту |
| `broll/inserter.py` | — | `suggest_broll_inserts` |
| `visual_evidence_agent.py` | 268 | Gemini vision анализ frames |
| `visual_validator.py` | — | `validate_arc` — vision validation |
| `cover_selector.py` | — | Выбор обложки из frames |

### 5.6. Vision подсистема

| Сервис | Роль |
|--------|------|
| `vision/factory.py` | Factory для vision-клиента |
| `vision/base.py` | `VisionClient` base |
| `vision/model_manager.py` | `VisionModelManager` |
| `vision/moondream_local.py` | Локальный Moondream через Ollama |
| `vision/frame_cache.py` | Кеш frames |
| `vision/rate_limiter.py` | RateLimit для vision API |
| `vision/registry.py` | `get_vision_provider` |
| `vision/types.py` | `VisionProfile`, `VisionRuntimeSettings` |
| `vision_settings_store.py` | БД-хранилище vision settings |

### 5.7. LLM слой

| Сервис | Роль |
|--------|------|
| `llm_client.py` | Фасад, `LLMTier`, `build_llm_for_tier` |
| `llm_clients/base.py` | `LLMClient`, `LLMError` protocol |
| `llm_clients/claude.py` | `ClaudeClient` |
| `llm_clients/gemini.py` | `GeminiClient` |
| `llm_clients/openai.py` | `OpenAIClient` |
| `llm_clients/zhipu.py` | `GLMClient` |
| `llm_clients/json_parser.py` | `parse_json_response` — устойчивый парсер |
| `llm_clients/retry.py` | `_retry`, `_is_retryable` |
| `llm_clients/tier_resolver.py` | Маппинг tier → модель |
| `llm_providers/registry.py` | Provider registry |
| `llm_providers/gemini_factory.py` | `GeminiProviderFactory` |
| `llm_providers/claude_factory.py` | `ClaudeProviderFactory` |
| `llm_providers/openai_factory.py` | `OpenAIProviderFactory` |
| `llm_providers/zhipu_factory.py` | `ZhipuProviderFactory` |
| `auto_config_advisor.py` | 615 | T11 pipeline_mode=automatic — решает параметры |
| `auto_config_llm_fallback.py` | 256 | Fallback если LLM недоступен |

### 5.8. Publer (социальная публикация)

| Сервис | Роль |
|--------|------|
| `publer/client.py` | `PublerClient`, `PublerClientError` |
| `publer/worker.py` | Background `PublerWorker` (стартует в lifespan) |
| `publer/media_uploader.py` | `upload_reel_to_publer` (re-encode >180MB) |
| `publer/post_builder.py` | `build_schedule_request` |
| `publer/caption_generator.py` | `generate_caption` (Gemini) |
| `publer/preset_applier.py` | `apply_presets` |
| `publer/scheduler_service.py` | `build_campaign_from_pool` |
| `publer/schemas.py` | `PublerAccount`, `PublerMediaRef`, DTO |
| `account_profiles_store.py` | БД presets per Publer account (импортируется multiline в `scheduler.py:36` и `publer/scheduler_service.py:25`) |
| `scheduler_campaigns_store.py` | БД campaigns |

### 5.9. Stores и settings

| Сервис | Назначение |
|--------|-----------|
| `projects_store.py` | CRUD Project (имя, цвет, описание — см. `models/project.py`) |
| `post_production_store.py` | 399 LoC — post-production presets |
| `runtime_settings_store.py` | `PerformanceSettings` CRUD, `get_performance_settings` |
| `performance_settings_store.py` | Deprecated-alias для runtime_settings_store (см. §7) |
| `settings_service.py` | Фасад `/api/v1/settings/*` |
| `subtitle_store.py` | Subtitle presets CRUD + seed |
| `vision_settings_store.py` | Vision settings |

---

## 6. Мёртвые модули (🔴 0 входящих импортов)

Grep'нут `\bNAME\b` + `videomaker.services.NAME` по всему `apps/backend/`, исключены self-references и `__pycache__`.

| Сервис | LoC | Статус | Комментарий |
|--------|-----|--------|-------------|
| `services/adaptive_leveller.py` | **95** | 🔴 мёртвый | T8.5 adaptive leveller. Флаг `adaptive_leveller_enabled` в `runtime_settings.py:471` есть, сам detector — нигде. **Feature stub — реализовать или удалить.** |
| `services/eye_trace_continuity.py` | **147** | 🔴 мёртвый | T10.8 MediaPipe Face Mesh iris landmarks. Никто не зовёт, флага даже нет. Stub-эксперимент. |
| `services/match_cuts.py` | **131** | 🔴 мёртвый | T2.6 perceptual hashing. Research-prototype, в composer не используется. |
| `services/person_cluster.py` | **196** | 🔴 мёртвый | Person clustering для fashion/travel. Не вызван. |
| `services/transition_chooser.py` | **204** | 🔴 мёртвый | T10.6 Smart Transition Chooser. Research-doc `editing-craft-2026.md`, сам модуль в pipeline не включён. |
| **Итого мёртвого** | **773** | — | ~3% от объёма `services/*.py`. |

**Рекомендация Этапу 02:** удалить эти 5 файлов + упоминания в флагах `runtime_settings.py` (если применимо). Коммит-риск — минимальный, т.к. 0 референсов.

---

## 7. Дубликаты и рефакторинг-кандидаты

### 7.1. `renderer.py` vs `project_renderer.py`

- `services/renderer.py` — legacy, комментарий в `pipeline.py:63-66`: «Зеркалит публичный контракт `renderer.RenderedReel` (которая удалится в Cycle 5)». Сейчас `pipeline.py` импортирует **обе**. Активный в рендере — `project_renderer.py`.
- **Рекомендация:** удалить `renderer.py` в Этапе 03 (REFACTR-21 или REFACTR-26).

### 7.2. `performance_settings_store.py` vs `runtime_settings_store.py`

- Оба хранят `PerformanceSettings`. `runtime_settings_store.get_performance_settings` — основной (7 импортёров). `performance_settings_store` — legacy alias.
- **Рекомендация:** убрать `performance_settings_store.py`, перебить импорты на `runtime_settings_store` (REFACTR-14).

### 7.3. `reducer.py` vs `narrative/clip_reducer.py`

- `reducer.reduce_and_rank` используется в bottom_up ветке (`analysis.py`).
- `narrative/clip_reducer.reduce_and_rank` — в map_reduce ветке.
- **Не дубликат, а две реализации под разные narrative_mode.**

### 7.4. `agents/orchestrator.py` vs `narrative/orchestrator.py` vs `narrative/map_reduce_orchestrator.py`

- `agents/orchestrator` — Kartoziya 6-agent bottom_up.
- `narrative/orchestrator` — top_down chaptered.
- `narrative/map_reduce_orchestrator` — map_reduce Phase 8.
- **Три независимых оркестратора под три narrative_mode.**

---

## 8. Narrative modes vs задача v2.0 (PRO vs Viral 2026)

Владелец требует оставить **только Viral 2026 (default) + Chapter Legacy**. В коде сейчас — четыре narrative_mode:

Объявление: `models/runtime_settings.py:55`

```python
NarrativeMode = Literal["bottom_up", "chaptered", "map_reduce", "viral_2026"]
```

| `narrative_mode` | В коде | Решение по task.md | Где используется |
|------------------|--------|---------------------|-------------------|
| `"bottom_up"` | **default** (`runtime_settings.py:269-284`) | **УДАЛИТЬ** | `pipeline_stages/analysis.py:125-677`, `agents/orchestrator.py`, `reducer.py`, `story_doctor.py`, `reels_composer.py`, `variants_generator.py`, `coherence_validator.py`, `closure_validator.py`, `cross_chunk_reducer.py` |
| `"chaptered"` | ветка в `_run_top_down_branch` | **ОСТАВИТЬ как «Chapter Legacy»** | `narrative/orchestrator.py`, `narrative/chapter_builder.py`, `narrative/hook_detector.py`, `narrative/arc_finder.py`, `narrative/boundary_extender.py`, `narrative/cross_chapter_ranker.py` |
| `"map_reduce"` | ветка в `_run_top_down_branch` | **УДАЛИТЬ** | `narrative/map_reduce_orchestrator.py`, `narrative/chunk_scorer.py`, `narrative/clip_reducer.py`, `narrative/global_context_builder.py`, `narrative/constants.py` |
| `"viral_2026"` | `_run_viral_2026_branch` 833-943 | **НОВЫЙ DEFAULT** | `viral_arc_builder.py` (474 LoC), `prompts.VIRAL_2026_PROMPT:561`, `multi_arc_builder.py` |

**Сколько кода под удаление в bottom_up + map_reduce (грубая оценка по LoC):**
- `agents/orchestrator.py` + `agents/base.py`
- `reducer.py` (673), `cross_chunk_reducer.py` (256), `cross_context_risk.py` (243)
- `story_doctor.py` (443)
- `variants_generator.py`
- `reels_composer.py` (**2198** — крупнейший файл!) — если полностью bottom_up. **Нужно проверить**, используется ли он в Viral 2026 тоже.
- `coherence_validator.py` (447), `closure_validator.py` (486) — возможно, часть переиспользуется.
- `extraction_coverage.py`, `composition_scorer.py`, `preference_memory.py` (353), `trend_lexicons.py`
- `canvas_builder.py` (603), `canvas_embedder.py` (243), `chunker.py` (257), `compression.py`
- `narrative/map_reduce_orchestrator.py`, `chunk_scorer.py`, `clip_reducer.py`, `global_context_builder.py`

**Порядок действий (гипотеза для Этапа 02):**

1. **Сначала проверить**, что Viral 2026 ветка (`_run_viral_2026_branch`) может работать без `canvas_builder`, `chunker`, `compression` — или всё-таки нужна pre-chunking стадия. Это проверяется чтением строк `833-943` в `analysis.py`.
2. Переключить `narrative_mode` default → `"viral_2026"` (REFACTR-13).
3. Пометить `bottom_up` и `map_reduce` как deprecated, запустить feature-flag kill-switch.
4. Удалять сервисы постепенно, граф импортов — основной guide.

### 8.1. «Профили видео» — отдельный концепт

**`profile_detector`** и **`profile_masks`** — это detection для **video profile** (talking_head / fashion / screencast / travel), а **не** для narrative PRO-профиля. Не трогать.

**`account_profiles_store`** — это **профили аккаунта Publer** (presets публикации), не контент-профиль. Не трогать.

**Путаница в именовании — потенциальный риск** (см. §9.3).

---

## 9. Риски при рефакторинге (для R-BACKEND-SURGEON)

### 9.1. Idempotent DDL bootstrap обходит Alembic

`main.py:45-51` вызывает `Base.metadata.create_all` при каждом старте. Новая таблица (Project с `settings_snapshot`, `stage_progress`, `soft_deleted_at`, `parent_project_id`) должна быть добавлена **И в Alembic migration, И в импорт на строке 48** (`from videomaker.models import job, post_production, scheduler`). Иначе свежая БД получит колонки через `create_all`, а на старой БД без миграции они не появятся.

### 9.2. PublerWorker — обязательный при startup

`main.py:92` всегда стартует `PublerWorker`. Это означает — при любом рефакторинге lifecycle (REFACTR-17 copy-from, REFACTR-18 delete) нельзя сломать импорт `publer.worker.PublerWorker`.

### 9.3. Три разных «profile»

Имена вводят в заблуждение:
- **profile_detector / profile_masks** — video profile (talking_head / fashion / screencast / travel).
- **account_profiles_store** — Publer account presets.
- **narrative_mode** (PRO, Viral 2026, Chapter Legacy) — mode анализа.

Рефакторинг удаления PRO **затрагивает только `narrative_mode`**. profile_detector/profile_masks/account_profiles_store — не трогать.

### 9.4. `reels_composer.py` — 2198 строк

Любое удаление bottom_up ветки требует либо:
- (a) полностью удалить `reels_composer.py` и переключить Viral 2026 на свой composer (если у него есть);
- (b) сохранить composer и только отключить upstream'ы (более безопасный вариант).

До начала Этапа 02 нужно прочитать `_run_viral_2026_branch:833-943` в `analysis.py`, чтобы понять — compose_reels() в Viral 2026 используется или нет.

### 9.5. Lifecycle кеширования

`font_scanner.ensure_cache_warm` (6 сек в фоне), `TranscriptCache` — persistent state на диске. Удаление `data/` запрещено (task.md §6.5). Миграции не должны чистить кеши.

### 9.6. SSE jobs events

`api/routes/jobs.py::GET /jobs/{id}/events` — SSE стрим, использует `job_event_bus.JobEventBus`. Новые события approve/reject/regenerate (REFACTR-20) должны публиковаться в ту же шину. Не городить второй bus.

### 9.7. `pipeline.py` — циклические импорты

`pipeline_stages/ingest.py:55` и `pipeline_stages/analysis.py:123` используют локальный импорт `from videomaker.services.pipeline import _advance` **внутри функции** — специально для обхода циклической зависимости. Добавление нового helper в pipeline.py должно следовать этой конвенции.

---

## 10. Зацепки для последующих REFACTR-чанков

### 10.1. REFACTR-01 (карта frontend) — что отдать

- 8 routes × их endpoints (уточнить в `api/routes/__init__.py` префикс `/api/v1`).
- SSE endpoint `/api/v1/jobs/{id}/events` — для live-статуса pipeline и идей.

### 10.2. REFACTR-02 (инвентаризация настроек)

- `runtime_settings.py` — **500+ строк с ~50 полями**. Каждое поле = один UI-control. Главный источник h-scroll боли на `/settings/subtitles` и `/settings/performance`.
- `subtitle_styles.py` (440), `subtitle_store.py` — source для subtitle editor.
- `vision_settings_store.py`, `prompt_store.py`, `profile_masks.py` — остальные настройки.

### 10.3. REFACTR-03 (PRO-код)

- `NarrativeMode` литерал — `models/runtime_settings.py:55`.
- `_run_top_down_branch:678`, `_run_viral_2026_branch:833` — branches для ветвления.
- Map-reduce оркестратор — `narrative/map_reduce_orchestrator.py`.
- `reels_composer.py` (2198 LoC) — **требует индивидуального решения** (keep or delete).

### 10.4. REFACTR-04 (схема данных)

- 17 файлов в `models/`. Главные ORM:
  - `models/job.py` — `Job`, `JobStage`, `SubtitleStyleConfig`, `VisionProfile`.
  - `models/project.py` — `Project` (минималистичный сейчас: name, description, color).
  - `models/scheduler.py` — `ScheduleAssignmentRow`, `AssignmentStatus`.
  - `models/post_production.py` — `PostProductionConfig`.
  - `models/runtime_settings.py` — `PerformanceSettings` (Pydantic, **не SQLAlchemy**).
- Alembic — в `apps/backend/alembic/` (не анализировался в этом чанке, отдельная задача REFACTR-04).

### 10.5. REFACTR-05 (pipeline stages)

- Три stage-функции: `run_ingest_stage`, `run_analysis_stage`, `run_render_stage`. Связываются через `PipelineContext`.
- Точки возобновления (restart-from-step): на границах stage. Нужно сохранять `ctx` в `settings_snapshot` / `stage_progress` (REFACTR-14).

### 10.6. REFACTR-19 (сервис идей рилсов)

- `models/reel_plan.py::AnalysisResult`, `ReelPlan` — уже есть DTO для списка рилсов. Для approve/reject потребуется **новая ORM таблица** `reel_idea` с полями `status` (pending/approved/rejected), `custom_prompt`, `regenerated_at`, `project_id`.

### 10.7. REFACTR-24/25 (security)

- `publer/media_uploader.py` — subprocess на ffmpeg. Проверить argv-only.
- `font_scanner.py` — `system_profiler` subprocess на macOS. Проверить.
- `proxy.py`, `project_renderer.py` — FFmpeg runners, argv-only обязательно.

---

## 11. Ключевые находки (TL;DR)

1. **97 сервисных файлов в `services/`**, из них **5 мёртвых (0 входящих импортов, 773 LoC)** — `adaptive_leveller`, `eye_trace_continuity`, `match_cuts`, `person_cluster`, `transition_chooser` — можно удалять без риска.
2. **`reels_composer.py` — 2198 строк**, крупнейший файл, центр bottom_up ветки. Нужно индивидуальное решение до начала ампутации PRO.
3. **Narrative modes — 4 варианта**, а не «PRO vs Viral 2026». task.md требует оставить `viral_2026` (default) + `chaptered` («Chapter Legacy»), удалить `bottom_up` + `map_reduce`. Точка переключения — `analysis.py:125-943` + `runtime_settings.py:55`.
4. **Имя `profile` перегружено** (video profile / Publer account profile / narrative mode). Переименовывать не требуется, но путаница — источник ошибок.
5. **Alembic обходится через `Base.metadata.create_all` в lifespan** (`main.py:45-51`). Новая таблица Project должна быть в обоих местах.
6. **Нет ни одной ссылки на `settings_snapshot`, `stage_progress`, `restart_from`, `autosave`** — автосохранение и restart-from-step **полностью отсутствуют**, будут реализованы с нуля (REFACTR-14, REFACTR-15, REFACTR-16).
7. **PRO-профиль как самостоятельный концепт не существует** — он выражен через `narrative_mode="bottom_up"`. Термин в task.md ссылается на эту ветку.
8. **`renderer.py` и `performance_settings_store.py` — legacy-aliases**, на их удаление есть комментарии в коде (Cycle 5 / deprecated). Удалить в Этапе 02/03.
9. **3 оркестратора analysis**: `agents/orchestrator` (bottom_up), `narrative/orchestrator` (chaptered), `narrative/map_reduce_orchestrator` (map_reduce). `viral_arc_builder` — четвёртый, встроен прямо в `_run_viral_2026_branch`.
10. **PublerWorker — mandatory startup dependency**. Любой рефакторинг lifespan/DI не должен сломать его импорт.

---

## 12. Рекомендации для Этапа 02 (порядок действий)

1. **REFACTR-13 (удаление PRO)** — начать с удаления мёртвых 5 модулей (§6) для прогрева и проверки Serena-safe_delete. Затем — `narrative_mode` migration: переключить default на `viral_2026`, Alembic-миграция для существующих проектов (PRO/bottom_up/map_reduce → viral_2026).
2. **REFACTR-14 (модель Project)** — новые поля `settings_snapshot_path` (str), `stage_progress` (JSON), `soft_deleted_at` (datetime|None), `parent_project_id` (int|None). И Alembic migration, и импорт в `main.py:48`.
3. **REFACTR-15 (PUT snapshot)** — новый endpoint в `projects.py`, ETag-conflict через Pydantic.
4. **REFACTR-16 (restart-from-step)** — POST endpoint + инвалидация downstream artifacts через `ArtifactsManager`.
5. **REFACTR-17 (copy-from)** — реиспользование Pydantic snapshot.
6. **REFACTR-18 (Finder-open + delete)** — subprocess `open -R` через argv-массив, guard на path traversal.
7. **REFACTR-19 (ReelIdea)** — новая ORM таблица, Gemini-генерация (переиспользовать `viral_arc_builder`).
8. **REFACTR-20 (approve/reject/regenerate)** — 4 endpoints + SSE events через существующий `JobEventBus`.

**Что не трогать на Этапе 02:**
- `profile_detector.py`, `profile_masks.py`, `account_profiles_store.py` — не про PRO.
- Vision подсистема (`vision/*`) — самостоятельная.
- Publer (`publer/*`, `scheduler_campaigns_store.py`) — отдельный домен.
- Ingest pipeline (`proxy.py`, `transcribers/*`, `translator.py`, `silence_cutter.py`, `vad.py`) — нейтральный слой.
- Render pipeline (`project_graph.py`, `project_renderer.py`, `filter_graph_builder.py`) — нейтральный слой, оптимизация в Этапе 03.

---

**Артефакт записан**: `docs/audit/00-backend-services-map.md`
**Serena memory**: `refactr-00-backend-services-map` (ссылка на этот файл).
**Следующий чанк**: REFACTR-01 — Карта frontend-страниц (`apps/frontend/`).
