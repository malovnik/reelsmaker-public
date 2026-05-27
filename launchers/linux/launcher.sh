#!/usr/bin/env bash
# launcher.sh — основной bootstrap-лаунчер Reelibra для Linux.
# Запускается из reelibraLINUX.sh (корень) или из .desktop (Exec).
#
# Что делает на каждом запуске:
#   1. Гейт платформы (x86_64 + glibc >= 2.35).
#   2. Диагностика + доустановка рантаймов: Python 3.12, uv, Node 20, pnpm, ffmpeg
#      (bundle → системный нужной версии → портативный download).
#   3. .env + структура данных.
#   4. Чистка предыдущей сессии: порты 8000/3000, висяки uvicorn/vite/ffmpeg,
#      зомби, stale .lock/.partial/.tmp (НЕ трогая *.db/-wal/-shm/data-контент).
#   5. uv sync + pnpm install (идемпотентно).
#   6. Запуск backend :8000 + frontend :3000, health-poll, открытие браузера.
#   7. trap cleanup при выходе.

set -euo pipefail

# Корень репозитория = на два уровня выше этого файла (launchers/linux/launcher.sh).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REELIBRA_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
export REELIBRA_ROOT

# shellcheck source=./lib.sh
source "$SCRIPT_DIR/lib.sh"

main() {
    detect_ui
    zenity_progress_start
    trap 'zenity_progress_stop' EXIT

    printf '%s┌─ Reelibra launcher ───────────────────────────────────┐%s\n' "$C_BOLD" "$C_RESET"

    step "1/5" "Проверка платформы"
    check_platform_gate

    step "2/5" "Проверка и установка окружения"
    mkdir -p "$RUNTIME_DIR" "$CACHE_DIR"
    ensure_python
    ensure_uv
    ensure_node
    ensure_pnpm
    ensure_ffmpeg
    ensure_env
    ensure_data_dirs

    step "3/5" "Чистка предыдущей сессии"
    cleanup_previous_session

    step "4/5" "Зависимости"
    sync_backend
    sync_frontend

    # Переустанавливаем trap: теперь нужно гасить сервисы при выходе.
    trap 'zenity_progress_stop; runtime_cleanup' EXIT INT TERM

    step "5/5" "Запуск"
    start_services
}

main "$@"
