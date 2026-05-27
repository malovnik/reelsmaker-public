# Exposure B — UI Surface Map

Role: UX Surface Cartographer. Question answered: *what can a user actually do by clicking?* — which backend capabilities have a UI control, and which live only in the API.

Source: `apps/frontend/src/{pages,components}/`, `router.tsx`. Cross-referenced against `phase2-backend-map/section-1-api-data.md` (81 endpoints) and `section-2-pipeline.md` (default-vs-dormant features).

---

## 1. Pages (routes) and what each does

**22 page files, 18 routable URLs** (RootLayout + SettingsLayout are layout shells, NotFoundPage is the catch-all).

| Route | Page | What the user can do |
|---|---|---|
| `/` | HomePage | Dashboard hero + **UploadWizard** (the main job-creation surface) + job list with filters/bulk actions. |
| `/projects` | ProjectsPage | List/create/edit/delete projects; assign jobs to projects. |
| `/jobs/:id` | JobDetailPage | Job hero (rename, vision-profile change, delete/purge), pipeline timeline (SSE), reel grid, like, export, schedule, captions. |
| `/jobs/:id/reels/:reelId` | ClipDetailPage | Single-reel detail: scrubber, like, **subtitle (.ass) editing**, export dialog. |
| `/jobs/:id/tinder` | JobTinderPage | Swipe UI to like/reject reels rapidly. |
| `/schedule` | SchedulePage | Schedule timeline (publishing calendar view). |
| `/scheduler` | SchedulerPage | Campaign list + scheduler dashboard. |
| `/scheduler/accounts` | AccountsPage | Publer account profiles + caption presets. |
| `/scheduler/new` | NewCampaignPage | Campaign wizard (pick reels, accounts, mode, schedule). |
| `/scheduler/presets` | PresetsPage | Caption preset CRUD. |
| `/scheduler/campaigns/:id` | CampaignDetailPage | Campaign detail, edit/approve/cancel/retry assignments. |
| `/settings/brand` | BrandKitPage | Brand-kit (frontend-only; no backend endpoint). |
| `/settings/connections` | ConnectionsPage | **DEAD UI** — YouTube OAuth connect/status (endpoints do not exist, see §4). |
| `/settings/models` | ModelsPage | Read-only provider/transcriber availability + **Moondream vision toggle/sample-rate** (the only writable control here). |
| `/settings/performance` | PerformanceSettingsPage | The big pipeline-tuning surface: ~25 control groups (narrative mode, LLM tier, DSP, motion, reel count, etc.). |
| `/settings/post-production` | PostProductionSettingsPage | Preset CRUD: intro/outro assets, audio normalize, zoom, split-screen, B&W. |
| `/settings/profiles` | VisionProfilesPage | Vision profile masks (5 profiles) override/reset. |
| `/settings/prompts` | PromptsPage | Edit LLM prompt overrides. |
| `/settings/subtitles` | SubtitleSettingsPage | Subtitle style preset editor + preview. |
| (layouts) | RootLayout, SettingsLayout | Shell/nav only. |
| `*` | NotFoundPage | 404. |

NavRail exposes 9 top-level destinations (`/`, projects, scheduler, profiles, models, subtitles, post-production, prompts, performance). `/settings/connections` and `/settings/brand` and `/schedule` are reachable by URL/buttons but **not in the main NavRail**.

---

## 2. Domain → backend capability → UI control? → where

### Jobs
| Backend capability | UI control? | Where |
|---|---|---|
| Create job (POST /jobs multipart) | **Yes** | UploadWizard (HomePage) |
| Upload-time: aspect, fit_mode, reel count, source lang, transcriber, llm_provider, vision_profile, subtitle preset, post-prod preset+overrides, split-screen override, custom_system_prompt, use_proxy, use_source_for_render, force_reingest | **Yes** | UploadWizard fields + "Дополнительно" disclosure |
| `composer_strategy_override` | **Yes** | UploadWizard ComposerStrategyBlock |
| Auto-config (auto-analyze + apply) | **Yes** | UploadWizard "Режим монтажа" auto/manual + AutoConfigSummary |
| `llm_model` (specific model id) | **No** (provider only; model picked server-side by tier) | — |
| Rename / delete (soft/hard/nuke) | **Yes** | JobList, JobHero |
| Change vision profile post-hoc | **Yes** | JobHero/JobCard ProfileSelector → `updateJobProfile` |
| Profile suggestion (`/profile/suggestion`) | **No** wired UI call found | — |
| Like / unlike reel | **Yes** | ReelCard, ClipDetail, Tinder |
| Liked-reels cross-job view | **Partial** (filters expose liked; no dedicated gallery page) | dashboard filters |
| Save reels to saved/ | **Yes** | ReelGrid |
| Delete single reel | Yes (via grid) | ReelGrid |
| Edit reel subtitles (.ass) | **Yes** | ClipDetail CaptionsEditor |
| Export reel (preset) | **Yes** (but see fiction §4) | ExportDialog |
| SSE live progress | **Yes** | PipelineTimeline / wizard progress bar |
| Source/job thumbnails | Yes | dashboard/job cards |

### Projects
Full CRUD + job assignment all exposed (ProjectsDashboard, ProjectFormModal).

### Scheduler / Publishing
| Capability | UI? | Where |
|---|---|---|
| Connection status, accounts list | Yes | SchedulerDashboard, AccountsPicker |
| Account profiles CRUD | Yes | AccountProfilesDashboard |
| Caption presets CRUD | Yes | CaptionPresetsDashboard / PresetsPage |
| Campaign create (3 modes) / detail / approve / delete | Yes | CampaignWizard, CampaignDetailClient |
| Assignment edit / cancel / retry | Yes | CampaignDetailClient |
| Manual publish-one | Yes | ManualPublishButton |

### Settings — performance (pipeline tuning)
~25 groups, each backed by `PerformanceSettings` fields. Exposed controls: LLMGroup (provider+tier), NarrativeModeGroup, MultiArc, RenderConcurrency, Defaults, Coherence, QualityGates (variants, rhythm-critique, target duration), AutoMode, Pacing, Punchline, Motion (punch-in, Ken Burns, face_tracker), ReelCount, Preference, AdaptiveAudio (breath/context/smart-jl/leveller), PauseCompression, Ensemble, FillerRemoval, CutSnap, RhythmCuts, JLCut, SemanticChunking, CrossChunk, Proxy, ProxyCache, ProxySkip.

### Settings — vision / models / subtitle / prompts / post-production
- Vision enabled + frame sample rate: **Yes** (MoondreamSettings).
- Vision profile masks: **Yes** (VisionProfilesPage).
- Provider/transcriber availability: **read-only display** (ModelsPage; keys are .env-only).
- Subtitle style (font, size, anchor, color, outline, weight, uppercase, safe-zone, max lines): **Yes** (SubtitleStyleEditor).
- Prompt overrides: **Yes** (PromptsEditorClient).
- Post-production: intro/outro assets, audio normalize, zoom (3 plane %, alternate, cadence), split-screen (companion, crop modes), B&W: **Yes**.

---

## 3. Dormant/configurable pipeline features — has UI control?

| Pipeline feature | Backend default | UI control? | Where / note |
|---|---|---|---|
| `vision.enabled` (whole vision layer) | OFF | **Yes** | MoondreamSettings (ModelsPage) |
| Vision frame sample rate | — | Yes | MoondreamSettings |
| `face_tracker_enabled` | OFF | **Yes** | MotionGroup |
| `narrative_mode` (4 modes incl chaptered) | bottom_up | **Yes** (all 4 radio incl chaptered) | NarrativeModeGroup |
| LLM provider (gemini/zhipu) | gemini | **Yes** | LLMGroup `pipeline_llm_provider` + UploadWizard provider select |
| LLM tier profile | fast | **Yes** | LLMGroup `llm_tier_profile`, `llm_lite_variant` |
| punch-in zoom / Ken Burns | punch-in on / KB off | **Yes** | MotionGroup |
| multi_arc_builder | OFF | **Yes** | MultiArcGroup |
| cross_chunk_reducer | OFF | **Yes** | CrossChunkGroup |
| reducer ensemble | size 1 | **Yes** | EnsembleGroup |
| semantic chunking | OFF | **Yes** | SemanticChunkingGroup |
| pause compression / breath | OFF | **Yes** | PauseCompressionGroup |
| filler removal | OFF | **Yes** | FillerRemovalGroup |
| cut_snap | ON | **Yes** | CutSnapGroup |
| J/L cuts | OFF | **Yes** | JLCutGroup |
| adaptive leveller / smart-jl / breath classifier / mouth-sound | OFF | **Partial** — leveller/smart-jl/breath/context exposed; **mouth_sound_removal hidden** | AdaptiveAudioGroup (mouth-sound deliberately removed from UI) |
| post-production object (intro/outro/zoom/split/B&W) | OFF | **Yes** | PostProductionSettingsPage + UploadWizard overrides |
| screencast cursor zoom / deictic zoom | dormant (compute-then-discard) | **No** — UI deliberately hidden | PerformanceSettingsClient comment lines 168–174, 290–293 (fields persist, no control) |
| B-roll subsystem, object_tracker, orphan modules | dead | **No** | not in UI |
| Deepgram/anthropic/openai as pipeline LLM | dead in narrative brain | **Partial** — providers shown read-only in ModelsPage; only gemini/zhipu selectable as pipeline provider | LLMGroup limited to 2 |

---

## 4. UI elements controlling fictions / decorative backend

1. **Export dialog "tier"/bitrate presets** (ExportDialog) — 4 presets (TikTok/Reels/Shorts/X) with bitrate+LUFS labels, but backend `POST .../export` is a **partial stub**: no transcode, returns the un-re-encoded mp4. The component's own footnote admits "MVP: возвращает ссылку на существующий MP4". The bitrate/LUFS shown are cosmetic.
2. **LLM tier profile "fast/legacy" + lite variant** (LLMGroup) — UI implies model-quality choice, but per pipeline map **all tiers physically resolve to Flash-Lite**; "pro inference" never happens. The "режим работы нейросети" toggle is largely fiction (only switches between two Lite variants).
3. **`chaptered` narrative mode** (NarrativeModeGroup) — selectable radio, but author-marked **broken on monologues** (returns 1 chapter); its own hint admits "Оставлен для отката". User can pick a known-broken mode.
4. **Assignment "cancel"** (CampaignDetailClient) — backend cancel is a **stub**: flips local status only, does not retract the Publer post.
5. **`/settings/connections` — entirely DEAD UI.** ConnectionsSettings fetches `/api/v1/connections/youtube/status` and POSTs `/api/v1/connections/youtube/connect`. Per section-1, the `connections`/`oauth_connections` router & table were **dropped** by the Publer migration — these endpoints do not exist. Connect button will always fail; the page promises YouTube OAuth that the backend cannot deliver. (Real publishing goes via Publer accounts in the scheduler domain instead.)
6. **Provider select in UploadWizard / ModelsPage** lists anthropic/openai/deepgram as if usable, but they are dead in the narrative brain (anthropic/openai never called; provider switch in viral_2026 mode is ignored — always Gemini).

---

## Returns

**Number of pages:** 22 page files; **18 routable URLs** (16 content routes + 404 + nested layouts); 9 in the primary NavRail.

**Top-10 backend capabilities with NO UI control:**
1. `/connections/youtube/*` — *(inverse: UI exists, backend doesn't — see fiction #5; but as a capability the OAuth connect flow has no working backend)*.
2. `llm_model` specific-id selection (only provider exposed; model is tier-resolved server-side).
3. `GET /jobs/{id}/profile/suggestion` — endpoint exists, no wired UI trigger.
4. `mouth_sound_removal_enabled` — field exists, deliberately removed from UI (dormant).
5. Screencast cursor-zoom (`screencast_cursor_zoom_enabled`, damping, max-factor) — fields persist, UI hidden.
6. Deictic zoom (`deictic_zoom_enabled`) — fields persist, UI hidden.
7. Provider `zhipu`/`gemini` aside, anthropic/openai/deepgram as **pipeline** LLM — not selectable (shown read-only only).
8. `DELETE /proxies/cleanup` and `/proxies/{sha256}` — proxy cache cleanup endpoints; no UI button (ProxyCacheGroup only sets policy, no manual purge action found).
9. `/settings/fonts/refresh` (rescan) — font list consumed in subtitle editor, but no explicit "refresh fonts" button surfaced.
10. `JobStatus.cancelled` / job cancellation mid-pipeline — no `mark_cancelled`, no cancel-job button (only delete/purge).

**UI controlling fictions:** Export bitrate/tier presets (no transcode); LLM "tier/quality" toggle (all Flash-Lite); `chaptered` mode (broken); assignment cancel (no Publer retract); **`/settings/connections` YouTube OAuth page (dead — backend endpoints dropped)**; multi-provider selects listing dead anthropic/openai/deepgram.
