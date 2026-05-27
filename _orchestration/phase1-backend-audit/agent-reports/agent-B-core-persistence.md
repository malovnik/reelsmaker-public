# Agent B — Core, Models, Job Lifecycle & Persistence

Root: `apps/backend/src/videomaker/`. Persistence engine: **SQLite via `sqlite+aiosqlite`** (single file `data/videomaker.db`), SQLAlchemy 2.0 async ORM. Schema managed by Alembic (`apps/backend/alembic/`, 19 migration files).

Истина состояния: **БД — единственный источник правды для job-домена и всех пользовательских настроек.** In-memory структуры существуют только как (a) SSE pub/sub шина, (b) TTL-кэши поверх БД, (c) per-job timing-телеметрия, которая всё равно флашится в `Job.options`. Артефакты pipeline (transcript/reel_plan/reels/subs) живут **на диске**, а БД хранит относительные пути к ним (`artifacts.path`).

---

## Ядро (core/)

### `core/db.py` — SQLAlchemy engine + session
- `Base(DeclarativeBase)` — общий declarative base для всех ORM-моделей.
- `get_engine()` (db.py:40) — singleton async-engine. `connect_args={"timeout": 30}`. Для SQLite навешивает `event.listen(... "connect", _enable_sqlite_foreign_keys)` → `PRAGMA foreign_keys=ON` (db.py:28) — иначе `ON DELETE CASCADE` игнорируется.
- `get_sessionmaker()` (db.py:60) — singleton `async_sessionmaker`, `expire_on_commit=False`.
- `session_scope()` (db.py:71) — главный async-context: commit при выходе, rollback+raise при исключении. Используется ВСЕМИ store'ами и JobService.
- `dispose_engine()` (db.py:83) — teardown.
- Истина: **БД.** Engine/sessionmaker — process-global singletons (module-level `_engine`, `_sessionmaker`).

### `core/config.py` — Settings (pydantic-settings)
- `Settings` (BaseSettings) — env-driven конфиг. Ключевое:
  - `app_db_path` = `data/videomaker.db` (config.py:82); `database_url` property = `sqlite+aiosqlite:///...` (config.py:241).
  - Каталоги на диске: `app_artifacts_dir` (`data/artifacts`), `app_upload_dir` (`data/uploads`), `app_post_production_assets_dir`, `app_proxies_dir`, `app_face_cache_dir`, `app_models_dir`, `app_fonts_cache_path`.
  - `ensure_directories()` — mkdir для всех путей (вызывается в `get_engine`).
  - env-значения proxy/perf служат **seed** для таблицы `runtime_settings` (config.py:94-96) — runtime берёт эффективные значения из БД, env только дефолт.
- `get_settings()` — кэшированный singleton.

### `core/artifacts.py` — файловый менеджер артефактов (НЕ БД)
- `ArtifactsManager` (artifacts.py:13) — иерархия `<artifacts_dir>/<job_id>/<kind>/` с kinds `{source, audio, text, reels, subs, logs}` (плюс `saved/`).
- Path-traversal защита: `job_dir` (artifacts.py:41) и `resolve_relative` (artifacts.py:62) рейзят `ValueError` при `..`/`/`/escape за пределы корня.
- `write_json` — атомарная запись через `.tmp` + `replace` (artifacts.py:89).
- `delete_job` — `shutil.rmtree` всей job-директории.
- Истина: **диск.** БД хранит только относительные пути в `artifacts.path` + `subtitle_path`/`poster_path` в `artifacts.meta`.

### `core/logging.py`
- `get_logger(__name__)` — structlog-обёртка. Без состояния.

---

## Модели данных и таблицы БД

### ORM-таблицы (Base-subclasses) — **12 таблиц**

| Таблица | ORM-класс (файл) | Назначение | Ключевые связи |
|---|---|---|---|
| `jobs` | `Job` (job_orm.py:47) | Основная запись обработки видео | `→ projects.id` (SET NULL), `→ post_production_presets.id` (SET NULL); `artifacts` (1:N cascade delete-orphan, lazy=selectin) |
| `artifacts` | `Artifact` (job_orm.py:139) | Файлы-выходы pipeline (transcript/reel_plan/reel_output/proxy/…) | `→ jobs.id` (CASCADE). Index `ix_artifacts_kind_created_at` |
| `prompt_settings` | `PromptSetting` (job_orm.py:167) | Версионированные LLM-промпты (PK=key, `default_content_hash`) | — |
| `runtime_settings` | `RuntimeSettingRow` (job_orm.py:188) | Per-installation конфиг — каждое поле PerformanceSettings/Vision как key/value_json | — |
| `subtitle_style_presets` | `SubtitleStylePresetRow` (job_orm.py:207) | Именованные пресеты стиля сабов (`is_builtin`, `is_default`) | — |
| `projects` | `ProjectRow` (project.py:17) | Логическая группа джобов | ← jobs |
| `video_assets` | `VideoAssetRow` (post_production.py:84) | Intro/outro файлы + ffprobe-метаданные + SHA256 (дедуп) | ← post_production_presets |
| `post_production_presets` | `PostProductionPresetRow` (post_production.py:116) | Пресет финальной обработки (loudnorm, zoom, intro/outro) | `→ video_assets.id ×2` (RESTRICT) |
| `account_profiles` | `AccountProfileRow` (scheduler.py:59) | Профиль Publer-аккаунта (PK=publer_account_id) | ← caption_presets, ← schedule_assignments |
| `caption_presets` | `CaptionPresetRow` (scheduler.py:88) | prepend/append текст к caption | `→ account_profiles` (CASCADE), nullable=global |
| `schedule_campaigns` | `ScheduleCampaignRow` (scheduler.py:119) | Группа запланированных публикаций | ← schedule_assignments (CASCADE) |
| `schedule_assignments` | `ScheduleAssignmentRow` (scheduler.py:139) | Одна публикация (reel×account→время+caption) | `→ campaigns/jobs/artifacts` (CASCADE), `→ account_profiles` (RESTRICT). Unique (campaign,reel,account) |

**Альбемик-история:** initial (`b375…`) создал jobs/artifacts/prompt_settings; затем инкрементальные добавления колонок jobs (display_name, fit_mode, source_language, target_reel_count, force_reingest, vision_profile, custom_system_prompt, post_production_*), embedding_json в artifacts, composite-индексы. `4d9b…` создал legacy YouTube/IG OAuth-таблицы (`oauth_connections`, `scheduled_posts`), которые `eb6d…` (publer migration) **дропнул** и заменил на 6 publer/projects-таблиц. То есть в текущей head-схеме `oauth_connections`/`scheduled_posts` НЕ существуют (только в downgrade-ветке). Итог head = **12 таблиц**.

### Pydantic-модели (DTO / value-objects — НЕ таблицы)
Чистые pydantic-модели, сериализуются в JSON-колонки или передаются между стадиями in-memory:
- `job_dto.py` — `JobCreate/JobRead/JobUpdate/JobProfileUpdate`, `ArtifactRead/ArtifactLikeUpdate`, `SavedReels*`, `SubtitleStylePreset{Create,Update,Read}`.
- `job_constants.py` — enums (`JobStatus`, `JobStage`, `FitMode`, `SourceLanguage`, `VisionProfile`, `ArtifactKind`, `SubtitleAnchor`, `FontWeight`) + `SubtitleStyleConfig` (хранится в `jobs.subtitle_style_json`).
- `runtime_settings.py` — `PerformanceSettings` (519 строк; разбирается в key/value строки `runtime_settings`).
- `vision_settings.py` — `VisionRuntimeSettings`, `VisionProfileOverride`, `ProfileMaskRead`.
- `canvas.py` / `evidence.py` / `narrative.py` / `story_script.py` / `reel_plan.py` / `audio_profile.py` — pipeline data-models, передаются между stages в `PipelineContext`, итог пишется на диск как `reel_plan.json` / `analysis_summary` (НЕ в БД, кроме путей в artifacts).
- `post_production.py` — `PostProductionConfig`, `SplitScreenConfig`, `*Create/Update/Read` DTO.

`models/job_types.py` — `_StrEnumColumn(TypeDecorator)` — VARCHAR ↔ StrEnum coercion (чтобы `Mapped[Enum]` не падал `.value`). `models/job.py` — фасад-реэкспорт (backward-compat), реальные модели разнесены в job_constants/job_types/job_orm/job_dto.

---

## State-машина job (детально)

`JobStatus` (job_constants.py:33): `pending → running → done | error | cancelled`
`JobStage` (job_constants.py:41): `ingest → proxy_generate → transcribe → translate → silence_cut → analyze → render → finalize → done`

Управляется `JobService` (services/jobs.py). Истина статуса/стадии — **колонки `jobs.status`, `jobs.current_stage`, `jobs.progress`**.

```
                 create() jobs.py:122
                        │  INSERT jobs(status=pending, progress=0)
                        │  bus.publish stage="created"
                        ▼
                  ┌──────────┐
                  │ pending  │
                  └────┬─────┘
                       │ first mark_stage() → status=running (буфер)
                       ▼
                  ┌──────────┐   mark_stage(stage, progress, msg)  jobs.py:286
                  │ running  │◄───────────────────────────────────┐
                  └────┬─────┘   • _enter_stage() копит timing     │
                       │         • _pending[job_id] буфер          │ каждая стадия
                       │         • _maybe_flush() в БД раз/3s      │ (9 стадий)
                       │         • bus.publish SSE-событие ────────┘
                       │
        ┌──────────────┼───────────────────┐
        │ success      │ exception в        │ рестарт приложения
        ▼              ▼ run_pipeline_safe  ▼
  mark_done()      mark_error()        reset_stale_running_jobs() jobs.py:881
  jobs.py:321      jobs.py:360         все running → error
  status=done      status=error        ("interrupted by restart")
  stage=done       error=<msg>
  progress=100     finished_at=now
  finished_at=now  _store_timings → options
  _store_timings   bus.publish error
  bus.publish done
        │
        ▼
   ┌────────┐         ┌──────────┐
   │  done  │         │  error   │
   └────────┘         └──────────┘
```

Особенности:
- **Throttled writes** (jobs.py:38, `FLUSH_INTERVAL_SEC=3.0`): `mark_stage` НЕ пишет в БД каждый раз — копит в `self._pending` (in-memory), флашит ≤раз/3с (`_maybe_flush`). `mark_done`/`mark_error` флашат сразу + чистят буфер. Риск: при крэше между флашами теряется до 3с прогресса (но статус восстанавливается через reset_stale_running).
- **Stage timing-телеметрия** — чисто in-memory (`_stage_starts/_stage_durations/_current_stage/_pipeline_start`, jobs.py:58-61), при `mark_done/mark_error` финализируется и пишется в `jobs.options.stage_durations` + `total_generation_sec` (`_store_timings`, jobs.py:901).
- **`extra` в mark_stage** (jobs.py:286) идёт ТОЛЬКО в SSE, не в БД.
- **`cancelled`** — enum-значение есть, но в JobService нет метода `mark_cancelled` (отмена, если есть, реализуется в API-слое — вне скоупа этого агента).
- **Soft/hard/nuke delete** (jobs.py:542): soft = `options.hidden=True`; hard = + удалить нелайкнутые reel_output (файлы+row); nuke = удалить job row + все artifacts + файлы. `list_jobs` фильтрует `options.hidden` Python-side (jobs.py:284).
- **`reset_stale_running_jobs`** (jobs.py:881) — на старте все `running → error`, защита от зависших после рестарта.

---

## Pipeline-оркестрация

`services/pipeline.py` — `run_pipeline()` (pipeline.py:96) → `_run_pipeline_impl` (pipeline.py:150). Обёртка `run_pipeline_safe` (pipeline.py:240) ловит исключения и зовёт `mark_error`. Прогресс маппится в 0–100 через `_STAGE_RANGES` (pipeline.py:55) + `_advance()` (pipeline.py:332).

Архитектура — **3 макро-стадии** (вынесены в пакет `services/pipeline_stages/`), внутри которых "9-stage Kartoziya" pipeline:

1. **`run_ingest_stage`** (pipeline_stages/ingest.py) — Stages 1-5: probe → proxy_generate → transcribe → translate → silence_cut.
2. **`run_analysis_stage`** (pipeline_stages/analysis.py, 61KB) — Stage 6 "analyze", внутри 9 под-стадий (mark_stage все с `JobStage.analyze`, прогресс 5→100 внутри стадии):
   - 6.1 compression → 6.2 canvas_builder → 6.3 orchestrate_extraction (6 агентов) → 6.4 reduce_and_rank → 6.5 compose_story_script → 6.6 check_rhythm → 6.7 generate_variants → 6.8 compose_reels. (Документировано в pipeline.py:6-18.)
3. **`run_render_stage`** (pipeline_stages/render.py, 73KB) — Stage 7-8: render через ProjectGraph→ffmpeg + finalize + `mark_done`.

Состояние между стадиями носит `PipelineContext` (pipeline_context.py) — in-memory dataclass, не персистится; финальные артефакты пишутся на диск через `ArtifactsManager` + регистрируются в БД через `service.add_artifact`.

**Automatic Mode (T11):** `run_pipeline_safe` читает `job.options.auto_config` и при `pipeline_mode=="automatic"` оборачивает весь pipeline в `job_settings_override(ContextVar)` (pipeline.py:269-320) — per-job override PerformanceSettings без записи в глобальную таблицу.

`pipeline_mode.py` — `detect_pipeline_mode()` (чистая функция, без состояния): классифицирует dialogue vs travel по WPM/silence_ratio/word_count.

`project_graph.py` (`ProjectGraph`) — декларативная NLE-модель одного рилса (ноды), компилируется `filter_graph_builder` в один ffmpeg-вызов. `project_renderer.py` (`ProjectRenderer`) — один `asyncio.create_subprocess_exec` на граф + parallel `render_many`. Состояние — in-memory/диск, не БД.

---

## Stores — таблица персистентности

| Store (services/) | Бэкенд | Таблица/файл | Персистит? |
|---|---|---|---|
| `jobs.py` (JobService) | DB | jobs, artifacts | ДА (истина статуса) |
| `job_event_bus.py` | **RAM** | `dict[job_id → list[Queue]]` | НЕТ — by design (SSE pub/sub, single-process) |
| `prompt_store.py` | DB | prompt_settings | ДА (+ версионированный seed) |
| `performance_settings_store.py` | DB + TTL-кэш | runtime_settings | ДА (кэш 30с поверх БД + ContextVar override) |
| `vision_settings_store.py` | DB + TTL-кэш | runtime_settings | ДА (тот же ключ-вэлью стор) |
| `runtime_settings_store.py` | — | — | **ФАСАД** (re-export performance+vision, своей записи нет) |
| `subtitle_store.py` | DB | subtitle_style_presets | ДА |
| `asset_store.py` | DB + диск | video_assets, post_production_presets | ДА (метаданные в БД, файл в data/post_production_assets) |
| `post_production_store.py` | DB | video_assets, post_production_presets | ДА |
| `projects_store.py` | DB | projects, jobs | ДА (принимает session извне) |
| `account_profiles_store.py` | DB | account_profiles, caption_presets | ДА |
| `scheduler_campaigns_store.py` | DB | schedule_campaigns, schedule_assignments | ДА |
| `preference_memory.py` | DB (read) + диск | artifacts (+ reel_plan.json) | ДА (читает лайки/embeddings, 0 LLM, fallback top_by_date) |

**Итог: 13 store-модулей. 11 реально персистят в БД. 1 — чистый in-memory by design (`job_event_bus`). 1 — фасад без собственного хранилища (`runtime_settings_store`).**

---

## Подозрения на заглушки / in-memory

Заглушек/fake-store'ов НЕ найдено. Все упомянутые in-memory структуры — осознанный дизайн, не недоделка:

1. **`JobEventBus` (RAM-only)** — единственный полностью in-memory store. Docstring явно: "один процесс, без Redis" (job_event_bus.py:20). Корректно для single-instance, но **не масштабируется горизонтально**: при >1 воркере SSE-подписчик на воркере A не получит события, опубликованные на воркере B. Очередь `maxsize=256`, при переполнении события молча дропаются (job_event_bus.py:46). Для multi-instance деплоя потребуется Redis/pub-sub.
2. **Throttled-буфер `JobService._pending`** — до 3с прогресса живёт только в RAM. При жёстком крэше теряется, но статус-инвариант чинит `reset_stale_running_jobs`. Приемлемо.
3. **Stage timing** — in-memory, но финализируется в `jobs.options`. ОК.
4. **TTL-кэши perf/vision (30с)** — module-global `_perf_cache`/`_vision_cache`. Read-through поверх БД, инвалидация при PUT. Корректно для single-process; при multi-instance кэш одного воркера не инвалидируется при PUT на другом (до 30с рассинхрон). Та же multi-instance оговорка, что и для шины.
5. **`runtime_settings_store.py`** — НЕ заглушка, а фасад-реэкспорт (явно документирован).

---

## Открытые вопросы

1. **Single-instance assumption:** `JobEventBus` + perf/vision-кэши привязаны к процессу. Целевой деплой single-instance (Railway 1 контейнер) или планируется горизонтальное масштабирование? Если второе — SSE и инвалидация кэша сломаются.
2. **`cancelled` статус:** enum есть, но в JobService нет `mark_cancelled`. Где реализуется отмена (API-роут, прямой UPDATE)? Если нигде — мёртвое значение enum.
3. **`reset_stale_running_jobs` при concurrency:** если задумано >1 воркер, рестарт одного помечает `running → error` ВСЕ джобы, включая активные на других воркерах. Безопасно только при single-instance.
4. **Throttle-потеря прогресса (3с):** при крэше теряется последнее окно прогресса; статус восстанавливается как `error`, но `progress`/`current_stage` могут отставать. Приемлемо?
5. **SQLite на проде:** один файл `data/videomaker.db`, `timeout=30`, async через aiosqlite. При параллельных pipeline + частых write-флашах возможны `database is locked`. Рассматривался ли WAL-mode / переход на Postgres? (Драйвер `value_json` через `sqlite_insert.on_conflict` — SQLite-специфичен, миграция на PG потребует правок в `set_performance_settings`.)
6. **JSON-колонки как scope-расширение:** `jobs.options` несёт `hidden`, `auto_config`, `stage_durations`, `composer_strategy_override`, `total_generation_sec` — фактически schema-less зона. Фильтрация `hidden` идёт Python-side (комментарий: пересмотреть при >1000 jobs). Точка роста техдолга.

---

## Сводка (для координатора)

- **Таблиц БД (head-схема):** **12** (jobs, artifacts, prompt_settings, runtime_settings, subtitle_style_presets, projects, video_assets, post_production_presets, account_profiles, caption_presets, schedule_campaigns, schedule_assignments). Движок — SQLite/aiosqlite, миграции Alembic (19 файлов).
- **Store'ов:** **13.** Персистят в БД — **11**. Чистый in-memory (by design) — **1** (`job_event_bus`). Фасад без своего хранилища — **1** (`runtime_settings_store`). **Заглушек/fake — 0.**
- **Job state-машина:** `pending → running → {done | error | cancelled}` со стадиями `ingest→proxy_generate→transcribe→translate→silence_cut→analyze→render→finalize→done`. Истина состояния — колонки `jobs.status/current_stage/progress`. Прогресс пишется throttled (раз/3с) через in-memory буфер; `done`/`error` флашатся немедленно. SSE-события — параллельный in-memory поток. Pipeline-данные между стадиями носит `PipelineContext` (RAM), финальные артефакты — на диске, в БД только пути. Restart-recovery: все `running → error`.
