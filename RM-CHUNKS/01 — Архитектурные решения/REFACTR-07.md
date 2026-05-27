# REFACTR-07 — ADR: Frontend-стек (Vite + React + TanStack vs альтернативы)

> **Этап:** 01 — Архитектурные решения
> **Шаг:** 8 из 67
> **Зависимости:** REFACTR-01 (карта фронта), REFACTR-06 (боль OOM).
> **Следующий шаг:** REFACTR-08 (ADR: Хранение данных)

---

## Роли

### R-ARCHITECT — Архитектор
**Профессия:** Ведущий инженер-архитектор, 14 лет опыта.
**Soul:** Стек выбирается под нагрузку, не под моду. Next.js 16 — отличный продукт для облачных SSR/ISR, но для локального single-user SPA это пушка по воробьям.

### R-FRONTEND-ARCHITECT
**Профессия:** Senior React.
**Soul:** Миграция — это не переписывание. Компоненты должны переноситься 1:1, меняется только обёртка.

### R-DEVIL — Адвокат дьявола
**Профессия:** Контроль качества решений.
**Soul:** «А что если останемся на Next.js и просто отключим SSR?» — каждый вариант должен получить честную оценку.

---

## ТРИЗ-принцип

*Принцип местного качества.* Локальное приложение ≠ облачное. Требования к стеку иные: быстрый HMR, низкая RAM, никакого SSR/SSG, никакого edge-runtime. Выбираем стек, идеально подходящий именно этому контексту.

---

## Оркестрация

**Режим:** Sequential + **Sequential Thinking** для FOR/AGAINST/VERDICT.

---

## Микрозадачи

### 07.1 Sequential Thinking: 3 варианта

Через Sequential Thinking провести анализ минимум 5 шагов:

**Вариант A: Next.js 16 + отключение SSR**
- + минимальная миграция
- − всё равно тянет тяжёлый runtime

**Вариант B: Vite 6 + React 19 + TanStack Router + TanStack Query**
- + dev-RAM ~300-500 МБ
- + HMR <100 мс
- + TanStack Query для data-fetching + SSE
- − нужно переписать роутинг

**Вариант C: Tauri 2 + Vite + React**
- + нативное macOS-приложение
- + ещё меньше RAM
- − оверкилл, и владелец явно запросил «веб-интерфейс на localhost»

### 07.2 Context7 документация

- [x] `resolve-library-id("vite")` + `get-library-docs` — актуальный major и рекомендации (Vite 6/7 stable, `/vitejs/vite`, `/websites/v7_vite_dev`).
- [x] `resolve-library-id("@tanstack/router")` + docs по file-based routing (`/tanstack/router` v1.114.3, `createFileRoute` + loaders + type-safe links).
- [x] `resolve-library-id("@tanstack/react-query")` + docs по SSE/streaming (`/tanstack/query` v5.90.3, `experimental_streamedQuery` + imperative `queryClient.setQueryData`).

### 07.3 Бенчмарк (опционально, если неочевидно)

- [x] Опущен сознательно: выбор очевиден из task.md §2.2 + архитектурной несовместимости Next.js 16 с single-user SPA (корневая проблема — heap ceiling Turbopack + App Router graph, а не prod-bundle). Цифровая верификация зашита в gate REFACTR-31 (≤500 МБ RSS).

### 07.4 Написать ADR

`docs/adr/0001-frontend-stack.md` по шаблону MADR:

- Контекст: 12 ГБ OOM, Next.js 16, локальное приложение без SSR.
- Рассмотренные варианты A/B/C.
- Решение: **Вариант B (Vite + React + TanStack)**.
- Последствия (миграция роутинга, новый data-fetching, положительные для RAM/HMR).
- Верификация: после REFACTR-31 dev-сервер идёт в <500 МБ.

### 07.5 Зафиксировать в PIPELINE-НАВИГАТОР

- [x] Обновить таблицу переменных: Frontend-стек (after) = Vite + React + TanStack.
- [x] Добавить лог.

### 07.6 Serena memory

- [x] `write_memory(name="refactr-07-adr-frontend-stack", content="...")`.

---

## GATE-чекпоинт

- [x] Sequential Thinking проведён (7 шагов: контекст → A → B → C → advocate-проверка → consequences → summary).
- [x] Context7 выдал актуальные версии: Vite 6/7 stable, TanStack Router v1.114.3, TanStack Query v5.90.3.
- [x] ADR-0001 создан, статус «ACCEPTED».
- [x] **Gate с человеком:** выбор зафиксирован владельцем в `task.md §2.2` (Vite + React 19 + TanStack Router + TanStack Query + Tailwind 4). ADR формализует обоснование.

**СТОП если:** владелец указал иной стек → переписать ADR на его выбор. (Не сработал — выбор уже подтверждён в task.md.)

---

## Артефакт на выходе

`docs/adr/0001-frontend-stack.md`.
