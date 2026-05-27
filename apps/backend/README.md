# videomaker-backend

FastAPI-сервис, который обрабатывает видео по 5-стадийному pipeline:
`ingest → transcribe → silence_cut → analyze (3-pass LLM) → render`.

Хранит прогресс в SQLite (через Alembic-миграции), транслирует события в
SSE и раздаёт готовые рилсы через `/api/v1/files/{job_id}/{kind}/{name}`.

## Зависимости окружения

- Python 3.12, `uv` для управления окружением.
- ffmpeg ≥ 7 с `hevc_videotoolbox` (macOS) или совместимым HEVC-энкодером.
- API-ключи (в `.env`, минимум Gemini):
  `GEMINI_API_KEY`, опционально `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
  `DEEPGRAM_API_KEY`.

## Локальная разработка

```bash
uv sync
uv run alembic upgrade head
uv run uvicorn videomaker.main:app --reload --reload-dir src
```

Docs: <http://127.0.0.1:8000/docs>. Health: `/api/v1/health`.

## Тесты и проверки

```bash
uv run pytest -q                  # быстрые unit-тесты
uv run pytest -m integration -q   # e2e с реальным ffmpeg
uv run ruff check src/
uv run mypy src/videomaker
uv run alembic check              # миграции в актуальном состоянии
```

## Структура пакета

```
src/videomaker/
├── api/routes/    # health, jobs (SSE + upload), settings, files, post_production
├── core/          # config, db (SQLAlchemy async), logging, artifacts
├── models/        # SQLAlchemy-таблицы + Pydantic-схемы
├── services/
│   ├── jobs.py                # JobService + in-memory JobEventBus
│   ├── pipeline.py            # 5-stage orchestrator
│   ├── transcribers/          # mlx-whisper / deepgram
│   ├── analyzers/             # 3-pass video analyzer + chunker
│   ├── llm_client.py          # Gemini / Claude (prompt cache) / OpenAI
│   ├── media.py               # ffmpeg wrappers (probe, extract, render)
│   ├── renderer.py            # HEVC presets + final encode
│   ├── project_renderer.py    # single-pass ffmpeg через ProjectGraph
│   ├── subtitles.py           # ASS-writer
│   ├── subtitle_styles.py     # ASS alignment/margin_v resolver
│   ├── silence_cutter.py      # RMS + filler regex
│   ├── face_tracker.py        # mediapipe face detect (для zoom-plan)
│   └── proxy.py               # lazy H.264 proxy генерация
├── config/        # YAML: fillers_ru.yaml, export_presets.yaml
└── main.py        # FastAPI entrypoint
```

## Операционные ограничения

* Текущий `JobEventBus` — in-memory, поэтому сервис должен запускаться
  одним воркером (`uvicorn ... --workers 1`). Для multi-worker потребуется
  Redis Pub/Sub в качестве транспорта между процессами.
* Pipeline записывает промежуточные артефакты в
  `data/artifacts/<job_id>/{text,audio,reels,subs}/` — это основной
  «state» для resumability (планируется checkpoint-режим).
* Все ffmpeg-вызовы проходят через `asyncio.create_subprocess` API
  со списком аргументов (без shell-интерполяции); пути к subtitle-файлам
  дополнительно экранируются в `ffmpeg_escape_path` (media.py).
