#!/usr/bin/env bash
# Reelibra — точка входа для macOS (двойной клик).
# Делегирует всю логику в launchers/macos/launcher.sh.
# Голый .command открывает Terminal с логом прогресса — это и есть UI запуска.

set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Свои скрипты безопасно освободить от quarantine, чтобы Gatekeeper не мешал
# дочерним вызовам при первом запуске.
xattr -dr com.apple.quarantine "$HERE/launchers/macos" "$HERE/reelibraMAC.command" 2>/dev/null || true

exec bash "$HERE/launchers/macos/launcher.sh" "$@"
