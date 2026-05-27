# TASK — videomaker: полный рефакторинг (v2.0-refactor)

> **Дата постановки:** 2026-04-24
> **Заказчик:** Малов Никита (владелец-единственный пользователь)
> **Исполнитель:** Ralph Loop / Looper (последовательные итерации, без параллельных субагентов без явного разрешения)
> **Рабочая папка pipeline:** `<source-repo>/RM-CHUNKS/`
> **Корень кода:** `<source-repo>/`
> **Завершение:** `<promise>REFACTR COMPLETE</promise>` — только когда все 11 этапов имеют статус ✅ в `PIPELINE-НАВИГАТОР.md` (все 67 REFACTR-чанков пройдены)

---

## 1. Контекст задачи

videomaker — локальное веб-приложение для нарезки длинных видео (30–90 мин) в рилсы/шортсы 9:16 на MacBook Pro M5 Pro (24 GB RAM). Пайплайн: транскрибация → удаление тишины/филлеров → мульти-проход LLM → генерация идей → склейка фрагментов из разных мест → color + subtitles + B-roll → рендер HEVC ≥15 Mbps.

Сервис работает, но **перегружен, не оптимизирован и болит**:

1. **OOM 12 ГБ в dev.** `NODE_OPTIONS=--max-old-space-size=12288` в `apps/frontend/package.json` — Next.js 16 пожирает память, dev-сервер падает при забитой RAM.
2. **Дизайн — каша.** Смешанные тёмные/светлые шрифты, ни одной цельной темы, настройки разбросаны по историческим страницам.
3. **Пост-продакшн и субтитры.** Страница `/settings/subtitles` с horizontal scroll — «омерзительно-омерзительно-омерзительно» (дословная цитата). Post-production без группировки.
4. **Cmd+K поиск не работает.**
5. **Нет Студии.** Главная не отражает ключевой сценарий «открыл → увидел проекты → выбрал/создал».
6. **Нет автосохранения** настроек проекта + **нет перезапуска pipeline с произвольного шага**.
7. **Нет потока идей рилсов.** Сейчас LLM сразу идёт в склейку; нужен approve/reject/regenerate до рендера, опциональный custom prompt.
8. **PRO-профиль** болтается в коде — оставляем только Viral 2026 (default) + Chapter Legacy.
9. **Рендер не оптимизирован под M5 Pro.** VideoToolbox hardware encode не подтверждён, нет fallback-лестницы, нет бенчмарков.

Цель — переизобрести сервис до продакшн-продукта 2026 года (YouTube/Instagram-динамика, dark default + light, persist, автосейв, Cmd+K, Simple/Expert режим), не потеряв ни одной рабочей фичи pipeline.

---

## 2. Ожидаемый результат (что получает владелец)

1. **Работающее приложение v2.0-refactor** с git-тегом. Запуск — `./run.sh`, открыть `http://localhost:3000`.
2. **Frontend на Vite 6 + React 19 + TanStack Router + TanStack Query + Tailwind 4.** Dev-RAM idle <500 МБ (против 12 ГБ).
3. **Дизайн-система videomaker.** Manifest + principles + tokens + атомы/молекулы + темы с persist + motion. Без AI-slop.
4. **Студия (главная страница)** — grid проектов с превью, контекстное меню (rename / soft-delete / hard-delete / Finder-open), модалка нового проекта с drop-zone и копированием настроек.
5. **Workbench (страница проекта)** — pipeline timeline с кнопкой «Начать заново с шага», режимы Авто/Review, grid идей с approve/reject/regenerate (+ опциональный custom prompt), tab клипов с прогрессом рендера.
6. **Настройки** — 7 смысловых групп без horizontal scroll, Simple/Expert режим.
7. **Cmd+K Command Palette** — context-aware, с fuzzy-поиском.
8. **Бэкенд:** PRO удалён, модель Project с settings_snapshot и stage_progress, API автосейв/restart/copy-from/Finder-open, сервис идей рилсов, health endpoint, rate-limit.
9. **Рендер под M5 Pro** — VideoToolbox HEVC по умолчанию + software fallback, ≤1.5× realtime на 60-мин видео, ≥15 Mbps.
10. **Безопасность:** argv-only для всех вызовов внешних процессов, path traversal blocked, secrets не утекают, semgrep 0 high/critical.
11. **DevX:** run.sh с preflight-checks + idempotent cleanup + orphan-guard на SIGINT/TERM/EXIT, унифицированные логи в `data/logs/`, health-check script.
12. **Документация:** README + ARCHITECTURE (C4 + ADR) + USER-GUIDE + CHANGELOG v2.0-refactor.
13. **E2E smoke** — 3 сценария проходят на чистой БД (new-project → ideas → render; copy-from; restart-from-step).

---

## 3. Входные данные — пути

### 3.1. Исходный код (read-write)

| Путь | Роль |
|------|------|
| `<source-repo>/` | Корень проекта, monorepo. |
| `apps/backend/src/videomaker/` | FastAPI + uv + SQLAlchemy. 80+ модулей в `services/`. |
| `apps/backend/alembic/` | Миграции. |
| `apps/frontend/` | Next.js 16.2.4 (будет заменён на Vite). |
| `data/` | Проекты, uploads, artifacts, logs. **Не удалять без разрешения владельца.** |
| `run.sh` | Единственная точка запуска. Обновляется на Этапе 09. |
| `.env` | Секреты (GEMINI_API_KEY и др.). **Не коммитить. Не утекать в логи/responses.** |
| `CONTEXT.md`, `README.md`, `idea.md` | Исходное видение проекта. |

### 3.2. Pipeline инфраструктура (рабочая)

Корневая папка: `<source-repo>/RM-CHUNKS/`

Файлы верхнего уровня:
- `PIPELINE-НАВИГАТОР.md` — карта 11 этапов, статусы, переменные проекта, мультироли, STOP-правила, лог.
- `PIPELINE-RALPH-PROMPT.md` — алгоритм одной итерации Ralph Loop (10 шагов).
- `README.md` — инструкция + обоснование плана.
- `task.md` — этот документ.

Папки этапов (единый префикс `REFACTR-NN.md` для чанков, L1-файлы — оглавления без префикса):
- `00 — Исследование и аудит/` — L1 + REFACTR-00..06 (7 чанков).
- `01 — Архитектурные решения/` — L1 + REFACTR-07..12 (6).
- `02 — Бэкенд чистка и проекты/` — L1 + REFACTR-13..20 (8).
- `03 — Бэкенд рендер и безопасность/` — L1 + REFACTR-21..26 (6).
- `04 — Фронт миграция стека/` — L1 + REFACTR-27..31 (5).
- `05 — Фронт дизайн-система и темы/` — L1 + REFACTR-32..38 (7).
- `06 — Фронт Студия и проекты/` — L1 + REFACTR-39..44 (6).
- `07 — Фронт Workbench и идеи/` — L1 + REFACTR-45..50 (6).
- `08 — Фронт настройки и Cmd+K/` — L1 + REFACTR-51..57 (7).
- `09 — Интеграция run.sh и DevX/` — L1 + REFACTR-58..61 (4).
- `10 — Финализация/` — L1 + REFACTR-62..66 (5).

Итого: 67 REFACTR-чанков + 11 L1-файлов + 3 корневых (навигатор, промпт, README, task).

### 3.3. Внешние зависимости (read-only)

| Ресурс | Роль |
|--------|------|
| Context7 MCP | Документация Vite 6, TanStack Router/Query, Tailwind 4, ffmpeg, VideoToolbox, Radix, Framer Motion. |
| Serena MCP | Символическая работа с Python/TypeScript. Обязательна для всех бэкенд-чанков. |
| Skill `frontend-design` | **Обязателен** в каждом фронт-чанке этапов 05–08 (перед первой строкой кода). |
| Skill `role-factory` | Создание ролей R-SECURITY, R-BACKEND-SURGEON, R-DESIGN-ALCHEMIST перед их использованием. |
| Skill `static-analysis:semgrep` | Security-сканы бэкенда (REFACTR-25, REFACTR-66). |
| Skill `superpowers:verification-before-completion` | Перед каждой заявкой «сделано». |
| Ralph Loop (local fork) | `<brandbook> ИИ/Софт/looper-tmux` — команда `/ralph-loop-local:ralph-loop`. |

---

## 4. Мультироли (профессиональные + soul)

Применяются внутри микрозадач по указанию в каждом REFACTR-чанке. Каждая роль — инструмент, не маска. Soul-элемент определяет приоритеты в спорных точках.

### R-AUDITOR — Аудитор проекта
**Профессия:** Senior-разработчик-картограф, специализация reverse engineering крупных monorepo.
**Soul:** Не обманывается объёмом кода. Отличает живой модуль от забытого. Пишет карту без сантиментов. Активна на Этапе 00.

### R-ARCHITECT — Архитектор
**Профессия:** Ведущий инженер-архитектор, 14 лет опыта.
**Soul:** Стек выбирается под нагрузку, не под моду. Next.js 16 — отличный продукт для облачного SSR, для локального single-user SPA — оверкилл. Активна на Этапах 01 и 04.

### R-BACKEND-SURGEON — Бэкенд-хирург
**Профессия:** Python-инженер, FastAPI + SQLAlchemy + Alembic, 10+ лет.
**Soul:** Хирургия ≠ экскаватор. Удаляем PRO, не задеваем Viral 2026. Миграции обратимы. Никаких mocks. Активна на Этапах 02–03.

### R-RENDER-ENG — Рендер-инженер
**Профессия:** Специалист по ffmpeg, VideoToolbox, h264/hevc-кодекам.
**Soul:** Каждый кадр — ресурс. Hardware encode на Apple Silicon — обязательство, не опция. Активна на Этапе 03 (REFACTR-21..23).

### R-SECURITY — Аудитор безопасности
**Профессия:** Security engineer для локальных Python-бэкендов и веб-сервисов.
**Soul:** Локальный ≠ безопасный. `.env` может утечь через логи, error-responses, скриншоты. Каждая утечка — инцидент. Активна на Этапе 03 (REFACTR-24..26) и всюду где есть запуск внешних процессов/path.

### R-FRONTEND-ARCHITECT — Фронт-архитектор
**Профессия:** Senior React + Vite + TanStack (Router/Query), 8+ лет.
**Soul:** Миграция — не переписывание. Компоненты переносятся 1:1, меняется оболочка. Активна на Этапе 04.

### R-DESIGN-ALCHEMIST — Дизайн-алхимик
**Профессия:** Senior UI/UX designer-dev, специализация на медиа-продуктах.
**Soul:** Продукт 2026 — динамичный как YouTube/Instagram, но со своим лицом. AI-slop и generic shadcn-компоненты — враги. Контент > хром. Активна на Этапах 05–08 (обязательна в каждом чанке через `frontend-design` skill).

### R-MOTION — Моушн-дизайнер
**Профессия:** Специалист по Framer Motion и CSS-анимациям.
**Soul:** Движение — язык. Говорит «это кликнулось», «что-то появилось». Без языка — мёртвый интерфейс, с переизбытком — шумный. Активна на Этапах 05, 07.

### R-UX-WRITER — UX-редактор
**Профессия:** Писатель интерфейсных текстов на русском.
**Soul:** Каждая надпись взвешена. «Distinctive» → «узнаваемое», «Get started free» → убрать, «И знаете что?» → убрать. Русский без английских вкраплений, без клише. Активна на Этапах 05–08.

### R-DEVOPS — DevOps локального стека
**Профессия:** Shell-скриптер, mac-админ.
**Soul:** Preflight-скрипт — первое впечатление. Процессы-сироты — инцидент. Идемпотентность обязательна. Активна на Этапе 09.

### R-QA — Финальный тестировщик
**Профессия:** QA-инженер, smoke + E2E specialist.
**Soul:** «Если не прошёл в браузере — не сделано». Руками + кодом, не верит логам. Активна на Этапе 10.

### R-DEVIL — Адвокат дьявола
**Профессия:** Риск-менеджер решений.
**Soul:** В каждом «всё нормально» ищет пропущенный риск. Активна во всех этапах где есть архитектурные выборы или удаления.

---

## 5. Chain of Thought — план работы

Крупные шаги → подшаги → микрозадачи. Микрозадачи детализированы в REFACTR-NN.md — здесь только карта фокуса.

### ШАГ 1. Этап 00 — Исследование и аудит
Цель: точная карта кода, настроек, pipeline, болей. Без изменений.

1.1. **REFACTR-00 Карта backend-сервисов** — 80+ модулей в `services/`, классификация живой/мёртвый/дубликат.
1.2. **REFACTR-01 Карта frontend-страниц** — 19 маршрутов Next.js + компоненты + проблемные места.
1.3. **REFACTR-02 Инвентаризация настроек** — 8 страниц `/settings/*`, все поля с file:line, h-scroll hunt.
1.4. **REFACTR-03 Профили и PRO-код** — все упоминания PRO, граф зависимостей, план ампутации.
1.5. **REFACTR-04 Схема данных** — SQLAlchemy модели, Alembic история, реальная БД, файловое хранилище.
1.6. **REFACTR-05 Pipeline stages** — граф стадий, вход/выход, точки возобновления, SSE events.
1.7. **REFACTR-06 UX-боли** — матрица «цитата владельца → file:line → этап решения → чанк».

Выход этапа: 7 документов в `docs/audit/` + Serena memory.

### ШАГ 2. Этап 01 — Архитектурные решения
Цель: 5 ADR + C4-диаграмма с обоснованием каждого.

2.1. **REFACTR-07 ADR: Frontend-стек** — Vite + React + TanStack vs альтернативы. Sequential Thinking + Context7. Gate-чекпоинт с человеком.
2.2. **REFACTR-08 ADR: Storage** — SQLite мета + JSON snapshots в `data/projects/{id}/settings.json`. Миграция существующих.
2.3. **REFACTR-09 ADR: Автосохранение** — PUT snapshot + ETag-conflict, debounce 10 с, 4 UI-состояния.
2.4. **REFACTR-10 ADR: Видеодвижок** — hevc_videotoolbox default + libx265 fallback + libx264 крайний. Параметры.
2.5. **REFACTR-11 ADR: Темы** — CSS variables на `<html>`, persist localStorage + backend, flash-prevention script.
2.6. **REFACTR-12 Итоговая C4** — Level 1 (System Context) + Level 2 (Containers) + 2 sequence-диаграммы.

Выход этапа: `docs/adr/0001..0005*.md` + `docs/architecture/c4-overview.md`.

### ШАГ 3. Этап 02 — Бэкенд: чистка и проекты
Цель: убрать PRO + новая модель Project + сервис идей рилсов + 7 endpoints.

3.1. **REFACTR-13 Удаление PRO** — Alembic migration (PRO→Viral 2026) + Serena safe_delete + grep чистый + smoke.
3.2. **REFACTR-14 Модель Project** — settings_snapshot_path, stage_progress JSON, soft_deleted_at, parent_project_id + backfill миграция.
3.3. **REFACTR-15 API автосейва** — PUT/GET `/api/projects/{id}/settings` + ETag + Pydantic-валидация.
3.4. **REFACTR-16 API restart-from-step** — POST `/api/projects/{id}/restart` + инвалидация downstream artifacts.
3.5. **REFACTR-17 API copy-from** — POST `/api/projects/{id}/settings/copy-from` + picker-endpoint для UI.
3.6. **REFACTR-18 Finder-open + delete** — subprocess argv-only с path-traversal guard + soft/hard delete.
3.7. **REFACTR-19 Сервис идей рилсов** — модель ReelIdea + Gemini генерация + интеграция в pipeline.
3.8. **REFACTR-20 API approve/reject/regenerate** — 4 endpoints + custom_prompt + SSE events.

Выход этапа: 7 API endpoints + 1 новая модель + 1 Alembic migration + тесты.

### ШАГ 4. Этап 03 — Бэкенд: рендер и безопасность
Цель: VideoToolbox HEVC работает и замерен + security-harden.

4.1. **REFACTR-21 VideoToolbox encode** — encoder_detection + encoder_strategy + ffmpeg_builder.
4.2. **REFACTR-22 VBR/CRF оптимизация** — экспериментальные прогоны, профиль Viral 2026, override в performance settings.
4.3. **REFACTR-23 Бенчмарк M5** — S/M/L видео × hardware/software = 6 прогонов. Цель ≤1.5× realtime.
4.4. **REFACTR-24 Secrets guard** — pydantic-settings, mask_secrets processor, frontend не знает ключей.
4.5. **REFACTR-25 Injection + path** — argv-only везде, safe_path helper, semgrep scan.
4.6. **REFACTR-26 Rate-limit + чистка** — slowapi, grep TODO/FIXME/print/console.log = 0, ruff/eslint strict.

Выход этапа: оптимизированный рендер + hardened backend + `docs/performance/m5-render-bench.md`.

### ШАГ 5. Этап 04 — Фронт: миграция стека
Цель: Next.js 16 → Vite 6. Без потери функционала.

5.1. **REFACTR-27 Инициализация Vite** — `apps/frontend-vite/`, TanStack Router + Query + Tailwind 4.
5.2. **REFACTR-28 Миграция роутинга** — 19 маршрутов в file-based TanStack routes.
5.3. **REFACTR-29 API-клиент + Query + SSE** — `api()` wrapper, queryKeys, hooks для всех сущностей, useEventSource.
5.4. **REFACTR-30 Shell** — AppShell + NavRail + TopBar перенос 1:1 (импорты Next → TanStack).
5.5. **REFACTR-31 Удаление Next.js** — `apps/frontend-legacy/` → delete, `apps/frontend-vite/` → `apps/frontend/`, RAM замерить <500 МБ.

Выход этапа: чистый Vite-проект, git-тег `pre-nextjs-removal` для отката.

### ШАГ 6. Этап 05 — Фронт: дизайн-система и темы
Цель: фундамент для UI. **Обязателен `frontend-design` skill в каждом чанке.**

6.1. **REFACTR-32 Manifest + principles** — эстетическое направление одной фразой, 10 референсов, anti-slop чеклист.
6.2. **REFACTR-33 Палитры dark/light** — accent-цвет, 20+ семантических токенов, CSS variables, WCAG AA.
6.3. **REFACTR-34 Типографика + spacing** — Inter Variable + JetBrains Mono (self-hosted), 9-step type scale, 4-based spacing.
6.4. **REFACTR-35 Атомы** — Button, Input, Select, Chip, Badge, Avatar, Icon.
6.5. **REFACTR-36 Молекулы** — Card, Modal, Toast, Tooltip, Popover, Tabs, DropdownMenu.
6.6. **REFACTR-37 ThemeProvider** — localStorage + backend sync, flash-prevention script.
6.7. **REFACTR-38 Motion** — tokens, правила, utils, prefers-reduced-motion, ретрофит атомов/молекул.

Выход этапа: `src/design/` + `docs/design/MANIFEST.md` + `/design-preview` route.

### ШАГ 7. Этап 06 — Фронт: Студия и проекты
Цель: главная страница = Студия с grid проектов. **`frontend-design` обязателен.**

7.1. **REFACTR-39 ProjectGrid** — responsive (2/3/4/5 col), ProjectCard, loading skeleton.
7.2. **REFACTR-40 Контекстное меню** — 6 действий: open, rename, Finder, copy-to-new, soft-delete, hard-delete.
7.3. **REFACTR-41 Модалка нового проекта** — drop-zone + auto-name + выбор стартовой конфигурации.
7.4. **REFACTR-42 Copy-from UI** — radio «Последний» / «Выбрать из списка» + picker с поиском.
7.5. **REFACTR-43 StudioHeader** — поиск (debounce), chip-фильтры, сортировка, view toggle, URL-sync.
7.6. **REFACTR-44 EmptyState** — приглашение + primary CTA + (опц.) онбординг-модалка.

Выход этапа: работающая Студия, полный цикл проекта через UI.

### ШАГ 8. Этап 07 — Фронт: Workbench + идеи
Цель: страница одного проекта. **`frontend-design` обязателен.**

8.1. **REFACTR-45 Layout Workbench** — video + resizable sidebar + main area с tabs.
8.2. **REFACTR-46 Pipeline timeline** — статусы через SSE, restart-from-step с confirm.
8.3. **REFACTR-47 Режимы Авто/Review** — segmented control, snapshot-field, backend-поведение.
8.4. **REFACTR-48 Grid идей** — карточка с описанием/хуком/текстом/таймкодами, фильтры, preview таймкодов.
8.5. **REFACTR-49 Approve/Reject/Regenerate** — optimistic updates + RegenerateModal с opt custom prompt + shortcuts A/R/G.
8.6. **REFACTR-50 Clips tab + рендер** — прогресс SSE, grid клипов 9:16, lightbox preview, download + all-zip.

Выход этапа: полный Workbench flow от открытия до скачивания рилсов.

### ШАГ 9. Этап 08 — Фронт: настройки и Cmd+K
Цель: структурированные настройки + Command Palette. **`frontend-design` обязателен.**

9.1. **REFACTR-51 Новая IA** — 7 групп (Запись/Обработка/Визуал/Субтитры/LLM/Интеграции/Устройство), вертикальный sidebar, редиректы старых URL.
9.2. **REFACTR-52 Settings/Subtitles** — адаптивный редактор без h-scroll на 1024/1280/1920, live-preview.
9.3. **REFACTR-53 Settings/Processing** — 5 подгрупп в accordion (Silence, Audio, Color/LUT, Transitions, Effects).
9.4. **REFACTR-54 Settings/LLM + Prompts** — tabs Модели/Промпты, редактор с версионностью и rollback.
9.5. **REFACTR-55 Settings/Visuals + Integrations** — Brand kit + B-roll + плашки; API-keys защищены, health-check.
9.6. **REFACTR-56 Settings/Device + Simple/Expert** — тема, режим UI, hotkeys, complexity-attribute система.
9.7. **REFACTR-57 Cmd+K** — context-aware палитра на cmdk, fuzzy-поиск, keyboard shortcuts.

Выход этапа: зеро h-scroll, работающий Cmd+K, Simple/Expert toggle, 7 секций настроек.

### ШАГ 10. Этап 09 — Интеграция run.sh и DevX
Цель: preflight + startup + cleanup + логи + health.

10.1. **REFACTR-58 Preflight deps** — uv/pnpm/ffmpeg/node check + version check + install + `.env` copy.
10.2. **REFACTR-59 Startup + trap** — Vite-dev (не Next), SIGINT/TERM/EXIT trap, pkill всего дерева, preflight_kill паттерны.
10.3. **REFACTR-60 Логи унифицированные** — structlog backend (JSON в `data/logs/`) + frontend logger + ErrorBoundary.
10.4. **REFACTR-61 .env guard + health-check** — GET `/api/health`, UI-индикатор, `scripts/health-check.sh`.

Выход этапа: `./run.sh` с нуля на чистой системе работает за <10 с.

### ШАГ 11. Этап 10 — Финализация
Цель: smoke + docs + git tag.

11.1. **REFACTR-62 E2E #1** — new-project → upload → ideas → approve → render → download (20 пунктов).
11.2. **REFACTR-63 E2E #2** — copy-from settings + сравнение snapshot через diff.
11.3. **REFACTR-64 E2E #3** — restart-from-step × 3 стадии (transcribe, ideas, render).
11.4. **REFACTR-65 Документация** — README + ARCHITECTURE + USER-GUIDE + CHANGELOG + CLAUDE.md update.
11.5. **REFACTR-66 Release** — финальный чеклист (30+ пунктов), semgrep, grep-мусор, подтверждение владельца, git tag `v2.0-refactor`.

Выход проекта: `<promise>REFACTR COMPLETE</promise>` + git tag.

---

## 6. Рабочий процесс

### 6.1. Принцип «1 REFACTR-чанк = 1 результат»

- Одна итерация Looper = один файл `REFACTR-NN.md`.
- Результат итерации — **артефакт в коде или документации** (указан в секции «Артефакт на выходе» чанка) + прохождение всех микрозадач + GATE-чекпоинт.
- Одна итерация ≠ несколько чанков. Следующий — только после явной остановки.

### 6.2. Двухфазный режим итерации

**Фаза 1 — план на итерацию.** Looper открывает REFACTR-NN, формулирует свой план: какие микрозадачи, каким порядком, какие инструменты (Serena / Context7 / frontend-design skill / role-factory). Здесь можно задать уточняющие вопросы владельцу — закрытые и конкретные, не «расскажите больше».

**Фаза 2 — выполнение.** Последовательно по микрозадачам. Чекбоксы отмечаются в файле чанка. При непонимании — Sequential Thinking мини-декомпозиция 3–5 шагов. Допущения помечаются явно.

### 6.3. Обязательные инструменты по этапам

(Сводная таблица — в `PIPELINE-НАВИГАТОР.md`, раздел «Инструменты по этапам».)

- Этапы 00, 02, 03: **Serena** 🔴 обязательна (символическая работа с кодом).
- Этап 01: Sequential Thinking 🔴, Context7 🔴 (Vite / TanStack / ffmpeg).
- Этап 03: Context7 🔴 (ffmpeg / VideoToolbox), role-factory security-auditor 🔴.
- Этап 04: Context7 🔴 (Vite 6, TanStack v5).
- Этапы 05–08: **frontend-design skill 🔴 ОБЯЗАТЕЛЕН в каждом чанке** — перед первой строкой кода. STOP-4: фронт без активного skill = чанк начинается заново.
- Этап 05: role-factory design-alchemist (генерация роли при отсутствии).
- Этап 09: Bash + shellcheck.
- Этап 10: E2E прогон (Playwright или ручной чеклист), semgrep финальный.

### 6.4. Принцип «production-ready с первой строки»

В любом чанке **запрещено**:
- TODO / FIXME / XXX / HACK в коде (кроме документации).
- Mocks / stubs / placeholders.
- Shell-mode вызовы внешних процессов (всё через argv-массив).
- Конкатенация строк в argv.
- Raw fetch вне `src/lib/api.ts`.
- Hex-цвета в компонентах (только через токены).
- Английские тексты в UI (только имена продуктов).
- Generic UI-клише («modern and clean», пустые крючки, фальшивый glassmorphism).

### 6.5. Принцип «не удалять данные без разрешения»

- **Не удалять**: `data/`, `.env`, `data/projects/*`, `chroma_db/`, `*.db`, `data/uploads/`.
- **Не коммитить**: `.env` — проверяется в `.gitignore`.
- При желании удалить что-либо из списка — STOP-3: **вопрос владельцу**.

### 6.6. ТАБУ (строго)

Политика / военные / религия / политики / криптовалюта — **не упоминаются** ни в коде, ни в документации, ни в примерах, ни в UI-текстах.

---

## 7. Дополнительные напоминания (инфраструктура Looper)

### 7.1. Логи итераций

После каждой итерации Looper:
- Записывает в **Serena memory** `videomaker-chunk-NN-result`: номер завершённого чанка, 3–5 ключевых решений/находок, следующий чанк.
- Обновляет статус в `PIPELINE-НАВИГАТОР.md` → секция «Лог изменений» строкой формата:
  ```
  | YYYY-MM-DD | Чанк N/67: REFACTR-NN «Название» ✅ — артефакт `path/to/file`. Коротко: что сделано. |
  ```
- При завершении всех чанков этапа — переводит статус этапа в ✅ в таблице «Статусы этапов».

### 7.2. Документация решений

Каждое архитектурное решение (Этап 01) — ADR в `docs/adr/NNNN-*.md` по шаблону MADR: контекст → варианты → решение → последствия → верификация.

Каждая цифра бенчмарка (Этап 03) — с источником (ffprobe output, ps RSS, timing command).

Каждая дизайн-находка (Этап 05) — зафиксирована в manifest/principles со ссылкой на референс.

### 7.3. Serena memory — что писать

- `videomaker-chunk-NN-result` — после каждого чанка: резюме 200-500 слов.
- `videomaker-architecture-v2` — после Этапа 01: принятые ADR, стек, ключевые решения.
- `videomaker-project-completed` — после REFACTR-66: финальная метрика + подтверждение владельца.

### 7.4. GATE-чекпоинты

Каждый REFACTR-чанк содержит GATE-чекпоинт в конце. **Выполнять строго.** Если не сходится — **СТОП**, возврат к микрозадачам или вопрос владельцу. Типовые критерии:
- Бэкенд: `curl` на endpoint возвращает ожидаемое + unit-тест.
- Фронт: страница открывается без console.error + dark/light работают.
- Архитектура/аудит: артефакт в `docs/` + Serena memory.
- Рендер: цифра бенчмарка зафиксирована в документе.
- Security: semgrep 0 important findings на затронутом коде.

### 7.5. STOP-правила

- **STOP-1:** 3 неудачные попытки подряд по одному подходу → Context7 (документация) → смена подхода.
- **STOP-2:** архитектурное решение не зафиксировано в чанке → **вопрос владельцу**.
- **STOP-3:** желание удалить `data/`, `.env`, `data/projects/*` → **вопрос владельцу**.
- **STOP-4:** фронт-чанк этапов 05–08 без активного `frontend-design` skill → перезапуск чанка с правильной последовательностью.
- **STOP-5:** UI-клише (generic градиенты, AI-slop buttons, «modern and clean», пустые крючки) → переписать по Phase 2 frontend-design.
- **STOP-6:** нарушение BIBLE.md / CLAUDE.md — остановиться, откатить, сообщить.

### 7.6. Backup и чистота файлов

- Перед каждым рискованным коммитом (Этап 02 удаление PRO, Этап 04 удаление Next.js) — git commit с тегом для отката.
- Изменения в рамках `apps/` и `docs/`. Исходные материалы (`CONTEXT.md`, `idea.md`, `.env.example`) — обновлять, не удалять.
- `.DS_Store` — в `.gitignore`.

---

## 8. Critical Path и порядок запуска

1. Открыть рабочую директорию:
   ```bash
   cd <source-repo>
   ```
2. Запустить Looper из папки RM-CHUNKS:
   ```bash
   /ralph-loop-local:ralph-loop \
       --max-iterations 80 \
       --completion-promise "REFACTR COMPLETE" \
       --prompt-file "RM-CHUNKS/PIPELINE-RALPH-PROMPT.md"
   ```
3. Looper читает `PIPELINE-НАВИГАТОР.md`, находит первый ⬜-чанк (REFACTR-00), выполняет.
4. После каждого чанка — `write_memory` + лог в навигаторе + остановка.
5. После завершения всех 67 REFACTR-чанков → `<promise>REFACTR COMPLETE</promise>`.
6. Владелец открывает `http://localhost:3000`, проходит smoke-сценарии, подтверждает.
7. Git tag `v2.0-refactor` (REFACTR-66).

---

## 9. Definition of Done всего проекта

- Все 11 этапов имеют статус ✅ в `PIPELINE-НАВИГАТОР.md`.
- Все 67 REFACTR-чанков отмечены ✅.
- Frontend переехал с Next.js 16 на Vite 6 + React 19 + TanStack (dev RAM <500 МБ замерено).
- PRO-профиль удалён (grep чистый), Viral 2026 + Chapter Legacy работают.
- Темы dark + light с persist.
- Студия, Workbench, Настройки переизобретены.
- Cmd+K работает везде.
- Автосохранение + restart-from-step + copy-from + idea approve/reject/regenerate — реальные endpoints + UI.
- VideoToolbox HEVC default, бенчмарк ≤1.5× realtime на M5.
- Semgrep backend: 0 high/critical.
- 3 E2E smoke-сценария прошли.
- README + ARCHITECTURE + USER-GUIDE + CHANGELOG — опубликованы.
- Git tag `v2.0-refactor` создан и запушен.
- `./run.sh` на чистой системе запускается за <10 с.
- Serena memory `videomaker-project-completed` содержит финальный лог.
- Владелец подтвердил в браузере: «работает как просил».

---

## 10. Что делать при проблемах

- **Не сходится GATE-чекпоинт:** не обходить — либо вернуться к микрозадачам, либо вопрос владельцу. Обход GATE = фиктивное завершение.
- **Нарушение ТАБУ в примерах/текстах:** переписать, зафиксировать в Serena memory.
- **Pre-tool-use hook блокирует запись:** security-hook срабатывает на опасные паттерны вызова внешних процессов (shell-mode, конкатенация). Переписать код через argv-массив. Документацию — через описание, не через исполняемый сниппет.
- **Противоречие с ADR Этапа 01:** ADR — источник правды. Если необходимо — STOP-2, владелец решает, меняется ADR с отметкой «Заменён».
- **VideoToolbox не укладывается в 1.5× realtime:** STOP-1, Context7 по hevc_videotoolbox tuning, экспериментальные прогоны.
- **Семantic-conflict миграции (PRO-проекты теряют фичи):** STOP-2 — владелец решает, сохранять или конвертировать.
- **Context сжимается:** Serena memory — подушка. Перед длинным чанком — `list_memories`, подтянуть нужное.
- **Bounded context:** Looper работает с одним чанком за итерацию. При необходимости перечитать ранее заполненные — целенаправленно через `read_memory`, не загружать всё.

---

**Конец task.md. Всё готово к запуску Looper.**
