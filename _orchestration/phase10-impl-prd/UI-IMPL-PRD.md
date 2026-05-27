# UI-IMPL-PRD — реализационный PRD редизайна (Phase 10)

> Консолидация 3 агентов (frontend-skill): data-binding, логика/состояние, последовательность. С внесёнными уточнениями.
> Вход для Phase 11 (стройка). Секции: [p10-1 binding](p10-1-binding.md) · [p10-2 logic](p10-2-logic-state.md) · [p10-3 sequencing](p10-3-sequencing.md)

## Готовность
- **Data-binding ~92%**, 0 осиротевших клиентов. Реальных эндпоинтов **82** (section-1 пропустила `/jobs/{id}/cancel`).
- **Логика реализуема** на React 19 + react-router 7. Data-слой (loaders, lib/api, useJobSse, useWizardState, useSettingsSave) переживает редизайн нетронутым.

## Разрешённые противоречия
1. **Export**: реально перекодирует (подтверждено Phase 6/7 по коду — jobs.py транскод через ffmpeg). section-1 «PARTIAL STUB» — УСТАРЕЛО. UI МОЖЕТ честно показывать bitrate/LUFS (они применяются).
2. Per-reel скор/heatmap/оценка времени — клиентские эвристики (не ручки), честно маркированы в спеке. ОК.

## HIGH-уточнения (внести в стройку)
- **R1 — guided S1-S11 = НОВЫЙ код.** Текущий `UploadWizard.tsx` (905 строк) рендерит все 6 шагов одновременно в одном скролле (`<Step>` — визуальный заголовок, нет `currentStep`/навигации). Пошаговая машина строится заново (пакет B).
- **R2 — WizardStateProvider обязателен.** Переключение guided↔expert без потери данных (включая `File`) невозможно при двух деревьях над локальным `useWizardState` (размонтирование обнулит). Нужен `WizardStateProvider` над обоими режимами. Спека (d2 §5) обещала, механизм дописываем.
- **R3 — route-level errorElement.** При lazy всех роутов root `errorElement:<NotFoundPage/>` поглотит и rejection чанков, и 404 — нужен отдельный route-level errorElement (не только root).
- **R5 — 100% tooltip через ТИПЫ**, не выдуманный билд-плагин: `name: keyof typeof controlHints` + обязательный `hint`-проп примитивов.
- **PF — memo на ReelCard** + узкая подписка (SSE-каскад в широкой галерее xl:5/2xl:6).

## Стратегия миграции токенов (аддитивно-замещающая, БЕЗ переименований)
- Токены двухслойные: физика (`--ink/--paper/--gold`) → семантика (`--text-primary/--surface-raised/--accent-primary`). 89 файлов потребляют семантику.
- **Меняем ЗНАЧЕНИЯ физ-слоя** на брендбук (Kuro/Sumi/Hai/Shiroi/Kasumi/Kinzoku/Dō/Kogane/Chi) + **перенаправляем семантику** на новую физику. Всё в `globals.css`.
- **Семантические имена НЕ переименовываем** → 89 файлов на `var(--*)` не ломаются, меняется только вид. (Переименование = 700+ правок = overreach.)
- `border-radius:0`: глобальный override `--radius-*` в @theme (72 файла с `rounded-*` → no-op) + чистка в пакетах. `box-shadow` запрет: 15 файлов. Шрифты: Noto Serif JP / Manrope / JetBrains Mono / Press Start 2P через @fontsource.
- Light-тему НЕ строим (спека резервирует, не переключатель).
- `router-compat.ts` (next/navigation эмуляция, 10 файлов) — НЕ мигрировать (overreach), зафиксировать как осознанный compat.

## Последовательность стройки (Phase 11)
**Долги → Фундамент → Оболочка → Режимы → Экраны → Полировка.**
Примитивы строго ДО перевёрстки экранов (иначе двойная работа). God-компоненты (CampaignDetailClient 878, CampaignWizard 491, SubtitleStyleEditor 652, SubtitlePreview 629, TinderClient) декомпозировать по образцу `performance-groups/` ПЕРЕД перевёрсткой, изолированно в своих пакетах.

## 5 пакетов для Phase 11 (по файловым доменам, без пересечений)
| Пакет | Зона | Файлы |
|-------|------|-------|
| **A — Фундамент** (СНАЧАЛА, последовательный, блокирует B-E) | токены, роутинг, примитивы, оболочка, контексты | `globals.css`, `router.tsx`, `components/ui/*` (новый), `components/shell/*`, `lib/nav/*` (новый), `UiModeContext`/`ToastContext`/`ConfirmContext`/`WizardStateProvider`, ErrorBoundary, humanizeError |
| **B — Студия/визард** | guided + expert режимы | `components/upload/*`, `HomeClient`, новые guided/expert обёртки |
| **C — Job/Reel** | детали джоба/рилса/tinder/dashboard | `components/job/*` (12), `components/dashboard/*`, `JobDetailClient`, `JobList` |
| **D — Scheduler/Projects** | публикация, проекты | `components/scheduler/*`, `components/projects/*` |
| **E — Settings** | настройки + tooltip-реестр | `components/settings*`, `settings-shared`, `maintenance`, `controlHints` реестр |
Общая точка — `router.tsx` и `globals.css` — правит ТОЛЬКО пакет A, замораживается до старта B-E.

## Минорное (доводка)
4 ручки не в UI (getDefaultPostProductionPreset, single-GET subtitle-preset/vision-profile/asset) — list-варианты покрывают; добавить при касании.

## Build-gates (Phase 11, на каждом пакете)
`pnpm build` (tsc -b + vite — подтверждено зелёным в Phase 6) + при нужде `tsc --noEmit`. Tooltip-gate через типы. Не ломать существующее.

## Метрики приёмки (Phase 12 валидация)
- Оба режима работают, переключение без потери данных (incl. File).
- Визуал по брендбуку (samurai brass-on-black, прямые углы, шрифты, токены).
- Tooltip на 100% контролов Эксперта. Error boundaries ловят. Тосты/confirm/humanizeError.
- pnpm build зелёный, существующее не сломано, data-binding работает (cancel/export/autoconfig/publish/project).
