# Stub-A — Vision Reality-Check (verification of Phase-1 Agent-D findings)

Root: `apps/backend/src/videomaker`. Method: call-trace by grep on every disputed
symbol/import, cross-checked against the live render pipeline
(`services/pipeline_stages/render.py`) and the frontend settings UI.

**Bottom line:** Agent-D's findings hold up under tracing, with **two
corrections** worth flagging:
1. `match_cuts.py` is a true orphan, but `transition_chooser.py` *implements*
   match-cut logic internally (aHash) — they are not the same thing; the
   `match_cuts` module is genuinely unused dead code separate from
   transition_chooser's own (also-orphan) match-cut rule.
2. The DORMANT toggles are **not all "disabled"** at the backend default.
   `screencast_cursor_zoom_enabled` defaults to **True**
   (`runtime_settings.py:478`). The UI is hidden (PerformanceSettingsClient.tsx
   :168-174), but the backend gate is open → for any `profile=screencast` job the
   OpenCV cursor detector **does run and burns compute**, output discarded. This
   is the worst kind of Potemkin: not just dead, but actively wasteful by default.

---

## Verdict table

| Module / Feature | Verdict | Proof (file:line) | Recommendation |
|---|---|---|---|
| **screencast cursor zoom** (`cursor_detector` + `spring_zoom_planner`) | DORMANT-computed-discarded | `render.py:1116` logs `screencast_cursor_zoom_dormant`; detector invoked `render.py:1133`; keyframes computed then `applier="deferred"` (`render.py:1147`) — never merged. Default ON (`runtime_settings.py:478`) → runs on every screencast job. | OЖИВИТЬ (top candidate) |
| **deictic zoom** (`deictic_zoom.py`) | DORMANT-computed-discarded | `render.py:1164` `deictic_zoom_dormant`; `inject_deictic_zoom_triggers(words, [])` called `:1177`, result logged then dropped `:1181`. Default OFF (`runtime_settings.py:496`). | OЖИВИТЬ |
| **mouth-sound removal** (`mouth_sound_detector.py`) | DORMANT-computed-discarded | `render.py:777` `mouth_sound_removal_dormant`; `detect_mouth_sounds` called `:790`, defects only counted/logged `:793`. No `mute_zones` API on ProjectGraph (grep `mute_zones` → only the dormant log strings). Default OFF. | OЖИВИТЬ (or OPT-IN) |
| **B-roll subsystem** (`broll/index,retriever,inserter`) | ORPHAN-never-called | grep `broll\|suggest_broll\|VisualEvidenceIndex` outside `/broll/` → **zero hits**. 294 LOC, no pipeline call-site. | УДАЛИТЬ (or full feature project) |
| **object_tracker** (`object_tracker.py`) | ORPHAN-never-called (effectively) | Imported only by `zoom_planner.py:47` as an optional param `object_track=None`. The sole live caller `render.py:566` `build_zoom_plan(...)` omits `object_track` entirely → always None → `zoom_planner.py:586` branch dead. 285 LOC. | УДАЛИТЬ or OPT-IN (depends on screencast object-follow roadmap) |
| **person_cluster.py** | ORPHAN-never-called | grep `person_cluster\|PersonCluster\|cluster_person*` outside module → **zero hits**. 196 LOC. | УДАЛИТЬ |
| **eye_trace_continuity.py** | ORPHAN-never-called | grep `eye_trace\|EyeTrace\|gaze` outside module → **zero hits**. 147 LOC. | УДАЛИТЬ |
| **match_cuts.py** | ORPHAN-never-called | grep `match_cuts\|find_match_cuts\|MatchCut` → only doc-comment text inside `transition_chooser.py` (no import). 131 LOC. | УДАЛИТЬ |
| **transition_chooser.py** | ORPHAN-never-called | grep `transition_chooser\|choose_transition\|TransitionChooser` outside module → **zero hits**. 204 LOC. (Its own internal match-cut/aHash logic is also unreachable.) | УДАЛИТЬ |
| **Moondream `detect`** | FAKE-heuristic | `moondream_local.py:259-298`: presence-VQA → 9-region position VQA → single fabricated bbox from `_POSITION_REGIONS`. `max_detections` explicitly ignored (`:269`). Docstring admits "GGUF не имеет нативного detect". | ОСТАВИТЬ-КАК-honest-heuristic (rename to avoid implying real detection); only consumer is the dead object_tracker path anyway |
| **face_tracker** | DISABLED-by-default | `runtime_settings.py:405` `face_tracker_enabled=False`; `render.py:269` gate → else-branch static center crop. Cause documented `render.py:274`: mediapipe CPU=0% hang on Apple Silicon, job `8a418e9b`. Implementation is real (mediapipe blaze_face). | ОСТАВИТЬ-КАК-OPT-IN until hang fixed |

**Confirmed WIRED-WORKS (not stubs):** full ffmpeg HEVC render path, emphasis
motion zoompan (`render.py:1194`, writes `motion_filter_expr` → applied), smart/
face zoom exprs (when face track present), split-screen, B&W effect, visual
validator / evidence agent / cover selector, STT + cache. No re-dispute.

**Dead-code tally (safe-delete candidates):** broll/* (294) + person_cluster
(196) + eye_trace_continuity (147) + match_cuts (131) + transition_chooser (204)
= **~972 LOC pure orphan**. Plus object_tracker (285) reachable only via a
permanently-None param.

---

## "Make it real" — per revival candidate

### 1. Screencast cursor zoom — TOP candidate, complexity **M**
- **Why first:** highest value (screencast is a named VisionProfile, this is its
  marquee feature), detector+planner already produce keyframes correctly, and a
  working sibling channel already exists.
- **Steps:** (a) The emphasis-motion path *already* proves keyframe→ffmpeg works:
  it serializes a `zoompan` expr into `graph.motion_filter_expr`
  (`render.py:1194`, applied in `filter_graph_builder`). Route the
  `spring_zoom_planner` `ZoomKeyframe[]` through the **same** `motion_filter_expr`
  channel instead of inventing the deferred "ZoomPlan merge" — sidesteps the
  `ZoomCommand`/`AnchorKeyframe` API extension entirely. (b) Add a
  keyframes→zoompan-expr builder (mirror `emphasis_motion.build_ffmpeg_motion_expr`).
  (c) Compose with emphasis expr (pick one or chain) — only conflict point.
  (d) Re-expose the already-persisted UI fields (PerformanceSettingsClient.tsx
  :168-174 — group + reset fn still in code).
- **Risk:** double-zoom stacking with emphasis motion if both active; needs a
  precedence rule. Default-ON gate should be flipped to only-run-when-applied so
  it stops wasting compute pre-revival.

### 2. Deictic zoom — complexity **S-M**
- Shares the exact same merge gap as #1. Once the `motion_filter_expr` route
  exists, deictic is just another keyframe source (word-anchored instead of
  cursor-anchored). `inject_deictic_zoom_triggers` already returns keyframes.
- **Risk:** trigger spam on filler words; needs min-interval debounce. Low.

### 3. Mouth-sound removal — complexity **M**
- Detector (`detect_mouth_sounds`) returns time zones; gap is a `mute_zones`
  channel on `ProjectGraph` → ffmpeg `afade`/`volume=0:enable='between(t,...)'`.
  This is a *different* (audio) plumbing than #1/#2, so it can't piggyback the
  zoom work — net-new audio-filter wiring in `filter_graph_builder`.
- **Risk:** clipping speech if detector over-fires (audio is unforgiving). Ship
  OPT-IN (default already False) with conservative thresholds. Medium.

**Not recommended for revival:** B-roll (L — needs an asset library + overlay
compositing layer that doesn't exist; it's a product, not a wiring task) and
object_tracker (depends on Moondream `detect` which is a ±20% heuristic — would
inherit garbage localization). Delete or shelve both.

---

## Top-3 revival candidates (summary)

1. **Screencast cursor zoom** — **M** — reuse existing `motion_filter_expr`
   channel; detector/planner already correct; flip wasteful default-ON gate.
2. **Deictic zoom** — **S-M** — free-rides on #1's keyframe→expr route once built.
3. **Mouth-sound removal** — **M** — needs separate audio `mute_zones` plumbing;
   ship OPT-IN with safe thresholds.

**Immediate hygiene regardless of revival:** (a) flip
`screencast_cursor_zoom_enabled` default to False or short-circuit the detector
when no applier exists — it currently runs OpenCV template-match per screencast
job for zero output. (b) Delete the ~972 LOC of true orphans (person_cluster,
eye_trace_continuity, match_cuts, transition_chooser, broll/*) unless a roadmap
ticket claims them. (c) Rename Moondream `detect`→`locate_heuristic` so no future
caller mistakes it for real object detection.
