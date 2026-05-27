# Reelibra — macOS Bootstrap Recon (mac-1)

Цель: пользователь скачал → распаковал → 2 клика по `reelibraMAC` → само проверилось/доустановилось с прогрессом → работает. Mac «с нуля», без brew/uv/node.

---

## 0. TL;DR (честная картина)

- **Apple Silicon (M1–M4) — целевая и единственная полноценная платформа.** Весь ML-стек проекта (`mlx-whisper`, `stable-ts[mlx]`, llama-cpp Metal, videotoolbox) рассчитан на arm64+Metal.
- **Intel-маки (x86_64) НЕ поддерживаются «из коробки».** `uv sync` на Intel **упадёт на этапе резолва** — у `mlx-whisper` и `stable-ts[mlx]` нет x86_64-колёс (MLX = arm64-only, см. источники). Это не «медленнее», это «не установится вообще» без правки `pyproject.toml`.
- **Рекомендуемая стратегия bootstrap:** портативный самодостаточный бандл = **python-build-standalone (через uv) + node-портабл + статический ffmpeg**, БЕЗ Homebrew. uv сам тянет нужный CPython 3.12, не трогая системный Python.
- **Двойной клик:** `.app`-бандл (`reelibraMAC.app`), внутри которого `Contents/MacOS/reelibraMAC` = bash-лаунчер. Прогресс — нативное окно через `osascript` (progress dialog) + Terminal как fallback-лог.
- **Gatekeeper:** самодельный неподписанный бандл → нужен обход. Лучший UX без платного Apple Developer ID — снять карантин самим лаунчером первым делом (`xattr -dr com.apple.quarantine`), либо инструкция right-click → Open. Идеально — ad-hoc подпись + нотаризация, но это требует Apple Developer аккаунт ($99/год).

---

## 1. Что нужно и что уже есть на маке

| Компонент | Версия (из проекта) | Есть на чистом маке? | Стратегия |
|-----------|--------------------|--------------------|-----------|
| **Python** | `>=3.12,<3.13` (строго 3.12) | macOS 14/15 системного Python **нет** (Apple убрал `/usr/bin/python2`; `python3` = заглушка, ведёт к Xcode CLT). **Нельзя полагаться.** | `uv` ставит CPython 3.12 standalone сам |
| **uv** | `uv_build>=0.9.11` (build backend) | Нет | Bootstrap через официальный установщик или вендорить бинарь uv в бандл |
| **Node** | Vite 7 + React 19 → Node ≥20 (Vite 7 требует Node 20.19+/22.12+) | Иногда есть, версия непредсказуема | Вендорить портабл node arm64 в бандл, НЕ полагаться на системный |
| **pnpm** | `run.sh` ожидает `pnpm dev` / `pnpm install` | Нет | `corepack enable pnpm` (идёт с node) или вендорить |
| **ffmpeg** | `av>=13.1` + прямые вызовы ffmpeg CLI (рендер, encoder-детект) | Нет | Вендорить статический ffmpeg arm64 (videotoolbox-enabled билд) |

Замечание: `run.sh` сейчас написан под dev и ждёт `uv`/`pnpm`/`ffmpeg` уже в `PATH` (только `command -v ... || echo "поставь brew install"`). Для дистрибутива это надо заменить — лаунчер должен **сам доустанавливать**, а не отправлять к brew.

---

## 2. Bootstrap: портативные бандлы vs Homebrew vs python-build-standalone

### Вердикт: НЕ Homebrew

Homebrew на чистом маке:
- требует Xcode Command Line Tools (отдельный ~1.5GB GUI-инсталл, пользователь должен кликать);
- ставит в общесистемный `/opt/homebrew`, конфликтует с тем что у юзера уже могло быть;
- небыстрый, сетевозависимый, может тянуть несовместимые версии (ffmpeg «последний», node «последний»);
- противоречит принципу «скачал-распаковал-работает» (это менеджер пакетов, а не бандл).

### Рекомендация: гибрид «вендор + uv-standalone»

1. **Python** — `uv` + python-build-standalone. uv при `uv sync` сам скачивает релокируемый CPython 3.12 (astral python-build-standalone), кладёт в `~/.local/share/uv/python`, **не трогает систему**. Это самый надёжный путь: один источник истины для версии, работает offline если предварительно прогрет кэш.
   - uv-бинарь либо вендорить в бандл (`reelibraMAC.app/Contents/Resources/bin/uv`, arm64), либо ставить первым шагом установщиком `curl -LsSf https://astral.sh/uv/install.sh | sh`.
2. **Node + pnpm** — вендорить портабл **Node arm64** (`node-vXX.x-darwin-arm64.tar.gz`, распаковать в `Resources/node/`), активировать pnpm через `corepack`. Не зависеть от системного node.
3. **ffmpeg** — вендорить статический arm64 ffmpeg с включённым VideoToolbox (например, билды evermeet/osxexperts). Положить в `Resources/bin/ffmpeg`, лаунчер добавляет в `PATH`.

Преимущество: после распаковки всё локально в бандле/каталоге проекта. Сеть нужна только для (а) первого `uv sync`/`pnpm install` если зависимости не вендорены и (б) скачивания ML-моделей (whisper-large-v3-turbo с HF, Moondream GGUF). Это честный объём — модели тяжёлые, их либо вендорить (большой архив), либо качать с прогрессом при первом запуске.

### Apple Silicon vs Intel — разные бандлы?

ДА, принципиально:
- **arm64-бандл:** python-build-standalone arm64, node darwin-arm64, ffmpeg arm64-vt. ML-стек ставится как есть.
- **x86_64 (Intel):** MLX не существует под x86_64. Нужен **отдельный pyproject-профиль без mlx** (см. §4) → STT только через Deepgram (облако, нужен API-ключ) или whisper.cpp/faster-whisper CPU. Это уже не «тот же продукт». Рекомендация: **на Intel не таргетиться в v1**, показывать честное сообщение «нужен Apple Silicon».

Источники: MLX публикует только arm64 macOS wheels — на Intel `pip/uv` не найдёт дистрибутив:
- https://pypi.org/project/mlx/
- https://github.com/ml-explore/mlx/issues/10
- https://ml-explore.github.io/mlx/build/html/install.html

---

## 3. Двойной клик + прогресс + Gatekeeper

### Формат: `.app`-бандл, не голый `.command`

| Вариант | Плюсы | Минусы |
|---------|-------|--------|
| `reelibraMAC.command` (chmod +x) | проще всего сделать | открывает Terminal, выглядит «хакерски»; иконки нет; Gatekeeper всё равно блокирует |
| **`reelibraMAC.app`** (рекоменд.) | нативная иконка, дабл-клик как у обычного приложения, можно ad-hoc подписать/нотаризовать, прячет Terminal | надо собрать структуру `Contents/{MacOS,Resources,Info.plist}` |

Минимальная структура `.app`:
```
reelibraMAC.app/
  Contents/
    Info.plist                 (CFBundleExecutable=reelibraMAC, CFBundleIconFile)
    MacOS/reelibraMAC          (bash, chmod +x — реальный лаунчер)
    Resources/
      bin/{uv,ffmpeg}
      node/...
      project/... (apps/, run-logic)
      reelibra.icns
```

### Прогресс: нативное окно, Terminal — fallback-лог

- Первичный UX — **osascript progress** (без Swift, без сборки): диалоги/прогресс-бар средствами AppleScript из bash-лаунчера. Этапов мало и они предсказуемы: «Проверяю Python», «Ставлю зависимости (uv sync)», «Качаю STT-модель», «Запускаю». Каждый шаг → обновление прогресс-окна.
- Для длинных шагов (uv sync, pnpm install, скачивание моделей) — псевдо-прогресс/спиннер + строка статуса; точный процент по uv/pnpm недоступен, честно показывать «это может занять несколько минут при первом запуске».
- Терминальный вывод (как в текущем `run.sh`) оставить включаемым лог-файлом (`data/logs/bootstrap.log`) для диагностики; не основной интерфейс.
- Если хочется «настоящего» нативного окна с реалтайм-логом — это уже маленький Swift/SwiftUI-врапер, но это +сложность сборки и подписи. На MVP osascript достаточно.

### Gatekeeper / quarantine (самодельный неподписанный бандл)

Проблема: скачанный из интернета `.app` получает `com.apple.quarantine`. Дабл-клик → «reelibraMAC не удаётся открыть, неизвестный разработчик».

Варианты обхода (от лучшего UX к худшему):

1. **Ad-hoc подпись + нотаризация (идеал, но нужен Apple Developer ID $99/год).** `codesign --deep --sign "Developer ID..."` + `xcrun notarytool` + `stapler`. Тогда дабл-клик работает чисто, без предупреждений. Если бюджет позволяет — это правильный путь для дистрибутива.
2. **Самоочистка карантина (без аккаунта, рекомендуемый компромисс).** Поскольку у нас всё равно есть управляемый первый запуск, можно НЕ обходить, а попросить пользователя ОДИН раз сделать **right-click → Open** (это легитимный системный путь подтверждения для неподписанного приложения). После первого «Open» macOS запоминает разрешение. Инструкция в README + картинка.
   - Альтернатива — снять карантин командой: `xattr -dr com.apple.quarantine reelibraMAC.app`. Но команду должен выполнить пользователь в терминале (сам бандл не может снять карантин с себя до того как ему дали запуститься) → менее дружелюбно. Можно обернуть в маленький `Установить.command`, но он тоже под карантином → замкнутый круг. Поэтому **right-click → Open остаётся самым честным путём для неподписанного бандла.**
3. **Ad-hoc подпись без нотаризации** (`codesign --sign -`) — убирает часть проблем со «сломанным» бандлом (особенно для arm64, где неподписанный код может вообще не запускаться), но Gatekeeper-предупреждение «неизвестный разработчик» всё равно покажет. Минимально стоит делать ad-hoc подпись всегда (arm64 требует хотя бы её для нативного кода в node/ffmpeg бинарях).

Имя: `reelibraMAC.app` (бандл для дабл-клика). Внутренний исполняемый — `reelibraMAC`. Запасной голый скрипт — `reelibraMAC.command`.

---

## 4. ЧЕСТНО: минимальная версия и поддержка железа

- **Минимальная macOS:** ориентир **macOS 14 Sonoma+** (а лучше 15). Причины: свежие MLX/Metal-фичи, актуальные Python/node бинарники, предсказуемое поведение Gatekeeper. macOS 13 возможно, но не тестовый таргет.
- **Apple Silicon (M1/M2/M3/M4): полная поддержка.** Это дом проекта.
- **Intel (x86_64): фактически НЕ поддерживается в v1.**
  - `mlx-whisper`, `stable-ts[mlx]` — arm64-only, `uv sync` упадёт.
  - Даже если вырезать MLX (отдельный extras-профиль) и завести STT на Deepgram (облако, ключ) или whisper.cpp/faster-whisper (CPU, медленно) — llama-cpp без Metal на CPU, нет videotoolbox-энкода. Получится деградированный продукт.
  - Рекомендация: лаунчер на старте делает `uname -m`; если `x86_64` → честный диалог «Reelibra работает только на Mac с Apple Silicon (M1 и новее)» и выход. Не пытаться героически фоллбэчить в v1.

---

## 5. GPU / железо

| Подсистема | Apple Silicon | Intel-мак |
|-----------|--------------|-----------|
| STT (mlx-whisper / stable-ts mlx) | Metal/MPS, быстро | **нет MLX** → только Deepgram (облако) или CPU whisper.cpp |
| Vision (Moondream GGUF, llama-cpp-python) | Metal backend авто (см. `services/vision/moondream_local.py`) | CPU-only, кратно медленнее |
| Видеоэнкод | `h264_videotoolbox`/`hevc_videotoolbox` — hardware | software libx264/libx265 |
| mediapipe (face tracking) | работает, но есть подтверждённый риск зависания на M-series (face-keyframes off by default, см. `pipeline_stages/render.py`, `runtime_settings.py`) | работает на CPU |

Хорошая новость по энкодеру: код **уже корректно фоллбэчит** VideoToolbox→software. `services/encoder_support.py` рантайм-детектит `ffmpeg -encoders` и при отсутствии VT берёт `libx264`/`libx265` с правильным stream-tag. То есть видеорендер не сломается на Intel/Linux — проблема Intel сосредоточена только в STT/MLX-слое, а не в рендере.

---

## 6. Риски

1. **MLX hard-dependency.** `mlx-whisper`+`stable-ts[mlx]` — обычные (не optional) зависимости в `pyproject.toml`. На Intel `uv sync` падает на резолве. Для Intel-профиля нужен отдельный набор extras без mlx — работа по реструктуризации зависимостей, не входит в bootstrap.
2. **STT по умолчанию = MLX, без платформенного гейта.** `Settings.available_transcribers` → `["stable_ts_mlx","mlx_whisper"]` (+deepgram если ключ). Нет автодетекта «нет Apple Silicon → deepgram». На не-arm это уже не доедет (см. п.1), но логика всё равно arm-centric.
3. **Размер дистрибутива.** ML-модели тяжёлые: whisper-large-v3-turbo (~1.5GB с HF), Moondream Q4_K_M GGUF, mediapipe ассеты. Либо вендорить (огромный архив), либо качать при первом запуске (нужна сеть + честный прогресс + обработка обрыва). Это главный UX-риск «двух кликов».
4. **Gatekeeper без Developer ID.** Без нотаризации первый запуск = ручной right-click→Open. Полностью бесшовно — только за $99/год Apple Developer + нотаризация.
5. **arm64 неподписанный нативный код.** node/ffmpeg/llama-cpp бинарники в бандле без хотя бы ad-hoc подписи могут не запускаться на Apple Silicon («killed: 9»). Обязательна минимум `codesign --sign -`.
6. **Node-версия для Vite 7.** Нужен Node ≥20.19/22.12. Системный node непредсказуем → вендорить, иначе `pnpm dev` упадёт на старом node.
7. **`run.sh` не дистрибутивный.** Сейчас он dev-ориентирован (ждёт uv/pnpm/ffmpeg в PATH, отправляет к brew, делает SIGKILL/preflight, `--reload`). Для лаунчера нужна отдельная prod-обёртка: bootstrap-проверки + установка + osascript-прогресс + запуск без `--reload`.

---

## Источники
- [mlx · PyPI](https://pypi.org/project/mlx/)
- [MLX install docs](https://ml-explore.github.io/mlx/build/html/install.html)
- [ml-explore/mlx issue #10 — pip install behavior](https://github.com/ml-explore/mlx/issues/10)
