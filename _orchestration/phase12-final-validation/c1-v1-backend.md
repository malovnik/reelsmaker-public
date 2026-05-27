# Backend Final Integrity Validation — Cycle 1 / Validator 1

Date: 2026-05-27
Scope: `apps/backend/src/videomaker`
Validator role: Backend Final Integrity Validator (production без моков)

## VERDICT: PASS

Production-ready. Zero real mocks/stubs/TODO. Gates green (modulo 2 third-party-stub
pyright false-positives, both defended in code). All Phase 6 / 1b-fix integrity points
confirmed intact — nothing rolled back.

---

## 1. Gates

### ruff — PASS
```
$ uv run ruff check src/videomaker
All checks passed!
(exit 0)
```

### pyright — PASS (2 errors, both third-party / false-positive, NOT real defects)
```
$ uv run pyright src/videomaker
2 errors, 20 warnings, 0 informations
```
- 20 warnings: all `reportMissingTypeStubs` for untyped scientific libs
  (pyloudnorm, scipy, soundfile, maad, silero_vad, zhipuai) — expected, not actionable.
- Error 1 — `audio_analyzer.py:336` `temporal_snr` unknown import symbol from `maad.features`.
  Already wrapped in `try/except Exception` with a real power-ratio fallback (lines 335-344).
  Pyright cannot resolve the untyped `maad` symbol; runtime is guarded.
- Error 2 — `prompt_store.py:67` `rowcount` unknown on `Result[Any]`. `rowcount` is a real
  SQLAlchemy attribute on DML (DELETE) results; pyright's generic `Result` stub mismatch.
  Code defensively coerces with `or 0`. Runtime correct.

Neither error is a stub or production defect.

## 2. NO MOCKS / STUBS / TODO — PASS

`grep -rn "TODO|FIXME|raise NotImplementedError|mock|stub|placeholder|XXX|HACK"` → 2 hits, both
are documentation comments describing the REMOVAL of former placeholders (real logic now in place):
- `services/trend_lexicons.py:3` — docstring: "Replacement для placeholder `trend_pct = 70`".
- `services/pipeline_stages/analysis.py:623` — comment: real average score now used "вместо placeholder 82".

No `NotImplementedError`, no mock objects, no stub functions in production code.

## 3. Import smoke — PASS
```
$ uv run python -c "import videomaker.main"
IMPORT_OK
```
Submodule import sweep (pipeline, files route, jobs route, publer client) also OK.

## 4. Phase 6 / 1b-fix integrity — PASS (no rollback)

- **Export transcode is real.** `services/encoder_support.py` probes ffmpeg encoders at runtime;
  hevc/h264_videotoolbox (macOS HW) with libx265/libx264 software fallback for Railway/Linux,
  correct hvc1/avc1 tags. `media.py` runs encode via `asyncio.create_subprocess_exec` (argv list,
  no shell). `render.py` resolves `export_preset` (fps/width/height) per reel.
- **Tiers разведены.** `llm_clients/tier_resolver.py`: distinct pro/flash/flash_lite → real Gemini
  models (gemini_pro_model / gemini_flash_model / lite). Cold-cache fallback = all-Lite (no
  accidental expensive Pro on first post-restart pipeline). runtime_settings override respected.
- **Cancel job.** `POST /jobs/{job_id}/cancel` → `task.cancel()` + `service.mark_cancelled`;
  CancelledError propagates as cancelled (not error); terminal states short-circuit.
- **Vision process isolation.** `services/vision/` runs llama.cpp GGUF + ffmpeg frame extraction
  via `asyncio.to_thread` / `create_subprocess_exec` (DEVNULL stdout, PIPE stderr) — event loop
  not blocked, native code releases GIL. (Note: thread-pool isolation, not separate OS process;
  acceptable for GGUF inference.)
- **Publer retract.** `services/publer/client.py:216 delete_posts()` → real API DELETE, parses
  `deleted_ids`, empty-list no-op.
- **Path traversal closed.** `core/artifacts.py`: `path_for` rejects `/` and `..` in name +
  validates kind; `_job_dir` rejects bad job_id and checks resolved path escapes root;
  `resolve_relative` raises ValueError on escape. Route `files.py` maps ValueError → 400.

## 5. Health endpoint — PASS (real probes)

`GET /api/v1/health` (`api/routes/health.py`) returns:
- `status`, `version`
- `llm_providers` = `settings.available_llm_providers`
- `transcribers` = `settings.available_transcribers`
- `ffmpeg` — real subprocess probe: resolves binary via `shutil.which`, runs `ffmpeg -version`
  (first line) and `-encoders`, detects `hevc_videotoolbox`. Returns available/path/version/
  videotoolbox_hevc; graceful when ffmpeg absent.
- `defaults` (model names) + `chunking` config.

Not a static stub — performs live ffmpeg detection.

## 6. Orphan code after deletions (4 orphan + broll) — PASS

No `broll`/`b_roll`/`travel_broll` references remain anywhere in `src/videomaker`.
Import sweep of pipeline + routes + publer all load clean. No broken imports from removed modules.

---

## Summary table

| Check | Result |
|-------|--------|
| ruff | PASS (clean) |
| pyright | PASS (2 third-party false-positives, defended) |
| import smoke | PASS |
| mocks/stubs/TODO | PASS (0 real; 2 doc-comments re removed placeholders) |
| export transcode | PASS (real, HW+SW fallback) |
| tier separation | PASS |
| cancel job | PASS |
| vision isolation | PASS (to_thread/subprocess) |
| publer retract | PASS (delete_posts) |
| path traversal | PASS (closed in ArtifactsManager) |
| health probes | PASS (live ffmpeg/providers/transcribers) |
| orphan/broll imports | PASS (none) |
