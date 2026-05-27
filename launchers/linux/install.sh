#!/usr/bin/env bash
# install.sh — разовая регистрация Reelibra в меню приложений Linux.
#
# Зачем: двойной клик по .sh в файл-менеджерах (Nautilus/Dolphin/Nemo) по
# умолчанию открывает скрипт в редакторе, а не исполняет. Нативный способ
# «иконка → клик → запуск» — это .desktop в ~/.local/share/applications.
#
# Запусти ОДИН раз из терминала:
#     bash launchers/linux/install.sh
# После этого Reelibra появится в меню приложений и запускается «честным» кликом.
#
# Установка не требует root, ничего не трогает в системных каталогах.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REELIBRA_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
export REELIBRA_ROOT

# shellcheck source=./lib.sh
source "$SCRIPT_DIR/lib.sh"

UI_MODE="tty"

printf '%s┌─ Reelibra — установка ярлыка ─────────────────────────┐%s\n' "$C_BOLD" "$C_RESET"

# Сделать корневой лаунчер исполняемым (на случай если права слетели при распаковке).
chmod +x "$REELIBRA_ROOT/reelibraLINUX.sh" 2>/dev/null || true
chmod +x "$SCRIPT_DIR/launcher.sh" 2>/dev/null || true

step "1/1" "Регистрирую .desktop и иконку"
install_desktop_entry

printf '\n%s✓ Готово.%s Reelibra теперь в меню приложений (раздел «Аудио и видео»).\n' "$C_GREEN$C_BOLD" "$C_RESET"
printf '  Запуск: иконка в меню ИЛИ %s./reelibraLINUX.sh%s из терминала.\n' "$C_BOLD" "$C_RESET"
printf '  Первый запуск скачает портативные Python/Node/ffmpeg (нужен интернет).\n'
