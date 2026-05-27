#!/usr/bin/env bash
# videomaker — запускает backend (FastAPI) и frontend (Vite dev server) параллельно.
#
# Перед стартом выполняется жёсткий preflight cleanup:
#   1. SIGKILL всех residual uvicorn/videomaker процессов и stale Vite dev-серверов.
#   2. Освобождение портов 8000 (backend) и 3000 (frontend) через lsof.
#   3. Удаление __pycache__ в backend/src — гарантирует что новый процесс
#      перекомпилирует bytecode из свежего .py, без stale .pyc из памяти.
#
# История: раньше фронтенд был на Next.js 16 + Turbopack — он стабильно
# съедал >12GB heap и падал при долгих сессиях. Перевели на Vite, теперь
# dev-сервер живёт на ~150-300MB и держится часами без перезагрузок.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [[ ! -f .env ]]; then
    echo "[videomaker] .env not found — копирую из .env.example"
    cp .env.example .env
    echo "[videomaker] отредактируй .env и добавь API-ключи (GEMINI_API_KEY минимум)"
fi

mkdir -p data/uploads data/artifacts data/logs

command -v uv >/dev/null || { echo "uv не установлен. Установи: curl -LsSf https://astral.sh/uv/install.sh | sh"; exit 1; }
command -v pnpm >/dev/null || { echo "pnpm не установлен. Установи: npm install -g pnpm"; exit 1; }
command -v ffmpeg >/dev/null || { echo "ffmpeg не установлен. Установи: brew install ffmpeg"; exit 1; }

#─── Установка/проверка зависимостей ───────────────────────────────────────
# Идемпотентно: если зависимости уже стоят и lock не изменился — обе
# команды отрабатывают за <1с. После git pull / уборки .venv поднимется
# окружение с нуля.

echo "[videomaker] backend deps (uv sync)…"
(cd "$ROOT_DIR/apps/backend" && uv sync --quiet)

echo "[videomaker] frontend deps (pnpm install)…"
(cd "$ROOT_DIR/apps/frontend" && pnpm install --silent)

#─── Preflight cleanup ─────────────────────────────────────────────────────
# Убивает всё что могло остаться от прошлого запуска. Идемпотентно.

preflight_kill() {
    local pattern="$1"
    local label="$2"
    local pids
    pids="$(pgrep -f "$pattern" 2>/dev/null | tr '\n' ' ' || true)"
    if [[ -n "${pids// /}" ]]; then
        echo "[videomaker] killing stale $label: $pids"
        # shellcheck disable=SC2086
        kill -9 $pids 2>/dev/null || true
    fi
}

preflight_free_port() {
    local port="$1"
    local pids
    pids="$(lsof -nP -iTCP:"$port" -sTCP:LISTEN -Fp 2>/dev/null | sed -n 's/^p//p' | tr '\n' ' ' || true)"
    if [[ -n "${pids// /}" ]]; then
        echo "[videomaker] freeing port $port (pids: $pids)"
        # shellcheck disable=SC2086
        kill -9 $pids 2>/dev/null || true
    fi
}

echo "[videomaker] preflight cleanup…"
preflight_kill "uvicorn videomaker.main" "uvicorn workers"
preflight_kill "uv run uvicorn" "uv-run wrappers"
preflight_kill "node .*vite" "vite dev workers"
preflight_kill "esbuild --service" "esbuild children"
preflight_kill "pnpm.*dev" "pnpm dev wrappers"
preflight_kill "ffmpeg.*data/artifacts" "residual ffmpeg renders"

# Подождать cleanup успеть освободить сокеты и file locks.
sleep 2

preflight_free_port 8000
preflight_free_port 3000

# Очистка bytecode — обязательно для dev, чтобы уж точно подхватились
# любые правки .py файлов, включая тонкие изменения констант которые
# `--reload` watchdog иногда пропускает при batch-commit/pull.
find "$ROOT_DIR/apps/backend/src" -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true
echo "[videomaker] pycache cleared"

#─── Startup ───────────────────────────────────────────────────────────────

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
    echo ""
    echo "[videomaker] останавливаю процессы…"
    [[ -n "$BACKEND_PID" ]] && kill -TERM "$BACKEND_PID" 2>/dev/null || true
    [[ -n "$FRONTEND_PID" ]] && kill -TERM "$FRONTEND_PID" 2>/dev/null || true
    sleep 2
    pkill -9 -f "uvicorn videomaker.main" 2>/dev/null || true
    pkill -9 -f "uv run uvicorn" 2>/dev/null || true
    pkill -9 -f "node .*vite" 2>/dev/null || true
    pkill -9 -f "esbuild --service" 2>/dev/null || true
    pkill -9 -f "pnpm.*dev" 2>/dev/null || true
    wait 2>/dev/null || true
    echo "[videomaker] выход"
}
trap cleanup EXIT INT TERM

(
    cd "$ROOT_DIR/apps/backend"
    exec uv run uvicorn videomaker.main:app \
        --host "${APP_HOST:-127.0.0.1}" \
        --port "${APP_PORT:-8000}" \
        --reload \
        --reload-dir src \
        --reload-exclude "**/__pycache__/*" \
        --reload-exclude "**/*.pyc" \
        --reload-exclude "**/.pytest_cache/*" \
        --log-level "${APP_LOG_LEVEL:-info}"
) &
BACKEND_PID=$!

(
    cd "$ROOT_DIR/apps/frontend"
    exec pnpm dev
) &
FRONTEND_PID=$!

echo "[videomaker] backend  → http://${APP_HOST:-127.0.0.1}:${APP_PORT:-8000}/docs (pid $BACKEND_PID)"
echo "[videomaker] frontend → http://localhost:3000 (pid $FRONTEND_PID)"
echo "[videomaker] Ctrl+C останавливает оба"

wait
