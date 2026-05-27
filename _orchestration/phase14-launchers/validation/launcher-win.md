# Windows Launcher — Validation

**Файлы:** `reelibraWIN.cmd` · `launchers/windows/launcher.ps1` · `launchers/windows/create-shortcut.ps1`
**Метод:** статический разбор (Windows-запуск недоступен) + verification реальных bootstrap-URL через HEAD-запросы + сверка внутренней структуры архивов + сверка с `run.sh` (эталон поведения).

## ВЕРДИКТ: PASS

Заглушек/моков/TODO нет (grep чист). PowerShell-синтаксис корректен. Все 4 bootstrap-URL живые и качают реальные бинарники. Логика уборки/портов/детей грамотная и не трогает БД. Найдено 2 minor-замечания (не блокеры) и подтверждены все 8 пунктов задачи.

---

## 1. PowerShell-синтаксис — OK

- Баланс скобок: `{}` 180/180, `()` 288/288, `[]` 57/57 — сбалансированы.
- `#Requires -Version 5.1`, `Set-StrictMode -Version Latest`, `$ErrorActionPreference='Stop'` — корректная преамбула; внешние утилиты обрабатываются вручную через `$LASTEXITCODE` (не валятся на не-zero под StrictMode).
- Интерполяция health-URL `"http://$AppHost`:$AppPort/api/v1/health"` — backtick перед `:` корректно экранирует двоеточие (иначе PS трактует `$AppHost:` как drive-scope). Идиома верная.
- Битых переменных нет. Скоупы аккуратные: `Read-DotEnv` пишет `$Script:AppHost/$Script:AppPort` (правильно — внутри функции), MAIN-тело пишет `$HealthUrl` в script-scope напрямую (try/catch не создаёт scope), функции `Start-Servers` читают его из родительского scope — работает.
- Backtick-переносы строк (line continuation) в `Start-Process … \`) и WebClient — корректны.

## 2. Bootstrap — OK (URL проверены live)

Все ссылки разрешаются в реальные ассеты (HEAD 200):
- Python: `python-build-standalone/releases/download/20241219/cpython-3.12.8+20241219-x86_64-pc-windows-msvc-install_only.tar.gz` → **41.8 МБ, 200 OK**. Внутренняя структура архива = `python/python.exe` → совпадает с ожидаемым `$PyDir\python\python.exe`. ✓
- Node: `nodejs.org/dist/v20.18.1/node-v20.18.1-win-x64.zip` → существует (30 МБ). Распаковка во временную папку + `Move-Item` содержимого `node-vXX-win-x64\` в `node-20\` — верно. ✓
- uv: `astral-sh/uv/releases/download/0.5.11/uv-x86_64-pc-windows-msvc.zip` → **15.7 МБ, 200 OK**. ✓
- ffmpeg: `BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip` → **211 МБ, 200 OK**. Поиск `ffmpeg.exe` рекурсивно в архиве + копирование ffmpeg/ffprobe — устойчиво к смене имени внутренней папки. ✓

Всё качается в `.reelibra-runtime\` (downloads + распаковка). Без админа. Исключение — VC++ Redist через `Start-Process -Verb RunAs … /quiet /norestart` (может всплыть UAC), что честно прокомментировано; коды 0/3010/1638 трактуются как успех, прочие → warning а не fatal. ✓

PATH/env выставляются в `Set-RuntimePath`: раннеры впереди системных, `UV_PYTHON=$PyExe`, `UV_PYTHON_DOWNLOADS=never` (uv не качает свой Python), `NPM_CONFIG_PREFIX` в runtime (pnpm без прав), `FFMPEG_BINARY/FFPROBE_BINARY`. ✓

TLS: Tls12|Tls13 с фолбэком на Tls12 — для старых сборок .NET. WebClient с системным прокси + фолбэк на `Invoke-WebRequest`. Пустой/нулевой файл → ошибка + удаление `.partial`. ✓

## 3. Диагностика идемпотентна — OK

- Каждый `Ensure-*` сначала `Test-Path` бинарника → если есть, печатает ОК и выходит. Повторный запуск ничего не качает. ✓
- `uv sync --project $BackendDir`: при ошибке → удаляет `.venv` → повтор. Фолбэк есть. ✓
- `pnpm install --silent`: при ошибке → `store prune` + удаление `node_modules` → повтор. ✓
- Invocation `uv run uvicorn videomaker.main:app` идентичен `run.sh` (эталон); пакет `videomaker` ставится editable через uv sync (layout `src/videomaker`, hatch source) — резолвится. ✓

## 4. Чистка висяков — OK

- `Stop-PidTree`: мягкий `Stop-Process` → через 300мс `taskkill /PID /T /F` — `/T` валит дерево детей (reloader uvicorn, esbuild у Vite, pnpm-дети). ✓
- **Защита от чужого процесса на порту:** `Test-OursPid` через `Win32_Process.CommandLine` — матчит только `uvicorn videomaker.main` / `uv run uvicorn` / node+vite / esbuild / pnpm+dev / ffmpeg в `data/artifacts` / любой процесс с путём репо в cmdline или ExecutablePath. Если на порту чужая программа → НЕ убивает, а `Fail` с именем/PID. ✓✓ (параноидально-корректно)
- `Get-OurStrayPids` дополнительно матчит путь репо (`-match $rootEsc`) — не убьёт чужой uvicorn другого проекта на 8000 (там нет нашего RootDir в cmdline; правда `uvicorn videomaker.main` матчится без проверки пути — см. minor #1).
- **НЕ трогает БД:** чистятся только `*.partial`/`*.tmp` + orphan `*.lock` старше 1800с. `*.db/-wal/-shm` и финальные медиа не включены в `-Include`. ✓✓
- PID-файлы и `__pycache__` чистятся (как в run.sh). ✓

## 5. NO MOCKS/TODO — OK

grep по `TODO/FIXME/MOCK/заглушк/stub/placeholder/HACK` — чисто (exit 1). Реальный рабочий код. ✓

## 6. Honesty — OK

- Deepgram: при пустом `DEEPGRAM_API_KEY` явное предупреждение «на Windows распознавание речи ТОЛЬКО через Deepgram (локальный MLX только на Mac), без ключа транскрипция не заработает». Честно. ✓
- `.env` создаётся из `.env.example` при отсутствии (как run.sh). Пустой `GEMINI_API_KEY` → warning. ✓

## 7. Иконка через .lnk — OK

`create-shortcut.ps1`: COM `WScript.Shell.CreateShortcut`, TargetPath=`reelibraWIN.cmd`, WorkingDirectory=root, IconLocation=`assets\reelibra.ico,0`. `reelibra.ico` присутствует в `assets/`. Создаёт .lnk на Desktop и в корне. Если ico нет — ярлык без иконки (graceful). ✓

## 8. Edge-кейсы — покрыты

- **Пробелы/кириллица в пути:** `.cmd` использует `set "REELIBRA_ROOT=%~dp0"` в кавычках + `chcp 65001`; PS везде `-LiteralPath`, `Join-Path`, пути в кавычках. Раннее предупреждение если путь содержит не-ASCII (`-match '[^\x00-\x7F]'`) с советом перенести в `C:\reelibra` (venv/uv могут спотыкаться на кириллице). ✓
- **Нет сети:** Download-File → пустой/неудачный → throw с понятным сообщением «проверь интернет»; ловится в MAIN catch → ReadKey, окно не закрывается. ✓
- **Занятый порт:** свой → гасит и перепроверяет (`Fail` если не освободился); чужой → `Fail` с именем программы, для FE отдельно поясняет strictPort. Vite `strictPort:true, port:3000` подтверждён в vite.config.ts — совпадает с логикой. ✓
- **Backend не стартовал:** health-poll 60с с проверкой `HasExited` + хвост err-лога в Fail. ✓

---

## Minor-замечания (не блокеры)

**Minor #1 (LOW) — stray-матч `uvicorn videomaker.main` без проверки пути репо.**
В `Test-OursPid` (стр. 425) и `Get-OurStrayPids` (стр. 449) правила `uvicorn videomaker.main` / `uv run uvicorn` срабатывают БЕЗ требования `$rootEsc` в cmdline. Если пользователь держит ДВЕ копии reelibra (напр. dev + public-клон) и запускает одну — уборка может прибить uvicorn другой копии. Сценарий редкий (тот же продукт, тот же порт всё равно конфликтует). Для строгой изоляции стоило бы и эти два правила привязать к `$rootEsc`, как сделано для node/pnpm/ffmpeg. Поведение для конечного пользователя (одна копия) — корректно.

**Minor #2 (INFO) — `Expand-Tar` комментарий упоминает `.tar.zst`, но bsdtar/tar.exe в части ранних Win10 1803 не имеет zstd.**
Фактически качается `.tar.gz` (gzip — поддерживается tar.exe везде с 1803+), так что реального риска нет; комментарий про zst вводит в заблуждение, но код берёт только gz-ассет. Косметика.

**Прочее (намеренно, не баг):** health-poll 60с может быть мало на первом холодном старте с тяжёлым `uv sync` уже позади — но sync вынесен ДО запуска серверов, так что 60с на DDL/seed достаточно. Vite `host:true` слушает 0.0.0.0 — `Get-NetTCPConnection -State Listen` всё равно найдёт. OK.

## Итог
Лаунчер production-ready для одиночной установки. Bootstrap честный и проверяемый, уборка безопасна для данных и чужих процессов, edge-кейсы (кириллица/пробелы/сеть/порты) обработаны, honesty по STT присутствует, иконка создаётся. Minor #1 — единственное, что стоит рассмотреть, если у пользователя бывает несколько копий репозитория.
