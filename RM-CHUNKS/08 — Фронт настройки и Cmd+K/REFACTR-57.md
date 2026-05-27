# REFACTR-57 — Cmd+K Command Palette

> **Этап:** 08
> **Шаг:** 58 из 67
> **Зависимости:** REFACTR-51..56.
> **Следующий шаг:** REFACTR-58 (run.sh preflight)

**ОБЯЗАТЕЛЬНО:** `frontend-design` skill активен.

---

## Роли

### R-DESIGN-ALCHEMIST
**Soul:** Cmd+K — сердце клавиатурного пользователя. Raycast-level. Не шаблонный cmdk-как-у-всех.

### R-UX-WRITER
**Soul:** Команды называются по результату, не по действию: «Новый проект» (не «Создать проект»), «Открыть настройки субтитров» (не «Перейти в subtitles page»).

---

## ТРИЗ-принцип

*Принцип местного качества.* Cmd+K доступен везде. Но результаты контекстные: в Workbench — показывает идеи+клипы+настройки. В Studio — проекты+new+настройки.

---

## Оркестрация

**Режим:** Sequential.

---

## Микрозадачи

### 57.1 Библиотека

`cmdk` (pacocoursey/cmdk) — Context7 подтвердить актуальную версию. Устанавливает primitives, мы строим визуал.

### 57.2 CommandPalette компонент

`src/features/command-palette/CommandPalette.tsx`:

- Dialog из Radix + cmdk внутри.
- Open/close state в global store (Zustand или обычный React context).
- Shortcut: Cmd+K (Mac) / Ctrl+K (Win). Global listener.

### 57.3 Группы команд

```
[🔍 Поиск: ... ]

НАВИГАЦИЯ
  ▸ Студия
  ▸ Настройки: Запись
  ▸ Настройки: Обработка
  ▸ Настройки: Субтитры
  ▸ Настройки: LLM
  ▸ ...

ДЕЙСТВИЯ
  + Новый проект
  ↕ Переключить тему
  ⚙ Simple / Expert режим
  ⟲ Перезапустить текущий проект

ПРОЕКТЫ  (filtered по search-тексту)
  🎬 Reels Алматы          открыть
  🎬 Тренинг #3             открыть
  🎬 Интервью Димы          открыть

ИДЕИ (если открыт Workbench)
  💡 Идея 1: "как..." — approve
  💡 Идея 2: "...однажды..." — regenerate
```

### 57.4 Поиск — fuzzy

cmdk поддерживает fuzzy-match из коробки. Настраиваем ranking:
- Точное совпадение в title > в description.
- Recent items (проекты, открывавшиеся недавно) — приоритет.

### 57.5 Keyboard

- Up/Down — навигация.
- Enter — выполнить.
- Cmd+Enter — в новой вкладке (если применимо).
- ESC — закрыть.
- / (в пустом palette) — focus поиск.

### 57.6 Context-aware команды

Если пользователь на `/jobs/{id}` — в palette появляются команды для этого проекта:
- Перезапустить с шага X.
- Экспортировать клипы.
- Удалить проект.
- Approve all pending ideas.

Если на Studio — команды по текущему фильтру.

### 57.7 Действия

Каждая команда — callback:

```tsx
const actions = [
  { id: 'new-project', label: 'Новый проект', shortcut: 'N', onSelect: () => openNewProjectModal() },
  { id: 'theme-toggle', label: 'Переключить тему', onSelect: () => toggleTheme() },
  ...
];
```

### 57.8 Verify frontend-design

- [ ] Открывается быстро (<50 мс).
- [ ] Backdrop — lite (не отвлекает).
- [ ] Спокойная анимация.
- [ ] Не занимает больше 60% viewport.

### 57.9 Commit + Serena + лог

### 57.10 Итог Этапа 08

- [ ] В `PIPELINE-НАВИГАТОР.md` Лог: «Этап 08 ЗАВЕРШЁН. Настройки и Cmd+K готовы.»

---

## GATE-чекпоинт

- [ ] Cmd+K открывает palette.
- [ ] Fuzzy поиск работает.
- [ ] Все группы команд видны.
- [ ] Context-aware: меняется в зависимости от роута.
- [ ] Keyboard navigation: up/down/enter/esc.
- [ ] **Этап 08 ЗАВЕРШЁН.**

---

## Артефакт на выходе

CommandPalette + действия + global store + shortcut listener.
