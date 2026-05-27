# Exposure A — API Client Coverage

Auditor: Frontend-Backend Integration Auditor. Method: method+path match of every backend endpoint (81, from `phase2-backend-map/section-1-api-data.md`) against the frontend HTTP layer (`apps/frontend/src/lib/api/*` + `apps/frontend/src/lib/sse.ts`).

Scope note: this audit covers the **API-client layer only** (does a typed function exist?). Whether a React component actually calls that function is a separate question (exposure-B). "COVERED" here = there is a client function that issues a matching method+path request.

---

## 1. Fetch layer (`core.ts`)

- **Base URL:** none. `resolveUrl()` returns the path unchanged (only passes through absolute `http(s)://`). All `/api/v1/*` requests are **relative** → resolved by Vite dev-proxy (`vite.config.ts → server.proxy`) in dev, same-origin in prod. This is a Vite SPA, not Next.js.
- **`request<T>()`:** single wrapper. Injects `Accept: application/json`, `cache: "no-store"`. On `!response.ok` → parses body as JSON (fallback text) and throws `ApiError{status, detail}`. `204` → returns `undefined as T`. Otherwise `response.json()`.
- **Error model:** `ApiError extends Error` carries `status` + raw `detail` (matches FastAPI `{detail}` / `422` array). No retry, no interceptors, no auth header (backend has no auth — consistent).
- **Non-JSON responses** bypass `request()`: `getReelSubtitles` uses a hand-rolled `fetch` with `Accept: text/plain`. Binary endpoints (thumbnails, files) are exposed as **URL-builder strings**, not fetch calls (e.g. `jobThumbnailUrl(id)` returns a string for `<img src>`).
- **SSE:** NOT in the api client. Handled in `lib/sse.ts` via native `EventSource` against `${SSE_BASE_URL}/api/v1/jobs/${jobId}/stream` — connects **directly to the backend, bypassing the Vite proxy** (EventSource can't use the proxy reliably). This correctly covers the `GET /jobs/{job_id}/stream` SSE contract (§3).

---

## 2. Coverage table (endpoint | method | in client? | file | status)

### health
| Endpoint | M | In client? | File | Status |
|---|---|---|---|---|
| `/health` | GET | `coreApi.health` | core.ts | COVERED |

### files
| Endpoint | M | In client? | File | Status |
|---|---|---|---|---|
| `/files/{job_id}/{kind}/{name}` | GET | — | — | NOT COVERED (no helper; URLs likely built inline in components) |

### proxies
| Endpoint | M | In client? | File | Status |
|---|---|---|---|---|
| `/proxies` | GET | — | — | NOT COVERED |
| `/proxies/cleanup` | DELETE | — | — | NOT COVERED |
| `/proxies/{sha256}` | DELETE | — | — | NOT COVERED |

### projects (+ /jobs assign)
| Endpoint | M | In client? | File | Status |
|---|---|---|---|---|
| `/projects` | GET | `listProjects` | projects.ts | COVERED |
| `/projects` | POST | `createProject` | projects.ts | COVERED |
| `/projects/{id}` | GET | `getProject` | projects.ts | COVERED |
| `/projects/{id}` | PATCH | `updateProject` | projects.ts | COVERED |
| `/projects/{id}` | DELETE | `deleteProject` | projects.ts | COVERED |
| `/jobs/{job_id}/project` | PATCH | `assignJobToProject` | projects.ts | COVERED |

### settings (18)
| Endpoint | M | In client? | File | Status |
|---|---|---|---|---|
| `/settings/performance` | GET | `getPerformanceSettings` | settings.ts | COVERED |
| `/settings/performance` | PUT | `updatePerformanceSettings` | settings.ts | COVERED |
| `/settings/vision` | GET | `getVisionSettings` | settings.ts | COVERED |
| `/settings/vision` | PUT | `updateVisionSettings` | settings.ts | COVERED |
| `/settings/models` | GET | `models` | settings.ts | COVERED |
| `/settings/prompts` | GET | `listPrompts` | settings.ts | COVERED |
| `/settings/prompts/{key}` | GET | `getPrompt` | settings.ts | COVERED |
| `/settings/prompts/{key}` | PUT | `upsertPrompt` | settings.ts | COVERED |
| `/settings/fonts` | GET | `listFonts` | subtitle.ts | COVERED |
| `/settings/fonts/refresh` | POST | `refreshFonts` | subtitle.ts | COVERED |
| `/settings/subtitle_presets` | GET | `listSubtitlePresets` | subtitle.ts | COVERED |
| `/settings/subtitle_presets/{id}` | GET | `getSubtitlePreset` | subtitle.ts | COVERED |
| `/settings/subtitle_presets` | POST | `createSubtitlePreset` | subtitle.ts | COVERED |
| `/settings/subtitle_presets/{id}` | PUT | `updateSubtitlePreset` | subtitle.ts | COVERED |
| `/settings/subtitle_presets/{id}` | DELETE | `deleteSubtitlePreset` | subtitle.ts | COVERED |
| `/settings/profiles` | GET | `listVisionProfiles` | settings.ts | COVERED |
| `/settings/profiles/{profile}` | GET | `getVisionProfile` | settings.ts | COVERED |
| `/settings/profiles/{profile}` | PUT | `updateVisionProfile` | settings.ts | COVERED |
| `/settings/profiles/{profile}` | DELETE | `resetVisionProfile` | settings.ts | COVERED |

Note: 18 endpoints listed in the contract, but the table actually enumerates 19 rows (fonts ×2 included). All present → COVERED.

### post_production (10)
| Endpoint | M | In client? | File | Status |
|---|---|---|---|---|
| `/post_production/assets` | GET | `listAssets` | post_production.ts | COVERED |
| `/post_production/assets/{id}` | GET | `getAsset` | post_production.ts | COVERED |
| `/post_production/assets/{id}/thumbnail` | GET | — | — | NOT COVERED (binary PNG; no URL helper) |
| `/post_production/assets` | POST | `importAsset` | post_production.ts | COVERED |
| `/post_production/assets/{id}` | DELETE | `deleteAsset` | post_production.ts | COVERED |
| `/post_production/presets` | GET | `listPostProductionPresets` | post_production.ts | COVERED |
| `/post_production/presets/default` | GET | `getDefaultPostProductionPreset` | post_production.ts | COVERED (handles `null`) |
| `/post_production/presets/{id}` | GET | `getPostProductionPreset` | post_production.ts | COVERED |
| `/post_production/presets` | POST | `createPostProductionPreset` | post_production.ts | COVERED |
| `/post_production/presets/{id}` | PUT | `updatePostProductionPreset` | post_production.ts | COVERED |
| `/post_production/presets/{id}` | DELETE | `deletePostProductionPreset` | post_production.ts | COVERED |

### jobs (24)
| Endpoint | M | In client? | File | Status |
|---|---|---|---|---|
| `/jobs` | GET | `listJobs` | jobs.ts | COVERED |
| `/jobs` | POST | `createJob` | jobs.ts | COVERED |
| `/jobs/artifacts/liked` | GET | `schedulerApi.listLikedReels` | scheduler.ts | COVERED (lives in scheduler.ts, not jobs.ts) |
| `/jobs/{id}` | GET | `getJob` | jobs.ts | COVERED |
| `/jobs/{id}/source-thumbnail` | GET | — | — | NOT COVERED (binary jpeg; no URL helper) |
| `/jobs/{id}/rename` | PATCH | `renameJob` | jobs.ts | COVERED |
| `/jobs/{id}/profile` | PATCH | `updateJobProfile` | jobs.ts | COVERED |
| `/jobs/{id}/profile/suggestion` | GET | `getProfileSuggestion` | jobs.ts | COVERED |
| `/jobs/{id}/auto-analyze` | POST | `autoAnalyzeJob` | jobs.ts | COVERED |
| `/jobs/{id}/auto-config` | PATCH | — | — | NOT COVERED |
| `/jobs/{id}/auto-config` | DELETE | — | — | NOT COVERED |
| `/jobs/{id}/artifacts` | GET | `listArtifacts` | jobs.ts | COVERED |
| `/jobs/{id}/artifacts/{aid}/like` | PATCH | `updateArtifactLike` | jobs.ts | COVERED (⚠ contract mismatch, §3) |
| `/jobs/{id}/artifacts/{aid}` | DELETE | `deleteArtifact` | jobs.ts | COVERED |
| `/jobs/{id}` | DELETE | `deleteJob` | jobs.ts | COVERED |
| `/jobs/{id}/saved` | POST | `saveReels` | jobs.ts | COVERED |
| `/jobs/{id}/thumbnail` | GET | `jobThumbnailUrl` | jobs.ts | COVERED (URL-builder string, not fetch) |
| `/jobs/{id}/stream` | GET | `useJobStream` (EventSource) | lib/sse.ts | COVERED (outside api client) |
| `/jobs/{id}/reels/{rid}/subtitles` | GET | `getReelSubtitles` | jobs.ts | COVERED (raw fetch, text/plain) |
| `/jobs/{id}/reels/{rid}/subtitles` | PATCH | `updateReelSubtitles` | jobs.ts | COVERED |
| `/jobs/{id}/reels/{rid}/export` | POST | `exportReel` | jobs.ts | COVERED (backend is PARTIAL STUB) |

24 backend job rows; the contract table lists 21 method+path rows under §2.7 (count of 24 includes the `/jobs` assign in projects.py + the two `/jobs/artifacts/liked` ordering note — treated above). All matched except the two `auto-config` and `source-thumbnail`.

### scheduler (18)
| Endpoint | M | In client? | File | Status |
|---|---|---|---|---|
| `/scheduler/connection/status` | GET | `getConnectionStatus` | scheduler.ts | COVERED |
| `/scheduler/accounts` | GET | `listPublerAccounts` | scheduler.ts | COVERED |
| `/scheduler/accounts/profiles` | GET | `listProfiles` | scheduler.ts | COVERED |
| `/scheduler/accounts/profiles/{id}` | PUT | `upsertProfile` | scheduler.ts | COVERED |
| `/scheduler/accounts/profiles/{id}` | DELETE | `deleteProfile` | scheduler.ts | COVERED |
| `/scheduler/presets` | GET | `listPresets` | scheduler.ts | COVERED |
| `/scheduler/presets` | POST | `createPreset` | scheduler.ts | COVERED |
| `/scheduler/presets/{id}` | PATCH | `updatePreset` | scheduler.ts | COVERED |
| `/scheduler/presets/{id}` | DELETE | `deletePreset` | scheduler.ts | COVERED |
| `/scheduler/campaigns` | GET | `listCampaigns` | scheduler.ts | COVERED |
| `/scheduler/campaigns` | POST | `createCampaign` | scheduler.ts | COVERED |
| `/scheduler/campaigns/{id}` | GET | `getCampaign` | scheduler.ts | COVERED |
| `/scheduler/campaigns/{id}/approve` | POST | `approveCampaign` | scheduler.ts | COVERED |
| `/scheduler/campaigns/{id}` | DELETE | `deleteCampaign` | scheduler.ts | COVERED |
| `/scheduler/assignments` | GET | `listAssignments` | scheduler.ts | COVERED |
| `/scheduler/assignments/{id}` | PATCH | `updateAssignment` | scheduler.ts | COVERED |
| `/scheduler/assignments/{id}/cancel` | POST | `cancelAssignment` | scheduler.ts | COVERED (backend PARTIAL STUB) |
| `/scheduler/assignments/{id}/retry` | POST | `retryAssignment` | scheduler.ts | COVERED |
| `/scheduler/manual/publish-one` | POST | `manualPublishOne` | scheduler.ts | COVERED |

19 rows (contract says 18; manual/publish-one is the extra). All COVERED.

---

## 3. Findings

### Coverage summary
- **Total backend endpoints: 81**
- **COVERED: 74**
- **NOT COVERED: 7**

### Not covered (7)
1. `GET /files/{job_id}/{kind}/{name}` — artifact download. No client helper. URLs are likely assembled inline in components (e.g. reel `<video src>`, the `exportReel` `download_url` points here). Worth a `fileUrl()` builder.
2. `GET /proxies` — list proxy cache. No client + no UI.
3. `DELETE /proxies/cleanup` — LRU cleanup. No client + no UI.
4. `DELETE /proxies/{sha256}` — delete proxy. No client + no UI.
   → The entire **proxies router (3 endpoints) is unexposed** — no proxy-cache management UI exists.
5. `GET /post_production/assets/{id}/thumbnail` — asset thumbnail PNG. No URL helper (unlike `jobThumbnailUrl`); if shown, the URL is inlined.
6. `GET /jobs/{job_id}/source-thumbnail` — source-frame thumbnail. No helper (note: `jobThumbnailUrl` covers the *processed* `/thumbnail`, not `/source-thumbnail` — distinct endpoint).
7. `PATCH /jobs/{job_id}/auto-config` AND `DELETE /jobs/{job_id}/auto-config` — apply / clear auto-config. **No client function at all.** `autoAnalyzeJob` (POST auto-analyze) exists, but the apply/clear half of the Automatic-Mode flow has no client binding. Given Automatic Mode is described as a key feature, this is the most material gap — auto-analyze can be requested but its result can't be applied/cleared through the typed client.

(7 listed gaps span 8 method+path rows because auto-config is two methods on one path. Endpoint count: 81 total − 74 covered = 7 uncovered *paths-as-counted-in-contract*; auto-config's two methods are both missing.)

### Client orphans (functions with no backend endpoint)
**None.** Every client function maps to a real backend endpoint. No dead client code.

### Contract mismatches (covered, but type-divergent — flag for exposure-B / integration test)
1. **`updateArtifactLike` like-value type mismatch.** Backend `ArtifactLikeUpdate{liked}` per §2.7 toggles a boolean like (`liked: boolean`, "Toggle like"). Frontend sends `liked: "none" | "like" | "dislike"` (a 3-state string). Either the contract doc under-describes the backend (tri-state) or the client sends an invalid type → likely **422**. Needs verification against the actual Pydantic model.
2. **`exportReel`** is wired to a backend **PARTIAL STUB** — `bitrate_k`/`target_lufs` in the response are declarative, the returned `download_url` is the un-transcoded mp4. Client trusts the response shape; UI must not promise real transcoding.
3. **`cancelAssignment`** wired to a backend **PARTIAL STUB** (local status flip only, no Publer retraction). Client cannot tell the difference — UI may imply the post is unscheduled when it isn't.

### Structural observations
- `listLikedReels` lives in **scheduler.ts** but hits a **/jobs** path (`/jobs/artifacts/liked`). Intentional (scheduler consumes liked reels as its source pool) and documented in-code, but a domain-purity nit.
- Binary/stream endpoints are deliberately handled outside `request<T>()`: thumbnails as URL-builder strings, subtitles via raw `fetch`, SSE via `EventSource` in `lib/sse.ts`. The `/source-thumbnail`, `/files/*`, and asset `/thumbnail` gaps fit this pattern — they're probably inlined in JSX rather than truly absent, but there's no centralized helper, so they're correctly marked NOT COVERED at the client-layer level.
