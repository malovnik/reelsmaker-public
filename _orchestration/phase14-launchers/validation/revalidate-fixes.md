# Re-validation: anti-fratricide launcher fixes

Verdict: **PASS** (1 cosmetic note, no regressions).

Tested against REAL running processes on this Mac (`pnpm preview` + vite + esbuild from
`/Users/malovnik/Documents/Dev/reelsmaker-public/apps/frontend/...`) plus synthetic foreign-project args.

## 1. Self-recognition NOT broken

Confirmed our processes really carry the project path in args, so anchoring holds.

| Process | Real args contain | macOS pattern | Linux `is_our_pid` | Windows `Test-OursPid` |
|---|---|---|---|---|
| vite child | `.../reelsmaker-public/apps/frontend/.../vite/bin/vite.js` | `ROOT/apps/frontend.*vite` MATCH | substring ROOT TRUE | `node.exe`+`vite`+rootEsc TRUE |
| esbuild | `.../apps/frontend/node_modules/.pnpm/@esbuild.../esbuild` | `ROOT/apps/frontend.*esbuild` MATCH | substring ROOT TRUE | `esbuild.exe`+rootEsc TRUE |
| backend uvicorn | `videomaker.main:app` | `uvicorn videomaker.main` MATCH | module rule (no path) TRUE | `uvicorn videomaker\.main` TRUE |

Backend is caught by the module-anchored rule on all three OSes — no path needed, correct.
Our vite/esbuild are caught because their args legitimately embed the absolute project path.
**Self-cleanup of our own stragglers works.**

## 2. Anti-fratricide works

Foreign vite (`/Users/someone/other-project/.../vite.js`) and foreign uvicorn
(`someotherapp.main`) are NOT recognized as ours on any platform (no ROOT path, non-matching
module). **A different project's dev server / render is left alone.**

## 3. macOS `.lock` find -mmin +1

Syntactically valid on BSD find (exit 0, no error). Integer `+1` is accepted (BSD rejects only
fractional `-mmin`). A lock aged past 1 min is matched and deleted; a fresh lock is skipped.
The `*.db`/`-wal`/`-shm` guard runs per-file before `rm`. **Correct and safe.**

## 4. Syntax / balance

- `bash -n`: macos/launcher.sh, linux/lib.sh, linux/launcher.sh, linux/install.sh, reelibraLINUX.sh — all clean.
- launcher.ps1 brace/paren/bracket fully balanced (179/179, 288/288, 57/57). pwsh not installed
  here for full AST parse, but balance + manual read show no structural issue.

## 5. New dead code / regressions

None introduced by the fixes.

## Notes (non-blocking)

- **macOS `pnpm.*dev.*ROOT` stale-pattern is effectively dead for the wrapper.** The real `pnpm`
  launcher process is `node ~/.npm-global/bin/pnpm dev` — its args contain neither the project
  path nor reliably `dev` before a path, so this pattern never matches the orphaned wrapper.
  This is NOT a functional bug: in-session the wrapper is killed by `$FRONTEND_PID` (exit trap),
  and across sessions the vite *child* is still killed via the `vite`/`esbuild` patterns plus
  `free_port 3000` (the child owns the listen socket). A leftover wrapper with a dead child holds
  no port and is harmless. Same reasoning applies to Linux `pnpm.*dev` and Windows `pnpm`+`dev`
  clauses — they only ever match if ROOT is in args, which the bare wrapper lacks. Anchoring
  correctly errs toward NOT killing rather than risking fratricide, consistent with the fix intent.
- Tested processes were `pnpm preview` (port 4188/4319), not `pnpm dev`, but the arg structure
  (wrapper without ROOT, vite/esbuild children with ROOT) is identical, so the analysis transfers.
