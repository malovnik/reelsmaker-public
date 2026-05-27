# Section 2 — Processing Pipeline

How a source video becomes finished 9:16 reels. This is the backend's "main line": a single fire-and-forget async task per job, orchestrated by `services/pipeline.py:run_pipeline`, streaming progress over SSE. Publishing is a separate, manual flow bolted onto the side.

Read this once and you should be able to trace any frame from upload to a rendered `.mp4` and explain which of the fancy features actually fire on a default run (most do not).

---

## 2.1 End-to-end flow

```
                          ┌─────────────────────────────────────────────────────────┐
   POST /jobs (multipart) │                  PIPELINE (one asyncio task)             │
        │                 │                                                          │
        ▼                 │                                                          │
   [0] UPLOAD ────────────┼─► INSERT job(pending) ─► ArtifactsManager.ensure_layout  │
   data/uploads/<file>    │                                                          │
                          │   ┌── INGEST ──────────────────────────────────────────┐│
                          │   │ [1] probe   (ffprobe: dims/duration)                ││
                          │   │ [2] proxy   (1080p H.264, LRU cache; skippable)     ││
                          │   │ [3] transcribe (stable-ts MLX, word timestamps)     ││
                          │   │ [4] translate  (CONDITIONAL: only if lang != ru)    ││
                          │   │ [5] silence_cut (mark pauses + fillers, no audio cut)││
                          │   └─────────────────────────────────────────────────────┘│
                          │                          │                                │
                          │                          ▼                                │
                          │   [6] ANALYZE  ── narrative "brain", 4 modes ───────────  │
                          │        chunk→compress→canvas→extract→reduce→             │
                          │        story_doctor→variants→compose→validators          │
                          │                          │                                │
                          │                          ▼  reel_plan.json                │
                          │   [7] RENDER  ── per reel, one ffmpeg filter_complex ───  │
                          │        crop → cut-transforms → zoom/motion → subtitles    │
                          │        → loudnorm → HEVC encode                           │
                          │                          │                                │
                          │                          ▼  reels/<id>.mp4                 │
                          │   [8] FINALIZE (timing, status=done, SSE done)            │
                          └──────────────────────────┼────────────────────────────────┘
                                                     │
                  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ▼ ─ ─ ─ (NOT part of pipeline)
                  [9] PUBLISH  user creates campaign in /scheduler/* → approve →
                       PublerWorker polls queue every 30s → upload media →
                       POST /posts/schedule → Publer holds until scheduled_at
```

Six pipeline phases (`run_pipeline`): **upload → ingest → analyze → render → finalize**, with ingest itself being a 5-step sub-sequence and publish living entirely outside the task. The transition from analyze to render is the `reel_plan.json` artifact — the analyze phase decides *which* moments become reels and where they start/end; render turns each plan into pixels.

Honest framing of two things up front, because they color everything below:

- **The job runs as a fire-and-forget `asyncio.create_task`** (`jobs.py`), tracked only in a module-level set. There is no persistent queue. Process restart = in-flight jobs are not resumed; `reset_stale_running_jobs` marks them `error`. This is a single-process / SQLite architecture.
- **Most "advanced" features are off by default.** A default run executes a solid but lean spine. The marquee vision/motion features are toggle-gated OFF, dormant (computed-then-discarded), or orphaned. Section 2.7 is the authoritative list.

---

## 2.2 The narrative brain (analyze phase)

The analyze phase is where the LLM does its work. Entry: `services/pipeline_stages/analysis.py:run_analysis_stage`.

### Common preamble (runs in ALL four modes)

Before branching on `PerformanceSettings.narrative_mode`, analysis always does:

1. **Chunking** — `chunker.py:chunk_transcript` (tiktoken token sliding-window) or `semantic_chunker.py` (embedding cosine-minima boundaries).
2. **Compression** — `compression.py:compress_chunks`, Flash-Lite, **parallel** (`asyncio.gather` + `Semaphore(llm_max_concurrency)`). Prompt `compression`.
3. **Canvas builder** — `canvas_builder.py:build_canvas`, one "Pro" call (physically Flash-Lite, see tier note). Prompt `canvas_builder`. Produces `ProjectCanvas` (themes / motifs / candidate_moments / tone_map / central_theme).
4. **Canvas embedding** — `canvas_embedder.py`.

### LLM providers & tier resolution

Provider registry (`services/llm_providers/registry.py`), facade `services/llm_client.py`:

| Provider | Client | Used in narrative pipeline? |
|---|---|---|
| `gemini` (default) | `GeminiClient`, supports context caching | **Yes — every stage.** |
| `zhipu` | `GLMClient` (GLM-5.1), own rate-limiter + concurrency=1 gate | Only via UI hard-switch `pipeline_llm_provider`. |
| `anthropic` | `ClaudeClient` (real `complete_json`) | **No** — registered & implemented but no narrative call-site. |
| `openai` | `OpenAIClient` (real) | **No** — same; dead in the narrative brain. |

Two entry points: `build_llm(provider, model)` (direct, used by translator + auto-config) and `build_llm_for_tier(tier, settings, provider_override)` — the **main pipeline path**, `tier ∈ {pro, flash, flash_lite}`, `provider_override=None → gemini`.

**Tier matrix is a fiction worth flagging.** `llm_clients/tier_resolver.py` enforces an all-Lite constraint: balanced/quality profiles were removed, and **all three tiers (pro/flash/flash_lite) physically resolve to a Flash-Lite model** (`gemini-2.5-flash-lite` or `gemini-3.1-flash-lite-preview`). So `story_doctor`, `canvas_builder`, and `variants_generator` *ask for* `pro` but *get* Lite. Cold-cache or any unrecognized profile coerces to `fast` (all-Lite) — the pipeline can never escape Lite by design (cost control). "Pro inference" does not actually happen. Zhipu uses a flat `pro/flash/flash_lite → glm-5.1` map.

Fallbacks: tenacity retry (`retry.py`), JSON-repair (`json_parser.py`) for verbose Lite output, and a deterministic per-stage fallback on almost every stage (`_fallback_chunk`, `_fallback_ranked_evidence`, `_fallback_script`, `_fallback_variants`, `_heuristic_rhythm_report`). Caveat: these are **silent** — a quietly failing LLM degrades quality without raising an error.

### The four modes

`PerformanceSettings.narrative_mode` dispatches to one of:

| Mode | Orchestrator | Stages | Essence |
|---|---|---|---|
| **`bottom_up`** (default) | inline in `analysis.py` | ~13 | Full Kartoziya: 6 extraction agents → reduce/rank → story_doctor 3-act → variants → composer + 2 validators. Most expensive, most "directorial". |
| **`map_reduce`** | `narrative/map_reduce_orchestrator.py` | 5 | OpusClip-parity (docstring calls it "production target"). global ctx (1 call) → parallel chunk-score (N) → reducer (1) → boundary extend → ReelPlan. Density-based count. |
| **`viral_2026`** | `services/viral_arc_builder.py` | 3 | Simplest: chunk → parallel score → temporal-IoU dedup. 1 LLM call / ~20K-char chunk, multi-segment reels. |
| **`chaptered`** (`top_down`) | `narrative/orchestrator.py` | 6 | Per-chapter: chapters → hooks → arcs → cross-chapter rank. **Author-marked "broken"**, kept only for rollback. |

**Mode A — `bottom_up` (default), ~13 stages.** The "Манифест живого кадра 2026" (`prompts.py:_OPUSCLIP_MANIFESTO`) is welded into the system prompt of every call. Stages: (1) preference_memory loads liked anchors from prior jobs (not LLM); (2) **extraction — 6 agents × N chunks**, the main parallelism point, Flash-Lite, two waves with a deterministic coverage barrier between — Wave 1 reaction (`hook_hunter`, `emotional_peak_finder`, `humor_specialist`), Wave 2 meaning (`dramatic_irony_scanner`, `thesis_extractor`, `motif_tracker`), per-agent Gemini context cache TTL 1800s; (3) reduce+rank (Flash, hybrid Jaccard+embedding dedup, optional ensemble of N temperatures + median + veto); (4) cross_chunk_reducer (Flash-Lite, opt-in); (5) story_doctor (3-act arc + book-end, wrapped in a critique loop with rhythm_check); (6) rhythm_check (Flash + heuristic middle-sag); (7) visual_validator (Moondream, opt-in); (8) variants_generator (4 formats); (9) multi_arc_builder (opt-in, parallel per candidate-moment); (10) compose_reels (sync, target N + uniqueness filter); (11) coherence_validator (Flash-Lite, hook↔payoff, off/reject/resort, parallel); (12) closure_validator (Flash-Lite, semantic tail + extend to ASR sentence boundary, parallel, **no toggle**); (13) cover_selector (Moondream, opt-in) + per-reel scoring + trend lexicon.

**Mode C — `map_reduce`.** global_context_builder (1 Flash-Lite call, falls back to `canvas.central_theme`) → chunk_scorer MAP (massive parallel `Semaphore(narrative_chunk_parallel_max)`, each chunk → `RawClipCandidate[]`) → clip_reducer REDUCE (deterministic temporal+Jaccard dedup, then 1 curation/rank call) → boundary_extender (deterministic) → ReelPlan. Density target = `duration_min / 2`, capped 3–300.

**Mode D — `viral_2026`.** `_build_chunks` (overlapping) → parallel `_score_chunk` per chunk (Flash-Lite, prompt `viral_2026`) → `_dedupe` (temporal IoU) → ReelPlan sorted by composite score. **Known quirk:** this mode calls `build_llm_for_tier("flash_lite", settings)` *without* `provider_override`, so it is **always Gemini even when the UI selects zhipu** — every other stage threads the provider through. Looks like a bug, not a stub.

bottom_up builds "bottom-up" from evidence agents and directs a 3-act arc; map_reduce/viral cut whole clips "top-down" like OpusClip. **Only bottom_up runs coherence + closure validators.**

All parallelism flows through one shared Gemini token-bucket (`rate_limiter.py`, default 60 RPM), so the global RPM cap holds across every `gather`.

---

## 2.3 Vision & video (ML models + render path)

### ML models / external tools

| Tool | Role |
|---|---|
| **ffmpeg / ffprobe** (CLI subprocess, argv-list, no shell) | The real render engine + media probing. |
| **Moondream 2 GGUF** via llama-cpp-python (Metal, `n_gpu_layers=-1`) | Vision VLM: `query` (yes/no VQA), `caption`, `detect`. |
| **mediapipe** blaze_face | Face detection → normalized bboxes (auto-downloaded). |
| **OpenCV** (cv2) | Cursor template-matching (graceful `[]` if absent). |
| **librosa / silero-vad / parselmouth** | Beat/onset/RMS-emphasis/VAD/pitch for cut snapping & motion. |

No pyannote / no diarization anywhere (see 2.5).

### Render path (`pipeline_stages/render.py:run_render_stage`)

Per reel, one declarative `ProjectGraph` compiles to **one ffmpeg invocation** (`filter_graph_builder.py:build_filter_graph`). Seven phases: ReelPlan→segments (min/max duration clamp) → preset resolve (fill/fit, HEVC `hevc_videotoolbox`+`hvc1`) → face tracking (only if `face_tracker_enabled`, default False → static center crop) → initial graphs (zoom_plan + base_crop_plan + early ASS) → cut transforms (each toggle-gated, failures swallowed: pause_compression → breath → filler_removal → cut_snap → rhythm_snap → J/L cuts) → motion/zoom layer (emphasis punch-in + Ken Burns zoompan) → finalize (two-pass loudnorm measure, ASS resync) → compile + render.

filter_complex stages: **A** per-cut trim/setpts + crop (piecewise-linear x(t)/y(t)) + audio atrim + adaptive afade + concat → **B** zoom split/crop/scale/concat → **B+** motion zoompan → **C** subtitle burn (`subtitles=<.ass>`) → **D** pluggable effects → **F** intro/outro normalize → **G** loudnorm → encoder (`hevc_videotoolbox -tag:v hvc1`, +faststart, AAC, even-dim clamping). Subtitles via libass with per-word `{\pos}`, fonts discovered via `fc-list`.

### Vision features: real vs dormant vs orphan

**Real & wired:** Moondream VQA/caption/detect (but `detect` is a **9-region VQA heuristic → single fabricated bbox**, not real object detection), visual_validator (3×VQA per segment), visual_evidence_agent (7th extraction agent), cover_selector (6-frame VQA), face-tracked zoom & base-crop, emphasis motion (zoompan), split-screen 9:16 vstack, B&W effect (the only registered effect). All gated behind `VisionRuntimeSettings.enabled` (default **False**) and per-feature toggles.

**Dormant (compute-then-discard, UI toggle disabled, explicitly logged):** screencast cursor zoom (`render.py:1116`), deictic zoom (`render.py:1163`), mouth-sound removal (`render.py:776`). Detectors run (cursor detection burns full OpenCV template-match over frames) and the output is thrown away — "ZoomPlan merge / mute_zones API не реализован".

**Built but never called:** entire B-roll subsystem (`broll/*`), object_tracker (`build_zoom_plan` is always called without `object_track`).

**Orphans (zero references):** `person_cluster.py`, `match_cuts.py`, `eye_trace_continuity.py`, `transition_chooser.py`.

---

## 2.4 Audio DSP

All real signal processing, all wired into `render.py` (none faked, every extractor graceful-degrades to a named safe default and logs the reason).

| Service | Tech | Does |
|---|---|---|
| `audio_analyzer.py` | librosa, pyloudnorm, parselmouth, silero-vad, scikit-maad | Extracts ~15 features in parallel (SNR, LUFS/LRA, spectral, F0/HNR, VAD gaps, rhythm CV). |
| `vad.py` | silero-vad ONNX | `detect_speech_segments` (16k resample) + silence inversion. |
| `audio_normalizer.py` | ffmpeg `loudnorm` | EBU R128 two-pass (−14 LUFS); measurement pass parses stderr JSON; `None` on failure → single-pass. |
| `adaptive_leveller.py` | pyloudnorm | Per-3s-window LUFS → clamped (±6 dB) gain list applied via ffmpeg `volume`. |
| `beat_detector.py` | librosa | beat_track + onset_detect; snap cut boundaries to nearest beat/onset within ±150ms (<4 beats → treat as non-musical). |
| `breath_classifier.py` | librosa | RMS-band breath events to **preserve** during pause compression. |
| `mouth_sound_detector.py` | librosa STFT | Lip-smack/click detection → mute-zone defects. |
| `silence_cutter.py` | word-gaps + `fillers_ru.yaml` | Marks silence (gap≥0.6s) + fillers for removal (pure; render does the trim). |
| `filler_removal.py` | word-level `is_filler` | Splits CutSpecs to excise fillers (±30ms buffer). |
| `pause_compression.py` | VAD segments | Shortens pauses > 0.4s to 0.2s, optional punctuation-aware keep. |

On a default run only **loudnorm** (two-pass) and **cut_snap** (to word boundaries) actually fire; the rest wait for their toggles.

---

## 2.5 Transcription

Factory `transcribers/factory.py:build_transcriber`, unified `TranscriptResult` (word-level timestamps, `is_filler` from RU+EN `FILLER_LEXICON`), SHA256-keyed disk cache invalidated on backend/model mismatch.

- **stable-ts (MLX)** — `stable_whisper.load_mlx_whisper`, **default**. `vad=True` + `regroup=True` for ±20–30ms word timing (filler-removal / J-L cuts need it).
- **mlx-whisper** — Apple MLX local STT with word timestamps.
- **Deepgram nova-3** — cloud, deepgram-sdk v6, `filler_words=true` + paragraphs/utterances, tenacity 3× backoff.

**No diarization.** Despite the brief mentioning pyannote, there is no pyannote backend and no speaker labels anywhere in the stack.

---

## 2.6 Publishing (Publer)

**Real integration, not a stub** — separate from the pipeline, triggered only by explicit user action.

- Async `httpx` client (`publer/client.py`) against `https://app.publer.com/api/v1`. Auth: `Authorization: Bearer-API <key>` + `Publer-Workspace-Id`. Endpoints: `GET /workspaces`, `GET /accounts`, `POST /media` (multipart → `media_id`), `POST /posts/schedule` (→ `job_id`), `GET /job_status/{id}`. Retry: 3 attempts exp backoff; HTTP 429 → sleep 125s without consuming budget, capped at 5.
- **Networks:** Instagram Reels (`feed=True`) and YouTube Shorts (`privacy=public`); any other → `ValueError`.
- **Delivery worker** (`publer/worker.py`) — real background service started in `main.py` lifespan, **no-op if `PUBLER_API_KEY` unset**. Polls `list_pending_due` every 30s for `queued` assignments, uploads media (or reuses cached `publer_media_id`), schedules, marks `scheduled` (max 3 attempts, TOCTOU-guarded). The worker does **not** wait for `scheduled_at` — Publer is the scheduler; the worker delivers ASAP and Publer holds the post.
- **Scheduler** (`scheduler_service.py`): three modes (`per_date` round-robin, `single_day` staggered, `serial` one-reel/day with jitter), tz-aware via `zoneinfo` (default `Asia/Ho_Chi_Minh`). Captions are real LLM (Gemini Flash-Lite) conditioned on account profile. State machine: `draft → queued → uploading → scheduled` (or `failed`).
- **Known limits:** reel >200 MB → hard `ValueError` (URL-flow not implemented); re-encode path uses `h264_videotoolbox` (macOS-only — would fail on a Linux/Railway deploy).

---

## 2.7 What runs by default vs off/decorative

Default profile: `transcriber=stable_ts_mlx`, `llm_provider=gemini`, `narrative_mode=bottom_up`, `target_aspect=9:16`, `fit_mode=fill`, `vision.enabled=False`, no post-production preset.

**Executes on default (the real working spine):**
1. Upload → INSERT → proxy (1080p, possibly skipped) → fire-and-forget pipeline task.
2. Transcription (stable-ts MLX, word timing, disk cache).
3. silence_cut marking (applied at render).
4. **Full bottom_up narrative brain** — chunk → compress → canvas → preference_memory → 6 extraction agents → reduce/rank → story_doctor 3-act → rhythm_check → variants → compose → coherence_validator → closure_validator → per-reel scoring. Dozens of Gemini Flash-Lite calls. This is the live heart of the service.
5. Render: cut+concat, **static center-crop** (face_tracker OFF), `cut_snap` to words, ASS subtitle burn (builtin preset), **two-pass loudnorm −14 LUFS** (fires even with no post-prod preset, via defensive `AudioNormalizeSpec(enabled=True)` — BUG-#F), HEVC videotoolbox encode.
6. SSE live progress.

**Conditional:** translate (only non-RU source; RU = instant skip, target hardcoded to `TARGET_LANGUAGE`).

**OFF by default (no compute):** entire vision layer (visual_evidence 7th agent, visual_validator, cover_selector); face tracking (flagship reframing → static center-crop, due to mediapipe hang on Apple Silicon); multi_arc_builder; cross_chunk_reducer; reducer ensemble (size=1); all cut-transform DSP except cut_snap; zoom Stage B + punch-in + Ken Burns; whole post-production object (intro/outro/split-screen/B&W).

**Dormant (compute-then-discard):** screencast cursor zoom (toggle defaults True but consumer discards), deictic zoom, mouth-sound removal.

**Unreachable / dead:** B-roll subsystem; object_tracker; 4 orphan modules; anthropic/openai providers (registered, implemented, never selected); `chaptered` mode (author-marked broken); `JobStatus.cancelled` (enum value with no `mark_cancelled`).

**Decorative (computed, not applied):** `POST .../export` returns bitrate/LUFS + download_url but does **no transcode** (links the un-re-encoded mp4); `POST .../cancel` flips local status but does not retract the Publer post; the `pro`/`flash` tier names (all physically Flash-Lite).

**Default-run stage count: ~22 executing stages** — 5 ingest (probe, proxy, transcribe, translate-as-skip, silence_cut) + ~9 executing analyze sub-stages (chunk/compress, canvas, preference_memory, extraction, reduce_rank, story_doctor, rhythm_check, variants, compose) + 2 validators (coherence, closure) + per-reel scoring + 5 executing render layers (base_crop, cut_snap, subtitle burn, loudnorm, HEVC encode) + finalize. Publish (stage 9) is not part of the pipeline.
