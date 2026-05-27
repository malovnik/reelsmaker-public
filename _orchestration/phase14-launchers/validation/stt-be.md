# Cross-Platform STT Validation — Backend lens

Code: `apps/backend`. Role: docu-paranoia — prove MLX is truly unreachable on Windows/Linux.

## Verdict: PASS (all checks)

| # | Check | Result |
|---|-------|--------|
| 1 | pyproject markers on MLX deps | PASS |
| 2 | No eager MLX import; lazy + raise in factory | PASS |
| 3 | config excludes MLX + default=deepgram off-darwin | PASS |
| 4 | Windows simulation (win32) | PASS |
| 5 | /health.transcribers = available_transcribers | PASS |
| 6 | Gates ruff + pyright | PASS |

---

## 1. pyproject.toml platform markers — PASS
`apps/backend/pyproject.toml` lines 29-30:
```
"mlx-whisper>=0.4.2; sys_platform == 'darwin'",
"stable-ts[mlx]>=2.19; sys_platform == 'darwin'",
```
Both MLX deps carry `; sys_platform == 'darwin'`. On Win/Linux `uv` resolves these out → packages never installed. Comment (lines 27-28) documents the rationale. Marker present and correct.

## 2. No eager MLX import + lazy raise — PASS
- `transcribers/__init__.py`: imports only `base`, `deepgram_backend`, `factory`. MLX backends (`MlxWhisperBackend`, `StableTsMlxBackend`) are NOT imported at module level (comment lines 16-18 confirms intent). Importing the package on Win/Linux does not touch `mlx_whisper`.
- `factory.py` `build_transcriber()` (lines 30-57): for names `stable_ts_mlx | stable_ts | mlx_whisper` it first checks `if sys.platform != "darwin": raise TranscriberError(...)` (lines 35-39) BEFORE any MLX import. The `from ...stable_ts_mlx_backend import` / `mlx_whisper_backend import` statements sit inside the darwin branch (lines 40-50), so they are reached only on macOS. Lazy import + guard both present.

## 3. config.py platform gating — PASS
`core/config.py`:
- L15: `IS_MACOS = sys.platform == "darwin"`
- L16: `DEFAULT_TRANSCRIBER = "stable_ts_mlx" if IS_MACOS else "deepgram"`
- `available_transcribers` (L272-279): `mlx = [...] if IS_MACOS else []` → empty off-darwin; `cloud = ["deepgram"] if self.deepgram_api_key else []`. Returns `mlx + cloud`. Off-darwin → `[]` (no key) or `["deepgram"]` (key set).
- `default_transcriber` (L281-286): `return "deepgram"` when not macOS.

## 4. Windows simulation — PASS
Direct monkeypatch-after-import (real platform is darwin; cannot pre-set sys.platform without breaking stdlib asyncio Windows-event import, so deps loaded first, then `sys.platform='win32'` + `importlib.reload(config, factory)`):

```
IS_MACOS= False
DEFAULT_TRANSCRIBER= deepgram
available (no key)= []
available (with key)= ['deepgram']
default_transcriber= deepgram
build stable_ts_mlx: TranscriberError OK
build mlx_whisper:   TranscriberError OK
build stable_ts:     TranscriberError OK
build deepgram:      DeepgramBackend OK
```
Proves on win32: (a) `available_transcribers` = `[]` or `["deepgram"]` — never any MLX entry; (b) `build_transcriber('stable_ts_mlx')` (and `mlx_whisper`, `stable_ts`) raise `TranscriberError` without importing MLX; (c) default = `deepgram`.

**Windows unreachability — triple proof:** (1) deps not installed (pyproject darwin marker), (2) factory raises `TranscriberError` before any MLX import, (3) MLX never appears in the advertised `available_transcribers` list. No path leads to MLX execution off macOS.

## 5. /health.transcribers — PASS
`api/routes/health.py` L25: `"transcribers": settings.available_transcribers`. Health surface is exactly the gated property → off-darwin health reports `[]`/`["deepgram"]`, never MLX.

## 6. Gates — PASS
No files modified (read-only audit); ran gates on the touched modules.
- `ruff check src/videomaker/services/transcribers/ core/config.py api/routes/health.py` → **All checks passed!**
- `pyright` (same files) → **0 errors, 0 warnings, 0 informations**.
