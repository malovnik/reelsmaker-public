# REFACTR-47 — Режимы: Полная автоматика vs Пошагово с approve

> **Этап:** 07
> **Шаг:** 48 из 67
> **Зависимости:** REFACTR-46 (timeline).
> **Следующий шаг:** REFACTR-48 (Grid идей)

**ОБЯЗАТЕЛЬНО:** `frontend-design` skill активен.

---

## Роли

### R-DESIGN-ALCHEMIST
**Soul:** Режимы = две дороги. Одна — «прогнать целиком, принесёшь результат», другая — «покажи мне каждую идею, я решу». Оба — легитимные workflows.

### R-UX-WRITER
**Soul:** Названия режимов короткие: «Автомат» и «С approve». Без калек.

---

## ТРИЗ-принцип

*Принцип матрёшки.* Режим — глобальный переключатель проекта. Влияет на поведение stages (Ideas — с approve или без).

---

## Оркестрация

**Режим:** Sequential.

---

## Микрозадачи

### 47.1 Модель данных

Добавить в `ProjectSettingsSnapshot` поле:
```ts
pipeline_mode: "auto" | "review"  // default "review"
```

Миграция не нужна (snapshot в JSON).

### 47.2 UI переключатель

Где разместить: в TopBar Workbench, рядом с меню. Или в первой строке sidebar. Выбор — в прототипе.

Компонент:
- Segmented control (два state): «Авто» / «С approve».
- Tooltip на каждом:
  - «Авто»: «Полный pipeline без остановок. Получишь готовые рилсы.»
  - «С approve»: «Pipeline остановится на идеях. Одобришь — пойдёт дальше.»

### 47.3 Поведение бэка

В pipeline после стадии «Генерация идей»:
- Если `pipeline_mode == "auto"` → автоматически approved все идеи (или ограниченный top-N) → продолжить.
- Если `pipeline_mode == "review"` → остановиться, отправить SSE `ideas_ready`.

Реализовать в backend при необходимости (учесть в REFACTR-19/20, иначе сейчас добавить).

### 47.4 UI реакция в Main area

В табе «Идеи»:
- Режим Auto → показать прогресс общий (не давая approve/reject).
- Режим Review → показать grid идей с approve/reject/regenerate + кнопка «Запустить рендер одобренных».

### 47.5 Кнопка «Запустить pipeline»

Если стадии ещё не начинались (новый проект) — кнопка «Запустить». В зависимости от режима — идёт до конца (auto) или до стадии ideas (review).

### 47.6 Verify frontend-design

- [ ] Segmented control — accent на active, clear visual.
- [ ] Tooltip объясняет без жаргона.

### 47.7 Commit + Serena

---

## GATE-чекпоинт

- [ ] Переключатель работает (setter → PUT settings → backend знает).
- [ ] Auto mode: pipeline идёт без остановок, рилсы готовы.
- [ ] Review mode: pipeline останавливается на ideas, фронт показывает grid.
- [ ] Reload сохраняет режим (snapshot).

---

## Артефакт на выходе

PipelineModeSwitcher + backend-поведение mode-aware.
