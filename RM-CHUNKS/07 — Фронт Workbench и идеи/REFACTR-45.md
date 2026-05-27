# REFACTR-45 — Layout Workbench (видео + sidebar + main area)

> **Этап:** 07 — Фронт: Workbench + идеи
> **Шаг:** 46 из 67
> **Зависимости:** Этап 05 (дизайн-система), Этап 02 (API проектов).
> **Следующий шаг:** REFACTR-46 (Pipeline timeline + restart)

**ОБЯЗАТЕЛЬНО:** `frontend-design` skill активен.

---

## Роли

### R-DESIGN-ALCHEMIST
**Soul:** Workbench — это Pro-инструмент. Плотный, но не клаустрофобный. Три зоны: видео, стадии, контент-область.

### R-FRONTEND-ARCHITECT
**Soul:** Split-layout с resizable panels. TanStack-compatible. Состояние панелей в localStorage.

---

## ТРИЗ-принцип

*Принцип матрёшки.* Workbench = Layout > зоны > компоненты. Sidebar слева раскрывается/сворачивается, main area адаптируется.

---

## Оркестрация

**Режим:** Sequential.

---

## Микрозадачи

### 45.1 Layout

```
┌─────────────────────────────────────────────────────────────┐
│ TopBar (общий) — ← Назад в Студию, название проекта, меню  │
├───────────┬─────────────────────────────────────────────────┤
│ Sidebar   │ Main area                                       │
│           │                                                 │
│ Pipeline  │   ┌────────────────────────┐                    │
│ stages:   │   │ Video player (preview) │                    │
│ ● Transc.│   │ 9:16 или 16:9          │                    │
│ ● Silen. │   └────────────────────────┘                    │
│ ◐ Ideas  │                                                 │
│ ○ Compose│   Tabs: Идеи | Клипы | Настройки               │
│ ○ Render │                                                 │
│           │   < контент выбранного таба >                   │
│           │                                                 │
└───────────┴─────────────────────────────────────────────────┘
```

### 45.2 Роут

`src/routes/jobs/$jobId.tsx` — преобразовать в Workbench. Параметр `$jobId` == project_id.

### 45.3 TopBar контекстный

Внутри Workbench — TopBar дополняется:
- Ссылка «← Студия».
- Название проекта (inline-rename, см. REFACTR-40 логика).
- Меню справа: открыть в Finder, удалить, экспорт.

### 45.4 Sidebar (PipelineStages)

Отдельный компонент `src/features/workbench/PipelineSidebar.tsx`.
Полное содержимое — REFACTR-46 (timeline + restart).

Здесь — только layout: sidebar занимает 240 px ширины, collapsible (иконка collapse).

### 45.5 Main area

Отдельный компонент `src/features/workbench/WorkbenchMain.tsx`:

- Video player сверху (aspect ratio — оригинальный, но кепка max-height 40vh).
- Tabs под ним: Идеи / Клипы / Настройки.
- Контент таба.

Video player: HTML `<video>` с минимальным хромом (play/pause, scrubber, volume). `ClipScrubber` уже есть в legacy — переносим.

### 45.6 Resizable

- Sidebar ширина — resizable через `react-resizable-panels` или собственный drag-handle.
- Ширина сохраняется в localStorage (`videomaker-workbench-sidebar-w`).

### 45.7 Loading states

- Project загружается → skeleton layout.
- Project not found → 404 с кнопкой «В Студию».

### 45.8 Verify frontend-design

- [ ] Плотный layout, но не давящий.
- [ ] Video player dominant (контент > хром).
- [ ] Sidebar не перегружен (иначе свёрнуть).

### 45.9 Commit + Serena

---

## GATE-чекпоинт

- [ ] `/jobs/{id}` открывается, показывает video + sidebar + main.
- [ ] Video play/pause работает.
- [ ] Tabs переключаются.
- [ ] Sidebar collapse/expand.
- [ ] Resize работает, persist.

---

## Артефакт на выходе

WorkbenchPage + PipelineSidebar (заготовка) + WorkbenchMain + VideoPlayer + Tabs.
