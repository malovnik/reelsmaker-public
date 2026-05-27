#!/usr/bin/env bash
# lib.sh — общая логика Linux-лаунчера Reelibra (bootstrap + диагностика + чистка).
# Подключается через `source` из launcher.sh и install.sh. Сам по себе не запускается.
#
# Принципы (см. recon linux-1/2/3):
#   - Никакого sudo и системных пакетников. Всё портативно в user-space.
#   - Идемпотентность: есть нужная версия → используем, нет → доустанавливаем.
#   - Гейт: x86_64 + glibc >= 2.35, иначе честный отказ.
#   - Чистка висяков: TERM → 5с → KILL. Никогда не трогаем *.db / -wal / -shm / data-контент.
#   - Все сообщения пользователю — по-русски, причина + действие.

set -euo pipefail

#─── Константы окружения ─────────────────────────────────────────────────────

# REELIBRA_ROOT задаётся вызывающим скриптом (корень репозитория).
: "${REELIBRA_ROOT:?REELIBRA_ROOT не задан — lib.sh должен подключаться из launcher.sh/install.sh}"

# Портативные рантаймы. По умолчанию — рядом с репо (виден, удаляется вместе с папкой),
# но можно переопределить в ~/.local/share/reelibra через REELIBRA_RUNTIME_HOME.
RUNTIME_DIR="${REELIBRA_RUNTIME_HOME:-$REELIBRA_ROOT/.reelibra-runtime}"
CACHE_DIR="$RUNTIME_DIR/cache"
PY_DIR="$RUNTIME_DIR/python"          # python-build-standalone 3.12
NODE_DIR="$RUNTIME_DIR/node"          # portable node 20
FFMPEG_DIR="$RUNTIME_DIR/ffmpeg"      # static ffmpeg
UV_HOME="$RUNTIME_DIR/uv"             # uv installer target (XDG_BIN_HOME)

# Целевые версии.
PY_VERSION="3.12.8"
PY_BUILD_TAG="20241219"               # релиз python-build-standalone
NODE_VERSION="20.18.1"
NODE_MAJOR_MIN=20
FFMPEG_MAJOR_MIN=7

# Порты (см. .env.example: APP_PORT=8000, frontend Vite 3000).
BACKEND_PORT=8000
FRONTEND_PORT=3000

# PID-файл (по заданию: data/.run/reelibra.pid).
RUN_DIR="$REELIBRA_ROOT/data/.run"
PID_FILE="$RUN_DIR/reelibra.pid"

GLIBC_MIN_MAJOR=2
GLIBC_MIN_MINOR=35

#─── UI: терминал + опциональный zenity ──────────────────────────────────────

C_RESET=$'\033[0m'; C_BOLD=$'\033[1m'; C_DIM=$'\033[2m'
C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'; C_RED=$'\033[31m'; C_CYAN=$'\033[36m'

UI_MODE="tty"
ZENITY_PIPE=""

detect_ui() {
    if [[ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]] && command -v zenity >/dev/null 2>&1; then
        UI_MODE="zenity"
    else
        UI_MODE="tty"
    fi
}

# Открыть фоновый zenity-прогресс (pulsate) — пишем в его stdin через FIFO.
zenity_progress_start() {
    [[ "$UI_MODE" == "zenity" ]] || return 0
    ZENITY_PIPE="$(mktemp -u "${TMPDIR:-/tmp}/reelibra-zenity.XXXXXX")"
    mkfifo "$ZENITY_PIPE" 2>/dev/null || { ZENITY_PIPE=""; return 0; }
    ( zenity --progress --pulsate --auto-close --no-cancel \
        --title="Reelibra" --text="Запуск…" --width=420 < "$ZENITY_PIPE" >/dev/null 2>&1 || true ) &
    # Держим FIFO открытым на запись, чтобы zenity не закрылся раньше времени.
    exec 9>"$ZENITY_PIPE"
}

zenity_progress_msg() {
    [[ -n "$ZENITY_PIPE" ]] || return 0
    printf '# %s\n' "$1" >&9 2>/dev/null || true
}

zenity_progress_stop() {
    [[ -n "$ZENITY_PIPE" ]] || return 0
    printf '100\n' >&9 2>/dev/null || true
    exec 9>&- 2>/dev/null || true
    rm -f "$ZENITY_PIPE" 2>/dev/null || true
    ZENITY_PIPE=""
}

step()  { printf '%s[%s]%s %s\n' "$C_CYAN$C_BOLD" "$1" "$C_RESET" "$2"; zenity_progress_msg "$2"; }
ok()    { printf '   %s✓%s %s\n' "$C_GREEN" "$C_RESET" "$1"; }
warn()  { printf '   %s!%s %s\n' "$C_YELLOW" "$C_RESET" "$1"; }
info()  { printf '   %s·%s %s\n' "$C_DIM" "$C_RESET" "$1"; }

# Фатальная ошибка: терминал + zenity --error, затем exit 1.
die() {
    local msg="$1"
    printf '\n%s✗ %s%s\n' "$C_RED$C_BOLD" "$msg" "$C_RESET" >&2
    if [[ "$UI_MODE" == "zenity" ]]; then
        zenity_progress_stop
        zenity --error --title="Reelibra — ошибка" --width=480 --text="$msg" >/dev/null 2>&1 || true
    fi
    exit 1
}

#─── Гейт: архитектура + glibc ────────────────────────────────────────────────

check_platform_gate() {
    local arch
    arch="$(uname -m)"
    if [[ "$arch" != "x86_64" ]]; then
        die "Архитектура $arch не поддерживается. Reelibra на Linux работает только на x86_64 (Intel/AMD 64-бит).
ARM64 и другие архитектуры пока вне поддержки (нет ML-wheels mediapipe/llama-cpp)."
    fi

    # musl (Alpine) не годится — ML-wheels только glibc.
    if ! ldd --version 2>&1 | head -1 | grep -qiE 'glibc|gnu libc'; then
        if [[ -f /etc/alpine-release ]] || ldd --version 2>&1 | grep -qi musl; then
            die "Обнаружена musl libc (Alpine?). Нужна glibc >= 2.35.
ML-зависимости (mediapipe, llama-cpp, onnxruntime) не имеют musl-сборок. Используй Ubuntu 22.04+/Fedora 37+."
        fi
    fi

    # Версия glibc.
    local glibc_ver major minor
    glibc_ver="$(ldd --version 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+' | head -1)"
    if [[ -z "$glibc_ver" ]]; then
        warn "Не удалось определить версию glibc — продолжаю, но при ошибках wheel'ов нужна glibc >= 2.35."
        return 0
    fi
    major="${glibc_ver%%.*}"
    minor="${glibc_ver#*.}"
    if (( major < GLIBC_MIN_MAJOR )) || { (( major == GLIBC_MIN_MAJOR )) && (( minor < GLIBC_MIN_MINOR )); }; then
        die "glibc $glibc_ver слишком старая. Нужна >= $GLIBC_MIN_MAJOR.$GLIBC_MIN_MINOR (Ubuntu 22.04+, Debian 12+, Fedora 37+).
Старые дистрибутивы (Ubuntu 20.04, CentOS 7) не поддерживаются — ML-wheels не встанут."
    fi
    ok "Платформа: x86_64, glibc $glibc_ver"
}

check_network() {
    # Лёгкая проверка сети перед скачиванием рантаймов.
    local host
    for host in astral.sh nodejs.org github.com; do
        if command -v curl >/dev/null 2>&1; then
            curl -sSf --connect-timeout 6 -o /dev/null "https://$host" 2>/dev/null && return 0
        elif command -v wget >/dev/null 2>&1; then
            wget -q --timeout=6 -O /dev/null "https://$host" 2>/dev/null && return 0
        fi
    done
    return 1
}

#─── Скачивание с прогрессом ──────────────────────────────────────────────────

download() {
    # download <url> <dest>
    local url="$1" dest="$2"
    mkdir -p "$(dirname "$dest")"
    local tmp="$dest.partial"
    rm -f "$tmp"
    if command -v curl >/dev/null 2>&1; then
        curl -fL --retry 3 --retry-delay 2 --connect-timeout 15 -o "$tmp" "$url" \
            || { rm -f "$tmp"; return 1; }
    elif command -v wget >/dev/null 2>&1; then
        wget -q --tries=3 --timeout=15 -O "$tmp" "$url" \
            || { rm -f "$tmp"; return 1; }
    else
        die "Нет ни curl, ни wget — нечем скачать рантаймы. Установи: sudo apt-get install curl"
    fi
    mv -f "$tmp" "$dest"
}

#─── Резолв бинарей: bundle → system → download ──────────────────────────────

# Глобальные пути к выбранным бинарям (заполняются ensure_*).
PY_BIN=""
NODE_BIN=""
NPM_BIN=""
PNPM_BIN=""
FFMPEG_BIN=""
UV_BIN=""

version_ge() {
    # version_ge <have> <min> — сравнение dotted-версий.
    [[ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -1)" == "$2" ]]
}

ensure_python() {
    # 1) bundle
    if [[ -x "$PY_DIR/bin/python3.12" ]]; then
        PY_BIN="$PY_DIR/bin/python3.12"; ok "Python 3.12 (bundle): $("$PY_BIN" --version 2>&1)"; return 0
    fi
    # 2) system python3.12 строго в диапазоне >=3.12,<3.13
    if command -v python3.12 >/dev/null 2>&1; then
        local v; v="$(python3.12 -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null || echo "")"
        if [[ "$v" == "3.12" ]]; then
            PY_BIN="$(command -v python3.12)"; ok "Python 3.12 (системный): $("$PY_BIN" --version 2>&1)"; return 0
        fi
    fi
    # 3) download python-build-standalone
    step "..." "Скачиваю портативный Python 3.12…"
    check_network || die "Нет сети — не могу скачать Python 3.12. Подключись к интернету и перезапусти."
    local fname="cpython-${PY_VERSION}+${PY_BUILD_TAG}-x86_64-unknown-linux-gnu-install_only.tar.gz"
    local url="https://github.com/astral-sh/python-build-standalone/releases/download/${PY_BUILD_TAG}/${fname}"
    local tarball="$CACHE_DIR/$fname"
    [[ -f "$tarball" ]] || download "$url" "$tarball" \
        || die "Не удалось скачать Python 3.12 ($url). Проверь сеть и перезапусти."
    # install_only-архив распаковывается в каталог python/ → ровно в $PY_DIR.
    rm -rf "$PY_DIR"
    tar -xzf "$tarball" -C "$RUNTIME_DIR" \
        || die "Архив Python повреждён. Удали $tarball и перезапусти."
    [[ -x "$PY_DIR/bin/python3.12" ]] || die "Распаковка Python не дала bin/python3.12 — архив неожиданной структуры."
    PY_BIN="$PY_DIR/bin/python3.12"
    ok "Python 3.12 установлен: $("$PY_BIN" --version 2>&1)"
}

ensure_uv() {
    # 1) bundle
    if [[ -x "$UV_HOME/uv" ]]; then
        UV_BIN="$UV_HOME/uv"; ok "uv (bundle): $("$UV_BIN" --version 2>&1)"; return 0
    fi
    # 2) system
    if command -v uv >/dev/null 2>&1; then
        UV_BIN="$(command -v uv)"; ok "uv (системный): $("$UV_BIN" --version 2>&1)"; return 0
    fi
    # 3) официальный installer в user-space (без root)
    step "..." "Устанавливаю uv (astral installer)…"
    check_network || die "Нет сети — не могу установить uv. Альтернатива: curl -LsSf https://astral.sh/uv/install.sh | sh"
    mkdir -p "$UV_HOME"
    # XDG_BIN_HOME направляет installer в наш каталог, без записи в ~/.local/bin и без модификации профиля.
    if command -v curl >/dev/null 2>&1; then
        curl -LsSf https://astral.sh/uv/install.sh \
            | env UV_INSTALL_DIR="$UV_HOME" XDG_BIN_HOME="$UV_HOME" INSTALLER_NO_MODIFY_PATH=1 sh \
            || die "Установка uv не удалась. Установи вручную: curl -LsSf https://astral.sh/uv/install.sh | sh"
    else
        wget -qO- https://astral.sh/uv/install.sh \
            | env UV_INSTALL_DIR="$UV_HOME" XDG_BIN_HOME="$UV_HOME" INSTALLER_NO_MODIFY_PATH=1 sh \
            || die "Установка uv не удалась. Установи вручную: curl -LsSf https://astral.sh/uv/install.sh | sh"
    fi
    [[ -x "$UV_HOME/uv" ]] || die "uv установился не туда, ожидался $UV_HOME/uv."
    UV_BIN="$UV_HOME/uv"
    ok "uv установлен: $("$UV_BIN" --version 2>&1)"
}

ensure_node() {
    # 1) bundle
    if [[ -x "$NODE_DIR/bin/node" ]]; then
        NODE_BIN="$NODE_DIR/bin/node"; NPM_BIN="$NODE_DIR/bin/npm"
        ok "Node (bundle): $("$NODE_BIN" --version 2>&1)"; return 0
    fi
    # 2) system node >= 20
    if command -v node >/dev/null 2>&1; then
        local v; v="$(node --version 2>/dev/null | sed 's/^v//')"
        local maj="${v%%.*}"
        if [[ -n "$maj" ]] && (( maj >= NODE_MAJOR_MIN )); then
            NODE_BIN="$(command -v node)"
            NPM_BIN="$(command -v npm || echo "$NODE_BIN")"
            ok "Node (системный): v$v"; return 0
        fi
    fi
    # 3) download portable node 20
    step "..." "Скачиваю портативный Node ${NODE_VERSION}…"
    check_network || die "Нет сети — не могу скачать Node. Подключись к интернету и перезапусти."
    local fname="node-v${NODE_VERSION}-linux-x64.tar.xz"
    local url="https://nodejs.org/dist/v${NODE_VERSION}/${fname}"
    local tarball="$CACHE_DIR/$fname"
    [[ -f "$tarball" ]] || download "$url" "$tarball" \
        || die "Не удалось скачать Node ($url). Проверь сеть и перезапусти."
    rm -rf "$NODE_DIR"; mkdir -p "$NODE_DIR"
    tar -xJf "$tarball" -C "$NODE_DIR" --strip-components=1 \
        || die "Архив Node повреждён. Удали $tarball и перезапусти."
    [[ -x "$NODE_DIR/bin/node" ]] || die "Распаковка Node не дала bin/node."
    NODE_BIN="$NODE_DIR/bin/node"; NPM_BIN="$NODE_DIR/bin/npm"
    ok "Node установлен: $("$NODE_BIN" --version 2>&1)"
}

ensure_pnpm() {
    # pnpm через corepack (идёт в составе Node 20). Активируем в нашем NODE_DIR/bin.
    local node_bindir; node_bindir="$(dirname "$NODE_BIN")"
    # 1) corepack-shim рядом с node
    if [[ -x "$node_bindir/pnpm" ]]; then
        PNPM_BIN="$node_bindir/pnpm"; ok "pnpm: $(PATH="$node_bindir:$PATH" "$PNPM_BIN" --version 2>&1)"; return 0
    fi
    # 2) системный pnpm
    if command -v pnpm >/dev/null 2>&1; then
        PNPM_BIN="$(command -v pnpm)"; ok "pnpm (системный): $("$PNPM_BIN" --version 2>&1)"; return 0
    fi
    # 3) corepack enable
    if [[ -x "$node_bindir/corepack" ]]; then
        step "..." "Активирую pnpm через corepack…"
        PATH="$node_bindir:$PATH" "$node_bindir/corepack" enable --install-directory "$node_bindir" pnpm 2>/dev/null \
            || PATH="$node_bindir:$PATH" "$node_bindir/corepack" enable pnpm 2>/dev/null || true
        PATH="$node_bindir:$PATH" "$node_bindir/corepack" prepare pnpm@latest --activate 2>/dev/null || true
        if [[ -x "$node_bindir/pnpm" ]]; then
            PNPM_BIN="$node_bindir/pnpm"; ok "pnpm активирован: $(PATH="$node_bindir:$PATH" "$PNPM_BIN" --version 2>&1)"; return 0
        fi
    fi
    # 4) npm i -g pnpm в наш node-prefix
    if [[ -x "$NPM_BIN" ]]; then
        step "..." "Устанавливаю pnpm через npm…"
        PATH="$node_bindir:$PATH" "$NPM_BIN" install -g pnpm --prefix "$(dirname "$node_bindir")" >/dev/null 2>&1 || true
        if [[ -x "$node_bindir/pnpm" ]]; then
            PNPM_BIN="$node_bindir/pnpm"; ok "pnpm установлен через npm"; return 0
        fi
    fi
    die "Не удалось получить pnpm (ни corepack, ни npm). Установи вручную: corepack enable pnpm"
}

ensure_ffmpeg() {
    # 1) bundle
    if [[ -x "$FFMPEG_DIR/ffmpeg" ]]; then
        FFMPEG_BIN="$FFMPEG_DIR/ffmpeg"; ok "ffmpeg (bundle): $("$FFMPEG_BIN" -version 2>/dev/null | head -1)"; return 0
    fi
    # 2) system ffmpeg >= 7
    if command -v ffmpeg >/dev/null 2>&1; then
        local v; v="$(ffmpeg -version 2>/dev/null | head -1 | grep -oE '[0-9]+(\.[0-9]+)*' | head -1)"
        local maj="${v%%.*}"
        if [[ -n "$maj" ]] && (( maj >= FFMPEG_MAJOR_MIN )); then
            FFMPEG_BIN="$(command -v ffmpeg)"; ok "ffmpeg (системный): $v"; return 0
        else
            info "Системный ffmpeg $v < $FFMPEG_MAJOR_MIN — ставлю портативный static build."
        fi
    fi
    # 3) static build (johnvansickle, glibc-free)
    step "..." "Скачиваю статичный ffmpeg…"
    check_network || die "Нет сети — не могу скачать ffmpeg. Подключись к интернету и перезапусти."
    local fname="ffmpeg-release-amd64-static.tar.xz"
    local url="https://johnvansickle.com/ffmpeg/releases/${fname}"
    local tarball="$CACHE_DIR/$fname"
    [[ -f "$tarball" ]] || download "$url" "$tarball" \
        || die "Не удалось скачать ffmpeg ($url). Проверь сеть или установи системный: sudo apt-get install ffmpeg"
    rm -rf "$FFMPEG_DIR"; mkdir -p "$FFMPEG_DIR"
    tar -xJf "$tarball" -C "$FFMPEG_DIR" --strip-components=1 \
        || die "Архив ffmpeg повреждён. Удали $tarball и перезапусти."
    [[ -x "$FFMPEG_DIR/ffmpeg" ]] || die "Распаковка ffmpeg не дала бинарь ffmpeg."
    FFMPEG_BIN="$FFMPEG_DIR/ffmpeg"
    ok "ffmpeg установлен: $("$FFMPEG_BIN" -version 2>/dev/null | head -1)"
}

#─── .env и структура данных ──────────────────────────────────────────────────

ensure_env() {
    cd "$REELIBRA_ROOT"
    if [[ ! -f .env ]]; then
        if [[ -f .env.example ]]; then
            cp .env.example .env
            warn ".env создан из .env.example — добавь GEMINI_API_KEY (и DEEPGRAM_API_KEY для STT) перед запуском пайплайна."
        else
            warn ".env и .env.example отсутствуют — backend стартует на дефолтах, без API-ключей пайплайн не сработает."
            return 0
        fi
    fi
    # Мягкая проверка ключей (не блокируем старт — UI всё равно поднимется).
    if [[ -f .env ]]; then
        grep -qE '^GEMINI_API_KEY=.+' .env 2>/dev/null \
            || warn "В .env пуст GEMINI_API_KEY — LLM-анализ не заработает без ключа."
        # Honesty про STT на Linux: MLX не работает, нужен Deepgram.
        if ! grep -qE '^DEEPGRAM_API_KEY=.+' .env 2>/dev/null; then
            warn "На Linux транскрипция (STT) работает ТОЛЬКО через Deepgram — MLX/Apple-Whisper недоступны."
            warn "Добавь DEEPGRAM_API_KEY в .env, иначе шаг распознавания речи завершится ошибкой."
        fi
    fi
}

ensure_data_dirs() {
    mkdir -p "$REELIBRA_ROOT/data/uploads" \
             "$REELIBRA_ROOT/data/artifacts" \
             "$REELIBRA_ROOT/data/logs" \
             "$RUN_DIR"
    ok "Каталоги данных готовы"
}

#─── Зависимости backend/frontend (идемпотентно) ─────────────────────────────

sync_backend() {
    step "..." "Backend-зависимости (uv sync)…"
    local be="$REELIBRA_ROOT/apps/backend"
    [[ -d "$be" ]] || die "Не найден apps/backend — структура репозитория нарушена."
    # uv использует наш портативный Python (UV_PYTHON), не качает свой.
    # Если репо ещё содержит mlx-* hard-deps без platform-маркеров — uv sync может упасть на Linux.
    # Это известный продуктовый блокер (см. recon): сообщаем честно.
    if ! ( cd "$be" && env \
            UV_PYTHON="$PY_BIN" \
            UV_CACHE_DIR="$CACHE_DIR/uv" \
            "$UV_BIN" sync --quiet ); then
        die "Установка backend-зависимостей (uv sync) не удалась.
Частая причина на Linux: пакеты mlx-whisper / stable-ts[mlx] (Apple-only) прописаны как жёсткие зависимости.
Их нужно пометить platform-маркером ('; sys_platform == \"darwin\"') в apps/backend/pyproject.toml.
Также проверь сеть и доступность Python 3.12."
    fi
    ok "Backend-зависимости установлены"
}

sync_frontend() {
    step "..." "Frontend-зависимости (pnpm install)…"
    local fe="$REELIBRA_ROOT/apps/frontend"
    [[ -d "$fe" ]] || die "Не найден apps/frontend — структура репозитория нарушена."
    local node_bindir; node_bindir="$(dirname "$NODE_BIN")"
    local lock_flag=""
    [[ -f "$fe/pnpm-lock.yaml" ]] && lock_flag="--frozen-lockfile"
    if ! ( cd "$fe" && PATH="$node_bindir:$PATH" "$PNPM_BIN" install $lock_flag --silent ); then
        # frozen-lockfile может упасть если lock рассинхронен — пробуем обычный install.
        warn "pnpm install --frozen-lockfile не прошёл, пробую обычный install…"
        ( cd "$fe" && PATH="$node_bindir:$PATH" "$PNPM_BIN" install --silent ) \
            || die "Установка frontend-зависимостей не удалась. Проверь Node >= 20 и pnpm-lock.yaml."
    fi
    ok "Frontend-зависимости установлены"
}

#─── Чистка висяков и портов ──────────────────────────────────────────────────

# Сигнатуры процессов Reelibra (см. run.sh / recon linux-2).
PROC_PATTERNS=(
    "uvicorn videomaker.main"
    "uv run uvicorn"
    "node .*vite"
    "esbuild .*--service"
    "pnpm.*dev"
)

# PID'ы по сигнатуре.
pids_by_pattern() {
    pgrep -f "$1" 2>/dev/null | tr '\n' ' ' || true
}

# Только наши ffmpeg — по пути проекта data/, не чужие рендеры пользователя.
pids_orphan_ffmpeg() {
    pgrep -f "ffmpeg.*${REELIBRA_ROOT//\//\\/}/data/" 2>/dev/null | tr '\n' ' ' || true
}

# PID'ы, слушающие порт. ss (нативно) → lsof (fallback).
pids_on_port() {
    local port="$1" pids=""
    if command -v ss >/dev/null 2>&1; then
        pids="$(ss -ltnHp "sport = :$port" 2>/dev/null | grep -oE 'pid=[0-9]+' | grep -oE '[0-9]+' | sort -u | tr '\n' ' ')"
    fi
    if [[ -z "${pids// /}" ]] && command -v lsof >/dev/null 2>&1; then
        pids="$(lsof -t -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | sort -u | tr '\n' ' ')"
    fi
    printf '%s' "$pids"
}

# Двухфазное завершение: TERM → poll 5с → KILL.
kill_graceful() {
    local pids="$1"
    [[ -z "${pids// /}" ]] && return 0
    # shellcheck disable=SC2086
    kill -TERM $pids 2>/dev/null || true
    local i alive
    for i in $(seq 1 10); do   # до 5с шагом 0.5с
        alive=""
        for p in $pids; do kill -0 "$p" 2>/dev/null && alive+="$p "; done
        [[ -z "${alive// /}" ]] && return 0
        sleep 0.5
    done
    # shellcheck disable=SC2086
    kill -KILL $pids 2>/dev/null || true
    sleep 1
}

# Описание процесса по pid (для honesty про чужие процессы на порту).
proc_desc() {
    local pid="$1"
    ps -o comm= -p "$pid" 2>/dev/null | head -1
}

# Является ли pid нашим (по сигнатурам)?
is_our_pid() {
    local pid="$1" cmd
    cmd="$(ps -o args= -p "$pid" 2>/dev/null || true)"
    [[ -z "$cmd" ]] && return 1
    local pat
    for pat in "${PROC_PATTERNS[@]}" "ffmpeg.*${REELIBRA_ROOT}/data/"; do
        [[ "$cmd" =~ $pat ]] && return 0
    done
    return 1
}

free_port() {
    local port="$1" pids p mine="" foreign=""
    pids="$(pids_on_port "$port")"
    [[ -z "${pids// /}" ]] && { ok "Порт $port свободен"; return 0; }
    for p in $pids; do
        if is_our_pid "$p"; then mine+="$p "; else foreign+="$p "; fi
    done
    if [[ -n "${mine// /}" ]]; then
        info "Порт $port держат наши процессы ($mine) — завершаю."
        kill_graceful "$mine"
    fi
    if [[ -n "${foreign// /}" ]]; then
        local names=""
        for p in $foreign; do names+="$(proc_desc "$p")(pid $p) "; done
        warn "Порт $port занят ЧУЖИМ процессом: $names"
        # В неинтерактивном (.desktop Terminal=true но без stdin tty) — не убиваем чужое молча.
        if [[ -t 0 ]]; then
            printf '   %sЗакрыть его? Это не процесс Reelibra. [y/N]: %s' "$C_YELLOW" "$C_RESET"
            local ans; read -r ans
            if [[ "$ans" =~ ^[Yy]$ ]]; then
                kill_graceful "$foreign"
            else
                die "Порт $port занят чужим процессом ($names). Закрой его вручную и перезапусти."
            fi
        else
            die "Порт $port занят чужим процессом ($names), не относящимся к Reelibra. Закрой его вручную и перезапусти."
        fi
    fi
    # Проверка результата.
    pids="$(pids_on_port "$port")"
    if [[ -n "${pids// /}" ]]; then
        die "Не удалось освободить порт $port (pid$pids ещё жив). Проверь права или TIME_WAIT, перезапусти позже."
    fi
    ok "Порт $port освобождён"
}

# Чистка stale-файлов. НИКОГДА не трогаем *.db / -wal / -shm / готовые артефакты.
clean_stale_files() {
    local d="$REELIBRA_ROOT/data"
    [[ -d "$d" ]] || return 0
    local n=0
    n=$(( n + $(find "$d/proxies" -name '*.lock'    -type f -mmin +30 -print -delete 2>/dev/null | wc -l) ))
    n=$(( n + $(find "$d/proxies" -name '*.partial' -type f -mmin +30 -print -delete 2>/dev/null | wc -l) ))
    n=$(( n + $(find "$d"         -name '*.tmp'     -type f -mmin +30 -print -delete 2>/dev/null | wc -l) ))
    # bytecode — как в run.sh, чтобы подхватились свежие .py.
    find "$REELIBRA_ROOT/apps/backend/src" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
    if (( n > 0 )); then ok "Удалено stale-файлов: $n (.lock/.partial/.tmp старше 30 мин)"; else info "Stale-файлов нет"; fi
}

# Зомби под нашим мёртвым родителем — убираем родителя.
reap_zombies() {
    local line pid ppid stat
    while read -r pid ppid stat _; do
        [[ "$stat" == Z* ]] || continue
        # Если родитель ещё жив и это наш процесс — добиваем родителя.
        if kill -0 "$ppid" 2>/dev/null && is_our_pid "$ppid"; then
            warn "Зомби (pid $pid) под нашим родителем (pid $ppid) — завершаю родителя."
            kill -KILL "$ppid" 2>/dev/null || true
        fi
    done < <(ps -eo pid=,ppid=,stat= 2>/dev/null)
}

# Главная процедура чистки предыдущей сессии.
cleanup_previous_session() {
    # 1) PID-файл → детект «жёстко закрыли».
    if [[ -f "$PID_FILE" ]]; then
        local role pid
        while read -r role pid; do
            [[ -n "$pid" ]] || continue
            if kill -0 "$pid" 2>/dev/null && is_our_pid "$pid"; then
                info "PID-файл: $role (pid $pid) ещё жив — предыдущая сессия не закрылась."
                kill_graceful "$pid"
            fi
        done < "$PID_FILE"
        rm -f "$PID_FILE"
    fi

    # 2) Добиваем по сигнатурам (на случай если PID-файла не было — kill -9 терминала).
    local pat pids
    for pat in "${PROC_PATTERNS[@]}"; do
        pids="$(pids_by_pattern "$pat")"
        [[ -n "${pids// /}" ]] && { info "Остаточные ($pat): $pids"; kill_graceful "$pids"; }
    done
    pids="$(pids_orphan_ffmpeg)"
    [[ -n "${pids// /}" ]] && { warn "Orphan ffmpeg нашего проекта: $pids"; kill_graceful "$pids"; }

    # 3) Зомби.
    reap_zombies

    # 4) Порты.
    free_port "$BACKEND_PORT"
    free_port "$FRONTEND_PORT"

    # 5) Stale-файлы.
    clean_stale_files
}

#─── Запуск сервисов ──────────────────────────────────────────────────────────

BACKEND_PID=""
FRONTEND_PID=""

write_pid_file() {
    mkdir -p "$RUN_DIR"
    {
        [[ -n "$BACKEND_PID" ]]  && echo "backend $BACKEND_PID"
        [[ -n "$FRONTEND_PID" ]] && echo "frontend $FRONTEND_PID"
    } > "$PID_FILE"
}

runtime_cleanup() {
    printf '\n%s[Reelibra] останавливаю процессы…%s\n' "$C_DIM" "$C_RESET"
    [[ -n "$BACKEND_PID" ]]  && kill -TERM "$BACKEND_PID"  2>/dev/null || true
    [[ -n "$FRONTEND_PID" ]] && kill -TERM "$FRONTEND_PID" 2>/dev/null || true
    sleep 2
    local pat
    for pat in "${PROC_PATTERNS[@]}"; do
        # shellcheck disable=SC2046
        kill -KILL $(pgrep -f "$pat" 2>/dev/null | tr '\n' ' ') 2>/dev/null || true
    done
    rm -f "$PID_FILE" 2>/dev/null || true
    wait 2>/dev/null || true
    printf '%s[Reelibra] выход%s\n' "$C_DIM" "$C_RESET"
}

# HTTP health-poll: ждём, пока URL начнёт отвечать.
wait_health() {
    local url="$1" name="$2" tries="${3:-60}"
    local i
    for i in $(seq 1 "$tries"); do
        if command -v curl >/dev/null 2>&1; then
            curl -sf -o /dev/null --max-time 2 "$url" && { ok "$name отвечает ($url)"; return 0; }
        elif command -v wget >/dev/null 2>&1; then
            wget -q --timeout=2 -O /dev/null "$url" && { ok "$name отвечает ($url)"; return 0; }
        fi
        # Если процесс умер — нет смысла ждать.
        [[ "$name" == "backend" && -n "$BACKEND_PID" ]] && { kill -0 "$BACKEND_PID" 2>/dev/null || { warn "$name упал на старте."; return 1; }; }
        sleep 1
    done
    warn "$name не ответил за ${tries}с — проверь логи."
    return 1
}

open_browser() {
    local url="$1"
    if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$url" >/dev/null 2>&1 &
    else
        warn "xdg-open не найден — открой вручную в браузере: $url"
    fi
}

start_services() {
    local be="$REELIBRA_ROOT/apps/backend"
    local fe="$REELIBRA_ROOT/apps/frontend"
    local node_bindir; node_bindir="$(dirname "$NODE_BIN")"
    local ff_dir; ff_dir="$(dirname "$FFMPEG_BIN")"

    # Загружаем APP_HOST/APP_PORT из .env, если есть.
    local app_host="127.0.0.1" app_port="$BACKEND_PORT"
    if [[ -f "$REELIBRA_ROOT/.env" ]]; then
        local h p
        h="$(grep -E '^APP_HOST=' "$REELIBRA_ROOT/.env" | tail -1 | cut -d= -f2- | tr -d '"'"'"' ' || true)"
        p="$(grep -E '^APP_PORT=' "$REELIBRA_ROOT/.env" | tail -1 | cut -d= -f2- | tr -d '"'"'"' ' || true)"
        [[ -n "$h" ]] && app_host="$h"
        [[ -n "$p" ]] && app_port="$p"
    fi

    # PATH с нашими портативными бинарями (ffmpeg/node/uv видны пайплайну).
    local launch_path="$ff_dir:$node_bindir:$UV_HOME:$PATH"

    step "..." "Запускаю backend (uvicorn :$app_port)…"
    (
        cd "$be"
        exec env PATH="$launch_path" UV_PYTHON="$PY_BIN" UV_CACHE_DIR="$CACHE_DIR/uv" \
            "$UV_BIN" run uvicorn videomaker.main:app \
            --host "$app_host" --port "$app_port" \
            --log-level "${APP_LOG_LEVEL:-info}"
    ) &
    BACKEND_PID=$!

    step "..." "Запускаю frontend (Vite :$FRONTEND_PORT)…"
    (
        cd "$fe"
        exec env PATH="$launch_path" "$PNPM_BIN" dev
    ) &
    FRONTEND_PID=$!

    write_pid_file

    info "backend  → http://$app_host:$app_port/docs (pid $BACKEND_PID)"
    info "frontend → http://localhost:$FRONTEND_PORT (pid $FRONTEND_PID)"

    # Health-poll и открытие браузера.
    wait_health "http://$app_host:$app_port/docs" "backend" 60 || true
    if wait_health "http://localhost:$FRONTEND_PORT" "frontend" 60; then
        zenity_progress_stop
        open_browser "http://localhost:$FRONTEND_PORT"
    fi

    printf '\n%s[Reelibra] работает. Ctrl+C останавливает оба сервиса.%s\n' "$C_BOLD" "$C_RESET"
    wait
}

#─── Регистрация .desktop (используется install.sh) ──────────────────────────

install_desktop_entry() {
    # Резолвим абсолютные пути и прописываем их в .desktop + иконки hicolor.
    local launcher_abs="$REELIBRA_ROOT/reelibraLINUX.sh"
    local tpl="$REELIBRA_ROOT/launchers/linux/reelibra.desktop"
    local apps_dir="$HOME/.local/share/applications"
    local icons_root="$HOME/.local/share/icons/hicolor"
    local src_png="$REELIBRA_ROOT/assets/reelibra.png"
    local src_svg="$REELIBRA_ROOT/assets/reelibra.svg"

    [[ -f "$tpl" ]]          || die "Шаблон reelibra.desktop не найден ($tpl)."
    [[ -f "$launcher_abs" ]] || die "Лаунчер reelibraLINUX.sh не найден ($launcher_abs)."

    mkdir -p "$apps_dir"

    # Иконки: SVG как мастер (scalable) + PNG в нескольких размерах.
    if [[ -f "$src_svg" ]]; then
        mkdir -p "$icons_root/scalable/apps"
        cp -f "$src_svg" "$icons_root/scalable/apps/reelibra.svg"
    fi
    if [[ -f "$src_png" ]]; then
        local sz
        for sz in 48 64 128 256; do
            mkdir -p "$icons_root/${sz}x${sz}/apps"
            # Если нет инструмента ресайза — кладём оригинал (DE отресайзит сам).
            if command -v convert >/dev/null 2>&1; then
                convert "$src_png" -resize "${sz}x${sz}" "$icons_root/${sz}x${sz}/apps/reelibra.png" 2>/dev/null \
                    || cp -f "$src_png" "$icons_root/${sz}x${sz}/apps/reelibra.png"
            else
                cp -f "$src_png" "$icons_root/${sz}x${sz}/apps/reelibra.png"
            fi
        done
    else
        warn "assets/reelibra.png не найден — иконка может не отобразиться в меню."
    fi

    # Генерируем .desktop с абсолютным Exec (self-patch путей).
    local dest="$apps_dir/reelibra.desktop"
    sed -e "s|@EXEC@|$launcher_abs|g" \
        -e "s|@ICON@|reelibra|g" \
        "$tpl" > "$dest"
    chmod +x "$dest" "$launcher_abs" 2>/dev/null || true

    # GNOME/Nautilus: пометить trusted, чтобы не было «Untrusted application».
    if command -v gio >/dev/null 2>&1; then
        gio set "$dest" metadata::trusted true 2>/dev/null || true
    fi

    # Обновить кэши меню/иконок (если инструменты есть).
    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$apps_dir" 2>/dev/null || true
    command -v gtk-update-icon-cache   >/dev/null 2>&1 && gtk-update-icon-cache -f -t "$icons_root" 2>/dev/null || true

    ok "Ярлык установлен: $dest"
    info "Иконка зарегистрирована в $icons_root"
}
