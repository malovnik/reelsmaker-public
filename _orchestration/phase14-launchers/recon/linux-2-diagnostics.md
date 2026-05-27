# Linux Launcher — Диагностика старта и чистка висяков

Recon-документ для Linux-версии лаунчера Reelibra (видеомейкер).
Цель: на каждом старте дать чистую систему — порты свободны, zombie/orphan
процессы убиты, stale-блокировки сняты, окружение проверено и доустановлено.

Источники истины (изучено в коде):
- `run.sh` — текущий macOS/bash-лаунчер (preflight cleanup на `pgrep`/`lsof`).
- `apps/backend/src/videomaker/main.py:75` — `reset_stale_running_jobs()` на старте lifespan.
- `apps/backend/src/videomaker/services/jobs.py:908` — reset логика: `Job.status==running → error`.
- `apps/backend/src/videomaker/services/proxy.py` — lockfile (`.lock`, O_EXCL, orphan cleanup по mtime) + atomic `.partial`.
- `apps/backend/src/videomaker/core/db.py:28` — SQLite **WAL** (`-wal`/`-shm` файлы — НЕ удалять).
- `apps/frontend/vite.config.*` — Vite, `port: 3000`, `strictPort: true`.
- `.env.example` — `APP_HOST=127.0.0.1`, `APP_PORT=8000`, `FRONTEND_ORIGIN=http://localhost:3000`, данные в `./data/*`.

Ключевые порты: **8000** (uvicorn backend), **3000** (Vite frontend).
Версии: Python `>=3.12,<3.13` (uv), Node + pnpm, ffmpeg.

---

## 1. Схема диагностики окружения (каждый запуск)

Идемпотентная проверка «есть → ок, нет → доустановка с прогрессом». Каждый
шаг возвращает `OK | INSTALLING | FAIL` и пишет понятную причину.

```
[1/7] Системные бинари
      ├─ python3.12  → command -v + python3.12 --version (нужен >=3.12,<3.13)
      ├─ uv          → есть? нет → curl -LsSf https://astral.sh/uv/install.sh | sh
      ├─ node        → command -v node + major >= 20
      ├─ pnpm        → есть? нет → corepack enable pnpm  ИЛИ  npm i -g pnpm
      └─ ffmpeg      → есть? нет → apt/dnf/pacman install (см. детект менеджера)

[2/7] Менеджер пакетов Linux (для ffmpeg, если отсутствует)
      детект: apt-get | dnf | yum | pacman | zypper | apk
      ffmpeg:  apt → sudo apt-get install -y ffmpeg
               dnf → sudo dnf install -y ffmpeg (нужен RPM Fusion)
               pacman → sudo pacman -S --noconfirm ffmpeg
      если sudo недоступен → понятная инструкция вручную, exit.

[3/7] .env
      нет → cp .env.example .env + предупреждение «добавь GEMINI_API_KEY».
      есть → проверить что GEMINI_API_KEY непустой (минимальный ключ).

[4/7] Структура данных
      mkdir -p data/{uploads,artifacts,logs} (+ proxies, transcripts, thumbnails — создаёт сам бэкенд).

[5/7] Backend deps
      cd apps/backend && uv sync   (idempotent, <1с если lock не менялся; с нуля — прогресс uv).
      проверка: .venv существует И uv.lock не новее .venv (иначе re-sync).

[6/7] Frontend deps
      cd apps/frontend && pnpm install --frozen-lockfile
      проверка: node_modules существует И pnpm-lock.yaml совпадает (иначе install).

[7/7] Сводка
      таблица: компонент | статус | версия | действие.
      любой FAIL → стоп с понятным текстом до запуска сервисов.
```

Детект менеджера пакетов (для прогресса/ошибок):

```bash
detect_pkg() {
  for m in apt-get dnf yum pacman zypper apk; do
    command -v "$m" >/dev/null 2>&1 && { echo "$m"; return; }
  done
  echo "unknown"
}
```

Проверка версии Python (узкий диапазон `>=3.12,<3.13`):

```bash
need_py312() {
  command -v python3.12 >/dev/null 2>&1 && return 0
  # uv сам поставит нужный интерпретатор — uv python install 3.12
  uv python install 3.12
}
```

---

## 2. Чистка висяков и портов (Linux)

На Linux предпочитаем `ss` (есть всегда, быстрее) с `lsof` как fallback.
`pgrep -f` — по сигнатурам процессов Reelibra.

### 2.1. Сигнатуры процессов (что искать)

| Процесс | pgrep -f паттерн |
|---|---|
| backend worker | `uvicorn videomaker.main` |
| uv-обёртка | `uv run uvicorn` |
| Vite dev | `node .*vite` |
| esbuild дети | `esbuild --service` или `esbuild.*--service` |
| pnpm обёртка | `pnpm.*dev` |
| residual ffmpeg | `ffmpeg.*data/artifacts` (и `.*data/proxies`) |

Важно: убивать только **свои** ffmpeg (по пути проекта `data/`), не чужие
рендеры пользователя в системе.

### 2.2. Освобождение портов через ss (Linux-нативно)

`lsof -iTCP:PORT` из `run.sh` на Linux часто требует прав/медленный.
Замена на `ss`:

```bash
free_port() {
  local port="$1"
  # ss -ltnp выдаёт строки вида: ... users:(("python",pid=1234,fd=7))
  local pids
  pids="$(ss -ltnHp "sport = :$port" 2>/dev/null \
          | grep -oP 'pid=\K[0-9]+' | sort -u | tr '\n' ' ')"
  if [[ -z "${pids// /}" ]]; then
    # fallback на lsof, если ss без -p (нет прав на чужие сокеты)
    pids="$(lsof -t -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | tr '\n' ' ')"
  fi
  [[ -n "${pids// /}" ]] && echo "$pids"
}
```

Примечание: `ss -p` показывает PID чужих процессов только под root —
для своих процессов работает без sudo. Если порт держит чужой не-Reelibra
процесс — НЕ убивать молча, спросить пользователя (см. UX поток).

### 2.3. Graceful → SIGKILL (двухфазное завершение)

«Жёстко закрыли» = процесс не успел обработать trap. Поэтому:

```
фаза 1 (graceful):  kill -TERM <pids>           # дать закрыть сокеты/flush БД
                    wait_gone <pids> до 5с       # poll: kill -0 пока жив
фаза 2 (hard):      kill -KILL <оставшиеся>      # SIGKILL висякам
                    sleep 1
проверка:           порт снова свободен? нет → FAIL с подсказкой.
```

```bash
kill_graceful() {
  local pids="$1"
  [[ -z "${pids// /}" ]] && return 0
  kill -TERM $pids 2>/dev/null || true
  for _ in $(seq 1 10); do          # до 5с, шаг 0.5с
    local alive=""
    for p in $pids; do kill -0 "$p" 2>/dev/null && alive+="$p "; done
    [[ -z "${alive// /}" ]] && return 0
    sleep 0.5
  done
  kill -KILL $pids 2>/dev/null || true   # висяки — жёстко
  sleep 1
}
```

### 2.4. Зомби и осиротевшие дети

- **Zombie** (`<defunct>`, state Z): убить нельзя — нужен reap родителем.
  Если родитель — наш мёртвый uvicorn, его дети-зомби заберёт init/PID 1
  после SIGKILL родителя. Проверка: `ps -o pid,ppid,stat,comm | awk '$3 ~ /Z/'`
  — если остаются зомби с живым нашим ppid, убить ppid.
- **Orphan ffmpeg** (ppid стал 1 после краха обёртки): отлавливается по
  сигнатуре `ffmpeg.*data/` независимо от ppid → SIGKILL.

### 2.5. Stale-файлы (чистить) vs данные (НЕ трогать)

ЧИСТИТЬ (безопасно, осиротели от краха):
- `data/proxies/*.lock` — orphan-локи. Бэкенд сам чистит по mtime>timeout
  (`proxy.py:_acquire_lock`), но при старте можно удалить **только старые**:
  `find data/proxies -name '*.lock' -mmin +30 -delete`.
- `data/proxies/*.partial` — недописанные ffmpeg-прокси (atomic rename не
  состоялся). Удалять только `.partial` старше N минут И без живого ffmpeg.
- `data/**/*.tmp` — недописанные артефакты (`artifacts.py`, `post_production.py`,
  `asset_store._pending/*.tmp`). Удалять старые tmp.

НЕ ТРОГАТЬ (потеря данных):
- `data/videomaker.db` + **`data/videomaker.db-wal`** + **`data/videomaker.db-shm`**
  (WAL mode — удаление `-wal` теряет незакоммиченные транзакции!).
- `data/uploads/`, `data/artifacts/` (готовые), `data/transcripts/`,
  `data/thumbnails/`, `data/face_cache/`, `data/vision_cache/`, `data/models/`,
  `data/post_production_assets/`.

Безопасная очистка:

```bash
clean_stale_files() {
  find data/proxies  -name '*.lock'    -type f -mmin +30 -delete 2>/dev/null || true
  find data/proxies  -name '*.partial' -type f -mmin +30 -delete 2>/dev/null || true
  find data          -name '*.tmp'     -type f -mmin +30 -delete 2>/dev/null || true
  # __pycache__ — как в run.sh, чтобы подхватились свежие .py
  find apps/backend/src -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
}
```

Порог `+30` мин совпадает с `app_proxy_lock_timeout_sec=1800` (config.py:110) —
не удалять локи активного параллельного процесса.

### 2.6. Stale running-jobs в БД («жёстко закрыли» во время рендера)

Это НЕ работа лаунчера — это делает сам бэкенд на старте lifespan:
`main.py:75 → reset_stale_running_jobs()` (jobs.py:908) переводит все
`Job.status == running` в `error` с текстом `"interrupted by application
restart"`. Лаунчеру делать ничего не нужно — достаточно дать бэкенду
стартовать. В UX-потоке: показать пользователю, если бэкенд залогировал
`stale_jobs_reset_on_startup` (grep по data/logs или по stdout backend).

---

## 3. Детект stale-состояния «жёстко закрыли»

Текущий `run.sh` **не пишет PID-файл** — PID хранятся только в памяти bash
и теряются при kill -9 терминала. Для Linux-лаунчера добавляем PID-файл,
чтобы отличать «чистый старт» от «после краха».

```
PID-файл:  data/logs/reelibra.pid   (строки: "backend <pid>" / "frontend <pid>")

детект stale при старте:
  1. PID-файл существует?
     ├─ нет  → возможно первый старт ИЛИ kill -9 (PID-файл не записался).
     │         падать назад на детект по портам/pgrep.
     └─ да   → читаем PID, kill -0 каждый:
               ├─ жив + наш паттерн → предыдущая сессия НЕ закрылась → чистим.
               └─ мёртв             → stale PID-файл, удаляем, идём дальше.
  2. порт 8000/3000 занят? → см. кто (ss -p):
               ├─ наш процесс (видно uvicorn/vite/node) → kill graceful→hard.
               └─ чужой процесс                          → спросить пользователя.
  3. running-jobs в БД → бэкенд сам сбросит (раздел 2.6), показать сводку.
```

Запись PID-файла после успешного старта; удаление в trap EXIT.

---

## 4. UX-поток лаунчера

Терминал всегда; если есть `$DISPLAY` и `zenity` — дублируем прогресс в GUI.

```
detect_ui() {
  if [[ -n "${DISPLAY:-}" ]] && command -v zenity >/dev/null 2>&1; then
    echo "zenity"; else echo "tty"; fi
}
```

Поток (нумерованные шаги, каждый со статусом):

```
┌─ Reelibra launcher ──────────────────────────────────────┐
│ [1/4] Проверка окружения                                 │
│   python 3.12 ........ OK (3.12.7)                        │
│   uv ................. OK (0.5.1)                         │
│   node ............... OK (v22.3)                         │
│   pnpm ............... OK (9.x)                           │
│   ffmpeg ............. УСТАНАВЛИВАЮ… [apt-get] ▓▓▓▓░ 80%  │
│                                                          │
│ [2/4] Чистка предыдущей сессии                           │
│   PID-файл: найден (краш предыдущего старта)             │
│   backend (pid 4012) .. graceful TERM → закрыт           │
│   vite    (pid 4090) .. graceful TERM → KILL (висяк)     │
│   порт 8000 ........... освобождён                       │
│   порт 3000 ........... освобождён                       │
│   stale .lock/.partial/.tmp .. удалено 3                 │
│                                                          │
│ [3/4] Зависимости                                        │
│   backend (uv sync) ... OK (<1с)                         │
│   frontend (pnpm) ..... OK (<1с)                         │
│                                                          │
│ [4/4] Запуск                                             │
│   backend  → http://127.0.0.1:8000/docs (pid …)          │
│   frontend → http://localhost:3000 (pid …)               │
│   ⚠ бэкенд сбросил 2 зависших job (interrupted restart)  │
│   Ctrl+C останавливает оба                               │
└──────────────────────────────────────────────────────────┘
```

zenity-вариант: `zenity --progress --pulsate` для длинных шагов
(установка ffmpeg, первый uv sync / pnpm install) с обновлением `--text`;
по завершении `--info` со списком URL или `--error` при FAIL.

---

## 5. Понятные ошибки (каждая = причина + действие)

| Ситуация | Сообщение пользователю |
|---|---|
| Нет uv | `uv не найден. Устанавливаю автоматически… (или: curl -LsSf https://astral.sh/uv/install.sh \| sh)` |
| Нет ffmpeg, нет sudo | `ffmpeg отсутствует, нет прав на установку. Установи вручную: sudo apt-get install ffmpeg` |
| Неизвестный пакетный менеджер | `Не распознан менеджер пакетов. Установи ffmpeg вручную и перезапусти.` |
| Порт 8000 держит чужой процесс | `Порт 8000 занят процессом <name> (pid X), не относящимся к Reelibra. Закрыть его? [y/N]` |
| Порт не освободился после SIGKILL | `Не удалось освободить порт 8000 (pid X жив). Проверь права / TIME_WAIT, перезапусти.` |
| .env без GEMINI_API_KEY | `.env создан из примера. Добавь GEMINI_API_KEY перед запуском пайплайна.` |
| uv sync упал | `Установка backend-зависимостей не удалась. Лог: <вывод uv>. Проверь Python 3.12 и сеть.` |
| pnpm install упал | `Установка frontend-зависимостей не удалась: <вывод pnpm>. Проверь node>=20 и lockfile.` |
| Python вне диапазона | `Нужен Python >=3.12,<3.13. uv поставит сам: uv python install 3.12` |
| Зомби не уходят | `Остались defunct-процессы под нашим ppid X — убиваю родителя.` |

---

## 6. Сводка отличий от текущего run.sh (что меняем для Linux)

1. `lsof -iTCP` → **`ss -ltnp`** (нативно, без прав на свои сокеты, быстрее).
2. Установка ffmpeg: `brew` → **детект apt/dnf/pacman/zypper/apk**.
3. `pnpm` install: `npm i -g pnpm` → **corepack enable pnpm** (Linux-friendly).
4. Добавить **PID-файл** `data/logs/reelibra.pid` → детект «жёстко закрыли».
5. Двухфазное завершение **TERM→(poll 5с)→KILL** вместо сразу `kill -9`
   (graceful flush БД/сокетов; SIGKILL только висякам).
6. Чистка `.lock`/`.partial`/`.tmp` с порогом **mmin +30** (= proxy lock timeout),
   строго НЕ трогая `*.db`/`*-wal`/`*-shm`/`data/`-контент.
7. UX: прогресс в tty + опциональный **zenity** при наличии `$DISPLAY`.
8. Обработка **зомби/orphan ffmpeg** по сигнатуре пути проекта.
9. running-jobs reset — оставить бэкенду (`reset_stale_running_jobs`), лаунчер
   только показывает результат.
```
