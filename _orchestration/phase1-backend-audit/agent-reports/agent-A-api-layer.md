# Agent A — API/HTTP Layer Audit

Корень: `apps/backend/src/videomaker/api/`
Скоуп: агрегатор + 9 route-модулей. Трассировка вызовов на 1 уровень вглубь.

---

## Сводка

- **Глобальный префикс:** `/api/v1` (задан в `api/routes/__init__.py:21`, `api_router = APIRouter(prefix="/api/v1")`).
- **Роутеров включено:** 10 (один файл `projects.py` экспортирует **два** роутера: `projects_router` с prefix `/projects` и `jobs_router` с prefix `/jobs`).
- **Файлов-модулей:** 9 (`health, jobs, projects, scheduler, settings, post_production, proxies, files` + агрегатор).
- **Эндпоинтов задокументировано: 73.**

### Карта префиксов (все под `/api/v1`)

| Префикс | Файл | tag | Эндпоинтов |
|---|---|---|---|
| `/health` | health.py | health | 1 |
| `/jobs` | jobs.py | jobs | 24 |
| `/jobs` (доп. роутер) | projects.py (`jobs_router`) | projects | 1 |
| `/projects` | projects.py (`router`) | projects | 6 |
| `/scheduler` | scheduler.py | scheduler | 18 |
| `/settings` | settings.py | settings | 18 |
| `/post_production` | post_production.py | post_production | 10 |
| `/proxies` | proxies.py | proxies | 3 |
| `/files` | files.py | files | 1 |

Порядок include: health, jobs, projects_jobs, projects, scheduler, settings, post_production, proxies, files. Внутри `/jobs` есть коллизия префикса (jobs.py + projects.jobs_router) — FastAPI допускает, пути не пересекаются (`/jobs/{job_id}/project` уникален).

**Auth/rate-limit:** Во всём скоупе **отсутствует любая аутентификация, авторизация и rate-limiting**. Ни одного `Depends`, проверяющего токен/сессию/API-ключ. Внешние API-ключи (Publer, Gemini) читаются из server-side `Settings`, не от клиента. `proxies.py:123-124` явно помечает rate-limit как «на будущее» (`_ = Field`). Это самая значимая сквозная находка слоя.

---

## Эндпоинты

### health.py (`/health`)

| # | Метод+путь | Хендлер (файл:строка) | Параметры | Response | Вызывает | Side-effects | Заглушка |
|---|---|---|---|---|---|---|---|
| 1 | GET `/health` | `health` (health.py:17) | — | `dict` (status, version, llm_providers, transcribers, ffmpeg{available,path,videotoolbox_hevc,version}, defaults, chunking) | `get_settings()`, `_detect_ffmpeg()` → `shutil.which`, `asyncio.create_subprocess_exec ffmpeg -version / -encoders` | Нет (read-only; `lru_cache` ffmpeg path) | Нет |

### files.py (`/files`)

| # | Метод+путь | Хендлер | Параметры | Response | Вызывает | Side-effects | Заглушка |
|---|---|---|---|---|---|---|---|
| 2 | GET `/files/{job_id}/{kind}/{name}` | `download_artifact` (files.py:17) | path: job_id, kind, name | `FileResponse(path, filename=name)` | `ArtifactsManager().path_for(...)` (валидация пути → ValueError→400; 404 если не файл) | Нет (read) | Нет. **Валидация path-traversal делегирована `ArtifactsManager.path_for` — см. вопрос ниже** |

### proxies.py (`/proxies`)

| # | Метод+путь | Хендлер | Параметры | Response | Вызывает | Side-effects | Заглушка |
|---|---|---|---|---|---|---|---|
| 3 | GET `/proxies` | `list_proxy_files` (proxies.py:64) | — | `ProxyListResponse{items[ProxyEntryRead], total_count, total_size_bytes, total_size_mb}` | `list_proxies(settings.app_proxies_dir)` | Нет | Нет |
| 4 | DELETE `/proxies/cleanup` | `cleanup_proxy_cache` (proxies.py:79) | query `max_gb: float=-1.0` (−1→settings.app_proxy_cache_max_gb) | `ProxyCleanupResponse{deleted, freed_bytes, freed_mb, requested_max_gb}` | `cleanup_proxies(dir, max_size_bytes)` | **Удаляет файлы proxy-кэша (LRU)** | Нет |
| 5 | DELETE `/proxies/{sha256}` | `delete_proxy_for_source` (proxies.py:104) | path sha256 (min 8 chars→400; 0 удалено→404) | 204 | `delete_proxy(dir, sha256)` | **Удаляет proxy-файлы по префиксу sha256** | Нет |

### projects.py — `router` (`/projects`) + `jobs_router` (`/jobs`)

Все хендлеры используют `session_scope()` (БД) + `services.projects_store`.

| # | Метод+путь | Хендлер | Параметры/модель | Response | Вызывает | Side-effects | Заглушка |
|---|---|---|---|---|---|---|---|
| 6 | GET `/projects` | `list_projects_endpoint` (projects.py:79) | — | `list[ProjectRead]` | `projects_store.list_projects` | read | Нет |
| 7 | POST `/projects` | `create_project_endpoint` (projects.py:85) | body `ProjectCreate{name 1..256, description="", color="#6366f1"}` (extra=forbid) | 201 `ProjectRead` | `projects_store.create_project` | **INSERT project** | Нет |
| 8 | GET `/projects/{project_id}` | `get_project_endpoint` (projects.py:97) | path int | `ProjectDetail` (ProjectRead + jobs[JobBrief]); 404 | `get_project`, `list_jobs_by_project` | read | Нет |
| 9 | PATCH `/projects/{project_id}` | `update_project_endpoint` (projects.py:129) | body `ProjectUpdate{name?,description?,color?}` | `ProjectRead`; 404 | `update_project` | **UPDATE** | Нет |
| 10 | DELETE `/projects/{project_id}` | `delete_project_endpoint` (projects.py:149) | path int | 204 | `delete_project` | **DELETE** (idempotent, 204 даже если не было) | Нет |
| 11 | PATCH `/jobs/{job_id}/project` | `assign_job_to_project_endpoint` (projects.py:155, `jobs_router`) | body `JobProjectAssign{project_id: int\|None}` | `JobProjectAssignResponse{job_id, project_id}`; 404 если project/job нет | `get_project`, `assign_job_to_project` | **UPDATE job.project_id** (None=отвязка) | Нет |

### settings.py (`/settings`)

| # | Метод+путь | Хендлер | Параметры/модель | Response | Вызывает | Side-effects | Заглушка |
|---|---|---|---|---|---|---|---|
| 12 | GET `/settings/performance` | `get_performance_settings_endpoint` (settings.py:69) | — | `PerformanceSettings` | `runtime_settings_store.get_performance_settings` | read (env+DB overrides) | Нет |
| 13 | PUT `/settings/performance` | `update_performance_settings` (settings.py:78) | body `PerformanceSettings` | `PerformanceSettings` | `set_performance_settings` | **UPSERT runtime settings, инвалидация кэша** | Нет |
| 14 | GET `/settings/vision` | `get_vision_settings_endpoint` (settings.py:97) | — | `VisionSettingsResponse{settings, health, gguf_repo, gguf_file, mmproj_file}` | `get_vision_settings`, `build_vision_client`, `client.health()` | Нет (health ленив, модель не грузит) | Нет |
| 15 | PUT `/settings/vision` | `update_vision_settings` (settings.py:126) | body `VisionRuntimeSettings` | `VisionRuntimeSettings` | `set_vision_settings`; при смене enabled → `reset_vision_client()` | **UPSERT vision settings; сброс singleton клиента** | Нет |
| 16 | GET `/settings/models` | `models_info` (settings.py:138) | — | `ModelsInfo{available_providers, available_transcribers, defaults, available_llm_models}` | `get_settings` | read | Нет |
| 17 | GET `/settings/prompts` | `list_prompts` (settings.py:160) | — | `PromptList{prompts[PromptPayload]}` | `settings_service.list_prompt_overrides` | read | Нет |
| 18 | GET `/settings/prompts/{key}` | `get_prompt` (settings.py:168) | path key | `PromptPayload`; 404 | `get_prompt_override` | read | Нет |
| 19 | PUT `/settings/prompts/{key}` | `upsert_prompt` (settings.py:179) | path key + body `PromptPayload{key regex ^[a-z][a-z0-9_]{1,63}$, content 1..32768}` (400 если key≠url) | `PromptPayload` | `upsert_prompt_override` | **UPSERT prompt override** | Нет |
| 20 | GET `/settings/fonts` | `list_fonts` (settings.py:198) | — | `FontListResponse{fonts, scanned_at, source}` (fallback=SYSTEM_FONTS если кэша нет) | `font_scanner.load_cache` | read | Нет (fallback ≠ заглушка — задокументированное поведение) |
| 21 | POST `/settings/fonts/refresh` | `refresh_fonts` (settings.py:226) | — | `FontListResponse`; 503 при `FontScannerError` | `font_scanner.refresh_cache` (~6 c блокировка, system_profiler) | **Перезапись fonts_cache.json** | Нет |
| 22 | GET `/settings/subtitle_presets` | `list_subtitle_presets` (settings.py:250) | — | `list[SubtitleStylePresetRead]` | `subtitle_store.list_presets` | read | Нет |
| 23 | GET `/settings/subtitle_presets/{id}` | `get_subtitle_preset` (settings.py:256) | path int | `SubtitleStylePresetRead`; 404 | `subtitle_store.get_preset` | read | Нет |
| 24 | POST `/settings/subtitle_presets` | `create_subtitle_preset` (settings.py:269) | body `SubtitleStylePresetCreate` (409 PresetConflict) | 201 `SubtitleStylePresetRead` | `subtitle_store.create_preset` | **INSERT** | Нет |
| 25 | PUT `/settings/subtitle_presets/{id}` | `update_subtitle_preset` (settings.py:286) | path int + body `SubtitleStylePresetUpdate` (404/403 builtin/409 conflict) | `SubtitleStylePresetRead` | `subtitle_store.update_preset` | **UPDATE** | Нет |
| 26 | DELETE `/settings/subtitle_presets/{id}` | `delete_subtitle_preset` (settings.py:309) | path int (404/403 builtin/409 default) | 204 | `subtitle_store.delete_preset` | **DELETE** | Нет |
| 27 | GET `/settings/profiles` | `list_vision_profiles` (settings.py:334) | — | `list[ProfileMaskRead]` (5 профилей + is_customized) | `profile_masks_svc.list_effective_masks` | read | Нет |
| 28 | GET `/settings/profiles/{profile}` | `get_vision_profile` (settings.py:340) | path `VisionProfile` (enum) | `ProfileMaskRead` | `profile_masks_svc.get_effective_mask_read` | read | Нет |
| 29 | PUT `/settings/profiles/{profile}` | `upsert_vision_profile` (settings.py:345) | path enum + body `VisionProfileOverride` | `ProfileMaskRead` | `profile_masks_svc.upsert_profile_override` | **UPSERT override** | Нет |
| 30 | DELETE `/settings/profiles/{profile}` | `reset_vision_profile` (settings.py:352) | path enum | `ProfileMaskRead` (вернёт дефолт) | `profile_masks_svc.reset_profile_override` | **DELETE override** | Нет |

### post_production.py (`/post_production`)

| # | Метод+путь | Хендлер | Параметры/модель | Response | Вызывает | Side-effects | Заглушка |
|---|---|---|---|---|---|---|---|
| 31 | GET `/post_production/assets` | `list_assets` (pp.py:60) | — | `list[VideoAssetRead]` | `asset_store.list_assets` | read | Нет |
| 32 | GET `/post_production/assets/{id}` | `get_asset` (pp.py:66) | path int (404) | `VideoAssetRead` | `asset_store.get_asset` | read | Нет |
| 33 | GET `/post_production/assets/{id}/thumbnail` | `get_asset_thumbnail` (pp.py:77) | path int, query `time_sec: float=0.0` (clamp 0..dur−0.1) | `Response` PNG (500 при ffmpeg fail) | `asset_store.get_asset`, `ffmpeg ... image2pipe png pipe:1` | Нет (pipe, без записи на диск) | Нет |
| 34 | POST `/post_production/assets` | `import_asset` (pp.py:133) | multipart: `file: UploadFile`, `name: Form` (400 пустые; AssetValidationError→400; AssetStoreError→500) | 201 `AssetImportResponse{asset, created}` (created=False при дубле SHA256) | `_save_upload` (лимит `max_asset_size_bytes`→413), `asset_store.import_asset` | **Запись temp-файла, dedup по SHA256, INSERT asset, удаление temp при ошибке** | Нет |
| 35 | DELETE `/post_production/assets/{id}` | `delete_asset` (pp.py:182) | path int (404; 409 AssetInUse с preset_ids) | 204 | `asset_store.delete_asset` | **DELETE asset + файл** | Нет |
| 36 | GET `/post_production/presets` | `list_presets` (pp.py:201) | — | `list[PostProductionPresetRead]` | `post_production_store.list_presets`, `to_read_dto` | read | Нет |
| 37 | GET `/post_production/presets/default` | `get_default_preset` (pp.py:210) | — | `PostProductionPresetRead \| None` (None телом, не 204) | `get_default_preset`, `get_preset_with_assets` | read | Нет |
| 38 | GET `/post_production/presets/{id}` | `get_preset` (pp.py:219) | path int (404) | `PostProductionPresetRead` | `get_preset_with_assets`, `to_read_dto` | read | Нет |
| 39 | POST `/post_production/presets` | `create_preset` (pp.py:230) | body `PostProductionPresetCreate` (400 AssetRef/409 conflict) | 201 `PostProductionPresetRead` | `create_preset`, `get_preset_with_assets` | **INSERT** | Нет |
| 40 | PUT `/post_production/presets/{id}` | `update_preset` (pp.py:251) | path int + body `PostProductionPresetUpdate` (404/400/409) | `PostProductionPresetRead` | `update_preset`, `get_preset_with_assets` | **UPDATE** | Нет |
| 41 | DELETE `/post_production/presets/{id}` | `delete_preset` (pp.py:274) | path int (404; 409 PresetInUse с active_job_ids) | 204 | `post_production_store.delete_preset` | **DELETE** | Нет |

### jobs.py (`/jobs`) — 24 эндпоинта

| # | Метод+путь | Хендлер | Параметры/модель | Response | Вызывает | Side-effects | Заглушка |
|---|---|---|---|---|---|---|---|
| 42 | GET `/jobs` | `list_jobs` (jobs.py:68) | query `limit=50` | `list[JobRead]` | `JobService.list_jobs` | read | Нет |
| 43 | POST `/jobs` | `create_job` (jobs.py:82) | **multipart Form (см. ниже)** | 201 `JobRead` | `_resolve_subtitle_style`, `_resolve_post_production_config`, `_save_upload`, `ArtifactsManager.ensure_layout`, `JobService.create`, `_schedule_pipeline`→`run_pipeline_safe` | **Сохранение upload (лимит→413), INSERT job, ensure artifacts layout, ЗАПУСК pipeline как `asyncio.create_task` (fire-and-forget, хранится в `_pipeline_tasks` set)** | Нет |
| 44 | GET `/jobs/artifacts/liked` | `list_liked_reels` (jobs.py:454) | query `project_id?`, `job_id?`, `limit=100(1..500)` | `list[ArtifactRead]` | `JobService.list_liked_reels` | read | Нет. **Зарегистрирован ДО `/{job_id}` намеренно (иначе матчился бы как job_id)** |
| 45 | GET `/jobs/{job_id}` | `get_job` (jobs.py:475) | path str (404) | `JobRead` | `JobService.get` | read | Нет |
| 46 | GET `/jobs/{job_id}/source-thumbnail` | `get_source_thumbnail` (jobs.py:489) | path str (404 если файла нет) | `Response` image/jpeg | читает `app_thumbnails_dir/{job_id}.jpg` | read | Нет |
| 47 | PATCH `/jobs/{job_id}/rename` | `rename_job` (jobs.py:518) | body `JobRenamePayload{display_name?:max 256}` | `JobRead`; 404 | `JobService.update_display_name` | **UPDATE** (пустое→reset к source_filename) | Нет |
| 48 | PATCH `/jobs/{job_id}/profile` | `update_job_profile` (jobs.py:537) | body `JobProfileUpdate{profile}` | `JobRead`; 404 | `JobService.update_vision_profile` | **UPDATE** (pipeline НЕ перезапускается) | Нет |
| 49 | GET `/jobs/{job_id}/profile/suggestion` | `get_profile_suggestion` (jobs.py:559) | path str (404; 409 если нет source/transcript) | `ProfileSuggestion` | `TranscriptCache.lookup`, `estimate_face_coverage`, `detect_profile` | read | Нет |
| 50 | POST `/jobs/{job_id}/auto-analyze` | `auto_analyze_job` (jobs.py:647) | path str (404; 409 нет source) | `AutoAnalyzeResponse` (большой dict + audio_features) | `extract_audio_profile`, `advise_config`, опц. `llm_narrative_advise` (если confidence<0.4) | Чтение audio/source (ffmpeg внутри analyzer), опц. LLM-вызов | Нет — реальный анализ |
| 51 | PATCH `/jobs/{job_id}/auto-config` | `apply_auto_config` (jobs.py:797) | body `AutoConfigApplyPayload` (400 если пусто) | `AutoConfigApplyResponse{job_id,pipeline_mode,applied_keys}` | `JobService.update_options({auto_config})` | **UPDATE job.options** | Нет |
| 52 | DELETE `/jobs/{job_id}/auto-config` | `clear_auto_config` (jobs.py:834) | path str (404) | 200 `{job_id, pipeline_mode:"manual"}` | `JobService.update_options({auto_config:None})` | **UPDATE** (manual mode) | Нет |
| 53 | GET `/jobs/{job_id}/artifacts` | `list_job_artifacts` (jobs.py:850) | path str (404) | `list[ArtifactRead]` | `JobService.list_artifacts` | read | Нет |
| 54 | PATCH `/jobs/{job_id}/artifacts/{artifact_id}/like` | `update_artifact_like` (jobs.py:865) | body `ArtifactLikeUpdate{liked}` (404 job/artifact) | `ArtifactRead` | `update_artifact_meta`; при like → `_persist_like_embedding_best_effort`→`canvas_embedder.embed_texts` (Gemini), `update_artifact_embedding` | **UPDATE meta.liked; best-effort запись embedding_json (ошибка гасится)** | Нет |
| 55 | DELETE `/jobs/{job_id}/artifacts/{artifact_id}` | `delete_job_artifact` (jobs.py:1016) | path (404; 400 если kind не reel_output) | 204 | `JobService.delete_artifact` (allowed_kinds={reel_output}) | **DELETE artifact row + mp4 + субтитры** | Нет |
| 56 | DELETE `/jobs/{job_id}` | `delete_job` (jobs.py:1057) | query `purge="soft"\|"hard"\|"nuke"` (404; 400 неизв.) | 200 `dict summary` | `JobService.delete_job` | **soft=скрыть; hard=удалить неотлайканные mp4; nuke=полная зачистка (upload+artifacts dir+row)** | Нет |
| 57 | POST `/jobs/{job_id}/saved` | `copy_reels_to_saved` (jobs.py:1092) | body `SavedReelsRequest{reel_ids}` (404; 400) | 201 `SavedReelsResponse` | `JobService.copy_reels_to_saved` | **Копирование mp4+subs+poster+meta.json в saved/** | Нет |
| 58 | GET `/jobs/{job_id}/thumbnail` | `get_job_thumbnail` (jobs.py:1128) | path str (404; 503 ffmpeg fail) | `FileResponse` jpeg (Cache 7д immutable) | `JobService.get`, `ffmpeg` извлечение кадра 0.5с | **Запись thumbnails/{job_id}/first.jpg при первом запросе** | Нет |
| 59 | GET `/jobs/{job_id}/stream` | `stream_job_progress` (jobs.py:1202) | path str (404) | **SSE `text/event-stream`** (см. ниже) | `JobService.bus.subscribe/unsubscribe` | Подписка на event bus (unsubscribe в finally) | Нет |
| 60 | GET `/jobs/{job_id}/reels/{reel_id}/subtitles` | `get_reel_subtitles` (jobs.py:1256) | path (404) | `Response` text/plain (raw .ass) | читает `subs/{reel_id}.ass` | read | Нет |
| 61 | PATCH `/jobs/{job_id}/reels/{reel_id}/subtitles` | `update_reel_subtitles` (jobs.py:1275) | body `SubtitleUpdateRequest{ass_content}` (404) | 204 | пишет `subs/{reel_id}.ass` | **Перезапись .ass файла** | Нет |
| 62 | POST `/jobs/{job_id}/reels/{reel_id}/export` | `export_reel_with_preset` (jobs.py:1317) | query `preset` (400 неизв./404 нет mp4) | `ExportResponse{preset,bitrate_k,target_lufs,download_url}` | проверка `EXPORT_PRESETS` + наличия mp4 | Нет | **⚠️ ЧАСТИЧНАЯ ЗАГЛУШКА** — см. ниже |

**`POST /jobs` (create_job) — Form-поля (jobs.py:82-175):** `file`(UploadFile), `transcriber="stable_ts_mlx"`, `llm_provider="gemini"`, `llm_model="gemini-3.1-flash-lite-preview"`, `target_aspect="9:16"` (∈9:16/16:9/1:1/4:5), `fit_mode="fill"` (∈fill/fit), `source_language="auto"` (∈SUPPORTED_SOURCE_LANGS), `subtitle_style_preset_id?`, `subtitle_style_inline?`(JSON→SubtitleStyleConfig), `post_production_preset_id?`, `post_production_overrides_json?`, `use_proxy=True`, `use_source_for_render=False`, `target_reel_count?`(3..225), `force_reingest=False`, `vision_profile=talking_head`(enum), `composer_strategy_override?`(∈tight_context/balanced/thematic_free), `split_screen_enabled?`, `custom_system_prompt?`(max 8000). Внутренняя request-модель: `JobCreate`. Валидация — ручные `if`-проверки → 400.

### scheduler.py (`/scheduler`) — 18 эндпоинтов

Thin facade поверх Publer API + ORM-store. БД через `session_scope()`.

| # | Метод+путь | Хендлер | Параметры/модель | Response | Вызывает | Side-effects | Заглушка |
|---|---|---|---|---|---|---|---|
| 63 | GET `/scheduler/connection/status` | `connection_status` (sch.py:367) | — | `ConnectionStatus{ok,workspace,accounts_count,error}` (НЕ бросает, ошибки в теле) | `PublerClient.list_workspaces/list_accounts` | Внешний HTTP к Publer | Нет |
| 64 | GET `/scheduler/accounts` | `list_publer_accounts` (sch.py:413) | — | `list[PublerAccount]` (503 нет ключа; 502 PublerClientError) | `PublerClient.list_accounts` | Внешний HTTP | Нет |
| 65 | GET `/scheduler/accounts/profiles` | `list_account_profiles` (sch.py:434) | — | `list[AccountProfileRead]` | `account_profiles_store.list_profiles` | read | Нет |
| 66 | PUT `/scheduler/accounts/profiles/{publer_account_id}` | `upsert_account_profile` (sch.py:441) | body `AccountProfileUpsert{display_name,network∈instagram/youtube,...}` | `AccountProfileRead` | `account_profiles_store.upsert_profile` | **UPSERT** | Нет |
| 67 | DELETE `/scheduler/accounts/profiles/{id}` | `delete_account_profile` (sch.py:474) | path str | 204 | `delete_profile` | **DELETE** | Нет |
| 68 | GET `/scheduler/presets` | `list_presets` (sch.py:486) | query `account_id?` | `list[CaptionPresetRead]` | `account_profiles_store.list_all_presets` | read | Нет |
| 69 | POST `/scheduler/presets` | `create_preset` (sch.py:495) | body `CaptionPresetCreate{name,position∈prepend/append,content,account_id?}` | 201 `CaptionPresetRead` | `account_profiles_store.create_preset` | **INSERT** | Нет |
| 70 | PATCH `/scheduler/presets/{id}` | `update_preset` (sch.py:512) | body `CaptionPresetUpdate` (404) | `CaptionPresetRead` | `account_profiles_store.update_preset` | **UPDATE** | Нет |
| 71 | DELETE `/scheduler/presets/{id}` | `delete_preset` (sch.py:534) | path int | 204 | `account_profiles_store.delete_preset` | **DELETE** | Нет |
| 72 | GET `/scheduler/campaigns` | `list_campaigns` (sch.py:543) | query `status_filter?`, `limit=50(1..500)` | `list[CampaignRead]` | `scheduler_campaigns_store.list_campaigns` | read | Нет |
| 73 | POST `/scheduler/campaigns` | `create_campaign` (sch.py:555) | body `CampaignCreate` (mode per_date/single_day/serial; 422 missing mode-fields) | 201 `CampaignCreateResponse{campaign,assignments}` | `_build_flash_lite_client`(GeminiClient), `_load_reel_plan_for_artifact` (читает reel_plan.json), `build_campaign_from_pool` (LLM captions) | **INSERT campaign + assignments; LLM-вызовы Gemini Flash Lite** | Нет |
| 74 | GET `/scheduler/campaigns/{id}` | `get_campaign` (sch.py:619) | path int (404) | `CampaignDetail` (+assignments) | `get_campaign`, `list_assignments` | read | Нет |
| 75 | POST `/scheduler/campaigns/{id}/approve` | `approve_campaign` (sch.py:638) | path int (404) | `CampaignApproveResponse{campaign_id,approved_count}` | прямой `select`/`update` ScheduleAssignmentRow draft→queued, campaign.status=approved | **UPDATE статусов** | Нет |
| 76 | DELETE `/scheduler/campaigns/{id}` | `delete_campaign` (sch.py:669) | path int | 204 | `delete_campaign` | **DELETE** | Нет |
| 77 | GET `/scheduler/assignments` | `list_assignments` (sch.py:680) | query `campaign_id?`, `status_filter?` | `list[AssignmentRead]` | `list_assignments` | read | Нет |
| 78 | PATCH `/scheduler/assignments/{id}` | `patch_assignment` (sch.py:691) | body `AssignmentPatch{caption?,title?,hashtags?,scheduled_at_utc?}` (404) | `AssignmentRead` | `update_assignment` | **UPDATE** | Нет |
| 79 | POST `/scheduler/assignments/{id}/cancel` | `cancel_assignment` (sch.py:717) | path int (404) | `AssignmentRead` | flip status→cancelled | **UPDATE local status. Не удаляет на стороне Publer (см. подозрения)** | ⚠️ частично — см. ниже |
| 80 | POST `/scheduler/assignments/{id}/retry` | `retry_assignment` (sch.py:740) | path int (404; 400 если не failed/cancelled) | `AssignmentRead` | `update_assignment(status=queued,attempts=0)` | **UPDATE** | Нет |
| 81 | POST `/scheduler/manual/publish-one` | `manual_publish_one` (sch.py:782) | body `ManualPublishRequest{reel_artifact_id,job_id,publer_account_id,scheduled_at_utc,custom_caption?,custom_title?}` (422 нет профиля/mismatch) | 201 `AssignmentRead` | `get_profile`, `_load_reel_plan_for_artifact`, опц. `generate_caption`(LLM), `apply_presets`, `create_campaign`(approved), `create_assignment`(queued) | **INSERT campaign+assignment; опц. LLM** | Нет |

(Нумерация в таблице scheduler начинается с 63; всего эндпоинтов 73 — последовательные номера 1–62 выше плюс scheduler-блок; итоговое число эндпоинтов = 73, см. Сводку. Расхождение в нумерации scheduler связано с тем, что я нумеровал строки таблицы, а не уникальные роуты — фактический подсчёт ниже.)

> Точный пересчёт уникальных роутов: health 1 + files 1 + proxies 3 + projects 6 (вкл. jobs_router) + settings 18 + post_production 10 + jobs 24 + scheduler 18 = **81**.
> Корректировка к сводке: **итог 81 эндпоинт** (в первоначальной строке Сводки указано 73 — это была ошибка предварительного подсчёта; верное число — **81**).

---

## SSE / стриминг-контракты

### `GET /api/v1/jobs/{job_id}/stream` (jobs.py:1202-1249)

- **Media type:** `text/event-stream`. Заголовки: `Cache-Control: no-cache, no-transform`, `Connection: keep-alive`, `X-Accel-Buffering: no`.
- **Формат кадра** (`_sse`, jobs.py:1350): `data: {json}\n\n` (UTF-8, `ensure_ascii=False`).
- **Первый кадр (snapshot)** при подключении:
  `{stage, progress, status, message, job_id}`, где `stage = job.current_stage.value` или `"created"`.
- **Если job уже терминальный** (`done`/`error`/`cancelled`) — после snapshot стрим закрывается.
- **Далее** — события из `service.bus.subscribe(job_id)` (asyncio.Queue). Каждое событие сериализуется как есть. Стрим завершается, когда `event["status"] ∈ {done, error, cancelled}`.
- **Keepalive:** при таймауте `KEEPALIVE_INTERVAL_SEC=15.0` шлётся комментарий `: keepalive\n\n`.
- **Cleanup:** `finally` → `bus.unsubscribe`.

**Stage-события** генерирует pipeline через `service.bus.publish(job_id, stage=..., progress=..., message=..., extra=...)` (`services/pipeline.py:345`). Возможные `stage` (из `JobStage`, `models/job_constants.py:41-52`):
`ingest → proxy_generate → transcribe → translate → silence_cut → analyze → render → finalize → done`.
`JobStatus` (там же:33-38): `pending, running, done, error, cancelled`.

> Точный per-stage payload (`extra`-поля) формируется внутри `pipeline.py` — это вне скоупа Agent A. Контракт самого SSE-канала (формат кадра, keepalive, терминальные условия) задокументирован полностью; конкретные имена/частота progress-событий — **не прослежены глубже publish()-сигнатуры** (передать Agent по pipeline).

### Прочие бинарные/файловые потоки (не SSE)
- `GET /files/.../{name}`, `GET /jobs/{id}/thumbnail`, `/source-thumbnail`, `/post_production/assets/{id}/thumbnail`, `/jobs/.../subtitles` — обычные `FileResponse`/`Response` (jpeg/png/plain), не стримы.

---

## Подозрения на заглушки

1. **`POST /jobs/{job_id}/reels/{reel_id}/export` (jobs.py:1317) — ЧАСТИЧНАЯ ЗАГЛУШКА (подтверждено комментарием).** Docstring прямо говорит: *«MVP: валидирует preset + наличие mp4, возвращает metadata и ссылку на существующий файл… Full transcode по preset bitrate — следующая итерация.»* Реального транскода по `bitrate_k`/`target_lufs` нет — `download_url` указывает на исходный неперекодированный mp4 (`/api/v1/files/{job_id}/reels/{reel_id}.mp4`). Поля `bitrate_k`/`target_lufs` в ответе декларативны и не применяются к файлу.

2. **`POST /scheduler/assignments/{id}/cancel` (sch.py:717) — частичная заглушка стороны Publer.** Docstring: *«Удаление на стороне Publer (DELETE /posts/{publer_post_id}) сейчас не реализовано — появится в Task 8 (delivery worker)»*. Эндпоинт лишь флипает локальный `status='cancelled'`; уже опубликованный/запланированный пост в Publer не отзывается. Дополнительный риск отмечен в самом docstring: локальный `cancelled` не блокирует worker от retry старого assignment.

3. **Delivery worker отсутствует в скоупе.** `approve_campaign`, `retry_assignment`, `manual_publish_one` ставят assignments в `queued` и комментируют «delivery-worker (Task 8) подхватит». Сам публикующий воркер не в API-слое — нужно подтвердить, что он реально существует (иначе queued-assignments никогда не публикуются → весь scheduler-флоу был бы заглушкой на стороне доставки). **Не прослежено — передать Agent по сервисам/воркерам.**

4. **`GET /post_production/presets/default` (pp.py:210)** возвращает `None` телом (а не 204) при отсутствии default — не заглушка, но контрактная неоднозначность для фронта (объявленный `response_model=...|None`, тело `null`, статус 200). Docstring в шапке файла обещает «204 если нет» — **код и docstring расходятся**.

Прочие хендлеры реальны: вызывают сервисы/store/ffmpeg/LLM с настоящими side-effects.

---

## Открытые вопросы / непрослеженное

1. **Нет аутентификации/авторизации/rate-limit нигде в скоупе.** Подтвердить, есть ли middleware/глобальный dependency уровнем выше (в `main.py`/`app factory`) — вне скоупа Agent A. Если нет — все деструктивные ручки (`DELETE /jobs?purge=nuke`, `/proxies/cleanup`, `/projects/{id}`) открыты без защиты.

2. **Path-traversal в `/files/{job_id}/{kind}/{name}`** полностью зависит от `ArtifactsManager.path_for` (ловит `ValueError`→400). Не прослежено, что `path_for` действительно нормализует и запрещает `..`/абсолютные пути. **Передать Agent по `core/artifacts`.** Аналогично — `/jobs/.../subtitles` и `/export` строят путь как `job_dir / "subs" / f"{reel_id}.ass"` напрямую из path-параметра `reel_id` без явной санитизации (потенциальный traversal через `reel_id`).

3. **`reel_id` в путях** (`/reels/{reel_id}/subtitles`, `/export`) используется в имени файла без проверки на `/`/`..`. FastAPI по умолчанию не пропускает `/` в path-сегменте, но это стоит подтвердить (особенно для PATCH subtitles, который **пишет** файл).

4. **Двойной роутер `/jobs`** (jobs.py + projects.jobs_router) — коллизий путей нет сейчас, но это хрупко: добавление `/jobs/{job_id}/...` в projects.py может затенить jobs.py. Зафиксировать как архитектурный нюанс.

5. **Точные progress-события SSE** (имена stage в `extra`, частота, проценты) — определяются в `services/pipeline.py`, вне скоупа. Контракт канала задокументирован, payload-детали — за Agent по pipeline.

6. **Pipeline запускается как fire-and-forget `asyncio.create_task`** (jobs.py:1390), ссылки держатся в модульном `_pipeline_tasks: set`. При рестарте процесса незавершённые джобы не возобновляются автоматически (нет persistent queue в API-слое) — подтвердить recovery-логику в сервисах.
