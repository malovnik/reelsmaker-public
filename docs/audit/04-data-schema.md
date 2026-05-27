# 04 — Схема данных: SQLite + файловое хранилище

> **Чанк:** REFACTR-04 (5 из 67). **Этап:** 00 — Исследование и аудит.
> **Дата:** 2026-04-24. **Роль:** R-AUDITOR + R-DATA-ARCHITECT (консультативно).
> **Зависимости:** REFACTR-00 (backend map), REFACTR-03 (PRO removal).
> **Следующий шаг:** REFACTR-05 (Pipeline stages).

---

## 0. Резюме

- **База:** SQLite, файл `data/videomaker.db` (1.25 MiB, бэкап `.bak-20260423-192330` того же размера).
- **ORM:** SQLAlchemy 2.0 (Mapped/mapped_column). Декларации в `apps/backend/src/videomaker/models/*.py` + ORM-stores в `services/*_store.py`.
- **Миграции:** Alembic, линейная цепочка из 18 ревизий, HEAD=`eb6d1b814c95` (publer_scheduler_schema). В коде есть startup-хак `Base.metadata.create_all` в `main.py:45-51`, обходящий Alembic для новых таблиц — см. §4.2.
- **Таблиц:** 12 прикладных + 1 `alembic_version` = **13**.
- **Файловое хранилище:** `data/` — 36 GB (~15 GB uploads + ~9.7 GB proxies + ~6.9 GB artifacts + 3.5 GB models + ~345 MB кэши).

---

## 1. ORM-модели (SQLAlchemy)

Все модели наследуются от `videomaker.core.db.Base`. Перечень по файлам.

### 1.1. `models/job_orm.py` — job-домен

| Таблица | Класс | PK | Ключевые поля / связи |
|---------|-------|----|----------------------|
| `jobs` | `Job` | `id` VARCHAR(36) UUID | `source_path`, `source_filename`, `source_size_bytes`, `display_name`, `source_duration_sec`; `status` (StrEnum JobStatus), `current_stage` (StrEnum JobStage), `progress`, `message`, `error`; `transcriber`, `llm_provider`, `llm_model`, `target_aspect` (9:16), `fit_mode` (fill), `source_language` (auto), `detected_language`; `subtitle_style_json` (JSON), `post_production_preset_id` (FK→post_production_presets.id ON DELETE SET NULL), `post_production_config_json` (JSON snapshot), `target_reel_count`, `force_reingest`, `vision_profile` (StrEnum default=talking_head, server_default=talking_head), `options` (JSON dict), `custom_system_prompt`, **`project_id`** (FK→projects.id ON DELETE SET NULL, INDEX); timestamps `created_at`, `updated_at`, `finished_at`; `artifacts` relationship (1:N cascade delete) |
| `artifacts` | `Artifact` | `id` INT autoincrement | `job_id` (FK→jobs.id ON DELETE CASCADE, INDEX), `kind` (StrEnum ArtifactKind), `path` (относительный), `meta` (JSON), `embedding_json` (nullable JSON float-array 256-dim — Gemini embedding для лайков, T6.1), `created_at`; composite index `ix_artifacts_kind_created_at(kind, created_at)` |
| `prompt_settings` | `PromptSetting` | `key` VARCHAR(64) | `content` (Text), `default_content_hash` (SHA-256 снепшот дефолта), `updated_at`; uniq `uq_prompt_settings_key` |
| `runtime_settings` | `RuntimeSettingRow` | `key` VARCHAR(128) | `value_json` (Text, pure JSON-строка), `updated_at`; uniq `uq_runtime_settings_key`. **Каждое поле `PerformanceSettings` = отдельная строка** (EAV-паттерн). |
| `subtitle_style_presets` | `SubtitleStylePresetRow` | `id` INT autoincrement | `name` uniq, `style_json` (JSON), `is_builtin`, `is_default` (app-enforced singleton), timestamps |

### 1.2. `models/project.py` — группировка jobs

| Таблица | Класс | PK | Поля |
|---------|-------|----|------|
| `projects` | `ProjectRow` | `id` INT autoincrement | `name` String(256), `description` Text, `color` String(16) default `#6366f1`, timestamps |

**Критично:** текущая модель — **минимальная**. Нет `settings_snapshot`, `stage_progress`, `soft_deleted_at`, `last_saved_at`, `parent_project_id`, `source_upload_path`. Задача REFACTR-14 (Этап 02) — расширить эту таблицу под требования task.md §2.4-5 (копирование настроек, автосейв, soft-delete, duplicate-from). В БД сейчас **0 записей** (!).

### 1.3. `models/post_production.py` — пост-продакшен

| Таблица | Класс | PK | Ключевые поля |
|---------|-------|----|---------------|
| `video_assets` | `VideoAssetRow` | `id` INT autoincrement | `name`, `file_path`, `file_hash` SHA-256 uniq (дедуп контента), `file_size_bytes`; ffprobe-метаданные (duration_sec, width, height, fps, video_codec, audio_codec, sample_rate, channels); `created_at` |
| `post_production_presets` | `PostProductionPresetRow` | `id` INT autoincrement | `name` uniq, `is_default` (app-enforced singleton); `intro_asset_id`, `outro_asset_id`, `companion_asset_id` (FK→video_assets.id ON DELETE RESTRICT); split-screen конфиг (9 полей), audio loudnorm (2), zoom config (10), `bw_enabled`; timestamps |

### 1.4. `models/scheduler.py` — Publer-расписание

| Таблица | Класс | PK | Ключевые поля |
|---------|-------|----|---------------|
| `account_profiles` | `AccountProfileRow` | `publer_account_id` VARCHAR(24) | `display_name`, `network` (instagram/youtube), `language`, `audience`, `tone`, `default_hashtags_json`, `banned_words_json`, `cta_style`, `max_caption_length`; timestamps |
| `caption_presets` | `CaptionPresetRow` | `id` INT autoincrement | `name`, `position` (prepend/append), `content` Text, `account_id` nullable FK→account_profiles.publer_account_id ON DELETE CASCADE (global если NULL), `is_active`; timestamps |
| `schedule_campaigns` | `ScheduleCampaignRow` | `id` INT autoincrement | `name`, `tz` default `Asia/Ho_Chi_Minh`, `time_of_day` String(8), `dates_json` list, `status` (draft/active/…); timestamps |
| `schedule_assignments` | `ScheduleAssignmentRow` | `id` INT autoincrement | `campaign_id` (FK CASCADE, INDEX), `job_id` (FK jobs.id CASCADE, INDEX), `reel_artifact_id` (FK artifacts.id CASCADE, INDEX), `publer_account_id` (FK RESTRICT, INDEX), `network`, `title`, `caption` Text, `hashtags_json`, `applied_preset_ids_json`, `scheduled_at_utc`, `status` (StrEnum AssignmentStatus: draft/queued/uploading/scheduled/published/failed/cancelled), Publer tracking (publer_media_id, publer_job_id, publer_post_id, publer_post_url), `error_message`, `attempts`, `last_attempt_at`; uniq `(campaign_id, reel_artifact_id, publer_account_id)` |

### 1.5. Pydantic-only модели (не ORM, но часто смешаны в тех же файлах)

Не хранятся в БД напрямую — только в JSON-колонках или в файлах:

| Модель | Файл | Хранение |
|--------|------|----------|
| `PerformanceSettings` (≈80 полей) | `models/runtime_settings.py` | `runtime_settings` EAV rows (один ключ = одна строка, см. §3.3) |
| `VisionRuntimeSettings` | `models/vision_settings.py` | `runtime_settings` rows (префиксы `vision_*`) |
| `PostProductionConfig`, `SplitScreenConfig`, `SplitScreenTransform` | `models/post_production.py` | Snapshot в `jobs.post_production_config_json` + in-row fields в `post_production_presets` |
| `PromptSettings` | `models/runtime_settings.py`? нет — отдельная таблица `prompt_settings` | Таблица `prompt_settings` |
| `ProjectCanvas`, `CandidateMoment`, `Theme`, `Motif` | `models/canvas.py` (236 LoC) | **Файлы:** `data/artifacts/<job_id>/text/canvas_full.json` |
| `Evidence`, `RankedEvidence` | `models/evidence.py` (114 LoC) | Файлы `data/artifacts/<job_id>/text/extraction_full.json`, `reduce_result.json` |
| `AudioProfile`, `AudioAnalysis` | `models/audio_profile.py` (97 LoC) | Файлы `data/artifacts/<job_id>/audio/` |
| `Chapter`, `HookCandidate`, `NarrativeArc`, `ExtendedArc`, `ReelCandidate`, `NarrativeMode` | `models/narrative.py` (230 LoC) | Файлы `data/artifacts/<job_id>/text/` (реорганизуются при REFACTR-13 — см. §5) |
| `AnalysisResult`, `ReelPlan`, `ReelSegment` | `models/reel_plan.py` (81 LoC) | Файл `data/artifacts/<job_id>/text/reel_plan.json` |
| `StoryScript`, `RhythmReport` | `models/story_script.py` (137 LoC) | Файлы `data/artifacts/<job_id>/text/story_script.json`, `rhythm_report.json` — bottom_up-only (удалим в REFACTR-13) |
| `JobRead`, `ArtifactRead`, `JobStatus`, `JobStage`, `VisionProfile`, `ArtifactKind` | `models/job_dto.py`, `models/job_constants.py`, `models/job_types.py` | DTO для API, StrEnum для ORM колонок |

---

## 2. History Alembic-миграций

Линейная цепочка (нет веток, нет merge). Запуск через `uv run alembic upgrade head` — **но** в `main.py:45-51` выполняется `Base.metadata.create_all(engine)` на startup, что создаёт таблицы **до** прогона Alembic. Это опасный паттерн (описано в REFACTR-00).

```
b375ed0ea0a0  initial_schema_jobs_artifacts_prompt     (ROOT)
ad0e5af03bfc  add_fit_mode_source_language_detected
db8c0fadfc0c  add_subtitle_style_presets_jobs
199a04cb840f  add_post_production_presets_and_video_
4b2e9f7c1a3d  add_target_reel_count_to_jobs
7c1f3a9b5e2d  add_bw_enabled_to_post_production
8d4a2c6e1f9b  add_default_content_hash_to_prompt
9e5b1f8a2c04  add_force_reingest_to_jobs
b1c4f7a9d3e2  add_vision_profile_to_jobs
4d9b9c14491d  add_oauth_connections_and_scheduled_
857f16ff0a07  add_display_name_to_jobs
c2f8a1b39e74  add_embedding_json_to_artifacts
d1a4f6b8e2c5  add_custom_system_prompt_to_jobs
e3f2c8a4d715  add_split_screen_to_presets
9df22144281d  split_main_companion_fit_modes
99f725157583  add_job_indices_status_created_at
31992a96f15c  add_artifact_kind_created_composite
eb6d1b814c95  publer_scheduler_schema                 (HEAD, CURRENT)
```

**Текущая ревизия в БД:** `eb6d1b814c95` (verified via `SELECT version_num FROM alembic_version`).

### 2.1. Что было в каждой ревизии (коротко)

| Ревизия | Краткое описание |
|---------|------------------|
| `b375ed0ea0a0` | Initial: jobs + artifacts + prompt_settings + runtime_settings |
| `ad0e5af03bfc` | `fit_mode`, `source_language`, `detected_language` в jobs |
| `db8c0fadfc0c` | Новая таблица `subtitle_style_presets` + FK в jobs |
| `199a04cb840f` | Новые `post_production_presets` + `video_assets` + FK в jobs |
| `4b2e9f7c1a3d` | `target_reel_count` в jobs |
| `7c1f3a9b5e2d` | `bw_enabled` в post_production_presets |
| `8d4a2c6e1f9b` | `default_content_hash` в prompt_settings (версионирование дефолтов) |
| `9e5b1f8a2c04` | `force_reingest` в jobs |
| `b1c4f7a9d3e2` | `vision_profile` в jobs (StrEnum) |
| `4d9b9c14491d` | `oauth_connections` + legacy `scheduled_projects` (исчезла позже) |
| `857f16ff0a07` | `display_name` в jobs |
| `c2f8a1b39e74` | `embedding_json` в artifacts (256-dim Gemini) |
| `d1a4f6b8e2c5` | `custom_system_prompt` в jobs |
| `e3f2c8a4d715` | `split_screen_*` в post_production_presets |
| `9df22144281d` | split_screen_fit_mode → main/companion раздельно |
| `99f725157583` | Индексы jobs по `(status, created_at)` |
| `31992a96f15c` | `ix_artifacts_kind_created_at(kind, created_at)` composite |
| `eb6d1b814c95` | Publer scheduler: account_profiles + caption_presets + schedule_campaigns + schedule_assignments |

### 2.2. Мета-наблюдения

- Темп миграций: 18 за ~8 месяцев → в среднем 2-3/мес. Миграции мелкие (1-2 column add или 1 table add). Хорошая гранулярность.
- Все миграции — **add-only**, ни одной `drop_column`/`drop_table`. Значит: есть legacy-поля, которые не используются (часть будет удалена в REFACTR-13 вместе с PRO-ампутацией).
- Нет `downgrade()` функций, заполненных смыслом, — скорее всего пустые `pass` везде. Откат миграций не поддержан. **Риск:** для Этапа 02 (ампутация PRO) это не блокер (миграция будет add + delete, не rollback-first), но надо проверить при REFACTR-14.

---

## 3. Содержимое реальной БД

### 3.1. Row counts (на 2026-04-24 14:22)

| Таблица | Rows |
|---------|------|
| `alembic_version` | 1 (HEAD=eb6d1b814c95) |
| `prompt_settings` | 24 (каждый ключ — один промпт) |
| `artifacts` | **725** |
| `subtitle_style_presets` | 6 |
| `video_assets` | 5 |
| `runtime_settings` | 87 (EAV rows) |
| `post_production_presets` | 2 |
| `account_profiles` | 3 (Publer-аккаунты) |
| `projects` | **0** (таблица не используется!) |
| `schedule_campaigns` | 1 |
| `caption_presets` | 0 |
| `schedule_assignments` | 15 (одна успешная Publer-кампания) |
| `jobs` | **50** (31 done + 19 error = ~62% success rate) |

### 3.2. Распределение artifacts по kind

| kind | count | Примечания |
|------|-------|------------|
| `reel_output` | 520 | финальные .mp4 в `data/artifacts/<job>/reels/r*.mp4` |
| `transcript` | 54 | `data/transcripts/<sha>/transcript.json` (hash-addressed cache) |
| `cleaned_transcript` | 48 | `data/artifacts/<job>/text/cleaned_transcript.json` |
| `reel_plan` | 43 | `data/artifacts/<job>/text/reel_plan.json` (2 с viral_2026 меткой, ~41 bottom_up) |
| `project_graph` | 35 | render graph snapshot |
| `proxy` | 25 | `data/proxies/<sha>__<id>.mp4` (downscaled для анализа) |

**Лайки:** 54 артефакта с `meta` содержащими `"liked":"like"` (preference_memory data). Орфанятся после ампутации PRO (REFACTR-13), но `embedding_json` можно сохранить как nullable read-only поле без удаления.

### 3.3. Runtime_settings (EAV) — структура и содержимое

87 rows, суммарный размер `value_json` = 841 bytes (очень компактно). Паттерн:

```sql
CREATE TABLE runtime_settings (
    key VARCHAR(128) NOT NULL PRIMARY KEY,
    value_json TEXT NOT NULL,  -- JSON-value: "viral_2026", true, 20000, ["arr"], ...
    updated_at DATETIME NOT NULL,
    CONSTRAINT uq_runtime_settings_key UNIQUE (key)
);
```

**Ключи текущей инсталляции:** 87 ключей на: `narrative_mode="viral_2026"` (REFACTR-03), 20 полей PRO-ампутации (удаляются), remaining: proxy_*, vision_*, punchline_*, punch_in_zoom_*, ken_burns_*, face_tracker_*, breath_*, filler_*, pause_*, rhythm_aware_*, snap_*, cut_snap_*, jl_cut_*, screencast_*, semantic_chunk_*, preference_retrieval_mode, pacing_profile, pipeline_mode, llm_tier_profile, llm_lite_variant, pipeline_llm_provider, reel_target_*, reel_count_*, deictic_zoom_enabled, context_aware_keep_sec_enabled, smart_jl_chooser_enabled, adaptive_leveller_enabled, mouth_sound_removal_enabled, default_use_source_for_render.

**EAV антипаттерн:** для ~80 полей всегда читается 80 строк → 80 SELECT'ов либо один `SELECT *`. В REFACTR-16 (settings snapshot) стоит рассмотреть переход на одну JSON-колонку `value` в одной строке (key='performance') — проще `settings_snapshot`-копирование.

### 3.4. Orphan-анализ

- **`projects: 0`** — таблица пустая, **нулевой data-migration risk** при расширении структуры в REFACTR-14 (новые поля `settings_snapshot_path`, `stage_progress`, `soft_deleted_at`, `parent_project_id`, `last_saved_at`, `source_upload_path`). Alembic-миграция — чистый `add_column`, ни одна запись не нуждается в backfill.
- **artifacts 725, папок на диске 5:** 720 строк в `artifacts` ссылаются на уже несуществующие job-папки (jobs чистились частично). Пути в `artifacts.path` — относительные от `data/artifacts/<job_id>/`. REFACTR-20 (cleanup) должен пройти по orphan'ам.
- **jobs (50) vs uploads (50 папок) vs artifacts-job-dirs (5 папок):** каждый job создал upload, но 45 из 50 потеряли свои `data/artifacts/<job_id>/` (вычищены), однако остались строки в `artifacts`. Данные фрагментарны.

---

## 4. Файловое хранилище

### 4.1. Структура и размеры

```
data/  ≈ 36 GB (без логов)
├── uploads/                  # 15 GB — исходные видео
│   └── <job_uuid>/
│       └── <filename>.mp4
├── proxies/                  # 9.7 GB — downscaled для анализа
│   └── <sha256>__<short>.mp4  # hash-addressed (дедуп между jobs)
├── artifacts/                # 6.9 GB — jobs artifacts (только 5 папок)
│   └── <job_uuid>/
│       ├── audio/            # source.wav, extracted_audio.wav
│       ├── logs/             # пусто или jobs-specific
│       ├── reels/            # r01.mp4..rNN.mp4 (финальные)
│       ├── source/           # копия source или proxy
│       ├── subs/             # r01.ass..rNN.ass
│       └── text/             # canvas_full.json, transcript.json, reel_plan.json, ...
├── models/                   # 3.5 GB — ML модели (moondream2, mlx-whisper кэш)
│   └── moondream2/
├── vision_cache/             # 318 MB — Moondream2 per-frame кэш
│   └── <video_sha256>/
├── post_production_assets/   # 69 MB — intro/outro библиотека
│   ├── <asset_id>__<name>.mp4
│   └── _pending/             # временная папка для загрузки
├── face_cache/               # 28 MB — MediaPipe face keyframes
│   └── <uuid>/
├── transcripts/              # 15 MB — transcript cache (hash-addressed)
│   └── <video_sha256>/
│       └── transcript.json
├── thumbnails/               # 1.7 MB — jpg per-job
│   └── <job_uuid>/
├── logs/                     # 0 B — ПУСТО, логи никуда не пишутся!
├── videomaker.db             # 1.25 MiB
└── videomaker.db.bak-20260423-192330  # 1.25 MiB
```

### 4.2. Naming conventions — mixed (техдолг)

Две параллельные схемы адресации:

| Данные | Naming | Локация | Плюс | Минус |
|--------|--------|---------|------|-------|
| Jobs/uploads/artifacts | UUID (`jobs.id`) | `uploads/<uuid>/`, `artifacts/<uuid>/`, `thumbnails/<uuid>/`, `face_cache/<uuid>/` | Прямая привязка к job записи | Если jobs чистятся, orphan-папки живут самостоятельно; потеря связи после delete |
| Proxies/transcripts/vision_cache | SHA-256 хеш контента | `proxies/<sha>__<uuid>.mp4`, `transcripts/<sha>/`, `vision_cache/<sha>/` | Дедупликация между jobs (один видеофайл = один кэш) | Нужно hash-calculate на каждый входящий файл; медленно для больших видео |
| Post-production assets | `<id>__<name>.mp4` (integer ID + human name) | `post_production_assets/<id>__<name>.mp4` | Человеко-читаемо в файл-менеджере | Требует БД-связи (без БД — не знаем kind) |

### 4.3. Секреты (`.env`)

26 переменных, **НЕ коммитить**. Категории:

| Категория | Ключи | Критичность |
|-----------|-------|-------------|
| LLM keys | `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `DEEPGRAM_API_KEY`, `ZHIPU_API_KEY` | CRITICAL — утечка = financial impact |
| Publer | `PUBLER_API_KEY`, `PUBLER_WORKSPACE_ID` | HIGH |
| App config (не секрет) | `APP_HOST`, `APP_PORT`, `APP_LOG_LEVEL`, `APP_DB_PATH`, `APP_ARTIFACTS_DIR`, `APP_UPLOAD_DIR`, `APP_MAX_UPLOAD_SIZE_MB`, `FRONTEND_ORIGIN` | LOW |
| Defaults | `GEMINI_DEFAULT_MODEL`, `ANTHROPIC_DEFAULT_MODEL`, `OPENAI_DEFAULT_MODEL`, `MLX_WHISPER_MODEL`, `DEEPGRAM_MODEL` | LOW |
| Pipeline tuning | `CHUNK_TOKEN_THRESHOLD`, `CHUNK_WINDOW_TOKENS`, `CHUNK_OVERLAP_TOKENS`, `LLM_MAX_CONCURRENCY`, `VISION_ENABLED` | LOW |

`.env.example` (2205 bytes) присутствует — template для нового клона. Good practice.

**Риск R-SECURITY (Этап 03):** секреты НИКОГДА не должны попадать в error-responses, логи, SSE-стримы. Проверка обязательна в REFACTR-24 (path traversal + argv-only + secrets leak scan через semgrep).

### 4.4. `data/logs/` — пустая

Директория существует, но **0 байт**. Это значит:
- Либо логирование идёт в stdout/stderr (через `loguru` или `structlog`) — `videomaker.core.logging::get_logger` — и не перенаправляется в файлы.
- Либо `app_log_file` не настроен.

REFACTR-59 (log rotation) должен:
1. Унифицировать логи в `data/logs/videomaker-YYYY-MM-DD.log` (daily rotation).
2. Отдельные файлы для pipeline stages (ingest/analysis/render) + http access + errors.

---

## 5. Таблица «где хранится что»

| Сущность | SQLite таблица | JSON-файлы | Binary-файлы | Secrets / cache |
|----------|----------------|------------|--------------|-----------------|
| Project (группа jobs) | `projects` | — | — | — |
| Job (обработка видео) | `jobs` + `artifacts` | `options` (JSON в jobs), `subtitle_style_json`, `post_production_config_json` (snapshots) | — | — |
| Video upload | `jobs.source_path` (pointer) | — | `data/uploads/<job>/*.mp4` | — |
| Transcript (content-addressed cache) | `artifacts` row kind=transcript (pointer) | `data/transcripts/<sha>/transcript.json` | — | — |
| Cleaned transcript | `artifacts` row kind=cleaned_transcript | `data/artifacts/<job>/text/cleaned_transcript.json` | — | — |
| Project canvas (LLM output) | — | `data/artifacts/<job>/text/canvas_full.json` | — | — |
| Extraction result (bottom_up, удаляем) | — | `data/artifacts/<job>/text/extraction_full.json` | — | — |
| Reel plan (финальный) | `artifacts` row kind=reel_plan | `data/artifacts/<job>/text/reel_plan.json` | — | — |
| Story script (bottom_up, удаляем) | — | `data/artifacts/<job>/text/story_script.json` | — | — |
| Rhythm report (bottom_up, удаляем) | — | `data/artifacts/<job>/text/rhythm_report.json` | — | — |
| Reel output (финальные рилсы) | `artifacts` row kind=reel_output | — | `data/artifacts/<job>/reels/r*.mp4` | — |
| Subtitle files | — | — | `data/artifacts/<job>/subs/r*.ass` (rendered) | — |
| Audio extract | — | — | `data/artifacts/<job>/audio/source.wav` | — |
| Proxy (downscaled) | `artifacts` row kind=proxy | — | `data/proxies/<sha>__<id>.mp4` | content-addressed cache |
| Vision cache (per-frame embeddings) | — | — | `data/vision_cache/<sha>/*` | Moondream2 cache |
| Face cache (MediaPipe keyframes) | — | — | `data/face_cache/<uuid>/*` | — |
| Thumbnails | — | — | `data/thumbnails/<uuid>/*.jpg` | per-job |
| ML models | — | — | `data/models/moondream2/*` | 3.5 GB |
| Settings (brand kit) | ??? | сейчас **нет** — раскидано по api/routes/settings.py + RuntimeSettings | — | — |
| Settings (performance) | `runtime_settings` (EAV) | — | — | — |
| Settings (vision) | `runtime_settings` (EAV, префикс `vision_*`) | — | — | — |
| Settings (subtitles) | `subtitle_style_presets` | — | — | — |
| Settings (post-production) | `post_production_presets` | — | — | — |
| Settings (prompts) | `prompt_settings` | — | — | — |
| Settings (models/connections) | — | — | — | `.env` |
| Video assets (intro/outro) | `video_assets` | — | `data/post_production_assets/<id>__<name>.mp4` | — |
| Publer accounts | `account_profiles` | — | — | Publer API via `.env::PUBLER_API_KEY` |
| Publer caption presets | `caption_presets` | — | — | — |
| Publer campaigns | `schedule_campaigns` | — | — | — |
| Publer assignments | `schedule_assignments` | — | — | — |
| Liked reels (preference_memory, удаляется) | `artifacts.meta::liked=like` + `artifacts.embedding_json` (256-dim) | `data/artifacts/<job>/text/reel_plan.json` | — | — |
| Logs | — | — | `data/logs/` **пусто, нужна настройка в REFACTR-59** | — |
| Secrets | — | — | — | `.env` (26 keys) |

---

## 6. Предварительный дизайн project-snapshot (для ADR REFACTR-08)

### 6.1. Целевая схема таблицы `projects` (REFACTR-14)

```python
class ProjectRow(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    color: Mapped[str] = mapped_column(String(16), nullable=False, default="#6366f1")

    #: Путь к файлу-снепшоту настроек на момент создания / последнего сейва.
    #: Относительный от data/projects/<id>/settings_snapshot.json.
    #: JSON содержит: performance, vision, post_production_config, subtitle_style,
    #: prompts (референсы ключей), brand_kit. Позволяет повторить pipeline
    #: даже после глобальных изменений в /settings/*.
    settings_snapshot_path: Mapped[str | None] = mapped_column(String(512), nullable=True)

    #: Состояние pipeline-стадий: {"ingest": "done", "analysis": "running", "render": "pending"}.
    #: Используется кнопкой "Начать заново с шага" (REFACTR-16).
    stage_progress: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    #: Timestamp soft-delete. NULL = активен. DATETIME = помечен к удалению,
    #: физически живёт ещё 30 дней до hard-delete.
    soft_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    #: Timestamp последнего успешного автосейва (REFACTR-15, debounce 10 сек).
    last_saved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    #: Reference к проекту-источнику настроек при duplicate-from (copy-from в task.md §2.4).
    #: NULL = проект создан "с нуля". int = клонирован из project_id.
    #: ON DELETE SET NULL — если родитель удалён, клон остаётся независимым.
    parent_project_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )

    #: Путь к source video. Для single-upload проекта. NULL если проект без видео
    #: (например, только настройки для копирования).
    source_upload_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now
    )
```

**Индексы:** `(soft_deleted_at)` для фильтрации активных проектов, `(parent_project_id)` для обратной связи.

### 6.2. Snapshot JSON-формат (`data/projects/<id>/settings_snapshot.json`)

```json
{
  "version": 1,
  "taken_at": "2026-04-24T14:22:00Z",
  "performance": {
    "narrative_mode": "viral_2026",
    "llm_tier_profile": "fast",
    "reel_target_duration_sec": 40.0,
    "pipeline_llm_provider": "gemini",
    /* ... остальные PerformanceSettings поля после ампутации PRO */
  },
  "vision": {
    "enabled": true,
    "profile_override_talking_head": {"face_centered": true, ...}
  },
  "post_production": {
    "preset_id": 1,
    "preset_snapshot": { /* PostProductionConfig снимок */ }
  },
  "subtitle_style": {
    "preset_id": 3,
    "style_snapshot": { /* SubtitleStyle */ }
  },
  "prompts": {
    "kartoziya_extract_core": { "hash": "sha256:...", "used_at": "2026-04-24T14:22:00Z" }
    /* референсы на prompt_settings keys, не полный контент */
  },
  "brand_kit": { "logo_path": null, "colors": {...} }
}
```

### 6.3. Stage progress JSON

```json
{
  "ingest": {
    "status": "done",
    "started_at": "2026-04-24T14:20:00Z",
    "finished_at": "2026-04-24T14:21:30Z",
    "substages": {"probe": "done", "proxy": "done", "transcribe": "done", "translate": "skipped", "silence_cut": "done"}
  },
  "analysis": {
    "status": "running",
    "started_at": "2026-04-24T14:21:31Z",
    "substages": {"compression": "done", "canvas": "done", "viral_2026": "running"}
  },
  "render": {"status": "pending"}
}
```

### 6.4. Migration risk

`projects` содержит **0 записей** → миграция REFACTR-14 полностью безопасна: только `add_column` (4 nullable поля + 1 JSON NOT NULL default) без backfill. Downgrade (если понадобится) — `drop_column` всех добавленных.

---

## 7. GATE-чекпоинт (REFACTR-04)

- [x] Все модели SQLAlchemy перечислены: **12 прикладных таблиц** в 4 ORM-файлах.
- [x] История Alembic-миграций зафиксирована: 18 ревизий, линейная цепочка, HEAD `eb6d1b814c95`, add-only.
- [x] Количество записей в реальной БД известно: jobs=50, artifacts=725, runtime_settings=87, projects=0 (!) — нулевой migration risk для расширения Project.
- [x] Файловое хранилище описано: 36 GB (uploads 15 + proxies 9.7 + artifacts 6.9 + models 3.5 + caches 345 MB); `data/logs/` **пусто** — требует настройки в REFACTR-59.
- [x] Предварительный дизайн snapshot предложен: 5 новых полей в `ProjectRow` + JSON-формат `settings_snapshot.json` + `stage_progress`.

---

## 8. Следующий чанк

**REFACTR-05** — Pipeline stages: детализировать три фазы (`ingest`, `analysis`, `render`) и внутренние sub-stages для кнопки «Начать заново с шага» (REFACTR-16 / REFACTR-49).
