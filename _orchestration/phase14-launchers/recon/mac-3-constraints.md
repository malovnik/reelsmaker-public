# Reelibra — macOS Hardware / Compatibility / Packaging (честный recon)

Источник: реальный код `apps/backend/pyproject.toml`, `.env.example`, `run.sh`,
`services/transcribers/*`, `services/vision/*`, `services/encoder_support.py`,
`core/config.py`, `apps/frontend/src/globals.css`. Не маркетинг — что реально требует код.

---

## 1. Минимальная macOS

- **Целевая платформа: macOS на Apple Silicon.** README прямо заявляет
  «macOS на Apple Silicon (оптимизировано под M5, 24 GB RAM)».
- Python pin: `requires-python = ">=3.12,<3.13"` — нужен ровно Python 3.12.
- Минимальная разумная версия ОС: **macOS 13 Ventura+**, реалистично
  **macOS 14 Sonoma / 15 Sequoia**. Обоснование честное:
  - `mlx-whisper` / `stable-ts[mlx]` тянут Apple **MLX**, который официально
    поддерживается на свежих macOS (13.5+ практический минимум, новые wheels
    собираются под 14+).
  - `llama-cpp-python` Metal-wheel ожидает современный Metal runtime.
  - VideoToolbox-энкодеры в системном ffmpeg стабильны на 13+.
- Жёсткой проверки версии ОС в коде НЕТ — деградация будет «по факту» при
  установке wheels, а не аккуратным сообщением. Лаунчер должен это закрыть.

---

## 2. Apple Silicon vs Intel — честно

**Это Apple-Silicon-first продукт. На Intel-Mac часть стека ломается, а не «медленнее».**

| Подсистема | Apple Silicon (M1+) | Intel Mac |
|---|---|---|
| `mlx-whisper` (локальный STT, дефолт) | Работает (Metal/ANE) | **НЕ работает** — MLX = только Apple Silicon. Wheel не встанет/не запустится |
| `stable-ts[mlx]` (word-level STT) | Работает | **НЕ работает** (тот же MLX) |
| Локальная транскрибация в целом | Да | **Нет** — единственный путь Deepgram cloud (нужен `DEEPGRAM_API_KEY`, платно) |
| Moondream vision (`llama-cpp-python` Metal) | GPU через Metal (`n_gpu_layers=-1`) | Только CPU-сборка llama.cpp → крайне медленно; vision по умолчанию OFF, так что не блокер |
| ffmpeg энкод | `hevc_videotoolbox` / `h264_videotoolbox` (HW) | Фолбэк на `libx264`/`libx265` (software) — код в `encoder_support.py` это умеет, но CPU-кодек медленный |
| LLM-пайплайн (Gemini/Claude/OpenAI/GLM) | Cloud — без разницы | Cloud — без разницы |

**Honest вывод для Intel:** продукт **не предназначен** для Intel-Mac.
Дефолтный локальный STT (`mlx_whisper` в `transcribers/factory.py`) там не
заведётся вообще. Теоретически можно жить на 100% cloud (Deepgram STT + Gemini),
vision OFF, software-ffmpeg — но это другой, платный и медленный режим, который
никто не тестировал. Лаунчер должен честно сказать: «Требуется Apple Silicon»,
а не делать вид что «работает везде».

---

## 3. ЧЕСТНОЕ железо мака (из кода, без выдумок про Nvidia)

**На Mac НЕТ дискретной видеокарты и она не нужна.** Apple Silicon = SoC с
unified memory; GPU и Neural Engine встроены, доступ через Metal/MLX. Любое
упоминание «дискретной GPU / Nvidia / VRAM» было бы ложью — в коде только
Metal (`hevc_videotoolbox`, llama.cpp Metal, MLX). Не выдумывать.

Что реально грузит железо (из кода):
- **MLX-Whisper** — дефолтная модель `whisper-large-v3-turbo` (`config.py:77`).
  Large-v3-turbo держит модель в unified memory; инференс на GPU/ANE через MLX.
- **Moondream 2 vision** — `llama-cpp-python` Metal, `n_gpu_layers=-1` (все слои
  на GPU). ВАЖНО: дефолтные файлы — **f16**, не Q4 (`config.py:127-128`:
  `moondream2-text-model-f16.gguf` + `moondream2-mmproj-f16.gguf`), несмотря на
  docstring про Q4_K_M. f16 заметно прожорливее по памяти. По умолчанию
  `vision_enabled=False`, так что это опциональная нагрузка.
- **mediapipe** face tracker (CPU, subprocess), **ffmpeg VideoToolbox** энкод
  (аппаратный медиаблок чипа), librosa/opensmile/parselmouth аудио-анализ (CPU).

### Минимальное железо (честно)
| Ресурс | Минимум | Рекомендуется (как в README) |
|---|---|---|
| Чип | **Apple Silicon M1** (8 GB) — запустится, но MLX-whisper large-v3-turbo и тяжёлый аудио-анализ на 8 GB будут впритык; vision f16 на 8 GB рискует свопом | **M-серия, 24 GB RAM** (бенчмарк-конфиг — M5/24 GB) |
| RAM | **16 GB** реалистичный минимум для комфортной работы (large-v3-turbo + ffmpeg + браузер). 8 GB — только лёгкие ролики, vision OFF | 24 GB+ |
| Диск | Несколько ГБ под зависимости (`.venv`, MLX/whisper-модель скачивается, Moondream GGUF f16 ~несколько ГБ при vision ON) + место под видео: `APP_MAX_UPLOAD_SIZE_MB=30720` (**30 GB** на загрузку) + артефакты/прокси-рендеры в `data/`. Закладывать **20–50 GB свободно**, на длинные видео больше | SSD, чем больше тем лучше |
| Сеть | Обязательна — LLM-пайплайн (Gemini и т.п.) всегда облачный; модели качаются с HuggingFace при первом запуске | — |

**Деградация на слабом железе (честно):** 8 GB M1 → возможен своп/OOM на
длинных видео и при vision ON; локальный STT работает, но медленнее. Нет MLX
(=не Apple Silicon) → локального STT нет совсем, только Deepgram cloud.

---

## 4. Иконка (.icns) — брендбук «самурай, золото на чёрном»

Палитра из `apps/frontend/src/globals.css` (брендбук 色の道 «латунь на чёрном лаке»):
- Фон **Kuro #0A0A0A** (не чистый чёрный — чистый чёрный/белый запрещены брендбуком).
- Sumi `#1A1A1A` (вторичный фон), акцент — **Kinzoku (золото/латунь)**, ≤25% площади, золото никогда не фон.
- Шрифт заголовков: Noto Serif JP.

Концепт иконки: тёмный фон Kuro, золотой самурайский знак/моно по центру
(тонкая золотая линия-обводка, не залитый прямоугольник — как в дизайн-системе
«свечение через линию»). Без эмодзи-клише.

### Генерация .icns (нативный путь, без сторонних либ)
1. Подготовить мастер PNG **1024×1024** (например `icon-1024.png`).
2. Собрать `.iconset` со всеми размерами и `@2x`, затем `iconutil`:

```bash
mkdir Reelibra.iconset
sips -z 16 16     icon-1024.png --out Reelibra.iconset/icon_16x16.png
sips -z 32 32     icon-1024.png --out Reelibra.iconset/icon_16x16@2x.png
sips -z 32 32     icon-1024.png --out Reelibra.iconset/icon_32x32.png
sips -z 64 64     icon-1024.png --out Reelibra.iconset/icon_32x32@2x.png
sips -z 128 128   icon-1024.png --out Reelibra.iconset/icon_128x128.png
sips -z 256 256   icon-1024.png --out Reelibra.iconset/icon_128x128@2x.png
sips -z 256 256   icon-1024.png --out Reelibra.iconset/icon_256x256.png
sips -z 512 512   icon-1024.png --out Reelibra.iconset/icon_256x256@2x.png
sips -z 512 512   icon-1024.png --out Reelibra.iconset/icon_512x512.png
cp                icon-1024.png      Reelibra.iconset/icon_512x512@2x.png
iconutil -c icns Reelibra.iconset -o Reelibra.icns
```

`sips` и `iconutil` — встроены в macOS, ничего ставить не нужно.

### Встраивание в .app
- `.app/Contents/Resources/Reelibra.icns` + ключ `CFBundleIconFile` (= `Reelibra`)
  в `Info.plist`.
- Если иконка не обновляется в Finder: `touch Reelibra.app && killall Finder`.

---

## 5. Дистрибуция — .app vs .command

Текущий запуск (`run.sh`): `uv sync` (backend) + `pnpm install`/`pnpm dev` (frontend Vite)
+ preflight kill портов 8000/3000 + параллельный старт uvicorn + Vite, открывается
в браузере на `localhost:3000`. То есть это **dev-двусервисный запуск с внешними
зависимостями (uv, pnpm, ffmpeg/brew)** — не самодостаточный бинарь.

**Честная оценка вариантов:**

| Вариант | Реалистичность | Комментарий |
|---|---|---|
| **`.command` + папка релиза** | ✅ Рекомендуется для v1 | Двойной клик по `Reelibra.command` запускает обёртку над `run.sh`, ставит deps, открывает браузер. Прозрачно, легко чинить. Минус — Gatekeeper ругнётся на неподписанный скрипт (right-click → Open) |
| **`.app`-бандл (обёртка-launcher)** | ⚠️ Средне | `.app`, который внутри зовёт тот же скрипт; даёт иконку и «нативный» вид. Но это всё ещё shell-launcher, не self-contained. Нужна `.icns` (см. п.4) |
| **Полностью упакованный self-contained `.app`** | ❌ Дорого / не сейчас | Backend Python + MLX/llama.cpp + ffmpeg + frontend в одном подписанном/нотаризованном бандле — это PyInstaller/py2app + сборка ffmpeg + Apple notarization. Большой отдельный проект, MLX/Metal wheels усложняют. Не для первого релиза |

### Внешние зависимости, которые лаунчер обязан проверить/поставить
`run.sh` уже требует: **`uv`**, **`pnpm`** (через npm), **`ffmpeg`** (`brew install ffmpeg`).
Их на чистом маке нет — лаунчер должен их детектить и либо ставить, либо честно
сказать как поставить. ffmpeg с VideoToolbox — это системный ffmpeg из Homebrew.

### Структура релиза (предложение)
```
Reelibra-macOS/
├── Reelibra.command        # двойной клик → запуск (обёртка run.sh)
├── Reelibra.app/           # опционально: launcher .app с .icns
├── app/                    # apps/ (backend + frontend) или git-clone при первом старте
├── .env.example
└── README-START.txt        # «нужен Apple Silicon + macOS 14+, при первом старте качаются модели»
```

### Скачивание с GitHub
- GitHub **Release** с zip-архивом папки релиза (а не raw clone) — обычный путь.
- Первый запуск: качаются Python-deps (uv), node-deps (pnpm), MLX-whisper модель
  и (если vision ON) Moondream GGUF с HuggingFace — **нужен интернет и время**.
- Gatekeeper: неподписанный `.command`/`.app` → пользователь делает right-click →
  Open один раз. Честно предупредить в README, либо в будущем подписать/нотаризовать.

---

## TL;DR (честно)
- **ОС:** macOS 14+ (минимум 13), Python 3.12 ровно.
- **Платформа:** Apple Silicon ONLY. На Intel локальный STT (MLX) не работает —
  продукт фактически не для Intel.
- **Железо:** Mac без дискретной GPU (и не нужна — Metal/ANE/unified memory).
  Минимум M1/16 GB реалистично, бенчмарк-конфиг M5/24 GB. Диск: 20–50 GB
  (upload-лимит 30 GB + модели + артефакты). Сеть обязательна (cloud-LLM + загрузка моделей).
- **Иконка:** `.icns` через `sips`+`iconutil`, стиль Kuro #0A0A0A + золото Kinzoku, самурайский знак.
- **Упаковка:** для v1 — `.command` (+ опц. `.app` launcher с иконкой), НЕ self-contained;
  требует uv/pnpm/ffmpeg на машине; дистрибуция через GitHub Release zip.
