# Linux Launcher Validation — reelibraLINUX

Role: Linux Launcher Validator (зоопарк distro, паранойя к edge-кейсам, нетерпимость к заглушкам).
Method: чтение + `bash -n` (целевая система не Linux, рантайм-исполнение не делалось).
Files: `reelibraLINUX.sh`, `launchers/linux/{launcher.sh,lib.sh,install.sh,reelibra.desktop}`.

## Verdict: PASS (с 1 средним багом и 2 низкими — ниже)

Лаунчер production-grade: реальный bootstrap, честный гейт, аккуратная чистка с защитой данных, ноль MOCK/TODO/заглушек. STT-honesty корректна. Один баг чистки (foreign-kill в `runtime_cleanup`) стоит починить, но он касается shutdown собственной сессии, не порчи данных.

---

## 1. `bash -n` — PASS
Все четыре `.sh` (`reelibraLINUX.sh`, `launcher.sh`, `lib.sh`, `install.sh`) проходят `bash -n` без ошибок.

## 2. Двойной клик / .desktop — PASS
- `install.sh` регистрирует `~/.local/share/applications/reelibra.desktop` через `sed`-патч шаблона: `@EXEC@` → абсолютный `$REELIBRA_ROOT/reelibraLINUX.sh`, `@ICON@` → `reelibra` (icon theme name, не путь — корректно для hicolor). Exec абсолютный. PASS.
- Иконки в hicolor: SVG → `scalable/apps/reelibra.svg`, PNG → `48/64/128/256x256/apps/reelibra.png` (с `convert`-ресайзом и фолбэком на копию оригинала). `assets/reelibra.{png,svg}` существуют. PASS.
- `Terminal=true` в шаблоне — есть. PASS.
- `gio set ... metadata::trusted true` снимает GNOME «Untrusted application». `update-desktop-database` + `gtk-update-icon-cache` под `command -v` гардами. PASS.
- Honest UX: README в `reelibraLINUX.sh` прямо говорит, что чистый «двойной клик по .sh» открывает редактор, и предлагает `install.sh` как нативный путь. Соответствует recon §3.

## 3. .desktop синтаксис (Desktop Entry spec) — VALID
`[Desktop Entry]`, `Type=Application`, `Name`, `GenericName`, `Comment`+`Comment[en]`, `Exec`, `Icon`, `Terminal=true`, `Categories=AudioVideo;Video;` (валидные main+additional, точка с запятой-терминатор есть), `Keywords=...;`, `StartupNotify=true`. Все ключи валидны, списки терминируются `;`. Спека соблюдена.

## 4. Bootstrap user-space без sudo — PASS
- Никакого `sudo`/пакетников. Всё в `$REELIBRA_ROOT/.reelibra-runtime/` (переопределяемо `REELIBRA_RUNTIME_HOME`). Соответствует recon §2.
- Fallback-цепочка `bundle → системный нужной версии → download` реализована для Python/uv/Node/pnpm/ffmpeg:
  - Python: bundle `$PY_DIR/bin/python3.12` → system `python3.12` (строго major.minor==3.12) → PBS download.
  - Node: bundle → system `node` major≥20 → portable download.
  - ffmpeg: bundle → system ffmpeg major≥7 → static download.
  - uv: bundle → system → astral installer с `UV_INSTALL_DIR`/`XDG_BIN_HOME`/`INSTALLER_NO_MODIFY_PATH=1` (не пишет в `~/.local/bin`, не правит профиль). Корректно.
  - pnpm: corepack-shim → system → `corepack enable` → `npm i -g --prefix`. Четыре уровня деградации.
- URL правдоподобны/проверены:
  - Node `https://nodejs.org/dist/v20.18.1/node-v20.18.1-linux-x64.tar.xz` — **подтверждён живым** (26 MB, 20-Nov-2024).
  - PBS: release `20241219` существует; имя `cpython-3.12.8+20241219-...-install_only.tar.gz` — стандартный PBS-формат, правдоподобно.
  - ffmpeg `https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz` — известный glibc-free static source (recon §2).
- Распаковка с проверкой структуры (`[[ -x ... ]] || die`), архивы кэшируются в `$CACHE_DIR`, повреждённый архив → `die` с инструкцией удалить и перезапустить.

## 5. Платформенный гейт — PASS
- `uname -m != x86_64` → `die` (честно: ARM/прочее вне поддержки, нет ML-wheels).
- musl/Alpine детект: `ldd --version` не содержит glibc/gnu libc И (`/etc/alpine-release` ИЛИ `ldd ... musl`) → `die` с честным объяснением (mediapipe/llama-cpp/onnxruntime без musl-сборок).
- glibc-версия: `ldd --version | grep -oE '[0-9]+\.[0-9]+' | head -1`. Проверено — на выводах вида `2.35.1` regex даёт чистое `2.35`, поэтому `minor` всегда целое, арифметика `(( minor < 35 ))` не падает. Порог 2.35 (Ubuntu 22.04+/Debian 12+/Fedora 37+). Если версию не извлечь — `warn` + продолжение (мягко, не блок). PASS.
  - Примечание: recon §6 целился в glibc ≥2.31 (Ubuntu 20.04+), а код ставит ≥2.35. Это СТРОЖЕ recon и согласуется с шапками всех файлов (22.04+). Не баг — осознанный выбор, но рассогласование с одной фразой recon. Если 20.04 должен поддерживаться — порог завышен.

## 6. Чистка висяков — PASS с 1 средним багом
- Порты: `pids_on_port` — `ss -ltnHp` (нативно) → `lsof -t -iTCP -sTCP:LISTEN` (fallback). Edge «нет ни ss, ни lsof» → вернёт пусто → порт считается свободным (приемлемая деградация).
- `free_port`: разделяет наши/чужие через `is_our_pid` (по `ps -o args=` против `PROC_PATTERNS` + ffmpeg, заякоренного на `$REELIBRA_ROOT/data/`). Чужой процесс на порту: в TTY спрашивает [y/N], в неинтерактиве — `die` (не убивает молча). Честно и безопасно.
- `PROC_PATTERNS` совпадают с `run.sh` (`uvicorn videomaker.main`, `uv run uvicorn`, `node .*vite`, `pnpm.*dev`). Orphan ffmpeg заякорен на путь проекта `data/` — чужие рендеры не трогает. PASS.
- TERM→KILL: `kill_graceful` шлёт TERM, поллит до 5с (10×0.5с), затем KILL. PASS.
- Зомби: `reap_zombies` добивает родителя только если `is_our_pid` — заякорено. PASS.
- Защита данных: `clean_stale_files` удаляет ТОЛЬКО `*.lock/*.partial` (в `data/proxies`, mtime>30мин) и `*.tmp` (mtime>30мин) + `__pycache__`. `*.db`/`-wal`/`-shm`/артефакты не трогаются. PASS — критичное требование выполнено.
- PID-файл: `data/.run/reelibra.pid`, формат `role pid`, читается при старте (детект «жёстко закрыли»), пишется после запуска, удаляется в cleanup. PASS.

### [СРЕДНИЙ] runtime_cleanup убивает чужие процессы по неякорным паттернам
`runtime_cleanup` (lib.sh ~590) в фазе KILL делает:
```
for pat in "${PROC_PATTERNS[@]}"; do
    kill -KILL $(pgrep -f "$pat" ...) ...
done
```
`pgrep -f` здесь НЕ заякорен на `$REELIBRA_ROOT` (в отличие от `is_our_pid`/orphan-ffmpeg). Паттерны `node .*vite` и `pnpm.*dev` широкие — при выходе из Reelibra это пошлёт `SIGKILL` любому чужому Vite/pnpm-dev (другой проект пользователя в зоопарке) на машине. `cleanup_previous_session` использует те же `pids_by_pattern`, та же проблема на старте. В отличие от `free_port`, тут нет фильтра `is_our_pid`.
Fix: прогонять кандидатов `pgrep -f` через `is_our_pid` перед kill, либо заякорить паттерны на cwd/путь проекта. Это тот же класс защиты, что уже сделан для портов и ffmpeg — просто не доведён до этих двух мест.

## 7. NO MOCKS/TODO/заглушек — PASS
Грепом по всем 5 файлам: нет TODO/FIXME/MOCK/заглушек/«not implemented». Каждая ветка либо делает реальную работу, либо `die`/`warn` с человекочитаемой причиной+действием. Вся логика рабочая.

### STT honesty (Deepgram на Linux) — PASS
`ensure_env` явно предупреждает дважды: «на Linux STT работает ТОЛЬКО через Deepgram, MLX/Apple-Whisper недоступны» + «добавь DEEPGRAM_API_KEY». `sync_backend` при падении `uv sync` честно называет вероятную причину (mlx hard-deps без platform-маркеров) и точное исправление. Согласуется с backend-аудитом `stt-be.md` (PASS): mlx-deps помечены `; sys_platform=='darwin'`, импорты ленивые, default off-darwin = deepgram. Лаунчер и код когерентны.

## 8. Edge-кейсы — покрыты
| Edge | Покрытие |
|---|---|
| Нет сети | `check_network` (curl/wget, 3 хоста) перед каждым download → `die` с инструкцией. PASS |
| Занятый порт (чужой) | `free_port`: TTY-вопрос или `die`, не убивает молча. PASS |
| Нет curl И wget | `download`→`die` «установи curl»; `check_network`/`wait_health` деградируют (вернут fail/пропустят). PASS |
| Нет xdg-open | `open_browser`→`warn` с URL вручную. PASS |
| Нет zenity / нет DISPLAY | `detect_ui`→`tty`, весь zenity-слой под `[[ UI_MODE==zenity ]]` гардами. PASS |
| Разные DE (GNOME/KDE/Wayland/X11) | UI=браузер, `.desktop` нативен, `gio`/cache-апдейты опциональны. PASS |
| Нет ss И lsof | порт считается свободным (мягкая деградация). Acceptable |
| Frozen lockfile рассинхрон | `sync_frontend` фолбэк на обычный `pnpm install`. PASS |
| Повреждённый архив | проверка `-x` после распаковки → `die` с инструкцией. PASS |

---

## Баги/заглушки (по приоритету)

1. **[СРЕДНИЙ] `runtime_cleanup` + `cleanup_previous_session` KILL по неякорным `pgrep -f`** — может прибить чужой Vite/pnpm-dev на машине. Фильтровать через `is_our_pid` (защита уже есть для портов/ffmpeg, не доведена сюда). Не портит данные, но нарушает «не трогать чужое».
2. **[НИЗКИЙ] glibc-порог 2.35 строже recon (2.31)** — Ubuntu 20.04 отсекается. Если это намеренно (ML-wheels) — ок, но рассинхрон с recon §6. Уточнить целевой минимум.
3. **[НИЗКИЙ] ffmpeg static — SPOF без checksum** — johnvansickle единственный источник, скачка без проверки хэша/подписи. Для MVP приемлемо (recon §2 это и предлагал), но supply-chain-замечание: при компрометации зеркала бинарь попадёт в пайплайн без верификации. Node/PBS — с github/nodejs.org, надёжнее.
4. **[ИНФО] `version_ge` определён, но нигде не вызывается** — мёртвый код (lib.sh ~179). Версии сравниваются инлайн через major. Безвреден, можно удалить.

## Резюме ответов на вопросы
- bash -n чисто: **да** (все 4).
- .desktop валиден, абсолютный Exec, иконка hicolor, Terminal=true: **да**.
- Bootstrap user-space без sudo, URL правдоподобны, fallback bundle→system→download: **да**.
- Гейт x86_64 + glibc≥2.35 + musl/Alpine отказ: **да** (порог строже recon).
- Чистка: порты ss/lsof, pgrep заякорен, TERM→KILL, зомби, НЕ трогает *.db/-wal/-shm, PID-файл: **да в основной чистке; НЕТ якоря в `runtime_cleanup`/start-KILL (средний баг #1)**. Данные защищены везде.
- NO MOCKS/TODO: **да**. STT honesty: **да**.
- Edge покрыты: **да** (см. таблицу).
