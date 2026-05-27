#!/usr/bin/env bash
# Собирает reelibraMAC.app — лёгкий launcher-бандл с нативной иконкой.
# Внутри он зовёт тот же launcher.sh (не self-contained, лишь нативный вид + иконка).
# Иконка берётся из assets/reelibra.icns (готова, не трогаем).
#
# Запуск (один раз, на машине-сборщике):
#   bash launchers/macos/make-app.sh
# Результат: reelibraMAC.app в корне проекта.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

APP="$ROOT_DIR/reelibraMAC.app"
ICNS="$ROOT_DIR/assets/reelibra.icns"

[[ -f "$ICNS" ]] || { echo "Иконка не найдена: $ICNS"; exit 1; }

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cp "$ICNS" "$APP/Contents/Resources/reelibra.icns"

cat >"$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>            <string>Reelibra</string>
  <key>CFBundleDisplayName</key>     <string>Reelibra</string>
  <key>CFBundleIdentifier</key>      <string>com.reelibra.launcher</string>
  <key>CFBundleVersion</key>         <string>1.0</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundlePackageType</key>     <string>APPL</string>
  <key>CFBundleExecutable</key>      <string>reelibraMAC</string>
  <key>CFBundleIconFile</key>        <string>reelibra.icns</string>
  <key>LSMinimumSystemVersion</key>  <string>13.0</string>
  <key>NSHighResolutionCapable</key> <true/>
</dict>
</plist>
PLIST

# Исполняемый бандла: открывает Terminal с launcher.sh, чтобы был виден прогресс.
cat >"$APP/Contents/MacOS/reelibraMAC" <<'LAUNCH'
#!/usr/bin/env bash
set -euo pipefail
# .app лежит в корне проекта; launcher.sh — в launchers/macos/.
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
LAUNCHER="$APP_DIR/launchers/macos/launcher.sh"
# Запускаем в Terminal, чтобы пользователь видел нумерованный прогресс и логи.
osascript >/dev/null 2>&1 <<OSA
tell application "Terminal"
  activate
  do script "bash " & quoted form of "$LAUNCHER"
end tell
OSA
LAUNCH
chmod +x "$APP/Contents/MacOS/reelibraMAC"

# ad-hoc подпись бандла — на arm64 обязательно, иначе «killed: 9».
codesign --force --deep --sign - "$APP" 2>/dev/null || \
  echo "⚠ codesign не сработал — приложение всё равно откроется через right-click → Open."

# Освежить иконку в Finder.
touch "$APP"
killall Finder 2>/dev/null || true

echo "Готово: $APP"
echo "Первый запуск неподписанного бандла: right-click по reelibraMAC.app → Open → Open."
