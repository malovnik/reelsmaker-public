# Auto Pipeline Integration — T10/T11 UI Exposure Plan

> **For agentic workers:** Execute inline via superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking. User rule `feedback_no_extra_tests` — build gates only, no new unit tests.

**Goal:** 100% вывести новые T10/T11 runtime_settings в frontend controls с standard-рекомендациями, заставить auto_config_advisor уважать PostProductionOverrides master toggles, провести end-to-end build gates и выполнить коммит.

**Architecture:** Backend PerformanceSettings уже содержит все T10/T11 поля (runtime_settings.py:160-196). Pipeline корректно применяет их (pipeline.py:1239, 1464, 1596). Недостающее звено — TypeScript interface + UI controls + advisor respect для overrides. Решение — расширить api.ts interface, добавить 4 новые секции в PerformanceSettingsClient с reset-to-default, научить advisor читать PostProductionOverrides.

**Tech Stack:** Python 3.12 / FastAPI / Pydantic v2 (backend), Next.js 16 / React 19 / Tailwind 4 (frontend).

**Completion promise:** `<promise>VIDEOMAKER-AUTO-PIPELINE-INTEGRATION-COMPLETE</promise>`

---

## Task 1: advisor respects master toggles

**Files:**
- Modify: `apps/backend/src/videomaker/services/auto_config_advisor.py`
- Verify: `apps/backend/src/videomaker/services/pipeline.py` (уже вызывает advisor с post_production_config)

- [ ] **Step 1:** Посмотреть сигнатуру `build_auto_config` в advisor.
- [ ] **Step 2:** Добавить optional параметр `post_production_overrides: PostProductionOverrides | None = None` (Pydantic модель из `videomaker.models.post_production`).
- [ ] **Step 3:** В теле функции после генерации decisions — если `overrides.enable_zoom is False` → `config.punch_in_zoom_enabled = False` и `config.ken_burns_drift_enabled = False` + warning message.
- [ ] **Step 4:** Обновить вызов в `jobs.py` — передать `post_production_overrides` из job_options.
- [ ] **Step 5:** Build gate: `cd apps/backend && uv run ruff check` — 0 errors.

## Task 2: extend api.ts PerformanceSettings interface

**Files:**
- Modify: `apps/frontend/src/lib/api.ts:247-289`

- [ ] **Step 1:** Добавить новые enum экспорты:
```ts
export const PIPELINE_MODES = ["automatic", "manual"] as const;
export type PipelineMode = (typeof PIPELINE_MODES)[number];

export const SNAP_STRATEGIES = ["off", "beat", "onset", "both"] as const;
export type SnapStrategy = (typeof SNAP_STRATEGIES)[number];

export const PACING_PROFILES = ["dynamic", "balanced", "mkbhd_clean", "documentary"] as const;
export type PacingProfile = (typeof PACING_PROFILES)[number];
```

- [ ] **Step 2:** Дописать в `PerformanceSettings` все T10/T11 поля:
```ts
// T11 Automatic Mode
pipeline_mode: PipelineMode;
pacing_profile: PacingProfile;
// T10.1 Punchline pause
punchline_pause_enabled: boolean;
punchline_pitch_drop_hz: number;
punchline_hold_after_sec: number;
// T10.2 Snap strategy
snap_strategy: SnapStrategy;
onset_snap_max_shift_sec: number;
// T10.3 Punch-in zoom
punch_in_zoom_enabled: boolean;
punch_in_zoom_scale: number;
punch_in_zoom_probability: number;
punch_in_zoom_hold_ms: number;
// T10.7 Ken Burns
ken_burns_drift_enabled: boolean;
ken_burns_scale_per_sec: number;
ken_burns_max_scale: number;
```

- [ ] **Step 3:** Build gate: `cd apps/frontend && pnpm tsc --noEmit` — 0 errors.

## Task 3: PerformanceSettingsClient.tsx secciones T10/T11

**Files:**
- Modify: `apps/frontend/src/components/PerformanceSettingsClient.tsx`

- [ ] **Step 1:** Обновить `DEFAULT` performance settings с T10/T11 полями и дефолтами (dynamic/off/true defaults как в Pydantic модели).
- [ ] **Step 2:** Добавить раздел "Автоматический режим" с dropdown для `pipeline_mode` (automatic/manual) — standard "automatic".
- [ ] **Step 3:** Добавить раздел "Темп и ритм (Pacing)" с dropdown `pacing_profile` (4 варианта), radio для `snap_strategy` (off/beat/onset/both), slider для `onset_snap_max_shift_sec` (0.0–0.15, standard 0.08).
- [ ] **Step 4:** Добавить раздел "Акценты (Punchline)" — toggle `punchline_pause_enabled`, sliders для `punchline_pitch_drop_hz` (10–80, std 20) и `punchline_hold_after_sec` (0.2–1.5, std 0.5).
- [ ] **Step 5:** Добавить раздел "Движение кадра (Motion)" — 
  - toggle `punch_in_zoom_enabled`, sliders `punch_in_zoom_scale` (1.0–1.3, std 1.08), `punch_in_zoom_probability` (0.0–1.0, std 0.5), `punch_in_zoom_hold_ms` (100–1500, std 600)
  - toggle `ken_burns_drift_enabled`, sliders `ken_burns_scale_per_sec` (0.0–0.02, std 0.002), `ken_burns_max_scale` (1.0–1.2, std 1.06)
- [ ] **Step 6:** Каждая секция — кнопка "Вернуть стандартные значения" сбрасывающая только свою группу.
- [ ] **Step 7:** Каждое поле — маленький badge с "стандарт: X" справа от input.
- [ ] **Step 8:** Build gate: `cd apps/frontend && pnpm lint && pnpm tsc --noEmit`.

## Task 4: UploadWizard Auto-mode acknowledgment

**Files:**
- Verify: `apps/frontend/src/components/upload/UploadWizard.tsx`

- [ ] **Step 1:** Проверить что Auto-mode блок уже подписан "Auto mode анализирует видео и сам выбирает склейки / звук / движение. Формат, модель, зум/интро/ч-б выбираешь сам".
- [ ] **Step 2:** Если нет — добавить такую подпись рядом с pipeline_mode toggle.

## Task 5: build gates + commit + push

- [ ] **Step 1:** `cd apps/backend && uv run ruff check` — 0 errors.
- [ ] **Step 2:** `cd apps/frontend && pnpm lint && pnpm tsc --noEmit && pnpm build` — 0 errors.
- [ ] **Step 3:** `git add -A` (исключая .env, build artefacts) и `git commit -m "feat(ui): expose T10/T11 runtime settings in frontend + advisor respects master toggles"`.
- [ ] **Step 4:** `git push origin main`.
- [ ] **Step 5:** Serena `write_memory` с именем `videomaker/t10-t11-ui-integration` — краткое резюме.
- [ ] **Step 6:** Отметить в `docs/research/consolidated-action-plan.md` секцию "Frontend control plan" как ✅ DONE.

## Success

После Task 5 вывести в чат:
`<promise>VIDEOMAKER-AUTO-PIPELINE-INTEGRATION-COMPLETE</promise>`
