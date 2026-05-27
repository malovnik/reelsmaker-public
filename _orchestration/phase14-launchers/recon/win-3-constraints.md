# Windows: честная оценка совместимости, железа, упаковки

Анализ реального стека Reelibra (`apps/backend/pyproject.toml`, `apps/frontend/package.json`, `.env.example`, services). README прямо заявляет цель «macOS на Apple Silicon (оптимизировано под M5, 24 GB RAM)». Ниже — что из этого реально едет на Windows и какой ценой.

---

## TL;DR (самое честное)

Это **Mac-first приложение**. На Windows оно НЕ запустится «из коробки» по двум жёстким причинам:

1. **`mlx-whisper` и `stable-ts[mlx]` — Apple-only.** MLX это фреймворк Apple для Apple Silicon. На Windows эти колёса (wheels) физически не существуют → `uv sync` упадёт на резолве зависимостей. А именно `stable_ts_mlx` — это **дефолтный STT-бэкенд** (`available_transcribers` в `core/config.py`).
2. **Локальный STT на Windows отсутствует как класс.** В `transcribers/factory.py` зарегистрированы ровно три бэкенда: `stable_ts_mlx`, `mlx_whisper` (оба MLX/Apple) и `deepgram` (облако). Нет ни `faster-whisper`, ни `whisper.cpp`, ни `openai-whisper`. Значит на Windows транскрипция = **только Deepgram (облако, платный ключ)**. Без `DEEPGRAM_API_KEY` приложение не сможет распознать речь вообще.

Вывод: для честного Windows-релиза нужно либо (а) выпилить MLX-зависимости из `pyproject.toml` и поставлять с обязательным Deepgram, либо (б) добавить CPU-бэкенд `faster-whisper`. Без правки кода/зависимостей Windows-сборки нет. README не должен обещать Windows, пока это не сделано.

---

## 1. ОС: с какой версии Windows реально

**Минимум реально: Windows 10 (64-bit, версия 1809+) или Windows 11.**
Архитектура: **только x64.** ARM (Windows on ARM) — нет (нет колёс под win-arm64 у mediapipe/llama-cpp/onnxruntime; MLX и так не едет).

Обоснование по версиям компонентов:
- **Python 3.12** (жёсткий пин `>=3.12,<3.13`). CPython 3.12 официально требует Windows 8.1+, но реальные wheels тяжёлых пакетов ниже описанного не тестируются. Win7/8 — **нет** (Python 3.12 их не поддерживает, end-of-support).
- **`numpy>=2.1`, `onnxruntime>=1.19`, `mediapipe>=0.10.33`, `opencv-python-headless>=4.13`, `llama-cpp-python>=0.3.2`** — все поставляют Windows-колёса только под x64, минимальная цель de-facto Windows 10. `mediapipe` на Windows исторически капризен (нужен свежий MSVC-рантайм, Visual C++ Redistributable 2015–2022).
- **Node.js ≥ 20** (README; frontend на Vite 7 + React 19) — Vite 7 требует Node 20.19+/22.12+. Node 20+ официально только Windows 10+.
- **ffmpeg ≥ 7** — не часть pip, ставится отдельно (см. ниже). Windows-билды ffmpeg (gyan.dev / BtbN) — Win10+.

Итог: **Windows 10 x64 (1809+) — нижняя планка, Windows 11 x64 — рекомендуемо.**

---

## 2. Железо ЧЕСТНО (из кода, ничего не выдумано)

### Нужна ли дискретная видеокарта?

**Нет, не обязательна. Всё критичное работает на CPU.** Но есть нюансы по двум подсистемам.

**ffmpeg энкодинг — на Windows идёт по CPU (software).**
`services/encoder_support.py` знает ровно два аппаратных кодека — `hevc_videotoolbox` и `h264_videotoolbox` (Apple VideoToolbox). Дефолт в `renderer.py` — `hevc_videotoolbox`. На Windows VideoToolbox отсутствует, и `resolve_video_codec()` уводит в software-фолбэк **libx265 / libx264** (CPU).
**NVENC (Nvidia), QSV (Intel), AMF (AMD) в коде НЕ используются вообще** — кода под них нет. То есть «GPU-ускорение энкода» на Windows = 0, рендер финального HEVC жмётся процессором. Это медленнее, чем на Mac с VideoToolbox, и грузит CPU. Дискретная карта тут не помогает (код её не зовёт).

**Vision-слой (Moondream 2 GGUF через `llama-cpp-python`) — опционален и по умолчанию ВЫКЛЮЧЕН.**
`core/config.py`: `vision_enabled: bool = False`. По умолчанию vision не используется → пайплайн работает без него. Если включить:
- дефолт `vision_n_gpu_layers = -1` (все слои на GPU). На Mac это Metal. На Windows стандартное колесо `llama-cpp-python` собрано **без CUDA → пойдёт на CPU** (или упадёт пытаясь оффлоадить). Для реального GPU-ускорения нужно ставить CUDA-сборку колеса вручную (отдельный wheel index) + Nvidia GPU.
- модель грузится в RAM/VRAM ~5 GB (комментарий в `vision/factory.py`: «llama.cpp instance тяжёлый ~5GB RAM»).
- Если GPU нет/CPU-колесо — выставить `VISION_N_GPU_LAYERS=0` (поле зажато `ge=-1`), тогда честный CPU-режим (`backend="cpu"` в health). Иначе vision просто оставить выключенным (дефолт).

**mediapipe (face/object detection) — CPU.**
`services/face_tracker.py` использует Tasks API (`FaceDetector`) с tflite-моделью, авто-скачивается с googleapis. GPU-delegate в коде не настраивается → CPU. Модель лёгкая.

**onnxruntime (silero-vad) — CPU** (зависимость `onnxruntime`, не `onnxruntime-gpu`).

**LLM (основная «мозговая» работа) — облако, не железо.**
Gemini / Claude / OpenAI / Zhipu по API-ключам. CPU/GPU локально на это не тратятся. Это ключевой момент: «ум» приложения вынесен в облако, локальной LLM нет.

### Что от какой видеокарты осмысленно

- **Без vision-слоя (дефолт): дискретная карта НЕ нужна.** Узкое место — CPU (software HEVC-энкод libx265 + аудио-анализ librosa/opensmile/parselmouth).
- **С vision-слоем + желанием ускорить: Nvidia с CUDA**, и только если поставить CUDA-сборку `llama-cpp-python` вручную. Осмысленно от **RTX 3060 12 GB** и выше (модель ~5 GB + контекст). AMD/Intel дискретки коду бесполезны (нет ROCm/oneAPI-пути).
- Энкод финального видео карта не ускорит при текущем коде в любом случае.

### Минимальные требования (реальные)

| Ресурс | Минимум | Комфорт |
|---|---|---|
| CPU | 4 ядра x64 | 8+ ядер (software HEVC-энкод + параллельный аудио-анализ — CPU-bound) |
| RAM | 8 GB (vision off) | 16–24 GB (vision on грузит ~5 GB + ffmpeg/librosa) |
| Диск | 5 GB (код+deps+ffmpeg) | + место под видео/артефакты/прокси (`data/`), легко десятки ГБ; `APP_MAX_UPLOAD_SIZE_MB=30720` = 30 GB на один аплоад |
| GPU | не нужна (CPU-путь) | Nvidia RTX 3060 12 GB+ только если включают vision и ставят CUDA-wheel |
| VRAM | 0 (vision off) | ~6 GB (vision on, CUDA-wheel) |
| Сеть | обязательна | LLM (Gemini/Claude/...) + STT (Deepgram) — всё облако |

**Дополнительно для Windows-сборки тяжёлых пакетов:** Microsoft Visual C++ Redistributable 2015–2022 (x64) — для mediapipe/llama-cpp/onnxruntime рантайма.

---

## 3. Иконка на .exe / .bat / ярлык

Приложение — это не один .exe (это FastAPI-бэкенд + Vite-фронт). На Windows запуск реалистично оформляется через **.bat / .cmd лаунчер** (поднимает `uv run uvicorn` + `pnpm`/статику и открывает браузер). У .bat своей иконки нет — иконку вешают одним из способов:

**Вариант A (рекомендую): ярлык .lnk с иконкой.**
.bat нельзя «иконкой украсить» напрямую, но ярлык на него — можно. Генерируется PowerShell-скриптом при установке:
```powershell
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut("$env:USERPROFILE\Desktop\Reelibra.lnk")
$sc.TargetPath = "$PSScriptRoot\start-reelibra.bat"
$sc.WorkingDirectory = "$PSScriptRoot"
$sc.IconLocation = "$PSScriptRoot\assets\reelibra.ico"
$sc.Save()
```
Кладём в релиз `create-shortcut.ps1` + `assets/reelibra.ico`. Пользователь раз запускает → на рабочем столе фирменный ярлык.

**Вариант B: собрать реальный .exe-лаунчер с встроенной иконкой.**
Тонкий launcher на Python через PyInstaller: `pyinstaller --onefile --icon reelibra.ico --noconsole launcher.py`. Иконка встроится в PE-ресурсы exe. Дороже (нужен PyInstaller в сборке), но получается «настоящий» брендированный .exe. Для MVP избыточно — хватит варианта A.

**Где взять .ico (брендбук: самурайский стиль, золото на чёрном).**
- Сгенерировать простую: чёрный квадрат + золотой символ (катана/мон/первая буква «R» золотом #C9A227 на #0A0A0A). Multi-resolution .ico (16/32/48/256 px) собирается из PNG: `ffmpeg -i icon.png icon.ico` (ffmpeg уже в стеке) или через Pillow (`pillow` уже в зависимостях):
```python
from PIL import Image
img = Image.open("reelibra_1024.png")
img.save("reelibra.ico", sizes=[(16,16),(32,32),(48,48),(256,256)])
```
- Положить в `assets/reelibra.ico` рядом с лаунчером.

---

## 4. Дистрибуция (zip / GitHub release)

**Реальность:** это исходники + зависимости, не self-contained бинарь. Два честных пути.

**Путь 1 — клон + установка (для разработчиков / технических):**
GitHub → `git clone` → запуск `setup-windows.bat`:
```
uv sync            (упадёт пока в pyproject есть MLX — см. TL;DR; нужна Windows-ветка зависимостей)
pnpm install && pnpm build   (в apps/frontend)
```
Требует предустановленных: Git, uv, Node 20+, ffmpeg 7+ (в PATH), VC++ Redist.

**Путь 2 — zip-релиз (для конечного пользователя), структура:**
```
Reelibra-win-x64-vX.Y.Z.zip
├── start-reelibra.bat          # лаунчер: активирует .venv, поднимает backend+frontend, открывает браузер
├── setup-windows.bat           # первичная установка (uv sync, pnpm build) — один раз
├── create-shortcut.ps1         # создаёт ярлык на рабочем столе с иконкой
├── assets/
│   └── reelibra.ico            # фирменная иконка (золото на чёрном)
├── apps/
│   ├── backend/                # исходники + pyproject (Windows-вариант без MLX)
│   └── frontend/               # исходники + собранный dist/
├── .env.example                # шаблон ключей (DEEPGRAM обязателен, GEMINI обязателен)
├── README-WINDOWS.md           # ЧЕСТНЫЕ требования: Win10 x64, ffmpeg, ключи, нет локального STT
└── tools/                      # опционально: portable ffmpeg.exe чтобы не требовать ручной установки
```
Рекомендация: **в zip класть portable `ffmpeg.exe`** (gyan.dev essentials build) в `tools/` и прописывать в PATH из .bat — иначе 90% пользователей споткнутся на «ffmpeg not found».

**Как пользователь скачивает:** GitHub → Releases → asset `Reelibra-win-x64-vX.Y.Z.zip` → распаковать → один раз `setup-windows.bat` → `create-shortcut.ps1` → дальше запуск ярлыком. Tag-релизы через `gh release create`.

---

## Честные предупреждения для README-WINDOWS

1. **Локальной транскрипции на Windows нет** — нужен платный Deepgram-ключ (mlx-whisper Apple-only). Либо ждать CPU-бэкенда (faster-whisper) в коде.
2. **Локальной LLM нет** — нужен ключ Gemini (или Claude/OpenAI/Zhipu). Без интернета приложение бесполезно.
3. **Рендер видео на Windows жмётся CPU (libx265), без аппаратного ускорения** — медленнее, чем на Mac. NVENC в коде не реализован.
4. **Дискретная GPU не нужна** для дефолтного режима; полезна только при ручном включении vision-слоя с CUDA-сборкой llama-cpp.
5. **MLX-зависимости блокируют `uv sync` на Windows** — без правки `pyproject.toml` (вынос mlx в Mac-only optional-group) Windows-сборка не соберётся. Это предпосылка для любого Windows-релиза.
