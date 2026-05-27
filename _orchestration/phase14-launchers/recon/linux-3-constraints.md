# Reelibra (videomaker) — Linux: железо, совместимость, упаковка

Честная оценка из РЕАЛЬНОГО кода (`apps/backend/pyproject.toml`, `.env.example`, `src/videomaker/services/*`). Заявления README про "только macOS Apple Silicon" — для Linux разбираем что реально работает, что ломается, что нужно допилить.

---

## 0. Главный вердикт честно

Проект написан под **macOS Apple Silicon** и Linux-портируемость частичная:

- ffmpeg-энкодинг **уже портирован** на Linux (`encoder_support.py` — runtime-детект VideoToolbox → фолбэк на libx264/libx265). Это работает.
- STT по умолчанию (`stable_ts_mlx` / `mlx_whisper`) **НЕ работает на Linux** — MLX это Apple-only фреймворк. На Linux обязателен `deepgram` (cloud, нужен ключ). См. §2.
- `mlx-whisper>=0.4.2` и `stable-ts[mlx]>=2.19` — **жёсткие зависимости** в `pyproject.toml` без platform-маркеров. `uv sync` на Linux попытается их поставить. mlx-whisper ставится (чистый Python wheel), но при импорте/инференсе на Linux упадёт (нет Metal). Это блокер для дефолтного транскрайбера — НЕ для установки.
- Vision (Moondream через llama-cpp-python) и mediapipe — кросс-платформенны, но дефолтный wheel = CPU-only (медленно). См. §2.

**Итог:** на Linux Reelibra запускается, но дефолтный STT надо переключить на Deepgram (или собрать CPU-whisper руками), а ускорение vision/llama требует ручной пересборки под GPU.

---

## 1. ОС: минимальные дистрибутивы

| Параметр | Значение |
|---|---|
| Архитектура | **x86_64** (рекомендовано). ARM64 (aarch64) — возможен, но llama-cpp/mediapipe wheels под ARM-Linux менее проверены |
| Python | **3.12** строго (`requires-python = ">=3.12,<3.13"`), ставится через `uv` |
| glibc | **≥ 2.35** (порог mediapipe 0.10.x manylinux_2_35 + onnxruntime + opencv wheels) |
| Node.js | **≥ 20**, pnpm |
| ffmpeg | **≥ 7** (README требует ≥7; на Linux нужны libx264/libx265, NOT videotoolbox) |

Минимальные дистрибутивы (по glibc ≥ 2.35):
- **Ubuntu 22.04 LTS** (glibc 2.35) — минимум. **Ubuntu 24.04 LTS** (glibc 2.39) — рекомендовано.
- **Debian 12 Bookworm** (glibc 2.36) — OK.
- **Fedora 37+** (glibc 2.36+) — OK.
- **Arch / EndeavourOS** (rolling, glibc свежий) — OK.
- ❌ Ubuntu 20.04 (glibc 2.31), Debian 11 (2.31), CentOS 7/8 — **слишком старый glibc** для современных ML-wheels.

ffmpeg: дистра-пакет (`apt install ffmpeg` / `dnf install ffmpeg` из RPMFusion / `pacman -S ffmpeg`) обычно собран с libx264/libx265 — этого достаточно (код сам детектит энкодеры).

---

## 2. ЖЕЛЕЗО ЧЕСТНО (из кода)

### Нужна ли дискретная видеокарта? — НЕТ для запуска, ЖЕЛАТЕЛЬНА для скорости.

Разбор по компонентам где код реально трогает GPU/CPU:

**a) ffmpeg энкодинг (`encoder_support.py`, `filter_graph_builder.py`, `export_presets.yaml`)**
- Пресеты просят `h264_videotoolbox`/`hevc_videotoolbox` → на Linux `resolve_video_codec()` фолбэчит на **libx264/libx265 (CPU software encode)**.
- Код **НЕ использует** nvenc/vaapi/qsv. Hardware-ускорение энкодинга на Linux НЕ реализовано. Значит энкодинг рилсов идёт на **CPU** — упор в количество ядер, а не в видеокарту.
- Вывод: для ffmpeg дискретная карта бесполезна (код её не задействует). Чем больше CPU-ядер — тем быстрее рендер.

**b) STT / транскрипция (`transcribers/factory.py`)**
- Дефолт `stable_ts_mlx` и fallback `mlx_whisper` — **Apple MLX, Metal-only. На Linux не работают** (упадут при инференсе, нет CUDA-пути в коде).
- Рабочий вариант на Linux: **`deepgram` (cloud, nova-3)** — требует `DEEPGRAM_API_KEY`, считает в облаке, локального железа НЕ грузит.
- Локального CPU/CUDA-whisper в коде **НЕТ** (нет faster-whisper / openai-whisper в deps). Чтобы STT работал локально на Linux — надо допиливать новый backend. Из коробки: **Linux STT = только Deepgram (cloud + ключ).**

**c) Vision / Moondream (`vision/moondream_local.py`, `vision/factory.py`, `config.py`)**
- llama-cpp-python с `n_gpu_layers=-1` (config default `vision_n_gpu_layers=-1` → все слои на GPU).
- На macOS prebuilt wheel = Metal автоматом. **На Linux дефолтный PyPI wheel `llama-cpp-python` = CPU-only.** `n_gpu_layers=-1` без CUDA-сборки молча идёт на CPU (медленно, но работает).
- Для GPU-ускорения на Linux нужна **ручная пересборка**: `CMAKE_ARGS="-DGGML_CUDA=on" pip install llama-cpp-python` (Nvidia/CUDA) или `-DGGML_HIPBLAS=on` (AMD/ROCm). Vision Layer — опциональная фича (toggle), можно держать на CPU или выключить.

**d) mediapipe (`face_tracker.py`, `object_tracker.py`)**
- Face/object detection. mediapipe на Linux = **CPU/CPU-GL**, дискретную карту по сути не использует. Face tracker по умолчанию **выключен** (`face_tracker_enabled=False` — GL context + блокировка worker'а).

**e) LLM-анализ (`Gemini` дефолт, Anthropic/OpenAI/Zhipu опц.)** — **полностью cloud**. Локального железа 0. Нужен `GEMINI_API_KEY`.

### Минимальные требования железа (честно)

| Ресурс | Минимум | Комфорт | Почему |
|---|---|---|---|
| CPU | 4 ядра x86_64 | 8+ ядер | libx264 software-энкодинг + ffmpeg фильтры = CPU-bound |
| RAM | 8 GB | 16 GB | Moondream Q4 GGUF в RAM (CPU-режим) + ffmpeg + onnxruntime VAD; README таргет 24 GB на M5 |
| Диск | 10 GB | 20+ GB | модели (Moondream GGUF ~1.5–2 GB, whisper turbo если local), артефакты, прокси-видео, аплоады (лимит 30 GB на загрузку) |
| VRAM/дискретка | **НЕ нужна** | 6–8 GB Nvidia (опц.) | только если пересобирать llama-cpp под CUDA для ускорения Vision Layer |

**От какой видеокарты осмысленно:** только если активно гоняешь Vision Layer локально — Nvidia RTX с **≥6 GB VRAM** (Moondream Q4 влезает в 2–3 GB, запас на контекст) после пересборки llama-cpp с `-DGGML_CUDA=on`. AMD — ROCm-сборка (`-DGGML_HIPBLAS=on`), официально хуже поддержана. **Для базового сценария (Deepgram STT + Gemini LLM + libx264 энкод) дискретка не даёт ничего** — узкое место CPU и сеть.

---

## 3. Иконка и .desktop

**Брендбук (`apps/frontend/src/globals.css`):** «色の道 — латунь на чёрном лаке», самурайский. Палитра:
- Kuro #0A0A0A (чёрный фон), Sumi #1A1A1A
- Kinzoku #C9A84C (латунь/золото — главный акцент), Kogane #E8C547 (блик), Dō #B87333 (медь)
- Шрифт-акцент: Noto Serif JP (`@fontsource/noto-serif-jp`)

**Реальных иконок в репо НЕТ.** Есть только дефолтные Vite-заглушки (`apps/frontend/public/{file,globe,window}.svg`) — не брендовые. Нужно **создать с нуля**: самурайский мотив, золото #C9A84C на чёрном #0A0A0A.

**.desktop файл (freedesktop spec):**
```ini
[Desktop Entry]
Type=Application
Name=Reelibra
Comment=Local long-video to vertical reels cutter
Exec=/opt/reelibra/run.sh
Icon=reelibra
Terminal=false
Categories=AudioVideo;Video;
```

**Формат иконок Linux:** не один файл, а набор PNG по размерам в hicolor theme + опционально master SVG:
```
~/.local/share/icons/hicolor/16x16/apps/reelibra.png
                              .../32x32/apps/reelibra.png
                              .../48x48/apps/reelibra.png
                              .../128x128/apps/reelibra.png
                              .../256x256/apps/reelibra.png
                              .../512x512/apps/reelibra.png
~/.local/share/icons/hicolor/scalable/apps/reelibra.svg   # масштабируемый
```
`Icon=reelibra` (без расширения/пути) — резолвится по theme. SVG предпочтителен как мастер (HiDPI), PNG нужны для DE без хорошего SVG-рендера. После установки — `gtk-update-icon-cache` / `update-desktop-database`.

---

## 4. Дистрибуция

Reelibra — это **не один бинарь**, а связка backend (Python/uv + ffmpeg + ML-модели) + frontend (Vite/React, статика после `pnpm build`). Это меняет стратегию упаковки.

### Вариант A (рекомендовано): tar.gz + .desktop + install-скрипт
Из-за тяжёлых нативных зависимостей (llama-cpp, mediapipe, onnxruntime, opencv) и системного ffmpeg — честнее распространять как разворачиваемый bundle.

Структура релиза:
```
reelibra-vX.Y.Z-linux-x86_64.tar.gz
├── apps/backend/         # исходники + pyproject.toml (uv sync на месте)
├── apps/frontend/dist/   # пре-собранная статика (pnpm build заранее)
├── run.sh                # запуск (правка: проверять ffmpeg/uv, как сейчас)
├── install.sh            # копирует .desktop + иконки в ~/.local/share, симлинк в ~/.local/bin
├── reelibra.desktop
├── icons/hicolor/.../reelibra.{png,svg}
└── README-linux.md       # требования: glibc≥2.35, ffmpeg≥7, DEEPGRAM_API_KEY для STT
```
- Зависимости (uv `.venv`, pnpm) ставятся на первом запуске `run.sh` — как сейчас. Минус: первый запуск долгий, нужен интернет + компилятор для некоторых wheels.
- Линукс-правки `run.sh`: убрать `brew install` хинты → `apt/dnf/pacman`, переключить дефолтный transcriber на `deepgram` если нет MLX.

### Вариант B: AppImage — проблематично
AppImage хорош для single-binary GUI-приложений. Здесь:
- ❌ ffmpeg ≥7 как системная зависимость (можно вкомпилить, но раздувает).
- ❌ Python-venv + нативные ML-wheels + GGUF-модели (1.5–2 GB) → AppImage станет огромным и хрупким (glibc-привязка к build-хосту).
- ❌ llama-cpp пересборка под GPU невозможна внутри замороженного AppImage.
- Вывод: **AppImage не подходит** для этого стека. Только если завернуть весь backend в Docker и сделать AppImage-launcher для браузера — оверинжиниринг.

### Вариант C (альтернатива): Docker Compose
Самый честный для воспроизводимости (фиксирует glibc/ffmpeg/Python), но это не «.desktop-приложение», а сервис. Подходит если целевая аудитория — техническая. GPU-проброс (`--gpus all`) для llama-cpp CUDA возможен.

**Скачивание с GitHub:** GitHub Releases → артефакт `reelibra-vX.Y.Z-linux-x86_64.tar.gz`. Пользователь: распаковал → `./install.sh` (иконка+.desktop) → запуск из меню приложений или `./run.sh`. Vision GPU-сборка — отдельная инструкция в README (опционально).

---

## TL;DR
- **Distro:** Ubuntu 22.04+ (glibc ≥2.35), x86_64, Python 3.12, ffmpeg ≥7, Node 20+.
- **Железо:** дискретка НЕ нужна (код не юзает nvenc/vaapi/CUDA-whisper). CPU-bound (libx264) + cloud (Gemini/Deepgram). 4 ядра/8 GB минимум, 8 ядер/16 GB комфорт. GPU (Nvidia ≥6 GB) осмысленна ТОЛЬКО при ручной пересборке llama-cpp под CUDA для Vision Layer.
- **Блокер Linux:** дефолтный STT `stable_ts_mlx`/`mlx_whisper` = Apple-only, не работает. На Linux обязателен Deepgram (cloud+ключ); локального CPU-whisper в коде нет.
- **Иконка:** реальных нет (только Vite-заглушки). Создать hicolor PNG-набор + SVG, самурай золото #C9A84C на чёрном #0A0A0A. `Icon=reelibra` в .desktop.
- **Упаковка:** tar.gz + install.sh + .desktop (AppImage не подходит — тяжёлый ML-стек + системный ffmpeg + GPU-пересборка). Релиз через GitHub Releases.
