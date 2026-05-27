# Валидация macOS-лаунчера — launcher-mac.md

**Вердикт: PASS с одним функциональным дефектом (non-destructive).**
Валидатор реально на Apple Silicon: `uname -m = arm64`, macOS `26.2`.

Файлы: `reelibraMAC.command`, `launchers/macos/launcher.sh`, `launchers/macos/make-app.sh`, `launchers/macos/README.md`.
(Примечание: `make-app.sh` и `README.md` лежат в `launchers/macos/`, не в корне — в ТЗ путь был указан как корневой.)

---

## Что РЕАЛЬНО протестировано на этом Mac

| # | Проверка | Результат |
|---|----------|-----------|
| 1 | `bash -n` всех 3 скриптов + извлечённый heredoc-исполняемый `.app` | Чисто, 0 синтаксических ошибок |
| 2 | Платформенные примитивы `uname -m`, `sw_vers` | arm64 / 26.2, ветка Apple Silicon отрабатывает (`ok`) |
| 3 | `pgrep -f` по всем 7 stale-паттернам (DRY, без kill) | Заякорены на путь проекта. Поймали ТОЛЬКО реальные vite/esbuild ЭТОГО проекта (PID 73392/85203/73398/85209 — подтверждено `ps`, все в `…/reelsmaker-public/apps/frontend/…`). Чужие процессы не матчатся. |
| 4 | `lsof -nP -iTCP:8000/3000 -sTCP:LISTEN -t` (DRY) | Оба порта free, синтаксис корректен |
| 5 | Логика чистки junk в изолированном temp-каталоге | `.partial`/`.tmp` удалены; `*.db`/`*.db-wal`/`*.db-shm` **выжили** (case-guard работает) |
| 6 | ad-hoc `codesign --force --sign -` на arm64 (фикс «killed:9») | Работает: `Signature=adhoc`. Это и есть защита Node/ffmpeg от убийства ядром |
| 7 | Наличие примитивов: xattr, codesign, osascript, lsof, curl, open, unzip, tar, seq | Все present |
| 8 | URL-достижимость (HEAD, без скачивания гигабайтов) | Node 200, osxexperts ffmpeg 200, evermeet fallback 200, astral uv 200 |
| 9 | `assets/reelibra.icns` | Валидная Mac-иконка (`ic12`, 115 KB) |
| 10 | Структура: `apps/backend`, `apps/frontend`, `.env.example`, `pyproject.toml` | Все на месте |

Полный bootstrap НЕ запускался (гигабайты) — функции проверены изолированно, как требовалось.

---

## БАГ (1, функциональный, не разрушительный)

**Orphan-`.lock` cleanup никогда не срабатывает.** launcher.sh:343:
```bash
find "$ROOT_DIR/data" -name '*.lock' -type f -mmin +0.1 -print0 2>/dev/null
```
BSD `find` (и `bfs` на этом Mac) **отвергают дробное** `-mmin +0.1`:
`bfs: error: 0.1 is not a valid integer`. Команда падает с exit 1, ошибка глотается `2>/dev/null`,
цикл получает пустой ввод → orphan-`.lock` **не удаляются никогда**. Документация (README:63,
«Удаляет … orphan-.lock») обещает то, чего нет.

- **Опасность: нулевая** (fail-safe — лишний lock остаётся, данные целы).
- **Фикс:** `-mmin +0.1` → `-mmin +1` (целое; «старше 1 мин», безопасно для свежего лока),
  либо `-newermt '-6 seconds'` если нужна именно 6-секундная гранулярность. `.partial`/`.tmp` ветка
  работает корректно (там нет `-mmin`).

---

## Проверка по пунктам ТЗ

- **Bootstrap-логика (2).** URL правдоподобны и живы (все 200). uv → офиц. installer, Python 3.12 через `uv python install` (кэш uv, систему не трогает), portable Node tar.gz arm64, static ffmpeg arm64 (osxexperts + evermeet fallback). ad-hoc `codesign` есть и для Node (launcher.sh:170) и для ffmpeg (212) — фикс «killed:9» подтверждён рабочим на этом arm64.
- **Чистка SIGTERM→SIGKILL (4).** `kill_graceful`: TERM → poll ≤5с → `kill -9`. `cleanup` (trap): TERM → sleep 2 → `pkill -9`. `*.db/-wal/-shm` защищены case-guard'ом (проверено реально). PID-файл `data/.run/launcher.pid` пишется (376) и снимается в cleanup (370).
- **Intel-детект (5).** `x86_64` → честное предупреждение про неработающий MLX-STT, требование Deepgram-ключа, CPU-энкод; интерактивный `[y/N]`, в неинтерактиве дефолт `n` → отказ. `uv sync`-фейл на Intel тоже даёт честное «требуется Apple Silicon». Корректно.
- **Gatekeeper (6).** `xattr -dr com.apple.quarantine` снимается со своих скриптов (.command:11, launcher.sh:121) и со скачанного ffmpeg (211). right-click→Open задокументирован в README. make-app: ad-hoc `codesign --force --deep --sign -`, иконка `.icns` копируется, Info.plist валиден, `LSMinimumSystemVersion 13.0`.
- **NO MOCKS/TODO (7).** grep по TODO/FIXME/XXX/MOCK/HACK/заглушк/stub — **0 совпадений.** Honesty STT соблюдён: Intel честно предупреждается, ничего не маскируется.
- **Health-poll + open + trap (8).** Poll ≤60с: проверяет жив ли backend/frontend PID (`kill -0`, при падении — `die` с указанием лога), `curl -fsS …/docs` + `lsof` LISTEN :3000. `open` браузера один раз (`OPENED` guard). `trap cleanup EXIT INT TERM`. Корректно. Мелочь: `OPENED` всегда 0 в момент проверки (флаг бессмысленный, но не баг).

## Наблюдения (не баги)

- Stale-паттерны без концевого якоря `$`: гипотетический sibling-каталог с тем же префиксом (`reelsmaker-publicX`) попал бы под матч. Таких siblings на диске нет; риск теоретический.
- `RE_ROOT` экранирует только `/`, не `.`. В пути проекта точек нет → безвредно.

---

## Висяки

**Не осталось.** Я создавал только temp-файлы (через `mktemp`, удалены) и подписывал копию `/bin/echo` в `/tmp` (удалена). Фоновых процессов не поднимал. Реальные dev-серверы проекта (PID 73392/85203/73398/85209), которые поймали pgrep-паттерны, **НЕ тронуты** — подтверждено `ps` после всех тестов: все 4 живы. Реальные данные/БД не удалялись (чистка тестировалась в изолированном `mktemp`-каталоге).
