# videomaker

Локальный нарезчик длинных видео на короткие вертикальные рилсы (9:16) через
multi-pass LLM-анализ транскрипта. Идея — собирать рилсы из разных частей
исходника (виртуальный монтаж), а не резать подряд.

План реализации: `/Users/malovnik/.claude/plans/optimized-crunching-pond.md`.

> **Полная справка:** [`docs/guide.md`](docs/guide.md) — детальное описание 8 страниц настроек, API, Vision Layer, Dramaturgy framework, scheduler, troubleshooting.

## Требования

- macOS на Apple Silicon (оптимизировано под M5, 24 GB RAM)
- Python 3.12 (ставится через `uv`)
- Node.js ≥ 20 и pnpm
- ffmpeg ≥ 7 c `hevc_videotoolbox` (`brew install ffmpeg`)

Если чего-то не хватает:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
brew install node pnpm ffmpeg
```

## Первый запуск

```bash
./run.sh
```

Скрипт поднимет:

- backend (FastAPI + SSE) на <http://127.0.0.1:8000>
- frontend (Next.js 16 + React 19) на <http://localhost:3000>

Docs API: <http://127.0.0.1:8000/docs>. Health: <http://127.0.0.1:8000/api/v1/health>.

На первом запуске будет создана `.env` из `.env.example`. Добавь туда минимум
`GEMINI_API_KEY` — это основной LLM по умолчанию. Остальные (Deepgram,
Anthropic, OpenAI) опциональные и активируются автоматически, если ключи
заданы.

### Где брать API-ключи

- Gemini (по умолчанию): <https://aistudio.google.com/app/apikey>
- Anthropic (Claude с prompt caching): <https://console.anthropic.com/settings/keys>
- OpenAI (GPT-5): <https://platform.openai.com/api-keys>
- Deepgram (альтернативный STT): <https://console.deepgram.com/signup>

## Поток обработки

Пайплайн обрабатывает каждое видео за 5 стадий:

1. **ingest** — ffprobe читает metadata исходника.
2. **transcribe** — mlx-whisper (локально на M5) или Deepgram nova-3 даёт
   word-level timestamps.
3. **silence_cut** — удаляются паузы ≥ 0.6 сек и филлеры (по regex-правилам
   в `apps/backend/src/videomaker/config/fillers_ru.yaml`).
4. **analyze** — 3-проходной LLM-анализ с RAG-chunking (см. план «Chunking
   strategy»): Pass 1 ищет явные тезисы, Pass 2 — неявные углы, Pass 3
   собирает рилсы из фрагментов разных мест.
5. **render** — ffmpeg `filter_complex` нарезает и склеивает фрагменты,
   VideoToolbox кодирует в HEVC (30fps, ≥15 Mbps, tag `hvc1`).

Прогресс транслируется через SSE на `/api/v1/jobs/{id}/stream` и live-
отображается в UI.

## Структура

```
apps/
├── backend/                      # Python 3.12, uv-managed
│   ├── pyproject.toml
│   ├── alembic/                  # миграции SQLite
│   └── src/videomaker/
│       ├── main.py
│       ├── api/routes/           # health, jobs (SSE), settings, files
│       ├── core/                 # config, db, logging, artifacts
│       ├── models/               # SQLAlchemy + Pydantic DTO
│       ├── services/
│       │   ├── jobs.py           # throttled updates + in-memory JobEventBus
│       │   ├── transcribers/     # mlx_whisper + deepgram factory
│       │   ├── analyzers/        # multi-pass LLM orchestrator
│       │   ├── chunker.py        # RAG-style sliding window по tiktoken
│       │   ├── llm_client.py     # Gemini / Claude (cache) / OpenAI
│       │   ├── prompts.py        # SYSTEM_PROMPT + stage prompts
│       │   ├── prompt_store.py   # seed + load из БД
│       │   ├── silence_cutter.py # RMS + regex filler detection
│       │   ├── media.py          # ffmpeg wrappers (probe, extract, render)
│       │   ├── subtitles.py      # ASS writer с local timeline
│       │   ├── renderer.py       # HEVC presets + render_reel_plans
│       │   └── pipeline.py       # 5-stage orchestrator
│       └── config/               # YAML: fillers, export_presets
└── frontend/                     # Next.js 16 + React 19 + Tailwind 4
    └── src/
        ├── app/
        │   ├── page.tsx          # upload + список jobs
        │   ├── jobs/[id]/        # детали job + video-плеер рилсов
        │   └── settings/         # prompts + models
        ├── components/           # client-компоненты
        └── lib/
            ├── api.ts            # typed fetch helpers + SSR URL resolver
            └── sse.ts            # useJobSse hook

data/ (создаётся run.sh)
├── videomaker.db                 # SQLite (jobs, artifacts, prompt_settings)
├── uploads/<job_id>/             # загруженные исходники
└── artifacts/<job_id>/
    ├── audio/                    # извлечённая WAV 16 kHz mono
    ├── text/                     # transcript.json, cleaned_transcript.json,
    │                             # reel_plan.json, analysis_summary.json,
    │                             # manifest.json
    ├── reels/                    # финальные mp4 (H.265 HEVC)
    └── subs/                     # ASS subtitles
```

## Dev-команды

### Backend

```bash
cd apps/backend
uv sync                               # установить deps
uv run alembic upgrade head           # применить миграции
uv run uvicorn videomaker.main:app --reload --reload-dir src
uv run ruff check src/
uv run pytest -q                      # 37 unit-тестов
uv run pytest -m integration -q       # 5 integration-тестов с реальным ffmpeg
```

### Frontend

```bash
cd apps/frontend
pnpm install
pnpm dev
pnpm lint
pnpm exec tsc --noEmit
```

## Настройка субтитров

Страница **`/settings/subtitles`** — 3-колоночный редактор: слева список
пресетов (4 built-in + пользовательские), центр — форма стиля (позиция,
шрифт, цвет, обводка, тень, подложка), справа — live preview с
pixel-accurate маппингом ASS-параметров (позиция, offset, letterbox для
`fit`, подложка как `BorderStyle=3`). Live preview воспроизводит то, что
libass нарисует в финальном рилсе.

Позиционирование:
- `fill` + `bottom/top` — offset 0-300 px от выбранного края кадра.
- `fit` + `bottom/top` — offset 1-150 px внутрь letterbox от границы видео-зоны.
- `center` + `fill` — offset 0-300 px сдвигает текст от центра кадра.
- `center` + `fit` — offset игнорируется (текст всегда по центру).

При создании job на главной — select «Стиль субтитров» + мини-preview.
Кнопка «редактировать» ведёт на `/settings/subtitles`. Избранные шрифты
запоминаются в LocalStorage браузера.

API (если нужен прямой доступ):

```bash
# Список пресетов
curl -s http://localhost:8000/api/v1/settings/subtitle_presets | jq

# Создание кастомного пресета
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

## Обновление промптов

Промпты хранятся в SQLite-таблице `prompt_settings`. При старте сервер
засидит дефолты из `services/prompts.py` только для отсутствующих ключей
(идемпотентно). Чтобы откатить промпт к дефолту — удали строку из БД:

```bash
sqlite3 data/videomaker.db "DELETE FROM prompt_settings WHERE key='pass3_virtual_cut';"
```

После рестарта сервер создаст дефолтный промпт заново.

## Troubleshooting

- **UI говорит «Не настроен ни один LLM-провайдер»** — проверь что в
  `.env` выставлен хотя бы `GEMINI_API_KEY` и перезапусти `./run.sh`.
- **HEVC output меньше 15 Mbps** — проверь `ffprobe data/artifacts/<id>/reels/<reel>.mp4`.
  Если `bit_rate` < 15M, VideoToolbox может игнорировать `-b:v` при
  особо простом контенте. В `config/export_presets.yaml` можно поднять
  `video_maxrate` или переключиться на CRF-подобный режим через `-q:v`.
- **Транскрибация на русском языке неточная** — попробуй Deepgram nova-3
  (добавь `DEEPGRAM_API_KEY` в `.env`). На длинных видео и сложных
  акцентах он обычно точнее mlx-whisper.
- **Рилсы получаются не из разных мест** — отредактируй промпт
  `pass3_virtual_cut` в `/settings/prompts`, подчеркни требование
  «склейка из 2-5 коротких фраз из РАЗНЫХ мест исходного видео».

## Прогресс MVP

| # | Шаг | Статус |
|---|-----|--------|
| 1 | Project scaffold | ✅ |
| 2 | FastAPI skeleton + SSE + persistence | ✅ |
| 3 | Transcriber (mlx-whisper + deepgram) | ✅ |
| 4 | Multi-pass LLM analyzer с RAG-chunking | ✅ |
| 5 | Next.js UI (upload, job list, progress) | ✅ |
| 6 | Silence cutter + filler filter | ✅ |
| 7 | Renderer (ffmpeg VideoToolbox HEVC) | ✅ |
| 8 | Subtitles (ASS burn-in) | ✅ |
| 9 | Prompts editor UI | ✅ |
| 10 | E2E integration tests (real ffmpeg) | ✅ |

## v0.3 (сделано)

- Редактор стилей субтитров с live preview (`/settings/subtitles`)
- 4 built-in пресета + user CRUD, API + LocalStorage favourite fonts
- Поддержка позиционирования: top/center/bottom с учётом letterbox в fit

## Запланировано на v1

- Nano Banana B-roll генерация на паузах
- Ken Burns / zoom transitions
- Цветокоррекция LUT
- Word-karaoke стиль субтитров
- Плашки CTA / «подписаться»
- Ручная правка таймкодов на canvas

## Лицензия

Proprietary. Внутренний инструмент.
