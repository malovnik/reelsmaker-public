# Reelibra — Windows Launch Diagnostics & Stale-Process Cleanup (recon spec)

Роль: Windows Process Lifecycle Engineer. Принцип: после любого краша система должна стартовать
чистой — без висящих процессов, занятых портов и битых артефактов, но БЕЗ потери пользовательских данных.

Это спецификация (что должен делать Windows-лаунчер), не код. Эталон поведения — `run.sh` (macOS/bash),
который надо воспроизвести на Windows без `pgrep`/`lsof`/`pkill`/SIGKILL.

---

## 0. Что поднимается (из репо)

| Компонент | Команда (cwd) | Порт | Особенности |
|---|---|---|---|
| Backend | `uv run uvicorn videomaker.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir src` (`apps/backend`) | 8000 (`APP_PORT`) | FastAPI lifespan; `--reload` плодит дочерний reloader-процесс |
| Frontend | `pnpm dev` → `vite` (`apps/frontend`) | 3000 (`strictPort: true`) | strictPort: занятый 3000 = **жёсткий fail**, не fallback. Vite спавнит esbuild-детей |
| ffmpeg | вызывается backend'ом | — | пишет в `data/proxies/*.partial`, рендеры в `data/artifacts` |

Lifespan backend (`apps/backend/src/videomaker/main.py`) уже при старте делает мягкий self-recovery:
- `reset_stale_running_jobs()` — все Job в `running` → `error` ("interrupted by application restart");
- Publer assignments `uploading` → `queued`;
- DDL bootstrap (`CREATE TABLE IF NOT EXISTS`), seed промптов/сабтайтлов, прогрев шрифтов в фоне.

Вывод: БД-уровень stale-state бэкенд лечит сам — лаунчеру **нельзя** трогать `videomaker.db` и `data/`.
Задача Windows-лаунчера = уровень ОС: процессы, порты, lock/partial-файлы.

Требуемые инструменты: `uv`, `pnpm` (+ `node`), `ffmpeg`, `python` (через uv). Окружения: `.venv` (backend),
`node_modules` (frontend). Конфиг: `.env` (копируется из `.env.example` при отсутствии).

---

## 1. Preflight: проверка установленного (что есть → ок, чего нет → доустановка)

Проверять последовательно, каждый шаг — строка статуса (см. §4). На Windows предпочесть `winget`
(встроен в Win10 21H2+/Win11) как установщик; PowerShell 5.1+ как раннер.

| Чек | Команда детекта | Что показываем при OK | Если нет → действие |
|---|---|---|---|
| Python | `uv python find` (uv тянет свой) | `Python 3.x ... ОК` | ставится автоматически `uv python install` (uv качает) |
| uv | `where uv` / `uv --version` | `uv 0.x.x ... ОК` | `winget install astral-sh.uv` → если winget нет: `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"` |
| Node | `where node` / `node --version` (нужен ≥20) | `Node vXX ... ОК` | `winget install OpenJS.NodeJS.LTS` |
| pnpm | `where pnpm` / `pnpm --version` | `pnpm X ... ОК` | `npm install -g pnpm` (после Node) или `winget install pnpm.pnpm` |
| ffmpeg | `where ffmpeg` / `ffmpeg -version` | `ffmpeg X ... ОК` | `winget install Gyan.FFmpeg`, затем добавить в PATH текущей сессии |
| `.env` | `Test-Path .env` | `конфиг найден` | копировать `.env.example`→`.env`, предупредить «добавь GEMINI_API_KEY» |
| backend deps | `uv sync` (идемпотентен, <1с если lock не менялся) | `зависимости backend ... ОК` | `uv sync` создаёт `.venv` + ставит (с прогрессом) |
| frontend deps | `pnpm install` (идемпотентен) | `зависимости frontend ... ОК` | `pnpm install` создаёт `node_modules` (с прогрессом) |
| data-каталоги | — | — | создать `data\uploads`, `data\artifacts`, `data\logs` (`mkdir -Force`) |

Целостность (а не только наличие):
- Версии: парсить `--version`, сверять с минимумами (Node ≥20, ffmpeg любой свежий, uv любой).
  Старая major-версия → предупреждение + предложить апгрейд (не блокировать жёстко, кроме Node <18).
- `.venv` битый: `uv sync` всё равно прогоняем всегда — он чинит/досоздаёт. Если падает → ловим
  как ошибку (§5), сообщение «окружение backend повреждено, пересоздаю» → `Remove-Item .venv -Recurse`
  + повторный `uv sync`.
- `node_modules` битый (например, прерванный install): признак — `pnpm install` упал; то же лечение
  через `pnpm store prune` + повторный install.
- После установки ffmpeg/uv через winget — PATH процесса не обновляется автоматически; лаунчер должен
  дописать путь в `$env:Path` текущей сессии, иначе следующий чек ложно провалится.

Идемпотентность: повторный запуск без изменений = все чеки зелёные за секунды, нулевая работа.

---

## 2. Чистка висяков прошлого запуска (Windows-эквивалент preflight_kill / preflight_free_port)

bash-эталон бьёт по паттернам командной строки и по слушающему порту. На Windows три независимых
вектора поиска — применять все, объединять PID'ы, дедуплицировать:

### 2a. По порту (надёжнее всего — освобождает то, что реально мешает старту)
- `Get-NetTCPConnection -LocalPort 8000 -State Listen` → `.OwningProcess` → PID.
- То же для 3000.
- Фолбэк без модуля NetTCPIP: `netstat -ano | findstr :8000 | findstr LISTENING` → последняя колонка = PID.
- Перед kill — верифицировать, что это наш процесс (имя `python`/`uvicorn`/`node`, см. 2b), чтобы не
  убить чужой сервис, случайно севший на 3000/8000.

### 2b. По имени образа + командной строке (ловит процессы, уже отвалившиеся от порта)
Win не матчит по cmdline через taskkill напрямую — использовать CIM:
```
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -match 'uvicorn videomaker\.main' -or
                 $_.CommandLine -match 'uv run uvicorn' -or
                 ($_.Name -eq 'node.exe'   -and $_.CommandLine -match 'vite') -or
                 ($_.Name -eq 'esbuild.exe') -or
                 ($_.Name -eq 'pnpm.cmd'    -and $_.CommandLine -match 'dev') -or
                 ($_.Name -eq 'ffmpeg.exe'  -and $_.CommandLine -match 'data[\\/]artifacts') }
```
Паттерны 1:1 с `preflight_kill` в run.sh (uvicorn, uv-run, vite, esbuild, pnpm dev, ffmpeg по artifacts).

### 2c. По рабочей папке (страховка: процесс нашего репо, но с неожиданной cmdline)
- Из CIM `Win32_Process` нет cwd напрямую; брать ExecutablePath/CommandLine и матчить подстроку
  пути репозитория (`reelsmaker-public\apps\backend` / `...\apps\frontend`). Это отсекает чужой
  Python/Node на машине от наших.

### Остановка: мягкая → жёсткая (душа «чистого выхода»)
1. **TERM-эквивалент** (graceful): `Stop-Process -Id <pid>` (посылает WM_CLOSE/обычный terminate).
   Дать ~2-3 с (как `sleep 2` в run.sh) на закрытие сокетов и flush БД бэкендом.
2. Перечекать порт/процессы. Кто жив — **жёстко**: `Stop-Process -Id <pid> -Force` (= SIGKILL),
   при упорстве дерево целиком: `taskkill /PID <pid> /T /F` (`/T` валит детей — reloader, esbuild).
3. Финальная верификация: порт 8000 и 3000 снова свободны (`Get-NetTCPConnection` пусто). Если нет —
   ошибка §5 «порт занят сторонним процессом <имя/PID>, освободи вручную».

Замечание про reloader: `--reload` означает 2 процесса (watcher + worker). `/T` обязателен, иначе
worker осиротеет и продолжит держать 8000.

### 2d. Lock/partial/tmp-артефакты (соответствие реальным путям в коде)
Удалять ТОЛЬКО орфанов от краша, не трогая валидный кэш и пользовательские данные:

| Артефакт | Путь | Правило удаления |
|---|---|---|
| proxy partial | `data\proxies\*.partial` | удалять все (незавершённый ffmpeg-вывод — всегда мусор) |
| proxy lock | `data\proxies\*.lock` | удалять только orphan: `mtime` старше lock_timeout (1800 с). Свежий lock = возможно живой процесс — но мы их уже убили в 2a-2c, после kill безопасно снять все |
| asset pending | `data\assets\_pending\*.tmp` (и `data\uploads` partial-загрузки) | удалять `*.tmp` — прерванные аплоады |
| font/face tmp | `*.tmp` рядом с `fonts_cache.json`, моделями в `data\models`, `data\face_cache` | удалять `*.tmp` (атомарная запись прервалась) |
| pycache | `apps\backend\src\**\__pycache__` | удалять (как в run.sh — гарантия свежего bytecode) |

НЕ трогать: `videomaker.db`, готовые `*.mp4`/`*.png` без `.partial`/`.tmp`, `fonts_cache.json` (сам файл),
`data\transcripts`, `data\thumbnails`, любые финальные артефакты. БД-stale лечит lifespan сам (§0).

Реализация: `Get-ChildItem -Path data -Include *.partial,*.tmp -Recurse -File | Remove-Item -Force`
+ отдельный проход lock с фильтром по `LastWriteTime`.

---

## 3. Детект «жёстко закрыли в прошлый раз» (stale-state)

Признаки нечистого выхода (любой ⇒ режим recovery):
1. **Занят порт 8000/3000** при старте, хотя лаунчер думает, что ничего не запускал → процесс пережил
   прошлый сеанс. (Главный сигнал; `strictPort` Vite на 3000 иначе сразу даст hard-fail.)
2. **Найдены процессы** по 2b/2c без активного нашего сеанса.
3. **Есть `.partial`/`.tmp`/свежие `.lock`** — запись прервалась на полуслове.
4. **PID-файл** (рекомендация ниже) существует, а процесс по нему уже мёртв → прошлый сеанс не завершился штатно.

Реакция:
- Процессы/порты → каскад остановки §2 (мягко→жёстко).
- Артефакты → чистка §2d.
- БД running-jobs → **не лаунчер**, делает backend lifespan (`running→error`). Лаунчеру достаточно дать
  бэкенду стартовать; в UX-логе показать «прерванные задачи прошлого сеанса помечены как ошибочные»
  (можно прочитать из health/логов бэкенда после старта, опционально).

Рекомендация (улучшение к текущему репо, где PID-файла нет): писать `data\.run\backend.pid` и
`data\.run\frontend.pid` после спавна, удалять при штатном выходе. Наличие файла при старте + мёртвый
PID = верный детект жёсткого закрытия, не полагаясь только на порт. (`.run` уже в gitignore через `data/`.)

---

## 4. UX-поток (нативно понятный, с прогрессом)

Один линейный лог, человеческим языком, без технического шума. Каждый шаг: `Действие… → ОК/статус`.
Долгие шаги (install) — с прогрессом (стримить вывод winget/uv/pnpm или спиннер + проценты).

```
Reelibra — подготовка к запуску

[1/4] Проверка окружения
   Python… ОК (3.12)
   uv… ОК (0.5.1)
   Node… не найден → устанавливаю… [▓▓▓▓░░░] 60%  → ОК (v20.11)
   pnpm… ОК
   ffmpeg… ОК
   Конфиг (.env)… создан из шаблона — добавь GEMINI_API_KEY
   Зависимости backend… ОК
   Зависимости frontend… устанавливаю… ОК

[2/4] Уборка после прошлого запуска
   Проверяю порт 8000… занят (uvicorn, PID 11234) → останавливаю… освобождён
   Проверяю порт 3000… свободен
   Зависшие процессы Reelibra… не найдено
   Временные файлы (.partial/.tmp/.lock)… удалено 3
   Прерванные задачи прошлого сеанса… будут помечены бэкендом

[3/4] Запуск
   Backend (порт 8000)… запущен
   Frontend (порт 3000)… запущен
   Жду готовности backend (/api/v1/health)… ОК

[4/4] Готово
   Открываю http://localhost:3000
   Закрой это окно (или Ctrl+C), чтобы остановить Reelibra
```

Принципы UX:
- Зелёный `ОК` / жёлтое предупреждение / красная ошибка — цвет в консоли, не только текст.
- Установка чего-либо — всегда явная строка «устанавливаю…» + прогресс, пользователь понимает паузу.
- После старта — health-poll бэкенда (GET `http://127.0.0.1:8000/api/v1/health`) с таймаутом ~30 с,
  только потом открывать браузер. Vite на 3000 поднимается быстро, но проксирует на backend — ждём backend.
- На закрытие окна/Ctrl+C — выполнить тот же мягко→жёстко каскад §2 (аналог `trap cleanup` в run.sh)
  + удалить PID-файлы.

---

## 5. Обработка ошибок (понятно, без сырых стектрейсов)

Каждую известную ошибку перехватывать и переводить в человеческое сообщение + действие:

| Ситуация | Сообщение пользователю | Что делать |
|---|---|---|
| winget отсутствует (старая Win10) | «Не нашёл winget. Открой install-страницу <tool> или обнови Windows» + прямая ссылка/скрипт | предложить ручной installer URL |
| Порт занят чужим процессом (не наш по 2b/2c) | «Порт 8000 занят программой `<имя>` (PID X). Это не Reelibra — закрой её или поменяй APP_PORT в .env» | НЕ убивать чужое, остановиться |
| `uv sync` упал | «Не удалось собрать окружение backend. Пересоздаю с нуля…» → повтор; если опять: показать последние 5 строк вывода, не весь трейс | авто-recreate .venv 1 раз |
| `pnpm install` упал | аналогично: «Не удалось установить зависимости frontend» + prune + retry | retry 1 раз |
| ffmpeg не ставится | «ffmpeg не установился автоматически. Скачай: <ссылка>, распакуй, добавь в PATH» | продолжить без него нельзя — backend упадёт на рендере; предупредить, но дать запуститься (рендер опционален на старте) |
| Нет GEMINI_API_KEY в .env | «GEMINI_API_KEY пуст — пайплайн не сгенерирует рилсы. Открой .env и добавь ключ» | предупреждение, запуск не блокировать |
| backend health не ответил за 30 с | «Backend не поднялся. Последние строки лога: …» (читать `data\logs`) | не открывать браузер, показать лог-хвост |
| Stop-Process «Access denied» | «Не хватает прав остановить PID X. Запусти от администратора» | предложить elevated-перезапуск |

Правило: сырой PowerShell/Python traceback пользователю не показывать — логировать в `data\logs\launcher.log`,
в консоль выводить 1-2 строки сути + что сделать.

---

## Резюме для имплементации

1. **Стек лаунчера:** PowerShell-скрипт (`run.ps1`) или `.bat`-обёртка к нему. Установщик — winget с
   фолбэком на официальные install-скрипты. Раннер процессов — `Start-Process`.
2. **Три вектора поиска висяков** (порт `Get-NetTCPConnection`, cmdline `Win32_Process`, путь репо),
   объединять PID'ы, дедуп, kill каскадом `Stop-Process` → `Stop-Process -Force` → `taskkill /T /F`.
3. **`/T` обязателен** из-за `--reload` reloader-детей (backend) и esbuild-детей (Vite).
4. **strictPort:3000** — порт 3000 ОБЯЗАН быть свободен до старта Vite, иначе hard-fail; чистка порта
   критична именно для фронта.
5. **Артефакты:** удалять `*.partial`, `*.tmp`, orphan `*.lock`, `__pycache__`; НЕ трогать `videomaker.db`
   и финальные медиа.
6. **БД-stale-state не трогаем** — backend lifespan сам делает `running→error` и `uploading→queued`.
7. **PID-файлы** (`data\.run\*.pid`) — добавить для надёжного детекта жёсткого закрытия.
8. **UX:** 4 фазы, health-poll перед открытием браузера, мягко→жёстко на выходе (зеркало `trap cleanup`).
