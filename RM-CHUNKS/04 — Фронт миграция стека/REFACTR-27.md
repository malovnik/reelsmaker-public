# REFACTR-27 — Инициализация Vite-проекта (TanStack Router + Query + Tailwind 4)

> **Этап:** 04 — Фронт: миграция стека
> **Шаг:** 28 из 67
> **Зависимости:** REFACTR-07 (ADR Frontend-стек).
> **Следующий шаг:** REFACTR-28 (Миграция роутинга)

---

## Роли

### R-FRONTEND-ARCHITECT — Фронт-архитектор
**Профессия:** Senior React + Vite + TanStack.
**Soul:** Vite — не просто сборщик. Это философия: zero-config для большинства, полная кастомизация для крайних случаев. Начинаем минимально.

### R-DEVOPS
**Soul:** Параллельный запуск старого Next.js и нового Vite в dev — временно. Финальное состояние — только Vite в `apps/frontend/`.

---

## ТРИЗ-принцип

*Принцип местного качества.* Начинаем с минимальной рабочей инкарнации Vite (скелет + TanStack Router + Query + Tailwind 4), потом наращиваем функциональность по чанкам 28-31.

---

## Оркестрация

**Режим:** Sequential + Context7 (Vite 6, TanStack).

---

## Микрозадачи

### 27.1 Context7 — актуальные рекомендации

- [ ] `resolve-library-id("vite")` → `get-library-docs` (Vite 6, scaffold команды).
- [ ] `resolve-library-id("@tanstack/router")` → docs (file-based routing setup, plugin Vite).
- [ ] `resolve-library-id("@tanstack/react-query")` → v5, API `useQuery`, `queryClient`.

### 27.2 Создать параллельную директорию

Временно: `apps/frontend-vite/` (будет переименовано в `apps/frontend/` в REFACTR-31 после удаления Next.js).

Команда: `pnpm create vite@latest apps/frontend-vite -- --template react-ts`.

### 27.3 Установка зависимостей

```
pnpm add react@^19 react-dom@^19
pnpm add @tanstack/react-router @tanstack/react-query @tanstack/react-router-devtools @tanstack/react-query-devtools
pnpm add -D @tanstack/router-plugin vite
pnpm add -D tailwindcss@^4 @tailwindcss/vite
```

Все версии сверить через Context7 (актуальный major).

### 27.4 Конфиг Vite

`vite.config.ts`:

- plugin `@tanstack/router-plugin` (file-based routing).
- plugin `@tailwindcss/vite`.
- server: `port: 3000`, `host: "127.0.0.1"`.
- build: `outDir: "dist"`, `sourcemap: true`.

### 27.5 Инициализация роутера

- [ ] Папка `src/routes/` — file-based routes (TanStack соглашение).
- [ ] `src/routes/__root.tsx` — корневой layout (будущий AppShell).
- [ ] `src/routes/index.tsx` — заглушка главной (перенос на REFACTR-28).

### 27.6 Инициализация QueryClient

`src/providers/QueryProvider.tsx`:
- `QueryClient` с sensible defaults (staleTime 60 с для обычных, 0 для live-данных).
- `QueryClientProvider` оборачивает `RouterProvider`.

### 27.7 Tailwind 4 entry CSS

`src/styles.css`: `@import "tailwindcss";` + базовые токены (заглушка, полноценно — в REFACTR-32..34).

### 27.8 Smoke

- [ ] `pnpm dev` стартует на 3001 (временно, пока 3000 у Next.js).
- [ ] Открывается главная с текстом «videomaker / vite».
- [ ] RAM idle замерена (должна быть <500 МБ, записать в memory).

### 27.9 Commit + Serena memory

---

## GATE-чекпоинт

- [ ] `apps/frontend-vite/` создан.
- [ ] Зависимости установлены и соответствуют Context7-рекомендациям.
- [ ] `pnpm dev` работает.
- [ ] Главная открывается.
- [ ] RAM < 500 МБ.
- [ ] Commit помечен.

---

## Артефакт на выходе

Рабочая заготовка Vite+React+TanStack+Tailwind 4 в `apps/frontend-vite/`.
