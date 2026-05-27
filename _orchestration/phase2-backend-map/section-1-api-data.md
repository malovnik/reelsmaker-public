# Section 1 — API Contract & Data Model

Reference for the videomaker backend (FastAPI). Source of truth: `apps/backend/src/videomaker/`. Frontend may integrate against this without reading backend code.

---

## 1. Overview

### Base URL & versioning
- Global prefix: **`/api/v1`** (set in `api/routes/__init__.py`, `APIRouter(prefix="/api/v1")`).
- App root: `GET /` returns `{name, version, docs:"/docs", health:"/api/v1/health"}`. OpenAPI UI at `/docs`.
- App title `videomaker`, version from `videomaker.__version__`.

### Authentication
**None.** No auth, authorization, or rate-limiting anywhere. No `Depends` checks a token/session/API key. Third-party keys (Publer, Gemini) are read server-side from `Settings`, never from the client. Destructive endpoints (`DELETE /jobs?purge=nuke`, `DELETE /proxies/cleanup`, `DELETE /projects/{id}`) are open. Treat the API as trusted-network / single-user only.

### Error format
Standard FastAPI. Errors are returned as:
```json
{ "detail": "<human-readable message>" }
```
- Validation errors (Pydantic / FastAPI) → **422** with the standard `{"detail":[{loc,msg,type}, ...]}` array.
- Application errors → `HTTPException` with a string `detail` (codes per endpoint table below).
- No custom global exception handlers; no app-wide error envelope beyond FastAPI defaults.

### CORS
Configured via `CORSMiddleware` in `main.py`:
- `allow_origins = [settings.frontend_origin]` — single origin, default `http://localhost:3000` (env-overridable).
- `allow_credentials = True`
- `allow_methods = ["*"]`, `allow_headers = ["*"]`
- `expose_headers = ["Content-Type", "Cache-Control"]`

---

## 2. Endpoint Reference (81 endpoints)

Routers under `/api/v1` (include order: health, jobs, projects_jobs, projects, scheduler, settings, post_production, proxies, files). Note: `projects.py` exports two routers — `router` (`/projects`) and `jobs_router` (`/jobs`); the latter contributes one `/jobs` endpoint that coexists with `jobs.py` without path collision.

| Prefix | File | Tag | Count |
|---|---|---|---|
| `/health` | health.py | health | 1 |
| `/files` | files.py | files | 1 |
| `/proxies` | proxies.py | proxies | 3 |
| `/projects` (+ `/jobs` extra) | projects.py | projects | 6 |
| `/settings` | settings.py | settings | 18 |
| `/post_production` | post_production.py | post_production | 10 |
| `/jobs` | jobs.py | jobs | 24 |
| `/scheduler` | scheduler.py | scheduler | 18 |
| **Total** | | | **81** |

### 2.1 health (`/health`)

| Method+Path | Params | Response | Purpose |
|---|---|---|---|
| GET `/health` | — | `dict`: status, version, llm_providers, transcribers, ffmpeg{available,path,videotoolbox_hevc,version}, defaults, chunking | Service health + capability probe (read-only) |

### 2.2 files (`/files`)

| Method+Path | Params | Response / Codes | Purpose |
|---|---|---|---|
| GET `/files/{job_id}/{kind}/{name}` | path: job_id, kind, name | `FileResponse` (filename=name); 400 invalid path, 404 not file | Download a pipeline artifact. Path-traversal guarded by `ArtifactsManager.path_for` (rejects `..`/escape → 400) |

### 2.3 proxies (`/proxies`)

| Method+Path | Params | Response / Codes | Purpose |
|---|---|---|---|
| GET `/proxies` | — | `ProxyListResponse{items[ProxyEntryRead], total_count, total_size_bytes, total_size_mb}` | List proxy cache files |
| DELETE `/proxies/cleanup` | query `max_gb: float = -1.0` (−1 → `app_proxy_cache_max_gb`) | `ProxyCleanupResponse{deleted, freed_bytes, freed_mb, requested_max_gb}` | LRU cleanup of proxy cache (deletes files) |
| DELETE `/proxies/{sha256}` | path sha256 (min 8 chars → 400; 0 deleted → 404) | 204 | Delete proxy files by sha256 prefix |

### 2.4 projects (`/projects` + `/jobs`)

All handlers use `session_scope()` + `projects_store`.

| Method+Path | Request | Response / Codes | Purpose |
|---|---|---|---|
| GET `/projects` | — | `list[ProjectRead]` | List projects |
| POST `/projects` | `ProjectCreate{name 1..256, description="", color="#6366f1"}` (extra=forbid) | 201 `ProjectRead` | Create project |
| GET `/projects/{project_id}` | path int | `ProjectDetail` (ProjectRead + jobs[JobBrief]); 404 | Project detail + its jobs |
| PATCH `/projects/{project_id}` | `ProjectUpdate{name?, description?, color?}` | `ProjectRead`; 404 | Update project |
| DELETE `/projects/{project_id}` | path int | 204 (idempotent) | Delete project |
| PATCH `/jobs/{job_id}/project` | `JobProjectAssign{project_id: int\|null}` | `JobProjectAssignResponse{job_id, project_id}`; 404 | Assign/detach job to project (null = detach) |

### 2.5 settings (`/settings`)

| Method+Path | Request | Response / Codes | Purpose |
|---|---|---|---|
| GET `/settings/performance` | — | `PerformanceSettings` | Effective perf settings (env + DB overrides) |
| PUT `/settings/performance` | `PerformanceSettings` | `PerformanceSettings` | Upsert perf settings (invalidates cache) |
| GET `/settings/vision` | — | `VisionSettingsResponse{settings, health, gguf_repo, gguf_file, mmproj_file}` | Vision config + lazy health |
| PUT `/settings/vision` | `VisionRuntimeSettings` | `VisionRuntimeSettings` | Upsert vision settings (resets client on enable change) |
| GET `/settings/models` | — | `ModelsInfo{available_providers, available_transcribers, defaults, available_llm_models}` | Available LLM/transcriber catalog |
| GET `/settings/prompts` | — | `PromptList{prompts[PromptPayload]}` | List prompt overrides |
| GET `/settings/prompts/{key}` | path key | `PromptPayload`; 404 | Get one prompt override |
| PUT `/settings/prompts/{key}` | `PromptPayload{key ^[a-z][a-z0-9_]{1,63}$, content 1..32768}` (400 if key≠url) | `PromptPayload` | Upsert prompt override |
| GET `/settings/fonts` | — | `FontListResponse{fonts, scanned_at, source}` (falls back to SYSTEM_FONTS if no cache) | List fonts |
| POST `/settings/fonts/refresh` | — | `FontListResponse`; 503 on FontScannerError | Rescan fonts (~6s blocking, system_profiler) |
| GET `/settings/subtitle_presets` | — | `list[SubtitleStylePresetRead]` | List subtitle presets |
| GET `/settings/subtitle_presets/{id}` | path int | `SubtitleStylePresetRead`; 404 | Get subtitle preset |
| POST `/settings/subtitle_presets` | `SubtitleStylePresetCreate` (409 conflict) | 201 `SubtitleStylePresetRead` | Create preset |
| PUT `/settings/subtitle_presets/{id}` | `SubtitleStylePresetUpdate` (404 / 403 builtin / 409) | `SubtitleStylePresetRead` | Update preset |
| DELETE `/settings/subtitle_presets/{id}` | path int (404 / 403 builtin / 409 default) | 204 | Delete preset |
| GET `/settings/profiles` | — | `list[ProfileMaskRead]` (5 profiles + is_customized) | List effective vision profile masks |
| GET `/settings/profiles/{profile}` | path `VisionProfile` (enum) | `ProfileMaskRead` | Get one profile mask |
| PUT `/settings/profiles/{profile}` | enum + `VisionProfileOverride` | `ProfileMaskRead` | Upsert profile override |
| DELETE `/settings/profiles/{profile}` | path enum | `ProfileMaskRead` (returns default) | Reset profile override |

### 2.6 post_production (`/post_production`)

| Method+Path | Request | Response / Codes | Purpose |
|---|---|---|---|
| GET `/post_production/assets` | — | `list[VideoAssetRead]` | List intro/outro assets |
| GET `/post_production/assets/{id}` | path int (404) | `VideoAssetRead` | Get asset |
| GET `/post_production/assets/{id}/thumbnail` | path int, query `time_sec: float = 0.0` (clamped) | PNG `Response`; 500 on ffmpeg fail | Asset thumbnail (ffmpeg pipe, no disk write) |
| POST `/post_production/assets` | multipart `file: UploadFile`, `name: Form` (400 empty / validation; 413 too large; 500 store error) | 201 `AssetImportResponse{asset, created}` (created=false on SHA256 dupe) | Import asset (dedup by SHA256) |
| DELETE `/post_production/assets/{id}` | path int (404; 409 AssetInUse with preset_ids) | 204 | Delete asset + file |
| GET `/post_production/presets` | — | `list[PostProductionPresetRead]` | List presets |
| GET `/post_production/presets/default` | — | `PostProductionPresetRead \| null` — **returns `null` body with status 200** when no default (file docstring claims 204; code/docstring diverge — frontend must handle `null`, not 204) | Get default preset |
| GET `/post_production/presets/{id}` | path int (404) | `PostProductionPresetRead` | Get preset |
| POST `/post_production/presets` | `PostProductionPresetCreate` (400 AssetRef / 409 conflict) | 201 `PostProductionPresetRead` | Create preset |
| PUT `/post_production/presets/{id}` | `PostProductionPresetUpdate` (404 / 400 / 409) | `PostProductionPresetRead` | Update preset |
| DELETE `/post_production/presets/{id}` | path int (404; 409 PresetInUse with active_job_ids) | 204 | Delete preset |

### 2.7 jobs (`/jobs`)

| Method+Path | Request | Response / Codes | Purpose |
|---|---|---|---|
| GET `/jobs` | query `limit=50` | `list[JobRead]` | List jobs (hidden filtered out) |
| POST `/jobs` | **multipart Form** (see below) | 201 `JobRead` | Create job + launch pipeline (fire-and-forget asyncio task) |
| GET `/jobs/artifacts/liked` | query `project_id?`, `job_id?`, `limit=100 (1..500)` | `list[ArtifactRead]` | Liked reels across jobs (registered before `/{job_id}` on purpose) |
| GET `/jobs/{job_id}` | path str (404) | `JobRead` | Get job |
| GET `/jobs/{job_id}/source-thumbnail` | path str (404) | image/jpeg `Response` | Source thumbnail (`app_thumbnails_dir/{job_id}.jpg`) |
| PATCH `/jobs/{job_id}/rename` | `JobRenamePayload{display_name?: max 256}` | `JobRead`; 404 | Rename (empty → reset to source_filename) |
| PATCH `/jobs/{job_id}/profile` | `JobProfileUpdate{profile}` | `JobRead`; 404 | Update vision profile (pipeline NOT re-run) |
| GET `/jobs/{job_id}/profile/suggestion` | path str (404; 409 no source/transcript) | `ProfileSuggestion` | Suggest profile from face coverage |
| POST `/jobs/{job_id}/auto-analyze` | path str (404; 409 no source) | `AutoAnalyzeResponse` (+audio_features) | Real audio/source analysis, optional LLM advise |
| PATCH `/jobs/{job_id}/auto-config` | `AutoConfigApplyPayload` (400 if empty) | `AutoConfigApplyResponse{job_id, pipeline_mode, applied_keys}` | Apply auto-config to job.options |
| DELETE `/jobs/{job_id}/auto-config` | path str (404) | 200 `{job_id, pipeline_mode:"manual"}` | Clear auto-config (manual mode) |
| GET `/jobs/{job_id}/artifacts` | path str (404) | `list[ArtifactRead]` | List job artifacts |
| PATCH `/jobs/{job_id}/artifacts/{artifact_id}/like` | `ArtifactLikeUpdate{liked}` (404) | `ArtifactRead` | Toggle like; best-effort Gemini embedding on like |
| DELETE `/jobs/{job_id}/artifacts/{artifact_id}` | path (404; 400 if kind≠reel_output) | 204 | Delete reel artifact (row + mp4 + subs) |
| DELETE `/jobs/{job_id}` | query `purge="soft"\|"hard"\|"nuke"` (404; 400 unknown) | 200 summary dict | Delete: soft=hide, hard=drop unliked mp4, nuke=full wipe |
| POST `/jobs/{job_id}/saved` | `SavedReelsRequest{reel_ids}` (404; 400) | 201 `SavedReelsResponse` | Copy reels (mp4+subs+poster+meta) to saved/ |
| GET `/jobs/{job_id}/thumbnail` | path str (404; 503 ffmpeg fail) | jpeg `FileResponse` (Cache 7d immutable) | Job thumbnail (writes first.jpg on first call) |
| GET `/jobs/{job_id}/stream` | path str (404) | **SSE `text/event-stream`** (§3) | Live progress stream |
| GET `/jobs/{job_id}/reels/{reel_id}/subtitles` | path (404) | text/plain (raw .ass) | Read reel subtitles |
| PATCH `/jobs/{job_id}/reels/{reel_id}/subtitles` | `SubtitleUpdateRequest{ass_content}` (404) | 204 | Overwrite reel .ass file |
| POST `/jobs/{job_id}/reels/{reel_id}/export` | query `preset` (400 unknown / 404 no mp4) | `ExportResponse{preset, bitrate_k, target_lufs, download_url}` | **⚠ PARTIAL STUB** — see §6 |

**`POST /jobs` Form fields** (internal model `JobCreate`; manual `if`-validation → 400):
`file`(UploadFile), `transcriber="stable_ts_mlx"`, `llm_provider="gemini"`, `llm_model="gemini-3.1-flash-lite-preview"`, `target_aspect="9:16"` (∈ 9:16/16:9/1:1/4:5), `fit_mode="fill"` (∈ fill/fit), `source_language="auto"` (∈ SUPPORTED_SOURCE_LANGS), `subtitle_style_preset_id?`, `subtitle_style_inline?` (JSON → SubtitleStyleConfig), `post_production_preset_id?`, `post_production_overrides_json?`, `use_proxy=true`, `use_source_for_render=false`, `target_reel_count?` (3..225), `force_reingest=false`, `vision_profile="talking_head"` (enum), `composer_strategy_override?` (∈ tight_context/balanced/thematic_free), `split_screen_enabled?`, `custom_system_prompt?` (max 8000). 413 if upload exceeds size limit.

### 2.8 scheduler (`/scheduler`)

Thin facade over Publer API + ORM store. DB via `session_scope()`.

| Method+Path | Request | Response / Codes | Purpose |
|---|---|---|---|
| GET `/scheduler/connection/status` | — | `ConnectionStatus{ok, workspace, accounts_count, error}` (never raises) | Publer connectivity probe |
| GET `/scheduler/accounts` | — | `list[PublerAccount]` (503 no key; 502 PublerClientError) | List Publer accounts |
| GET `/scheduler/accounts/profiles` | — | `list[AccountProfileRead]` | List local account profiles |
| PUT `/scheduler/accounts/profiles/{publer_account_id}` | `AccountProfileUpsert{display_name, network∈instagram/youtube, ...}` | `AccountProfileRead` | Upsert account profile |
| DELETE `/scheduler/accounts/profiles/{id}` | path str | 204 | Delete account profile |
| GET `/scheduler/presets` | query `account_id?` | `list[CaptionPresetRead]` | List caption presets |
| POST `/scheduler/presets` | `CaptionPresetCreate{name, position∈prepend/append, content, account_id?}` | 201 `CaptionPresetRead` | Create caption preset |
| PATCH `/scheduler/presets/{id}` | `CaptionPresetUpdate` (404) | `CaptionPresetRead` | Update caption preset |
| DELETE `/scheduler/presets/{id}` | path int | 204 | Delete caption preset |
| GET `/scheduler/campaigns` | query `status_filter?`, `limit=50 (1..500)` | `list[CampaignRead]` | List campaigns |
| POST `/scheduler/campaigns` | `CampaignCreate` (mode per_date/single_day/serial; 422 missing mode fields) | 201 `CampaignCreateResponse{campaign, assignments}` | Create campaign + assignments (LLM caption gen) |
| GET `/scheduler/campaigns/{id}` | path int (404) | `CampaignDetail` (+assignments) | Get campaign |
| POST `/scheduler/campaigns/{id}/approve` | path int (404) | `CampaignApproveResponse{campaign_id, approved_count}` | Approve: draft→queued, campaign→approved |
| DELETE `/scheduler/campaigns/{id}` | path int | 204 | Delete campaign |
| GET `/scheduler/assignments` | query `campaign_id?`, `status_filter?` | `list[AssignmentRead]` | List assignments |
| PATCH `/scheduler/assignments/{id}` | `AssignmentPatch{caption?, title?, hashtags?, scheduled_at_utc?}` (404) | `AssignmentRead` | Edit assignment |
| POST `/scheduler/assignments/{id}/cancel` | path int (404) | `AssignmentRead` | **⚠ PARTIAL STUB** — local status flip only — see §6 |
| POST `/scheduler/assignments/{id}/retry` | path int (404; 400 if not failed/cancelled) | `AssignmentRead` | Reset to queued, attempts=0 |
| POST `/scheduler/manual/publish-one` | `ManualPublishRequest{reel_artifact_id, job_id, publer_account_id, scheduled_at_utc, custom_caption?, custom_title?}` (422 no profile/mismatch) | 201 `AssignmentRead` | One-off: create approved campaign + queued assignment |

---

## 3. SSE Contract — `GET /api/v1/jobs/{job_id}/stream`

- **Media type:** `text/event-stream`. Headers: `Cache-Control: no-cache, no-transform`, `Connection: keep-alive`, `X-Accel-Buffering: no`.
- **Frame format:** `data: {json}\n\n` (UTF-8, `ensure_ascii=False`). No `event:` field — all frames are default `message`.
- **First frame (snapshot)** on connect:
  ```json
  { "stage": "<JobStage|'created'>", "progress": 0, "status": "...", "message": "...", "job_id": "..." }
  ```
- **Terminal short-circuit:** if the job is already `done`/`error`/`cancelled`, the stream sends the snapshot then closes.
- **Subsequent frames** come from `service.bus.subscribe(job_id)` (in-memory asyncio.Queue). Each event is serialized as-is. Stream ends when `event["status"] ∈ {done, error, cancelled}`.
- **Keepalive:** every `KEEPALIVE_INTERVAL_SEC=15.0` of silence → comment frame `: keepalive\n\n`.
- **Cleanup:** `finally` → `bus.unsubscribe`.

### Event payload fields
Published by the pipeline via `bus.publish(job_id, stage=..., progress=..., message=..., extra=...)`:

| Field | Type | Notes |
|---|---|---|
| `job_id` | str | |
| `stage` | str | one of JobStage below |
| `progress` | int 0–100 | mapped via `_STAGE_RANGES` |
| `status` | str | JobStatus; terminal values close the stream |
| `message` | str | human text |
| `extra` | object | per-stage detail, SSE-only (never persisted) |

**JobStage:** `ingest → proxy_generate → transcribe → translate → silence_cut → analyze → render → finalize → done` (`analyze` internally runs the 9 Kartoziya sub-stages, all reported as `analyze`).
**JobStatus:** `pending, running, done, error, cancelled`.

> Exact per-stage `extra` field names/frequency are produced in `services/pipeline.py` (pipeline domain, not the API layer). The channel contract above is complete; granular `extra` schemas should be sourced from the pipeline map.

> Other binary streams (`/files/...`, `/jobs/{id}/thumbnail`, `/source-thumbnail`, `/post_production/assets/{id}/thumbnail`, `/reels/.../subtitles`) are plain `FileResponse`/`Response`, **not** SSE.

---

## 4. Data Model (12 tables)

Engine: **SQLite** (`data/videomaker.db`) via `sqlite+aiosqlite`, SQLAlchemy 2.0 async ORM, Alembic migrations (19 files). `PRAGMA foreign_keys=ON` is enabled per-connection, so `ON DELETE` rules apply. DB is the single source of truth for the job domain and all user settings; pipeline artifacts live on disk with relative paths stored in `artifacts.path`.

> Note: head schema has 12 tables. Legacy `oauth_connections` / `scheduled_posts` were created by an early migration and **dropped** by the Publer migration — they do not exist in the current head.

| Table | ORM class | Purpose | Key relations |
|---|---|---|---|
| `jobs` | `Job` | Main video-processing record | → `projects.id` (SET NULL), → `post_production_presets.id` (SET NULL); 1:N `artifacts` (cascade delete-orphan, lazy=selectin) |
| `artifacts` | `Artifact` | Pipeline output files (transcript / reel_plan / reel_output / proxy / …) | → `jobs.id` (CASCADE). Index `ix_artifacts_kind_created_at` |
| `prompt_settings` | `PromptSetting` | Versioned LLM prompts (PK=key, default_content_hash) | — |
| `runtime_settings` | `RuntimeSettingRow` | Per-install config; each PerformanceSettings/Vision field as key/value_json | — |
| `subtitle_style_presets` | `SubtitleStylePresetRow` | Named subtitle style presets (is_builtin, is_default) | — |
| `projects` | `ProjectRow` | Logical job grouping | ← jobs |
| `video_assets` | `VideoAssetRow` | Intro/outro files + ffprobe metadata + SHA256 (dedup) | ← post_production_presets |
| `post_production_presets` | `PostProductionPresetRow` | Final-processing preset (loudnorm, zoom, intro/outro) | → `video_assets.id` ×2 (RESTRICT) |
| `account_profiles` | `AccountProfileRow` | Publer account profile (PK=publer_account_id) | ← caption_presets, ← schedule_assignments |
| `caption_presets` | `CaptionPresetRow` | prepend/append caption text | → `account_profiles` (CASCADE), nullable = global |
| `schedule_campaigns` | `ScheduleCampaignRow` | Group of scheduled publications | ← schedule_assignments (CASCADE) |
| `schedule_assignments` | `ScheduleAssignmentRow` | One publication (reel×account → time+caption) | → campaigns/jobs/artifacts (CASCADE), → account_profiles (RESTRICT). Unique (campaign, reel, account) |

### Relationship summary (ER, text)
- A **project** has many **jobs** (job.project_id, SET NULL on project delete).
- A **job** owns many **artifacts** (CASCADE delete). A job optionally references one `post_production_preset` (SET NULL).
- A **post_production_preset** references up to two **video_assets** (intro/outro, RESTRICT — asset can't be deleted while referenced).
- An **account_profile** owns **caption_presets** (CASCADE; preset.account_id null = global) and is referenced by **schedule_assignments** (RESTRICT).
- A **schedule_campaign** owns **schedule_assignments** (CASCADE). Each assignment links one reel artifact + one job + one account at a scheduled time, unique per (campaign, reel, account).

### Non-table data (DTOs / value objects)
Pydantic models serialized into JSON columns or passed between pipeline stages in memory — not tables:
- `job_dto.py`: JobCreate/Read/Update, ArtifactRead, SavedReels*, SubtitleStylePreset DTOs.
- `job_constants.py`: enums (JobStatus, JobStage, FitMode, SourceLanguage, VisionProfile, ArtifactKind, SubtitleAnchor, FontWeight) + `SubtitleStyleConfig` (stored in `jobs.subtitle_style_json`).
- `runtime_settings.py`: `PerformanceSettings` (decomposed into key/value rows of `runtime_settings`).
- `vision_settings.py`: VisionRuntimeSettings, VisionProfileOverride, ProfileMaskRead.
- `canvas.py`/`narrative.py`/`reel_plan.py`/`audio_profile.py` etc.: pipeline stage models carried in `PipelineContext` (RAM), final result written to disk as `reel_plan.json` (DB stores only the artifact path).
- `post_production.py`: PostProductionConfig, SplitScreenConfig, *Create/Update/Read DTOs.

`jobs.options` is a schema-less JSON column carrying `hidden`, `auto_config`, `stage_durations`, `composer_strategy_override`, `total_generation_sec`. Hidden-job filtering is done Python-side.

---

## 5. Stores — Persistence Map

13 store modules: 11 persist to DB, 1 is RAM-only by design, 1 is a re-export facade. **No stubs / fakes.**

| Store (services/) | Backend | Table / file | Persists? |
|---|---|---|---|
| `jobs.py` (JobService) | DB | jobs, artifacts | Yes (status source of truth) |
| `job_event_bus.py` | **RAM** | `dict[job_id → list[Queue]]` | **No — by design** (SSE pub/sub, single-process) |
| `prompt_store.py` | DB | prompt_settings | Yes (versioned seed) |
| `performance_settings_store.py` | DB + 30s TTL cache | runtime_settings | Yes (cache + ContextVar override) |
| `vision_settings_store.py` | DB + 30s TTL cache | runtime_settings | Yes |
| `runtime_settings_store.py` | — | — | **Facade** (re-export of perf+vision, no own storage) |
| `subtitle_store.py` | DB | subtitle_style_presets | Yes |
| `asset_store.py` | DB + disk | video_assets, post_production_presets | Yes (metadata in DB, file in data/post_production_assets) |
| `post_production_store.py` | DB | video_assets, post_production_presets | Yes |
| `projects_store.py` | DB | projects, jobs | Yes (session injected) |
| `account_profiles_store.py` | DB | account_profiles, caption_presets | Yes |
| `scheduler_campaigns_store.py` | DB | schedule_campaigns, schedule_assignments | Yes |
| `preference_memory.py` | DB (read) + disk | artifacts (+ reel_plan.json) | Yes (reads likes/embeddings, 0 LLM, fallback top_by_date) |

### In-memory structures (intentional, not stubs)
- **JobEventBus** — RAM-only SSE pub/sub. Single-process only; queue `maxsize=256`, silently drops on overflow. Does **not** scale horizontally (subscriber on worker A misses events published on worker B).
- **JobService `_pending` buffer** — progress writes throttled to ≤ once / 3s (`FLUSH_INTERVAL_SEC=3.0`); `mark_done`/`mark_error` flush immediately. Up to 3s of progress can be lost on hard crash (status repaired by `reset_stale_running_jobs` → all `running` become `error` on startup).
- **Stage timing** — in-memory, finalized into `jobs.options.stage_durations` + `total_generation_sec`.
- **Perf/Vision TTL caches (30s)** — module-global, read-through over DB, invalidated on PUT (single-process only).

> All single-process assumptions (event bus, caches, stale-running reset) hold only for single-instance deployment. Horizontal scaling would break SSE delivery and cache invalidation.

---

## 6. Stub / partial-implementation status

| Endpoint | Status | Detail |
|---|---|---|
| `POST /jobs/{job_id}/reels/{reel_id}/export` | **PARTIAL STUB** | MVP: validates preset + mp4 existence, returns metadata + link to the **existing un-transcoded** mp4 (`/api/v1/files/{job_id}/reels/{reel_id}.mp4`). `bitrate_k` / `target_lufs` in the response are declarative and **not applied** to the file. Full transcode = next iteration. |
| `POST /scheduler/assignments/{id}/cancel` | **PARTIAL STUB (Publer side)** | Flips local `status='cancelled'` only. Does **not** call Publer `DELETE /posts/{id}` — already-scheduled posts are not retracted (planned for delivery-worker task). Local `cancelled` does not block worker retry of the old assignment. |
| `GET /post_production/presets/default` | Contract quirk | Returns `null` body with **200** when no default exists (file docstring claims 204; code wins). Frontend must handle `null`, not 204. |
| Delivery worker | Out of API scope | `approve_campaign`, `retry_assignment`, `manual_publish_one` leave assignments `queued` for a delivery worker that is not part of the API layer. Confirm the worker exists in the services layer; otherwise queued assignments never publish. |

### Path-safety notes (open for verification at endpoint level)
- `/files/{job_id}/{kind}/{name}` — traversal guarded by `ArtifactsManager.path_for` (confirmed in core: `job_dir` / `resolve_relative` raise `ValueError` on `..`/`/`/escape).
- `/jobs/.../reels/{reel_id}/subtitles` (read + **write**) and `/export` build `job_dir/"subs"/f"{reel_id}.ass"` directly from the `reel_id` path param. FastAPI rejects `/` in a path segment by default, but `reel_id` is not otherwise sanitized — note for the PATCH (write) route.
