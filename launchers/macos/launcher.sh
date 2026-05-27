#!/usr/bin/env bash
# Reelibra — macOS bootstrap launcher (Apple Silicon).
#
# Двойной клик по reelibraMAC.command (или reelibraMAC.app) → этот скрипт:
#   1. Проверяет платформу (Apple Silicon обязательно, иначе честное сообщение).
#   2. Разворачивает локальный runtime в .reelibra-runtime/ БЕЗ Homebrew:
#      uv (офиц. installer) → CPython 3.12 (uv python install) → portable Node 20
#      → static ffmpeg arm64 (videotoolbox). Всё кэшируется, повторный запуск быстрый.
#   3. Идемпотентно ставит зависимости (uv sync + pnpm install).
#   4. Чистит висяки прошлого запуска (graceful TERM→5с→KILL) и мусорные файлы.
#   5. Поднимает backend :8000 + frontend :3000, ждёт health, открывает браузер.
#
# Никаких системных модификаций: всё живёт в каталоге проекта (.reelibra-runtime/)
# и в ~/.local/share/uv (стандартный кэш uv). Система не трогается.

set -euo pipefail

#─── Пути ──────────────────────────────────────────────────────────────────
# Скрипт лежит в launchers/macos/, корень проекта — на два уровня выше.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$ROOT_DIR"

RUNTIME_DIR="$ROOT_DIR/.reelibra-runtime"
BIN_DIR="$RUNTIME_DIR/bin"
NODE_DIR="$RUNTIME_DIR/node"
LOG_DIR="$ROOT_DIR/data/logs"
RUN_DIR="$ROOT_DIR/data/.run"
PID_FILE="$RUN_DIR/launcher.pid"
BOOT_LOG="$LOG_DIR/bootstrap.log"

APP_HOST="${APP_HOST:-127.0.0.1}"
APP_PORT="${APP_PORT:-8000}"
FRONTEND_PORT="3000"

# Закреплённые версии портативных инструментов.
NODE_VERSION="20.18.1"
NODE_PKG="node-v${NODE_VERSION}-darwin-arm64"
NODE_URL="https://nodejs.org/dist/v${NODE_VERSION}/${NODE_PKG}.tar.gz"
# Статический ffmpeg arm64 с VideoToolbox (evermeet — общепринятый источник для macOS).
FFMPEG_URL="https://www.osxexperts.net/ffmpeg711arm.zip"
FFMPEG_FALLBACK_URL="https://evermeet.cx/ffmpeg/getrelease/ffmpeg/zip"

mkdir -p "$BIN_DIR" "$NODE_DIR" "$LOG_DIR" "$RUN_DIR"

#─── Вывод ─────────────────────────────────────────────────────────────────
BOLD=$'\033[1m'; DIM=$'\033[2m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'
RED=$'\033[31m'; GOLD=$'\033[38;5;179m'; RESET=$'\033[0m'

log()  { printf '%s\n' "$*" | tee -a "$BOOT_LOG"; }
step() { printf '  %-34s' "$*"; printf '  %-34s\n' "$*" >>"$BOOT_LOG"; }
ok()   { printf '%sОК%s\n' "$GREEN" "$RESET"; printf 'OK\n' >>"$BOOT_LOG"; }
skip() { printf '%s%s%s\n' "$DIM" "${1:-—}" "$RESET"; printf '%s\n' "${1:-skip}" >>"$BOOT_LOG"; }
warn() { printf '%s⚠ %s%s\n' "$YELLOW" "$*" "$RESET" | tee -a "$BOOT_LOG"; }
phase(){ printf '\n%s[%s] %s%s\n' "$GOLD" "$1" "$2" "$RESET"; printf '\n[%s] %s\n' "$1" "$2" >>"$BOOT_LOG"; }

# Понятная русская ошибка + выход.
die() {
    printf '\n%s✗ %s%s\n' "$RED" "$1" "$RESET"
    printf '\n✗ %s\n' "$1" >>"$BOOT_LOG"
    [[ -n "${2:-}" ]] && printf '  %s\n' "$2"
    printf '\n  Подробный лог: %s\n' "$BOOT_LOG"
    printf '\n  Окно можно закрыть.\n'
    # Не схлопываем Terminal мгновенно при дабл-клике — даём прочитать.
    [[ -t 0 ]] && { printf '\n  Нажмите Enter для выхода…'; read -r _ || true; }
    exit 1
}

: >"$BOOT_LOG"
log "${BOLD}${GOLD}Reelibra — запуск${RESET}"
log "${DIM}$(date '+%Y-%m-%d %H:%M:%S')  ·  $ROOT_DIR${RESET}"

#─── PATH локального runtime ─────────────────────────────────────────────────
export PATH="$BIN_DIR:$NODE_DIR/bin:$PATH"
# uv ставит свой бинарь сюда по умолчанию.
export PATH="$HOME/.local/bin:$PATH"
# Изолируем pnpm/corepack store внутри runtime, не засоряем системный ~/.
export COREPACK_HOME="$RUNTIME_DIR/corepack"
export PNPM_HOME="$RUNTIME_DIR/pnpm"
export PATH="$PNPM_HOME:$PATH"

# ───────────────────────────────────────────────────────────────────────────
# [1/5] Платформа
# ───────────────────────────────────────────────────────────────────────────
phase "1/5" "Проверка платформы"

ARCH="$(uname -m)"
OS_VER="$(sw_vers -productVersion 2>/dev/null || echo '0')"
OS_MAJOR="${OS_VER%%.*}"

step "Архитектура (${ARCH})…"
if [[ "$ARCH" == "x86_64" ]]; then
    # Не блокируем целиком — но честно предупреждаем: MLX-STT не работает.
    printf '%sIntel%s\n' "$YELLOW" "$RESET"
    warn "Это Intel-Mac. Локальная транскрибация (MLX) НЕ работает на Intel."
    warn "Reelibra рассчитан на Apple Silicon (M1+). Запуск продолжится, но:"
    printf '    • локальный STT (mlx-whisper/stable-ts) не установится/не заведётся;\n'
    printf '    • нужен облачный STT — впишите DEEPGRAM_API_KEY в .env (платно);\n'
    printf '    • видеоэнкод уйдёт на CPU (libx264), медленнее.\n'
    printf '\n  Продолжить на свой риск? [y/N] '
    if [[ -t 0 ]]; then read -r ans || true; else ans="n"; fi
    [[ "$ans" =~ ^[Yy]$ ]] || die "Запуск отменён — нужен Mac с Apple Silicon (M1 и новее)."
else
    ok
fi

step "Версия macOS (${OS_VER})…"
if [[ "$OS_MAJOR" =~ ^[0-9]+$ ]] && (( OS_MAJOR < 13 )); then
    warn "macOS ${OS_VER}: рекомендуется 14+. Возможны проблемы с MLX/Metal."
else
    ok
fi

# ───────────────────────────────────────────────────────────────────────────
# [2/5] Runtime (uv / Python 3.12 / Node 20 / ffmpeg)
# ───────────────────────────────────────────────────────────────────────────
phase "2/5" "Проверка и установка инструментов"

# Снимаем quarantine со скриптов лаунчера (свои файлы — безопасно), чтобы
# дочерние .command/.sh не спотыкались о Gatekeeper при первом запуске.
xattr -dr com.apple.quarantine "$SCRIPT_DIR" "$ROOT_DIR/reelibraMAC.command" 2>/dev/null || true

# --- uv ---
step "uv…"
if command -v uv >/dev/null 2>&1; then
    ok
else
    printf '%sставлю…%s\n' "$DIM" "$RESET"
    if ! curl -LsSf https://astral.sh/uv/install.sh | sh >>"$BOOT_LOG" 2>&1; then
        die "Не удалось установить uv." "Проверьте интернет и повторите запуск."
    fi
    export PATH="$HOME/.local/bin:$PATH"
    command -v uv >/dev/null 2>&1 || die "uv установился, но не виден в PATH." "Перезапустите лаунчер."
    log "  uv установлен → $(command -v uv)"
fi

# --- CPython 3.12 (через uv, в кэш uv, систему не трогаем) ---
step "Python 3.12…"
if uv python find 3.12 >/dev/null 2>&1; then
    ok
else
    printf '%sскачиваю интерпретатор (1-2 мин)…%s\n' "$DIM" "$RESET"
    uv python install 3.12 >>"$BOOT_LOG" 2>&1 \
        || die "Не удалось установить Python 3.12 через uv." "Проверьте интернет."
    uv python find 3.12 >/dev/null 2>&1 || die "Python 3.12 не найден после установки."
    log "  Python 3.12 готов"
fi

# --- Portable Node 20 ---
step "Node ${NODE_VERSION%%.*}…"
need_node=1
if [[ -x "$NODE_DIR/bin/node" ]]; then
    cur="$("$NODE_DIR/bin/node" -v 2>/dev/null | sed 's/^v//;s/\..*//')"
    [[ "$cur" =~ ^[0-9]+$ ]] && (( cur >= 20 )) && need_node=0
fi
if (( need_node == 0 )); then
    ok
else
    printf '%sскачиваю portable Node…%s\n' "$DIM" "$RESET"
    tmp_tgz="$RUNTIME_DIR/node.tar.gz.partial"
    if ! curl -fLs "$NODE_URL" -o "$tmp_tgz" >>"$BOOT_LOG" 2>&1; then
        rm -f "$tmp_tgz"
        die "Не удалось скачать Node ${NODE_VERSION}." "Проверьте интернет."
    fi
    rm -rf "$NODE_DIR"; mkdir -p "$NODE_DIR"
    tar -xzf "$tmp_tgz" -C "$NODE_DIR" --strip-components=1 >>"$BOOT_LOG" 2>&1 \
        || { rm -f "$tmp_tgz"; die "Архив Node повреждён." "Удалите .reelibra-runtime/node и повторите."; }
    rm -f "$tmp_tgz"
    # ad-hoc подпись нативного бинаря — на arm64 неподписанный код может убиваться.
    codesign --force --sign - "$NODE_DIR/bin/node" >>"$BOOT_LOG" 2>&1 || true
    "$NODE_DIR/bin/node" -v >/dev/null 2>&1 || die "Node не запускается после установки."
    log "  Node $("$NODE_DIR/bin/node" -v) готов"
fi

# --- pnpm через corepack (идёт в комплекте с Node) ---
step "pnpm…"
if command -v pnpm >/dev/null 2>&1; then
    ok
else
    printf '%sактивирую через corepack…%s\n' "$DIM" "$RESET"
    mkdir -p "$PNPM_HOME"
    if "$NODE_DIR/bin/corepack" enable pnpm --install-directory "$PNPM_HOME" >>"$BOOT_LOG" 2>&1 \
       || "$NODE_DIR/bin/corepack" enable --install-directory "$PNPM_HOME" >>"$BOOT_LOG" 2>&1; then
        "$NODE_DIR/bin/corepack" prepare pnpm@latest --activate >>"$BOOT_LOG" 2>&1 || true
    fi
    command -v pnpm >/dev/null 2>&1 || die "Не удалось активировать pnpm через corepack."
    log "  pnpm готов → $(command -v pnpm)"
fi

# --- Static ffmpeg arm64 (videotoolbox) ---
step "ffmpeg…"
if command -v ffmpeg >/dev/null 2>&1 && [[ ! -x "$BIN_DIR/ffmpeg" ]]; then
    # Системный ffmpeg уже есть в PATH — используем его, не качаем.
    ok
elif [[ -x "$BIN_DIR/ffmpeg" ]]; then
    ok
else
    printf '%sскачиваю static ffmpeg arm64…%s\n' "$DIM" "$RESET"
    tmp_zip="$RUNTIME_DIR/ffmpeg.zip.partial"
    got=0
    for url in "$FFMPEG_URL" "$FFMPEG_FALLBACK_URL"; do
        if curl -fLs "$url" -o "$tmp_zip" >>"$BOOT_LOG" 2>&1 && [[ -s "$tmp_zip" ]]; then
            got=1; break
        fi
    done
    (( got == 1 )) || { rm -f "$tmp_zip"; die "Не удалось скачать ffmpeg." "Проверьте интернет, либо установите ffmpeg вручную."; }
    unzip -o -j "$tmp_zip" -d "$BIN_DIR" >>"$BOOT_LOG" 2>&1 \
        || { rm -f "$tmp_zip"; die "Архив ffmpeg повреждён."; }
    rm -f "$tmp_zip"
    chmod +x "$BIN_DIR/ffmpeg" 2>/dev/null || true
    xattr -dr com.apple.quarantine "$BIN_DIR/ffmpeg" 2>/dev/null || true
    codesign --force --sign - "$BIN_DIR/ffmpeg" >>"$BOOT_LOG" 2>&1 || true
    "$BIN_DIR/ffmpeg" -version >/dev/null 2>&1 || die "ffmpeg не запускается после установки."
    log "  ffmpeg готов → $BIN_DIR/ffmpeg"
fi

# ───────────────────────────────────────────────────────────────────────────
# [3/5] Зависимости проекта
# ───────────────────────────────────────────────────────────────────────────
phase "3/5" "Зависимости проекта"

# .env
step "Файл .env…"
if [[ -f .env ]]; then
    ok
else
    cp .env.example .env
    printf '%sсоздан из примера%s\n' "$YELLOW" "$RESET"
fi
# Проверка ключа Gemini — предупреждение, не блокер.
# || true: grep первым в pipe под set -o pipefail возвращает 1, если строки нет
# (пользователь удалил/закомментировал GEMINI_API_KEY) → иначе set -e убил бы лаунчер.
gem="$(grep -E '^GEMINI_API_KEY=' .env 2>/dev/null | head -1 | cut -d= -f2- | tr -d ' "'"'"'' || true)"
[[ -z "$gem" ]] && warn "GEMINI_API_KEY пуст — нарезка не заработает. Впишите ключ в Настройках после запуска."

# Каталоги данных
step "Каталоги data/…"
mkdir -p data/{uploads,artifacts,logs,proxies,thumbnails,transcripts,face_cache,vision_cache,models,post_production_assets} 2>/dev/null || true
ok

# Backend deps
step "Backend (uv sync)…"
printf '%s…%s\n' "$DIM" "$RESET"
if ! ( cd "$ROOT_DIR/apps/backend" && uv sync 2>&1 | tee -a "$BOOT_LOG" ); then
    if [[ "$ARCH" == "x86_64" ]]; then
        die "uv sync упал — на Intel-Mac MLX-зависимости не ставятся." "Это ожидаемо: Reelibra требует Apple Silicon."
    fi
    die "Не удалось установить зависимости backend." "Проверьте интернет и лог."
fi
log "  backend deps ОК"

# Frontend deps
step "Frontend (pnpm install)…"
printf '%s…%s\n' "$DIM" "$RESET"
# CI=1 + флаг подавляют интерактивный prompt pnpm («modules dir will be removed,
# Proceed? Y/n») — при дабл-клике .command stdin не должен ничего спрашивать.
( cd "$ROOT_DIR/apps/frontend" && CI=1 pnpm install --config.confirm-modules-purge=false 2>&1 | tee -a "$BOOT_LOG" ) \
    || die "Не удалось установить зависимости frontend." "Проверьте интернет и лог."
log "  frontend deps ОК"

# ───────────────────────────────────────────────────────────────────────────
# [4/5] Чистка прошлого запуска
# ───────────────────────────────────────────────────────────────────────────
phase "4/5" "Проверка и чистка прошлого запуска"

# graceful TERM → ждать до 5с → KILL.
kill_graceful() {
    local label="$1"; shift
    local pids=("$@")
    [[ ${#pids[@]} -eq 0 ]] && return 0
    printf '  Останавливаю %s (%s)… ' "$label" "${pids[*]}"
    kill -TERM "${pids[@]}" 2>/dev/null || true
    local waited=0
    while (( waited < 5 )); do
        local alive=0
        for p in "${pids[@]}"; do kill -0 "$p" 2>/dev/null && alive=1; done
        (( alive == 0 )) && break
        sleep 1; waited=$((waited + 1))
    done
    for p in "${pids[@]}"; do kill -0 "$p" 2>/dev/null && kill -9 "$p" 2>/dev/null || true; done
    printf '%sОК%s\n' "$GREEN" "$RESET"
}

# Сироты по паттернам команд (ffmpeg/esbuild порт не держат).
collect_pids() {
    pgrep -f "$1" 2>/dev/null | tr '\n' ' ' || true
}

# Якорим vite/esbuild/pnpm/ffmpeg на путь проекта, чтобы НЕ убить чужие Vite-серверы
# или ffmpeg-рендеры пользователя в других приложениях. uvicorn-паттерн уникален сам.
RE_ROOT="${ROOT_DIR//\//\\/}"
found_stale=0
declare -a stale_patterns=(
    "uvicorn videomaker.main"
    "${RE_ROOT}/apps/frontend.*vite"
    "${RE_ROOT}/apps/frontend.*esbuild"
    "pnpm.*dev.*${RE_ROOT}"
    "ffmpeg.*${RE_ROOT}/data/artifacts"
    "ffmpeg.*${RE_ROOT}/data/proxies"
)
for pat in "${stale_patterns[@]}"; do
    read -r -a pids <<<"$(collect_pids "$pat")"
    if (( ${#pids[@]} > 0 )) && [[ -n "${pids[0]:-}" ]]; then
        found_stale=1
        kill_graceful "$pat" "${pids[@]}"
    fi
done

# Освобождение портов 8000/3000 (LISTEN-сокеты).
free_port() {
    local port="$1"
    local pids
    pids="$(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null | tr '\n' ' ' || true)"
    printf '  Порт %s… ' "$port"
    if [[ -n "${pids// /}" ]]; then
        found_stale=1
        read -r -a parr <<<"$pids"
        kill -TERM "${parr[@]}" 2>/dev/null || true
        local waited=0
        while (( waited < 5 )) && lsof -nP -iTCP:"$port" -sTCP:LISTEN -t >/dev/null 2>&1; do
            sleep 1; waited=$((waited + 1))
        done
        pids="$(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null | tr '\n' ' ' || true)"
        if [[ -n "${pids// /}" ]]; then
            read -r -a parr <<<"$pids"
            kill -9 "${parr[@]}" 2>/dev/null || true
        fi
        printf '%sосвобождён%s\n' "$YELLOW" "$RESET"
    else
        printf '%sсвободен%s\n' "$GREEN" "$RESET"
    fi
}
free_port "$APP_PORT"
free_port "$FRONTEND_PORT"

# Мусорные файлы — НЕ трогаем *.db/-wal/-shm/uploads/artifacts.
step "Временные файлы (.partial/.tmp/.lock)…"
removed=0
while IFS= read -r -d '' f; do rm -f "$f" && removed=$((removed + 1)); done < <(
    find "$ROOT_DIR/data" \( -name '*.partial' -o -name '*.tmp' \) -type f -print0 2>/dev/null
)
# orphan-locks: только старше 1 мин (BSD find не принимает дробные -mmin;
# свежий лок параллельного запуска не успеет состариться), и никогда не *.db.
while IFS= read -r -d '' f; do
    case "$f" in *.db|*.db-wal|*.db-shm) continue;; esac
    rm -f "$f" && removed=$((removed + 1))
done < <(find "$ROOT_DIR/data" -name '*.lock' -type f -mmin +1 -print0 2>/dev/null)
# stale bytecode
find "$ROOT_DIR/apps/backend/src" -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true
printf '%sубрано %d%s\n' "$DIM" "$removed" "$RESET"

if (( found_stale == 1 )); then
    log "  ${DIM}Данные и БД не тронуты. Прерванные задачи backend пометит как ошибку на старте.${RESET}"
fi

# ───────────────────────────────────────────────────────────────────────────
# [5/5] Запуск
# ───────────────────────────────────────────────────────────────────────────
phase "5/5" "Запуск"

BACKEND_PID=""
FRONTEND_PID=""
OPENED=0

cleanup() {
    printf '\n%s[Reelibra] останавливаю процессы…%s\n' "$DIM" "$RESET"
    [[ -n "$BACKEND_PID" ]]  && kill -TERM "$BACKEND_PID"  2>/dev/null || true
    [[ -n "$FRONTEND_PID" ]] && kill -TERM "$FRONTEND_PID" 2>/dev/null || true
    sleep 2
    # uvicorn videomaker.main — глобально уникальный модуль (это наш backend),
    # поэтому путь не нужен. Голый "uv run uvicorn" НЕ якорим и НЕ убиваем: он
    # родовой и прибил бы чужой проект пользователя с таким же раннером (fratricide).
    pkill -9 -f "uvicorn videomaker.main"            2>/dev/null || true
    pkill -9 -f "${ROOT_DIR}/apps/frontend.*vite"     2>/dev/null || true
    pkill -9 -f "${ROOT_DIR}/apps/frontend.*esbuild"  2>/dev/null || true
    rm -f "$PID_FILE" 2>/dev/null || true
    wait 2>/dev/null || true
    printf '%s[Reelibra] выход%s\n' "$DIM" "$RESET"
}
trap cleanup EXIT INT TERM

echo "$$" >"$PID_FILE"

# Backend: prod-режим без --reload. uv сам подберёт Python 3.12 из .venv.
( cd "$ROOT_DIR/apps/backend" && exec uv run uvicorn videomaker.main:app \
    --host "$APP_HOST" --port "$APP_PORT" \
    --log-level "${APP_LOG_LEVEL:-info}" ) >>"$LOG_DIR/backend.log" 2>&1 &
BACKEND_PID=$!

( cd "$ROOT_DIR/apps/frontend" && exec pnpm dev ) >>"$LOG_DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!

printf '  Backend  → http://%s:%s/docs (pid %s)\n' "$APP_HOST" "$APP_PORT" "$BACKEND_PID"
printf '  Frontend → http://localhost:%s (pid %s)\n' "$FRONTEND_PORT" "$FRONTEND_PID"
printf '  %sздоровье сервисов…%s ' "$DIM" "$RESET"

# Health-poll: ждём оба порта до 60с.
healthy=0
for _ in $(seq 1 60); do
    kill -0 "$BACKEND_PID" 2>/dev/null  || die "Backend упал на старте." "Лог: $LOG_DIR/backend.log"
    kill -0 "$FRONTEND_PID" 2>/dev/null || die "Frontend упал на старте." "Лог: $LOG_DIR/frontend.log"
    # Фронт проверяем честным HTTP-GET, а не по LISTEN-сокету: Vite (strictPort)
    # открывает сокет ДО окончания компиляции бандла, и браузер открылся бы на
    # висящей странице. curl-GET отвечает только когда дев-сервер реально готов.
    if curl -fsS "http://$APP_HOST:$APP_PORT/docs" >/dev/null 2>&1 \
       && curl -fsS "http://localhost:$FRONTEND_PORT" >/dev/null 2>&1; then
        healthy=1; break
    fi
    sleep 1
done

if (( healthy == 1 )); then
    printf '%sОК%s\n' "$GREEN" "$RESET"
    if (( OPENED == 0 )); then open "http://localhost:$FRONTEND_PORT"; OPENED=1; fi
    printf '\n%s%sReelibra работает.%s  Браузер открыт на http://localhost:%s\n' \
        "$BOLD" "$GREEN" "$RESET" "$FRONTEND_PORT"
    printf '  %sCtrl+C или закрытие окна останавливает оба сервиса.%s\n' "$DIM" "$RESET"
else
    warn "Сервисы поднимаются дольше обычного. Откройте http://localhost:$FRONTEND_PORT вручную."
    open "http://localhost:$FRONTEND_PORT" || true
fi

wait
