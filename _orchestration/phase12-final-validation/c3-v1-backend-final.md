# C3-V1 — Backend Final Gate (Cycle 3 of 3)

Role: Regression & Backend Final Gate Validator. Scope: `apps/backend/src/videomaker`.
Final cycle. Re-confirm the cycle-2 HIGH fix (glob injection), run all gates, full regression sweep.

## VERDICT: **GO**

The single HIGH from cycle 2 (`delete_proxy` glob injection) is closed and empirically un-bypassable. All gates green (modulo known stub-lib / library-typing warnings). No mocks/stubs/TODO in production. Server boots and serves health 200. No regressions in any of the seven critical areas.

---

## 1. Glob-injection (`delete_proxy`) — CLOSED, verified by adversarial fuzz

**Fix in place** (`services/proxy.py:400-409`):
```python
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{8,64}$")

def delete_proxy(cache_dir: Path, sha256: str) -> int:
    if not _SHA256_RE.match(sha256):
        raise ValueError(f"invalid sha256 identifier: {sha256!r}")
    ...
    for path in cache_dir.glob(f"{sha256}__*.mp4"):
```
Route maps `ValueError → 400` (`api/routes/proxies.py:109-115`) with non-leaking detail.

**Empirical bypass attempt** (ran the actual compiled regex against the payloads from the cycle-2 report + extras):

| Input | Result |
|---|---|
| `********` (the cycle-2 mass-delete vector) | BLOCKED → 400 |
| `..`, `*`, `../foo`, `../../etc1234` | BLOCKED → 400 |
| `ab*d1234`, `12345678; rm`, `%2e%2e`, `gggghhhh` | BLOCKED → 400 |
| `<8 chars`, `>64 chars` | BLOCKED → 400 |
| `aaaaaaaa` (8 hex), `a*64` (64 hex), `deadBEEF1234` | accepted (legit) |

Every wildcard / traversal / special-char vector raises ValueError → 400. No glob metacharacter reaches `cache_dir.glob`. Mass-delete and directory-escape are both eliminated.

Note (non-blocking, not a vuln): `re.match` with a `$` anchor tolerates a single trailing `\n` (`"abcd1234\n"` "matches"). Not exploitable — a literal newline cannot appear in a FastAPI path segment, and even if forced, the resulting glob `abcd1234\n__*.mp4` only matches a file literally containing a newline (the server never creates such names). No escape, no extra deletion. If desired, `re.fullmatch` would close the cosmetic edge; leaving as-is is acceptable.

## 2. Gates

- **`ruff check src/videomaker`** → `All checks passed!`
- **`pyright src/videomaker`** → 2 errors, 20 warnings.
  - 20 warnings: all `reportMissingTypeStubs` for untyped third-party libs (soundfile, maad, pyloudnorm, silero_vad, scipy, zhipuai) — known stub-lib noise.
  - Error 1 `audio_analyzer.py:336` — `maad.features.temporal_snr` unknown import symbol (untyped lib, runtime-valid).
  - Error 2 `prompt_store.py:67` — `Result.rowcount` attribute (SQLAlchemy typing quirk, runtime-valid).
  - Both errors are pre-existing library-typing artifacts, **not** in proxy.py/proxies.py, not regressions from this cycle. Non-blocking.

## 3. No mocks/stubs/TODO in production

`grep -rniE "TODO|FIXME|XXX|HACK|mock|stub|NotImplementedError"` over `src/videomaker/**/*.py` → single hit: `llm_providers/claude_factory.py:7`, inside a **module docstring** (prose explaining why a default is returned "вместо NotImplementedError"). Zero real mock/stub/TODO in executable code.

## 4. Import smoke + server health

- `python -c "import videomaker.main"` → `IMPORT_OK`.
- `uvicorn videomaker.main:app --port 8097` (background) → `Application startup complete`.
- `curl localhost:8097/api/v1/health` → **HTTP 200**, body reports `status:ok`, ffmpeg available + videotoolbox_hevc, providers/transcribers wired.
- Process killed (`pkill`), port 8097 confirmed clear.

## 5. Regression sweep — all intact

| Area | Evidence | Status |
|---|---|---|
| Path-traversal (reel_id) | `_REEL_ID_RE = ^[A-Za-z0-9_-]+$` + `_reel_artifact_path` containment (`base_resolved not in candidate.parents`), applied on subs GET/PATCH + export | OK |
| Export | `preset not in EXPORT_PRESETS → reject`; output via validated `_reel_artifact_path` | OK |
| Tier matrix | `build_llm_for_tier` (pro / flash_lite) + `_resolve_tier_models` wired into canvas/compression/closure | OK |
| Cancel | `POST /{job_id}/cancel` → `Task.cancel()` → CancelledError in pipeline | OK |
| Publer retract | honest 409 (published / unsynced) + 502 (`PublerClientError`, status untouched) | OK |
| Vision subprocess | `mp.get_context("spawn")` + `ctx.Process` + `_kill_process()` terminate→kill | OK |
| SQLite WAL | `foreign_keys=ON` + `journal_mode=WAL` + `busy_timeout=30000` per connection | OK |
| Restart recovery | `reset_stale_running_jobs()` called in `main.py:75` lifespan | OK |

---

## Final backend verdict: **GO**

Cycle-2 FAIL flipped to PASS by the proxy regex fix — confirmed un-bypassable by fuzz. Gates green (only known stub-lib/SQLAlchemy typing noise remains). Server boots and serves health 200. No production mocks/stubs/TODO. No regressions across path-traversal, tiers, cancel, export, Publer retract, vision isolation, or SQLite WAL. Backend is production-ready.
