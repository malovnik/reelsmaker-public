# Этап 04: Фронт — миграция стека

> Статус: ⬜ Не начат
> Родитель: [[PIPELINE-НАВИГАТОР]]
> Проект: **videomaker-рефакторинг**

## Суть этапа

Уход с Next.js 16 на **Vite 6 + React 19 + TanStack Router + TanStack Query + Tailwind 4**. Причина — в `package.json` явно: `NODE_OPTIONS=--max-old-space-size=12288`. Для локального single-user приложения без SSR/SSG это оверкилл.

Миграция — не переписывание с нуля. Сохраняем:
- Компоненты React (`components/*`) переносим один-в-один, меняется только роутинг и data-fetching слой.
- Tailwind 4 конфиг остаётся.
- API-клиент — адаптируется под TanStack Query (вместо `fetch` + руками).
- SSE для прогресса pipeline — нативный EventSource внутри Query observer.

После миграции проект запускается параллельно (старый Next.js не трогаем до финальной верификации). Порт фронта меняем временно на 3001, потом переключаемся обратно на 3000 после успеха.

**Режим работы:** Sequential. Пять чанков, каждый — проверяемая единица.

## Подэтапы (REFACTR-27..REFACTR-31)

- **REFACTR-27** — Инициализация Vite-проекта: `apps/frontend-vite/`, TanStack Router, Query, Tailwind 4 ⬜
- **REFACTR-28** — Миграция роутинга (projects, jobs, settings, scheduler) — file-based routes TanStack ⬜
- **REFACTR-29** — API-клиент + TanStack Query hooks + SSE-интеграция ⬜
- **REFACTR-30** — Миграция shell-компонентов (AppShell, NavRail, TopBar) ⬜
- **REFACTR-31** — Удаление Next.js, верификация памяти (<500 МБ в dev), обновление `run.sh` ⬜

## Вход

- ADR-07 (Frontend-стек).
- Карта frontend-страниц из REFACTR-01.
- Все существующие компоненты `apps/frontend/src/components/*`.

## Выход

- Новая директория `apps/frontend/` (после удаления старого — имя сохраняется).
- Работают все маршруты: `/`, `/projects`, `/jobs/:id`, `/settings/*`, `/scheduler/*`.
- `package.json` без `--max-old-space-size`, dev-сервер в покое съедает <500 МБ RAM.
- `run.sh` использует `vite dev` вместо `next dev`.

## Критические факты по стеку

- **Vite 6** — официальная LTS по состоянию на март 2026 (Context7 verify).
- **TanStack Router** — file-based или code-based, выбор в ADR-07. Предпочтительно file-based для совместимости мигрирующих Next.js-роутов.
- **TanStack Query v5** — кеширование, optimistic updates, SSE-observer через `streamedQuery` паттерн.
- **Tailwind 4** работает нативно с Vite без конфигурации (уже настроен в проекте).

## GATE-чекпоинт этапа

- [ ] Все 19 существующих роутов Next.js перенесены и открываются без console.error.
- [ ] `pnpm dev` стартует за <3 с, RAM idle <500 МБ, peak <1 ГБ.
- [ ] HMR работает: правка компонента → обновление без full-reload <200 мс.
- [ ] Все API-вызовы идут через TanStack Query (grep на прямой `fetch(` в `.tsx` — 0 результатов, кроме SSE).
- [ ] SSE-прогресс pipeline работает (визуальная проверка на живом рендере).
- [ ] `next`, `eslint-config-next` удалены из `package.json`.
