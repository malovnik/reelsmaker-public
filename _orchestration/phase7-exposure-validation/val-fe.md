# Frontend Acceptance Validation — Phase 7 (по коду)

Скоуп: frontend-эпики PRD-expose. Метод: grep + чтение call-site'ов + `pnpm build` + `tsc --noEmit` + проверка router.tsx.
Корень: `apps/frontend/src`.

## Сводный вердикт
| Эпик | Вердикт |
|------|---------|
| 1 — Убрать ложь UI | PASS |
| 2 — Связать обрывы потока | ЧАСТИЧНО (1 дыра: папка проекта недостижима из UI) |
| 3 — Cancel job | PASS |
| 4 — Automatic Mode | PASS |
| 6 — Честные tier'ы | PASS |
| 7 — Vision/face opt-in | PASS |
| 8 — Доводка экспозиции | PASS |

**Build:** `pnpm build` ✅ зелёный (182 modules, built in 914ms). **tsc --noEmit** ✅ exit 0.
Единственное предупреждение build — косметический CSS-lint на комментарий в `index.css` (`Unexpected token Delim('*')`), не ошибка, не ломает сборку. Плюс штатный warning о chunk >500kB.

---

## EPIC 1 — Убрать ложь UI — PASS

- **R1.1 connections/youtube** — PASS. `grep "connections/youtube|ConnectionsPage|/settings/connections"` → NONE. Роута нет в `router.tsx`, навигация чистая.
- **R1.2 chaptered** — PASS. Не предлагается как выбираемая опция: `NarrativeModeGroup.tsx:5` type = `bottom_up|map_reduce|viral_2026`; `:29` старое значение `chaptered` из БД коерсится в `bottom_up`, чтобы радиогруппа не висела пустой. В `settings.ts:158` `chaptered` остаётся лишь в union типа ответа сервера (read-only DTO), не как UI-контрол. Мёртвой выбираемой опции нет.
- **R1.3 dead providers** — PASS. Pipeline-provider select фильтруется: `useWizardState.ts:156` `livePipelineProviders = available_providers.filter(p === "gemini" || p === "zhipu")`. `anthropic/openai` упоминаются только в комментарии. `deepgram` в `ModelsPage.tsx:64` — это read-only **статус транскрайберов** (точка доступности ключа), не pipeline-LLM-селект — корректно.
- **R1.4 viral-score** — PASS. Честно подписан: `ReelCard.tsx:162` «Клиентская эвристика по длине и ритму, не оценка движка нарезки», `:420` title аналогично, `ClipDetailClient.tsx:223` «эвристика длины и ритма».

## EPIC 2 — Связать обрывы потока — ЧАСТИЧНО

- **R2.1 project_id / assignJobToProject** — PASS. Клиент `assignJobToProject` (`projects.ts:77` → `PATCH /api/v1/jobs/{id}/project`) вызывается в `useWizardState.ts:322` сразу после создания джоба (паттерн из уточнения PRD: не в `POST /jobs`, а отдельным PATCH).
- **R2.2 экран папки saved/<folder>** — **ЧАСТИЧНО / дыра.** `pages/ProjectFolderPage.tsx` существует (127 строк), залужен в роутинге `router.tsx:52` (`projects/:id/folder`, lazy + Suspense), имеет back-link на `/projects` и ссылки на рилсы. **НО:** ни одного inbound-перехода в UI — карточки проектов в `ProjectsList.tsx` имеют только кнопки «Редактировать»/«Удалить» (нет «Открыть папку»), `grep` ссылок на `/folder` вне самого роутера/страницы → NONE. Страница достижима только ручным вводом URL. Не битая ссылка (висячих нет), но недостижимый экран = поток обрывается на шаге «открыть папку проекта».
- **R2.3 legacy /schedule + ScheduleButton** — PASS. `grep "api/v1/schedule"(singular)|ScheduleButton` → только `/api/v1/scheduler/*` (множественное, Publer-механизм PD3). Legacy singular-эндпоинта и кнопки нет. Один механизм публикации.
- **R2.4 ManualPublishButton** — PASS. Смонтирован: `ReelCard.tsx:145` `<ManualPublishButton artifactId jobId label="Опубликовать">`; клиент `scheduler.ts:340` → `POST /api/v1/scheduler/manual/publish-one`.
- **R2.5 done-CTA** — PASS. `HomeClient.tsx:72-89` — крупный блок «нарезка готова» с кнопкой «Смотреть рилсы» → `/jobs/{id}`, показывается когда нет активных джобов и есть свежий `done`.
- **R2.6 cancel публикации (Publer)** — бэкенд-скоуп (не frontend). Клиент `cancelAssignment` есть (`scheduler.ts:328` `/assignments/{id}/cancel`). Реальный отзыв в Publer — серверная проверка, вне этого FE-валидатора.

## EPIC 3 — Cancel job — PASS

- **R3.1** — PASS. Клиент `cancelJob` (`jobs.ts:222` → `POST /api/v1/jobs/{id}/cancel`); вызов `JobDetailClient.tsx:30`. Кнопка «Отменить обработку» рендерится под `{isActive && ...}` (`JobDetailClient.tsx:124-128`), с disabled-состоянием и error-выводом. Активна только для активного джоба.

## EPIC 4 — Automatic Mode — PASS

- **R4.1** — PASS. `applyAutoConfig` (`jobs.ts:228` PATCH) + `clearAutoConfig` (`jobs.ts:235` DELETE) реализованы. Clear-UI: `AutoConfigSummary.tsx` — кнопка «Сбросить авто-настройки» (handleClear:32, `:40` `api.clearAutoConfig`), clearing/clearError состояния. Apply: `useWizardState.ts:401` PATCH `/auto-config`.
- **R4.2 like-контракт** — VERIFY-ONLY (бэк). `liked` enum-контракт `jobs.ts:191` — фронт-сторона совпадает с задекларированным; рассогласований в FE нет.

## EPIC 6 — Честные tier'ы — PASS

- **R6.1/R6.2** — PASS. `LLMGroup.tsx`: тоггл `llm_tier_profile` (`:22`) с честными опциями `:27` «Качество — Pro / Flash / Flash-Lite по стадиям» vs legacy «Классика — одна Flash Lite». Предупреждение о Pro `:35-36` «заметно дороже и медленнее обычного. Используй осознанно». Дефолтная модель — Flash-Lite (cost control), Pro = opt-in. Тоггл реально пишет `llm_tier_profile`.

## EPIC 7 — Vision/face opt-in — PASS

- **R7.2 двухуровневый тоггл + пометка** — PASS. `MotionGroup.tsx:92` Face tracker — label «· экспериментально, opt-in», hint описывает process-изоляцию + hard-таймаут + фолбэк на center-crop, default OFF (`:94` `?? false`). `MoondreamSettings.tsx:163` vision — «Включить анализ кадров · экспериментально, opt-in». Оба уровня честно помечены, дефолт безопасный.
- **R7.3 profile/suggestion триггер в UI** — PASS. `useWizardState.ts:147-149,328-332` стейт + `getProfileSuggestion(job.id)`; UI в `UploadWizard.tsx:809-837` — карточка рекомендованного профиля с confidence %, reasons и кнопкой `applyProfileSuggestion`.

## EPIC 8 — Доводка экспозиции — PASS

- **R8.1 proxies UI** — PASS. `ProxyCacheManager.tsx` смонтирован в `MaintenancePage.tsx:20`.
- **R8.2 fonts refresh** — PASS. `FontsRefresh.tsx` (POST `/settings/fonts/refresh`) смонтирован `MaintenancePage.tsx:21`.
- **R8.3 thumbnail хелперы** — PASS. `jobs.ts:215` `jobThumbnailUrl`, `:217` `sourceThumbnailUrl`, `:219` assets/thumbnail хелпер.

---

## Router-аудит (битые/висячие ссылки)
- Все `import`/lazy в `router.tsx` резолвятся (build + tsc зелёные).
- Висячих ссылок (link на несуществующий роут) НЕ найдено.
- **Обратная проблема:** роут `projects/:id/folder` существует, но НЕ имеет inbound-ссылки → недостижим из UI (см. R2.2). Не «битая ссылка», а недостижимый экран.

## Дыры (для Phase 6/9)
1. **R2.2 (ЧАСТИЧНО):** `ProjectFolderPage` недостижима из UI — нет кнопки/ссылки «Открыть папку» на карточке проекта (`ProjectsList.tsx`). Поток create→…→view папки проекта обрывается. Добавить `<Link to={`/projects/${p.id}/folder`}>` на карточку. PRD «ОТКРЫТЫЕ ЗАВИСИМОСТИ от Phase 9» допускает, что сами экраны папок доделываются в редизайне — но inbound-навигация сейчас отсутствует полностью.

## pnpm build (результат)
```
vite v7.3.2 building client environment for production...
✓ 182 modules transformed.
dist/assets/ProjectFolderPage-*.js   2.91 kB  (code-split OK)
dist/assets/index-*.js             705.22 kB │ gzip: 191.86 kB
✓ built in 914ms
```
Warning: косметический CSS-lint (комментарий в @theme) + chunk>500kB. Ошибок нет. `tsc --noEmit` exit 0.
