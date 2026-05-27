# Final Launcher Gatekeeper — Overall Revalidation

Дата: 2026-05-27 · Роль: Final Launcher Gatekeeper (3 ОС)
Критерий вердикта: «дебил скачал репо → 2 клика → работает».

## Вердикт по ОС

| ОС | Вердикт | Условие «2 клика» |
|----|---------|-------------------|
| **macOS (Apple Silicon)** | **GO** | дабл-клик `reelibraMAC.command` (либо собрать `.app` через make-app.sh) |
| **Windows 10/11 x64** | **GO** | дабл-клик `reelibraWIN.cmd` (опц. ярлык с иконкой через create-shortcut.ps1) |
| **Linux x86_64 (glibc≥2.35)** | **GO** | `bash launchers/linux/install.sh` (раз) → клик по иконке в меню; либо `./reelibraLINUX.sh` |

Остаточных блокеров нет. Все три — GO.

## Проверки (8/8 пройдено)

1. **Точки входа существуют, исполнимы, ссылаются правильно** — OK.
   - `reelibraMAC.command` (0755) → `launchers/macos/launcher.sh`.
   - `reelibraLINUX.sh` (0755) → `launchers/linux/launcher.sh` → `lib.sh`.
   - `reelibraWIN.cmd` (0644, +x на Windows не нужен) → `launchers/windows/launcher.ps1` через `-ExecutionPolicy Bypass`.
   - Все вспомогательные .sh исполнимы (0755).

2. **Иконки на месте и валидны, ссылки корректны** — OK.
   - `reelibra.ico` = MS Windows icon, 6 размеров (16/32 + др.) → create-shortcut.ps1.
   - `reelibra.icns` = Mac OS X icon → make-app.sh (Info.plist `CFBundleIconFile`).
   - `reelibra.png` 256×256 + `reelibra.svg` → lib.sh install_desktop_entry (hicolor scalable + 48/64/128/256).
   - Каждая ОС ссылается на свой правильный формат.

3. **Полный цикл в каждом лаунчере** — OK.
   - Bootstrap без admin/brew: uv + python-build-standalone 3.12 + portable Node 20 + static ffmpeg. Win: + VC++ Redist auto. Всё в `.reelibra-runtime/` (user-space).
   - Диагностика: версии/наличие каждый запуск, идемпотентные uv sync / pnpm install.
   - Cleanup: TERM→5с→KILL, освобождение портов 8000/3000, anti-fratricide (чужие процессы по портам не убиваются молча), stale .partial/.tmp/.lock, НЕ трогает *.db/-wal/-shm/контент.
   - Start: backend uvicorn :8000 + frontend Vite :3000, health-poll (60с), открытие браузера. trap-cleanup на выходе/Ctrl+C.
   - Health-gate валиден на всех ОС: mac/linux ждут `/docs` (включён, `docs_url` не отключён), Windows ждёт `/api/v1/health` (роут существует). Vite `port:3000, strictPort:true` совпадает с лаунчерами.

4. **.gitignore исключает .reelibra-runtime/** — OK.
   - `git check-ignore` подтверждает: `.reelibra-runtime/`, `reelibraMAC.app/`, `Reelibra.lnk` игнорируются. Большие бинарники в репо не попадут.

5. **Honesty на всех ОС** — OK.
   - Windows/Linux: явное предупреждение «STT ТОЛЬКО через Deepgram (MLX = Apple-only), нужен DEEPGRAM_API_KEY». Ключ присутствует в .env.example (стр. 40).
   - macOS Intel (x86_64): отдельная ветка с предупреждением (MLX не работает, нужен Deepgram, энкод на CPU) + интерактивное подтверждение y/N.
   - Win7/8 не заявлены: ps1 явно «Windows 10 x64 (1809+) / Windows 11 x64». Linux: glibc≥2.35 (Ubuntu 22.04+), musl/Alpine честно отклоняется. macOS: рекомендация 14+, LSMinimumSystemVersion 13.0.
   - GEMINI_API_KEY предупреждение на всех ОС (обязателен для пайплайна).

6. **NO MOCKS/TODO/заглушек** — OK. Скан launchers/ + точек входа: ноль реальных совпадений (единственный хит — `XXXXXX` в mktemp-шаблоне, false positive).

7. **bash -n + PS1 баланс** — OK.
   - `bash -n`: все 7 shell-файлов чисто.
   - PS1 launcher.ps1: braces 179/179, parens 288/288, brackets 57/57. create-shortcut.ps1 сбалансирован.

8. **Реализм «скачал → 2 клика → работает»** — реалистично на всех 3 ОС (см. таблицу). Бывший продуктовый блокер устранён: `mlx-whisper` и `stable-ts[mlx]` в `apps/backend/pyproject.toml` (стр. 29-30) помечены `; sys_platform == 'darwin'` → `uv sync` на Win/Linux их пропускает, окружение собирается.

## Honesty + no-mocks — подтверждение

- HONESTY: подтверждена на всех ОС (Deepgram-зависимость Win/Linux, Intel-Mac warning, минимальные версии ОС заявлены честно, Win7/8 не обещаны).
- NO MOCKS/TODO: подтверждено — заглушек, временного кода и недописанных веток нет.

## Незначительные замечания (не блокеры)

- macOS launcher.sh читает `APP_PORT`/`APP_HOST` только из env-переменных процесса, не парсит `.env` (Linux/Windows парсят). При нестандартном APP_PORT в .env mac будет слушать бэкенд на 8000, а health-poll пойдёт туда же — рассинхрона нет, пока пользователь не задаёт APP_PORT именно в .env. Дефолт 8000 совпадает везде. Косметика.
- Первый запуск качает ~сотни МБ рантаймов (Python/Node/ffmpeg) — ожидаемо, требует интернет; во всех лаунчерах об этом сказано.
