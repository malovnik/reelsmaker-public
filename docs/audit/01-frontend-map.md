# 01 — Карта frontend-страниц и компонентов

> **Артефакт REFACTR-01.** Зона охвата: `apps/frontend/src/` (Next.js 16.2.4 + React 19.2.4 + Tailwind 4).
> **Дата:** 2026-04-24.
> **Автор:** R-AUDITOR + R-FRONTEND-ARCHITECT (консультативно).
> **Назначение:** отдать Этапу 04 (миграция Next.js → Vite 6) точную карту: что переносится 1:1, что переделывается в дизайне 2026, что удаляется.

---

## 1. Технологический срез

| Что | Версия / значение | Источник |
|-----|-------------------|----------|
| Next.js | 16.2.4 (App Router, file-based routing) | `apps/frontend/package.json:14` |
| React + React-DOM | 19.2.4 | `package.json:15-16` |
| Tailwind CSS | `^4` + `@tailwindcss/postcss ^4` | `package.json:19-20` |
| TypeScript | `^5` | `package.json:25` |
| ESLint | `^9` + `eslint-config-next 16.2.4` | `package.json:22-23` |
| Router | Next.js App Router (папки `app/`, файлы `page.tsx` / `layout.tsx`) | — |
| Data fetching | Server Component + `fetch` в `app/**/page.tsx` + `api` клиент `src/lib/api` | — |
| SSE | кастомный хук `src/lib/sse.ts` | — |
| State | локальный `useState` + polling (`setInterval` 5 сек на `/` для jobs) | `HomeClient.tsx:44-50` |

**Что отсутствует:** zustand / Redux / TanStack Query / TanStack Router / Radix / Framer Motion / cmdk / react-hotkeys. **Весь state — `useState` + polling.** Это критично для Этапа 04: при миграции на Vite одновременно вводится TanStack Query + Router, что переписывает весь слой data fetching.

---

## 2. OOM-болевой артефакт (подтверждение владельца)

**`apps/frontend/package.json:6`:**

```json
"dev": "NODE_OPTIONS='--max-old-space-size=12288' next dev"
```

**12 ГБ heap для `next dev`.** Это прямое подтверждение заявки в task.md §1: «OOM 12 ГБ в dev». Next.js 16 + hot-reload + ESLint 9 + Tailwind 4 + десятки Client Components съедают всю RAM MacBook M5 Pro. **Цель Этапа 04:** Vite 6 dev idle RAM <500 МБ (х 24 раза меньше).

---

## 3. Таблица маршрутов (19 страниц)

Все маршруты — `apps/frontend/src/app/**/page.tsx`. `layout.tsx` — `app/layout.tsx` (корневой) + `app/settings/layout.tsx` (sidebar subnav).

| # | Маршрут | Файл (page.tsx) | Главный компонент | Render | Статус task.md | Действие при миграции |
|---|---------|-----------------|-------------------|--------|----------------|-----------------------|
| 1 | `/` | `app/page.tsx` | `components/HomeClient.tsx` (Hero + UploadWizard + JobList) | SSR server fetch | **ПЕРЕДЕЛАТЬ → Студия** (task.md §2.4) | Заменить на ProjectGrid + новая модалка «новый проект» (REFACTR-39–44) |
| 2 | `/projects` | `app/projects/page.tsx` | `components/projects/ProjectsDashboard.tsx` | SSR | **СЛИТЬ с `/`** (Студия) | Удалить маршрут, перенести фичи в `/` |
| 3 | `/jobs/[id]` | `app/jobs/[id]/page.tsx` | `components/JobDetailClient.tsx` | SSR | **ПЕРЕДЕЛАТЬ → Workbench** (task.md §2.5) | Переписать на layout video + resizable sidebar + tabs (REFACTR-45–50). URL: `/projects/[id]` или сохранить `/jobs/[id]` — решение REFACTR-45 |
| 4 | `/jobs/[id]/reels/[reelId]` | `app/jobs/[id]/reels/[reelId]/page.tsx` | `components/job/ClipDetailClient.tsx` | SSR | ПЕРЕНЕСТИ в Workbench как lightbox/модалка | Убрать отдельный маршрут, превью в модалке на Workbench |
| 5 | `/jobs/[id]/tinder` | `app/jobs/[id]/tinder/page.tsx` | `components/job/TinderClient.tsx` (470+ LoC, fullscreen, хардкод `bg-black text-white`) | SSR | ПЕРЕНЕСТИ или УДАЛИТЬ (заменяется idea approve/reject REFACTR-48–49) | Tinder-UX встроить в Grid идей с keyboard shortcuts A/R |
| 6 | `/schedule` | `app/schedule/page.tsx` | `components/schedule/ScheduleClient.tsx` | SSR | ПЕРЕНОС | Относится к Publer scheduler — переносится 1:1, редизайн опционально |
| 7 | `/scheduler` | `app/scheduler/page.tsx` | `components/scheduler/SchedulerDashboard.tsx` | SSR | ПЕРЕНОС | 1:1 |
| 8 | `/scheduler/new` | `app/scheduler/new/page.tsx` | `components/scheduler/CampaignWizard.tsx` | SSR | ПЕРЕНОС | 1:1 |
| 9 | `/scheduler/campaigns/[id]` | `app/scheduler/campaigns/[id]/page.tsx` | `components/scheduler/CampaignDetailClient.tsx` | SSR | ПЕРЕНОС | 1:1 |
| 10 | `/scheduler/accounts` | `app/scheduler/accounts/page.tsx` | `components/scheduler/AccountProfilesDashboard.tsx` | SSR | ПЕРЕНОС | 1:1 |
| 11 | `/scheduler/presets` | `app/scheduler/presets/page.tsx` | `components/scheduler/CaptionPresetsDashboard.tsx` | SSR | ПЕРЕНОС | 1:1 |
| 12 | `/settings/brand` | `app/settings/brand/page.tsx` | `components/settings/BrandKitClient.tsx` | SSR | ПЕРЕГРУППИРОВАТЬ в «Визуал» | REFACTR-55 |
| 13 | `/settings/connections` | `app/settings/connections/page.tsx` | `components/ConnectionsSettings.tsx` | SSR | ПЕРЕГРУППИРОВАТЬ в «Интеграции» | REFACTR-55 |
| 14 | `/settings/models` | `app/settings/models/page.tsx` | `components/MoondreamSettings.tsx` + `ProfileSelector` | SSR | ПЕРЕГРУППИРОВАТЬ в «LLM» | REFACTR-54 |
| 15 | `/settings/performance` | `app/settings/performance/page.tsx` | `components/PerformanceSettingsClient.tsx` + **29 групп** в `performance-groups/` | SSR | ПЕРЕГРУППИРОВАТЬ в «Обработка» + accordion | REFACTR-53 |
| 16 | `/settings/post-production` | `app/settings/post-production/page.tsx` | `components/PostProductionSettingsClient.tsx` + **6 секций** | SSR | ПЕРЕГРУППИРОВАТЬ (5 подгрупп в accordion) | REFACTR-53 |
| 17 | `/settings/profiles` | `app/settings/profiles/page.tsx` | `components/VisionProfilesSettingsClient.tsx` | SSR | ПЕРЕГРУППИРОВАТЬ в «Запись» | REFACTR-51 |
| 18 | `/settings/prompts` | `app/settings/prompts/page.tsx` | `components/PromptsEditorClient.tsx` | SSR | ПЕРЕГРУППИРОВАТЬ в «LLM → Промпты» tab с версионностью | REFACTR-54 |
| 19 | `/settings/subtitles` | `app/settings/subtitles/page.tsx` | `components/SubtitleSettingsClient.tsx` + `SubtitleStyleEditor.tsx` (653 LoC) + `SubtitlePreview.tsx` | SSR | **ПОЛНОСТЬЮ ПЕРЕДЕЛАТЬ** (task.md §1 «омерзительно-омерзительно-омерзительно») | REFACTR-52 — адаптивный редактор без h-scroll |

**Сводка по миграции:**
- **1:1 перенос:** 6 маршрутов (scheduler/* — 5 + schedule — 1).
- **Переделать радикально:** 3 (`/`, `/jobs/[id]`, `/settings/subtitles`).
- **Слить / удалить:** 2 (`/projects` → в Студию, `/jobs/[id]/tinder` → интеграция в Workbench).
- **Перегруппировать (IA settings):** 7 (`/settings/*` → 7 смысловых групп REFACTR-51).
- **Tinder-маршрут:** особое решение — перенести клавиатурные shortcuts A/R в Grid идей (REFACTR-49) и удалить отдельный маршрут.

---

## 4. Таблица компонентов (96 файлов .tsx)

**Условные обозначения:**
- 🟢 **переносится 1:1** — функциональный компонент без UI-долга, переносим без изменений.
- 🟡 **переделывается под 2026 дизайн** — логика остаётся, оболочка переписывается на новую дизайн-систему.
- 🔴 **удаляется** — заменяется новой абстракцией в новом дизайне.
- 🟣 **slop-источник** — содержит клишированный AI-дизайн (хардкод bg-black/white, эмодзи, generic shadcn-like) — приоритет на полный редизайн.

### 4.1. Shell (оболочка приложения) — 3 файла

| Файл | LoC | Статус | Назначение | Миграция |
|------|-----|--------|-----------|----------|
| `shell/AppShell.tsx` | 18 | 🟡 | Каркас: NavRail + TopBar + content | 1:1 перенос + Router context (TanStack) |
| `shell/NavRail.tsx` | — | 🟡 | Боковая навигация | 1:1 перенос, редизайн под Студию |
| `shell/TopBar.tsx` | ~50 | 🟡 | Breadcrumbs + сегмент-лейблы | Расширить до context-aware + добавить Cmd+K trigger |

### 4.2. Dashboard / Home — 5 файлов

| Файл | Статус | Миграция |
|------|--------|----------|
| `HomeClient.tsx` | 🔴 | Заменяется на новый ProjectGrid (REFACTR-39) |
| `dashboard/DashboardHero.tsx` | 🔴 | Заменяется новым StudioHeader (REFACTR-43) |
| `dashboard/JobCard.tsx` | 🟡 | Служит основой для ProjectCard (redesign) |
| `dashboard/BulkActions.tsx` | 🟡 | Перенос в StudioHeader bulk-actions |
| `dashboard/FilterChipRow.tsx` | 🟡 | Chip-фильтры в StudioHeader |
| `dashboard/ResultsFilters.tsx` | 🟡 | Логика фильтров — перенос |

### 4.3. Projects (существующий) — 3 файла

| Файл | Статус | Миграция |
|------|--------|----------|
| `projects/ProjectsDashboard.tsx` | 🔴 | Заменяется на Студию |
| `projects/ProjectsList.tsx` | 🔴 | Логика в ProjectGrid |
| `projects/ProjectFormModal.tsx` | 🟡 | Основа модалки «новый проект» (REFACTR-41) |

### 4.4. Job (существующий Workbench) — 11 файлов

| Файл | Статус | Назначение | Миграция |
|------|--------|-----------|----------|
| `JobDetailClient.tsx` | 🔴 | Страница /jobs/[id] | Переписывается в Workbench (REFACTR-45) |
| `JobList.tsx` | 🔴 | Список job'ов на главной | → ProjectGrid |
| `job/JobHero.tsx` | 🟡 | Header job'а | → WorkbenchHeader |
| `job/PipelineTimeline.tsx` | 🟡 | Таймлайн стадий | REFACTR-46 + restart-from-step button |
| `job/ArtifactsAccordion.tsx` | 🟡 | Просмотр артефактов | → debug panel в Expert mode |
| `job/CaptionsEditor.tsx` | 🟡 | Редактор субтитров | Отдельный таб в Workbench |
| `job/ClipDetailClient.tsx` | 🟡 | Детали рилса | → lightbox в ClipGrid |
| `job/ClipScrubber.tsx` | 🟢 | Скраббер видео | 1:1 перенос |
| `job/ExportDialog.tsx` | 🟡 | Экспорт | 1:1 с редизайном UI |
| `job/HeatmapBar.tsx` | 🟢 | Визуализация | 1:1 |
| `job/ReelCard.tsx` | 🟣 | Карточка рилса — хардкод `bg-black/55 text-white border-white/15` (line 240, 254, 285) | Полный редизайн под токены (REFACTR-50) |
| `job/ReelGrid.tsx` | 🟡 | Grid клипов | → ClipsTab в Workbench (REFACTR-50) |
| `job/ScheduleButton.tsx` | 🟢 | Кнопка Publer | 1:1 |
| `job/TinderClient.tsx` | 🔴🟣 | Tinder-UX, 370+ LoC, хардкод `bg-black text-white`, fullscreen overlay | Функция переносится в idea Grid с shortcuts, компонент удаляется |
| `job/WaveformBar.tsx` | 🟢 | Осциллограмма | 1:1 |

### 4.5. Upload — 5 файлов

| Файл | Статус | Миграция |
|------|--------|----------|
| `upload/UploadWizard.tsx` | 🟡 | 4-step wizard | → модалка «новый проект» (REFACTR-41) |
| `upload/WizardSteps.tsx` | 🟡 | Step progress UI | Перенос в модалку |
| `upload/VideoPreviewCard.tsx` | 🟢 | Preview видео | 1:1 |
| `upload/AspectPreview.tsx` | 🟢 | 9:16 preview | 1:1 |
| `upload/AutoConfigSummary.tsx` | 🟡 | Summary пресетов | Перенос + редизайн |

### 4.6. Scheduler (Publer) — 10 файлов

Все 🟢 / 🟡 — переносятся. Это зрелый домен, редизайн опционален.

| Файл | Статус |
|------|--------|
| `scheduler/SchedulerDashboard.tsx` | 🟢 |
| `scheduler/CampaignWizard.tsx` | 🟢 |
| `scheduler/CampaignDetailClient.tsx` | 🟢 |
| `scheduler/ScheduleTimeline.tsx` | 🟢 |
| `scheduler/AccountProfilesDashboard.tsx` | 🟢 |
| `scheduler/CaptionPresetsDashboard.tsx` | 🟢 |
| `scheduler/CaptionPresetFormModal.tsx` | 🟢 |
| `scheduler/AccountsPicker.tsx` | 🟢 |
| `scheduler/ManualPublishButton.tsx` | 🟢 |
| `scheduler/ReelPicker.tsx` | 🟢 |
| `schedule/ScheduleClient.tsx` | 🟢 |

### 4.7. Settings — общие + post-production + performance-groups — 47 файлов

**Общие settings компоненты (корень `components/`):**

| Файл | LoC | Статус | Миграция |
|------|-----|--------|----------|
| `PerformanceSettingsClient.tsx` | 309 | 🟡 | Оркестратор 29 групп → accordion (REFACTR-53) |
| `PostProductionSettingsClient.tsx` | 429 | 🟡 | 6 секций → accordion (REFACTR-53) |
| `SubtitleSettingsClient.tsx` | 458 | 🔴 | **Полная переделка** (REFACTR-52) — корень h-scroll |
| `SubtitleStyleEditor.tsx` | 653 | 🔴 | **Полная переделка** — крупнейший settings-компонент |
| `SubtitlePreview.tsx` | ~600 | 🟡 | Live-preview — перенос + fix цветов (🟣 хардкод `bg-black/70 text-white` line 522, 570, 623) |
| `SplitScreenPreviewEditor.tsx` | — | 🟣 | хардкод `color: "#fff"` (103), `background: "#000"` (297) |
| `ConnectionsSettings.tsx` | — | 🟡 | → «Интеграции» |
| `MoondreamSettings.tsx` | — | 🟡 | → «LLM» |
| `PromptsEditorClient.tsx` | — | 🟡 | → «LLM → Промпты» tab |
| `ProfileSelector.tsx` | — | 🟡 | хардкод `text-white` (131) |
| `VisionProfilesSettingsClient.tsx` | — | 🟡 | → «Запись» |
| `TranscriptCacheBadge.tsx` | — | 🟢 | 1:1 |

**Settings shared controls (`components/settings-shared/`) — 5 файлов:**

| Файл | Статус | Назначение |
|------|--------|-----------|
| `Group.tsx` | 🟡 | Wrapper группы (title + children) — переносится как базовый компонент новой design system |
| `NumberRow.tsx` | 🟡 | Row для number input |
| `SelectRow.tsx` | 🟡 | Row для select |
| `SliderRow.tsx` | 🟡 | Row для slider |
| `SwitchRow.tsx` | 🟡 | Row для toggle |

**Performance groups (`components/settings/performance-groups/`) — 29 файлов** — каждый = одна группа настроек (AdaptiveAudio, AutoMode, Coherence, CrossChunk, CutSnap, Defaults, Ensemble, FillerRemoval, JLCut, LLM, ManualEditingPresetCard, Motion, MultiArc, NarrativeMode, Pacing, PauseCompression, Preference, ProxyCache, Proxy, ProxySkip, Punchline, QualityGates, ReelCount, RenderConcurrency, RhythmCuts, SaveBar, SemanticChunking). Все 🟡 — логика переносится, оболочка — новый дизайн (REFACTR-53).

**Post-production секции (`components/settings/post-production/`) — 9 файлов:**

| Файл | Статус | Примечание |
|------|--------|-----------|
| `AssetsColumn.tsx` | 🟡 | Колонка ассетов |
| `PresetListColumn.tsx` | 🟡 | Колонка пресетов |
| `PresetIdentitySection.tsx` | 🟡 | — |
| `IntroOutroSection.tsx` | 🟡 | — |
| `AudioNormalizationSection.tsx` | 🟡 | — |
| `ZoomSection.tsx` | 🟡 | — |
| `VideoEffectsSection.tsx` | 🟡 | — |
| `SplitScreenSection.tsx` | 🟣 | **`overflow-x-auto` line 181** — подтверждение бедра владельца |
| `shared.tsx` | 🟡 | Shared helpers |
| `index.ts` | 🟢 | Barrel |

**Settings-level components (`components/settings/`):**

| Файл | Статус |
|------|--------|
| `BrandKitClient.tsx` | 🟡 |
| `SettingsSubNav.tsx` | 🟡 |

### 4.8. Итого компонентов

| Категория | Файлов | 🟢 1:1 | 🟡 редизайн | 🔴 удаление | 🟣 slop-источник |
|-----------|-------:|-------:|-------------:|-------------:|------------------:|
| Shell | 3 | 0 | 3 | 0 | 0 |
| Dashboard/Home | 6 | 0 | 5 | 1 | 0 |
| Projects | 3 | 0 | 1 | 2 | 0 |
| Job / Workbench | 15 | 4 | 7 | 2 | 3 |
| Upload | 5 | 2 | 3 | 0 | 0 |
| Scheduler | 11 | 11 | 0 | 0 | 0 |
| Settings (общие) | 12 | 1 | 6 | 2 | 3 |
| Settings shared (атомы) | 5 | 0 | 5 | 0 | 0 |
| Performance groups | 29 | 0 | 29 | 0 | 0 |
| Post-production | 10 | 1 | 8 | 0 | 1 |
| Settings/brand + nav | 2 | 0 | 2 | 0 | 0 |
| **Итого** | **101** | **19** | **69** | **7** | **7** |

*Разница с `find` (96 файлов) — `index.ts`/`shared.tsx` учтены отдельно.*

**Вывод:** 19 компонентов (19%) переносятся 1:1, 69 (68%) редизайнятся, 7 удаляются, 7 содержат явный slop-хардкод. Это реалистичный объём для Этапов 04–08.

---

## 5. `lib/` и `hooks/` — 13 файлов

| Файл | LoC | Статус | Миграция |
|------|-----|--------|----------|
| `lib/api.ts` | — | 🟡 | Фасад-реэкспорт для обратной совместимости, будет удалён после миграции на TanStack Query |
| `lib/api/core.ts` | — | 🟡 | `fetch`-wrapper → переделать под `api()` helper (REFACTR-29) |
| `lib/api/index.ts` | — | 🟡 | Barrel |
| `lib/api/jobs.ts` | — | 🟡 | Клиент `/jobs` → `useJobs`, `useJob` hooks |
| `lib/api/projects.ts` | — | 🟡 | Клиент `/projects` |
| `lib/api/post_production.ts` | — | 🟡 | Клиент `/post-production` |
| `lib/api/scheduler.ts` | — | 🟡 | Клиент `/scheduler` |
| `lib/api/settings.ts` | — | 🟡 | Клиент `/settings/*` |
| `lib/api/subtitle.ts` | — | 🟡 | Клиент `/settings/subtitles` |
| `lib/constants/scheduler.ts` | — | 🟢 | Константы — 1:1 |
| `lib/sse.ts` | — | 🟡 | `EventSource` wrapper → `useEventSource` hook (REFACTR-29) |
| `lib/video-thumbnail.ts` | — | 🟢 | Генерация thumbnail из `<video>` — 1:1 |
| `lib/viralScore.ts` | — | 🟢 | Scoring formula — 1:1 |
| `hooks/useSettingsSave.ts` | — | 🟡 | Debounced save → универсальный `useAutoSave` с ETag (REFACTR-09) |

---

## 6. Проблемные места (🔴 от владельца) — file:line verification

### 6.1. OOM 12 ГБ в dev

**Подтверждено:** `apps/frontend/package.json:6`

```
"dev": "NODE_OPTIONS='--max-old-space-size=12288' next dev"
```

**Диагноз:** Next.js 16 + Tailwind 4 + ESLint 9 + React Server Components + hot-reload — heap растёт до 12 ГБ. Удаляется вместе с Next.js в REFACTR-31.

### 6.2. Горизонтальная прокрутка в `/settings/subtitles`

**Корень:** `components/SubtitleSettingsClient.tsx:239`

```tsx
<div className="grid grid-cols-1 gap-6 lg:grid-cols-[240px_1fr_auto]">
```

Трёхколоночный grid: **preset list (240px) + editor (1fr) + preview (auto)**. Родительский `app/settings/layout.tsx` — `max-w-7xl` (1280px) + subnav 240px = **main area ≤ 1020px**. При полном `SubtitleStyleEditor` (653 LoC controls, включая fonts picker, 2-col grids — строки 70, 238: `grid grid-cols-2 gap-3`) + preview (обычно 360-400px) получается **editor «съедает» preview**, либо контент шире viewport → h-scroll на body уровне.

**Сопутствующие места:**
- `components/settings/post-production/SplitScreenSection.tsx:181` — `<div className="overflow-x-auto">` — локальный h-scroll в split-screen секции.
- `components/PostProductionSettingsClient.tsx:315` — `lg:grid-cols-[260px_260px_1fr]` — ещё один трёхколоночный grid в main area (260+260+1fr = минимум ~650px + margins).

**Решение Этапа 08:** breakpoint-aware layout. На 1024/1280 — 2 колонки (list+editor), preview — bottom sticky или tab. На 1920+ — 3 колонки комфортно.

### 6.3. Пост-продакшн без группировки

**Корень:** `components/PostProductionSettingsClient.tsx:374-414`

Все 6 секций (`PresetIdentitySection`, `IntroOutroSection`, `AudioNormalizationSection`, `ZoomSection`, `VideoEffectsSection`, `SplitScreenSection`) рендерятся подряд в одной колонке — без accordion, без категоризации, всё одновременно открыто. Страница — «колбаса» контролов без визуальной иерархии.

**Решение:** REFACTR-53 — 5 подгрупп в accordion (Silence, Audio, Color/LUT, Transitions, Effects).

### 6.4. Смешанные тёмные/светлые шрифты — хардкод-цвета

**Статистика grep:**
- `bg-white` / `bg-black` — **35 вхождений** в .tsx.
- `text-white` — массовый хардкод. Ключевые очаги:

| Файл | Строки | Pattern |
|------|--------|---------|
| `components/job/TinderClient.tsx` | 195, 199, 205, 246, 252, 268, 351, 358 | fullscreen `bg-black text-white` — весь компонент tinder-fullscreen hardcoded |
| `components/job/ReelCard.tsx` | 240, 241, 254, 255, 285, 286, 334, 413, 422 | `border-white/40`, `bg-black/55 text-white`, `border-white/15` — все overlay-элементы карточки |
| `components/SubtitlePreview.tsx` | 522, 570, 623 | `bg-black/70 text-white`, `bg-sky-500/85`, `bg-red-600/80` — debug бейджи поверх preview |
| `components/SplitScreenPreviewEditor.tsx` | 103, 297 | inline styles `color: "#fff"`, `background: "#000"` |
| `components/job/PipelineTimeline.tsx` | 133, 154 | `text-white` в иконках стадий |
| `components/ProfileSelector.tsx` | 131 | `text-white` в badge |
| `components/JobList.tsx` | 317 | `text-white` на danger-кнопке |
| `components/dashboard/BulkActions.tsx` | 27 | `text-white` на danger-кнопке |
| `components/dashboard/JobCard.tsx` | 234 | `border-white/40 text-white` в selection state |
| `components/settings/performance-groups/ManualEditingPresetCard.tsx` | 25 | `bg-violet-600 text-white` |

**Где правильно** (как показать пример): `components/JobList.tsx:317` — используется `bg-[color:var(--danger)]` (var-токен) — но всё равно `text-white` хардкодом. В новой дизайн-системе (REFACTR-33) token будет `--danger-fg` с парой light/dark.

**Решение:** REFACTR-33/34 — все цвета через CSS-variables, dark/light theme pair. REFACTR-50 — полный редизайн ReelCard. TinderClient удаляется как отдельный маршрут.

### 6.5. Cmd+K не работает

**Подтверждено (негативным grep):**

```bash
grep -rnE "cmdk|CommandPalette|CommandMenu|command-palette|useHotkeys|keydown" apps/frontend/src
# 0 matches
```

**Диагноз:** нет ни импорта библиотеки `cmdk`, ни keyboard listener, ни даже комментария. Функция не реализована. В `TopBar.tsx` — только breadcrumbs, никаких хоткеев.

**Решение:** REFACTR-57 — `cmdk` библиотека + context-aware actions (новый проект, открыть настройки, поиск по проектам, ребилд стадии). Глобальный listener `<Shell>` на `meta+K` / `ctrl+K`.

---

## 7. Риски миграции и архитектурные находки

### 7.1. Server Components зависимости — точки разрыва при миграции на Vite

В `app/page.tsx` и `app/settings/**/page.tsx` используется `await api.*` прямо в async server component:

```tsx
// app/settings/subtitles/page.tsx:21-25
const [presets, fontList] = await Promise.all([
  api.listSubtitlePresets(),
  api.listFonts(),
]);
```

В Vite SPA нет RSC — server fetch переезжает в `loader` TanStack Router + TanStack Query hydration (или Suspense).

### 7.2. Polling вместо реактивности

`HomeClient.tsx:44-50` и аналогичные — `setInterval(refreshJobs, 5000)`. Нет SSE подписки на job-events (хотя в backend она есть через `/api/v1/jobs/{id}/events`). SSE используется только в `lib/sse.ts`, вероятно в job detail.

**Вывод для REFACTR-29:** мигрировать polling → SSE через `useEventSource` hook, как указано в task.md §5.3.

### 7.3. AGENTS.md / CLAUDE.md в `apps/frontend/` — дополнительные инструкции

`apps/frontend/AGENTS.md` и `apps/frontend/CLAUDE.md` — отдельные инструкции для фронта. Перед миграцией на Vite — прочитать и перенести.

### 7.4. Next.js специфические импорты

`import Link from "next/link"`, `import { usePathname } from "next/navigation"` — в `shell/TopBar.tsx`, `settings/SettingsSubNav.tsx` и др. При миграции (REFACTR-28) — замена на `@tanstack/react-router` (`Link`, `useRouterState`).

### 7.5. Нет тестов

Ни одного `*.test.tsx` / `*.spec.tsx` файла. Это **не баг** (по task.md §6.4 тесты запрещены кроме корректности сборки), но означает, что миграция верифицируется только smoke-сценариями + визуальной проверкой (REFACTR-62–64).

### 7.6. Зона с 🟣 slop-паттерном

Компоненты с tinder-стилем (`bg-black text-white` fullscreen):
- `TinderClient.tsx` (🔴 удалить как маршрут).
- `ReelCard.tsx` (overlay controls поверх видео) — исторически dark-only. В новой design system нужен overlay-токен, работающий в обеих темах (REFACTR-50).

---

## 8. Что отдать REFACTR-02 (инвентаризация настроек)

REFACTR-02 требует детализации 8 страниц `/settings/*`. Уже известно:
- **7 маршрутов** (profiles, models, performance, post-production, prompts, subtitles, brand, connections = 8 — с brand/connections = 8).
- **12 settings-level файлов** + **29 performance-groups** + **9 post-production секций** + **5 shared row-controls**.
- Главные источники h-scroll: `SubtitleSettingsClient:239` (3-col grid) и `PostProductionSettingsClient:315` (3-col grid) + `SplitScreenSection:181` (overflow-x-auto).
- **PerformanceSettings** — 50+ Pydantic полей в backend `models/runtime_settings.py` (см. REFACTR-00 §9.1 / §10.2) отображается через 29 групп на фронте. **Главная цель REFACTR-53** — accordion + Simple/Expert фильтр.

---

## 9. Что отдать REFACTR-03 (PRO-код)

На фронте есть компонент:
- `components/settings/performance-groups/NarrativeModeGroup.tsx` — UI-selector для `narrative_mode`. После REFACTR-13 бэкенда — только `viral_2026` (default) + `chaptered` (Chapter Legacy).

---

## 10. Ключевые находки (TL;DR)

1. **19 маршрутов**: 6 переносятся 1:1, 3 переделываются (`/`, `/jobs/[id]`, `/settings/subtitles`), 2 удаляются/сливаются (`/projects`, `/jobs/[id]/tinder`), 7 группируются в новую IA settings, 1 (reels detail) становится модалкой.
2. **101 компонент**: 19 1:1, 69 редизайн, 7 удаляются, 7 — slop-источники.
3. **OOM 12 ГБ подтверждён** в `package.json:6`.
4. **H-scroll корень** — `SubtitleSettingsClient.tsx:239` (3-col grid в 1020px main area) + `PostProductionSettingsClient.tsx:315` (3-col 260+260+1fr) + `SplitScreenSection.tsx:181` (overflow-x-auto).
5. **Cmd+K полностью отсутствует** — 0 результатов grep по всем ключевым словам.
6. **Post-production без accordion** — 6 секций подряд в одной колонке без группировки.
7. **Хардкод цветов** — 35 `bg-white`/`bg-black` + десятки `text-white` в TinderClient/ReelCard/SubtitlePreview. Ключевая область для REFACTR-33/50.
8. **Нет TanStack Query / cmdk / Radix / Framer Motion** — весь state на `useState` + polling. Миграция на Vite одновременно вводит все эти зависимости (REFACTR-27/29).
9. **Scheduler (10 файлов) — самый зрелый домен** — 1:1 перенос без редизайна.
10. **Performance-groups — 29 мелких файлов** — лучший паттерн модульности в кодовой базе, переносятся как есть, оборачиваются в accordion на Этапе 08.

---

## 11. Дорожная карта миграции по фронту (матрица)

| Этап | Чанки | Что делаем с frontend |
|------|-------|----------------------|
| 04 | REFACTR-27–31 | Полный skeleton Vite + TanStack + миграция 19 маршрутов (file-based routes) + API-hooks + SSE + удаление Next.js |
| 05 | REFACTR-32–38 | Дизайн-система: manifest, токены, dark/light, атомы/молекулы, motion. **Все 🟣 компоненты правятся здесь через токены.** |
| 06 | REFACTR-39–44 | Студия: новая главная (заменяет HomeClient+DashboardHero+ProjectsDashboard+JobList). |
| 07 | REFACTR-45–50 | Workbench: переписывается `/jobs/[id]` + ReelCard + Grid идей с approve/reject/regenerate + Pipeline timeline + Clips tab. TinderClient удаляется как маршрут. |
| 08 | REFACTR-51–57 | Новая IA settings (7 групп), SubtitleSettings без h-scroll, PostProd в accordion, Simple/Expert, Cmd+K. |

---

**Артефакт записан:** `docs/audit/01-frontend-map.md`
**Serena memory:** `refactr-01-frontend-map`
**Следующий чанк:** REFACTR-02 — Инвентаризация настроек (8 `/settings/*` страниц, полный список полей с file:line, hunt h-scroll).
