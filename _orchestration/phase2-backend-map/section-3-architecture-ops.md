# System Architecture & Operations

> Source: consolidation of Phase 1 backend audit (agents A–E), Phase 1b STUB-REALITY-MAP, plus direct read of `run.sh`, `README.md`, `.env.example`, `main.py`.
> Subject: **videomaker** — local long-video → vertical reels (9:16) cutter driven by multi-pass LLM analysis.

---

## 1. Архитектурный обзор

**Монорепо**, два приложения под `apps/`:

```
apps/
├── backend/    Python 3.12 (uv-managed) — FastAPI + SQLite + ffmpeg + LLM/Vision/STT
│   ├── pyproject.toml · alembic/ (19 миграций) · src/videomaker/
└── frontend/   Vite dev-server + React 19 + Tailwind 4 (порт 3000)
```

> Примечание о расхождении: README/структура местами называет фронт «Next.js 16», но `run.sh` стартует `pnpm dev` через **Vite** (миграция выполнена из-за >12 GB heap у Next/Turbopack — см. шапку `run.sh`). Истина = Vite.

### Слои бэкенда (api → services → core → db)

```
HTTP client / SSE
      │
      ▼
api/routes/  (8 модулей, 10 роутеров, префикс /api/v1, 81 эндпоинт)
   health · jobs · projects(+jobs_router) · scheduler · settings
   · post_production · proxies · files
      │  (ручная валидация → 400; auth/rate-limit ОТСУТСТВУЕТ во всём слое)
      ▼
services/  (бизнес-логика: pipeline, narrative/, llm_*, vision/, video_effects/,
   broll/, transcribers/, publer/, audio-DSP, 13 store-модулей)
      │
      ▼
core/  config (pydantic-settings) · db (SQLAlchemy async engine/session)
   · artifacts (файловый менеджер) · logging (structlog)
      │
      ▼
db: SQLite (sqlite+aiosqlite, один файл data/videomaker.db, 12 таблиц)
   + диск: data/artifacts/<job_id>/ (transcript/reel_plan/reels/subs/...)
```

**Истина состояния:** БД — единственный источник правды для job-домена и всех пользовательских настроек. Артефакты pipeline живут на диске; БД хранит относительные пути (`artifacts.path`). In-memory структуры — только (a) SSE pub/sub шина, (b) TTL-кэши поверх БД, (c) per-job timing, который всё равно флашится в `jobs.options`.

### Точка входа — `main.py`

`create_app()` → FastAPI с CORS-middleware (единственный middleware; `allow_origins=[frontend_origin]`) + `api_router`. Корневой `GET /` отдаёт name/version/docs/health.

**Lifespan (startup → yield → shutdown):**
1. `configure_logging` + `ensure_directories()`.
2. Idempotent DDL bootstrap: `Base.metadata.create_all` (CREATE TABLE IF NOT EXISTS — добавляет таблицы без миграций; Alembic — основной механизм схемы).
3. `seed_default_prompts()` — засев дефолтных LLM-промптов в `prompt_settings` (только отсутствующие ключи).
4. `seed_builtin_if_needed()` — built-in subtitle-пресеты.
5. **Фоновый воркер 1** — `fonts_cache_warmup` (`asyncio.create_task`, ~6 c system_profiler, не блокирует старт).
6. `reset_stale_running_jobs()` — все `running → error` (recovery после рестарта).
7. Сброс publer-assignments `uploading → queued` (recovery доставки).
8. **Фоновый воркер 2** — `PublerWorker(settings).start()` — фоновый delivery-loop (no-op без `PUBLER_API_KEY`).
9. `yield`.
10. Shutdown: остановка PublerWorker → отмена fonts-task → `service.flush_all()` (дослив throttled-буфера прогресса) → `dispose_engine()`.

**Pipeline-воркеры:** сам обработчик видео запускается per-job как fire-and-forget `asyncio.create_task` из `POST /jobs` (ссылки в модульном `_pipeline_tasks: set`). Persistent queue нет — незавершённые при рестарте джобы помечаются `error` (не возобновляются).

---

## 2. Диаграмма зависимостей модулей (services/)

```
                         api/routes/jobs.py  POST /jobs
                                   │  asyncio.create_task
                                   ▼
                         services/pipeline.py  run_pipeline_safe
                                   │  (читает job.options.auto_config →
                                   │   Automatic Mode = per-job override через ContextVar)
        ┌──────────────────────────┼──────────────────────────────┐
        ▼                          ▼                               ▼
  pipeline_stages/ingest     pipeline_stages/analysis        pipeline_stages/render
   probe→proxy→transcribe     («мозг», 9 под-стадий)          ffmpeg HEVC граф
   →translate→silence_cut             │                              │
        │                            │                              │
  ┌─────┴───────┐         ┌──────────┼────────────┐        ┌────────┴─────────┐
  ▼             ▼         ▼          ▼            ▼        ▼                  ▼
proxy.py    transcribers/  chunker  narrative/  agents/   project_graph +    audio-DSP
media.py    (stable_ts,    +semantic (4 mode    (6 extr.  filter_graph_     (vad, loudnorm,
(ffmpeg)    mlx_whisper,    _chunker  orches-    агентов)  builder →          beat-snap,
            deepgram)                 трато-              project_renderer    breath/mouth,
                                      ров)                 → 1 ffmpeg/reel)   filler, pause)
                                       │                          │
                                       ▼                          ▼
                              llm_client.py facade        vision/ (Moondream,
                              ├─ llm_providers/ registry   face_tracker, zoom,
                              │   gemini · zhipu ·          cover_selector,
                              │   anthropic · openai        visual_validator)
                              ├─ llm_clients/ (tier_resolver,
                              │   retry, json_parser, cache)
                              └─ rate_limiter (gemini bucket + zhipu sem)

  Параллельная ветка (НЕ часть pipeline, отдельный ручной флоу):
   api/routes/scheduler.py → publer/scheduler_service.py (build campaign, LLM captions)
        → scheduler_campaigns_store (draft→queued) → publer/worker.py (delivery)
        → publer/client.py (httpx → Publer API v1)
```

**Поддомены services и связи:**

| Поддомен | Модули | Зависит от |
|---|---|---|
| Orchestration | `pipeline.py`, `pipeline_stages/{ingest,analysis,render}`, `pipeline_context`, `pipeline_mode` | всё ниже |
| Narrative/LLM | `narrative/` (12), `agents/`, `compression`, `reducer`, `story_doctor`, `variants_generator`, `coherence/closure_validator`, `viral_arc_builder`, `chunker`/`semantic_chunker`, `prompts`/`prompt_store` | `llm_client` facade |
| LLM infra | `llm_client.py` (facade), `llm_providers/` (6), `llm_clients/` (9), `rate_limiter` | внешние LLM API |
| Vision | `vision/` (Moondream, model_manager, frame_cache), `face_tracker`, `zoom_planner`, `cover_selector`, `visual_validator`, `visual_evidence_agent`, `emphasis_motion` | llama-cpp, mediapipe, ffmpeg |
| Render | `project_graph`, `filter_graph_builder`, `project_renderer`, `renderer`, `split_screen`, `subtitles`/`subtitle_styles`/`font_scanner`, `video_effects/` | ffmpeg |
| Audio-DSP | `audio_analyzer`, `audio_normalizer`, `adaptive_leveller`, `beat_detector`, `vad`, `breath/mouth_*`, `silence_cutter`, `filler_removal`, `pause_compression` | librosa/pyloudnorm/silero/parselmouth, ffmpeg |
| Media | `media.py`, `proxy.py` | ffmpeg/ffprobe |
| Scheduler/Publish | `publer/` (9: client, worker, scheduler_service, media_uploader, caption_generator, post_builder, preset_applier, schemas), `scheduler_campaigns_store`, `account_profiles_store` | Publer API, Gemini (captions) |
| Persistence (stores) | 13 store-модулей (`jobs`, `prompt_store`, `performance/vision_settings_store`, `runtime_settings_store` facade, `subtitle_store`, `asset_store`, `post_production_store`, `projects_store`, `account_profiles_store`, `scheduler_campaigns_store`, `preference_memory`, `job_event_bus` RAM-only) | `core/db` |

---

## 3. Конфигурация

### ENV-переменные (`.env.example`, через pydantic-settings `Settings`)

**LLM-провайдеры:**
| Var | Default | Роль |
|---|---|---|
| `GEMINI_API_KEY` | — | **Обязателен** (дефолтный LLM всего pipeline) |
| `GEMINI_DEFAULT_MODEL` | `gemini-2.5-flash` | (но tier matrix форсит Flash-Lite, см. §4) |
| `ANTHROPIC_API_KEY` / `ANTHROPIC_DEFAULT_MODEL` | — / `claude-sonnet-4-5` | Опц. (клиент реален, в narrative НЕ вызывается) |
| `OPENAI_API_KEY` / `OPENAI_DEFAULT_MODEL` | — / `gpt-5` | Опц. (то же — мёртв в narrative) |
| `ZHIPU_API_KEY` / `ZHIPU_BASE_URL` / `ZHIPU_*_MODEL` | — / `api.z.ai/.../v4` / `glm-5.1` | Опц. GLM-5.1 (hard-switch через UI PerformanceSettings) |
| `ZHIPU_MAX_OUTPUT_TOKENS` | 16000 | |

**STT:**
| Var | Default | Роль |
|---|---|---|
| `MLX_WHISPER_MODEL` | `whisper-large-v3-turbo` | локальный, без ключа |
| `DEEPGRAM_API_KEY` / `DEEPGRAM_MODEL` | — / `nova-3` | Опц. cloud STT |

(дефолтный транскрайбер — `stable_ts_mlx`, тоже локальный без ключа.)

**App:**
`APP_HOST=127.0.0.1`, `APP_PORT=8000`, `APP_LOG_LEVEL=INFO`, `APP_DB_PATH=./data/videomaker.db`, `APP_ARTIFACTS_DIR`, `APP_UPLOAD_DIR`, `APP_MAX_UPLOAD_SIZE_MB=30720`, `FRONTEND_ORIGIN=http://localhost:3000` (CORS), `PUBLIC_BACKEND_ORIGIN` (база для legacy OAuth redirect; OAuth-таблицы дропнуты — см. §6).

**Chunking:**
`CHUNK_TOKEN_THRESHOLD=20000`, `CHUNK_WINDOW_TOKENS=15000`, `CHUNK_OVERLAP_TOKENS=1500`, `LLM_MAX_CONCURRENCY=10` (главный кап параллелизма extraction).

**Publer (из `core/config.py`, частично не в .env.example):**
`PUBLER_API_KEY`, `PUBLER_WORKSPACE_ID` (обязательны для публикации; воркер no-op без ключа), `PUBLER_SCHEDULER_TZ=Asia/Ho_Chi_Minh`, `PUBLER_BASE_URL=https://app.publer.com/api/v1`, `PUBLER_REQUEST_TIMEOUT_SEC=30`.

### Runtime/perf/vision settings stores

ENV даёт **только seed-дефолты**; эффективные значения берутся из таблицы `runtime_settings` (key/value_json):
- `PerformanceSettings` (519-строчная модель) — narrative_mode, llm_tier_profile/lite_variant, concurrency-капы, все toggle-фичи. Read-through TTL-кэш 30 c + `ContextVar` per-job override (Automatic Mode).
- `VisionRuntimeSettings` — `vision_enabled` kill-switch, gguf repo/file, profile-маски (5 профилей). Тот же key/value стор + TTL-кэш.
- `runtime_settings_store.py` — **фасад**, реэкспортит performance+vision, своего хранилища нет.

---

## 4. Внешние зависимости

| Зависимость | Обязательность | Назначение |
|---|---|---|
| **ffmpeg / ffprobe** (на PATH, ≥7 с `hevc_videotoolbox`) | **ОБЯЗАТЕЛЬНА** | реальный render-движок (cut/concat/crop/zoom/subtitle-burn/loudnorm) + probe + proxy |
| **Gemini API** (`GEMINI_API_KEY`) | **ОБЯЗАТЕЛЬНА** | дефолтный LLM всех narrative-стадий + captions; без него pipeline не работает |
| **stable-ts MLX / mlx-whisper** (локально, Apple Silicon) | **ОБЯЗАТЕЛЬНА** (дефолтный STT) | транскрипция без ключа; альтернатива — Deepgram |
| Zhipu GLM-5.1 (`ZHIPU_API_KEY`) | Опциональна | альтернативный pipeline-LLM (hard-switch в UI; concurrency=1 gate) |
| Deepgram nova-3 (`DEEPGRAM_API_KEY`) | Опциональна | cloud-STT, точнее на RU/сложных акцентах |
| Anthropic / OpenAI (`ANTHROPIC_/OPENAI_API_KEY`) | Опциональна | клиенты реальны, но в narrative-pipeline НЕ вызываются (только translator/auto_config); по MEMORY стек = Gemini-only |
| Publer Business API v1 (`PUBLER_API_KEY`+`WORKSPACE_ID`) | Опциональна | публикация Reels/Shorts; воркер no-op без ключа |
| **Moondream 2 GGUF** (llama-cpp-python, Metal) | Опциональна | vision-слой; выключен kill-switch `vision_enabled=False` по умолчанию; авто-download через huggingface_hub |
| **mediapipe** (blaze_face) | Опциональна | face-tracking; выключен по умолчанию (hang на M-series) |
| OpenCV / librosa / silero-vad / parselmouth / scikit-maad | Опциональны (graceful-degrade) | cursor-detect / audio-DSP — при отсутствии возвращают safe-defaults |

**Обязательных внешних зависимостей: 3** — ffmpeg/ffprobe, Gemini API, локальный MLX-STT (stable-ts/mlx-whisper). Всё остальное опционально и/или graceful-degrades.

> Портируемость: re-encode в `media_uploader` исторически был macOS-only (`h264_videotoolbox`). В 1b-fix добавлен рантайм-выбор энкодера с `libx264` fallback (`_has_videotoolbox_h264`) — Linux-деплой теперь не падает на этом пути.

---

## 5. Запуск / эксплуатация

**Подъём:** `./run.sh` из корня (требует `uv`, `pnpm`, `ffmpeg` на PATH).
Скрипт: создаёт `.env` из `.env.example` при отсутствии → `mkdir data/{uploads,artifacts,logs}` → `uv sync` (backend) + `pnpm install` (frontend) → **preflight cleanup** (SIGKILL residual uvicorn/vite/esbuild/ffmpeg, освобождение портов 8000/3000 через lsof, очистка `__pycache__`) → запускает **оба процесса параллельно** с `trap cleanup`.

**Порты:**
- backend (uvicorn FastAPI, `--reload`) — `127.0.0.1:8000`; docs `/docs`, health `/api/v1/health`.
- frontend (Vite dev) — `localhost:3000`.

**БД-файл:** `data/videomaker.db` (SQLite, `sqlite+aiosqlite`, `timeout=30`, **WAL + busy_timeout=30000** включены в 1b-fix). PRAGMA `foreign_keys=ON` навешан на connect (иначе CASCADE игнорируется). Схема — Alembic (`uv run alembic upgrade head`), + idempotent `create_all` на старте.

**Артефакты на диске** (`data/`):
```
data/
├── videomaker.db
├── uploads/<job_id>/            исходники
├── artifacts/<job_id>/{source,audio,text,reels,subs,logs}/ + saved/
│     text/: transcript.json, cleaned_transcript.json, reel_plan.json,
│            analysis_summary.json, project_graphs.json, manifest.json
│     reels/: финальные mp4 (HEVC) · subs/: .ass
├── proxies/                     1080p H.264 proxy-кэш (LRU, keyed по sha256+profile)
├── post_production_assets/      intro/outro (dedup по SHA256)
├── thumbnails/, face_cache/, models/ (Moondream GGUF), fonts_cache.json
└── logs/
```
ArtifactsManager пишет JSON атомарно (`.tmp`+replace) и защищает от path-traversal (`ValueError` на `..`/escape). Чистка: `DELETE /jobs?purge=soft|hard|nuke`, `DELETE /proxies/cleanup` (LRU).

**Эксплуатационные ограничения (single-instance):** `JobEventBus` (SSE) и perf/vision TTL-кэши привязаны к процессу — горизонтальное масштабирование сломает SSE и инвалидацию кэша (нужен Redis). `reset_stale_running_jobs` на старте бьёт ВСЕ `running` джобы — безопасно только при одном инстансе. Целевой деплой — локальный single-user инструмент.

---

## 6. Техдолг и риски

Статус «починено в 1b-fix» подтверждён прямым чтением кода.

| # | Проблема | Приоритет | Статус 1b-fix | Доказательство |
|---|---|---|---|---|
| 1 | `reel_id` path-traversal (PATCH subtitles = write-primitive) | 🔒 P0 | ✅ FIXED — `_validate_reel_id` (regex `^[A-Za-z0-9_-]+$`+len) на всех 3 call-site | jobs.py:1286,1327,1351,1401 |
| 2 | viral_2026 игнорировал выбор провайдера (жёг Gemini при Zhipu) | 🐞 P1 | ✅ FIXED — `pipeline_provider` пробрасывается в `build_llm_for_tier(provider_override=...)` | viral_arc_builder.py:407,432,436 |
| 3 | `h264_videotoolbox` macOS-only в re-encode (>180MB рилс падал на Linux) | 🐞 P1 | ✅ FIXED — рантайм-выбор + libx264 fallback | media_uploader.py:80,133,147 |
| 4 | cancel job не работал (`mark_cancelled` отсутствовал — мёртвый enum) | 🔴 P1 | ✅ FIXED — `mark_cancelled` реализован | services/jobs.py:385 |
| 5 | SQLite database-locked при параллельных флашах (нет WAL/busy_timeout) | 🟡 P2 | ✅ FIXED — PRAGMA WAL + busy_timeout=30000 | core/db.py:40-41 |
| 6 | ~972 LOC orphan-кода (B-roll, object_tracker, person_cluster, match_cuts, eye_trace_continuity, transition_chooser) | 🧹 — | ❌ НЕ удалено (модули всё ещё на диске) | services/broll, services/{object_tracker,person_cluster,match_cuts,eye_trace_continuity,transition_chooser}.py |
| 7 | tier «pro»/«flash» — фикция (все → Flash-Lite); fallback'ы тихо маскируют LLM-сбой; Moondream `detect` = VQA-эвристика, не детекция | 🏷️ честность | ⏸️ ОТЛОЖЕНО | tier_resolver.py:37-52, moondream_local.py:259 |
| 8 | DORMANT video-фичи (screencast cursor zoom, deictic zoom, mouth-sound removal) — детекторы крутятся, выход выбрасывается, UI-toggle off | 🟡 — | ⏸️ ОТЛОЖЕНО (PRD): выключить дефолт ИЛИ оживить | render.py:776,1116,1163 |
| 9 | `POST /jobs/{id}/reels/{rid}/export` — нет реального транскода (download_url = исходный mp4, bitrate/lufs декларативны) | 🟡 M | ⏸️ ОТЛОЖЕНО (PRD) | jobs.py:1317 |
| 10 | `POST /scheduler/assignments/{id}/cancel` — только local flip, нет DELETE в Publer | 🟡 M | ⏸️ ОТЛОЖЕНО (PRD) | scheduler.py:717 |
| 11 | `GET /post_production/presets/default` — 200+null вместо 204 | 🟡 S | ⏸️ ОТЛОЖЕНО | post_production.py:210 |
| 12 | fire-and-forget pipeline (рестарт = потеря незавершённых джоб, persistent queue нет) | 🟡 P2 | ⏸️ ОТЛОЖЕНО (PRD) | jobs.py:1390 |
| 13 | Vision-слой целиком + face-tracking OFF по умолчанию (flagship reframing тёмный; mediapipe hang на M-series) | DECISION | ⏸️ PRD | runtime_settings.py:405 |
| 14 | Полное отсутствие auth/authz/rate-limit (только CORS) | DECISION | ⏸️ Сознательно НЕ добавляем | main.py (CORS only) |
| 15 | Single-instance: JobEventBus + кэши process-bound; не масштабируется горизонтально | 🟡 P3 | ⏸️ приемлемо для single-instance | — |
| 16 | Publer >200MB рилс = hard ValueError («URL-flow не реализован») | 🟡 — | ⏸️ задокументированный лимит | media_uploader.py:56 |
| 17 | `narrative_mode=chaptered` помечен автором broken, но выбираем из UI | 🟡 — | ⏸️ убрать из UI/починить | map_reduce_orchestrator.py:18 |

**Решение по auth:** сервис спроектирован как локальный single-user инструмент; публичность репо ≠ публичный деплой. Auth НЕ добавляется по умолчанию (Karpathy-дисциплина), документируется как deploy-time concern. Path-traversal (#1) починен независимо — это баг при любом сценарии.

**Заглушек/fake-store в персистентности и audio/publer-слоях — 0** (агенты B и E). Все in-memory структуры — осознанный дизайн (SSE-шина, throttle-буфер, TTL-кэши), не недоделка.
