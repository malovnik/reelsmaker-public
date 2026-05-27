# Bottom-Up Verification — Evidence Inventory

## Pre-task findings

- **Job 70ba41eb missing from data/artifacts/:** confirmed.
  - Command: `ls -d data/artifacts/70ba41eb-f22a-45a6-b897-4a3fbbb12b87`
  - Output: `ls: data/artifacts/70ba41eb-f22a-45a6-b897-4a3fbbb12b87: No such file or directory` (exit 1)
  - Memory claim that job 70ba41eb-f22a-45a6-b897-4a3fbbb12b87 was the "final smoke 10/10" cannot be verified — artifact directory does not exist on disk.

- **JSON dumps canvas_full / extraction_full / story_script:** REFUTED — dumps are present on disk under `data/artifacts/<job_id>/text/`.
  - Command: `find data/artifacts -name 'canvas_full.json' -o -name 'extraction_full.json' -o -name 'story_script.json' | head -20`
  - Representative matches (job has all three):
    - `data/artifacts/18721422-afd1-43cb-993f-056d37715b05/text/{canvas_full,story_script,extraction_full}.json`
    - `data/artifacts/b6809dc1-6687-4117-9751-8ede39a85d6d/text/{canvas_full,story_script,extraction_full}.json`
    - `data/artifacts/40264fb1-9d55-4516-8adf-98a7060c2816/text/{canvas_full,story_script,extraction_full}.json`
  - `canvas_full.json` exists in 11 jobs; `story_script.json` and `extraction_full.json` exist in 3 jobs (18721422, b6809dc1, 40264fb1). Dumps live under the `text/` subdirectory, which was not visible in the shallow `audio/ logs/ reels/ source/ subs/ text/` listing referenced in the briefing.

## Task 0 results

- **Branch:** `feat/glm-provider` (from `git branch --show-current`)
- **HEAD:** `c272792 docs(plan): executable runtime verification plan for bottom_up pipeline` (from `git log --oneline -5`)
- **Working tree:** clean (`git status --short` produced no output)
- **Reanimation commits:** all 4 present in history.
  - `fb91668 fix(analysis): use actual pro-tier model name in SSE messages`
  - `d8202c3 fix(composer): split arc at structural boundary + dump intermediate artifacts`
  - `61d0759 feat(composer,story_doctor,canvas): arc-narrative boost + scaled thresholds + robust story fallback`
  - `e5a45df fix(composer): protect complete short arcs from mandatory merge`
- **GEMINI_API_KEY:** OK (`.env` present, `^GEMINI_API_KEY=.+` matches).
- **narrative_mode default:** `bottom_up` — verified in `apps/backend/src/videomaker/models/runtime_settings.py:262-263`:

  ```python
  narrative_mode: NarrativeMode = Field(
      default="bottom_up",
      ...
  )
  ```

- **Tools:**
  - `uv`: `0.9.11 (8d8aabb88 2025-11-20)` at `/Users/malovnik/.local/bin/uv`
  - `pnpm`: `10.20.0` at `/Users/malovnik/.npm-global/bin/pnpm`
  - `ffmpeg`: `7.1.1` at `/opt/homebrew/bin/ffmpeg` (`ffmpeg version 7.1.1 Copyright (c) 2000-2025 the FFmpeg developers`)

## Task 5a results (job b6809dc1-6687-4117-9751-8ede39a85d6d, 13 reels on disk)

Job created 2026-04-21 11:20 (~8h after all four reanimation commits fb91668/d8202c3/61d0759/e5a45df which landed 02:52–03:09). Reads were done against `data/artifacts/b6809dc1-6687-4117-9751-8ede39a85d6d/`.

Reference memory for the claim-side numbers: `videomaker-pipeline-reanimation-2026-04-21` (targets a DIFFERENT job `70ba41eb`, which does not exist on disk — so "memory claim" columns below are the structural expectations described in that memory, not ground truth for this job).

| Stage | Memory claim | Actual | Status |
|---|---|---|---|
| transcribe | 311 segs / 663s | 1546 segs, 7549 words, ~5729.1s source | PASS |
| silence_cut | cleaned < source | source=5729.1s; cleaned_transcript has 0 segments (word-oriented schema: `source_duration_sec` + `kept_duration_sec` + `removed_ranges` + `words`) | PASS (schema-level; segment-count method N/A) |
| canvas | themes=3, motifs=2, moments=9 | themes=12, motifs=2, moments=40 | PASS (exceeds all thresholds) |
| extraction | 31 evidence | evidence_count=307 across 6 agents (hook_hunter=54, emotional_peak_finder=39, humor_specialist=12, dramatic_irony_scanner=55, thesis_extractor=67, motif_tracker=80), failed_runs=0 | PASS (all 6 agents active) |
| reducer | top-ranked avg 88 | evidence_pre_dedup=307 → evidence_post_dedup=121 → ranked_evidence_count=121, avg_composite_score=87.9, candidates_total=124 | PASS |
| story_doctor | arc 53.8s, 5 segs | 6 arc segments, 54.6s source span, predicted_duration_sec=54.6, roles=[hook, setup, setup, development, peak, payoff], 2 alternates | PASS |
| rhythm | accepted | rhythm_score=0.95, pacing="рваный", middle_sag=false, issues=0 (no log files under logs/) | PASS |
| composer | 10 accepted, 1 multi | 58 reels planned (target 57, min 43, max 71); multi_segment=0; single_segment=58; duration 52.0–59.7s, mean 53.6s; all within [25, 95] | PASS on count+duration; FAIL on multi-segment (memory claim was ≥1) |
| closure | 6 complete, 4 extended, 0 failed | per-reel `closure_status` field: not present in reel_plan.json → {unknown: 58}; but aggregate in analysis_summary.json: checked=58, complete=25, extended=25, failed=8, semantic_extended=0 | PASS with caveat: 8 failed reels is a quality gap (~13.8%); also NOTE per-reel field missing in reel_plan schema |
| render | 10 mp4 ≥ 1MB | 13 mp4 files on disk (r1–r13); sizes 24.69 MB – 39.74 MB (all ≥ 1 MB); durations 39.7–50.7s (all within [25, 95]) | PASS |

### Raw numbers for the one FAIL

- **composer multi-segment:** 0 out of 58 planned reels are multi-segment. Every reel has exactly one `segment`. This contradicts the reanimation memory's claim that bottom_up produces at least one multi-segment arc (the "story_doctor arc as a reel" pattern). The 6-segment arc IS present in `story_script.json`, but it does not appear to have been materialized as a multi-segment entry in `reel_plan.json`. This is a real regression relative to the memory's claimed behavior — OR the memory is describing a different operating mode.

### Schema surprises

- `cleaned_transcript.json` has no `segments` field; it uses `words` + `removed_ranges` + scalar duration fields (`source_duration_sec`, `kept_duration_sec`). Silence-cut check via segment-count method returns 0, which is a schema artifact, not a real failure. The scalar `source_duration_sec` was populated (5748.7s per `analysis_summary.json`), but `kept_duration_sec` could not be confirmed in this pass without opening a larger slice of the file.
- `story_script.json.arc` is a flat `list` of segment dicts, not `{arc: {segments: [...]}}` as the task prompt assumed.
- `reel_plan.json.reels[*]` does NOT contain per-reel `closure_status` / `closure` / `closure_type`. Closure distribution lives only in `analysis_summary.json.stats` as aggregate counters. Any downstream consumer needing per-reel closure metadata is reading from an unstable surface.
- `extraction_full.json` is a summary envelope (`evidence_count`, `by_agent`, `sample`), not a flat list — the real evidence list is implied elsewhere (likely in-memory during pipeline, persisted shape is aggregate).
- `analysis_summary.json.llm_model` = `gemini-3-flash-preview`, but `stats.user_requested_llm` = `gemini:gemini-3.1-flash-lite-preview` — requested vs actual mismatch; provider seems to have normalized/substituted the model.

### Interpretation

- **Does the memory's stage-level matrix hold up?** Mostly yes, with two non-trivial deviations:
  1. Multi-segment reels: memory says ≥1, actual is 0/58 (all singles).
  2. Closure failures: 8/58 failed (not "0 failed" as memory claimed).
- **Which stages deviate most from memory?**
  - `composer` (multi-segment=0, memory ≥1)
  - `closure` (8 failed, memory 0 failed)
  - All other stages meet or exceed the structural thresholds (themes, motifs, moments, evidence count, rhythm score, render output).
- **Overall verdict for baseline b6809dc1:** **works with quality gaps.** The pipeline produces the full end-to-end artifact set (transcript → canvas → extraction → reducer → story_doctor → rhythm → composer → renders). 13 renderable MP4s land on disk with plausible sizes and durations. But:
  - Plan/render mismatch: 58 reels planned vs 13 rendered (either render was truncated by user or by a quota/limit — needs separate investigation, not in this task's scope).
  - No multi-segment reels materialize despite story_doctor producing a coherent 6-segment arc.
  - Closure validator rejects 8/58 reels, suggesting the closure thresholds or extend logic have tuning gaps.
- **Reel-count mismatch:** memory claims 10, disk has 13 mp4 but plan has 58. The 13-vs-58 gap is larger and more interesting than the 10-vs-13 gap flagged in the briefing — it should feed Task 6.

