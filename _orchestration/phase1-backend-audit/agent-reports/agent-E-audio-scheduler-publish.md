# Agent E — Audio DSP, Scheduler, Publishing & Post-Production

Scope root: `apps/backend/src/videomaker/services/`. Audited: `publer/*` (9), `pipeline_stages/{ingest,analysis,render}.py` (sampled — analysis/render owned by other agents, only DSP-wiring verified), `agents/*` (base, orchestrator), all audio DSP services, `translator.py`, `media.py`, `proxy.py`, `settings_service.py`, `scheduler_campaigns_store.py`, `account_profiles_store.py`.

Verdict up front: **No stubs found in this scope.** Publer integration is a **real HTTP client against the live Publer Business API v1**. All audio DSP is real signal processing (librosa / pyloudnorm / silero-vad / parselmouth / ffmpeg) and is wired into `render.py`. The only `placeholder` string in scope is a comment in `analysis.py:607` about a DashboardHero score (not this agent's domain).

---

## Publer / паблишинг (реальность интеграции)

**REAL — не заглушка.** Async `httpx` client hitting `https://app.publer.com/api/v1` (`publer/client.py`).

- **Auth:** `Authorization: Bearer-API <PUBLER_API_KEY>` + `Publer-Workspace-Id: <PUBLER_WORKSPACE_ID>` header on workspace-scoped calls (`client.py:59-68`). Missing key → `PublerClientError` at construction (`client.py:41-42`).
- **Real endpoints called:**
  - `GET /workspaces` (`client.py:117`)
  - `GET /accounts` (`client.py:128`)
  - `POST /media` multipart file upload → returns Publer `media_id` (`client.py:139`)
  - `POST /posts/schedule` → returns `job_id` (`client.py:201`)
  - `GET /job_status/{job_id}` (`client.py:216`)
- **Retry/rate-limit policy (real, well-engineered):** 3 attempts, exponential backoff 1s/3s/9s on `httpx.HTTPError` + 5xx; on HTTP 429 sleeps 125s and retries without consuming the retry budget, capped at 5 rate-limit hits (`client.py:80-115`). Upload path duplicates the same logic with a 600s timeout for large videos (`client.py:151-199`).
- **Networks supported:** Instagram (Reels, `feed=True`) and YouTube (Shorts, `privacy=public`). Built in `post_builder.py:38-54` via `PublerInstagramNetwork` / `PublerYoutubeNetwork`. Any other network → `ValueError`. Network enum is `PublerNetwork` in `models/scheduler.py`.
- **Contract / payload shape (`publer/schemas.py`):** `bulk.state="scheduled"` + `posts[]`, each post = one network + one account target with `scheduled_at` (ISO) and labels `["videomaker-auto", "campaign-{id}"]`. Models use `extra="allow"` + `populate_by_name=True` to tolerate Publer's evolving snake/camelCase responses — pragmatic, won't break on new fields.
- **Media handling (`media_uploader.py`):** uploads reel directly if ≤180 MB; otherwise on-the-fly ffmpeg `h264_videotoolbox` re-encode targeting ~150 MB (bitrate computed from ffprobe duration). If still >200 MB after re-encode → `ValueError` ("URL-flow пока не реализован" — see Open Questions). Re-encoded temp file cleaned in `finally`.
- **Caption generation (`caption_generator.py`):** REAL LLM call (Gemini Flash Lite via `LLMClient.complete_json`) producing `{title, caption, hashtags}` per (reel × account), conditioned on account profile (tone/audience/CTA/banned words/max length). Not a template stub.
- **Preset application (`preset_applier.py`):** deterministic prepend/append of active caption presets. Pure function.

**Delivery worker (`publer/worker.py`) — REAL background service.**
- Instantiated and started in app lifespan: `main.py:91-92` (`PublerWorker(settings).start()`), stopped at shutdown (`main.py:97`). No-op if `PUBLER_API_KEY` unset (`worker.py:52-53`).
- Polls `scheduler_campaigns_store.list_pending_due` every 30s for `status=queued` assignments, then for each: upload media (or reuse cached `publer_media_id`) → `POST /posts/schedule` → mark `scheduled` with `publer_job_id`. Max 3 attempts; on final failure → `failed`, else back to `queued` (`worker.py:106-184`). TOCTOU-guarded re-read of the row before delivery (`worker.py:101-103`).
- **Design note (correct, documented):** the worker does NOT wait for `scheduled_at` — Publer itself is the scheduler. The worker delivers ASAP; Publer holds the post until the future `scheduled_at`. `limit=50`/tick × 2 requests = 100 req, exactly Publer's 100 req/2min ceiling (`worker.py:8-9`).

---

## Планировщик и кампании

Domain entry point: `publer/scheduler_service.py::build_campaign_from_pool` — called from `api/routes/scheduler.py` (Agent A's route zone). Persistence: `scheduler_campaigns_store.py` (CRUD, real SQLAlchemy async).

- **Timezone handling (correct):** `compute_scheduled_at_utc` (`scheduler_service.py:37-54`) builds a tz-aware local `datetime` via `zoneinfo.ZoneInfo(tz_name)` and converts to UTC. Default tz `Asia/Ho_Chi_Minh` (`config.py:203`). `tz` validated by attempting `ZoneInfo(tz)` (`scheduler_service.py:213-216`); `time_of_day` validated against `HH:MM` regex + range (`scheduler_service.py:202-212`).
- **Three scheduling modes** (`_compute_assignment_schedule`, `scheduler_service.py:57-139`):
  - `per_date` — round-robin over a `dates[]` list using flat index `reel_index*total_accounts + account_index`.
  - `single_day` — all posts on one day, staggered by `single_day_interval_min` (default 60) × flat index.
  - `serial` — one reel per day stepped by `serial_interval_days`; same-reel accounts get a 2-min × account_index jitter so Publer doesn't fire them simultaneously.
  - Unknown mode → `ValueError`. Required-field validation per mode is enforced both in the builder and the compute helper.
- **Campaign build flow:** for each (reel × account): load `AccountProfileRow` (skip with warning if missing), generate caption (LLM), apply presets, compute UTC slot, create `ScheduleAssignmentRow` in `draft` (ready-to-review in UI). Campaign created in `draft` too. YouTube gets a `title`, others empty.
- **Store** (`scheduler_campaigns_store.py`): standard CRUD; `update_assignment` whitelists mutable fields via `_MUTABLE_ASSIGNMENT_FIELDS` (good — prevents arbitrary column writes). `list_pending_due` selects `queued` ordered by `scheduled_at_utc`, `limit=50`.

State machine: `draft` → (user approves, route) `queued` → worker `uploading` → `scheduled` (or `failed`).

---

## Аудио-конвейер

All real, all wired into `pipeline_stages/render.py` (confirmed by grep: detect_speech_segments @691, breath @751, mouth @790, pause-compress @809/877, filler @912, beat/onset snap @993-1004, loudnorm measure @1304). Ingest stage uses proxy + silence_cutter (`ingest.py:21-33`).

| Service | Tech | What it really does |
|---|---|---|
| `audio_analyzer.py` | librosa, pyloudnorm, scipy, parselmouth, silero-vad, scikit-maad | Extracts ~15 audio features in parallel (`asyncio.to_thread`): SNR, EBU R128 LUFS/LRA, spectral flatness/centroid, F0 mean/std + HNR (Praat), VAD gap distribution + kurtosis, rhythm CV (onset IOI). Every extractor graceful-degrades to a named safe default, logging into `profile.failures[]`. `_warm_imports()` pre-loads scipy to dodge a thread-race circular import. (`extract_audio_profile`, line 86) |
| `audio_normalizer.py` | ffmpeg `loudnorm` | EBU R128 two-pass: `measure_source_loudness` (audio-only measurement pass, `-vn -f null`), parses JSON summary from stderr; pass 2 done in `filter_graph_builder` with `linear=true`. Returns `None` on any failure → caller falls back to single-pass. (line 125) |
| `adaptive_leveller.py` | pyloudnorm, librosa | Per-window (3s) LUFS measurement → clamped (±6 dB) gain list `[(start,end,gain_db)]` applied later via ffmpeg `volume` between(). Graceful `[]` if deps missing / <2s audio. (`compute_adaptive_gains`, line 22) |
| `beat_detector.py` | librosa | `detect_beats` (beat_track) + `detect_onsets` (onset_detect, tight window for talking-head) + `snap_cuts_to_beats`/`snap_cuts_to_reference` snapping cut boundaries to nearest beat/onset within ±150ms via binary search, with min-duration guard. <4 beats → `[]` (treats voice as non-musical). (line 51) |
| `vad.py` | silero-vad (ONNX) + soundfile + torch | `detect_speech_segments` — 16k resample, `get_speech_timestamps`, returns `SpeechSegment[]`. Model cached `@lru_cache`. `silence_gaps` inverts speech spans. (line 61) |
| `breath_classifier.py` | librosa | RMS-band heuristic (10th–50th pct) outside VAD speech, 150–600ms → breath events to PRESERVE during pause compression. Graceful `[]`. (line 18) |
| `mouth_sound_detector.py` | librosa STFT | Lip-smack/click detection via lip-band(2–8k)/speech-band(80–300Hz) energy ratio >95th pct, 20–100ms → `AudioDefect[]` for mute zones. Graceful `[]`. (line 28) |
| `silence_cutter.py` | transcript word-gaps + `config/fillers_ru.yaml` | Marks silence (`gap ≥ min_silence_sec`, default 0.6) + filler words (single & multi-word regex from YAML) for removal → `CleanedTranscript`. Pure (no audio I/O); render does the trim. (`clean_transcript`, line 103) |
| `filler_removal.py` | word-level `is_filler` + confidence | Splits `CutSpec`s to excise filler words (±30ms buffer); aggressive mode also drops `confidence < threshold` words. Min 50ms sub-segment guard. (`remove_fillers_from_cuts`, line 81) |
| `pause_compression.py` | VAD speech segments | Shortens pauses > `min_pause_sec` (0.4) to `keep_sec` (0.2), optional context-aware keep based on trailing punctuation (`.`/`?`/`,`). Pure function. (`compress_pauses_in_cuts`, line 93) |
| `translator.py` | LLM (`build_llm`) | Batched (15 segments) LLM translation to target language, redistributes translated words across the source word-span to keep subtitle sync. Skips only on explicit same-language target. Per-batch fallback to original on parse failure. (`Translator.translate`, line 65) |

Adjacent infra (real):
- `media.py` — ffmpeg/ffprobe wrappers; **no shell** (`create_subprocess_exec` with `list[str]`), command injection not possible. `ffmpeg_escape_path` correctly escapes lavfi filter args.
- `proxy.py` — 1080p H.264 proxy cache keyed by `source_sha256 + profile_id`, atomic O_EXCL lockfile with orphan cleanup, atomic `.partial`→final rename, LRU eviction. Solid.
- `agents/base.py` + `orchestrator.py` — REAL Gemini extraction (6 agents × N chunks), `response_schema`-constrained JSON, per-agent context caching (TTL 1800s, deleted in `finally`), wave-1/wave-2 execution with deterministic coverage reducer between waves. Tolerant of partial failures.

---

## Сервисы (таблица)

| File | Purpose | In/Out | Key fn (file:line) |
|---|---|---|---|
| publer/client.py | Publer API HTTP client | settings → API resp | `_request` 70, `upload_media_file` 139, `schedule_posts` 201 |
| publer/worker.py | Background delivery loop | DB queue → Publer | `_run` 77, `_deliver_one` 106 |
| publer/scheduler_service.py | Build draft campaign | reels+accounts → rows | `build_campaign_from_pool` 142, `_compute_assignment_schedule` 57 |
| publer/media_uploader.py | Reel→media_id (+re-encode) | Path → media_id | `upload_reel_to_publer` 21 |
| publer/caption_generator.py | LLM caption/title | reel+profile → text | `generate_caption` 23 |
| publer/post_builder.py | Build schedule payload | rows → request | `build_schedule_request` 20 |
| publer/preset_applier.py | Prepend/append presets | text+presets → text | `apply_presets` 7 |
| publer/schemas.py | Publer Pydantic models | — | `PublerScheduleRequest` 89 |
| scheduler_campaigns_store.py | Campaign/assignment CRUD | DB | `list_pending_due` 171, `update_assignment` 157 |
| account_profiles_store.py | Account profiles + presets store | DB | (CRUD; consumed by scheduler_service) |
| settings_service.py | Prompt-override domain ops | DB | `upsert_prompt_override` 47 |
| audio_analyzer / normalizer / leveller / beat / vad / breath / mouth / silence / filler / pause | see audio table above | | |
| translator.py | LLM transcript translation | transcript → transcript | `translate` 65 |
| media.py | ffmpeg/ffprobe wrappers | Path → MediaInfo / files | `probe` 38, `extract_audio` 73 |
| proxy.py | Proxy cache | source → cached mp4 | `generate_or_get_proxy` 143 |
| agents/base.py | Generic extraction agent | chunk+canvas → evidence | `run_extraction_agent` 125 |
| agents/orchestrator.py | 6-agent × N-chunk runner | chunks → evidence | `orchestrate_extraction` 65 |

---

## Внешние зависимости/ключи

Env keys (`core/config.py`):
- `PUBLER_API_KEY`, `PUBLER_WORKSPACE_ID` (required for publishing; worker no-ops without the key), `PUBLER_SCHEDULER_TZ` (default `Asia/Ho_Chi_Minh`), `PUBLER_BASE_URL` (default `https://app.publer.com/api/v1`), `PUBLER_REQUEST_TIMEOUT_SEC` (default 30).
- `GEMINI_API_KEY` (caption gen, extraction agents, translator default) — model matrix hard-limited to Flash-Lite (`gemini-2.5-flash-lite` default).
- `DEEPGRAM_API_KEY` (transcription, model `nova-3`) — consumed in ingest via transcriber factory (not this agent's file but feeds the audio pipeline).
- Optional `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `ZHIPU_API_KEY` (translator/LLM provider overrides).

Binaries (must be on PATH): **ffmpeg, ffprobe** (media, proxy, normalizer, media_uploader re-encode — uses `h264_videotoolbox`, i.e. macOS/Apple-Silicon assumption for the re-encode path).

Python libs: `httpx`, `librosa`, `pyloudnorm`, `scipy`, `numpy`, `soundfile`, `parselmouth`, `silero-vad`, `torch`, `scikit-maad`, `pyyaml`, `sqlalchemy`.

---

## Подозрения на заглушки (ПОДРОБНО)

Aggressive grep for `NotImplementedError|TODO|FIXME|mock|stub|заглушк|placeholder|dummy|fake` across the full scope returned **one hit**, and it is NOT a stub:
- `pipeline_stages/analysis.py:607` — comment "…настоящий средний балл в DashboardHero вместо placeholder 82" — describes a real computed score replacing a frontend placeholder. analysis.py is another agent's zone; flagged for completeness only.

No fake HTTP, no mocked responses, no hardcoded sample data, no `pass`-only functions in this scope. Graceful-degrade `return []` / safe-default paths in the audio extractors are **legitimate fallbacks**, not stubs — each logs a reason and the pipeline continues.

---

## Открытые вопросы

1. **Publer >200 MB reel = hard `ValueError`** (`media_uploader.py:56-59`). The "URL-flow" (presigned/remote URL ingest) is explicitly not implemented. Fine for ≤90s 9:16 reels, but a long/high-bitrate export would fail delivery rather than degrade. Confirm this ceiling is acceptable for all profiles.
2. **`h264_videotoolbox` in the re-encode path** (`media_uploader.py:104`) is Apple-Silicon/macOS-specific. On a Linux/Railway deploy this codec is unavailable and the re-encode (only triggered for >180 MB reels) would fail. Confirm deploy target — if Linux, this branch needs `libx264` or a runtime codec check.
3. **No real Publer credentials available in this audit** — integration is real *by code*, but I could not execute a live round-trip. Worth a smoke test against a sandbox workspace.
4. **`account_profiles_store.py`** was listed in scope but is plain CRUD consumed by `scheduler_service`; not deeply re-audited beyond confirming it backs the campaign builder. If profile validation (e.g. account_id format, network enum) matters, verify there.
5. **`scheduled_at` precision vs Publer**: jitter logic (2 min × account_index in `serial`) assumes Publer honors per-target `scheduled_at` to the minute. Confirm Publer's scheduling granularity matches.

---

### Summary returned to orchestrator
- **Publer status: REAL integration** — async httpx client against Publer Business API v1 (`/workspaces`, `/accounts`, `/media`, `/posts/schedule`, `/job_status`), Bearer-API auth, proper retry + 429 handling, live background delivery worker wired in `main.py` lifespan. Instagram Reels + YouTube Shorts.
- **Audio: everything real and wired into render.py** — VAD (silero), loudness (pyloudnorm/ffmpeg loudnorm two-pass), adaptive leveller, beat/onset snapping (librosa), breath/mouth-sound heuristics, filler removal, pause compression, full 15-feature analyzer. All graceful-degrade, none faked.
- **External APIs:** Publer (key+workspace), Gemini (Flash-Lite), Deepgram (nova-3), optional Anthropic/OpenAI/Zhipu; binaries ffmpeg/ffprobe.
- **Top-5 stub findings:** (1) none — zero stubs in scope; (2) only false-positive: a `placeholder` *comment* in analysis.py:607 (other agent's file, describes real fix); (3) "URL-flow not implemented" is a deliberate documented limit (>200MB reels hard-fail), not a stub; (4) `h264_videotoolbox` macOS-only re-encode is a portability risk, not a stub; (5) graceful `return []` fallbacks in audio extractors are real fallbacks, not mocks.
