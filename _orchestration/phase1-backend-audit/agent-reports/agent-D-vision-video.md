# Agent D — Vision, Video Effects, Render & Transcription

Root: `apps/backend/src/videomaker`. Scope = vision/, video_effects/, broll/, transcribers/, trackers, zoom/motion planners, cut/transition planners, renderer/composer/canvas, validators, subtitles/fonts.

Forensic verdict up front: the **render path and the core vision-assist features are real and pixel-bound**. A meaningful fraction of the "advanced" services are either explicitly self-labelled DORMANT in render.py, or are fully implemented modules with **zero call-sites in the live pipeline** (dead code shipped as if it were a feature). Details below.

---

## ML-модели и внешние тулзы

| Tool / Model | Where invoked | How |
|---|---|---|
| **ffmpeg** (CLI subprocess) | `vision/frame_cache.py:127`, `face_tracker.py:324`, `renderer`/`project_renderer`, `filter_graph_builder.py`, `split_screen.py` | argv-list `create_subprocess_exec` (no shell). Frame extraction (`-ss … -vframes 1`, `-vf fps=`), and the full render filter_complex graph. **This is the real render engine.** |
| **ffprobe** | `services/media.probe` | media dimensions/duration |
| **Moondream 2 GGUF** (vision VLM) | `vision/moondream_local.py:124` via **llama-cpp-python** `MoondreamChatHandler` | text model Q4_K_M + mmproj-f16, downloaded via `huggingface_hub.hf_hub_download` (`model_manager.py:99`). Metal backend, `n_gpu_layers=-1`. Methods: `query` (yes/no VQA), `caption`, `detect`. |
| **mediapipe** FaceDetector | `face_tracker.py:367` `mp_vision.FaceDetector` | model `blaze_face_short_range.tflite` auto-downloaded over https (`face_tracker.py:410`). Sampled frames → normalized bboxes. |
| **mlx-whisper** | `transcribers/mlx_whisper_backend.py:56` | Apple MLX local STT, word_timestamps |
| **stable-ts (MLX)** | `transcribers/stable_ts_mlx_backend.py:68` `stable_whisper.load_mlx_whisper` | default local STT; `vad=True`, `regroup=True`. ±20-30ms word timing. |
| **Deepgram nova-3** | `transcribers/deepgram_backend.py:87` `client.listen.v1.media.transcribe_file` | cloud STT, deepgram-sdk v6, tenacity retry. `filler_words/paragraphs/utterances` on. |
| **OpenCV** (`cv2`) | `cursor_detector.py:46`, `object_tracker` indirectly | template-match cursor sprites; **graceful-degrades to `[]`** if cv2 or templates absent. |
| **librosa/audio libs** | `beat_detector`, `emphasis_motion`, `punchline_detector`, `vad` (Silero) | beat/onset/RMS-emphasis/pitch detection for cut snapping & motion |

**pyannote: NOT present.** Task brief mentioned pyannote diarization — there is no pyannote backend and no speaker diarization anywhere in the transcriber stack. The `speaker`/`diariz` grep hits are unrelated (LLM narrative prompts). If the spec promised diarization, it is unimplemented.

---

## Путь рендера (детально, ffmpeg)

Orchestrated by `pipeline_stages/render.py::run_render_stage` → `_run_render_stage_via_project_graph` (7 phases). Per reel, one declarative `ProjectGraph` is compiled to **one ffmpeg invocation** by `filter_graph_builder.py::build_filter_graph`.

1. **ReelPlan → segments**: `renderer.coerce_segments` + `truncate_to_max_duration` (min/max reel duration from `config/export_presets.yaml`). Skips <0.25s and <min-duration reels.
2. **Preset resolve** (`_resolve_render_presets`): `load_presets` → fill/fit variant, HEVC `hevc_videotoolbox` + `hvc1` tag, two-pass-loudnorm-capable, subtitle style via `subtitle_styles.resolve_style`.
3. **Face tracking** (`_prepare_face_tracking`) — **only if `PerformanceSettings.face_tracker_enabled` (default False)**. mediapipe dense sample, disk-cached. Default path = static center crop (no face keyframes).
4. **Initial graphs** (`_build_initial_graphs`): per reel builds zoom_plan (`zoom_planner.build_zoom_plan`) + base_crop_plan (`build_base_crop_plan`, only `fit_mode=fill`) + early ASS write. Split-screen skips base_crop/zoom.
5. **Cut transforms** (`_apply_graph_transforms`, each toggle-gated, failures swallowed): pause_compression (Silero VAD) → breath_compression → filler_removal → cut_snap (word boundaries) → rhythm_snap (beat/onset via `beat_detector`) → J/L cuts (`jl_cut_planner`).
6. **Motion/zoom layer** (`_apply_zoom_layer`): emphasis punch-in + Ken Burns → `emphasis_motion.build_ffmpeg_motion_expr` produces a `zoompan` expr written to `graph.motion_filter_expr`. (Screencast cursor zoom + deictic zoom are DORMANT here — see below.)
7. **Finalize** (`_finalize_graphs`): two-pass loudnorm measurement (`audio_normalizer.measure_source_loudness`), ASS subtitle **resync** from final mutated cuts, dump `project_graphs.json`.
8. **Compile + render** (`_render_and_persist_reels` → `ProjectRenderer.render_many`, or `split_screen.render_split_single_pass`).

**filter_complex stages** (`build_filter_graph`):
- **A** per-cut `trim,setpts` + (base_crop `crop=…` with piecewise-linear `x(t)/y(t)` expr | preset scale) + `fps,setsar`; per-cut audio `atrim,asetpts` + adaptive `afade` (10-25ms, click suppression); `concat` (separate v/a concat when J/L cuts present, `render.py`/`filter_graph_builder.py:146`).
- **B** zoom: `split` → per-cmd `crop+scale` (static or piecewise-linear tracking) → `concat`.
- **B+** motion: `motion_filter_expr` (zoompan) between zoom and subs.
- **C** subtitle burn: `subtitles=<escaped .ass>`.
- **D** pluggable video effects (`graph.video_effects`, each `effect.filter_expr`).
- **F** intro/outro normalize (`scale+pad+setsar+fps`, audio `aresample`) + `concat`.
- **G** loudnorm single- or two-pass (`linear=true` when measured).
- **encoder**: `hevc_videotoolbox -tag:v hvc1 -allow_sw 1 -realtime 0 -prio_speed 0`, `+faststart`, AAC. Even-dimension clamping throughout (yuv420p / HEVC requirement).

Subtitles: `subtitles.py::write_ass` → libass `.ass` with per-word `{\pos}`; styles `subtitle_styles.py`; fonts discovered via `font_scanner.scan_system_fonts` (`fc-list`).

---

## Vision-фичи (реализовано / подключено к pipeline)

| Фича | Реализовано | Подключено к pipeline | Примечание |
|---|---|---|---|
| Moondream VQA/caption/detect | Да (`moondream_local.py`) | Да | `detect` is a **heuristic** (presence VQA + 9-region position → 1 bbox), not native object detection. Single instance only. |
| Visual validator (per-segment visual_score) | Да (`visual_validator.py`) | Да — `analysis.py:1165`, gated `vision_runtime.enabled` | real 3×VQA, disk-cached |
| Visual evidence agent (7th agent) | Да (`visual_evidence_agent.py`) | Да — `analysis.py:992`, merged into ranked at `:355` | real |
| Cover/thumbnail selection | Да (`cover_selector.py`) | Да — `analysis.py:1095` | 6-frame VQA scoring |
| Face tracking + face-aware base crop | Да (`face_tracker.py`, `zoom_planner`) | **Default OFF** (`face_tracker_enabled=False`); when off → static center crop | known mediapipe hang on M-series (render.py:266) |
| Smart/face-tracked zoom (Stage B) | Да (`zoom_planner.py`, real ffmpeg crop exprs) | Da (gated on `zoom_enabled`) | piecewise-linear tracking expr is genuinely emitted |
| Emphasis motion (punch-in + Ken Burns) | Да (`emphasis_motion.py` → zoompan) | Да (`render.py:1194`) | real zoompan expr |
| Split-screen 9:16 vstack | Да (`split_screen.py`, single-pass) | Да (gated `split_screen.enabled` + companion_path) | real |
| B&W effect | Да (`video_effects/bw.py` `hue=s=0`) | Да (only registered effect) | registry has just 1 effect |
| Object tracking (arbitrary label) | Да (`object_tracker.py`) | **NO** — `build_zoom_plan` called at `render.py:566` without `object_track`; param always defaults None | dead in live pipeline |
| Screencast cursor zoom | Да (`cursor_detector.py` + `spring_zoom_planner.py`) | **DORMANT** — `render.py:1116` logs `screencast_cursor_zoom_dormant`, "ZoomPlan merge API не реализован, UI toggle disabled" | detect/plan run, output discarded |
| Deictic zoom (вот/смотри/здесь) | Да (`deictic_zoom.py`) | **DORMANT** — `render.py:1163` `deictic_zoom_dormant`, output discarded | |
| Mouth-sound removal | Detector exists (`mouth_sound_detector.py`) | **DORMANT** — `render.py:776` `mouth_sound_removal_dormant`, "mute_zones API not implemented, UI toggle disabled" | |
| B-roll (index/retriever/inserter) | Да (`broll/*`) | **NO** — `VisualEvidenceIndex.build` / `suggest_broll_inserts` have **zero call-sites** outside the module | fully implemented, never invoked |

---

## Транскрипция / диаризация

- Factory `transcribers/factory.py::build_transcriber`: `stable_ts_mlx` (alias `stable_ts`, **default**), `mlx_whisper`, `deepgram`. Unknown name → `TranscriberError`.
- Unified `TranscriptResult` (word-level timestamps, `is_filler` flag from `FILLER_LEXICON` — RU + EN paraziti).
- `transcribe_with_cache` = SHA256-keyed disk cache, invalidated on backend/model mismatch.
- Deepgram: nova-3, `filler_words=true`, paragraphs/utterances → segments; tenacity 3× exp backoff.
- stable-ts: `vad=True`+`regroup=True` for tight word timing (rationale: filler-removal/J-L cuts need it).
- **Diarization: none.** No pyannote, no speaker labels.

---

## Сервисы (таблица)

| Service | Назначение | Вход → выход | Ключевые символы |
|---|---|---|---|
| vision/moondream_local.py | Moondream 2 GGUF VLM | image Path → query/caption/detect | `MoondreamLocalClient.query/caption/detect:227/243/259`, `_load_llama_sync:120` |
| vision/model_manager.py | HF download Moondream GGUF | cfg → 2 file paths | `ensure_model_available:71` |
| vision/factory.py / registry.py | provider singleton + registry | cfg → VisionClient\|None | `build_vision_client:32` (None when `vision_enabled=False`) |
| vision/frame_cache.py | ffmpeg frame extract + VQA result cache | video,ts → JPEG + JSONL | `FrameExtractor.extract:87`, `VisionResultCache:159` |
| vision/rate_limiter.py | GPU concurrency semaphore | — | `VisionRateLimiter` |
| visual_validator.py | per-segment visual_score/flags | StoryScript → StoryScript | `validate_arc:83` |
| visual_evidence_agent.py | frame timeline (caption+person) | video → VisualEvidenceResult | `run_visual_evidence_agent:87` |
| cover_selector.py | best thumbnail frame | reel → CoverResult | `select_cover:74` |
| composition_scorer.py | geometric face-centering score | face_track,t → score | `compute_face_centering_score`, `is_off_center` |
| face_tracker.py | mediapipe face track + interp | video → FaceTrackResult | `track_faces:214`, `best_face_at:103` |
| object_tracker.py | VLM arbitrary-object track | video,label → ObjectTrack | `ObjectTrack` (**unwired**) |
| person_cluster.py | — | — | **ZERO refs (orphan)** |
| profile_detector.py | classify vision profile | used by api/routes/jobs | `detect_profile` (API only, not render) |
| profile_masks.py | per-profile composition mask | profile → ProfileMask | used in render |
| zoom_planner.py | face/obj-aware crop & zoom plans → ffmpeg exprs | segments,face_track → ZoomPlan/BaseCropPlan | `build_zoom_plan:209`, `build_base_crop_plan:801` |
| emphasis_motion.py | punch-in + Ken Burns zoompan | audio → motion expr | `detect_emphasis_moments:106`, `build_ffmpeg_motion_expr:295` |
| spring_zoom_planner.py | screencast spring-damped zoom | cursor events → keyframes | `plan_screencast_zoom:41` (**dormant consumer**) |
| cursor_detector.py | OpenCV cursor template match | video → CursorEvent[] | `detect_cursor_events:33` (**dormant consumer**) |
| deictic_zoom.py | word-anchored zoom triggers | words → keyframes | `inject_deictic_zoom_triggers:36` (**dormant consumer**) |
| eye_trace_continuity.py | — | — | **ZERO refs (orphan)** |
| match_cuts.py | — | — | **ZERO refs (orphan)** |
| transition_chooser.py | — | — | **ZERO refs (orphan)** |
| cut_snapper.py | snap cuts to word boundaries | cuts,words → cuts | `snap_cuts_to_words` (wired) |
| jl_cut_planner.py | J/L audio-lead cuts | cuts → cuts | `plan_jl_cuts` (wired) |
| split_screen.py | 9:16 vstack single-pass | graph+companion → mp4 | `render_split_single_pass` (wired) |
| renderer.py | preset load + segment coerce | yaml → presets | `load_presets:46` (no subprocess itself) |
| filter_graph_builder.py | ProjectGraph → ffmpeg argv | graph → CompiledGraph | `build_filter_graph:75` |
| canvas_builder.py / canvas_embedder.py | narrative canvas + text embeddings | — | wired in analysis/narrative |
| extraction_coverage.py | coverage summary | — | wired in orchestrator |
| pacing_profile.py | pacing model | — | wired via reels_composer/analysis |
| video_effects/* | pluggable post-crop fx | ctx → filter expr | only `BWEffect` registered |
| broll/* | keyword B-roll retrieval | StoryScript,index → suggestions | **unwired** |
| transcribers/* | STT backends + cache | audio → TranscriptResult | factory `build_transcriber:31` |
| subtitles.py / subtitle_styles.py / font_scanner.py | ASS gen + styling + font discovery | spec → .ass | `write_ass:77`, `scan_system_fonts:59` |

---

## Подозрения на заглушки

1. **DORMANT (run-but-discarded, explicitly logged)** — screencast cursor zoom (`render.py:1116`), deictic zoom (`render.py:1163`), mouth-sound removal (`render.py:776`). Each computes results then throws them away because the "ZoomPlan merge / mute_zones API не реализован". UI toggles disabled. These burn CPU (cursor detection runs full OpenCV template match over frames) for zero output. The honesty is commendable but these are placeholders shipped as features.
2. **Unwired-but-complete subsystems** — `broll/` (index+retriever+inserter, `suggest_broll_inserts` never called), `object_tracker.py` (`build_zoom_plan` always called without `object_track`). Real code, no live path.
3. **Orphans (zero references anywhere)** — `person_cluster.py`, `match_cuts.py`, `eye_trace_continuity.py`, `transition_chooser.py`. Dead modules.
4. **Moondream `detect` is heuristic, not detection** — presence VQA + 9-region position string → single fabricated bbox (`moondream_local.py:259`). `max_detections` ignored. Anything downstream treating it as real localization (e.g. B-roll person_position, object_tracker) inherits coarse ±20% accuracy.
5. **Face tracking default OFF** — the headline "smart reframing" feature is opt-in (`face_tracker_enabled=False`) due to a confirmed mediapipe hang on Apple Silicon (`render.py:266`). Default output is static center crop. Not a stub, but the marquee vision feature is dark by default.
6. **`profile_detector` API-only** — used by `api/routes/jobs.py` but not inside the render/analysis pipeline; profile selection in render comes from elsewhere (`profile_masks`).

---

## Открытые вопросы

1. Diarization was in the brief but is absent — was it descoped, or is a pyannote backend expected?
2. Are the 4 orphan modules (person_cluster, match_cuts, eye_trace_continuity, transition_chooser) abandoned experiments safe to delete, or pending wiring?
3. The 3 DORMANT features still execute their detectors (cursor_detector runs OpenCV across frames). Should detection be short-circuited when the apply-path is disabled, to stop wasting compute?
4. Should B-roll (`broll/*`) be wired into the render overlay path, or removed?
5. `object_tracker` exists solely to feed `zoom_planner` but render never supplies it — intended for screencast object-follow that was never finished?

---

## Краткое резюме для родителя

**ML-модели/тулзы:** ffmpeg/ffprobe (real render engine), Moondream 2 GGUF via llama-cpp-python (Metal), mediapipe blaze_face (face), mlx-whisper + stable-ts-MLX + Deepgram nova-3 (STT), OpenCV (cursor), librosa/Silero (beat/VAD/emphasis). **No pyannote / no diarization.**

**Реально работает в pipeline:** полный ffmpeg HEVC render (cut/concat/crop/zoom/subtitle-burn/loudnorm/intro-outro), visual_validator, visual_evidence_agent, cover_selector, emphasis motion (zoompan), face-tracked zoom & base-crop (но face-tracking default OFF → static center crop), split-screen, B&W effect, transcription+cache.

**Заглушки / dormant / dead:**
- DORMANT (compute then discard, toggles disabled): screencast cursor zoom, deictic zoom, mouth-sound removal.
- Implemented-but-never-called: entire B-roll subsystem, object_tracker.
- Orphan modules (zero refs): person_cluster, match_cuts, eye_trace_continuity, transition_chooser.
- Moondream `detect` is a 9-region VQA heuristic, not real object detection (single bbox, coarse).

**Топ-5 находок:**
1. 3 video features (cursor zoom / deictic zoom / mouth-sound removal) are DORMANT — detectors run, output is thrown away; UI toggles disabled.
2. B-roll engine and object_tracker are fully built but have no pipeline call-site (dead weight).
3. Four service modules are total orphans with zero references.
4. No diarization despite brief; STT is solid otherwise.
5. Flagship face-tracked reframing is OFF by default (mediapipe M-series hang) — default render is static center crop, and Moondream `detect` is heuristic not real detection.
