# BV-2 — Functional Integration Validation (Phase 11)

Роль: Functional Integration Validator. Цель — целостность после редизайна, runtime-безопасность, build.

## Итог: PASS с замечаниями (build зелёный, провайдеры/флоу целы, остался legacy raw-error/confirm в settings-клиентах — не регресс редизайна)

---

## 1. Контексты потребляются корректно — PASS

Дерево провайдеров (`src/main.tsx`): `ErrorBoundary → UiModeProvider → ToastProvider → ConfirmProvider → RouterProvider`. Порядок верный (Confirm может слать тосты — Toast выше).

- `useUiMode` — потребители: `HomeClient`, `shell/ModeSwitch`, `shell/Onboarding`. Все под `UiModeProvider` (root). OK.
- `useToast` / `useConfirm` — потребители под Toast/Confirm провайдерами (root). OK.
- `useWizardStateContext` — потребители только `upload/guided/GuidedFlow` и `upload/UploadWizard`; оба рендерятся под `<WizardStateProvider>` в `HomeClient` (выше `StudioSwitch`, т.е. над обоими режимами guided↔expert). Lossless switch (incl. File) обеспечен. OK.
- Все 4 хука бросают понятный Error при использовании вне провайдера (guard есть).

Отсутствующих провайдеров в дереве нет.

## 2. humanizeError/тосты заменили сырьё — PARTIAL (не блокер)

Перевёрстанные флоу-компоненты (Job/Reel/Scheduler/Projects/upload) используют `useConfirm` + `toast.showError(err)` корректно: `JobDetailClient`, `JobList`, `ReelCard`, `ExportDialog`, `CampaignDetailClient`, `ProjectsDashboard`, `SchedulerDashboard`, `GuidedFlow`, `ProxyCacheManager`, `maintenance`.

Осталось СЫРЬЁ (legacy settings-клиенты, инлайн `setError`, своя локальная подача — НЕ через тост/confirm):

window.confirm / global confirm():
- `PostProductionSettingsClient.tsx:195,253` — `confirm(...)`
- `SubtitleSettingsClient.tsx:200` — `window.confirm(...)`
- `scheduler/AccountProfilesDashboard.tsx:198` — `confirm(...)`
- `scheduler/CaptionPresetsDashboard.tsx:103` — `confirm(...)`

Сырые ошибки (String(err)/JSON.stringify(err.detail)/err.message в UI-строку):
- `PostProductionSettingsClient.tsx` (131,143,187,205,245,267)
- `SubtitleSettingsClient.tsx` (454,456)
- `PromptsEditorClient.tsx:64`, `VisionProfilesSettingsClient.tsx` (171-172,192-193)
- `MoondreamSettings.tsx:57`, `settings/BrandKitClient.tsx:93`
- `upload/AutoConfigSummary.tsx:44` — `setClearError(...${String(err)})`

Эти файлы НЕ импортируют `useToast`/`useConfirm` — они в пакете E (settings) и используют легаси-паттерн локального `setError`. Большинство хотя бы разбирают `ApiError`/`extractDetail`. Это технический долг, не регресс редизайна флоу; на runtime не падает.

Допустимое сырьё (не в счёт):
- `ui/ErrorBoundary.tsx:86`, `router.tsx`, `pages/NotFoundPage.tsx` — dev-only тех-детали внутри error-экранов (намеренно).

## 3. Флоу связаны с реальными клиентскими функциями — PASS

Все 7 функций определены в `lib/api/*` и вызываются из компонентов:
- `cancelJob` (jobs.ts:222) → `JobDetailClient`, `useWizardState`, `GuidedFlow`.
- `applyAutoConfig` (jobs.ts:228) / `clearAutoConfig` (jobs.ts:235) → `useWizardState`, `upload/AutoConfigSummary`.
- `exportReel` (jobs.ts:314) → `job/ExportDialog`.
- `manualPublishOne` (scheduler.ts:339) → `scheduler/ManualPublishButton`.
- `assignJobToProject` (projects.ts:77) → `useWizardState`.
- `cancelAssignment` (scheduler.ts:326) → `CampaignDetailClient`.

409/502: явная развилка в `CampaignDetailClient.tsx:151-159` (409 = уже опубликовано/необратимо, 502 = Publer недоступен/повторить). `humanizeError` покрывает 400/422/401/403/404/409/429/5xx. `PostProductionSettingsClient:200` ловит 409 отдельно. OK.

## 4. Runtime-безопасность — PASS

- `ReelCard` читает `artifact.meta` через `Record<string,unknown>` + `typeof`-проверки и `?? fallback` (reel_id, duration_sec, cross_context_risk) — без слепого доступа.
- `HomeClient`: polling в try/catch; `latestDoneJob` через `done[0] ?? null`; setInterval-зависимость на булев флаг (нет лишних таймеров).
- `CampaignDetailClient` `.assignments.length` — массив гарантирован моделью (не nullable).
- Поиск небезопасного вложенного доступа (`.reels.`/`.assignments.`/`.artifacts.`/`[0]`/heatmap/score без `?.`/guard) по job/dashboard/scheduler/guided — значимых находок нет.

## 5. Error boundaries + onboarding health-gate — PASS

- Root: `<ErrorBoundary>` в `main.tsx` (ловит сбой провайдеров/роутера).
- Route-level: `<ErrorBoundary>` вокруг `<Outlet/>` в `RootLayout` (рантайм-throw экрана, рейл/шапка живут) + `errorElement: <RouteError/>` на КАЖДОМ роуте (R3 — отделяет сбой lazy-чанка от 404; chunk-error → hard reload). Двойная защита на месте.
- Onboarding (`shell/Onboarding`, смонтирован в `AppShell` под всеми провайдерами): health-gate через `coreApi.health()` → `buildChecks` (gemini/ffmpeg/stt). `hasBlocker` дизейблит «Создать первую нарезку», «Проверить снова» перепингивает, нет связи с сервером — отдельный красный стейт. Открывается при `!onboarded || notReady`. Работает.

## 6. Build — PASS

`pnpm build` → exit 0, `✓ built in ~1.03s`. tsc -b + vite прошли, чанки разбиты (index 327KB / HomePage 90KB и т.д.). Существующее не сломано.

---

## Рекомендации (не блокеры)
1. Перевести 4 `confirm()`/`window.confirm` (PostProduction, Subtitle, AccountProfiles, CaptionPresets) на `useConfirm`.
2. Заменить инлайн `String(err)`/`JSON.stringify(err.detail)` в settings-клиентах (PostProduction, Subtitle, Prompts, VisionProfiles, Moondream, BrandKit, AutoConfigSummary) на `humanizeError`/`toast.showError` для единого UX ошибок.
