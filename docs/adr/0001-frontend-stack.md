# ADR-0001 — Frontend-стек: Vite 6 + React 19 + TanStack Router + TanStack Query

- **Статус:** ACCEPTED
- **Дата:** 2026-04-24
- **Авторы:** R-ARCHITECT (ведущий), R-FRONTEND-ARCHITECT, R-DEVIL
- **Контекст чанка:** `RM-CHUNKS/01 — Архитектурные решения/REFACTR-07.md` (шаг 8/67)
- **Связано с:** ADR-0002 (хранение данных), REFACTR-27..31 (миграция фронта)

---

## Контекст

`videomaker` — локальное single-user приложение для нарезки длинных видео в рилсы. Запускается через `./run.sh` на MacBook Pro M5 (24 GB RAM), пользователь один (владелец), открытие на `http://localhost:3000`. Бэкенд — FastAPI на `http://localhost:8000`.

Текущий фронт — **Next.js 16.2.4 + React 19.2.4 + Tailwind 4** (`apps/frontend/package.json`):

```json
"dev": "NODE_OPTIONS='--max-old-space-size=12288' next dev"
```

Флаг `--max-old-space-size=12288` (12 ГБ heap ceiling) обязателен — без него Node OOM-падает на этапе загрузки App Router + Turbopack graph. Это **боль #1** из `docs/audit/06-ux-pains.md`: dev-сервер не работоспособен на машинах с ≤16 ГБ свободной памяти и тормозит разработку на 24 ГБ.

Дополнительные факты из аудита:

- 19 маршрутов (`docs/audit/01-frontend-map.md`) — все single-page без SSR-ценности.
- 101 компонент `.tsx` (~38 000 LoC) — крупные экранные клиенты (SubtitleStyleEditor 653, SubtitleSettingsClient 458, PostProductionSettingsClient 429).
- Data-fetching — полностью client-side через `lib/api.ts` → FastAPI REST + SSE (`/jobs/{id}/stream`).
- Нет `getServerSideProps`, Server Actions, revalidate, middleware, edge runtime, ISR — весь SSR-арсенал Next.js не используется.
- Нет SEO-требований (локальное приложение без публичного URL).

---

## Decision Drivers

1. **RAM в dev ≤ 500 МБ** — разработчик не должен терять 12 ГБ оперативки на dev-сервер.
2. **HMR <100 мс** — итеративный фронт-редизайн (этапы 05–08) предполагает сотни правок в день.
3. **Type-safe роутинг** — URL-persisted state Workbench (`?stage=analyze&idea=12`) должен проверяться при сборке.
4. **Server-state слой с поддержкой SSE** — job-progress идёт через Server-Sent Events; нужна библиотека, в которую это встраивается без велосипедов.
5. **Отсутствие SSR/SSG/edge** — стек не должен тащить неиспользуемый runtime.
6. **Стабильность мажорной версии** — выбор должен прожить ≥12 месяцев без breaking changes.
7. **Совместимость с React 19** — React Compiler, use(), новые хуки.

---

## Рассмотренные варианты

### Вариант A — Next.js 16 + `output: 'export'` (минимальная миграция)

Остаёмся на App Router, переключаем сборку в static export (SPA), убираем SSR-фичи.

**FOR:**
- Самый дешёвый путь: ноль переписывания кода и роутинга.
- Сохраняем `next/font/local`, иерархию layouts, client-components-паттерн.

**AGAINST:**
- **Не решает корневую проблему.** `NODE_OPTIONS=--max-old-space-size=12288` останется: Turbopack + App Router держат в памяти полный граф routes независимо от output-режима. Boль #1 — про heap dev-сервера, а не про prod-бандл.
- `output: 'export'` несовместим с будущими `next` minor/major обновлениями: каждая версия расширяет serverless-only фичи (PPR, server actions, dynamic-io), которые регулярно ломают export-сборку (см. историю Next.js 13→14→15 changelog).
- App Router всё ещё требует держать в голове двойную модель «client vs server component» через директивы `"use client"`, даже когда серверной стороны нет. Когнитивный оверхед без value.
- Next.js 16 — movable target. Nexts-команда оптимизирует под Vercel/edge нагрузку, а не под локальный SPA: приоритеты фреймворка не совпадают с нашими.
- Потеря дизайн-цели: фреймворк, заточенный под SSR/ISR/streaming, в SPA-режиме ощущается как «автомобиль на третьей передаче в пробке».

**VERDICT:** отклонён. Мнимая миграция — проблема не лечится.

---

### Вариант B — Vite 6 + React 19 + TanStack Router v1 + TanStack Query v5 + Tailwind 4

Переход на esbuild/Rolldown dev-сервер, file-based type-safe роутинг, канонический server-state слой.

**FOR:**
- **Vite 6+ dev-сервер** — native ESM, compile-on-demand. Idle memory 200–400 МБ на проектах с тысячами модулей (см. Context7 `/websites/v6_vite_dev`, `/websites/v7_vite_dev`). Флаг `NODE_OPTIONS` не требуется.
- **HMR <100 мс** для одного компонента (vs ~800–2000 мс у Next.js 16 App Router на крупной странице).
- **TanStack Router v1** (latest `v1.114.3`, API через `createFileRoute`, `routeTree.gen.ts` автогенерация):
  ```tsx
  // src/routes/projects/$projectId.tsx
  export const Route = createFileRoute('/projects/$projectId')({
    loader: ({ params }) => api.getProject(params.projectId),
    component: ProjectDetail,
  });
  ```
  - Compile-time валидация URL: `<Link to="/projects/$projectId" params={{ projectId }} />` ломает TS при опечатке.
  - Type-safe search-params через Zod (Workbench-стейт в URL).
  - Встроенные loaders с кэшированием — идеально для prefetching проектов при наведении.
- **TanStack Query v5** (latest `v5.90.3`, official React Query 5 SDK):
  - `useQuery`/`useMutation` как канонический слой для REST-эндпоинтов.
  - SSE встраивается через `queryClient.setQueryData(['job', id], updater)` в обработчике `EventSource` — Context7 подтверждает паттерн (`experimental_streamedQuery` + classic imperative cache updates).
  - Optimistic updates, query cancellation, retry policies — зрелые примитивы.
- **Прямой контроль** над tsconfig/Vite-config/Tailwind — ничто не навязывается фреймворком.
- **Экосистема** (Radix, Framer Motion, cmdk, Zod, zustand) работает без обёрток.
- **Стабильность**: Vite 6+ API стабилен с 2024 года; Vite 7 — drop-in minor; TanStack Router v1 API заморожен для production.

**AGAINST:**
- Полная миграция 19 routes с App Router → TanStack Router file-based convention. Оценка — 3–5 рабочих дней (распределено в REFACTR-27..31).
- `fetch` по всему коду → `useQuery`/`useMutation` — 101 компонент проверить. Смягчается: `lib/api.ts` уже абстрагирует endpoints, замена на query-хуки идёт поверх существующих функций.
- Потеря `next/image` — для локального приложения не критично (все медиа отдаёт FastAPI через streaming); `<img loading="lazy">` достаточно.
- Потеря `next/font/local` — заменяется на CSS `@font-face` с `?url` импортами Vite. Self-hosted шрифты уже лежат в `public/fonts/`.
- Потеря Server Actions — заменяется стандартным `useMutation` + `fetch` POST (паттерн и так доминирует в текущем коде).

**VERDICT:** принят. Решает корневую проблему, даёт каноническую архитектуру для single-user SPA с интенсивным server-state.

---

### Вариант C — Tauri 2 + Vite + React (нативное macOS-приложение)

Упаковка фронта в WebKit shell, бэкенд — Rust с IPC вместо FastAPI.

**FOR:**
- Самый низкий RAM в runtime (WebKit вместо Chromium/Node).
- Native file-system API (drag-n-drop из Finder, open-in-Finder) без middleware.
- Distribution как `.app` с code-signing.

**AGAINST:**
- **Нарушает явное требование** `task.md §3.1`: «`./run.sh`, открыть `http://localhost:3000`». Формат — веб-интерфейс, не desktop-app.
- Бэкенд уже Python FastAPI с 80+ сервисами (ffmpeg wrappers, LLM клиенты, SQLAlchemy модели). Переход на Tauri требует либо двойного рантайма (Rust shell + Python backend через sidecar), либо переписывания бэкенда — оба варианта оверкилл.
- Distribution-преимущества Tauri бесполезны для single-user локальной установки.
- Apple Developer certificate для signing — лишний накладной процесс.
- Дополнительная миграционная нагрузка (Tauri CLI, macOS notarization, build pipeline) без пропорциональной выгоды.

**VERDICT:** отклонён. Оверкилл, не соответствует явно зафиксированному формату.

---

## Decision Outcome

**Выбран Вариант B: Vite 6 + React 19 + TanStack Router v1 + TanStack Query v5 + Tailwind 4.**

### Целевая конфигурация

| Слой | Библиотека | Минимальная версия | Роль |
|------|-----------|---------------------|------|
| Build/Dev | `vite` | `^6.0.0` (совместимо с `^7`) | ESM dev-сервер, prod-bundle через Rollup/Rolldown |
| React plugin | `@vitejs/plugin-react` | `^5` | Fast Refresh, JSX transform, React 19 support |
| UI runtime | `react`, `react-dom` | `^19.2.0` | React Compiler, `use()`, Actions |
| Router | `@tanstack/react-router` | `^1.114.0` | File-based routing, type-safe links, loaders |
| Router plugin | `@tanstack/router-plugin` | `^1.114.0` | Генерация `routeTree.gen.ts` |
| Server-state | `@tanstack/react-query` | `^5.90.0` | REST + SSE + mutations + optimistic updates |
| Devtools | `@tanstack/react-query-devtools` | `^5.90.0` | Query inspector в dev |
| Styling | `tailwindcss` + `@tailwindcss/vite` | `^4` | Атомарный CSS, OKLCH-токены из `globals.css` |
| TypeScript | `typescript` | `^5.7` | Strict mode, exactOptionalPropertyTypes |

### Опции, не включённые в стек (обоснование)

- **Zustand/Jotai/Redux.** Client-state минимален (UI toggles, form drafts). `useState` + TanStack Query cache покрывают всё. Добавим только при появлении кросс-компонентного client-state, которого нельзя поднять в URL.
- **React Router v7.** Работающая альтернатива, но без встроенных type-safe search-params и Zod-интеграции. Приоритет TanStack — type-safety из коробки.
- **SWR.** Нет mutation-хуков и suspense-режима на уровне API v5 — проигрывает TanStack Query.
- **Next.js 16 + App Router (текущее).** Отклонён (см. Вариант A).
- **Remix / TanStack Start / Waku.** SSR-ориентированные фреймворки — лишний runtime для локалки.

---

## Consequences

### Положительные (измеримые)

1. **Dev RAM idle** с ≥4 ГБ (обязательный `NODE_OPTIONS=12288`) падает до **<500 МБ** (цель REFACTR-31). `NODE_OPTIONS` удаляется из `package.json`.
2. **HMR** одиночного компонента: Next.js 16 ~800–2000 мс → Vite **<100 мс** (esbuild transform + ESM HMR boundary).
3. **Build-time** prod-сборки: Next.js 16 ~30–60 с → Vite **~8–15 с** (Rollup tree-shaking без SSR-bundle).
4. **Type-safety роутинга**: 0 compile-time checks → 100% routes/params/search валидируются TS через `routeTree.gen.ts`.
5. **Bundle size main chunk**: text/split по страницам в автоматическом режиме (route-based code splitting встроен в TanStack Router).

### Отрицательные / риски

| Риск | Вероятность | Mitigation |
|------|-------------|------------|
| Миграция 19 routes затянется | средняя | Декомпозиция на REFACTR-27..31, компоненты переносятся 1:1. |
| Отсутствие `next/image` → регресс LCP | низкая | Локальное приложение без публичного трафика. Превью рендерятся FFmpeg-stills в preview-endpoint. |
| TanStack Router breaking changes | низкая | Pinning major version `^1`, quarterly upgrade review. API заморожен с v1.0 release. |
| Tailwind 4 нестабильность | низкая | Tailwind 4 stable с начала 2025; текущий проект уже на v4. |
| Потеря DX-привычек (layouts/templates) | низкая | TanStack Router поддерживает nested routes через `__root.tsx` → `routes/_app.tsx` с аналогичной семантикой. |

### Нейтральные последствия

- Убирается различие client/server components. Все компоненты — client-only.
- `lib/api.ts` остаётся, но оборачивается в TanStack Query hooks: `useProjectsQuery`, `useCreateJobMutation`, etc.
- SSE-обработчик для `/jobs/{id}/stream`: `useEffect` → `new EventSource()` → `onmessage` → `queryClient.setQueryData(['job', id], (prev) => ({ ...prev, progress: next.progress }))`. Канонический паттерн из доков v5.

---

## Верификация (gate критерии)

После завершения **REFACTR-31** следующее должно быть истинным:

1. `pnpm dev` в `apps/frontend/` запускает сервер без `NODE_OPTIONS`.
2. Через 60 с после старта `ps -o rss= -p $(pgrep -f "vite dev")` возвращает ≤512 000 (≤ 500 МБ RSS).
3. `/` отдаёт HTML, далее JS-бандл ≤500 КБ gzipped main chunk.
4. Переходы между страницами через `<Link>` компилируются без TS-ошибок.
5. SSE job-progress обновляет UI без перезагрузки страницы.
6. `pnpm build && pnpm preview` отдаёт production-сборку, открывающуюся на `http://localhost:3000`.

---

## References

- Context7 `/websites/v6_vite_dev` — Vite 6 guide (snippets 435).
- Context7 `/websites/v7_vite_dev` — Vite 7 release notes (backward-compat с Vite 6).
- Context7 `/tanstack/router` `v1.114.3` — File-based routing, loaders, type-safe links.
- Context7 `/tanstack/query` `v5.90.3` — `useQuery`, `useMutation`, `experimental_streamedQuery`.
- `RM-CHUNKS/task.md §2.2` — требование владельца «Vite 6 + React 19 + TanStack Router + TanStack Query + Tailwind 4».
- `docs/audit/01-frontend-map.md` — карта 19 routes + 101 компонент.
- `docs/audit/06-ux-pains.md §1` — боль OOM 12 ГБ, основание решения.
