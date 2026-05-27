# Linux Bootstrap Recon — reelibraLINUX

Роль: Linux Bootstrap Engineer. Цель: «скачал → распаковал → 2 клика по `reelibraLINUX` → само проверилось/доустановилось с прогрессом → работает» на чистом Linux. Честность про зоопарк distro вшита в каждый раздел.

Источник истины по стеку: `apps/backend/pyproject.toml`, `apps/frontend/package.json`, `run.sh`, `.env.example` (на 2026-05-27).

---

## 0. Что выяснено по коду (факты, не предположения)

| Компонент | Откуда | Linux-статус |
|---|---|---|
| Python | `requires-python = ">=3.12,<3.13"` — **строго 3.12** | python-build-standalone 3.12 |
| Node/pnpm | frontend = Vite 7 + React 19, `run.sh` требует `pnpm` | portable node + corepack pnpm |
| ffmpeg | `run.sh` хардкодит `brew install ffmpeg` (macOS-only сообщение) | static build / пакетник |
| uv | `run.sh` требует `uv` (astral installer) | официальный installer — кросс-distro |
| **mlx-whisper** | dep + `import` в `transcribers/__init__.py` и `factory.py` | **НЕ СТАВИТСЯ на Linux** — Apple-only. Блокер. |
| **stable-ts[mlx]** | dep, default transcriber `stable_ts_mlx` | **НЕ СТАВИТСЯ на Linux** — тянет mlx |
| deepgram-sdk | dep, cloud STT | работает везде (нужен ключ) |
| llama-cpp-python | dep, vision/Moondream local (`vision/model_manager.py`) | ставится, но компиляция / CUDA опц. |
| mediapipe | dep, `face_tracker.py`/`object_tracker.py` | Linux x86_64 wheels есть (glibc) |
| ffmpeg encoder | `encoder_support.py` уже даёт software-фолбэк `videotoolbox→libx264/libx265` | Linux работает на libx264 из коробки |
| LLM | Gemini default (`.env.example`), Claude/OpenAI/Zhipu опц. | cloud, кросс-платформ |

**Ключевой вывод:** репо в текущем виде на Linux **не запустится** — `uv sync` упадёт на `mlx-whisper`/`stable-ts[mlx]`. Bootstrap-лаунчер обязан это обойти (см. §4). Без этого «2 клика» — фикция.

---

## 1. Что нужно доустановить и как кросс-distro

Целевые рантаймы: **Python 3.12, Node ≥20, ffmpeg, uv, pnpm**.

Зоопарк менеджеров пакетов:
- Debian/Ubuntu/Mint/Pop → `apt`
- Fedora/RHEL/Rocky/Alma → `dnf`
- Arch/Manjaro/EndeavourOS → `pacman`
- openSUSE → `zypper`
- Alpine → `apk` (musl, не glibc — отдельный риск, см. §5)

Универсальная установка через системный пакетник = **ненадёжно**: разные имена пакетов (`ffmpeg` vs `ffmpeg-free` на Fedora из-за патентов на кодеки), разные версии Python (Ubuntu 22.04 = 3.10, нет 3.12), требует `sudo` (root-сюрпризы, пароль в GUI-двойном-клике невозможен без polkit-агента).

**Решение: не трогать системные пакетники. Всё ставить портативно в user-space** (`~/.local/share/reelibra/runtime/`). Это и есть честный кросс-distro путь без root.

---

## 2. Стратегия bootstrap: портативные бандлы > пакетные менеджеры

Рекомендация: **portable user-space bundle**, никакого `sudo`.

| Рантайм | Источник портативного бандла | Почему |
|---|---|---|
| Python 3.12 | **python-build-standalone** (astral, `cpython-3.12.*-x86_64-unknown-linux-gnu-install_only.tar.gz`) | self-contained, glibc, разворачивается в папку, не зависит от system python |
| uv | официальный `curl -LsSf https://astral.sh/uv/install.sh` ставит в `~/.local/bin` (без root) | кросс-distro, сам astral |
| Node | **portable Node** (`node-v*-linux-x64.tar.xz` с nodejs.org) → распаковка в папку, `corepack enable` даёт pnpm | без npm-global/root |
| ffmpeg | **static build** (johnvansickel.com `ffmpeg-release-amd64-static.tar.xz` — полностью статичный, glibc-free) | один бинарь, работает на любом distro, включает libx264 |

Почему портативно надёжнее пакетников:
- Версии детерминированы (Python ровно 3.12, не «что в repo»).
- Ноль `sudo` → двойной клик в GUI работает без polkit/пароля.
- Не ломает систему пользователя, не конфликтует с distro-python.
- Один код установки для apt/dnf/pacman/zypper — bootstrap не разбирает distro вообще.

Fallback-цепочка на рантайм: `найден в bundle dir → найден в PATH (системный, проверить версию) → скачать портативный`. Если у юзера уже стоит ffmpeg/node нужной версии — переиспользуем, не качаем зря.

### AppImage — вердикт
AppImage привлекателен («один файл, двойной клик»), но для этого проекта **не подходит как primary**:
- Это не одно бинарное приложение, а backend (FastAPI/uvicorn) + frontend (Vite dev-сервер) + браузер. Vite dev-server и `--reload` несовместимы с read-only squashfs-монтированием AppImage.
- mediapipe/llama-cpp/ffmpeg внутри AppImage придётся пересобирать — большой объём работы на сомнительный выигрыш.
- AppImage всё равно требует FUSE (на части свежих distro FUSE2 не предустановлен → «двойной клик ничего не делает»).

Вердикт: **portable bundle в `~/.local/share/reelibra/` + `.desktop`-лаунчер** надёжнее и проще, чем AppImage. AppImage оставить как возможный v2 (если упакуем production-build фронта статикой и заменим dev-сервер).

---

## 3. Механизм «двойного клика» в Linux

Проблема: двойной клик по `.sh` в большинстве файл-менеджеров (Nautilus/GNOME, Dolphin, Nemo) по умолчанию **открывает в текстовом редакторе**, а не исполняет — даже с `chmod +x`. Это самый частый «почему не запускается».

**Решение: `.desktop` launcher.** Это нативный Linux-механизм «иконка → клик → Exec».

Структура поставки (после распаковки архива):
```
reelibra/
├── reelibraLINUX.desktop      ← по нему кликает юзер
├── bootstrap.sh               ← реальная логика (Exec из .desktop)
├── icon.png
├── apps/ ...                  ← код репо
```

`reelibraLINUX.desktop`:
```ini
[Desktop Entry]
Type=Application
Name=reelibraLINUX
Comment=Reelibra — long video to reels
Exec=/path/to/reelibra/bootstrap.sh
Icon=/path/to/reelibra/icon.png
Terminal=true
Categories=AudioVideo;
```

Тонкости (честно, тут есть грабли):
- **Путь в `Exec` должен быть абсолютным.** `.desktop` не знает «свою папку». Решение: `bootstrap.sh` при первом запуске сам прописывает абсолютный путь в `.desktop` (self-patch) ИЛИ кладём `.desktop` в `~/.local/share/applications/` с резолвом пути на установке.
- **«Untrusted application» диалог** (GNOME/Nautilus): при первом клике GNOME требует «Allow Launching» / пометить trusted (`gio set ... metadata::trusted true`). KDE Dolphin спрашивает «Execute / Open». Это нельзя обойти полностью из коробки — нужна одна строка в инструкции «правый клик → Allow Launching» ИЛИ короткий `install.sh` (тот же двойной клик-проблема). Самый чистый путь: первый запуск через терминал `./install.sh`, который регистрирует `.desktop` в меню приложений — дальше запуск из меню/иконки работает «честно».
- `Terminal=true` — открывает терминал и показывает прогресс bootstrap. Надёжно кросс-DE. Минус — выглядит «технично».

### Прогресс: терминал vs GUI
- **MVP: `Terminal=true` + текстовый прогресс** в терминале (echo-шаги «[1/6] Python… [2/6] ffmpeg…»). Работает везде, ноль зависимостей.
- **Опционально красивее: `zenity`** (`--progress`) или `kdialog` — GTK/Qt progress-bar. Но `zenity` есть не на всех distro (на минимальных нет), `kdialog` только KDE. Делать через `command -v zenity` с фолбэком на терминал.
- Рекомендация: терминал-прогресс как база, zenity как прогрессивное улучшение если найден. Не делать GUI обязательным.

---

## 4. STT без MLX — обязательная развилка (это блокер запуска)

В текущем коде дефолтный transcriber = `stable_ts_mlx`, оба mlx-бэкенда **импортируются на старте** (`transcribers/__init__.py`, `factory.py`), а `mlx-whisper`+`stable-ts[mlx]` — hard-deps в `pyproject.toml`. На Linux:
- `uv sync` **упадёт** (нет mlx-wheel под Linux).
- Даже если убрать из deps — `import` в `__init__.py` уронит приложение при старте.

Что обязан сделать Linux-bootstrap (минимум для «работает»):

**Вариант A (рекомендован, минимальные правки кода):** STT = **Deepgram cloud**.
- Bootstrap ставит зависимости **без mlx** (нужен Linux-вариант deps — `uv sync --extra`/отдельная группа без mlx, либо `pyproject` с `[project.optional-dependencies]` платформенным маркером `; sys_platform == "darwin"` на mlx-пакеты).
- Импорты mlx-бэкендов сделать **ленивыми** (внутри `build_transcriber`, не на уровне модуля) — иначе старт упадёт даже без вызова.
- `available_transcribers` на Linux должен возвращать `["deepgram"]` (или local-whisper, см. B), дефолт переключить с `stable_ts_mlx`.
- Требует `DEEPGRAM_API_KEY` в `.env` → bootstrap должен явно предупредить «на Linux STT работает только с Deepgram-ключом» (честность про разнообразие).

**Вариант B (полностью локально, без cloud):** добавить **faster-whisper** (CTranslate2) или openai-whisper как Linux-local бэкенд.
- faster-whisper: CPU (любой Linux) и CUDA (GPU). Word-level timestamps есть. Кросс-distro wheels.
- Это новый transcriber-backend + регистрация в factory — объём работы больше, но даёт «работает без ключей/без интернета», что соответствует духу проекта (local-first).

**Рекомендация:** для phase14-лаунчера сделать **A как немедленный путь** (Deepgram, минимум кода) + зафиксировать B (faster-whisper) как «правильный local-first Linux STT» в backlog. Платформенные маркеры в `pyproject` (`sys_platform == "darwin"`) — обязательны, чтобы один репо ставился и на mac, и на Linux.

---

## 5. GPU и минимум

- **ffmpeg энкод:** `encoder_support.py` уже фолбэчит videotoolbox→**libx264/libx265 (software)** — на Linux работает из коробки на CPU. nvenc/vaapi detection в коде **нет** → GPU-энкод не используется, но и не требуется. Минимум: software libx264 (static ffmpeg его включает). GPU-энкод (nvenc/vaapi) — опциональный апгрейд, не для MVP.
- **llama-cpp-python (vision/Moondream):** ставится CPU-сборкой по умолчанию (медленно, но работает кросс-distro). CUDA/ROCm — opt-in пересборка (`CMAKE_ARGS`), требует toolchain → для bootstrap **CPU-only**, GPU не трогаем.
- **mediapipe (face/object tracking):** Linux x86_64 wheels = только **glibc** (не musl). На Alpine не встанет.
- **LLM:** Gemini cloud (default) — никакого GPU. Это и есть «минимум»: пайплайн думает в облаке, локально только ffmpeg+vision+STT.

GPU-вердикт: **MVP = CPU-only везде** (libx264 + llama CPU + faster-whisper CPU или Deepgram cloud). GPU — отдельная фаза.

---

## 6. Честность про distro/версии (что реально заработает)

| Distro | Статус | Комментарий |
|---|---|---|
| Ubuntu 22.04 / 24.04, Debian 12, Mint, Pop!_OS | ✅ основная цель | glibc ≥2.35, X11/Wayland — UI в браузере, без проблем |
| Fedora 39+, Rocky/Alma 9 | ✅ | glibc свежий; ffmpeg-free в repo — но мы ставим static, обходим |
| Arch/Manjaro | ✅ | rolling, всё свежее |
| openSUSE Tumbleweed/Leap 15.5+ | ⚠️ вероятно ✅ | не тестировано, glibc ок |
| **старый glibc** (CentOS 7, glibc <2.28, Ubuntu 18.04) | ❌ | python-build-standalone и mediapipe wheels требуют свежий glibc |
| **Alpine / musl** | ❌ | mediapipe/llama wheels = glibc-only; musl несовместим |
| WSL2 | ⚠️ | backend ок; UI — браузер на Windows-хосте через `localhost`, работает, но «двойной клик .desktop» в WSL смысла не имеет |

- **glibc** — главный гейт. Целимся в glibc ≥2.31 (Ubuntu 20.04+). Bootstrap должен проверить `ldd --version` и честно отказать с понятным сообщением, а не падать молча.
- **Wayland vs X11** — для самого приложения **неважно**: UI = веб-страница в системном браузере (`xdg-open http://localhost:3000`). И Wayland, и X11 открывают браузер одинаково. Графика проекта рендерится ffmpeg-ом (headless), не зависит от display-сервера. Единственное место где DE важно — `.desktop` trust-диалог и zenity (см. §3).
- `xdg-open` для открытия браузера — кросс-DE, но иногда не настроен на минимальных системах → фолбэк на проверку `command -v xdg-open` + сообщение с URL.

---

## 7. Риски (приоритизированы)

1. **[БЛОКЕР] mlx hard-deps** — без платформенных маркеров в `pyproject` + ленивых импортов в transcribers, репо на Linux не ставится и не стартует. Правка кода обязательна, не обходится только лаунчером.
2. **[ВЫСОКИЙ] STT-путь** — без Deepgram-ключа ИЛИ без добавления faster-whisper на Linux нет STT вообще → пайплайн нерабочий. Нужно явное решение A/B (§4).
3. **[СРЕДНИЙ] `.desktop` trust-диалог** — «двойной клик» в чистом виде упирается в GNOME «Allow Launching» / KDE «Execute». Честный UX = один разовый `install.sh` из терминала, дальше иконка. «Прям совсем 2 клика без единого терминала» на Linux недостижимо на 100% кросс-DE.
4. **[СРЕДНИЙ] glibc / musl** — старые и musl-системы не поддерживаются; нужна проверка-гейт с человекочитаемым отказом.
5. **[НИЗКИЙ] absolute path в `.desktop`** — решается self-patch при установке.
6. **[НИЗКИЙ] ffmpeg static без некоторых кодеков** — johnvansickle build включает libx264/libx265/aac, достаточно для пайплайна; экзотика (vaapi/nvenc) не входит — для MVP не нужна.
7. **[НИЗКИЙ] mediapipe размер/совместимость** — тяжёлый wheel, но glibc x86_64 ставится; на ARM Linux (aarch64) wheels могут отсутствовать → пока только x86_64.

---

## Итоговая рекомендация для phase14-лаунчера

1. **Bootstrap = portable user-space bundle** (python-build-standalone 3.12 + portable Node + static ffmpeg + uv-installer), ноль `sudo`, всё в `~/.local/share/reelibra/`. Пакетники distro не трогаем.
2. **Запуск = `.desktop`-лаунчер** (`reelibraLINUX.desktop`, `Terminal=true`, абсолютный Exec через self-patch). Прогресс — текст в терминале, zenity опционально. Один разовый `install.sh` регистрирует иконку в меню — это честный максимум «двойного клика» на Linux.
3. **STT = Deepgram (вариант A)** немедленно + платформенные маркеры на mlx в `pyproject` + ленивые импорты mlx-бэкендов. faster-whisper (вариант B) — в backlog как local-first Linux STT.
4. **GPU = CPU-only MVP** (libx264 software-фолбэк уже в коде; llama CPU; Gemini cloud для LLM).
5. **Поддержка честно: glibc ≥2.31, x86_64, X11/Wayland (UI = браузер).** musl/Alpine/старый glibc/aarch64 — вне scope, с явным гейтом-проверкой.
