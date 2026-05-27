# REFACTR-43 — Header Студии: сортировка, фильтр, inline-поиск

> **Этап:** 06
> **Шаг:** 44 из 67
> **Зависимости:** REFACTR-39 (Grid).
> **Следующий шаг:** REFACTR-44 (Empty state + онбординг)

**ОБЯЗАТЕЛЬНО:** `frontend-design` skill активен.

---

## Роли

### R-DESIGN-ALCHEMIST
**Soul:** Header Студии — дирижёр grid'а. Там ничего лишнего, только то, что помогает найти нужный проект.

### R-UX-WRITER
**Soul:** Фильтры называются по-русски без калек. «Все» / «В работе» / «Готовые» / «С ошибкой» — не «Active / Ready / Error».

---

## ТРИЗ-принцип

*Принцип сегментации.* Header = Title + Поиск + Фильтры + Сортировка + CTA. Каждая часть — маленький компонент, комбинация — плотная.

---

## Оркестрация

**Режим:** Sequential.

---

## Микрозадачи

### 43.1 Layout

```
┌────────────────────────────────────────────────────────────┐
│ Студия                      [ 🔍 поиск ]   [+ Новый проект] │
│                                                            │
│ Все 47  │ В работе 3 │ Готовые 38 │ С ошибкой 1 │ Скрытые 5│
│                                                            │
│                                       Сортировка ▾  Вид ▾   │
└────────────────────────────────────────────────────────────┘
```

### 43.2 Поиск

- Input с иконкой.
- Debounce 200 ms.
- Query-param в URL: `?q=xxx`.
- Результат — фильтрует grid client-side (TanStack Query, где data уже загружена).

### 43.3 Chip-фильтры

- Radix RadioGroup или просто кнопки-chips.
- Значения: `all | running | ready | error | soft_deleted`.
- Active chip — accent-muted bg.
- Клик → query-param `?status=xxx`.

Числа в chip: подсчёт динамически по Project list.

### 43.4 Сортировка

DropdownMenu:
- По дате сохранения (новые сверху / старые сверху).
- По названию (A-Z / Z-A).
- По статусу.

Query-param `?sort=...`.

### 43.5 Вид

DropdownMenu:
- Сетка (default).
- Список (с крупными строками, когда много проектов).

Query-param `?view=grid|list`.

### 43.6 Sync с URL

TanStack Router search-params:
```ts
const { q, status, sort, view } = Route.useSearch();
```
Router валидирует через Zod-схему.

### 43.7 CTA «Новый проект»

Primary-кнопка. По клику открывает NewProjectModal (REFACTR-41).

### 43.8 Keyboard shortcut

- `/` или `Cmd+F` (override browser) — фокус в поиск.
- `N` — новый проект.

### 43.9 Verify frontend-design

- [ ] Spacing плотный, но не тесный.
- [ ] CTA «Новый проект» — accent.
- [ ] Chip-фильтры — читаемы, active state ясен.

### 43.10 Commit + Serena

---

## GATE-чекпоинт

- [ ] Header отрисован поверх grid'а.
- [ ] Поиск фильтрует grid.
- [ ] Chip-фильтры работают, счётчики актуальны.
- [ ] Сортировка меняет порядок карточек.
- [ ] Вид переключает grid/list.
- [ ] URL sync работает (reload сохраняет состояние).
- [ ] Shortcuts `/` и `N`.

---

## Артефакт на выходе

StudioHeader + все подкомпоненты (Search, Filters, Sort, ViewToggle).
