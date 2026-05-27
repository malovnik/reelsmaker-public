# LAUNCHER-RECON — консолидация разведки (9 агентов, 3×3 ОС)

> Все 9 агентов независимо сошлись на критичных honesty-находках. Это вход для решения о скоупе.

## 🔴 КРИТИЧНО: текущий код запускается ТОЛЬКО на Apple Silicon Mac
`mlx-whisper` и `stable-ts[mlx]` — **жёсткие (не optional) зависимости**, импортируются на уровне модуля в `transcribers/__init__.py` + `factory.py`, дефолтный STT = `stable_ts_mlx`. MLX — фреймворк Apple, колёс под Windows/Linux/Intel НЕТ.
**Следствие:** на Windows / Linux / Intel-Mac `uv sync` падает на резолве, а даже при обходе — импорт крашит сервер на старте. **Лаунчеры для Win/Linux бессмысленны, пока это не починено в коде.** Это продуктовый блокер, не проблема скрипта.
→ Фикс: маркеры `; sys_platform == 'darwin'` на MLX-пакеты + ленивые импорты MLX-бэкендов + кросс-платформенный дефолтный STT.

## 🔴 Win7/8 — невозможно (честно)
Python запинён `>=3.12,<3.13`; mediapipe, llama-cpp, onnxruntime, numpy 2.1, Node 20 — ни один не поддерживает Win7/8. **Честный минимум: Windows 10 x64 (1809+).**

## 🔴 GPU — НЕ нужен (противоречит исходному предположению)
Из кода: энкод = CPU software (libx264/x265; nvenc/vaapi/qsv в коде НЕТ). LLM = облако (Gemini). Vision (Moondream) по умолчанию ВЫКЛ; при включении нужен ручной CUDA-rebuild. mediapipe/VAD = CPU.
**Дискретная видеокарта НЕ требуется.** README должен сказать это честно (а не «нужна дискретная карта»).

## Честная матрица платформ (как есть сейчас vs после фикса STT)
| Платформа | STT локально | Работает as-is | После фикса |
|-----------|--------------|----------------|-------------|
| macOS Apple Silicon (M1+) | MLX ✅ | ✅ | ✅ полноценно |
| macOS Intel | ❌ MLX нет | ❌ краш | только cloud STT (Deepgram) |
| Windows 10+ x64 | ❌ MLX нет | ❌ краш | cloud STT, либо faster-whisper |
| Linux x86_64 (glibc≥2.35) | ❌ MLX нет | ❌ краш | cloud STT, либо faster-whisper |

## Honest железо (из кода, для README)
- **GPU дискретный — НЕ нужен.** ffmpeg-энкод на CPU. LLM в облаке.
- Mac: Apple Silicon (unified memory/Metal/ANE), без Nvidia. Минимум M1/16GB.
- Win/Linux: 4 ядра / 8GB / ~10GB диск (+ до 30GB на аплоады). Комфорт 8 ядер/16GB (энкод CPU-bound).
- Сеть обязательна (cloud-LLM + скачивание моделей при первом старте).
- Vision GPU (опц.): Nvidia ≥RTX 3060 12GB + ручная CUDA-сборка llama-cpp.

## Стратегия bootstrap (консенсус, после фикса STT)
- **Портативные бандлы в user-space, НЕ пакетные менеджеры**: python-build-standalone 3.12 + portable Node 20 + static ffmpeg + uv + offline wheelhouse. ~1.3-1.6GB распакованный.
- Двойной клик: **Win** `reelibraWIN.cmd`→`launcher.ps1` (не .exe/SmartScreen, не голый .ps1); **Mac** `reelibraMAC.app`/`.command` + обход Gatekeeper (right-click Open, ad-hoc codesign); **Linux** `.desktop` + разовый `install.sh` (двойной клик по .sh открывает редактор).
- Прогресс: нумерованные шаги в консоли/нативном окне («Проверяю Python… ОК», «Освобождаю порт 8000…»).

## Диагностика + чистка висяков (консенсус)
- Бэкенд САМ лечит БД-stale (`reset_stale_running_jobs` в lifespan), Publer uploading→queued, proxy `.lock` по mtime>1800с. **Лаунчер БД/`-wal`/`-shm`/data НЕ трогает.**
- Лаунчер на уровне ОС: убить зависшие uvicorn/node/ffmpeg (Win `taskkill /T`, Mac/Linux `lsof`/`ss`+pgrep, TERM→5с→KILL), освободить порты 8000/3000 (Vite `strictPort` — занятый порт фатален), удалить `.partial`/`.tmp`/orphan-`.lock`. PID-файл `data/.run/*.pid` добавить для детекта жёсткого закрытия.
- Каждый старт: проверка наличия/версий (python3.12/node20/ffmpeg/uv/.venv/node_modules) → есть ОК, нет → доустановка с прогрессом.

## Иконки
В репо иконок нет (только Vite-заглушки). Создать в стиле брендбука (Kuro #0A0A0A + Kinzoku #C9A84C золото, самурайский мотив): `.ico` (Win, Pillow уже в deps), `.icns` (Mac, sips+iconutil), PNG hicolor + SVG (Linux .desktop Icon=).

## Дистрибуция
GitHub Releases: per-OS zip/tar.gz с лаунчером + portable tools/ + .env.example + per-OS README. (clone тоже работает, но Releases чище для не-разработчиков.)
