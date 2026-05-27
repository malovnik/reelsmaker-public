# C2-V3 — Backend Security & Data Integrity Deep Validation

Role: Backend Security & Data Integrity Deep Validator. Scope: `apps/backend/src/videomaker`.
Cycle 2 of 3. Deep re-verification of cycle-1 findings + adversarial path-traversal / data-destruction hunt.

## VERDICT: FAIL

One real data-destruction vulnerability (`DELETE /proxies/{sha256}` glob injection). Everything else (path-traversal in artifacts/reels/export, vision isolation, SQLite WAL, Publer honesty, restart recovery, secrets) holds up to scrutiny.

---

## 1. Path-traversal — MOSTLY CLOSED, one hole

### ArtifactsManager (`core/artifacts.py`) — CLOSED
- `job_dir`: rejects empty / `"/"` / `".."`, resolves, then containment-checks `self.root not in path.parents and path != self.root`. Solid.
- `path_for`: `kind` allowlist (`ALLOWED_KINDS`) + `name` rejects `"/"`/`".."`. Solid.
- `resolve_relative`: resolves candidate then containment-checks against `job_dir`. Used by `delete_job(hard)` / `copy_reels_to_saved` for DB-stored `artifact.path` — safe even if a malicious relative path got into the DB.
- `saved_dir`: subfolder sanitized (`"/"`/`".."` rejected). Folder name is server-generated (`<timestamp>_reelsN`), not user input.

### reel_id (`api/routes/jobs.py`) — CLOSED (defence-in-depth)
- `_validate_reel_id`: `re.fullmatch(r"^[A-Za-z0-9_-]+$")` + max 128. Rejects `.`, `/`, `..` outright.
- `_reel_artifact_path`: independent `resolve()` + `base_resolved not in candidate.parents` containment. Verified: a legit `v0_r1.mp4` passes; any traversal candidate fails containment. Even if regex were bypassed, containment blocks escape.
- Applied consistently on all reel routes: subtitles GET/PATCH, export POST.

### Export path (`export_reel_with_preset`) — CLOSED
- `preset` checked against `EXPORT_PRESETS` allowlist before use.
- Output path built via `_reel_artifact_path(reels_dir, reel_id, f".{preset}.mp4")` → same validated/contained builder. ffmpeg argv passed as list (no shell), source = validated reel path. No injection.

### files.py download — CLOSED
- Delegates entirely to `ArtifactsManager.path_for` (kind allowlist + name sanitization) + `is_file()` check.

### HOLE — `delete_proxy` glob injection (`services/proxy.py:399` via `api/routes/proxies.py:104`)
`DELETE /proxies/{sha256}` validates only `len(sha256) >= 8`, then:
```python
for path in cache_dir.glob(f"{sha256}__*.mp4"):
    path.unlink()
```
`sha256` is interpolated raw into a glob pattern. Verified empirically:
- `sha256 = "********"` (8 chars, passes length check) → pattern `********__*.mp4` matches **every** proxy in the cache → mass-delete of unrelated cached proxies (data destruction beyond the single intended source).
- `sha256 = "../<anything>"` → glob `..` segment traverses **out of** `cache_dir` (confirmed: `glob('../sub/*__*.mp4')` resolves siblings outside the directory). Combined with `*` this can match/delete `.mp4` files outside the proxy cache.

Impact: destructive, no auth (accepted for local app) but the input is a path/glob param — a malformed or crafted value silently wipes the whole proxy cache or escapes the cache dir. This is exactly the "case удаление за пределы ожидаемого" the task asks to find. Severity: HIGH (data loss / scope escape), even single-user (a buggy frontend call or copy-paste of a wildcard nukes the cache).

Fix: validate `sha256` against `^[0-9a-fA-F]{8,64}$` before globbing (or `glob.escape`), reject anything else with 400.

---

## 2. Destructive open endpoints — SAFE except proxy above

- `DELETE /jobs/{id}?purge=nuke` (`jobs.py:594`): scoped strictly by `job_id`. Deletes only `Artifact.where(job_id==id)`, the single `Job` row, `source_path` (file + empty parent via `is_file()`/`is_dir()` guards), and `artifacts_manager.job_dir(job_id)` (itself traversal-guarded). `job_id` is server-generated UUID-style; `job_dir` rejects `..`/`/`. No cross-job or out-of-tree deletion. Safe.
- `purge=hard`: deletes only `reel_output` artifacts with `liked != "like"` for that job; unlink via `resolve_relative` (contained). Liked reels, proxy, transcript preserved. Safe.
- `DELETE /jobs/{id}/artifacts/{artifact_id}`: kind-restricted to `reel_output`; will not touch proxy/transcript. Safe.
- `DELETE /proxies/cleanup`: LRU by mtime within `app_proxies_dir`. `max_gb` clamped: negative → settings default; `max_gb=0` is legitimate ("evict all") and stays inside cache dir. Safe.
- Scheduler deletes (`delete_account_profile`, assignment cancel/retry): scoped by id, DB rows only. Safe.

`copy_reels_to_saved` (`jobs.py:724`): reel_ids filtered by `job_id` + `reel_output` kind in SQL; raises if none belong to job. Copy (not move), contained dst. Safe.

## 3. Vision isolation (face_tracker.py) — FACT: SUBPROCESS, not thread

The cycle-1 validator's doubt is **resolved**. `_detect_faces_in_subprocess` (line 442) is the real path used by `track_faces` (line 284):
- `ctx = mp.get_context("spawn")` → spawned **process** (`ctx.Process`, `daemon=True`).
- Result via `mp.Queue`; parent waits with `asyncio.wait_for(asyncio.to_thread(queue.get), timeout=timeout_sec)` (default 600 s).
- On timeout: `_kill_process()` → `terminate()` + `join(5s)`, then `kill()` + `join(5s)`. Raises `FaceTrackerError` → render falls back to center-crop.
- `finally` always reaps the process (no zombie) and closes the queue.

The sync `_detect_faces_in_frames` docstring still says "запускается через asyncio.to_thread" (stale comment, line 368-369) — but the actual caller is the subprocess worker `_detect_faces_worker`, NOT `to_thread`. The hard-kill-on-timeout requirement is met by subprocess. (Only `to_thread` use is the *blocking wait on the queue*, which is itself bounded by `wait_for`.) Confirmed correct.

## 4. SQLite — WAL + busy_timeout APPLIED (`core/db.py`)

`_configure_sqlite_connection` on every new connection sets:
- `PRAGMA foreign_keys=ON` (CASCADE works)
- `PRAGMA journal_mode=WAL` (concurrent readers don't block writer)
- `PRAGMA busy_timeout=30000` (30 s wait instead of instant "database is locked")
Plus engine `connect_args={"timeout": 30}`. Registered via `event.listen(... "connect" ...)` only for sqlite URLs. Parallel writes (concurrent ffmpeg renders / jobs) serialize safely with 30 s wait. Correct.

## 5. Publer retract — HONEST codes, does not lie

`POST /assignments/{id}/cancel` (`scheduler.py:720`):
- already `published` → **409** "нельзя отозвать опубликованное", local status untouched.
- has `publer_post_id` & not published → real `DELETE /posts` to Publer; on `PublerClientError` → **502** "не удалось отозвать… статус не изменён", local status untouched (no false "cancelled").
- only `publer_job_id`, no `publer_post_id` → **409** "id ещё не сверён", untouched.
- no publer id (never sent) → local-only flip to `cancelled` (honest: nothing to retract).
No path flips to `cancelled` after a failed remote delete. Correct.

## 6. Data integrity / persistence — SOLID

- Stores persist via SQLAlchemy `session_scope` (commit on success, rollback on exception). Artifact JSON writes are atomic (`.tmp` + `replace`) in `artifacts.write_json`, face cache, proxy (`.partial` + `replace`), model download.
- Restart recovery: `reset_stale_running_jobs` (`jobs.py:908`) flips all `running` → `error` ("interrupted by application restart") on lifespan startup (`main.py:75`). No job stuck in `running` after crash. Confirmed.
- Job flush races: `_pending` / `_last_flush` mutations guarded by `self._lock` (asyncio.Lock). `mark_done`/`mark_error` pop pending under lock then write final state in a fresh session. Single-process FastAPI → no cross-process race. Proxy generation guarded by atomic `O_CREAT|O_EXCL` lockfile with stale-orphan cleanup. Safe.

## 7. Secrets — NO HARDCODED KEYS

`grep -rn "AIza|sk-[A-Za-z0-9]|api_key=...|secret=...|token=..."` over `*.py` returned only docstring mentions of "cache" in `frame_cache.py` / `transcribers/cache.py` — zero real matches. All credentials (`publer_api_key`, LLM keys) read from `settings.*` / env. Clean.

---

## Summary of findings

| # | Area | Result |
|---|------|--------|
| 1 | Path-traversal artifacts/reels/export/files | CLOSED |
| 1b | `delete_proxy` glob injection | **VULN (HIGH)** — mass-delete + dir escape via `*`/`..` in `{sha256}` |
| 2 | Destructive endpoints scope | SAFE (except 1b) |
| 3 | Vision isolation | **subprocess (spawn) + terminate/kill timeout** — confirmed, not to_thread |
| 4 | SQLite WAL + busy_timeout | APPLIED |
| 5 | Publer retract codes | HONEST (409/502, no false cancelled) |
| 6 | Persistence / restart recovery / flush race | SOLID |
| 7 | Hardcoded secrets | NONE |

**Single fix to flip FAIL→PASS:** sanitize the `sha256` path param in `proxies.py` / `delete_proxy` (regex `^[0-9a-fA-F]{8,64}$` or `glob.escape`) before globbing.

Minor (non-blocking): stale docstring in `face_tracker._detect_faces_in_frames` claims `to_thread` execution; actual path is subprocess. Cosmetic only.
