# Руководство пользователя videomaker

> Полная справка по локальному нарезчику длинных видео на вертикальные рилсы 9:16 через multi-pass LLM-анализ.
>
> Обновлено: 2026-04-19

## Оглавление

1. [Что это и для кого](#1-что-это-и-для-кого)
2. [Быстрый старт](#2-быстрый-старт)
3. [Архитектура проекта](#3-архитектура-проекта)
4. [Pipeline обработки](#4-pipeline-обработки)
5. [UI: тур по страницам](#5-ui-тур-по-страницам)
6. [Настройки](#6-настройки)
7. [API Reference](#7-api-reference)
8. [Vision Layer](#8-vision-layer)
9. [Dramaturgy Framework](#9-dramaturgy-framework)
10. [Workflow: от загрузки до рилса](#10-workflow-от-загрузки-до-рилса)
11. [Scheduler и публикации](#11-scheduler-и-публикации)
12. [Dev-команды](#12-dev-команды)
13. [Troubleshooting и FAQ](#13-troubleshooting-и-faq)

---

## 1. Что это и для кого

### 1.1 Проблема

Длинные подкасты, лекции и интервью продолжительностью 1–3 часа содержат десятки сильных моментов, но добраться до них вручную дорого.

- Ручной монтаж 10 рилсов из двухчасового подкаста занимает 4–8 часов работы монтажёра
- Результат при ручном подходе — как правило 1–2 рилса, нарезанных подряд из одного места исходника
- Смысловая плотность страдает: хороший рилс собирается из фраз из **разных** временных точек, а не является вырезкой одного куска
- Масштабирование невозможно: при библиотеке в сотни часов ручной монтаж становится узким местом

```
ДО videomaker:
[Подкаст 2ч] → ручной монтаж 8ч → 1-2 рилса подряд из одного места

С videomaker:
[Подкаст 2ч] → upload → 25-35 мин → 6-12 рилсов из РАЗНЫХ мест (виртуальный монтаж)
```

### 1.2 Решение — виртуальный монтаж

videomaker анализирует транскрипт в несколько проходов и собирает рилсы-склейки из фрагментов, которые расположены в разных местах исходника.

- LLM обрабатывает транскрипт в 3 прохода: явные тезисы → неявные углы → сборка рилса из фрагментов разных мест
- Каждый рилс — склейка из 2–5 коротких фраз, взятых из разных временных точек
- Автоматический pipeline: upload → 25–35 минут → готовые mp4 рилсы 9:16 HEVC
- Работает локально на Apple Silicon (M5, 24 GB RAM): транскрибация через mlx-whisper или Deepgram API, рендер через ffmpeg VideoToolbox
- Видео на выходе: H.265 (HEVC), битрейт ≥15 000 kbps, 30 fps, соотношение сторон 9:16

### 1.3 Для кого

- **Креаторы и продюсеры** с библиотекой длинных интервью и подкастов, которым нужен поток коротких видео без найма монтажёра
- **SMM-команды**, которым требуется регулярный поток вертикальных видео из длинного исходного контента
- **Лекторы и эксперты**, которые записывают часовые выступления и хотят быстро получить нарезку смысловых цитат

### 1.4 Не для кого

- Короткие ролики менее 5 минут — нечего собирать из разных мест, проще вырезать вручную
- Live-стримы без записи — pipeline требует файл с word-level timestamps
- Музыкальные клипы и видео без речи — вся логика построена вокруг временных меток слов
- Пользователи не на Apple Silicon — mlx-whisper и VideoToolbox требуют нативного ARM-стека; Deepgram API снимает это ограничение для транскрибации, но рендер через VideoToolbox остаётся

### 1.5 Философия

> Замена монтажёра полностью, не помощь на 60%.

Это означает конкретные архитектурные решения:

- **Каждая новая фича — toggle on/off.** Пользователь решает, какие слои включить: Vision Layer, Arc-Coherence Validator, Smart Zoom и т.д. Если фича мешает — её отключают, не удаляют
- **Automatic Mode — ключевая фича.** Один клик, минимум настроек, результат на выходе. Тонкая настройка — для тех, кто хочет, а не требование
- **Legacy-код не удаляется, а изолируется.** Старые стратегии нарезки и модели остаются доступны через профили и настройки — пользователь выбирает, что работает для его контента

### 1.6 Что не делает (границы ответственности)

- **Не публикует без одобрения.** Scheduler требует подтверждения времени и платформы перед каждой публикацией
- **Не делает вертикальный кроп говорящих голов.** Авто-рефрейминг под спикера — отдельный инструмент; videomaker работает с исходным кадрированием или применяет Smart Zoom
- **Не работает как транскрибация-как-сервис.** Транскрипт — часть внутреннего pipeline, отдельный экспорт не предусмотрен
- **Не заменяет профессиональную цветокоррекцию.** Применяет пресеты LUT и базовые ffmpeg-фильтры; DaVinci Resolve для этого подходит лучше

## 2. Быстрый старт

### 2.1 Системные требования

| Компонент | Версия | Зачем |
|---|---|---|
| macOS + Apple Silicon | M1 или новее (оптимизировано под M5, 24 GB RAM) | mlx-whisper + VideoToolbox HEVC encoding |
| Python | 3.12 (ставится через `uv`) | backend |
| Node.js | >= 20 | frontend dev server |
| pnpm | любая | frontend package manager |
| ffmpeg | >= 7 с `hevc_videotoolbox` | рендер, транскод, silence cut |

Linux и Intel Mac формально не поддерживаются: mlx-whisper и VideoToolbox — Apple-specific технологии, которые не работают вне нативного ARM-стека. Теоретически можно переключиться на Deepgram STT вместо mlx-whisper и на кодировщик `libx265` или `libx264` вместо VideoToolbox, но это требует правок в `config/export_presets.yaml` и не входит в стандартный путь установки.

---

### 2.2 Установка зависимостей

```bash
# uv (Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# node + pnpm + ffmpeg через Homebrew
brew install node pnpm ffmpeg
```

Проверка установки:

```bash
uv --version           # >= 0.5
node --version         # >= v20
pnpm --version
ffmpeg -version        # смотри что есть hevc_videotoolbox в "--enable-..."
ffmpeg -hide_banner -encoders 2>&1 | grep hevc_videotoolbox
```

Если последняя команда ничего не вернула — у твоего ffmpeg нет VideoToolbox. Переустанови через:

```bash
brew reinstall ffmpeg
```

---

### 2.3 Первый запуск

```bash
cd <source-repo>
./run.sh
```

Что делает `run.sh`:

1. Проверяет наличие `.env` — если нет, копирует из `.env.example` и печатает напоминание добавить `GEMINI_API_KEY`
2. Создаёт директории `data/uploads`, `data/artifacts`, `data/logs`
3. Проверяет наличие `uv`, `pnpm`, `ffmpeg` — выходит с ошибкой если чего-то нет
4. Запускает backend (`uvicorn videomaker.main:app --reload`) на `http://127.0.0.1:8000`
5. Запускает frontend (`pnpm dev`) на `http://localhost:3000`
6. `Ctrl+C` останавливает оба процесса (через trap cleanup)

---

### 2.4 Минимальный `.env`

Сразу после первого запуска — открой `.env` и впиши ключи. Минимум для работы — `GEMINI_API_KEY`. Остальное опционально.

```env
# Обязательно
GEMINI_API_KEY=AIza...
GEMINI_DEFAULT_MODEL=gemini-2.5-flash

# Опционально — альтернативный STT для русского
DEEPGRAM_API_KEY=
DEEPGRAM_MODEL=nova-3

# Опционально — fallback LLM с prompt caching
ANTHROPIC_API_KEY=
ANTHROPIC_DEFAULT_MODEL=claude-sonnet-4-5-20250929

# Опционально — GPT-5 как дополнительный fallback
OPENAI_API_KEY=
OPENAI_DEFAULT_MODEL=gpt-5

# Прикладные настройки (дефолты подойдут)
APP_HOST=127.0.0.1
APP_PORT=8000
APP_LOG_LEVEL=INFO
APP_MAX_UPLOAD_SIZE_MB=30720

# Chunking thresholds (не трогай без понимания)
CHUNK_TOKEN_THRESHOLD=20000
CHUNK_WINDOW_TOKENS=15000
CHUNK_OVERLAP_TOKENS=1500
LLM_MAX_CONCURRENCY=10
```

**Где брать API-ключи:**

| Провайдер | Зачем | Стоимость | Ссылка |
|---|---|---|---|
| Gemini | Основной LLM, tier: Pro/Flash/Flash Lite | Есть бесплатный уровень | <https://aistudio.google.com/app/apikey> |
| Deepgram | Альтернативный STT, nova-3 точнее для русского | $200 бесплатных кредитов | <https://console.deepgram.com/signup> |
| Anthropic | Claude с prompt caching (экономит токены на длинных транскриптах) | Платный | <https://console.anthropic.com/settings/keys> |
| OpenAI | GPT-5 как дополнительный fallback | Платный | <https://platform.openai.com/api-keys> |

---

### 2.5 Первая проверка работоспособности

Backend:

```bash
curl http://127.0.0.1:8000/api/v1/health
# → {"status":"ok",...}
```

Интерактивная документация API:

<http://127.0.0.1:8000/docs>

Frontend:

<http://localhost:3000> — должна открыться главная страница с upload-зоной и пустым списком jobs.

---

### 2.6 Что делать если что-то не запустилось

- `uv не установлен` — скрипт `run.sh` выдаст точный совет, следуй ему
- `pnpm не установлен` — `npm install -g pnpm`
- `ffmpeg не установлен` — `brew install ffmpeg`
- Порт 8000 занят — измени `APP_PORT` в `.env`
- Порт 3000 занят — Next.js автоматически предложит 3001
- UI пишет «Не настроен ни один LLM-провайдер» — проверь что `GEMINI_API_KEY` в `.env` не пустой, затем перезапусти `./run.sh`

Полный список проблем — раздел 13 «Troubleshooting».

## 3. Архитектура проекта

### 3.1 Monorepo layout

```
videomaker/
├── apps/
│   ├── backend/          # Python 3.12 (FastAPI + SQLAlchemy + Alembic), uv-managed
│   └── frontend/         # Next.js 16 + React 19 + Tailwind 4, pnpm
├── data/                 # создаётся run.sh
│   ├── videomaker.db     # SQLite (jobs, artifacts, settings, connections...)
│   ├── uploads/<job_id>/ # исходные mp4
│   └── artifacts/<job_id>/
│       ├── audio/        # извлечённая WAV 16 kHz mono
│       ├── text/         # transcript.json, reel_plan.json, manifest.json
│       ├── reels/        # финальные mp4 (H.265 HEVC)
│       └── subs/         # ASS subtitles
├── docs/                 # планы, research, this guide
├── Референсы/             # примеры рилсов для вдохновения
├── run.sh                # скрипт запуска backend + frontend
├── .env                  # ключи и настройки приложения
├── README.md             # короткий quickstart
└── CONTEXT.md            # исходный контекст проекта
```

Два приложения живут в `apps/` и запускаются одной командой `./run.sh`. Данные хранятся за пределами обоих приложений — в `data/`, который никогда не попадает в git.

### 3.2 Backend слои

| Директория | Ответственность |
|---|---|
| `apps/backend/src/videomaker/main.py` | FastAPI приложение, lifespan для seed промптов |
| `apps/backend/src/videomaker/api/routes/` | HTTP endpoints: `health`, `jobs`, `settings`, `files`, `schedule`, `connections`, `post_production`, `proxies` |
| `apps/backend/src/videomaker/core/` | config, DB session, logging, artifacts paths |
| `apps/backend/src/videomaker/models/` | SQLAlchemy таблицы + Pydantic DTO |
| `apps/backend/src/videomaker/services/` | Бизнес-логика: ~70 сервисов (pipeline, analyzers, transcribers, renderer, scheduler...) |
| `apps/backend/src/videomaker/services/agents/` | Multi-agent orchestrator (Kartoziya framework) — `base.py` + `orchestrator.py` |
| `apps/backend/src/videomaker/services/vision/` | Moondream локальный vision-модуль (`model_manager`, `frame_cache`, `rate_limiter`, `factory`) |
| `apps/backend/src/videomaker/services/broll/` | B-roll index + retriever + inserter |
| `apps/backend/src/videomaker/services/transcribers/` | mlx-whisper + Deepgram factory |
| `apps/backend/src/videomaker/services/video_effects/` | Реестр эффектов (ч/б сейчас) |
| `apps/backend/src/videomaker/services/prompts_data/` | Seed-промпты для всех 12 стадий |
| `apps/backend/src/videomaker/config/` | `fillers_ru.yaml` + `export_presets.yaml` |
| `apps/backend/alembic/` | Миграции SQLite |
| `apps/backend/tests/` | Unit + integration тесты (~190 тестов) |

### 3.3 Ключевые сервисы — что за что отвечает

> После архитектурного рефакторинга (2026-04-20) `services/pipeline.py` сжался с 2769 до 363 LOC. Фактическая логика вынесена в:
> - `services/pipeline_context.py` — `PipelineContext` dataclass, shared state между стадиями
> - `services/pipeline_stages/ingest.py` — stages 1–4 (probe/proxy/transcribe/translate/silence_cut)
> - `services/pipeline_stages/analysis.py` — Kartoziya 5.1–5.10
> - `services/pipeline_stages/render.py` — финальная сборка MP4 + graph transforms + ffmpeg

- `services/pipeline.py` — тонкий оркестратор: `ctx = PipelineContext(...); ctx = await run_ingest_stage(ctx); ctx = await run_analysis_stage(ctx); ctx = await run_render_stage(ctx)`
- `services/jobs.py` — throttled progress updates для SSE, хранит live-статус job
- `services/job_event_bus.py` — in-memory SSE pub/sub (выделено из jobs.py)
- `services/analyzers/` — multi-pass LLM: Pass 1 явные тезисы → Pass 2 неявные углы → Pass 3 виртуальный монтаж из фрагментов разных мест
- `services/chunker.py` + `semantic_chunker.py` — RAG-style sliding window по tiktoken; нарезает длинные транскрипты на перекрывающиеся окна перед подачей в LLM
- `services/compression.py` — Stage 3: параллельная Flash Lite компрессия чанков транскрипта, уменьшает объём для следующих стадий
- `services/canvas_builder.py` + `canvas_embedder.py` — Stage 4: строит Canvas-документ (структурированное представление контента) из сжатого транскрипта через Gemini Pro
- `services/reducer.py` + `cross_chunk_reducer.py` — Stage 6: дедупликация кандидатов через Jaccard similarity + LLM-ранкинг лучших моментов
- `services/coherence_validator.py` — Stage 5.9: проверка arc-coherence собранного рилса; режимы off / reject / resort через `PerformanceSettings`
- `services/story_doctor.py` — Stage 7: финальная склейка сценария рилса через Gemini Pro с fallback
- `services/rhythm_check.py` — Stage 8: эвристическая проверка ритма рилса (длительности фраз, паузы, темп)
- `services/variants_generator.py` — Stage 9: генерирует 4 варианта рилса (разные ракурсы, тональность, хук)
- `services/llm_client.py` — facade поверх `services/llm_clients/` пакета + `build_llm` / `build_llm_for_tier` через `PROVIDER_REGISTRY` (hot-plug точка для новых LLM)
- `services/llm_clients/` — пакет: `base.py` (Protocol + `_BaseLLMClient` ABC), `gemini.py` / `claude.py` / `openai.py` / `zhipu.py` (4 клиента), `retry.py`, `json_parser.py`, `tier_resolver.py`
- `services/llm_providers/` — factory-пакет для registry-driven регистрации провайдеров (`register_llm_provider(GeminiProviderFactory())` и т.п.)
- `services/prompt_store.py` + `prompts.py` — загрузка и seed промптов из БД; если запись пустая, вставляет дефолт из `prompts_data/`
- `services/rate_limiter.py` — защита от rate limits провайдеров; контролирует окно запросов к каждому LLM-провайдеру
- `services/silence_cutter.py` — RMS-детекция тишины + regex-детекция слов-паразитов по `fillers_ru.yaml`; вырезает паузы из финального рилса
- `services/media.py` — ffmpeg wrappers: probe, extract audio, cuts; единая точка входа для всех операций с медиафайлами
- `services/renderer.py` + `project_renderer.py` — HEVC пресеты + `render_reel_plans`; финальный рендер mp4 через ffmpeg VideoToolbox
- `services/filter_graph_builder.py` — построение `ffmpeg filter_complex` для склеек, zoom, субтитров и аудио-эффектов в одном проходе
- `services/subtitles.py` + `subtitle_styles.py` + `subtitle_store.py` — ASS writer + 4 встроенных пресета + CRUD настроек субтитров
- `services/profile_detector.py` + `profile_masks.py` — 5 профилей (Лектор, Интервью, Подкаст, Скринкаст, Универсал); детектирует тип контента и применяет маску настроек
- `services/adaptive_leveller.py` + `audio_normalizer.py` + `audio_analyzer.py` — audio обработка: нормализация громкости, адаптивное выравнивание уровней
- `services/vad.py` + `beat_detector.py` + `breath_classifier.py` — audio-аналитика: VAD для точных границ слов, детекция битов, классификация вдохов для чистых резов
- `services/zoom_planner.py` + `deictic_zoom.py` + `spring_zoom_planner.py` — smart zoom: автозум для скринкастов (на курсор) и talking head (на лицо), плавный spring-анимированный zoom
- `services/cover_selector.py` — выбор кадра-обложки для рилса через Vision Layer или эвристики
- `services/emphasis_motion.py` + `match_cuts.py` + `jl_cut_planner.py` — монтажные приёмы: подчёркивание ключевых фраз, match cuts, J/L-нахлёсты
- `services/face_tracker.py` + `object_tracker.py` + `cursor_detector.py` + `person_cluster.py` + `eye_trace_continuity.py` — computer vision: трекинг лица и объектов, детекция курсора в скринкастах, кластеризация спикеров
- `services/visual_validator.py` + `visual_evidence_agent.py` — Vision Layer: валидация рилсов через Moondream; проверяет визуальное качество кадров
- `services/scheduler_worker.py` + `scheduled_posts_store.py` — фоновый worker отложенных публикаций + хранилище расписания
- `services/instagram_publisher.py` + `youtube_oauth.py` — интеграции публикации в Instagram и YouTube
- `services/connections_store.py` — хранилище OAuth токенов и API ключей пользовательских интеграций
- `services/runtime_settings_store.py` — facade; реальная логика разделена на `performance_settings_store.py` (PerformanceSettings + TTL cache + job ContextVar override) и `vision_settings_store.py` (VisionRuntimeSettings)
- `services/vision/registry.py` — VISION_REGISTRY: hot-plug точка для новых vision providers (сейчас только `moondream_local`, готово под Gemini Vision / OpenAI Vision)
- `services/settings_service.py` — domain-level CRUD для prompt overrides (вынесено из `api/routes/settings.py` в рамках чистки layers)
- `services/preference_memory.py` — «нравится/не нравится» пользователя по конкретным рилсам; используется для улучшения ранкинга в следующих jobs

### 3.4 Frontend страницы

| Путь | Страница | Что показывает |
|---|---|---|
| `src/app/page.tsx` | Dashboard | upload-зона + список jobs с текущим статусом |
| `src/app/jobs/[id]/page.tsx` | Job details | live SSE прогресс 9 стадий + video player готовых рилсов |
| `src/app/settings/models/page.tsx` | Models | LLM-провайдеры, tier matrix (Pro / Flash / Flash Lite) |
| `src/app/settings/prompts/page.tsx` | Prompts | редактор 12 промптов стадий pipeline |
| `src/app/settings/subtitles/page.tsx` | Subtitles | 3-колоночный редактор стилей + live preview |
| `src/app/settings/profiles/page.tsx` | Profiles | 5 профилей (Лектор / Интервью / Подкаст / Скринкаст / Универсал) |
| `src/app/settings/performance/page.tsx` | Performance | coherence validator, scaling reducer caps |
| `src/app/settings/brand/page.tsx` | Brand | логотип, водяные знаки, бренд-цвета |
| `src/app/settings/connections/page.tsx` | Connections | YouTube OAuth + Instagram токен |
| `src/app/settings/post-production/page.tsx` | Post-production | B-roll, video effects, музыка |
| `src/app/schedule/page.tsx` | Schedule | календарь отложенных публикаций |

### 3.5 Frontend слои

| Директория | Ответственность |
|---|---|
| `src/app/` | Next.js 16 routes (Server + Client Components) |
| `src/components/` | UI компоненты (shadcn + custom) |
| `src/components/settings-shared/` | shared form primitives (Group, SwitchRow, NumberRow, SliderRow, SelectRow) |
| `src/components/settings/performance-groups/` | 22 group-компонента для `PerformanceSettingsClient` |
| `src/components/settings/post-production/` | 8 section-компонентов для `PostProductionSettingsClient` |
| `src/components/upload/` | `UploadWizard` + `useWizardState` hook + `WizardSteps` primitives |
| `src/hooks/useSettingsSave.ts` | Shared hook для save state (busy/dirty/error/savedAt) в settings клиентах |
| `src/lib/api.ts` | Facade re-export — см. `src/lib/api/` |
| `src/lib/api/` | Domain-split HTTP клиент: `core.ts` (request wrapper), `jobs.ts`, `settings.ts`, `subtitle.ts`, `post_production.ts` |
| `src/lib/sse.ts` | `useJobSse` hook для live прогресса job через SSE |
| `src/lib/video-thumbnail.ts` | Client-side thumbnail extraction через `<video>` + `<canvas>` для split-screen preview |

### 3.6 Data слой — SQLite

База данных находится в `data/videomaker.db`. Создаётся автоматически при первом запуске. Миграции управляются через Alembic (`apps/backend/alembic/versions/`).

Ключевые таблицы:

| Таблица | Содержимое |
|---|---|
| `jobs` | все загруженные видео и их статус обработки |
| `artifacts` | метаданные файлов: пути, длительность, размер, тип |
| `prompt_settings` | пользовательские промпты; если запись пустая — seed из `prompts_data/` |
| `subtitle_presets` | 4 встроенных пресета + user-defined стили субтитров |
| `runtime_settings` | настройки из UI (STT-провайдер, performance флаги, активный профиль...) |
| `scheduled_posts` | очередь отложенных публикаций с платформой и временем |
| `connections` | OAuth токены (YouTube refresh token, Instagram long-lived token) |
| `preferences` | `preference_memory` — оценки рилсов пользователем для улучшения ранкинга |

## 4. Pipeline обработки

### 4.1 Обзор pipeline

Pipeline оркестрируется функцией `run_pipeline` в `apps/backend/src/videomaker/services/pipeline.py`. На вход поступает путь к загруженному mp4-файлу, на выходе — список `RenderedReel` (финальных рилсов). Прогресс транслируется в реальном времени через SSE в диапазоне 0–100 процентов; каждой стадии соответствует свой числовой диапазон, определённый в словаре `_STAGE_RANGES`. Внутри стадии `analyze` запускается вложенный Kartoziya 8-sub-stage LLM pipeline, который составляет основную долю вычислительной работы.

---

### 4.2 Top-level стадии

| Стадия (`JobStage`) | Прогресс | Описание |
|---|---|---|
| `ingest` | 0–5 % | ffprobe читает метаданные исходника: длительность, fps, разрешение, кодек |
| `proxy_generate` | 5–15 % | опционально: создаёт быстрый прокси-файл для длинных видео, ускоряет seek при рендере |
| `transcribe` | 15–40 % | word-level timestamps через mlx-whisper (локально) или Deepgram nova-3 (API) |
| `translate` | 40–50 % | адаптивный EN→RU перевод, если detected language != `ru` |
| `silence_cut` | 50–60 % | удаление пауз ≥ 0.6 с + filler regex по `config/fillers_ru.yaml` |
| `analyze` | 60–80 % | Kartoziya 8-sub-stage LLM pipeline (см. 4.3) |
| `render` | 80–95 % | ffmpeg `filter_complex` + VideoToolbox HEVC + ASS subtitles burn-in |
| `finalize` | 95–99 % | обновление `job.artifacts`, запись `manifest.json` |
| `done` | 100 % | готово, SSE `done` event |

---

### 4.3 Kartoziya 8-sub-stage LLM pipeline (внутри стадии `analyze`)

Под-стадии выполняются последовательно внутри `analyze`. Каждая использует определённый tier LLM (Pro / Flash / Flash Lite), который настраивается в `/settings/models`.

**1. `compression` — сжатие транскрипта**

- Модель: Flash Lite (дешёвый, быстрый)
- `services/chunker.py` режет транскрипт на перекрывающиеся окна по tiktoken (sliding window)
- Каждый chunk обрабатывается параллельно: на выходе — список ключевых утверждений + метаданные временных меток
- Файл: `services/compression.py`

**2. `canvas_builder` — построение Canvas проекта**

- Модель: Pro (один вызов на весь проект)
- Вход: сжатый транскрипт со всех chunks
- Выход: `ProjectCanvas` — драматургическая карта: темы, тезисы, конфликты, персонажи
- Файл: `services/canvas_builder.py`

**3. `orchestrate_extraction` — параллельная экстракция кандидатов рилсов**

- Модель: Flash Lite для Wave 1, Flash с `thinking_budget=512` для Wave 2
- 6 агентов × N chunks, разделены на 2 волны
- **Wave 1 (reaction-extractors):** `hook_hunter`, `emotional_peak_finder`, `humor_specialist`
- **Wave 2 (meaning-extractors):** `dramatic_irony_scanner`, `thesis_extractor`, `motif_tracker`
- Wave 2 видит `coverage_summary` от Wave 1 и фокусируется на непокрытых chunk'ах
- Подробнее о каждом агенте — раздел 9.3
- Файлы: `services/agents/orchestrator.py`, `services/agents/base.py`, `AGENT_REGISTRY`

**4. `reduce_and_rank` — дедупликация и ранжирование**

- Модель: Flash + Jaccard dedup (нечёткое сравнение по пересечению слов)
- Удаляет дублирующиеся кандидаты, ранжирует оставшиеся по importance score
- Опциональный `cross_chunk_reducer` (performance setting) — ищет противоречия между кандидатами из разных chunks, вычищает непоследовательные
- Опциональный `coherence_validator` (performance setting, режимы `off` / `reject` / `resort`) — проверяет драматургическую связность набора кандидатов
- Файлы: `services/reducer.py`, `services/cross_chunk_reducer.py`, `services/coherence_validator.py`

**5. `compose_story_script` — финальный story script**

- Модель: Pro
- Строит 3-act arc для каждого отобранного рилса: setup → conflict → resolution
- Выход: `StoryScript` с точными сегментами и их порядком
- Файл: `services/story_doctor.py`

**6. `check_rhythm` — проверка ритма**

- Модель: Flash + эвристика
- Ищет middle-sag: ритмическую проблему, при которой середина рилса слабее начала и конца
- Помечает рилсы, которые нужно переписать или перерезать
- Файл: `services/rhythm_check.py`

**7. `generate_variants` — варианты формата**

- Модель: Pro
- Для каждого утверждённого рилса генерирует 4 формата: `punchline` / `conflict` / `visual` / `authority`
- Позволяет A/B-тестировать разные углы подачи одного и того же тезиса
- Файл: `services/variants_generator.py`

**8. `compose_reels` — финальная сборка**

- Sync-операция (без LLM): склейка segments из разных временных точек по плану
- Uniqueness filter: если два рилса после composing слишком похожи, один отбрасывается
- Target N: подрезается до целевого количества, если пользователь задал `target_reel_count`
- Файл: `services/reels_composer.py`

---

### 4.4 Что происходит после `analyze` (стадия `render`)

К моменту старта рендера стадия `silence_cut` уже отработала: паузы и filler-слова помечены в транскрипте.

- `services/filter_graph_builder.py` строит `filter_complex` для ffmpeg: concat сегментов из разных временных точек + resize под 9:16 + overlay субтитров
- `services/renderer.py` / `project_renderer.py` запускает ffmpeg с `-c:v hevc_videotoolbox` (Apple hardware encoder)
- `services/subtitles.py` записывает ASS-файл с позиционированием по выбранному `subtitle_preset`
- Результат: `data/artifacts/<job_id>/reels/*.mp4`

---

### 4.5 Выходные артефакты

После успешного завершения все файлы сохраняются в `data/artifacts/<job_id>/`:

| Файл | Содержимое |
|---|---|
| `text/transcript.json` | raw STT-output с word-level timestamps |
| `text/cleaned_transcript.json` | транскрипт после `silence_cut` и filler removal |
| `text/reel_plan.json` | план рилсов (сегменты) после `analyze` |
| `text/analysis_summary.json` | агрегированная метаинформация по job |
| `text/manifest.json` | индекс всех файлов job (заполняется в `finalize`) |
| `audio/audio.wav` | извлечённый 16 kHz mono WAV |
| `reels/*.mp4` | финальные HEVC рилсы (9:16, 30 fps, ≥ 15 Mbps) |
| `subs/*.ass` | ASS субтитры, по одному файлу на рилс |

---

### 4.6 Live прогресс через SSE

Прогресс транслируется через Server-Sent Events:

```
GET /api/v1/jobs/{id}/stream
```

Формат событий (стандарт SSE):

```
event: progress
data: {"stage": "analyze", "progress": 68, "message": "compression: 12 chunks через Flash Lite"}

event: done
data: {"job_id": "abc", "reels": 8}
```

Frontend использует `useJobSse` hook (`apps/frontend/src/lib/sse.ts`) для live-отображения прогресс-бара и текущего сообщения стадии. Подробная документация всех SSE-событий и REST эндпоинтов — раздел 7 «API Reference».

## 5. UI: тур по страницам

### 5.1 Dashboard — главная страница (`/`)

Dashboard — точка входа. Здесь пользователь загружает видео, выбирает профиль и следит за списком jobs.

Схема экрана:

```
[ Dashboard ]
┌─────────────────────────────────────┐
│  Профиль: [Подкаст ▾] ⓘ             │
│  Стиль субтитров: [TikTok белый ▾]  │
│  [редактировать стили →]            │
│                                      │
│  ┌─────────────────────────────┐   │
│  │   Drop video here           │   │
│  │   или [Выбрать файл]        │   │
│  └─────────────────────────────┘   │
│                                      │
│  Недавние jobs:                     │
│  ● job_abc123   Done  (12 рилсов)  │
│  ◐ job_xyz789   Stage analyze 68%  │
│  ○ job_old      Queued             │
└─────────────────────────────────────┘
```

**Upload-зона** (`UploadDropzone`):

- Принимает drag-and-drop или выбор через file picker
- Максимальный размер файла — 30 ГБ (задаётся через `APP_MAX_UPLOAD_SIZE_MB` в `.env`)
- После выбора файла немедленно инициируется POST-загрузка; появляется индикатор прогресса upload
- Поддерживаются любые видеоформаты, которые понимает ffprobe; внутри pipeline исходник конвертируется при необходимости

**ProfileSelector** (`ProfileSelector`):

- Выпадающий список пяти профилей: Лектор / Интервью / Подкаст / Скринкаст / Универсал
- Кнопка `ⓘ` рядом открывает tooltip с описанием профиля и ключевыми отличиями маски настроек
- Выбранный профиль передаётся вместе с job при загрузке; pipeline резолвит маску профиля один раз в начале обработки
- Детальный редактор профилей — `/settings/profiles` (раздел 6.4)

**Стиль субтитров**:

- Выпадающий select со встроенными пресетами и пользовательскими стилями из `subtitle_presets`
- Рядом отображается мини-preview пресета: цвет, шрифт, позиция на кадре
- Кнопка «редактировать стили» ведёт на `/settings/subtitles` (раздел 6.3)
- Последний выбранный пресет запоминается в `localStorage` браузера и подставляется при следующем визите

**Список jobs**:

- Отображает все jobs в обратном хронологическом порядке
- Индикаторы статуса: `Queued` (ожидание), `Running` / название текущей стадии + процент (в процессе), `Done` + количество рилсов, `Failed` + краткое сообщение ошибки
- Клик на строку job переходит на `/jobs/[id]`

Файлы: `apps/frontend/src/app/page.tsx`, `apps/frontend/src/components/ProfileSelector.tsx`, `apps/frontend/src/components/UploadDropzone.tsx`.

---

### 5.2 Job details — детали job (`/jobs/[id]`)

Страница открывается сразу после загрузки видео и обновляется в реальном времени через SSE без ручного refresh.

**Live прогресс (пока job выполняется)**:

- Название текущей стадии pipeline (например, `transcribe`, `analyze`) и числовой процент из SSE
- Сообщение прогресса под прогресс-баром (например, «compression: 12 chunks через Flash Lite»)
- Frontend подписывается на `GET /api/v1/jobs/{id}/stream` через hook `useJobSse` (`apps/frontend/src/lib/sse.ts`); компонент обновляется при каждом SSE-событии типа `progress`
- По получении события `done` прогресс-бар скрывается, появляется сетка рилсов

**Сетка рилсов (после завершения)**:

Каждая карточка рилса содержит:

- Preview первого кадра; при наведении (hover) — автовоспроизведение без звука
- Длительность, битрейт, размер файла в человекочитаемом формате
- Кнопки действий: скачать mp4, опубликовать сейчас (Instagram / YouTube), запланировать публикацию, удалить
- Отметки «нравится» / «не нравится» — записываются в `preference_memory` (`services/preference_memory.py`) и используются для улучшения ранкинга в следующих jobs

**Кнопка «Опубликовать сейчас»**:

- Открывает модальное окно выбора платформы (Instagram / YouTube) и подтверждения
- Требует предварительно настроенного подключения в `/settings/connections`; если токена нет, предлагает перейти в настройки

**Кнопка «Запланировать»**:

- Открывает date/time picker
- После подтверждения добавляет запись в `scheduled_posts` и перенаправляет на `/schedule`

Файлы: `apps/frontend/src/app/jobs/[id]/page.tsx`, клиентские компоненты плеера и карточек рилсов.

---

### 5.3 Schedule — календарь отложенных публикаций (`/schedule`)

Страница управления очередью публикаций. Worker `scheduler_worker.py` работает в фоне и сам подхватывает посты, когда приходит время, — пользователю не нужно держать страницу открытой.

**Список scheduled posts**:

- Фильтры по статусу: `pending` (ожидает публикации), `posted` (опубликовано), `failed` (ошибка при публикации)
- Для каждого поста отображается: время публикации, платформа (Instagram / YouTube), идентификатор рилса (`reel_id`), текущий статус
- Посты отсортированы по времени публикации

**Действия над постом**:

- «Изменить время» — открывает date/time picker, обновляет запись в `scheduled_posts`
- «Опубликовать сейчас» — немедленно запускает публикацию, минуя расписание
- «Отменить» — удаляет пост из очереди (доступно только для статуса `pending`)

**Фоновый worker**:

- `apps/backend/src/videomaker/services/scheduler_worker.py` поллит базу каждые 60 секунд
- Подхватывает записи с `status=pending` и `scheduled_at <= now()`, вызывает `instagram_publisher.py` или `youtube_oauth.py` в зависимости от платформы
- При успехе обновляет статус на `posted`; при ошибке — на `failed` с сохранением сообщения ошибки
- Хранилище расписания: `apps/backend/src/videomaker/services/scheduled_posts_store.py`

Файлы: `apps/frontend/src/app/schedule/page.tsx`, `apps/backend/src/videomaker/services/scheduler_worker.py`, `apps/backend/src/videomaker/services/scheduled_posts_store.py`.

---

### 5.4 Общая навигация и sidebar

Sidebar присутствует на всех страницах приложения. Реализован в `apps/frontend/src/app/layout.tsx`; для страниц группы Settings используется вложенный `apps/frontend/src/app/settings/layout.tsx`.

**Пункты навигации**:

- **Dashboard** (`/`) — главная страница, upload и список jobs
- **Schedule** (`/schedule`) — очередь отложенных публикаций
- **Settings** — expandable группа, разворачивается кликом:
  - Models (`/settings/models`) — LLM-провайдеры и tier matrix
  - Prompts (`/settings/prompts`) — редактор 12 промптов стадий pipeline
  - Subtitles (`/settings/subtitles`) — стили субтитров и live preview
  - Profiles (`/settings/profiles`) — редактор 5 профилей обработки
  - Performance (`/settings/performance`) — coherence validator, scaling reducer caps
  - Brand (`/settings/brand`) — логотип, водяные знаки, бренд-цвета
  - Connections (`/settings/connections`) — YouTube OAuth и Instagram токен
  - Post-production (`/settings/post-production`) — B-roll, видеоэффекты, музыка

Страницы настроек подробно описаны в разделе 6.

## 6. Настройки

Все страницы настроек доступны через sidebar → Settings. Изменения применяются без перезапуска backend — они сохраняются через `runtime_settings_store` или в соответствующие таблицы SQLite и вступают в силу при следующем job.

---

### 6.1 `/settings/models` — LLM-провайдеры

**Путь UI:** Settings → Models
**Backend routes:** `apps/backend/src/videomaker/api/routes/settings.py` — `GET /api/v1/settings/providers`, `GET/POST /api/v1/settings/models/selection`
**Связанные сервисы:** `services/llm_client.py`, `services/auto_config_advisor.py`, `services/auto_config_llm_fallback.py`, `services/rate_limiter.py`

Страница отображает доступные LLM-провайдеры и позволяет настроить, какая модель какого провайдера используется на каждом уровне tier matrix.

**Провайдеры и статус подключения:**

Индикатор «active» загорается зелёным, если соответствующий `*_API_KEY` найден в `.env`:

| Провайдер | Env-переменная | Статус без ключа |
|---|---|---|
| Gemini (primary) | `GEMINI_API_KEY` | не подключён |
| Anthropic (Claude) | `ANTHROPIC_API_KEY` | не подключён |
| OpenAI | `OPENAI_API_KEY` | не подключён |
| Zhipu Z.AI (GLM-5.1) | `ZHIPU_API_KEY` | не подключён |

**Hard switch LLM-провайдера (Pipeline provider):**

На странице `/settings/performance` есть селектор **Pipeline provider**:

- **Gemini (tier-матрица)** — дефолт, весь pipeline идёт через Gemini, tier-матрица берётся из режима работы (`llm_tier_profile`).
- **Zhipu GLM-5.1 (hard switch)** — вся Kartoziya 8-sub-stage цепочка уходит на `glm-5.1`. Режим работы ниже игнорируется. Требуется `ZHIPU_API_KEY` в `.env`.

Переключение сохраняется в `runtime_settings` без рестарта. Защита от регрессии: дефолт `gemini` — при откате pipeline работает как раньше.

**Ограничения GLM по сравнению с Gemini:**
- `response_schema` (строгий OpenAPI) не поддерживается — fallback на текстовую инструкцию в system промпте + `response_format={"type": "json_object"}`.
- Нет prompt caching — `cached_content` игнорируется.
- `thinking_budget > 0` маппится в `thinking={"type": "enabled"}` (GLM-5.1 reasoning mode).

**Tier matrix — три уровня производительности:**

Kartoziya 8-sub-stage pipeline распределяет вызовы по трём tier. Каждый tier можно переключить на другой провайдер.

| Tier | Характеристика | Используется в под-стадиях |
|---|---|---|
| **Pro** | дорогой, умный, один вызов на задачу | `canvas_builder`, `compose_story_script`, `generate_variants` |
| **Flash** | средний, быстрый | `reduce_and_rank`, `check_rhythm` |
| **Flash Lite** | дешёвый, массовый, параллельные вызовы | `compression`, `orchestrate_extraction` (6 агентов × N chunks) |

**Prompt caching для Anthropic:**

Если в качестве провайдера для tier Pro или Flash выбран Anthropic, `llm_client.py` автоматически добавляет заголовок `anthropic-beta: prompt-caching-2024-07-31` к запросам. Это позволяет кэшировать длинный повторяющийся префикс с Canvas-документом между вызовами в рамках одного job и существенно снижает расход токенов.

Prompt caching включается автоматически — отдельной настройки в UI нет. Процент cache hit отображается в логах backend при уровне `DEBUG`.

**API:**

```bash
# Список провайдеров и их статус
curl http://localhost:8000/api/v1/settings/providers | jq

# Текущий выбор моделей по tier
curl http://localhost:8000/api/v1/settings/models/selection | jq

# Переключить модель для tier
curl -X POST http://localhost:8000/api/v1/settings/models/selection \
  -H 'content-type: application/json' \
  -d '{"tier": "pro", "provider": "anthropic", "model": "claude-sonnet-4-5-20250929"}'
```

---

### 6.2 `/settings/prompts` — редактор промптов

**Путь UI:** Settings → Prompts
**Backend routes:** `apps/backend/src/videomaker/api/routes/settings.py` — `GET/POST /api/v1/settings/prompts`
**Связанные сервисы:** `services/prompt_store.py`, `services/prompts.py`, `services/prompts_data/`, `services/prompts_legacy.py`

Страница предоставляет доступ к 12 промптам под-стадий Kartoziya pipeline и дополнительным вспомогательным промптам. Хранятся в таблице `prompt_settings` SQLite.

**Архитектура seed-системы:**

При каждом старте сервера функция `prompt_store.seed()` (вызывается в lifespan `main.py`) проверяет таблицу `prompt_settings`. Для каждого ключа, которого ещё нет в таблице, вставляется дефолтное значение из `services/prompts_data/`. Операция идемпотентна: уже существующие записи не перезаписываются.

**Интерфейс:**

- Список ключей промптов слева (например, `pass1_thesis`, `pass3_virtual_cut`, `canvas_build`, `story_doctor`)
- Textarea-редактор справа с выбранным промптом
- Кнопка «Сохранить» — POST к `/api/v1/settings/prompts` с ключом и новым текстом
- Изменения вступают в силу при следующем job — уже запущенные jobs используют те версии промптов, которые были актуальны на момент старта stage `analyze`

**Откат промпта к дефолту:**

Удаление записи из БД без рестарта не применит дефолт — seed работает только при старте. Правильная процедура отката:

```sql
-- 1. Удалить кастомный промпт
DELETE FROM prompt_settings WHERE key = 'pass3_virtual_cut';
```

```bash
# 2. Перезапустить backend
# (run.sh перезапустит оба процесса через Ctrl+C + повторный запуск)
```

После рестарта `prompt_store.seed()` обнаружит отсутствие ключа и вставит дефолт из `services/prompts_data/`.

**Промпты и Kartoziya framework:**

Все 12 промптов написаны с учётом Kartoziya dramaturgy framework: они содержат ролевые инструкции для агентов, драматургические принципы отбора материала и указания по структуре 3-act arc. Детали — в разделе 9.

**API:**

```bash
# Получить все промпты
curl http://localhost:8000/api/v1/settings/prompts | jq

# Обновить конкретный промпт
curl -X POST http://localhost:8000/api/v1/settings/prompts \
  -H 'content-type: application/json' \
  -d '{"key": "pass3_virtual_cut", "value": "Ты монтажёр. Собери рилс из фрагментов..."}'
```

---

### 6.3 `/settings/subtitles` — стили субтитров

**Путь UI:** Settings → Subtitles
**Backend routes:** `apps/backend/src/videomaker/api/routes/settings.py` — `GET /api/v1/settings/subtitle_presets`, `POST /api/v1/settings/subtitle_presets`, `PUT /api/v1/settings/subtitle_presets/{id}`, `DELETE /api/v1/settings/subtitle_presets/{id}`
**Связанные сервисы:** `services/subtitles.py`, `services/subtitle_styles.py`, `services/subtitle_store.py`, `services/font_scanner.py`

3-колоночный редактор: список пресетов | форма стиля | live preview.

**Встроенные пресеты:**

4 пресета засеиваются через `subtitle_store` при старте сервера (TikTok, классический, мини, крупный CTA-стиль). Они доступны только для чтения — удалить их через UI нельзя. Пользователь может создавать неограниченное количество собственных пресетов.

**Параметры стиля:**

| Параметр | Тип | Описание |
|---|---|---|
| `anchor` | `top` / `center` / `bottom` | вертикальная точка привязки текста |
| `offset_px` | int | смещение от точки привязки в пикселях |
| `font` | string | название шрифта (сканируется `font_scanner.py`) |
| `size` | int | размер шрифта в пикселях |
| `weight` | `normal` / `bold` | насыщенность |
| `primary_color` | hex | цвет текста |
| `outline_color` | hex | цвет обводки |
| `outline_width` | float | толщина обводки в пикселях |
| `background` | bool | подложка за текстом (`BorderStyle=3` в ASS) |
| `fit_mode` | `fit` / `fill` | вписывание кадра в letterbox или полный кадр |

**Логика позиционирования:**

| anchor | fit_mode | offset_px | поведение |
|---|---|---|---|
| `bottom` | `fill` | 0–300 | отступ от нижнего края кадра |
| `top` | `fill` | 0–300 | отступ от верхнего края кадра |
| `bottom` | `fit` | 1–150 | отступ внутрь letterbox от нижней границы видео-зоны |
| `top` | `fit` | 1–150 | отступ внутрь letterbox от верхней границы видео-зоны |
| `center` | `fill` | 0–300 | сдвиг от центра кадра |
| `center` | `fit` | игнорируется | текст всегда по центру |

Live preview в правой колонке — pixel-accurate: использует ту же логику позиционирования, что libass при burn-in субтитров в рендере.

**ASS и BorderStyle:**

При `background: true` ASS-файл генерируется с `BorderStyle=3` — это режим непрозрачной подложки за текстом вместо обводки. Цвет подложки вычисляется автоматически (полупрозрачный чёрный).

**Шрифты:**

`font_scanner.py` сканирует системные шрифты macOS и возвращает список доступных. Последний выбранный шрифт сохраняется в `localStorage` браузера.

**API:**

```bash
# Список пресетов
curl -s http://localhost:8000/api/v1/settings/subtitle_presets | jq

# Создание пресета
curl -X POST http://localhost:8000/api/v1/settings/subtitle_presets \
  -H 'content-type: application/json' \
  -d '{
    "name": "Мой стиль",
    "style": {
      "anchor": "bottom", "offset_px": 160, "font": "Inter",
      "size": 70, "weight": "bold", "primary_color": "#FFFFFF",
      "outline_color": "#000000", "outline_width": 3.0,
      "background": false
    },
    "is_default": false
  }'

# Job с inline-стилем (минует таблицу пресетов)
curl -F 'file=@video.mp4' \
  -F 'subtitle_style_inline={"anchor":"top","offset_px":30,"font":"Arial","primary_color":"#FFFFFF"}' \
  http://localhost:8000/api/v1/jobs
```

---

### 6.4 `/settings/profiles` — 5 профилей обработки

**Путь UI:** Settings → Profiles
**Backend routes:** `apps/backend/src/videomaker/api/routes/settings.py` — `GET/POST /api/v1/settings/profiles`
**Связанные сервисы:** `services/profile_detector.py`, `services/profile_masks.py`, `services/runtime_settings_store.py`, `services/pipeline_mode.py`

5 профилей задают разные маски параметров pipeline под разные типы исходного контента.

**Профили:**

| Профиль | Описание | Акцент маски |
|---|---|---|
| **Лектор** | одна говорящая голова перед камерой | минимум B-roll, акцент на смысловые тезисы |
| **Интервью** | 2+ собеседника | приоритет конфликту и диалогу между спикерами |
| **Подкаст** | аудио-центричный формат | больше цитат, меньше динамики |
| **Скринкаст** | запись экрана | активные smart zoom на курсор, дейктические слова |
| **Универсал** | fallback | автодетекция через `profile_detector.py` |

**Детектирование профиля:**

`profile_detector.py` использует эвристики (соотношение кадров с лицами по данным `face_tracker.py`, наличие курсора в кадрах скринкаста) для автоматического выбора профиля при режиме «Универсал». Результат детектирования логируется в events job.

**Override через runtime_settings:**

Пользователь может переопределить отдельные параметры профиля без изменения самого профиля. Переопределения хранятся в `runtime_settings`. При создании job pipeline резолвит профиль и применяет override один раз в начале обработки (`detect_pipeline_mode`) — после этого маска заморожена до конца job.

**Редактор в UI:**

- Список профилей слева
- Редактор параметров справа — отображает текущие значения с возможностью задать override
- При сбросе override восстанавливается дефолтная маска профиля из `profile_masks.py`

**API:**

```bash
# Получить все профили
curl http://localhost:8000/api/v1/settings/profiles | jq

# Установить override для профиля
curl -X POST http://localhost:8000/api/v1/settings/profiles \
  -H 'content-type: application/json' \
  -d '{"profile": "podcast", "overrides": {"broll_enabled": false, "target_reel_count": 8}}'
```

---

### 6.5 `/settings/performance` — производительность и флаги pipeline

**Путь UI:** Settings → Performance
**Backend routes:** `apps/backend/src/videomaker/api/routes/settings.py` — `GET/POST /api/v1/settings/performance`
**Связанные сервисы:** `services/reducer.py`, `services/cross_chunk_reducer.py`, `services/coherence_validator.py`, `services/runtime_settings_store.py`

Страница управляет флагами, которые влияют на качество отбора рилсов и расход токенов.

**Arc-Coherence Validator:**

Проверяет, что отобранные кандидаты образуют связную драматургическую дугу.

| Режим | Поведение |
|---|---|
| `off` | валидатор отключён; все candidates проходят дальше без проверки |
| `reject` | отклоняет рилсы, не прошедшие coherence check; строгий режим, может уменьшить итоговое количество рилсов |
| `resort` | сортирует по coherence score, оставляет топ; мягкий режим, количество рилсов не меняется (default) |

Порог срабатывания (`coherence_threshold`) задаётся числом от 0 до 1. Значение по умолчанию откалибровано на типичных подкастах. Если валидатор отклоняет слишком много рилсов — снижайте порог или переключайте в режим `resort`.

**Scaling Reducer Caps:**

Предотвращают взрыв токенов при обработке длинных видео. До введения этих ограничений хардкод `MAX_RANKED_ITEMS=60` создавал регрессию: для 2.5-часового видео генерировалось 110 candidates, но выживало только 61.

| Длина видео | cap candidates | cap final ranked |
|---|---|---|
| ~ 30 минут | 60 | 80 |
| ~ 2.5 часа | 300 | 375 |

Значения интерполируются линейно для промежуточных длительностей.

**Cross-Chunk Reducer:**

Дополнительная проверка согласованности между candidate moments из разных chunk'ов транскрипта.

| Параметр | Значения | Описание |
|---|---|---|
| `enabled` | bool | включить / выключить |
| `strictness` | `low` / `medium` / `high` | чувствительность к противоречиям между chunks |

При `high` strictness агрессивно удаляются кандидаты, которые противоречат или дублируют кандидатов из других chunks. Рекомендуется для видео с повторяющимися тезисами (длинные лекции, нарративные подкасты).

**Temporal Dedup:**

Удаляет сегменты, пересекающиеся по времени в исходнике. Фикс бага, при котором одна и та же фраза попадала в два разных рилса.

| Параметр | Описание |
|---|---|
| `enabled` | включить / выключить (рекомендуется держать включённым) |
| `overlap_threshold_s` | минимальный overlap в секундах для признания сегментов дублями (дефолт: 0.5) |

**Reducer Ensemble:**

Запускает ранжирование N раз и агрегирует результаты голосованием.

| Параметр | Описание |
|---|---|
| `ensemble_size` | количество запусков (1 = ensemble отключён) |
| `veto_threshold` | минимальное число «против» для исключения кандидата из финального списка |

Ensemble повышает стабильность результата на неоднозначном материале, но увеличивает расход токенов пропорционально `ensemble_size`.

**API:**

```bash
# Получить текущие настройки performance
curl http://localhost:8000/api/v1/settings/performance | jq

# Обновить
curl -X POST http://localhost:8000/api/v1/settings/performance \
  -H 'content-type: application/json' \
  -d '{
    "coherence_mode": "resort",
    "coherence_threshold": 0.4,
    "cross_chunk_reducer_enabled": true,
    "cross_chunk_strictness": "medium",
    "temporal_dedup_enabled": true,
    "temporal_dedup_overlap_threshold_s": 0.5,
    "ensemble_size": 1,
    "veto_threshold": 2
  }'
```

---

### 6.6 `/settings/brand` — брендинг

**Путь UI:** Settings → Brand
**Backend routes:** `apps/backend/src/videomaker/api/routes/settings.py` — `GET/POST /api/v1/settings/brand`
**Связанные сервисы:** `services/asset_store.py`, `services/runtime_settings_store.py`

Страница управляет визуальными брендинговыми элементами, которые накладываются на готовые рилсы.

**Логотип (водяной знак):**

- Загрузка SVG или PNG через file picker
- Файл сохраняется в `data/` через `asset_store.py`
- Позиционирование: выбор угла кадра (`top-left` / `top-right` / `bottom-left` / `bottom-right`) + offset в пикселях по X и Y
- Прозрачность логотипа задаётся отдельным слайдером (0–100 %)
- Водяной знак накладывается через `filter_graph_builder.py` в стадии `render` — до финального H.265 encode

**Брендовые цвета:**

- Primary color и Accent color в формате hex
- Primary используется в CTA-плашках (нижние текстовые баннеры рилса)
- Accent используется для выделения слов в субтитрах в стилях с `subtitle_accent: true`

**Параметры сохраняются в `runtime_settings`** и применяются при следующем job без перезапуска.

**API:**

```bash
# Получить текущие настройки бренда
curl http://localhost:8000/api/v1/settings/brand | jq

# Обновить настройки без замены файла логотипа
curl -X POST http://localhost:8000/api/v1/settings/brand \
  -H 'content-type: application/json' \
  -d '{
    "logo_position": "bottom-right",
    "logo_offset_x": 40,
    "logo_offset_y": 40,
    "logo_opacity": 70,
    "primary_color": "#1A1A2E",
    "accent_color": "#E94560"
  }'

# Загрузить новый логотип (multipart)
curl -X POST http://localhost:8000/api/v1/settings/brand \
  -F 'logo=@logo.png' \
  -F 'logo_position=bottom-right' \
  -F 'logo_offset_x=40' \
  -F 'logo_offset_y=40' \
  -F 'logo_opacity=70'
```

---

### 6.7 `/settings/connections` — OAuth интеграции

**Путь UI:** Settings → Connections
**Backend routes:** `apps/backend/src/videomaker/api/routes/connections.py`
**Связанные сервисы:** `services/youtube_oauth.py`, `services/instagram_publisher.py`, `services/connections_store.py`

Страница управляет токенами публикации для Instagram и YouTube. Все токены хранятся в таблице `connections` SQLite — они не попадают в `.env` и не видны в логах.

**YouTube — OAuth 2.0:**

1. Нажать «Подключить YouTube» — браузер перенаправляется на Google OAuth consent screen
2. Авторизоваться под нужным аккаунтом, выдать разрешение `youtube.upload`
3. Google редиректит на callback route (`/api/v1/connections/youtube/callback`)
4. Backend сохраняет refresh token в таблице `connections`
5. На странице отображается email подключённого аккаунта и статус «Подключён»

Кнопка «Отключить» удаляет запись из `connections`. После этого публикация в YouTube недоступна до повторной авторизации.

**Instagram — Graph API long-lived token:**

Instagram не предоставляет стандартный OAuth flow для незарегистрированных приложений. Подключение выполняется вручную:

1. Убедитесь, что у вас Business Account, связанный с Facebook Page
2. Получите long-lived token через Facebook Developer Portal (инструкция — в tooltip рядом с полем)
3. Вставьте токен в поле и нажмите «Сохранить»

Ограничения Graph API:
- Максимум 25 постов в день
- Размер файла — до 100 МБ (проверяется перед публикацией)
- Требуется видео в формате MP4 H.264

**Статус подключений:**

```bash
# Проверить статус всех подключений
curl http://localhost:8000/api/v1/connections/status | jq
```

**API:**

```bash
# Начать YouTube OAuth flow (откроется в браузере)
curl -L http://localhost:8000/api/v1/connections/youtube/connect

# Сохранить Instagram токен
curl -X POST http://localhost:8000/api/v1/connections/instagram/token \
  -H 'content-type: application/json' \
  -d '{"token": "EAAxxxxxxxxx..."}'

# Отключить провайдер
curl -X DELETE http://localhost:8000/api/v1/connections/youtube
curl -X DELETE http://localhost:8000/api/v1/connections/instagram
```

---

### 6.8 `/settings/post-production` — пост-продакшн слои

**Путь UI:** Settings → Post-production
**Backend routes:** `apps/backend/src/videomaker/api/routes/post_production.py` — `GET/POST /api/v1/post_production/config`
**Связанные сервисы:** `services/post_production_store.py`, `services/broll/`, `services/video_effects/`, `services/adaptive_leveller.py`, `services/audio_normalizer.py`, `services/zoom_planner.py`

Каждая фича на этой странице — toggle on/off в соответствии с философией проекта (раздел 1.5). Включённые слои применяются поверх базового рилса в стадии `render`.

**B-roll insertion:**

Вставка изображений или коротких видеоклипов на смысловых паузах рилса.

- `services/broll/index.py` + `services/broll/retriever.py` — индекс и ретривер B-roll материала
- `services/broll/inserter.py` — вставка клипа в готовый рилс в нужной временной точке
- Требует Vision Layer для оценки совместимости B-roll с визуальным контекстом кадра
- Параметры: минимальная длительность паузы для вставки, источник B-roll (загруженные файлы / стоковый индекс)

**Video effects:**

Реестр визуальных фильтров, применяемых к финальному рилсу.

- Текущий набор: ч/б (`services/video_effects/bw.py`)
- Регистрация новых фильтров — через `services/video_effects/registry.py` (добавьте Python-файл с функцией `apply(filter_graph)` и зарегистрируйте в реестре)
- Фильтры применяются через `filter_graph_builder.py` — в том же проходе ffmpeg, что и субтитры и zoom

**Smart Zoom:**

Ken Burns, punch-in и дейктический zoom. Подробная документация — раздел 8 «Vision Layer».

На этой странице управляется включение по типу контента:

| Тип | Описание |
|---|---|
| Talking head | плавный zoom на лицо спикера через `zoom_planner.py` |
| Screencast | zoom на курсор + zoom на области при произнесении дейктических слов (`deictic_zoom.py`) |
| Стоп-кадры | Ken Burns-эффект для статичных кадров |

**Loudness normalization:**

EBU R128 нормализация громкости через `audio_normalizer.py`.

| Параметр | Дефолт | Описание |
|---|---|---|
| `target_lufs` | -16 LUFS | целевой уровень громкости (стандарт Instagram/YouTube Reels) |
| `tolerance_lu` | 1.0 LU | допустимое отклонение без повторной нормализации |

`adaptive_leveller.py` применяется дополнительно для выравнивания локальных пиков речи внутри рилса.

**Music / soundtrack:**

Подложка фоновой музыки под рилс.

- Выбор трека из внутренней библиотеки
- Duck под речь: автоматическое приглушение музыки в моменты, когда есть активная речь (по данным VAD из `services/vad.py`)
- Fade in / fade out на начало и конец рилса

**Split-screen (вертикальный реакшн-формат 9:16):**

Верхняя половина финального рилса — нарезанный pipeline'ом контент, нижняя — произвольное companion-видео, загруженное как asset (аналогично intro/outro). Использование: реакшн-видео, где снизу автор комментирует, а сверху идёт нарезка источника.

- **Как настроить в пресете:** Settings → Post-production → Сплит-скрин:
  - Загрузить companion-видео в раздел assets (как intro/outro).
  - Включить toggle «Сплит-скрин», выбрать companion из списка assets.
  - Режим: Crop-to-fill (без чёрных полос, кадр обрезается по краям) / Fit (letterbox, виден весь кадр) / Вручную (ручные transforms обоих слоёв через drag+resize).
  - Split ratio — доля верхней половины от 20 до 80 % (игнорируется в mode="Вручную").
  - Встроенный preview-редактор показывает итоговый композит. В mode="Вручную" можно тащить и масштабировать панели.

- **Per-job override:** UploadWizard Step 5 имеет три варианта — «По пресету / Включить / Выключить» — если пресет содержит companion_asset. Даёт возможность один и тот же пресет использовать в обоих режимах без дублирования.

- **Поведение рендера:**
  - Audio всегда берётся только с рилса (верх). Companion воспроизводится mute'ом.
  - Companion короче рилса → loop через `-stream_loop -1`.
  - Companion длиннее рилса → обрезается концом рилса (`-shortest`).
  - Финальный canvas — 1080×1920, два overlay'а по вычисленным прямоугольникам.

- **Архитектура:** split-screen — отдельный post-process ffmpeg pass в `services/split_screen.py`, запускается в pipeline после `ProjectRenderer.render_many()`. Не трогает основной `filter_graph_builder` (zero regression risk). Конфиг живёт в `PostProductionConfig.split_screen` (SplitScreenConfig snapshot) + `PostProductionPresetRow.companion_asset_id` FK.

**API:**

```bash
# Получить текущую конфигурацию post-production
curl http://localhost:8000/api/v1/post_production/config | jq

# Обновить конфигурацию
curl -X POST http://localhost:8000/api/v1/post_production/config \
  -H 'content-type: application/json' \
  -d '{
    "broll_enabled": false,
    "video_effects": ["bw"],
    "smart_zoom_enabled": true,
    "smart_zoom_types": ["talking_head", "screencast"],
    "loudness_normalization_enabled": true,
    "target_lufs": -16,
    "tolerance_lu": 1.0,
    "music_enabled": false
  }'

# Thumbnail companion asset для превью в UI
curl "http://localhost:8000/api/v1/post_production/assets/{asset_id}/thumbnail?time_sec=0.5" -o thumb.png
```

## 7. API Reference

API сервера запускается на `http://127.0.0.1:8000` (настраивается через `APP_HOST` и `APP_PORT` в `.env`). Все маршруты префиксированы `/api/v1`. Интерактивная документация с Swagger UI — <http://127.0.0.1:8000/docs>, OpenAPI JSON — `/openapi.json`. Все POST/PUT/PATCH ожидают JSON тело, кроме upload (`POST /jobs`) и asset-upload (`POST /post_production/assets`) — там multipart/form-data.

### 7.1 Health

Router: `apps/backend/src/videomaker/api/routes/health.py`

| Method | Path | Описание |
|--------|------|----------|
| GET | `/api/v1/health` | Проверка работоспособности сервера |

Примеры:

```bash
curl http://127.0.0.1:8000/api/v1/health
# → {"status": "ok", ...}
```

---

### 7.2 Jobs

Router: `apps/backend/src/videomaker/api/routes/jobs.py`

| Method | Path | Описание |
|--------|------|----------|
| GET | `/api/v1/jobs` | Список всех jobs → `list[JobRead]` |
| POST | `/api/v1/jobs` | Создать job (multipart: `file`, `profile?`, `subtitle_preset_id?`, `subtitle_style_inline?`, ...) → `JobRead` (201) |
| GET | `/api/v1/jobs/{job_id}` | Детали job |
| PATCH | `/api/v1/jobs/{job_id}/rename` | Переименовать job |
| PATCH | `/api/v1/jobs/{job_id}/profile` | Сменить профиль job-а |
| GET | `/api/v1/jobs/{job_id}/profile/suggestion` | Предложение профиля от детектора |
| POST | `/api/v1/jobs/{job_id}/auto-analyze` | Auto-analyze для AutoConfig Advisor |
| PATCH | `/api/v1/jobs/{job_id}/auto-config` | Применить auto-config |
| DELETE | `/api/v1/jobs/{job_id}/auto-config` | Сбросить auto-config |
| GET | `/api/v1/jobs/{job_id}/artifacts` | Список артефактов job |
| GET | `/api/v1/jobs/{job_id}/thumbnail` | Thumbnail первого кадра |
| GET | `/api/v1/jobs/{job_id}/stream` | SSE поток прогресса (event-stream) |
| GET | `/api/v1/jobs/{job_id}/reels/{reel_id}/subtitles` | ASS файл субтитров рилса |
| PATCH | `/api/v1/jobs/{job_id}/reels/{reel_id}` | Редактирование рилса |
| POST | `/api/v1/jobs/{job_id}/reels/{reel_id}/export` | Экспорт рилса (платформа-specific) |
| DELETE | `/api/v1/jobs/{job_id}` | Удалить job и все артефакты |

Примеры:

```bash
# Загрузить видео и создать job
curl -F 'file=@podcast.mp4' \
     -F 'profile=podcast' \
     -F 'subtitle_preset_id=tiktok_white' \
     http://127.0.0.1:8000/api/v1/jobs
# → {"id": "job_abc", "status": "queued", ...}

# Детали job
curl http://127.0.0.1:8000/api/v1/jobs/abc | jq

# Список всех jobs
curl http://127.0.0.1:8000/api/v1/jobs | jq

# Удалить job
curl -X DELETE http://127.0.0.1:8000/api/v1/jobs/abc
```

SSE поток прогресса (JavaScript):

```javascript
const es = new EventSource('http://127.0.0.1:8000/api/v1/jobs/abc/stream');
es.addEventListener('progress', (e) => {
  const data = JSON.parse(e.data);
  console.log(`Stage ${data.stage}: ${data.progress}% — ${data.message}`);
});
es.addEventListener('done', (e) => {
  es.close();
});
```

SSE поток прогресса (curl, для тестирования):

```bash
# -N (no buffering) обязательно для streaming
curl -N http://127.0.0.1:8000/api/v1/jobs/abc/stream
```

---

### 7.3 Settings

Router: `apps/backend/src/videomaker/api/routes/settings.py`

| Method | Path | Описание |
|--------|------|----------|
| GET | `/api/v1/settings/performance` | Получить `PerformanceSettings` |
| PUT | `/api/v1/settings/performance` | Обновить performance-настройки |
| GET | `/api/v1/settings/vision` | Получить `VisionSettingsResponse` |
| PUT | `/api/v1/settings/vision` | Обновить vision-настройки |
| GET | `/api/v1/settings/models` | `ModelsInfo` — провайдеры и tier matrix |
| GET | `/api/v1/settings/prompts` | Список промптов |
| GET | `/api/v1/settings/prompts/{key}` | Конкретный промпт по ключу |
| PUT | `/api/v1/settings/prompts/{key}` | Обновить промпт |
| GET | `/api/v1/settings/fonts` | Доступные шрифты |
| POST | `/api/v1/settings/fonts/refresh` | Пересканировать системные шрифты |
| GET | `/api/v1/settings/subtitle_presets` | Список пресетов субтитров |
| GET | `/api/v1/settings/subtitle_presets/{id}` | Конкретный пресет субтитров |
| POST | `/api/v1/settings/subtitle_presets` | Создать пресет субтитров |
| PUT | `/api/v1/settings/subtitle_presets/{id}` | Обновить пресет субтитров |
| DELETE | `/api/v1/settings/subtitle_presets/{id}` | Удалить пресет субтитров |
| GET | `/api/v1/settings/profiles` | Список масок профилей |
| GET | `/api/v1/settings/profiles/{profile}` | Маска одного профиля |
| PUT | `/api/v1/settings/profiles/{profile}` | Обновить маску профиля |
| DELETE | `/api/v1/settings/profiles/{profile}` | Сбросить профиль к дефолту |

Примеры:

```bash
# Обновить performance-настройки
curl -X PUT http://127.0.0.1:8000/api/v1/settings/performance \
  -H 'content-type: application/json' \
  -d '{
    "coherence_validator_mode": "resort",
    "cross_chunk_reducer_enabled": true,
    "cross_chunk_reducer_strictness": "medium"
  }'

# Список пресетов субтитров
curl -s http://127.0.0.1:8000/api/v1/settings/subtitle_presets | jq

# Список профилей
curl http://127.0.0.1:8000/api/v1/settings/profiles | jq

# Сбросить профиль к дефолту
curl -X DELETE http://127.0.0.1:8000/api/v1/settings/profiles/podcast
```

---

### 7.4 Files

Router: `apps/backend/src/videomaker/api/routes/files.py`

| Method | Path | Описание |
|--------|------|----------|
| GET | `/api/v1/files/{job_id}/{kind}/{name}` | Доступ к артефакту (kind ∈ {audio, text, reels, subs}, name — имя файла) |

Примеры:

```bash
# Скачать готовый рилс
curl -O http://127.0.0.1:8000/api/v1/files/abc/reels/reel_01.mp4

# Скачать ASS субтитры
curl -O http://127.0.0.1:8000/api/v1/files/abc/subs/reel_01.ass
```

---

### 7.5 Schedule

Router: `apps/backend/src/videomaker/api/routes/schedule.py`

| Method | Path | Описание |
|--------|------|----------|
| GET | `/api/v1/schedule` | Список `scheduled_posts` |
| POST | `/api/v1/schedule` | Создать scheduled post (201) |
| GET | `/api/v1/schedule/{post_id}` | Один пост |
| DELETE | `/api/v1/schedule/{post_id}` | Отменить пост (204) |

Примеры:

```bash
# Запланировать публикацию
curl -X POST http://127.0.0.1:8000/api/v1/schedule \
  -H 'content-type: application/json' \
  -d '{
    "job_id": "abc",
    "reel_id": "reel_01",
    "platform": "youtube",
    "scheduled_at": "2026-04-20T18:00:00+03:00",
    "title": "Название видео",
    "description": "Описание",
    "tags": ["тег1", "тег2"]
  }'

# Список запланированных публикаций
curl http://127.0.0.1:8000/api/v1/schedule | jq

# Отменить пост
curl -X DELETE http://127.0.0.1:8000/api/v1/schedule/post_123
```

---

### 7.6 Connections

Router: `apps/backend/src/videomaker/api/routes/connections.py`

| Method | Path | Описание |
|--------|------|----------|
| GET | `/api/v1/connections` | Список подключений |
| GET | `/api/v1/connections/youtube/status` | Статус YouTube подключения |
| POST | `/api/v1/connections/youtube/connect` | Начать OAuth → `ConnectStartResponse` с redirect URL |
| GET | `/api/v1/connections/youtube/callback` | OAuth callback (вызывается Google автоматически) |
| DELETE | `/api/v1/connections/youtube` | Отключить YouTube (204) |

Примеры:

```bash
# 1. Начать OAuth
curl -X POST http://127.0.0.1:8000/api/v1/connections/youtube/connect
# → {"redirect_url": "https://accounts.google.com/o/oauth2/v2/auth?..."}

# 2. Открыть redirect_url в браузере, авторизоваться.
# Google редиректит на /api/v1/connections/youtube/callback с code.
# Сервер обменивает code на токены, сохраняет в connections.

# 3. Проверить статус
curl http://127.0.0.1:8000/api/v1/connections/youtube/status
# → {"connected": true, "email": "...", ...}

# Отключить YouTube
curl -X DELETE http://127.0.0.1:8000/api/v1/connections/youtube
```

---

### 7.7 Post-production

Router: `apps/backend/src/videomaker/api/routes/post_production.py`

| Method | Path | Описание |
|--------|------|----------|
| GET | `/api/v1/post_production/assets` | Список video assets (логотипы, музыка, ...) |
| GET | `/api/v1/post_production/assets/{asset_id}` | Один asset |
| POST | `/api/v1/post_production/assets` | Загрузить asset (multipart/form-data) |
| DELETE | `/api/v1/post_production/assets/{asset_id}` | Удалить asset |
| GET | `/api/v1/post_production/presets` | Список post-production пресетов |
| GET | `/api/v1/post_production/presets/default` | Дефолтный пресет |
| GET | `/api/v1/post_production/presets/{preset_id}` | Один пресет |
| POST | `/api/v1/post_production/presets` | Создать пресет |
| PUT | `/api/v1/post_production/presets/{preset_id}` | Обновить пресет |
| DELETE | `/api/v1/post_production/presets/{preset_id}` | Удалить пресет |

Примеры:

```bash
# Загрузить логотип
curl -F 'file=@logo.png' \
     -F 'kind=logo' \
     http://127.0.0.1:8000/api/v1/post_production/assets

# Список assets
curl http://127.0.0.1:8000/api/v1/post_production/assets | jq

# Дефолтный пресет
curl http://127.0.0.1:8000/api/v1/post_production/presets/default | jq
```

---

### 7.8 Proxies

Router: `apps/backend/src/videomaker/api/routes/proxies.py`

| Method | Path | Описание |
|--------|------|----------|
| GET | `/api/v1/proxies` | Список прокси-файлов (кэш для длинных видео) |
| DELETE | `/api/v1/proxies/cleanup` | Массовая очистка старых прокси |
| DELETE | `/api/v1/proxies/{sha256}` | Удалить конкретный прокси по SHA256 ключу |

Примеры:

```bash
# Список прокси
curl http://127.0.0.1:8000/api/v1/proxies | jq

# Очистить все устаревшие прокси
curl -X DELETE http://127.0.0.1:8000/api/v1/proxies/cleanup

# Удалить конкретный прокси
curl -X DELETE http://127.0.0.1:8000/api/v1/proxies/a1b2c3d4e5f6...
```

---

Полная интерактивная документация доступна через Swagger UI по адресу <http://127.0.0.1:8000/docs>. Машиночитаемая схема в формате OpenAPI 3.x — `/openapi.json`.

## 8. Vision Layer

### 8.1 Что такое Vision Layer

Локальный модуль визуального анализа на базе Moondream 2 GGUF — компактной quantized vision-language модели, работающей на CPU или Apple Silicon (Metal). Разработан в 6 фаз за 21 итерацию Ralph Loop: 340/340 тестов pass, 18 коммитов.

Зачем нужен Vision Layer:

- Проверка того, что рилс имеет визуальное подтверждение тезиса, а не только голосовое
- Smart zoom на ключевые элементы кадра: лицо говорящего, курсор на экране, указываемый объект
- Автоматический выбор обложки рилса по визуальному качеству
- Оценка совместимости travel/b-roll материала с содержанием рилса

Vision Layer включается через `.env`:

```bash
ENABLE_VISION=true
MOONDREAM_MODEL_PATH=/path/to/moondream-2b.gguf
```

При `ENABLE_VISION=false` (дефолт) весь слой пропускается, pipeline работает только на транскрипте. Это позволяет запустить основной поток без Moondream и без дополнительных зависимостей.

---

### 8.2 Phase 1 — Infrastructure

Базовые компоненты расположены в `apps/backend/src/videomaker/services/vision/`:

| Файл | Что делает |
|---|---|
| `model_manager.py` | Lazy-load Moondream GGUF. Потокобезопасный singleton. |
| `frame_cache.py` | Кэш извлечённых кадров (dedup по timestamp + sha256 исходника). |
| `rate_limiter.py` | Защита от OOM на 24 GB RAM — ограничивает количество одновременных inference. |
| `factory.py` | Выбор backend: `local` (Moondream GGUF) или `remote` (API fallback). |
| `moondream_local.py` | Обёртка над llama.cpp bindings для инференса. |
| `types.py` | Общие типы: `FrameAnalysis`, `VisionResult`, `ZoomHint` и др. |
| `base.py` | Абстрактный класс `VisionBackend` — интерфейс для local/remote реализаций. |
| `__init__.py` | Публичный экспорт модуля. |

---

### 8.3 Phase 2 — Visual Validator

- Файл: `apps/backend/src/videomaker/services/visual_validator.py`
- Запускается после Stage 4 (`reduce_and_rank`) pipeline
- Для каждого candidate moment извлекает кадры из видео и спрашивает Moondream: подтверждается ли тезис визуально
- Если тезис про конкретный объект или действие, а в кадре только говорящая голова — рилс помечается как `weak_visual_evidence`

Используется совместно с `coherence_validator` (см. раздел 6.5) для финального отбора рилсов. При `visual_validator_enabled: false` шаг пропускается без изменения логики pipeline.

---

### 8.4 Phase 3 — Multimodal Dramaturgy

- Файл: `apps/backend/src/videomaker/services/visual_evidence_agent.py`
- Vision-агент, дополняющий Kartoziya orchestrator (Stage 3 pipeline, раздел 4.3)
- При извлечении candidate moments агенты могут запросить visual-контекст кадра: что реально видно, есть ли персонаж, что он делает, какая эмоция
- Это повышает точность ранжирования: «виден плач» имеет больше веса, чем «слышен грустный тон»

Агент реализован как один из `AgentConfig` в registry Stage 5, запускается параллельно с другими extraction-агентами.

---

### 8.5 Phase 4 — Smart Zoom

Три стратегии zoom, включаемые отдельно для каждого типа контента:

| Стратегия | Файл | Когда применяется |
|---|---|---|
| Spring zoom | `services/spring_zoom_planner.py` | Плавный пружинящий zoom для talking head |
| Deictic zoom | `services/deictic_zoom.py` | Говорящий использует указательные слова + курсор/палец на экране — zoom на указываемую область |
| Zoom planner | `services/zoom_planner.py` | Общий оркестратор: выбирает стратегию по Vision-контексту |

Для скринкастов — детекция курсора:

- `services/cursor_detector.py` — template match + confidence score
- Deictic words (русский): «вот», «сюда», «тут», «здесь», «смотрите», «смотри», «видите», «посмотрите»

Для talking head:

- `services/face_tracker.py` — bbox лица + стабилизация между кадрами
- `services/eye_trace_continuity.py` — проверяет, что взгляд остаётся в кадре после crop/zoom

Детали реализации auto-zoom для скринкастов — `docs/screencast-zoom-research.md` (внутренний research-отчёт, 2026-04-18).

---

### 8.6 Phase 5 — Cover Selector

- Файл: `apps/backend/src/videomaker/services/cover_selector.py`
- Для каждого рилса выбирает лучший кадр как обложку

Критерии скоринга:

| Критерий | Метод |
|---|---|
| Резкость | Laplacian variance |
| Открытые глаза | `face_tracker` + ML-классификатор |
| Эмоциональная насыщенность | Moondream: анализ выражения лица |
| Отсутствие motion blur | Оценка по optical flow |
| Композиция | Rule of thirds: лицо в сетке 1/3 |

Выход: `cover.jpg` в директории `data/artifacts/<job_id>/reels/<reel_id>/` для каждого рилса.

---

### 8.7 Phase 6 — Travel / B-roll

Связан с `services/broll/` (index + retriever + inserter). Vision Layer оценивает семантическое соответствие B-roll кадра содержанию рилса:

- `services/composition_scorer.py` — скоринг визуальной композиции кандидатов B-roll
- `services/transition_chooser.py` — выбор типа перехода (cut / fade / whip / match cut) на основе визуального сходства соседних кадров

Интеграция с pipeline: `broll_scoring_enabled` в настройках включает вызов Vision Layer при подборе B-roll вставок.

---

### 8.8 Как включить и настроить

В файле `.env`:

```bash
ENABLE_VISION=true
MOONDREAM_MODEL_PATH=/Users/<you>/models/moondream-2b-q4_0.gguf
VISION_MAX_CONCURRENCY=2        # одновременных inference
VISION_FRAME_CACHE_SIZE_MB=2048 # размер кэша кадров в памяти
```

Через API — проверить текущие настройки:

```bash
curl http://127.0.0.1:8000/api/v1/settings/vision | jq
```

Доступные параметры:

| Параметр | Тип | Описание |
|---|---|---|
| `visual_validator_enabled` | `bool` | Включить проверку визуального подтверждения тезиса |
| `smart_zoom_mode` | `"off" \| "spring" \| "deictic" \| "auto"` | Стратегия zoom. `auto` — выбирается по контенту |
| `cover_selector_enabled` | `bool` | Автовыбор обложки рилса |
| `broll_scoring_enabled` | `bool` | Vision-скоринг при подборе B-roll |

Изменить параметр:

```bash
curl -X PATCH http://127.0.0.1:8000/api/v1/settings/vision \
  -H "Content-Type: application/json" \
  -d '{"smart_zoom_mode": "deictic"}'
```

---

### 8.9 Ограничения и риски

- Moondream 2B quantized работает быстро, но неточна на мелком тексте и мелких деталях экрана
- На 24 GB RAM при параллельно активном mlx-whisper — риск OOM; контролируется через `rate_limiter.py` (`VISION_MAX_CONCURRENCY`)
- Inference на каждый кадр — bottleneck; `frame_cache` обязателен и включён автоматически
- Отключай Vision Layer (`ENABLE_VISION=false`) для быстрого draft-режима или при нехватке RAM
- При `ENABLE_VISION=false` весь модуль не импортируется — нет зависимости от llama.cpp и `moondream_local.py`

## 9. Dramaturgy Framework

### 9.1 Что это за фреймворк

Dramaturgy Framework — подход к анализу долгого видео через лезвие драматургии вместо
«найди самые смешные моменты». Вместо поверхностного ранжирования по яркости или энергетике
система строит структурную карту проекта, затем запускает специализированных агентов, каждый
из которых ищет один тип драматургического материала.

Три ключевых слоя:

- **Canvas** — карта драматургической структуры проекта (темы, конфликты, персонажи, мотивы).
  Строится один раз Pro-моделью перед запуском агентов.
- **6 extraction-агентов в 2 волнах** — каждый агент специализируется на своём типе материала.
  Wave 1 ищет поверхностное (зацепки, эмоции, шутки), Wave 2 — скрытые смыслы (ирония, тезисы,
  мотивы), при этом видит что уже нашла Wave 1 и не дублирует.
- **Reducer + Story Doctor** — превращают сырые candidate moments в рабочий 3-act script с
  дедупликацией, ранжированием и проверкой драматургической дуги.

Методологический источник — Kartoziya dramaturgy framework. Название фигурирует в `pipeline.py`
как «Kartoziya 8-sub-stage pipeline» и отражает набор принципов: конфликт как движущая сила,
3-act arc, непредсказуемость через нарушение ожиданий.

---

### 9.2 Canvas — карта проекта

Файлы:
- `apps/backend/src/videomaker/services/canvas_builder.py` — построение canvas через LLM
- `apps/backend/src/videomaker/services/canvas_embedder.py` — embeddings для chunk-matching
- `apps/backend/src/videomaker/models/canvas.py` — Pydantic-модель `ProjectCanvas`

Canvas содержит структурные элементы проекта:

| Поле | Что хранит |
|---|---|
| `topics` | Темы — что обсуждается в видео |
| `theses` | Тезисы — что утверждается, ключевые идеи |
| `conflicts` | Конфликты — противоречия, несогласия, борьба идей |
| `personae` | Персонажи — говорящие лица и их роли |
| `motifs` | Мотивы — повторяющиеся образы и идеи |

Canvas строится Pro-моделью за один LLM-вызов на весь транскрипт проекта. Это дорого, но
критично: canvas используется всеми агентами Wave 2 как контекст для поиска скрытых смыслов.
Без canvas Wave 2 не знает, какие темы и конфликты вообще есть в материале.

---

### 9.3 6 агентов экстракции (AGENT_REGISTRY)

Полный реестр в `apps/backend/src/videomaker/services/agents/base.py`:

| Агент | Wave | Ищет | extra_fields | Strength field |
|---|---|---|---|---|
| `hook_hunter` | 1 | Крючки — моменты, цепляющие внимание в первые 3 секунды | `hook_type` | `strength` |
| `emotional_peak_finder` | 1 | Эмоциональные пики (смех, гнев, растроганность) | `emotion` | `intensity` |
| `humor_specialist` | 1 | Юмористические моменты, панчлайны, абсурд | `humor_type` | `funniness` |
| `dramatic_irony_scanner` | 2 | Драматическая ирония, противоречия между сказанным и подразумеваемым | `irony_type`, `pairs_with_theme_id` | `significance` |
| `thesis_extractor` | 2 | Чёткие тезисы-утверждения, которые стоят отдельного рилса | `thesis_type`, `summary` | `strength` |
| `motif_tracker` | 2 | Повторяющиеся мотивы — связывающие разные фрагменты видео | `role` | `significance` |

**Двухволновая схема:**

Wave 1 запускается первой. Reaction-экстракторы (`hook_hunter`, `emotional_peak_finder`,
`humor_specialist`) работают без extended reasoning и быстро покрывают очевидный материал.
Их evidence агрегируется в `coverage_summary` — карту того, что уже найдено по каждому чанку
и теме.

Wave 2 запускается после. Meaning-экстракторы (`dramatic_irony_scanner`, `thesis_extractor`,
`motif_tracker`) получают `coverage_summary` и работают с `thinking_budget=512` (extended
reasoning). Они видят, что Wave 1 уже обнаружила, и фокусируются на непокрытых чанках и темах,
избегая дублирования.

Это сочетание экономит токены (Wave 2 пропускает уже покрытые зоны) и повышает разнообразие
финальной подборки (нет дублей «смешного момента» от трёх агентов одновременно).

---

### 9.4 Reducer + Story Doctor

После экстракции pipeline проходит через несколько этапов постобработки:

**Reducer** (`services/reducer.py`)
Jaccard-дедупликация перекрывающихся candidate moments, затем Flash-ранжирование по
релевантности canvas. Опциональный ensemble (несколько прогонов ранжирования с veto threshold)
повышает стабильность результата при коротких транскриптах.

**Cross-chunk reducer** (`services/cross_chunk_reducer.py`)
Ищет противоречия между кандидатами из разных чанков: если говорящий утверждает X в первой
трети и не-X в третьей, один из этих рилсов содержит ложный тезис и должен быть отфильтрован
или помечен.

**Coherence validator** (`services/coherence_validator.py`)
Строит score по drama-arc согласованности набора кандидатов. Режимы: `off` (выключен),
`reject` (слабые кандидаты удаляются), `resort` (пересортировка без удаления). Настраивается
в `/settings/performance` через `PerformanceSettings`.

**Story Doctor** (`services/story_doctor.py`)
Pro-вызов, собирает 3-act arc для каждого рилса: setup → conflict → resolution. Проверяет
что у рилса есть завязка и развязка, а не просто «яркий момент» без контекста.

**Rhythm check** (`services/rhythm_check.py`)
Flash + эвристика на middle-sag — провал середины рилса. Выявляет кандидатов, у которых
первая и последняя трети сильные, а середина пустая.

---

### 9.5 Как агенты используют промпты

Каждый агент имеет `prompt_key` — ключ в `prompt_store` / SQLite-таблице `prompt_settings`.
Seed-промпты находятся в `apps/backend/src/videomaker/services/prompts_data/`.

Промпты разделены по двум осям:

- **Tier-specific** — отдельные варианты под Pro / Flash / Flash Lite, оптимизированные под
  возможности конкретной модели (Pro — reasoning-heavy, Flash Lite — краткий шаблон)
- **Stage-specific** — по одному промпту на каждую под-стадию и агента: `compression`,
  `canvas_builder`, `hook_hunter`, `thesis_extractor` и т.д.

Отредактировать промпт можно через UI `/settings/prompts` или напрямую через API:

```
PATCH /api/v1/settings/prompts/{key}
```

(см. раздел 7.3 для полной документации API промптов).

Для отката промпта к дефолтному значению (seed из `prompts_data/`):

```bash
sqlite3 data/videomaker.db "DELETE FROM prompt_settings WHERE key='thesis_extractor';"
```

После перезапуска бэкенда `lifespan` пересеет промпт из seed-файла.

---

### 9.6 Как добавить собственного агента

Для разработчиков, форкающих проект. Минимальный шаблон:

```python
# apps/backend/src/videomaker/services/agents/base.py

AGENT_REGISTRY["my_custom_agent"] = AgentConfig(
    name="my_custom_agent",
    prompt_key=PromptKey.my_custom_agent,  # добавить в PromptKey enum
    extra_fields=("my_field",),
    min_strength_field="strength",
    thinking_budget=512,  # только если Wave 2 с extended reasoning
    wave=2,
)
```

Дополнительные шаги:

1. Добавить `my_custom_agent` в `PromptKey` enum (`models/prompt_key.py`)
2. Создать seed-промпт в `services/prompts_data/my_custom_agent.py` (или `.yaml` — по аналогии
   с существующими)
3. Перезапустить бэкенд — `lifespan` засеит новый промпт в БД автоматически

После этого оркестратор (`pipeline.py`) начнёт запускать агента наравне с 6 встроенными, в
правильной волне согласно полю `wave`.

---

### 9.7 Связь с пайплайном

Dramaturgy Framework входит в pipeline как stage 3 (`orchestrate_extraction`) внутри общей
стадии `analyze`. Полный поток стадий описан в разделе 4.3.

Поток внутри стадии `analyze`:

```
Canvas (stage 2, Pro)
        │
        ▼
AGENT_REGISTRY Wave 1 (hook_hunter, emotional_peak_finder, humor_specialist)
  └── 3 агента × N chunks, параллельно, без reasoning
        │
        ▼
coverage_summary (агрегация находок Wave 1)
        │
        ▼
AGENT_REGISTRY Wave 2 (dramatic_irony_scanner, thesis_extractor, motif_tracker)
  └── 3 агента × N chunks, thinking_budget=512, видят coverage_summary
        │
        ▼
candidate_moments (raw pool)
        │
        ├── Cross-chunk reducer
        ├── Jaccard dedup + Flash rank (Reducer)
        ├── Coherence validator (off / reject / resort)
        ├── Story Doctor (Pro, 3-act arc)
        └── Rhythm check (Flash + эвристика)
                │
                ▼
           Variants (финальные рилсы)
```

Параллелизм внутри каждой волны контролируется `rate_limiter.py`. При нехватке токенов
(`thinking_budget=512` × N агентов × M чанков) Wave 2 может быть узким местом по скорости —
в этом случае уменьши количество чанков через `CHUNK_MAX_TOKENS` или отключи reasoning через
`thinking_budget=None` в конфиге агента.

## 10. Workflow: от загрузки до рилса

Сценарий: у вас есть запись подкаста длительностью 2 часа. Цель — получить 6-10 готовых вертикальных рилсов для публикации. По опыту на M5 + 24 GB RAM весь процесс занимает около 25-35 минут в pipeline, а ваше личное участие — не более 5 минут.

### Шаг 1 — Открыть Dashboard

Откройте браузер и перейдите на `http://localhost:3000`. Вы увидите список всех jobs с их статусами и кнопку «Новый проект».

Убедиться, что backend запущен:

```bash
curl http://127.0.0.1:8000/api/v1/health
```

Ожидаемый ответ: `{"status": "ok", "version": "..."}`. Если backend недоступен — запустите `uv run uvicorn videomaker.main:app --reload` в директории `apps/backend/`.

### Шаг 2 — Выбрать профиль

В селекторе ProfileSelector в шапке выберите один из 5 профилей (подробнее — раздел 6.4). Для двухчасового подкаста выберите профиль **«Подкаст»**: он настроен на длинные монологи, расставляет паузы как точки среза и поднимает значимость смысловых кульминаций.

Если не уверены в типе контента — выберите **«Универсал»**: детектор audio-сигнатуры определит характер материала автоматически и скорректирует параметры на стадии ingest.

### Шаг 3 — Выбрать стиль субтитров

В select «Стиль субтитров» выберите пресет. Рядом с ним отображается мини-превью с образцом шрифта и цвета. Для подкаста хорошо подходит «TikTok белый» или «Новости жёлтый».

Получить полный список доступных пресетов через API:

```bash
curl -s http://127.0.0.1:8000/api/v1/settings/subtitle_presets | jq
```

Если ни один пресет не подходит — создайте кастомный через `/settings/subtitles` в UI или через API (см. раздел 6.3). Новый пресет сразу появится в селекторе.

### Шаг 4 — Загрузить видео

Перетащите файл в зону drag-n-drop или нажмите «Выбрать файл». Ограничение размера задаётся переменной `APP_MAX_UPLOAD_SIZE_MB` (по умолчанию 30 ГБ). Поддерживаемые форматы: MP4, MOV, MKV, WebM.

API-эквивалент (создаёт job и запускает pipeline):

```bash
curl -F 'file=@podcast.mp4' \
     -F 'profile=podcast' \
     -F 'subtitle_preset_id=tiktok_white' \
     http://127.0.0.1:8000/api/v1/jobs
# → {"id": "job_abc123", "status": "queued", "stage": "ingest", ...}
```

Что происходит в backend: файл копируется в `data/uploads/job_abc123/`, создаётся запись в таблице `jobs`, job отправляется в background worker через очередь.

### Шаг 5 — Мониторить прогресс

UI автоматически переходит на страницу `/jobs/[id]` с live-обновлением через SSE (подробнее — раздел 5.2). Прогресс-бар отображает текущую стадию, процент и описательное сообщение.

Если нужен собственный SSE-клиент (JavaScript):

```javascript
const es = new EventSource('http://127.0.0.1:8000/api/v1/jobs/job_abc123/stream');
es.addEventListener('progress', (e) => {
  const data = JSON.parse(e.data);
  console.log(`${data.stage}: ${data.progress}% — ${data.message}`);
});
es.addEventListener('done', (e) => {
  const data = JSON.parse(e.data);
  console.log(`Готово! Рилсов: ${data.reels}`);
  es.close();
});
```

Или напрямую через curl:

```bash
curl -N http://127.0.0.1:8000/api/v1/jobs/job_abc123/stream
```

### Шаг 6 — Ожидание

Ориентиры по времени на M5 + 24 GB RAM:

| Длительность исходника | Примерное время pipeline |
|---|---|
| 30 минут | ~8-12 минут |
| 1 час | ~15-22 минуты |
| 2 часа | ~25-35 минут |
| 2.5+ часа | ~45+ минут (зависит от scaling reducer caps, см. 6.5) |

Самые медленные стадии — `transcribe` (mlx-whisper работает примерно в 0.3× realtime на длинных файлах) и `analyze` (Stage 5 параллельных агентов: количество итераций зависит от числа chunk'ов и tier'а моделей). Если нужно ускорить — снизьте `CHUNK_MAX_TOKENS` или переключите модели на Gemini Flash Lite в настройках performance (раздел 6.5).

### Шаг 7 — Просмотр результатов

После завершения pipeline на странице `/jobs/[id]` появляется сетка карточек рилсов. Каждая карточка показывает: inline-превью видео, длительность клипа, размер файла, драматургическую метку (hook, peak, resolution) и итоговый score.

Получить список рилсов через API:

```bash
curl http://127.0.0.1:8000/api/v1/jobs/job_abc123 | jq '.reels'
```

Файлы лежат в `data/artifacts/job_abc123/reels/*.mp4`.

### Шаг 8 — Оценка и обратная связь

На каждой карточке есть кнопки «нравится» и «не нравится». Отметки сохраняются в `preference_memory` и влияют на ранжирование рилсов в следующих jobs — чем больше фидбека, тем точнее подбор.

API-эквивалент:

```bash
curl -X PATCH http://127.0.0.1:8000/api/v1/jobs/job_abc123/reels/reel_01 \
  -H 'content-type: application/json' \
  -d '{"preference": "like"}'
```

Актуальные эндпоинты всегда доступны в Swagger UI по адресу `http://127.0.0.1:8000/docs`.

### Шаг 9 — Скачивание

Нажмите кнопку «Скачать» на карточке рилса — браузер получит финальный mp4.

Через API:

```bash
curl -O http://127.0.0.1:8000/api/v1/files/job_abc123/reels/reel_01.mp4
```

Формат выходного файла: H.265 HEVC, 30 fps, битрейт не ниже 15 Mbps, соотношение сторон 9:16 (1080×1920 или 720×1280 — зависит от разрешения исходника).

### Шаг 10 — Публикация или планирование

Два варианта: опубликовать немедленно или поставить в расписание.

**Опубликовать сейчас** (пример для Instagram):

```bash
curl -X POST http://127.0.0.1:8000/api/v1/jobs/job_abc123/reels/reel_01/export \
  -H 'content-type: application/json' \
  -d '{"platform": "instagram", "caption": "Текст подписи", "hashtags": ["подкаст", "рилсы"]}'
```

Требование: Instagram-аккаунт должен быть подключён в `/settings/connections` (раздел 6.7).

**Запланировать публикацию** (через scheduler):

```bash
curl -X POST http://127.0.0.1:8000/api/v1/schedule \
  -H 'content-type: application/json' \
  -d '{
    "job_id": "job_abc123",
    "reel_id": "reel_01",
    "platform": "youtube",
    "scheduled_at": "2026-04-20T18:00:00+03:00",
    "title": "Название для YouTube",
    "description": "Описание",
    "tags": ["tag1", "tag2"]
  }'
```

Worker `scheduler_worker.py` опубликует рилс автоматически в назначенное время. Подробнее о scheduler — в разделе 11.

---

> **Итог сценария:** 2-часовой подкаст → 28 минут в pipeline → 8 готовых рилсов → выбрали 4 лучших → опубликовали один сразу, три поставили в расписание на следующие дни. Общее время участия человека: около 5 минут (выбор профиля + оценка рилсов).

## 11. Scheduler и публикации

### 11.1 Как работает scheduler

Фоновый worker `services/scheduler_worker.py` запускается при старте сервера (lifespan в `main.py`) и poll'ит таблицу `scheduled_posts` каждые 60 секунд. Когда находит пост со статусом `pending` и `scheduled_at <= now()` — переводит в `posting`, вызывает соответствующий publisher, фиксирует результат (`posted` или `failed`).

Таблица `scheduled_posts` (схема):

| Поле | Тип | Что хранит |
|---|---|---|
| `id` | str | UUID записи |
| `job_id` | str | ссылка на job |
| `reel_id` | str | конкретный рилс |
| `platform` | enum | `instagram` / `youtube` |
| `scheduled_at` | datetime | UTC время публикации |
| `status` | enum | `pending` / `posting` / `posted` / `failed` |
| `title` | str | заголовок для YouTube |
| `description` | str | описание / caption |
| `tags` | list[str] | теги |
| `error` | str\|null | сообщение ошибки если `failed` |
| `published_url` | str\|null | URL после успешной публикации |
| `created_at` | datetime | когда запланировано |

Файлы: `services/scheduler_worker.py` (worker loop), `services/scheduled_posts_store.py` (CRUD + query).

### 11.2 Публикация в YouTube

OAuth 2.0 flow реализован в `services/youtube_oauth.py`:

1. Пользователь кликает «подключить YouTube» в `/settings/connections`
2. Frontend вызывает `POST /api/v1/connections/youtube/connect` — сервер возвращает `redirect_url` на Google OAuth consent screen
3. Пользователь авторизуется, даёт scope `youtube.upload`
4. Google редиректит на `/api/v1/connections/youtube/callback?code=...`
5. Сервер обменивает `code` на `access_token` + `refresh_token`, сохраняет `refresh_token` в таблице `connections`

При публикации сервер использует `refresh_token` для получения свежего `access_token` и загружает видео через YouTube Data API v3 (`videos.insert`, resumable upload). После успешной загрузки `published_url` сохраняется обратно в `scheduled_posts`.

Ограничения YouTube Data API:
- Квота 10 000 единиц в день. Один upload ~1600 единиц — практически 6 видео/день на проект. Для production-объёмов подать заявку на увеличение квоты в Google Cloud Console.
- Видимость: по умолчанию `private`. Параметр `privacyStatus` можно переопределить.

Проверка статуса подключения:

```bash
curl http://127.0.0.1:8000/api/v1/connections/youtube/status
# → {"connected": true, "email": "...", "expires_at": "..."}
```

Отключение:

```bash
curl -X DELETE http://127.0.0.1:8000/api/v1/connections/youtube
```

### 11.3 Публикация в Instagram

Реализация в `services/instagram_publisher.py`. Instagram Graph API не предоставляет стандартный OAuth flow для личных приложений — пользователь вручную получает long-lived token через Facebook Developers Console.

Процедура получения токена:
1. Создать Facebook App (категория Business)
2. Связать Instagram Business Account с Facebook Page
3. В Graph API Explorer получить user access token со scope `instagram_basic`, `instagram_content_publish`, `pages_show_list`, `pages_read_engagement`
4. Обменять на long-lived token (живёт 60 дней)
5. Сохранить в `/settings/connections`

Сохранение токена через API:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/connections/instagram/token \
  -H 'content-type: application/json' \
  -d '{"token": "IGQVJ...", "business_account_id": "1784..."}'
```

Процесс публикации (Graph API требует двухшагового создания):
1. Создать media container (`POST /{ig_user_id}/media`) с video URL или resumable upload
2. Опубликовать container (`POST /{ig_user_id}/media_publish`)

Ограничения Instagram Graph API:
- 25 публикаций рилсов в день на аккаунт
- Формат: 9:16, max 90 секунд для reels, max 1 ГБ
- Видео должно быть доступно по публичному URL или загружено через resumable upload
- Token истекает через 60 дней — необходимо обновлять через `GET /refresh_access_token`

### 11.4 Создание scheduled post

Полный пример запроса:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/schedule \
  -H 'content-type: application/json' \
  -d '{
    "job_id": "job_abc123",
    "reel_id": "reel_01",
    "platform": "youtube",
    "scheduled_at": "2026-04-20T18:00:00+03:00",
    "title": "Как выбрать коворкинг в Азии",
    "description": "Разобрал три критерия на своём опыте...",
    "tags": ["цифровой кочевник", "Азия", "подкаст"]
  }'
```

Отмена поста:

```bash
curl -X DELETE http://127.0.0.1:8000/api/v1/schedule/{post_id}
```

Список всех запланированных постов:

```bash
curl http://127.0.0.1:8000/api/v1/schedule | jq
```

### 11.5 UI — календарь /schedule

Страница `/schedule` (см. раздел 5.3) показывает все `scheduled_posts` в виде списка/календаря с фильтрами по статусу. Для каждого поста клик открывает детали и позволяет отменить или перенести время публикации.

### 11.6 Надёжность и retry

- Если publisher падает с transient error (network, 500 от API) — worker отмечает пост как `failed`, сохраняет текст ошибки в поле `error`. Автоматический retry не выполняется — решение за пользователем.
- Чтобы повторить публикацию: удалить пост через `DELETE /api/v1/schedule/{post_id}` и создать новый через `POST /api/v1/schedule`.
- Permanent errors (auth expired, нарушение guidelines) — в `error` записывается объяснение. Пользователь должен починить connection и создать новый пост.
- Worker не публикует одно и то же дважды: при переходе `pending → posting` используется DB-level lock (SELECT FOR UPDATE или аналог для SQLite) для предотвращения двойной отправки.

### 11.7 Тайм-зоны

- `scheduled_at` хранится в UTC
- Frontend конвертирует в локальную TZ браузера для отображения
- В payload API можно передавать ISO 8601 с любым UTC-offset — сервер нормализует значение в UTC перед сохранением

## 12. Dev-команды

### 12.1 Backend (Python 3.12, uv)

```bash
cd apps/backend

# Установить/обновить зависимости
uv sync

# Применить миграции БД
uv run alembic upgrade head

# Создать новую миграцию (после изменения моделей)
uv run alembic revision --autogenerate -m "описание изменения"

# Откатить на 1 миграцию
uv run alembic downgrade -1

# Запустить dev сервер (обычно через run.sh, но можно отдельно)
uv run uvicorn videomaker.main:app --reload --reload-dir src

# Линтер
uv run ruff check src/
uv run ruff check src/ --fix        # автофиксы

# Форматирование
uv run ruff format src/

# Type check
uv run pyright                       # из корня apps/backend — читает pyrightconfig.json

# Unit тесты
uv run pytest -q                     # все unit

# Конкретный тест
uv run pytest tests/path/test.py::test_name -v

# Integration тесты (реальный ffmpeg)
uv run pytest -m integration -q

# Coverage
uv run pytest --cov=src/videomaker --cov-report=html

# Параллельный pytest (если установлен pytest-xdist)
uv run pytest -n auto
```

### 12.2 Frontend (Next.js 16, pnpm)

```bash
cd apps/frontend

# Установить зависимости
pnpm install

# Dev сервер
pnpm dev

# Production build
pnpm build
pnpm start                           # запуск built-версии

# Линтер
pnpm lint

# Type check (TypeScript)
pnpm exec tsc --noEmit

# Очистить кэш (если dev ведёт себя странно)
rm -rf .next node_modules/.cache
pnpm install
```

### 12.3 Корневой `run.sh`

Что делает скрипт:

1. Проверяет наличие `.env` — копирует из `.env.example` и печатает reminder добавить `GEMINI_API_KEY`
2. Создаёт `data/uploads`, `data/artifacts`, `data/logs` если не существуют
3. Проверяет наличие `uv`, `pnpm`, `ffmpeg` — выходит если чего-то нет
4. Запускает backend через `uv run uvicorn ... --reload` на `$APP_HOST:$APP_PORT` (дефолт `127.0.0.1:8000`)
5. Запускает frontend через `pnpm dev` на `:3000`
6. trap cleanup — по Ctrl+C останавливает оба процесса

```bash
cd <source-repo>
./run.sh
# Ctrl+C → остановка
```

### 12.4 Миграции БД (Alembic)

Конфиг: `apps/backend/alembic.ini` + `apps/backend/alembic/env.py`
Миграции: `apps/backend/alembic/versions/*.py`

Создание новой миграции:

```bash
cd apps/backend

# 1. Изменить модели в src/videomaker/models/
# 2. Создать миграцию
uv run alembic revision --autogenerate -m "add scheduled_posts table"

# 3. Проверить сгенерированный файл в alembic/versions/ — Alembic иногда пропускает изменения enum и уникальные constraints
# 4. Применить
uv run alembic upgrade head

# Откатить если что-то пошло не так
uv run alembic downgrade -1
```

Если есть data-миграция, добавить её в функцию `upgrade()` созданной миграции вручную.

### 12.5 Логи

- Backend stdout — виден в терминале где запущен `run.sh`
- Backend файловые логи (если настроено) — `data/logs/`
- Frontend stdout — вывод `pnpm dev`

Уровень логирования регулируется через `APP_LOG_LEVEL` в `.env`:

```bash
APP_LOG_LEVEL=DEBUG   # подробные логи
APP_LOG_LEVEL=INFO    # дефолт
APP_LOG_LEVEL=WARNING # только предупреждения
```

### 12.6 Работа с БД напрямую

```bash
# SQLite CLI
sqlite3 data/videomaker.db

# Внутри:
.tables                              # список таблиц
.schema jobs                         # схема таблицы
SELECT * FROM jobs ORDER BY created_at DESC LIMIT 5;
SELECT key, value FROM prompt_settings;
DELETE FROM prompt_settings WHERE key='pass3_virtual_cut';  # сброс промпта к дефолту
.exit

# Экспорт таблицы в CSV
sqlite3 -header -csv data/videomaker.db "SELECT * FROM jobs;" > jobs.csv

# Бэкап (атомарно)
sqlite3 data/videomaker.db ".backup data/videomaker-backup-$(date +%Y%m%d).db"
```

### 12.7 Очистка артефактов

Артефакты растут быстро (2-часовое видео → ~500 МБ в `data/artifacts/<job_id>/`). Очистка:

```bash
# Удалить все artifacts старше 30 дней
find data/artifacts -maxdepth 1 -type d -mtime +30 -exec rm -rf {} \;

# Удалить uploads старше 30 дней
find data/uploads -maxdepth 1 -type d -mtime +30 -exec rm -rf {} \;

# Удалить только proxies (регенерируются при следующем запуске)
curl -X DELETE http://127.0.0.1:8000/api/v1/proxies/cleanup
```

Полное удаление одного job (включая записи в БД):

```bash
curl -X DELETE http://127.0.0.1:8000/api/v1/jobs/job_abc123
```

### 12.8 Debug checklist при ошибках

1. `curl /api/v1/health` — backend жив?
2. Логи в терминале `run.sh` — есть traceback?
3. `.env` загружен? `GEMINI_API_KEY` не пустой?
4. Миграции накачены? `uv run alembic current`
5. Место на диске? `df -h data/`
6. `ffmpeg -version` — есть `hevc_videotoolbox`?
7. Если всё перечисленное ок — смотри раздел 13 «Troubleshooting»

## 13. Troubleshooting и FAQ

### 13.1 Troubleshooting — частые проблемы

---

**13.1.1 «Не настроен ни один LLM-провайдер»**

Причина: `GEMINI_API_KEY` не указан или пустой в `.env`.

Решение:
```bash
# Открыть .env, убедиться что есть строка:
# GEMINI_API_KEY=AIza...
# После сохранения — перезапустить:
./run.sh
```

---

**13.1.2 HEVC output получается меньше 15 Mbps**

Причина: VideoToolbox игнорирует `-b:v` на простом контенте (статичный кадр, однотонный фон) — encoder опускает битрейт ниже цели.

Решение: открыть `apps/backend/src/videomaker/config/export_presets.yaml`, поднять `video_maxrate` или переключиться на CRF-подобный режим через `-q:v`. Проверить итог:
```bash
ffprobe data/artifacts/<job_id>/reels/<reel>.mp4
# смотри строку bit_rate=...
```

---

**13.1.3 Транскрибация на русском языке неточная**

Причина: `mlx-whisper large-v3-turbo` на акцентах и длинных монологах иногда слабее Deepgram nova-3.

Решение: добавить в `.env`:
```bash
DEEPGRAM_API_KEY=...
DEEPGRAM_MODEL=nova-3
```
Затем в `/settings` переключить STT-провайдер на Deepgram.

---

**13.1.4 Рилсы нарезаны из одного куска исходника вместо разных мест**

Причина: промпт `pass3_virtual_cut` (или соответствующая Kartoziya stage) недостаточно явно требует склейку из разных временных отрезков.

Решение: открыть `/settings/prompts`, найти `pass3_virtual_cut`, добавить явное требование: «склейка обязательно из 2–5 коротких фраз из РАЗНЫХ мест исходного видео». Сохранить и запустить новый job (уже запущенные job-ы применили старые промпты — они не пересчитываются).

---

**13.1.5 Job завис на stage analyze несколько часов без прогресса**

Причина: Gemini rate limit (429) + fallback не сработал, или hang в одном из параллельных агентов.

Решение:
1. Проверить логи: `tail -f data/logs/*.log` или stdout `run.sh`.
2. Если видишь `429 Too Many Requests` — подождать 1–5 минут либо переключить провайдера в `/settings/models`.
3. Если hang без traceback — отменить job через `DELETE /api/v1/jobs/{id}` и создать заново с auto-config advisor:
```bash
curl -X POST http://127.0.0.1:8000/api/v1/jobs/{id}/auto-analyze
```

---

**13.1.6 Coherence validator отклоняет все рилсы**

Причина: режим `reject` + неоднородный контент (интервью вперемешку с B-roll, частая смена темпа).

Решение: в `/settings/performance` переключить `coherence_validator_mode` с `reject` на `resort` (мягкий режим — перераспределяет по оценке) или `off` (отключить полностью). Детали — раздел 6.5.

---

**13.1.7 Слишком мало рилсов на выходе**

Причина: scaling reducer cap или hardcoded `MAX_RANKED_ITEMS` ограничивает пул кандидатов ещё до финального отбора.

Решение: в `/settings/performance` поднять caps в блоке Scaling Reducer. Ориентиры: для 30 мин → 60/80, для 2.5 ч → 300/375 (подробнее — раздел 6.5).

---

**13.1.8 Дубли фраз внутри одного рилса**

Причина: сегменты пересекаются по времени (баг до хотфикса с temporal dedup).

Решение: убедиться что версия актуальная — temporal dedup включён в performance settings по умолчанию. Если явно отключён — включить обратно в `/settings/performance`.

---

**13.1.9 Moondream (Vision Layer) падает с OOM**

Причина: 24 GB RAM не хватает при одновременной работе `mlx-whisper` + Moondream + рендер нескольких рилсов.

Решение: в `.env` уменьшить конкурентность:
```bash
VISION_MAX_CONCURRENCY=1
```
Или полностью отключить Vision Layer:
```bash
ENABLE_VISION=false
```
Все параметры описаны в разделе 8.8.

---

**13.1.10 Instagram публикация failed — token expired**

Причина: Instagram long-lived token истёк (срок действия — 60 дней).

Решение: получить новый токен через Facebook Developers Console, обновить через API:
```bash
curl -X POST http://127.0.0.1:8000/api/v1/connections/instagram/token \
  -H "Content-Type: application/json" \
  -d '{"access_token": "<new_token>"}'
```
Процедура получения токена описана в разделе 11.3.

---

**13.1.11 YouTube upload: `quotaExceeded`**

Причина: дневной лимит YouTube Data API v3 — 10 000 единиц, один upload стоит ~1 600 единиц.

Решение: подать заявку на увеличение квоты в Google Cloud Console → APIs & Services → YouTube Data API v3 → Quotas. До одобрения — ждать 24 часа (квота сбрасывается в полночь по тихоокеанскому времени).

---

**13.1.12 Субтитры обрезаны снизу или вылезают за пределы кадра**

Причина: неправильный `anchor`, `fit_mode` или `offset_px` в настройках субтитров.

Решение: открыть `/settings/subtitles`, воспользоваться live preview в правой колонке чтобы увидеть итоговое положение в реальном времени. Таблица совместимости параметров — раздел 6.3.

---

**13.1.13 `ffmpeg: unknown encoder 'hevc_videotoolbox'`**

Причина: ffmpeg установлен без поддержки VideoToolbox (например, из стороннего brew tap или собранный вручную без нужных флагов).

Решение:
```bash
brew reinstall ffmpeg
ffmpeg -hide_banner -encoders 2>&1 | grep hevc_videotoolbox
# должна быть строка: V..... hevc_videotoolbox ...
```

---

**13.1.14 Frontend не подключается к backend (CORS / fetch failed)**

Причина: `FRONTEND_ORIGIN` в `.env` не совпадает с реальным адресом, на котором запущен frontend.

Решение: проверить `.env`:
```bash
FRONTEND_ORIGIN=http://localhost:3000
```
После изменения — перезапустить backend (`./run.sh`).

---

**13.1.15 SSE-поток обрывается в браузере через 30–60 секунд**

Причина: прокси (nginx / Cloudflare) режет idle connections; при локальном запуске — OS idle timeout.

Решение: в dev-режиме не критично — хук `useJobSse` переподключается автоматически. В production настроить nginx:
```nginx
proxy_read_timeout 3600;
proxy_buffering off;
```

---

### 13.2 FAQ

**Q: Можно ли запустить на Linux?**
A: Формально нет — VideoToolbox и mlx-whisper требуют Apple Silicon. Теоретически можно переключить STT на Deepgram (API) и encoder на `libx265`/`libx264` (CPU) через правку `config/export_presets.yaml`, но это неподдерживаемый путь без гарантии качества.

---

**Q: Сколько стоит обработка 1 часа видео?**
A: Ориентир: Gemini (Pro + Flash + Flash Lite через tier matrix) — ~$0.08–0.15 на час контента. Deepgram nova-3, если используется, — ~$0.30/час. С только Gemini + локальным mlx-whisper расходы близки к нулю (в рамках бесплатных лимитов).

---

**Q: Поддерживаются ли другие языки кроме русского?**
A: Транскрибация поддерживает любой язык (nova-3 и mlx-whisper мультиязычные), но промпты, `fillers_ru.yaml` и часть эвристик заточены под русский. Для английского — переписать промпты через `/settings/prompts`, создать `fillers_en.yaml` и указать его в конфиге.

---

**Q: Можно ли работать только через API без UI?**
A: Да, раздел 7 документирует все endpoints. UI — это удобный клиент над теми же REST вызовами. Автоматизация через скрипты и CI — стандартный use case.

---

**Q: Где хранятся готовые рилсы?**
A: `data/artifacts/<job_id>/reels/*.mp4`. Субтитры — `data/artifacts/<job_id>/subs/*.ass`. Обложки (если Vision Layer включён) — рядом с соответствующим mp4 в той же директории `reels/`.

---

**Q: Как экспортировать в TikTok?**
A: Прямой интеграции нет. Рилсы уже в нужном формате (9:16, 30 fps, HEVC) — скачиваешь и загружаешь через TikTok вручную или через сторонние API-сервисы.

---

**Q: Можно ли коммитить `data/videomaker.db`?**
A: Нет. База в `.gitignore` — содержит пользовательские настройки, OAuth токены, историю jobs. Для бэкапа — раздел 12.6.

---

**Q: Как восстановить дефолтные промпты?**
A: Удалить нужные строки из SQLite:
```bash
sqlite3 data/videomaker.db "DELETE FROM prompt_settings WHERE key='<prompt_key>';"
```
После перезапуска сервер засеит дефолтные значения заново.

---

**Q: Что делать если видео длиннее 3 часов?**
A: Pipeline справится, но займёт больше времени. Рекомендации: подать заявку на увеличение Gemini rate limit в Google Cloud Console, включить `proxy_generate` для быстрого seek при рендере, поднять `MAX_UPLOAD_SIZE_MB` в `.env`.

---

**Q: Как открыть Swagger UI?**
A: Перейти по адресу <http://127.0.0.1:8000/docs>. Там интерактивная версия всего API из раздела 7 плюс автогенерированные схемы Pydantic-моделей.

---

**Q: Где посмотреть все текущие prompts и settings для аудита?**
A: Через curl (описано в разделе 7.3):
```bash
GET /api/v1/settings/prompts
GET /api/v1/settings/performance
GET /api/v1/settings/profiles
GET /api/v1/settings/vision
GET /api/v1/settings/subtitle_presets
```

---

**Q: Что делать если нужна новая фича — кастомный агент или video-эффект?**
A: Для extraction-агента — раздел 9.6 даёт шаблон. Для video effects — `services/video_effects/registry.py` + пример `bw.py`. После добавления запустить существующие тесты: `uv run pytest apps/backend/tests/ -x`.

---

## 13. Расширение системы (hot-plug points)

После архитектурного рефакторинга 2026-04-20 ключевые точки расширения оформлены как registry-driven. Добавление новых компонентов не требует правки core-файлов.

### 13.1 Новый LLM-провайдер

1. Создать factory в `apps/backend/src/videomaker/services/llm_clients/my_provider.py` — класс наследник `_BaseLLMClient` с `provider: ClassVar[str]`, `_create_client()`, `complete_json()`.
2. Создать provider-factory в `apps/backend/src/videomaker/services/llm_providers/my_provider_factory.py`:
   ```python
   class MyProviderFactory:
       name = "my_provider"
       def build_client(self, *, settings, model) -> LLMClient: ...
       def tier_model(self, settings, tier) -> str: ...
   ```
3. В `services/llm_providers/__init__.py` добавить строку `register_llm_provider(MyProviderFactory())`.
4. Добавить API-ключ в `core/config.py` Settings и `.env.example`.
5. Всё — `build_llm("my_provider", model)` и `build_llm_for_tier(tier, provider_override="my_provider")` работают.

### 13.2 Новый pipeline stage

1. Создать `apps/backend/src/videomaker/services/pipeline_stages/my_stage.py::run_my_stage(ctx: PipelineContext) -> PipelineContext`.
2. Добавить в `services/pipeline_stages/__init__.py`: `from .my_stage import run_my_stage` + в `__all__`.
3. Добавить вызов в `services/pipeline.py::_run_pipeline_impl` в нужное место:
   ```python
   ctx = await run_my_stage(ctx)
   ```
4. Если стадия пишет в ctx новое поле — добавить в `services/pipeline_context.py` с типом через `TYPE_CHECKING` при необходимости.
5. Если нужен progress SSE-event — импортировать `_advance` локально из `pipeline` (lazy, чтобы избежать циклов) и вызвать его.

### 13.3 Новый vision provider

1. Создать клиент в `apps/backend/src/videomaker/services/vision/my_vision.py` — класс реализующий `VisionClient` Protocol.
2. Создать factory там же (или в отдельном файле):
   ```python
   class MyVisionFactory:
       name = "my_vision"
       def build(self, cfg: Settings) -> VisionClient: ...
   ```
3. В `services/vision/__init__.py` добавить `register_vision_provider(MyVisionFactory())`.
4. Расширить Literal в `models/vision_settings.py::VisionProvider`.
5. `build_vision_client(cfg, provider="my_vision")` работает.

### 13.4 Новый extraction agent

1. Добавить `AgentName` в enum в `services/agents/base.py`.
2. Добавить запись в `AGENT_REGISTRY` dict там же (with `AgentConfig`).
3. Добавить промпт в `services/prompts_data/my_agent.md` (seed файл).
4. В `services/prompts.py` добавить `MY_AGENT_PROMPT = _load_stage_prompt("my_agent.md")`.

### 13.5 Новый post-production effect

1. Создать `apps/backend/src/videomaker/services/video_effects/my_effect.py` — класс реализующий `VideoEffect` Protocol (есть шаблон в `bw.py`).
2. Добавить в `services/video_effects/registry.py::EFFECTS_REGISTRY` tuple.
3. Обновить `PostProductionConfig` Pydantic model в `models/post_production.py` — добавить поле `my_effect_enabled: bool = False`.
4. Добавить Alembic миграцию для новой колонки в `post_production_presets`.
5. UI — добавить `SwitchRow` в `components/settings/post-production/VideoEffectsSection.tsx`.

### 13.6 Новая settings-группа (frontend)

1. Создать `apps/frontend/src/components/settings/performance-groups/MyGroup.tsx` — импортирует `Group`, `SwitchRow`, `NumberRow`, `SliderRow`, `SelectRow` из `@/components/settings-shared`.
2. Добавить в `components/settings/performance-groups/index.ts` re-export.
3. Добавить компонент в `PerformanceSettingsClient.tsx` composition.
4. Расширить `PerformanceSettings` interface в `@/lib/api/settings.ts`.
5. Pydantic model в `models/runtime_settings.py` + default в `from_settings`.

### 13.7 Новый эндпоинт API

1. Добавить функцию в соответствующий `services/*_service.py` (не пиши SQL в route напрямую — нарушает layers).
2. Route handler в `api/routes/*.py` делегирует в service.
3. Добавить typed API-wrapper в `lib/api/<domain>.ts` через `request<T>()` из `lib/api/core.ts`.
4. Использовать напрямую из компонента через `import { ... } from "@/lib/api/<domain>"` (или через `@/lib/api` facade — backward compat).
