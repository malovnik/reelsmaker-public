# Навигатор Pipeline: videomaker-рефакторинг

> Проект: **videomaker** — локальный веб-сервис нарезки длинных видео в рилсы/шортсы 9:16 на MacBook Pro M5.
> Корень кода: `/Users/malovnik/Documents/Dev/videomaker/`
> Режим: **Ralph Loop** (последовательно, без параллельных субагентов без явного разрешения).
> Промпт: `PIPELINE-RALPH-PROMPT.md`

---

## Переменные проекта

| Переменная | Значение |
|------------|----------|
| Приложение | videomaker (локальное, без логинов) |
| Железо | MacBook Pro, Apple Silicon M5, 24 GB RAM |
| Формат вывода | 9:16 (приоритет), 30 fps, HEVC H.265, ≥15 Mbps |
| Backend-стек | Python 3.12 + FastAPI + uv + SQLAlchemy + aiosqlite (оставляем) |
| Frontend-стек (after) | **Vite 6 + React 19 + TanStack Router + TanStack Query + Tailwind 4** (замена Next.js 16) |
| Frontend-стек (before) | Next.js 16.2.4 + React 19.2 (OOM 12 ГБ, удаляем) |
| LLM по умолчанию | Gemini 2.5 Flash (переключаемо: Gemini Pro / Claude Sonnet-Opus / GPT-5) |
| Транскрибация | MLX-Whisper (основная, M5-нативная) + Deepgram nova-3 (облачная опция) |
| Рендер | ffmpeg + PyAV, **VideoToolbox hardware encode (h264/hevc_videotoolbox)** + software fallback |
| Профили (after) | Viral 2026 (default) + legacy chapter bot |
| Профили (before) | Viral 2026 + legacy chapter bot + **PRO (удаляется полностью)** |
| Темы | dark (default) + light, CSS variables, persist localStorage + backend-копия |
| Автосохранение | debounce 10 с + ручное сохранение настроек проекта |
| Запуск | `./run.sh` с preflight cleanup |
| Порты | backend 8000, frontend 3000 |
| Корень хранилища | `data/` (projects, uploads, artifacts, logs) |
| Картозия RAG | **не обязательна** для этого pipeline (технический рефакторинг, не контентный) |

---

## Принцип «чистая хирургия, не хаос»

Запрещено в чанках:
- Писать в коде TODO/FIXME/mocks/plug — запрет действует на всю итерацию.
- Менять больше, чем требует чанк.
- Пропускать GATE-чекпоинт. Чанк не считается выполненным, пока не прошёл GATE.
- Удалять данные пользователя (`data/projects`, `data/artifacts`) без явного разрешения.

Разрешено:
- Консультироваться с Context7 по любой библиотеке (Vite, TanStack, Tailwind, ffmpeg, VideoToolbox).
- Использовать Sequential Thinking для архитектурных решений.
- Запускать `role-factory` для генерации специализированных ролей (security-auditor, design-alchemist, backend-surgeon, и т. п.).
- На этапах UI **обязательно** использовать `frontend-design` skill перед написанием любого куска frontend-кода.

---

## Принцип именования

**Единый префикс `REFACTR-NN.md` для всех PROD-чанков.** Сквозная нумерация от 00 до 66. Лупер определяет чанки по префиксу.

L1-файлы этапов (`00-АУДИТ.md` и пр.) — оглавления, лупер читает их как контекст, но не исполняет.

## Статусы этапов

| # | Этап | Статус | Чанки REFACTR-NN | Ключевые инструменты |
|---|------|--------|------------------|----------------------|
| 00 | Исследование и аудит | ⬜ | 00–06 | Serena, grep, file reads |
| 01 | Архитектурные решения | ✅ | 07–12 | Sequential Thinking, Context7 |
| 02 | Бэкенд: чистка и проекты | ⬜ | 13–20 | Serena, role-factory (backend-surgeon) |
| 03 | Бэкенд: рендер и безопасность | ⬜ | 21–26 | Context7 (ffmpeg), role-factory (security-auditor) |
| 04 | Фронт: миграция стека | ⬜ | 27–31 | Context7 (Vite, TanStack) |
| 05 | Фронт: дизайн-система и темы | ⬜ | 32–38 | **frontend-design skill (обязателен)**, role-factory (design-alchemist) |
| 06 | Фронт: Студия и проекты | ⬜ | 39–44 | **frontend-design skill** |
| 07 | Фронт: Workbench + идеи | ⬜ | 45–50 | **frontend-design skill** |
| 08 | Фронт: настройки и Cmd+K | ⬜ | 51–57 | **frontend-design skill** |
| 09 | Интеграция: run.sh и DevX | ⬜ | 58–61 | Bash, shellcheck |
| 10 | Финализация | ⬜ | 62–66 | E2E smoke, docs |

**Итого:** 11 этапов, 67 PROD-чанков (REFACTR-00..REFACTR-66), 11 L1-файлов, 1 навигатор, 1 Ralph-промпт, 1 README.

---

## Порядок выполнения

```
Этап 00 (Аудит) → Этап 01 (Архитектура) → Этап 02 (BCK) → Этап 03 (Render+Sec)
                                                                   │
Этап 10 (Финал) ← Этап 09 (DevX) ← Этап 08 (Settings+Cmd+K) ← Этап 07 (Workbench) ← Этап 06 (Студия) ← Этап 05 (Design System) ← Этап 04 (Front stack)
```

Внутри этапов — строгий последовательный порядок: L1-файл читается первым, затем PROD-чанки по возрастанию номера.

---

## Мультироли pipeline

| # | Код | Роль | Профессия | Soul | Этапы |
|---|-----|------|-----------|------|-------|
| 1 | R-AUDITOR | Аудитор проекта | Senior-разработчик, картограф кодовой базы | Видит живой код и мёртвый код, не обманывается объёмом | 00 |
| 2 | R-ARCHITECT | Архитектор | Ведущий инженер-архитектор, 14 лет опыта | Выбирает стек не по моде, а по нагрузке и боли пользователя | 01, 04 |
| 3 | R-BACKEND-SURGEON | Бэкенд-хирург | Python-инженер, FastAPI + SQLAlchemy | Умеет удалять не ломая, хирургия, а не экскаватор | 02, 03 |
| 4 | R-RENDER-ENG | Рендер-инженер | Спец по видеокодекам, ffmpeg, VideoToolbox | Каждый кадр — ресурс, hardware acceleration — право, не опция | 03 |
| 5 | R-SECURITY | Аудитор безопасности | Security engineer для локальных веб-сервисов | Локальный ≠ безопасный: .env, path traversal, ffmpeg-injection | 03 |
| 6 | R-FRONTEND-ARCHITECT | Фронт-архитектор | Senior React + Vite + TanStack | Next.js — тяжёлый SSR-стек. Для локального SPA — оверкилл | 04 |
| 7 | R-DESIGN-ALCHEMIST | Дизайн-алхимик | Senior UI/UX designer-dev | Продукт 2026 — динамичный как YouTube/Instagram, не AI-slop | 05, 06, 07, 08 |
| 8 | R-MOTION | Моушн-дизайнер | Специалист по анимациям Framer-Motion / CSS | Движение служит смыслу, не украшает пустоту | 05, 07 |
| 9 | R-UX-WRITER | UX-редактор | Писатель интерфейсных текстов | Русскоязычный UI без английских вкраплений, без клише | 05, 06, 07, 08 |
| 10 | R-DEVOPS | DevOps-инженер локального стека | Shell-скриптер, mac-админ | Preflight-cleanup, idempotent, никаких orphan-процессов | 09 |
| 11 | R-QA | Финальный тестировщик | QA-инженер smoke + E2E | Если не проверил в браузере — считай, не сделал | 10 |

Soul-элемент обязателен в каждой роли (как у Мусатова): профессия отвечает «что делает», soul — «почему именно так, а не иначе».

---

## Инструменты по этапам

| Этап | Serena | Context7 | Sequential Thinking | role-factory | frontend-design | Exa/Tavily |
|------|--------|----------|---------------------|--------------|-----------------|------------|
| 00 | 🔴 | — | ⚪ | — | — | — |
| 01 | — | 🔴 Vite, TanStack, ffmpeg | 🔴 | ⚪ | — | ⚪ |
| 02 | 🔴 | ⚪ | 🔴 | 🔴 backend-surgeon | — | — |
| 03 | 🔴 | 🔴 ffmpeg, VideoToolbox | 🔴 | 🔴 security-auditor | — | ⚪ |
| 04 | — | 🔴 Vite 6, TanStack | 🔴 | ⚪ | — | — |
| 05 | — | ⚪ Tailwind 4, RadixUI | ⚪ | 🔴 design-alchemist | 🔴 | ⚪ |
| 06 | — | ⚪ | ⚪ | ⚪ | 🔴 | — |
| 07 | — | ⚪ | ⚪ | ⚪ | 🔴 | — |
| 08 | — | ⚪ | ⚪ | ⚪ | 🔴 | — |
| 09 | — | ⚪ | ⚪ | ⚪ | — | — |
| 10 | — | — | ⚪ | — | — | — |

🔴 — обязательно в каждом подэтапе. ⚪ — по необходимости. — — не применяется.

---

## Дефолты инструментов

- **Serena:** `get_symbols_overview → find_symbol(include_body=True) → replace_symbol_body` для кодовых правок. `write_memory` для кросс-чанкового состояния.
- **Context7:** `resolve-library-id → get-library-docs` для любой документации библиотек.
- **Sequential Thinking:** минимум 5 шагов на архитектурные решения, формат FOR → AGAINST → VERDICT для спорных.
- **role-factory (`/create-role`):** генерация новой роли перед её первым использованием в чанке, если роль не в списке выше.
- **frontend-design skill:** запускается в НАЧАЛЕ каждого фронт-чанка этапов 05–08 командой `Skill → frontend-design`. Пишет код только после Phase 1–2 чеклиста скилла.

---

## Правила GATE-чекпоинта

Чанк считается завершённым только когда:
1. Артефакт создан в коде (или документация — для этапов 00, 01, 10).
2. Ручной smoke-тест пройден (где применимо: backend — `curl` на новый endpoint, frontend — открытие в браузере).
3. Нет регрессии: существующие фичи не сломаны (проверяется через запуск `run.sh` и минимальный e2e).
4. Нет TODO/FIXME/mocks в добавленном коде.
5. `git status` чистый в пределах чанка (все изменения относятся к одному результату).
6. Строка-лог добавлена в `PIPELINE-НАВИГАТОР.md` → секция «Лог изменений».

**СТОП-правила (обязательны для всех чанков):**

- STOP-1: 3 неудачные попытки подряд → обращение к Context7 (документация) → изменение подхода.
- STOP-2: архитектурное решение без явного указания в чанке → **спросить пользователя**, не решать самостоятельно.
- STOP-3: возникает желание удалить `data/` или `.env` → **спросить пользователя**.
- STOP-4: фронт-чанк (этапы 05–08) без активированного `frontend-design skill` → **остановить, запустить skill, переначать чанк**.
- STOP-5: появляются клише UI («modern and clean», generic gradient, AI-slop buttons) → **переписать согласно Phase 2 frontend-design skill**.

---

## Лог изменений

| Дата | Что |
|------|-----|
| 2026-04-24 | **Этап 01 ЗАВЕРШЁН.** Архитектурная основа зафиксирована: 5 ADR (0001 Frontend / 0002 Storage / 0003 Autosave / 0004 Video Engine / 0005 Theming) + C4-обзор (Level 1 + Level 2 + 2 sequence). Gate с человеком — ожидает подтверждения владельца перед Этапом 02. |
| 2026-04-24 | Чанк 13/67: REFACTR-12 «Итоговая C4-диаграмма» ✅ — артефакт `docs/architecture/c4-overview.md` (≈520 строк, 4 Mermaid-диаграммы). **Level 1 (System Context):** 7 участников — Никита (single-user), Gemini/Anthropic/OpenAI (LLM HTTPS, Gemini default), Deepgram (ASR HTTPS, опционально), macOS Finder (open -R), VideoToolbox (hardware encoder). **Level 2 (Containers):** 7 контейнеров — Frontend SPA (Vite 6 + React 19 + TanStack + Tailwind 4), Backend API (FastAPI + SQLAlchemy async + aiosqlite + uvicorn), Pipeline workers (asyncio in-process), Rendering engine (ffmpeg 7.1.1 VT subprocess argv-only), Transcription engine (MLX-Whisper subprocess или Deepgram httpx), SQLite (`data/videomaker.db` WAL + 12 таблиц + stage_progress JSON), File storage (`data/projects/{id}/settings.json` mutable + `runs/{run_id}/settings.json` immutable copy-on-run). 8 протоколов связи — REST + SSE fetch/EventSource, SQLAlchemy async aiosqlite, POSIX atomic-write (Path.replace + fsync), subprocess argv, httpx async для LLM/ASR. **Sequence 1 (new-project-to-reel):** 3 rect-блока стадий (Ingest с proxy-encode, Analysis с MLX-Whisper + Gemini generateContent + draft reel_ideas, Render с EncoderCapabilities-cache + per-idea loop + SSE progress). Frozen snapshot создаётся при POST /api/projects/{id}/runs — закрепляет settings для restart-from-step. **Sequence 2 (autosave-conflict):** нормальный поток (If-Match совпал) + 409 Conflict (вторая вкладка со stale ETag) + 3 альтернативы (reload / force-overwrite с копией в .trash/conflict-{ts}.json / cancel) + cross-tab theme sync через storage event. **8 системных инвариантов** с тестами: single-user localhost, .env никогда не покидает бэкенд (grep GEMINI_API_KEY apps/frontend = 0), SQLite single writer (WAL mode), autosave изолирован от runs/, argv-only subprocess (semgrep python.lang.security.audit.dangerous-subprocess = 0), VT default + software fallback, no-FOUC (Chrome DevTools Throttle 6× CPU тест FCP), data/ protection. **Этап 01 закрыт** — архитектурные контракты зафиксированы, переход к реализации. Gate с человеком (ожидает подтверждения владельца по 7 пунктам) → Этап 02 REFACTR-13 (удаление PRO / narrative_mode bottom_up\|map_reduce). |
| 2026-04-24 | Чанк 1/67: REFACTR-00 «Карта backend-сервисов» ✅ — артефакт `docs/audit/00-backend-services-map.md`. 97 services файлов (24 932 LoC), 5 мёртвых модулей (773 LoC под удаление), 8 API routes, 3 pipeline stage. Ключевая находка: PRO = `NarrativeMode="bottom_up"` в `models/runtime_settings.py:55`; оставляем `viral_2026` + `chaptered`. Автосохранение/restart-from-step/settings_snapshot — ноль ссылок, пишем с нуля в REFACTR-14–16. |
| 2026-04-24 | Чанк 2/67: REFACTR-01 «Карта frontend-страниц» ✅ — артефакт `docs/audit/01-frontend-map.md`. 19 маршрутов (6 1:1, 3 переделка, 2 удаление/слияние, 7 перегруппировка, 1 в модалку), 101 компонент .tsx (19 1:1 / 69 редизайн / 7 удаление / 7 slop). Подтверждены все 5 болей: OOM 12 ГБ (`package.json:6`), h-scroll корень (`SubtitleSettingsClient.tsx:239` — 3-col grid), post-prod без accordion (`PostProductionSettingsClient.tsx:374-414`), хардкод цветов (35 bg-white/black, очаги в TinderClient/ReelCard/SubtitlePreview), Cmd+K отсутствует (0 matches grep). |
| 2026-04-24 | Чанк 3/67: REFACTR-02 «Инвентаризация настроек» ✅ — артефакт `docs/audit/02-settings-inventory.md`. 8 страниц, ~224 настройки (performance 97 / post-prod 47 / profiles 24 / prompts 21 / subtitles 20 / models 10 / brand 5 / connections 0). Корень h-scroll `SubtitleSettingsClient.tsx:239` (grid-cols-[240px_1fr_auto] в ≤1020px). Конфликты: 3 разных «profile», brand kit не применяется, Instagram placeholder, флаг adaptive_leveller→мёртвый сервис, rhythm_aware vs snap_strategy дубликат. Предложена 7-групповая IA для REFACTR-51..57. |
| 2026-04-24 | Чанк 4/67: REFACTR-03 «PRO removal plan» ✅ — артефакт `docs/audit/03-pro-removal-plan.md`. Дизамбигуация 3 «profile»: `narrative_mode` (ампутируем), `vision_profile` (НЕ трогать), `account_profile` (НЕ трогать). **Открытие:** в БД уже `narrative_mode="viral_2026"` (с 2026-04-21) — ампутация формализует состоявшийся переход. 19 файлов под удаление (≥7 067 LoC, крупнейший `reels_composer.py` 2198 LoC), 20 полей в PerformanceSettings, 6 refs в frontend. Расширить safety-migration `performance_settings_store.py:91-98` на `bottom_up|map_reduce→viral_2026`. Функциональная регрессия Viral 2026 vs bottom_up (нет preference_memory/variants/coherence/ensemble) — требует ADR на Этапе 01 (REFACTR-07..12). STOP-2 не срабатывает. |
| 2026-04-24 | Чанк 5/67: REFACTR-04 «Схема данных» ✅ — артефакт `docs/audit/04-data-schema.md`. 12 прикладных таблиц + `alembic_version`, HEAD `eb6d1b814c95` (18 ревизий линейная add-only цепочка). Row counts: jobs=50 (31 done/19 error), artifacts=725, runtime_settings=87 EAV, **projects=0 → нулевой migration risk** для REFACTR-14. 720 orphan artifact-rows (5 job-папок vs 725 записей). Файловое хранилище 36 GB (uploads 15/proxies 9.7/artifacts 6.9/models 3.5/caches 345 MB); `data/logs/` пусто (→ REFACTR-59). `.env` 26 ключей, 5 LLM API. Предложен дизайн `ProjectRow` +5 полей (settings_snapshot_path, stage_progress JSON, soft_deleted_at, last_saved_at, parent_project_id, source_upload_path) + JSON snapshot format для ADR-08. |
| 2026-04-24 | Чанк 6/67: REFACTR-05 «Pipeline stages» ✅ — артефакт `docs/audit/05-pipeline-stages.md`. 3 фазы: ingest (347 LoC, 5 substages) → analysis (1454 LoC, 4-branch switch: bottom_up 11 substages / chaptered 1 / map_reduce 1 / viral_2026 1 + shared preamble/postprocess) → render (1733 LoC, 9 substages). Progress через `_STAGE_RANGES` (9 JobStage × диапазон 0-100). SSE централизован через `JobEventBus` (47 LoC) + `service.mark_stage` → endpoint `/api/v1/jobs/{id}/stream`; 6 типов событий (snapshot, created, stage-progress, profile_changed, done, error). **Критический пробел:** restart-from-step отсутствует, только `proxy_generate` + `transcribe` имеют automatic skip (content-addressed cache). Остальные артефакты пишутся, но loader-функций нет — требуется REFACTR-16 (+ stage_progress field в Project + endpoint + per-stage skip-check). |
| 2026-04-24 | Чанк 12/67: REFACTR-11 «ADR Темизация» ✅ — артефакт `docs/adr/0005-theming.md` (≈420 LoC, MADR). **Текущее состояние:** `globals.css:11` декларирует «одна единственная тёмная тема, без light-mode switcher» — инвариант устаревает, task.md §Goals требует «dark default + light, persist». **Решение ACCEPTED: Вариант B** — `html[data-theme="dark"|"light"]` атрибут-driven + 24 семантических токена в OKLCH (те же имена, два набора значений) + localStorage-first persist + async backend sync + inline flash-prevention script в `<head>`. Отклонены: (A) Tailwind 3-style class="dark" — нет места для system без доп. класса, `dataset` легче; (C) только prefers-color-scheme — нарушает требование persist. **Backward-compat:** 24 токена переносятся из `:root` в `:root, html[data-theme="dark"]` — существующие компоненты работают без правок. **Light-тема** — не просто инверсия L, новая иерархия: `--ink` paper-surface, `--paper` ink-text, `--gold` warm 0.68/0.16/80, `--focus` blue (не gold) для 3:1 контраста, тени меньше opacity + больший blur. **WCAG AA:** все body-text токены ≥Δ0.50 (4.5:1), UI-tokens ≥Δ0.30 (3:1). Exception: `--danger` light нужно скорректировать до `L=0.48 C=0.24` для Δ0.50. **Persist:** localStorage `videomaker-theme` ∈ {"dark","light","system"} + `matchMedia` для system + backend table `device_settings` (1 row, PK="default") с `GET/PUT /api/settings/device`. **Cross-tab sync** через `window.addEventListener('storage', ...)`. **Conflict:** localStorage выигрывает, backend async. **React:** `<ThemeProvider>` + `useTheme()` + `<ThemeToggle />` в TopBar (рядом с `<SaveStatusBadge />` из ADR-0003), hotkeys Cmd+Shift+L / Cmd+Shift+T. **Flash-prevention inline script** ~400 bytes в `<head>`: try/localStorage/matchMedia/dataset.theme/colorScheme — синхронное применение до FCP. **Tailwind 4** через `@theme` + `darkMode: ['selector', 'html[data-theme="dark"]']`. 10 gate-критериев для REFACTR-33/37 (localStorage, FOUC zero при throttle 6×, system-live-change, cross-tab, backend down + retry, WCAG AA через apca-w3, grep 0 hardcoded цветов). |
| 2026-04-24 | Чанк 11/67: REFACTR-10 «ADR Видеодвижок» ✅ — артефакт `docs/adr/0004-video-engine.md` (≈350 LoC, MADR). **Ключевая архитектурная корректировка:** вместо одного `hevc_videotoolbox` default (как в чанке) — **два render-профиля**, потому что `export_presets.yaml:6` уже переключён на `h264_videotoolbox` (commit `b3a97c1` — fix для Publer API ≤200 MB, 90-с HEVC 25 Mbps = 280 MB не влезает). **Решение ACCEPTED: Вариант B.** Профиль `publer_direct` (default, для direct-upload в Publer/Instagram/TikTok/YouTube Shorts): `h264_videotoolbox` + `avc1` + `-b:v 12M -maxrate 17M -bufsize 24M -pix_fmt yuv420p` + `-allow_sw 1 -realtime 0 -prio_speed 0` — 90-с рилс ≈135 MB. Профиль `archive_hevc` (optional, для архива/YouTube 4K): `hevc_videotoolbox` + `hvc1` + `-b:v 15M -maxrate 20M -bufsize 30M -pix_fmt yuv420p10le 10-bit` + color BT.709. **Fallback-лестницы:** publer_direct → `libx264 -crf 21 -preset medium`; archive_hevc → `libx265 -crf 23 -preset medium 10-bit` → `libx264 -crf 21 -preset slow` (крайний 8-bit). **Detection:** `EncoderDetector` при старте uvicorn кеширует `EncoderCapabilities` в `runtime_settings` (не переспрашивается на каждый рендер). **Проверено локально:** ffmpeg 7.1.1 с `--enable-videotoolbox` (homebrew, M5 10c/24 GB) — h264/hevc/prores videotoolbox + libx264/libx265 доступны. **Защита ≤200 MB Publer:** VBR вместо `-q:v` для детерминированного размера. **Progress:** regex `frame=N ... time=HH:MM:SS speed=Xx` из stderr → `JobEventBus.mark_stage_progress` (SSE-инфра из REFACTR-05). **Concurrency:** 2 parallel VT-encode на M-chip (сохраняется из `renderer.py:125`). Отклонены: (A) один HEVC default — ломает Publer, нужен re-encode костыль; (C) H.264 + HEVC post-hoc транскод — удвоение времени. 10 gate-критериев для REFACTR-21/22 (size, bitrate, tags, Publer POST, kill-VT → fallback, SSE progress 500 ms, 15 рилсов × 90 с ≤10 мин, <1 GB RAM, <40% CPU, detection кеш). |
| 2026-04-24 | Чанк 10/67: REFACTR-09 «ADR Автосохранение» ✅ — артефакт `docs/adr/0003-autosave.md` (380 LoC, MADR). Sequential Thinking 5 шагов + сравнение с Figma/Notion/Google Docs/GitHub/VSCode. **Решение ACCEPTED: Вариант B** — debounce 10 с (как в `task.md §2.3`) + last-write-wins + weak ETag по `last_saved_at` (RFC 7232 `If-Match`) + 4-state UI-индикатор + localStorage last-only queue для backend-down. Отклонены: (A) наивный debounce без ETag — тихая потеря данных при двух вкладках; (C) OT/CRDT (Figma/Google Docs) — overkill для single-user локалки. **Контракт API:** `PUT /api/projects/{id}/settings` с `If-Match: W/"{epoch_ms}"`; ответ 200 + новый ETag или 409 Conflict с `{current_etag, current_snapshot, current_last_saved_at}` в теле; 404/410/422 по стандарту. **Frontend:** хук `useAutosaveSettings(projectId)` на TanStack Query v5 `useMutation` + `use-debounce` (3 kB); Ctrl+S/Cmd+S — immediate flush через `debouncedFlush.flush()`; beforeunload confirm при dirty-state. **4 состояния:** idle (серая галочка + `Intl.RelativeTimeFormat` «Сохранено 5 с назад»), debouncing (жёлтый pulse), saving (синий spinner), error (красный + retry). **5-е состояние conflict:** модалка `<ConflictDialog />` с 3 опциями (reload / force save / cancel); force save копирует перетираемый серверный snapshot в `.trash/conflict-{timestamp}.json` (REFACTR-17). **Offline:** health-poll 5 с → `localStorage['videomaker.autosave.queue.{project_id}']` содержит только последний payload (last-write-wins) → flush при восстановлении. **Pipeline-изоляция:** автосейв пишет только в `settings.json`; `runs/{run_id}/settings.json` — copy-on-run (REFACTR-16), мутации автосейва не видны запущенному run-у. 10 gate-критериев для REFACTR-15/32-35 (curl-тесты 409, race-safety, debounce, Ctrl+S, kill uvicorn+localStorage, 2-вкладки, pipeline-isolation, beforeunload). |
| 2026-04-24 | Чанк 9/67: REFACTR-08 «ADR Хранение данных» ✅ — артефакт `docs/adr/0002-data-storage.md`. Sequential Thinking + проверка БД (`projects=0`, jobs без project_id=0 → greenfield). **Решение ACCEPTED: Вариант B** — SQLite (мета + hot-state JSON column `stage_progress`) + плоские JSON-файлы на диске. Отклонено: (A) всё в SQLite как JSON blob — раздувает БД, блокирует autosave, неинспектируемо; (C) Plain-JSON + SQLite index — хуже hot-path stage_progress, теряем Alembic. **Ключевое усиление сверх task.md §2.8:** введён per-run immutable snapshot `data/projects/{id}/runs/{run_id}/settings.json` — даёт детерминизм restart-from-stage (REFACTR-16). Финальная схема Project (12 полей): UUID PK + name/description/color + source_video_path + settings_snapshot_path + stage_progress JSON + last_saved_at + soft_deleted_at + parent_project_id FK (ON DELETE SET NULL) + profile_id (default viral_2026) + created/updated. Jobs расширены `run_id` для связи с frozen snapshot. Структура диска: `settings.json` (mutable, autosave 10 с, atomic write через `Path.replace()`) + `settings.meta.json` (schema_version + checksum_sha256) + `runs/{run_id}/` (immutable артефакты ingest/analysis/render) + shared clips/renders/thumbnails. Алгоритмы: atomic-write с os.fsync+replace, hard-delete (rmtree→commit + daily cleanup_orphans REFACTR-17), copy-from-project (копия settings.json, НЕ runs/, parent_project_id ссылка). Формат settings.json: `{schema_version, project_id, profile_id, sections: {runtime, brand_kit, post_production_preset, subtitle_style_preset, vision, prompts, profile_masks}, exported_at}`. Gate-критерии (REFACTR-14+16+17): alembic upgrade чистый, per-run snapshot создаётся, restart читает frozen snapshot, hard-delete consistent, orphans cleanup. |
| 2026-04-24 | Чанк 8/67: REFACTR-07 «ADR Frontend-стек» ✅ — артефакт `docs/adr/0001-frontend-stack.md`. Sequential Thinking 7 шагов (FOR/AGAINST/VERDICT × 3 варианта + advocate-проверка + consequences). **Решение ACCEPTED:** Vite 6 + React 19 + TanStack Router v1.114.3 + TanStack Query v5.90.3 + Tailwind 4. Context7 подтвердил: Vite 6 (`/websites/v6_vite_dev`), Vite 7 (`/websites/v7_vite_dev` — drop-in backward-compat); TanStack Router file-based routing через `createFileRoute` + автоген `routeTree.gen.ts` + type-safe links; TanStack Query v5 SSE-паттерн через `queryClient.setQueryData` в обработчике `EventSource` (или `experimental_streamedQuery` для AsyncIterable). Отклонены: (A) Next.js 16 + `output:'export'` — не решает корневую проблему heap ceiling Turbopack+App Router graph; (C) Tauri 2 — нарушает требование task.md §3.1 «localhost:3000 web», требует переписывания бэкенда. Gate-критерии REFACTR-31: `pnpm dev` без NODE_OPTIONS, RSS ≤500 МБ через 60 с, prod main chunk ≤500 КБ gzipped, type-safe `<Link>` без TS-ошибок. Миграционная нагрузка 3–5 дней распределена по REFACTR-27..31 (компоненты переносятся 1:1, меняется обёртка роутинга и fetch→useQuery). Потеря `next/image`/`next/font/local` — некритична для локалки (медиа через FastAPI streaming, шрифты self-hosted CSS `@font-face`). **Этап 01 стартовал.** |
| 2026-04-24 | Чанк 7/67: REFACTR-06 «UX-боли» ✅ — артефакт `docs/audit/06-ux-pains.md`. **11 болей** (6 владельца + 5 из аудита) с техническим доказательством `file:line`. Сматчены на чанки: #1 OOM 12 ГБ (`package.json:6`) → REFACTR-27/28/31; #2 mixed theming (13 компонентов с light-scale red-50/red-900 на тёмном фоне, 27 stone/zinc/slate/neutral/gray использований, hardcoded #fff/#000 в 9 точках) → REFACTR-33/37; #3 Cmd+K (0 handlers на `TopBar.tsx:90-111`) → REFACTR-57; #4 subtitles h-scroll (SubtitleStyleEditor 653 LoC + SubtitleSettingsClient 458 LoC без adaptive grid) → REFACTR-52; #5 post-production плоская IA (6 секций без группировки в `PostProductionSettingsClient.tsx:374-423`) → REFACTR-53; #6 нет Simple/Expert (0 matches grep, 8 разделов настроек) → REFACTR-51/56; #7 нет autosave (0 matches grep) → REFACTR-14/18; #8 нет restart-from-step (2/9 стадий со skip) → REFACTR-16/48; #9 нет Студии (Home = DashboardHero+UploadWizard+JobList, проекты отдельно в /projects) → REFACTR-39..44; #10 нет approve/reject/regenerate идей (LLM → render без паузы) → REFACTR-46/47/49; #11 95 backend-сервисов, ≥19 под удаление (~7067 LoC) → REFACTR-13/15. Приоритет лечения: OOM → autosave+restart → dead-code → дизайн-система → Студия → ideas-flow+Simple/Expert → IA subtitles/post-prod → Cmd+K. **ЭТАП 00 ЗАВЕРШЁН — 5 главных находок:** (1) Pipeline уже на viral_2026 в проде, PRO формализует ампутацию; (2) `projects=0` в БД даёт нулевой risk миграции схемы; (3) только 2/9 стадий поддерживают skip, остальное нужно строить с нуля (REFACTR-16); (4) 13 компонентов нарушают dark-theme через light-mode scale — smoking gun для дизайн-системы; (5) 95 backend-модулей с ~20% мёртвого долга блокируют безопасный рефакторинг до REFACTR-13/15. Переход → Этап 01 (Архитектурные решения, REFACTR-07). |
