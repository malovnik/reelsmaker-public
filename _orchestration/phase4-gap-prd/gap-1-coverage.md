# Gap-1 — Coverage Gaps (NOTEXPOSED + MISSING)

> Phase 4, Lens 1 of N. Role: API Coverage Gap Analyst. Input: BACKEND-MAP + section-1-api-data + FRONTEND-EXPOSURE (A/B). Goal: ни одной пропущенной ручки/возможности.
> Scope per ROADMAP product decisions: **auth НЕ добавляем** (single-user local). **Dormant/orphan НЕ оживляем** (B-roll, 6 orphan modules, cursor/deictic zoom, mouth-sound) — WONTFIX-by-decision.

## Gap taxonomy
- **GAP-NOTEXPOSED** — backend endpoint exists, no client function and/or no UI control wires to it.
- **GAP-MISSING** — a pipeline capability or settings field exists, but there is no UI control to drive it.
- Out of this lens: "exposed-broken" (fictions, dead UI, transcode stub) — those are *covered but wrong*, handled by the honesty/revival lens, not coverage. Listed here only as cross-refs where they overlap.

Priority key: **P0** blocks a core promised flow · **P1** material gap in a key feature · **P2** useful, non-blocking · **P3** nice-to-have / cosmetic.
Effort: **S** ≤ small (client helper + one button) · **M** (new component/dialog + state) · **L** (new page/flow or cross-layer wiring).

Product-decision refs (ROADMAP §"Продуктовые решения"): **PD1** exposed-broken → real or honest-remove · **PD2** vision/face-tracking opt-in revival, safe default · **PD3** Publer single path + projects↔jobs link + saved-folder screen · **PD4** balanced honest service, dormant/orphan cut — not revived.

---

## GAP-NOTEXPOSED (9)

| ID | Endpoint / file | Description | Prio | Covered by | Effort |
|---|---|---|---|---|---|
| **NX-01** | `PATCH /jobs/{job_id}/auto-config` (jobs.py) | Apply auto-config to job.options. **No client fn at all.** Half of the Automatic-Mode flow: `autoAnalyzeJob` (POST auto-analyze) is wired, but its result can't be applied through the typed client. Most material client gap. | **P0** | PD4 (Automatic Mode = key feature) | M |
| **NX-02** | `DELETE /jobs/{job_id}/auto-config` (jobs.py) | Clear auto-config → manual mode. No client fn. Pair of NX-01. | **P0** | PD4 | S |
| **NX-03** | `GET /jobs/{job_id}/profile/suggestion` (jobs.py) | Suggest vision profile from face coverage. **Client fn `getProfileSuggestion` exists, but no wired UI trigger** (exposure-B §2). Exposed at client layer, dead at UI layer. Directly supports PD2 safe-default vision. | **P1** | PD2 | S |
| **NX-04** | `GET /proxies` (proxies.py) | List proxy cache files (count, size MB). No client, no UI. | **P2** | PD4 | M |
| **NX-05** | `DELETE /proxies/cleanup` (proxies.py) | LRU cleanup of proxy cache. No client, no UI button (ProxyCacheGroup sets *policy* only, no manual purge action). | **P2** | PD4 | S |
| **NX-06** | `DELETE /proxies/{sha256}` (proxies.py) | Delete one proxy by sha256 prefix. No client, no UI. | **P3** | PD4 | S |
| **NX-07** | `POST /settings/fonts/refresh` (settings.py) | Rescan system fonts (~6s blocking). `refreshFonts` client fn exists, but **no explicit "refresh fonts" button** surfaced in subtitle editor. Client-covered, UI-dead. | **P3** | PD4 | S |
| **NX-08** | `GET /jobs/{job_id}/source-thumbnail` (jobs.py) | Source-frame thumbnail (distinct from processed `/thumbnail` which IS covered via `jobThumbnailUrl`). No URL helper; if shown, inlined. | **P3** | PD4 | S |
| **NX-09** | `GET /post_production/assets/{id}/thumbnail` (post_production.py) | Asset (intro/outro) thumbnail PNG. No URL helper; if rendered, inlined. | **P3** | PD4 | S |

> `GET /files/{job_id}/{kind}/{name}` is **not** counted as a true gap: no centralized `fileUrl()` helper, but URLs are assembled inline in components (`<video src>`, `download_url` from `exportReel`). Functionally exposed. Recommend a `fileUrl()` builder for hygiene (P3/S) but it is not a coverage hole. If counted as a helper gap → 10 NOTEXPOSED; functionally → 9.

---

## GAP-MISSING (6)

Pipeline capability / settings field present, no UI control to drive it.

| ID | Capability / field (file) | Description | Prio | Covered by | Effort |
|---|---|---|---|---|---|
| **MS-01** | Cancel running job (`JobStatus.cancelled`; real cancel landed in 1b-fix; SSE terminal `cancelled` supported) | Backend + SSE fully support mid-pipeline cancel after 1b-fix, but **no cancel-job button** — UI only offers delete/purge. User cannot stop a long wrong run. | **P0** | PD4 (honest working service) | S |
| **MS-02** | `llm_model` specific model id (POST /jobs Form field `llm_model`; `available_llm_models` in `/settings/models`) | UploadWizard exposes **provider** only; model is tier-resolved server-side. The per-job specific `llm_model` field and the `available_llm_models` catalog have no UI control. Tightly linked to the "tier toggle is fiction" problem (PD1: split tiers onto real models). | **P1** | PD1 | M |
| **MS-03** | Projects ↔ jobs wiring (POST /jobs `project_id` not sent; `assignJobToProject` client exists but not called from create flow) | Client + endpoint exist, but UploadWizard never sends `project_id` and the assign call is not invoked on creation → folders non-functional e2e. Also no saved-folder screen for `POST /jobs/{id}/saved` output. | **P0** | PD3 | M |
| **MS-04** | `mouth_sound_removal_enabled` (PerformanceSettings) | Field persists; UI control **deliberately removed** (dormant, compute-then-discard). | WONTFIX | PD4 (dormant — not revived) | — |
| **MS-05** | Screencast cursor zoom (`screencast_cursor_zoom_enabled`, damping, max-factor) (PerformanceSettings) | Fields persist; toggle is ON internally but output discarded; UI deliberately hidden. Burns CPU. | WONTFIX | PD4 (dormant cut, not revived) | — |
| **MS-06** | Deictic zoom (`deictic_zoom_enabled`) (PerformanceSettings) | Field persists; UI deliberately hidden; dormant. | WONTFIX | PD4 (dormant cut) | — |

> Additional pipeline capabilities listed in exposure-B as "no UI" that are actually adjacent to other lenses, not coverage gaps: anthropic/openai/deepgram as pipeline LLM (dead in narrative brain → exposed-broken/PD1 honesty, NOT a missing control to add); `/connections/youtube/*` (UI exists, backend dropped → exposed-broken/PD1, inverse gap). Excluded from MISSING count to avoid double-listing with the honesty lens.

---

## Returns (summary)

- **GAP-NOTEXPOSED: 9** (NX-01..NX-09). +1 if the `fileUrl()` helper hygiene item is counted → 10.
- **GAP-MISSING: 6** (MS-01..MS-06) — of which **3 actionable** (MS-01, MS-02, MS-03) and **3 WONTFIX-by-decision** (MS-04/05/06 dormant).

### P0 list (blocks a core promised flow)
- **NX-01** — `PATCH /jobs/{id}/auto-config`: no client → Automatic Mode half-broken.
- **NX-02** — `DELETE /jobs/{id}/auto-config`: no client → can't return to manual.
- **MS-01** — Cancel running job: backend+SSE ready, no UI button.
- **MS-03** — Projects↔jobs wiring + saved-folder screen (PD3).

### P1 list (material gap in a key feature)
- **NX-03** — profile/suggestion: client exists, no UI trigger (PD2 safe-default vision).
- **MS-02** — specific `llm_model` selection / `available_llm_models` catalog unused (PD1 real tiers).

### WONTFIX-by-decision
- **MS-04** mouth_sound_removal · **MS-05** screencast cursor zoom · **MS-06** deictic zoom — all dormant, PD4 says cut/hide not revive.
- **Not added** (per ROADMAP): auth on destructive endpoints (single-user local), orphan modules (B-roll, object_tracker, person_cluster, match_cuts, eye_trace_continuity, transition_chooser ~972 LOC) — no endpoints, not a coverage gap; slated for deletion not exposure.
