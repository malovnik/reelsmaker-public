# REFACTR-39 — Grid проектов + карточка проекта

> **Этап:** 06 — Фронт: Студия и проекты
> **Шаг:** 40 из 67
> **Зависимости:** Этап 05 (дизайн-система), REFACTR-14..18 (API проектов).
> **Следующий шаг:** REFACTR-40 (Контекстное меню)

**ОБЯЗАТЕЛЬНО:** `frontend-design` skill активен.

---

## Роли

### R-DESIGN-ALCHEMIST
**Soul:** Студия — витрина. Превью проектов — визуальный акцент. Chrome — прозрачен.

### R-FRONTEND-ARCHITECT
**Soul:** Grid — responsive, виртуализация при 100+ проектах. TanStack Virtual (future-proof).

### R-UX-WRITER
**Soul:** Пустое состояние: не «у вас нет проектов», а что-то живое («Начнём с первого видео?»).

---

## ТРИЗ-принцип

*Принцип сегментации.* Студия = grid + header + empty state + loading state. Каждая часть — свой компонент.

---

## Оркестрация

**Режим:** Sequential.

---

## Микрозадачи

### 39.1 Layout главной

`src/routes/index.tsx`:

```tsx
export const Route = createFileRoute('/')({
  component: StudioPage,
});

function StudioPage() {
  return (
    <div class="flex flex-col h-full">
      <StudioHeader />          {/* REFACTR-43: filters, sort, search */}
      <ProjectGrid />            {/* this chunk */}
    </div>
  );
}
```

### 39.2 ProjectGrid

`src/features/studio/ProjectGrid.tsx`:

- Loading skeleton (на время Query).
- Empty state (если нет проектов).
- Grid `grid-cols-2 md:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-4`.
- На 100+ проектов — TanStack Virtual grid (заготовка на будущее, сейчас простой grid).

### 39.3 ProjectCard

`src/features/studio/ProjectCard.tsx`:

Структура карточки:
- Превью (aspect-ratio 9:16 перевёрнуто → 16:9 для thumbnail — ширина-приоритет; либо 9:16 с реальным превью видео, решить по дизайн-эксперименту).
- Название проекта (text-md, weight 500).
- Статус-chip (pending / running / ready / error).
- Дата изменения (text-xs text-muted).
- Меню (три точки — открывает контекстное меню, REFACTR-40).

Hover:
- scale 1.02 + shadow-lift + border accent-subtle.

Click on card: navigate → `/jobs/{projectId}` (Workbench).

### 39.4 Превью

API: `GET /api/projects/{id}/preview` → возвращает первый кадр исходного видео (ffmpeg-extracted). Если нет — placeholder (колонка с градиентом accent-muted → bg-tertiary).

Поле в Project: `preview_path` — путь к файлу preview. Генерируется при upload.

Backend-fix если отсутствует (добавить в REFACTR-14 или отдельно) — если preview не генерируется, добавить.

### 39.5 Анимация входа

- Первая загрузка: cards появляются с `stagger` (задержка 30 мс между карточками).
- Framer Motion `AnimatePresence` + `motion.div` с delay.
- Subsequent renders: без анимации (uncomment useReducedMotion).

### 39.6 Empty state

Отдельный компонент:
- Большая иконка (кинокамера или фильм).
- Заголовок: «Тут будут твои видео».
- Текст: «Начни с первого — закинь видео, и студия сделает из него рилсы.»
- Кнопка primary «Новый проект» (открывает модалку REFACTR-41).

### 39.7 Verify frontend-design

- [ ] Phase 2: Color pops (accent на кнопках и активной карточке).
- [ ] Нет generic flat cards — у них есть spatial depth (shadow + subtle border).
- [ ] Контент > хром (превью крупные, тексты компактные).

### 39.8 Commit + Serena

---

## GATE-чекпоинт

- [ ] Grid открывается, показывает проекты.
- [ ] Карточка работает: превью, статус, hover, клик → Workbench.
- [ ] Empty state отрисован.
- [ ] Loading skeleton.
- [ ] Адаптивность: 2/3/4/5 колонок.

---

## Артефакт на выходе

StudioPage + ProjectGrid + ProjectCard + EmptyState + SkeletonGrid.
