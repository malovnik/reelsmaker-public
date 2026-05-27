# End-to-End Default Run Trace

**Скоуп:** один реальный прогон джобы с дефолтными настройками формы `POST /jobs` + дефолтами `PerformanceSettings`/`VisionRuntimeSettings`/`PostProductionConfig`. Источник — 5 отчётов Phase 1 (A–E) + точечная верификация дефолтов в коде.

**Дефолтный профиль прогона (что приходит на вход):**
- Форма `POST /jobs`: `transcriber=stable_ts_mlx`, `llm_provider=gemini`, `llm_model=gemini-3.1-flash-lite-preview`, `target_aspect=9:16`, `fit_mode=fill`, `source_language=auto`, `use_proxy=True`, `use_source_for_render=False`, `vision_profile=talking_head`, **`post_production_preset_id` НЕ передаётся (опциональное поле)**, `subtitle_style_preset_id` НЕ передаётся (берётся builtin default из БД), `split_screen_enabled` НЕ передаётся.
- `PerformanceSettings`: `narrative_mode="bottom_up"`, `coherence_mode="resort"` (вкл), `reducer_ensemble_size=1` (ensemble выкл), `cut_snap_enabled=True`, `variants_generator_enabled=True`, `screencast_cursor_zoom_enabled=True` (но потребитель DORMANT), `context_aware_keep_sec_enabled=True`, `reel_count_enforce_floor_ceiling=True`. **Всё остальное — OFF:** `face_tracker_enabled=False`, `multi_arc_enabled=False`, `cross_chunk_reducer_enabled=False`, `pause_compression_enabled=False`, `breath_compression_enabled=False`, `filler_removal_enabled=False`, `jl_cut_enabled=False`, `rhythm_aware_cuts_enabled=False`, `punch_in_zoom_enabled=False`, `ken_burns_drift_enabled=False`, `adaptive_leveller_enabled=False`, `mouth_sound_removal_enabled=False`, `deictic_zoom_enabled=False`, `breath_classifier_enabled=False`, `smart_jl_chooser_enabled=False`, `punchline_pause_enabled=False`.
- `VisionRuntimeSettings.enabled=False` (главный kill-switch, `vision_settings.py:35`) → весь Moondream-слой тёмный.
- `PostProductionConfig`: т.к. preset_id отсутствует, `_resolve_post_production_config` возвращает **`None`** (`jobs.py:374`) → пост-продакшн как объект выключен. **НО** `build_project_graph` при `post_production_config is None` ставит defensive `AudioNormalizeSpec()` с `enabled=True` (BUG-#F, `project_graph.py:523-530`) → loudnorm всё равно работает.

---

## Полная трасса (стадия → исполняется/выключено/недостижимо → артефакт)

| # | Стадия (JobStage) | Что РЕАЛЬНО на дефолте | Артефакт |
|---|---|---|---|
| 0 | **Upload / create_job** (`jobs.py:82`) | ИСПОЛНЯЕТСЯ. Multipart upload → лимит размера → INSERT job(status=pending) → `ArtifactsManager.ensure_layout` → pipeline стартует как fire-and-forget `asyncio.create_task` (НЕ persistent queue) | `data/uploads/<file>`, строка `jobs`, `source` artifact |
| 1 | **ingest: probe** | ИСПОЛНЯЕТСЯ (ffprobe размеры/длительность) | media_info (in-memory) |
| 2 | **ingest: proxy_generate** | ИСПОЛНЯЕТСЯ при `use_proxy=True`, НО может **скипнуться** по `should_skip_proxy` (низкое разрешение/короткое/низкий битрейт) — нормальное поведение, не сбой | `data/proxies/<sha256>_<profile>.mp4` (1080p H.264, LRU-cache) |
| 3 | **transcribe** | ИСПОЛНЯЕТСЯ. stable-ts MLX (vad+regroup), word-level timestamps, SHA256 disk-cache. **Диаризации НЕТ** (pyannote отсутствует) | `transcript.json` artifact |
| 4 | **translate** | **УСЛОВНО.** Запускается ТОЛЬКО если `detected_lang != ru` (`ingest.py:265`, цель захардкожена `TARGET_LANGUAGE`). Для русского источника — скип с сообщением «перевод не требуется». На РУ-видео декоративно проходит мгновенно | `translated_transcript.json` (только если перевод был) |
| 5 | **silence_cut** | ИСПОЛНЯЕТСЯ всегда. `clean_transcript` помечает паузы (gap≥0.6s) + филлеры (`fillers_ru.yaml`). Это маркировка для render, аудио ещё не режется | `CleanedTranscript` (in-memory → context) |
| 6 | **analyze** (9 под-стадий, `bottom_up`) | См. разбивку ниже | `reel_plan.json`, `analysis_summary` |
| 6.1 | chunking + compression | ИСПОЛНЯЕТСЯ (Flash-Lite параллельно) | — |
| 6.2 | canvas_builder + canvas_embedding | ИСПОЛНЯЕТСЯ («Pro» tier, но физически Flash-Lite) | — |
| 6.3 | preference_memory (лайки прошлых job) | ИСПОЛНЯЕТСЯ (на первом прогоне лайков нет → пусто; не LLM) | — |
| 6.4 | extraction: 6 агентов × N chunks (2 волны) | ИСПОЛНЯЕТСЯ — **главная точка нагрузки**, Flash-Lite, context-cache | — |
| 6.5 | 7-й агент visual_evidence | **ВЫКЛЮЧЕН** (vision disabled) | — |
| 6.6 | reduce_and_rank | ИСПОЛНЯЕТСЯ. Ensemble судей **ВЫКЛ** (`ensemble_size=1`) → один проход | — |
| 6.7 | cross_chunk_reducer | **ВЫКЛЮЧЕН** (`cross_chunk_reducer_enabled=False`) | — |
| 6.8 | story_doctor (3-act + rhythm loop) | ИСПОЛНЯЕТСЯ («Pro» = Flash-Lite) | — |
| 6.9 | rhythm_check | ИСПОЛНЯЕТСЯ (Flash + эвристика) | — |
| 6.10 | visual_validator | **ВЫКЛЮЧЕН** (vision disabled, `analysis.py:1165` gated) | — |
| 6.11 | variants_generator | ИСПОЛНЯЕТСЯ (`variants_generator_enabled=True`) | — |
| 6.12 | multi_arc_builder | **ВЫКЛЮЧЕН** (`multi_arc_enabled=False`) → legacy single-arc | — |
| 6.13 | compose_reels (+ floor/ceiling enforce) | ИСПОЛНЯЕТСЯ | — |
| 6.14 | coherence_validator | ИСПОЛНЯЕТСЯ (`coherence_mode="resort"` ≠ off, `analysis.py:552`) | — |
| 6.15 | closure_validator | ИСПОЛНЯЕТСЯ **БЕЗУСЛОВНО** (нет toggle, `analysis.py:575`) | — |
| 6.16 | cover_selector + per-reel scoring | cover_selector **ВЫКЛ** (vision); per-reel scoring (rhythm/narrative/trend) ИСПОЛНЯЕТСЯ (без LLM) | — |
| 7 | **render** (per reel, 1 ffmpeg/граф) | ИСПОЛНЯЕТСЯ. См. разбивку слоёв ниже | `reels/<reel_id>.mp4` + `subs/<reel_id>.ass` + `project_graphs.json` artifacts |
| 7a | base_crop (fit_mode=fill) | ИСПОЛНЯЕТСЯ, но БЕЗ face-keyframes → **статичный center-crop** (face_tracker OFF) | — |
| 7b | cut transforms (pause/breath/filler/jl/rhythm_snap) | **ВСЕ ВЫКЛЮЧЕНЫ**, КРОМЕ `cut_snap` (`=True`, snap к word boundaries) | — |
| 7c | zoom layer (Stage B smart zoom) | **ВЫКЛЮЧЕН** — gated на `post_production_config.zoom_enabled`, а config=None → zoom_plan=None (`render.py:559-562`) | — |
| 7d | motion (punch-in + Ken Burns) | **ВЫКЛЮЧЕН** (оба toggle False) | — |
| 7e | screencast cursor zoom / deictic zoom / mouth-sound | **DORMANT** — детекторы могут крутиться, выход ОТБРАСЫВАЕТСЯ (`render.py:1116/1163/776`) | — |
| 7f | subtitle burn | ИСПОЛНЯЕТСЯ (libass, builtin default preset) | — |
| 7g | intro/outro/split-screen/B&W | **ВЫКЛЮЧЕНЫ** (post_production_config=None) | — |
| 7h | loudnorm (EBU R128 two-pass −14 LUFS) | **ИСПОЛНЯЕТСЯ** несмотря на отсутствие preset (defensive `AudioNormalizeSpec(enabled=True)`, `project_graph.py:287`) | — |
| 7i | HEVC encode (`hevc_videotoolbox`+hvc1, faststart, AAC) | ИСПОЛНЯЕТСЯ — реальный ffmpeg | финальный mp4 |
| 8 | **finalize / mark_done** | ИСПОЛНЯЕТСЯ. timing → `jobs.options`, status=done, SSE done | — |
| 9 | **(scheduler/publer публикация)** | **НЕ ЧАСТЬ pipeline.** Полностью ручной отдельный флоу через `/scheduler/*`. Worker реален (`main.py:91`), но публикация запускается ТОЛЬКО когда юзер создаёт кампанию + approve. No-op если `PUBLER_API_KEY` не задан | `schedule_campaigns`/`schedule_assignments` (по запросу) |

---

## Что работает «по-настоящему» на дефолте

Минимальный рабочий каркас, который реально превращает видео в готовые рилсы:

1. **Upload → job → ingest:** загрузка, INSERT, proxy (1080p, с возможным skip), запуск pipeline (fire-and-forget task).
2. **Транскрипция:** stable-ts MLX, word-level timing, disk-cache. Реальный STT.
3. **silence_cut:** маркировка пауз/филлеров (применяется на render).
4. **Narrative `bottom_up` (полный LLM-мозг):** chunking → compression → canvas → preference_memory → 6 extraction-агентов → reduce_rank → story_doctor (3-act) → rhythm_check → variants → compose_reels → coherence_validator → closure_validator → per-reel scoring. Десятки Gemini Flash-Lite вызовов. Это «сердце» сервиса и оно живое.
5. **Render (ffmpeg HEVC):** cut+concat, статичный center-crop 9:16, `cut_snap` к словам, burn ASS-субтитров (builtin preset), **two-pass loudnorm −14 LUFS** (работает даже без postprod-пресета), HEVC videotoolbox encode. Реальный pixel-bound выход.
6. **SSE прогресс:** реальный live-стрим стадий через event bus.
7. **Audio DSP инфра** (audio_analyzer, vad, beat_detector и т.д.) — реализованы и проводно подключены, но на дефолте задействован только loudnorm + cut_snap; остальные пути ждут включения toggle.
8. **Publer (вне pipeline):** реальный HTTP-клиент + delivery worker — но запускается только по явному пользовательскому действию.

**Условно-работает:** translate (только non-RU источник; на РУ — мгновенный скип).

---

## Что декоративно / выключено на дефолте

**Выключено toggle (OFF by default), вычислений не происходит:**
- Vision-слой целиком (`vision_enabled=False`): visual_evidence (7-й агент), visual_validator, cover_selector — kill-switch.
- Face tracking → flagship «smart reframing» тёмный, рендер = статичный center-crop (mediapipe hang на Apple Silicon).
- multi_arc_builder, cross_chunk_reducer, reducer ensemble (size=1).
- Все cut-transform DSP кроме cut_snap: pause_compression, breath_compression, filler_removal, jl_cut, rhythm_aware_cuts, adaptive_leveller, punchline_pause.
- Zoom Stage B (gated на postprod zoom_enabled=False) + punch_in zoom + Ken Burns drift.
- Весь post-production объект (intro/outro/split-screen/B&W) — config=None т.к. preset не передаётся.

**DORMANT (compute-then-discard — потенциально жгут CPU «для вида»):**
- screencast cursor zoom (`render.py:1116`) — `screencast_cursor_zoom_enabled=True` по дефолту, но потребитель отбрасывает результат («ZoomPlan merge API не реализован»). На talking_head не релевантно, но toggle включён.
- deictic zoom (`render.py:1163`), mouth-sound removal (`render.py:776`) — детекторы запускаются, выход в мусор.

**Недостижимо (orphan / dead в pipeline):**
- B-roll подсистема (`broll/*`) — полностью реализована, ноль call-site.
- object_tracker — `build_zoom_plan` всегда без `object_track`.
- 4 orphan-модуля: person_cluster, match_cuts, eye_trace_continuity, transition_chooser (zero refs).
- LLM-провайдеры anthropic/openai — зарегистрированы, реализованы, но narrative-мозг их не выбирает (всё Gemini).
- narrative_mode `chaptered`/`top_down` — автором помечен broken, для отката.
- `JobStatus.cancelled` — enum есть, `mark_cancelled` в JobService отсутствует (мёртвое значение).

**Декоративный результат (посчитали, не применили):**
- `POST /jobs/{job_id}/reels/{reel_id}/export` — возвращает `bitrate_k`/`target_lufs` + download_url, но **транскода НЕТ** (MVP-заглушка, ссылка на исходный неперекодированный mp4).
- `POST /scheduler/assignments/{id}/cancel` — флипает локальный статус, но на стороне Publer пост НЕ отзывается.
- Tier «pro»/«flash» в story_doctor/canvas/variants — все физически = Flash-Lite (наименование вводит в заблуждение, реального Pro-инференса нет).

---

## Критические разрывы потока (где пайплайн может молча не доехать)

1. **Fire-and-forget pipeline без persistent queue** (`jobs.py:1390`): задача держится только в module-level `_pipeline_tasks` set. **Рестарт процесса = незавершённые джобы НЕ возобновляются**; `reset_stale_running_jobs` помечает их `error`. На single-instance приемлемо, на проде с рестартами — потеря работы.

2. **Throttled-флаш прогресса (3с)**: при крэше до 3с прогресса теряется (статус восстановим через stale-reset, но `current_stage`/`progress` отстают).

3. **JobEventBus RAM-only, maxsize=256**: при переполнении SSE-события **молча дропаются**; на multi-instance деплое SSE и инвалидация кэшей (perf/vision TTL 30с) ломаются — архитектура жёстко single-process/SQLite.

4. **Тихие LLM-fallback'и в narrative**: почти каждая стадия при провале Gemini молча отдаёт детерминистический fallback (`_fallback_chunk`, `_fallback_ranked_evidence`, `_fallback_script`, `_fallback_variants`, `_heuristic_rhythm_report`). При тихих сбоях LLM качество деградирует **без явной ошибки** — пайплайн «доезжает», но результат хуже, чем кажется.

5. **Publer >200 MB reel = hard `ValueError`** (URL-flow не реализован) + re-encode использует `h264_videotoolbox` (macOS-only). На Linux/Railway-деплое ветка re-encode упадёт — публикация длинного/тяжёлого рилса не деградирует, а падает.

6. **translate захардкожен на RU-цель**: target_language = `TARGET_LANGUAGE` константа, форма `source_language=auto` влияет только на детект. Если детект ошибётся — либо лишний перевод, либо его отсутствие, без пользовательского контроля цели.

7. **Нет auth/rate-limit во всём API** (подтверждено Agent A): деструктивные ручки (`DELETE /jobs?purge=nuke`, `/proxies/cleanup`) открыты — не разрыв потока, но разрыв безопасности всего сервиса.
