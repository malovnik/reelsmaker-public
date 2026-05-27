# Windows Bootstrap Recon — Reelibra (reelsmaker-public)

Автор: Windows Bootstrap Engineer. Цель: «скачал → распаковал → 2 клика по `reelibraWIN` → само доустановилось → работает».
Дата: 2026-05-27. Источник истины — реальные манифесты репо (см. ссылки на файлы внизу).

---

## 0. TL;DR (читать это, если больше ничего)

- **Honest minimum: Windows 10 64-bit (1809+) / Windows 11. Win7/8 — НЕТ, врать не буду.** Блокеры: Python 3.12 (MS убрал поддержку Win7 ещё в 3.9), mediapipe, современный ffmpeg, llama-cpp wheels. Win7 отпадает по нескольким независимым причинам сразу.
- **Главный архитектурный блокер для Windows: локальный STT.** Дефолтный и единственный *локальный* транскрайбер — `mlx-whisper` / `stable-ts[mlx]`. **MLX — это Apple-only фреймворк (Metal). На Windows его НЕТ и не будет.** Значит на Windows транскрипция работает только через **Deepgram (cloud, нужен API-ключ)**. Это надо явно сказать пользователю в инсталляторе, иначе «два клика» молча сломаются на первом же видео.
- **Рекомендуемая стратегия: портативный бандл (zero-install, без админа, без winget), а не авто-инсталл через winget/choco.** Надёжнее для «дебил нажал два раза».
- **Реалистичный размер бандла: ~1.0–1.6 ГБ распакованным** (Python embeddable + venv с тяжёлыми ML-колёсами + node + статический ffmpeg). Это много, но честно: numpy/scipy/librosa/mediapipe/opencv/llama-cpp/onnxruntime — крупные.
- **GPU не обязателен.** Весь «умный» слой (нарезка/драматургия) — облако (Gemini). Локальная vision (Moondream через llama-cpp) и face-tracker (mediapipe) по умолчанию **выключены** (`vision_enabled=False`, `face_tracker_enabled=False`). На Windows стартуем в CPU-режиме без GPU. ffmpeg nvenc — опционально, не требуется.

---

## 1. Реальные зависимости (из манифестов, не из головы)

### Backend — `apps/backend/pyproject.toml`
- **Python pin: `requires-python = ">=3.12,<3.13"`.** То есть строго **Python 3.12.x**. Не 3.11, не 3.13. Это жёстко сужает выбор бандла.
- Веб/инфра (чистый Python, проблем на Win нет): fastapi, uvicorn[standard], sse-starlette, pydantic(-settings), sqlalchemy, aiosqlite, alembic, httpx, tenacity, pyyaml, tiktoken, structlog, json-repair, greenlet.
- LLM-клиенты (cloud, чистый Python): google-genai, anthropic, openai, zhipuai, deepgram-sdk.
- **Тяжёлые ML/DSP колёса (бинарные, размер + платформа):**
  - `mlx-whisper`, `stable-ts[mlx]` → **APPLE-ONLY. На Windows не ставятся / бесполезны.** ← ключевой блокер.
  - `mediapipe` (>=0.10.33) — Windows wheels есть, но только **x86-64** (нет ARM64/Win), и тянет protobuf/opencv. Используется только для face-tracker → по умолчанию OFF.
  - `llama-cpp-python` (>=0.3.2) — для локальной Moondream vision. На Windows ставится из prebuilt wheel (CPU) или CUDA-wheel. По умолчанию vision OFF.
  - `onnxruntime`, `silero-vad` — CPU OK на Windows.
  - `av` (PyAV) — bundled ffmpeg-libs в колесе, Win wheels есть.
  - `librosa`, `numpy>=2.1`, `soundfile`, `pyloudnorm`, `noisereduce`, `scikit-maad` — научный стек, Win wheels есть, но крупные.
  - `opensmile`, `praat-parselmouth`, `pedalboard` — бинарные, Win wheels есть (проверить pin под 3.12).
  - `opencv-python-headless` — Win OK.
  - `ffmpeg-python` — это **обёртка-вызов внешнего `ffmpeg`/`ffprobe` бинаря**, сам ffmpeg в неё НЕ входит → ffmpeg надо поставлять отдельно.

### Frontend — `apps/frontend/package.json`
- Vite 7 + React 19 + react-router 7 + Tailwind 4 + TypeScript 5.7. Чистый Node-стек. Менеджер по `run.sh` — **pnpm**. Нужен **Node 20+** (Vite 7 требует Node ≥20.19/22).

### Внешние бинари (из `run.sh` + кода)
- **ffmpeg + ffprobe** — обязательны. `run.sh` падает если нет (`command -v ffmpeg`). `services/encoder_support.py` рантайм-детектит энкодеры через `ffmpeg -encoders` и фолбэчит VideoToolbox→libx264/libx265, т.е. **software-энкодинг есть всегда, GPU не нужен**.
- **uv** — менеджер Python-окружения (бэкенд).
- **pnpm** (через npm) — менеджер фронта.

### Запуск (`run.sh`, bash — на Windows НЕ работает as-is)
backend: `uv run uvicorn videomaker.main:app --host 127.0.0.1 --port 8000`; frontend: `pnpm dev` (Vite на :3000). `.env` копируется из `.env.example`, создаются `data/uploads|artifacts|logs`. **Этот скрипт bash-only (set -euo pipefail, pgrep, lsof, trap) — для Windows нужен отдельный лаунчер, переписанный на нативные инструменты.**

### Ключи/сеть (`.env.example`)
- `GEMINI_API_KEY` — де-факто обязателен (вся нарезка). Без него pipeline не поедет.
- `DEEPGRAM_API_KEY` — **на Windows фактически обязателен для STT** (локальный MLX недоступен).
- Остальное (ANTHROPIC/OPENAI/ZHIPU/YouTube/Instagram OAuth) — опционально.

---

## 2. Honest Windows minimum (без вранья)

| ОС | Вердикт | Почему |
|---|---|---|
| **Win7 / 8 / 8.1** | ❌ Невозможно | Python 3.12 не поддерживает <Win8.1 (CPython дропнул Win7 в 3.9); mediapipe/современный ffmpeg/llama-cpp wheels собраны под Win10+ UCRT; Node 20 не поддерживает Win7. Любой из пунктов — стоп. |
| **Win10 x64 (1809+)** | ✅ Целевая | Python 3.12, Node 20, mediapipe, ffmpeg — всё работает. Нужен VC++ Redist (см. ниже). |
| **Win11 x64** | ✅ Идеал | — |
| **Windows on ARM** | ⚠️ Частично | mediapipe и часть бинарных колёс не имеют win-arm64 wheels. Не целиться. Только x86-64. |

**Что обязательно докинуть на чистой Win10/11:**
1. Python 3.12.x — поставляем в бандле (НЕ просим пользователя ставить).
2. Node 20.x LTS — поставляем portable.
3. ffmpeg+ffprobe (static gpl build, win64) — поставляем.
4. uv (один .exe) — поставляем.
5. **Microsoft Visual C++ Redistributable 2015–2022 (x64)** — runtime-DLL (`vcruntime140.dll`, `msvcp140.dll`) нужны numpy/opencv/mediapipe/llama-cpp/onnxruntime. На свежих Win11 обычно есть, на чистой Win10 — НЕ всегда. Лаунчер должен проверить наличие `vcruntime140.dll` и при отсутствии запустить тихую установку `vc_redist.x64.exe` (единственный кусок, который может попросить UAC — поэтому либо бандлим redist и ставим `/install /quiet /norestart`, либо детектим и предупреждаем).

---

## 3. Стратегия bootstrap: портативный бандл vs winget/choco

**Рекомендация: ПОРТАТИВНЫЙ БАНДЛ.** winget/choco — НЕ для «двух кликов».

| Критерий | Портативный бандл | winget / choco |
|---|---|---|
| Нужен админ/UAC | Нет (кроме VC++ redist один раз) | Да (choco всегда; winget часто) |
| Работает оффлайн/за корп-прокси | Да (всё внутри) | Нет — сюрпризы с сетью/прокси/политиками |
| Воспроизводимость («у меня не ставится») | Высокая — версии заморожены | Низкая — winget тянет latest, ломается |
| Установлен ли менеджер | Не нужен | winget есть не везде (LTSC/Server/старые), choco почти ни у кого |
| «Дебил нажал два раза» | ✅ | ❌ нужен опыт |
| Минус | Размер ~1–1.6 ГБ | Лёгкий, но хрупкий |

**Состав бандла (распакованный рядом с репо):**
```
reelibra/
  reelibraWIN.cmd          ← двойной клик #2 (после распаковки = клик #1)
  runtime/
    python-3.12/           ← python-build-standalone (astral), win64, ~40МБ → распак ~120МБ
    node-20/               ← Node portable win-x64, ~70МБ
    ffmpeg/                 ← ffmpeg+ffprobe static gpl (gyan.dev/BtbN), ~90МБ
    uv.exe                 ← один бинарь, ~30МБ
    vc_redist.x64.exe      ← ~25МБ, ставится при отсутствии vcruntime140.dll
  apps/ data/ .env ...     ← сам репо
```

**Почему python-build-standalone, а не embeddable:** официальный Windows *embeddable* zip кривой для venv/pip (нет ensurepip, обрезанный). `python-build-standalone` (тот же, что качает uv) — полноценный, идеально дружит с `uv venv --python <path>`. uv сам умеет ставить нужный Python (`uv python install 3.12`), но это сетевой шаг — для оффлайн-надёжности кладём Python в бандл и указываем `uv venv --python runtime/python-3.12`.

**Колёса:** при первом запуске `uv sync` ставит ~1 ГБ wheels в `.venv`. Два варианта:
- (A) **Тонкий бандл** (~250 МБ): без `.venv`, ставится при первом клике из PyPI. Минус — нужна сеть и 3–8 минут на первый запуск; риск отсутствия Win-wheel для редкого пакета.
- (B) **Толстый бандл** (~1.3–1.6 ГБ): предсобранный `.venv` под Win64/py3.12 уже внутри. Первый клик = секунды. Надёжнее для «двух кликов», но venv непортативен между путями → лаунчер должен пересоздавать через `uv sync` если путь/хэш сменился. Практичный гибрид: бандлить **колёсный кэш** (`wheels/` + `uv sync --offline --find-links`) — это и оффлайн, и path-independent.

**Рекомендация: гибрид (B-кэш) — бандлим `wheels/` (offline wheelhouse) + portable runtime.** При клике `uv sync --offline` собирает venv из локальных колёс за ~1–2 мин, без сети, path-independent.

⚠️ **Перед сборкой wheelhouse: убрать `mlx-whisper` и `stable-ts[mlx]` из набора для Windows** (их Win-wheels не существует — `uv sync` упадёт). Нужен либо отдельный `pyproject` / extras-группа `[windows]` без MLX, либо `--no-build-isolation` обход. Это **обязательная правка перед тем как Windows-бандл вообще соберётся.** Без неё `uv sync` фейлится на резолве MLX.

---

## 4. Механизм двойного клика

**Формат: `.cmd` (батник) как точка входа + встроенный PowerShell для прогресса.** Не `.exe`.

- **`.cmd`, а не `.exe`:** .exe требует сборки (PyInstaller/Inno) и провоцирует SmartScreen/антивирус («неизвестный издатель», блок). Голый `.cmd` SmartScreen не трогает, правится глазами, не требует подписи. Для open-source-репо «скачал и запустил» это надёжнее.
- **`.ps1` напрямую — нет:** дабл-клик по `.ps1` по умолчанию открывает редактор, плюс ExecutionPolicy блочит. Поэтому обёртка `.cmd`, которая внутри зовёт `powershell -ExecutionPolicy Bypass -File launcher.ps1`. Так получаем и надёжный дабл-клик, и нормальный скрипт-движок для прогресса/проверок.
- **Имя:** `reelibraWIN.cmd` (как в задаче). Рядом можно положить `.lnk` ярлык с иконкой Reelibra и именем без расширения — выглядит как «приложение».

**Что делает `reelibraWIN.cmd` → launcher.ps1 (псевдо-поток):**
1. Self-locate (путь к своей папке), `chcp 65001` для UTF-8 (русский в логах).
2. **Preflight-проверки с прогрессом** (псевдографика в консоли — `[1/7] Проверка Python… OK`):
   - vcruntime140.dll → если нет, тихо ставим `vc_redist.x64.exe /install /quiet /norestart`.
   - runtime/python-3.12, node-20, ffmpeg, uv.exe — наличие.
   - `.env` → если нет, копируем из `.env.example` и **СТОП с понятным сообщением**: «Открой .env, впиши GEMINI_API_KEY (обязательно) и DEEPGRAM_API_KEY (нужен для распознавания речи на Windows)». Без ключей честно не запускаем — иначе «два клика» отработают, а нарезка молча упадёт.
   - создать `data\uploads`, `data\artifacts`, `data\logs`.
3. `uv sync --offline` (бэкенд venv из wheelhouse) — с прогресс-строкой.
4. `pnpm install --silent` (через portable node; если pnpm нет — `corepack enable` или `npm i -g pnpm` в portable-scope).
5. Освободить порты 8000/3000 (нативно: `netstat -ano | findstr :8000` → `taskkill /PID /F`) — аналог lsof-части `run.sh`.
6. Стартовать backend (uvicorn, БЕЗ `--reload` для конечного юзера) и frontend (Vite/preview) — два фоновых процесса; PID в файл для последующей остановки.
7. Подождать `http://127.0.0.1:8000/health` (poll), затем `start http://localhost:3000` — **браузер открывается сам**. Консоль остаётся открытой как «сервер»; закрытие окна = `taskkill` детей (trap-аналог).

**Прогресс — две опции:**
- (Простая, рекомендую для v1) Консоль с нумерованными шагами `[n/7]`, спиннер из `- \ | /`, цветной OK/FAIL через ANSI (Win10+ терминал умеет). Zero-dependency.
- (Богатая, позже) Минимальное WinForms-окно из того же PowerShell (`Add-Type -AssemblyName System.Windows.Forms`) с ProgressBar. Без внешних зависимостей, но больше кода. Для MVP не нужно — консоль честнее и отлаживаемее.

---

## 5. GPU / железо

| Компонент | GPU? | Дефолт | Комментарий для Windows |
|---|---|---|---|
| Нарезка/драматургия (LLM) | Нет (cloud) | ON | Gemini API. Сеть, не железо. |
| STT локальный (MLX) | — | — | **Недоступен на Windows вообще.** |
| STT Deepgram | Нет (cloud) | — | Реальный STT-путь на Windows. Нужен ключ. |
| ffmpeg энкод | Опц. nvenc | software | `encoder_support.py` сам фолбэчит в libx264/libx265. **GPU не требуется.** nvenc можно включить если есть NVIDIA, но не обязательно. |
| Vision (Moondream/llama-cpp) | CUDA опц. | **OFF** (`vision_enabled=False`) | На Windows если включат — CPU-режим (медленно) или CUDA-wheel llama-cpp при NVIDIA. По умолчанию выключено → не трогаем. |
| Face-tracker (mediapipe) | CPU/GL | **OFF** (`face_tracker_enabled=False`) | CPU. По умолчанию выключено. |

**Вывод по железу:** минимальная рабочая конфигурация Windows = **обычный x64 CPU + интернет + 2 API-ключа. GPU не нужен ни для чего по дефолту.** RAM-планка: ~4–6 ГБ свободных (ffmpeg-рендер + научный стек). При включении локальной vision — +5–6 ГБ и желательно NVIDIA, но это явный opt-in.

---

## 6. Ключевые риски (отсортировано по злобности)

1. 🔴 **Локальный STT = Apple-only.** На Windows нет локального распознавания речи вообще. Либо Deepgram (ключ, деньги, сеть), либо нужно ДОБАВИТЬ кроссплатформенный backend (`faster-whisper` на CTranslate2 — есть Win wheels, CPU/CUDA). **Это не bootstrap-задача, это продуктовый пробел.** Bootstrap обязан явно предупредить пользователя. Рекомендация продукту: добавить `faster-whisper` backend для паритета — иначе Windows-юзер без Deepgram-аккаунта получает нерабочее приложение.
2. 🔴 **`uv sync` упадёт на `mlx-whisper`/`stable-ts[mlx]`** (нет Win-wheels). Нужен отдельный набор зависимостей для Windows (extras-группа `[windows]` без MLX, или платформенный маркер `sys_platform == 'darwin'` на MLX-пакетах в pyproject). Без этого бандл не собирается в принципе. Минимальная правка: навесить маркер `; sys_platform == 'darwin'` на оба MLX-пакета.
3. 🟠 **VC++ Redist** — единственный шаг, который может потребовать UAC. На чистой Win10 numpy/opencv/llama-cpp упадут с `DLL load failed` если его нет. Бандлим `vc_redist.x64.exe`, ставим тихо при детекте отсутствия.
4. 🟠 **Размер бандла ~1.3–1.6 ГБ.** Для GitHub-релиза → нужен Release asset / внешний хостинг (РФ-доступный, см. ru-cdn-fallback). Не влезает в обычный git.
5. 🟠 **SmartScreen / антивирус** на портативном Node/ffmpeg/uv. `.cmd`-вход минимизирует, но Defender может карантинить ffmpeg.exe. Митигейт: брать ffmpeg из gyan.dev/BtbN (репутационно чистые), документировать.
6. 🟡 **bash `run.sh` неприменим** — весь preflight (pgrep/lsof/trap/SIGKILL) надо переписать нативно (`taskkill`/`netstat`). Это и есть работа лаунчера, заложено в §4.
7. 🟡 **pnpm на portable Node** — `corepack enable` требует прав на симлинки в node-папку; проще `npm i -g pnpm` со scope в portable prefix, либо вызывать `pnpm` через `npx pnpm`. Проверить на чистой машине.
8. 🟡 **Python pin `<3.13`** — нельзя взять любой Python. Строго 3.12.x в бандле.
9. 🟡 **Пути с пробелами/кириллицей** (`C:\Users\Вася\Загрузки\reelibra`) — классика поломки venv/uv/ffmpeg. Лаунчер должен везде кавычить пути и предупреждать при кириллице в пути.

---

## 7. Итоговая рекомендация

- **Стратегия:** портативный гибрид-бандл (python-build-standalone 3.12 + portable Node 20 + static ffmpeg + uv.exe + offline wheelhouse + vc_redist), zero-install, без админа.
- **Минимальный честный Windows:** Windows 10 x64 (1809+) / Windows 11 x64. **Win7/8 — невозможно, точка.** Только x86-64 (не ARM).
- **Двойной клик:** `reelibraWIN.cmd` → `powershell -ExecutionPolicy Bypass -File launcher.ps1`, прогресс нумерованными шагами в консоли, авто-старт двух серверов, авто-открытие браузера на :3000.
- **Железо:** обычный CPU + интернет + GEMINI_API_KEY + DEEPGRAM_API_KEY. GPU не нужен. Vision/face-tracker по умолчанию OFF.
- **Два обязательных предусловия продукта перед сборкой:** (1) навесить `sys_platform=='darwin'` маркер на MLX-пакеты, иначе `uv sync` не пройдёт; (2) либо требовать Deepgram-ключ как обязательный на Windows, либо добавить `faster-whisper` для локального STT-паритета.

---

## Источники (реальные файлы репо)
- `/Users/malovnik/Documents/Dev/reelsmaker-public/apps/backend/pyproject.toml` — Python pin 3.12, все ML/DSP зависимости, MLX-пакеты.
- `/Users/malovnik/Documents/Dev/reelsmaker-public/apps/frontend/package.json` — Vite 7 / React 19 / Node 20+ / pnpm.
- `/Users/malovnik/Documents/Dev/reelsmaker-public/run.sh` — bash-only запуск (uv + pnpm + ffmpeg обязателен), порты 8000/3000.
- `/Users/malovnik/Documents/Dev/reelsmaker-public/.env.example` — GEMINI обязателен, DEEPGRAM для STT, прочее опц.
- `apps/backend/src/videomaker/services/transcribers/factory.py` + `core/config.py:271` — локальный STT только MLX (Apple), кроссплатформенного нет.
- `apps/backend/src/videomaker/services/encoder_support.py` — software-фолбэк ffmpeg, GPU не нужен.
- `apps/backend/src/videomaker/core/config.py:125` — `vision_enabled=False`; `models/runtime_settings.py:405` — `face_tracker_enabled` OFF.
- `apps/backend/src/videomaker/services/vision/moondream_local.py` — llama-cpp/GPU vision, opt-in.
