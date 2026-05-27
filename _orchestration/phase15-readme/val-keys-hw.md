# README Validation — Ключи / STT / Железо

Источники: README.md (RU+EN), config.py, transcribers/factory.py, encoder_support.py, .env.example, services/publer/{client,worker}.py, services/vision/moondream_local.py.

## Итог по пунктам

| # | Утверждение README | Вердикт | Подтверждение в коде |
|---|--------------------|---------|----------------------|
| 1 | `GEMINI_API_KEY` обязателен всегда (LLM-ядро) | ПРАВДА | config: `gemini_default_model` дефолт пайплайна; `available_llm_providers` включает gemini только при наличии ключа. Без LLM нарезка не работает. |
| 2 | `DEEPGRAM_API_KEY` обязателен на Win/Linux/Intel-Mac, НЕ нужен на Apple Silicon | ПРАВДА | config: `DEFAULT_TRANSCRIBER = "stable_ts_mlx" if IS_MACOS else "deepgram"`; `available_transcribers` = MLX только при `IS_MACOS`, иначе deepgram при наличии ключа. factory: MLX-бэкенды бросают ошибку если `sys.platform != "darwin"`, deepgram бросает ошибку без `DEEPGRAM_API_KEY`. Точное соответствие. |
| 3 | Publer опционален; нужны `PUBLER_API_KEY` + `PUBLER_WORKSPACE_ID` | ПРАВДА (имена), но НЕТ в .env.example | config: `publer_api_key` (alias `PUBLER_API_KEY`), `publer_workspace_id` (alias `PUBLER_WORKSPACE_ID`). client.py читает именно их, worker — no-op без `PUBLER_API_KEY`. Опциональность подтверждена (default=""). НО: переменные отсутствуют в `.env.example` — см. ниже. |
| 4 | Дискретная видеокарта НЕ обязательна, энкод на CPU | ПРАВДА | encoder_support: только VideoToolbox (Mac) → фолбэк libx264/libx265 (CPU). `nvenc`/`cuda` в кодовой базе видеорендера НЕ найдены. |
| 5 | Ресурсоёмкая, скорость зависит от железа | ПРАВДА (честно) | CPU-энкод libx264/x265 + локальный MLX STT на Mac + параллелизм (`llm_max_concurrency=10`, vision/face subprocess). Нагрузка реальна. |
| 6 | Vision / face по умолчанию выключены | ПРАВДА | config: `vision_enabled: bool = False`. Face tracker — отдельный toggle (см. ниже), по умолчанию в pipeline выключен (README "off by default" соответствует прежней фиксации feat: default OFF). |
| 7 | GPU опционален для Vision (Nvidia RTX 3060 12GB + ручная сборка) | ПРАВДА | vision/moondream_local: llama-cpp-python, `n_gpu_layers=-1` (все слои на GPU). Дефолт-сборка = Metal на Mac; CUDA на Nvidia требует ручной пересборки llama-cpp-python с CUDA-флагами (prebuilt wheel в проекте Metal). Соответствует "ручная пересборка". |
| 8 | Порты 8000/3000, лимит загрузки 30GB | ПРАВДА | config: `app_port` default 8000, `frontend_origin`/`FRONTEND_ORIGIN` = localhost:3000, `app_max_upload_size_mb` default 30720 (= 30 GiB). .env.example: `APP_PORT=8000`, `APP_MAX_UPLOAD_SIZE_MB=30720`. |

## Найденная ложь / неточности

**Прямой лжи нет.** Все 8 утверждений соответствуют коду.

Одна несостыковка документации (не ложь README, а дефект `.env.example`):

- **Publer-переменные отсутствуют в `.env.example`.** README говорит "впишите ключи в `.env`, создаётся из `.env.example`" и перечисляет `PUBLER_API_KEY` + `PUBLER_WORKSPACE_ID`. Но в `.env.example` этих строк нет вообще (как и `PUBLER_WORKSPACE_ID`, `PUBLER_SCHEDULER_TZ`, `PUBLER_BASE_URL`). Имена в README верные и совпадают с алиасами в config.py, код их читает корректно — но пользователь, копирующий `.env.example`, не увидит подсказки про Publer. Рекомендация: добавить закомментированный блок Publer в `.env.example` для консистентности (опционально, т.к. pydantic читает alias из env в любом случае).

## Заметки
- README пункт 6: "Vision и трекинг лица по умолчанию выключены" — vision_enabled=False подтверждён в config; face_tracker конфиг присутствует (sample_interval/confidence/timeout), его enable — runtime-toggle, дефолт OFF (соответствует прежней фиксации feat-флага). Утверждение честное.
- Apple Silicon vision использует Metal (n_gpu_layers != 0 → "metal"), не CPU — README не противоречит (GPU "только если включить Vision").
