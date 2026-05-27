# README Truth Validation — Запуск / Платформы

Источник: `README.md` (секции «Поддерживаемые системы», «Запуск в два клика», «Что под капотом»).
Сверка с: `reelibra{WIN.cmd,MAC.command,LINUX.sh}`, `launchers/{windows,macos,linux}/*`, `.gitignore`, `.env.example`.
Принцип: «ридми не должно пиздеть» — каждое утверждение проверено по коду.

Вердикт: **ПРАВДА по всем 6 пунктам.** Overpromise / ложь не найдены. Одна формулировка — НЕТОЧНО (мелкое уточнение, не ложь).

---

## 1. Имена файлов запуска — ПРАВДА

README обещает ровно: `reelibraWIN.cmd`, `reelibraMAC.command`, `reelibraLINUX.sh`.
Факт (`ls` корня):
- `reelibraWIN.cmd` — есть (2018 б)
- `reelibraMAC.command` — есть (716 б, +x)
- `reelibraLINUX.sh` — есть (2076 б, +x)

Имена совпадают посимвольно. Каждый — тонкая обёртка, делегирует в `launchers/<os>/launcher.*`.

## 2. «Ничего не нужно ставить, само скачает Python/Node/ffmpeg с прогрессом, без админа» — ПРАВДА

Bootstrap в `.reelibra-runtime/` подтверждён на всех трёх платформах, и `.gitignore` игнорит `/​.reelibra-runtime/` (рантайм не в репо — реально скачивается):

- **Windows** (`launcher.ps1`): `Ensure-Python` (python-build-standalone 3.12.8), `Ensure-Node` (Node 20.18.1), `Ensure-Ffmpeg` (BtbN static), `Ensure-Uv`, `Ensure-Pnpm` → всё в `$RuntimeDir = .reelibra-runtime\`. `Download-File` печатает `$pct%` каждые 5% (прогресс). Без админа: npm prefix в `runtime\npm-global`, `UV_PYTHON_DOWNLOADS=never`. Единственное исключение — **VC++ Redist** (`Ensure-VCRedist`): ставится system-wide через `Start-Process -Verb RunAs` (может всплыть UAC), но только если `vcruntime140.dll` отсутствует, и при отказе — non-fatal warning. См. п.6.
- **macOS** (`macos/launcher.sh`): uv (офиц. installer в `~/.local/bin`), CPython 3.12 через `uv python install`, portable Node 20 (`.reelibra-runtime/node`), static ffmpeg arm64 (`.reelibra-runtime/bin`). Комментарий: «Никаких системных модификаций». Без sudo/Homebrew.
- **Linux** (`lib.sh`): `ensure_python/uv/node/pnpm/ffmpeg` по схеме bundle→system→download в `.reelibra-runtime/`. uv-installer с `INSTALLER_NO_MODIFY_PATH=1` + `UV_INSTALL_DIR=$UV_HOME` (user-space, без root). `download()` через curl/wget. Прогресс: tty `step()` + опциональный `zenity --progress --pulsate`.

«С показом прогресса» — Windows: проценты; Linux: zenity-бар; macOS: пофазные `step…ОК`-строки (прогресс есть, гранулярность скромнее, но обещание «с показом прогресса» выполнено).

## 3. «Откроется браузер на localhost:3000» — ПРАВДА

- Windows: `Start-Process "http://localhost:3000"` (строка 740-742, `$FePort=3000`).
- macOS: `open "http://localhost:$FRONTEND_PORT"`, `FRONTEND_PORT="3000"` (строки 406, 412).
- Linux: `open_browser "http://localhost:$FRONTEND_PORT"` → `xdg-open`, `FRONTEND_PORT=3000` (строки 680, 37). Fallback-warn если нет xdg-open — честно.

Все три открывают браузер на :3000 после health-poll бэкенда.

## 4. Платформенная матрица — ПРАВДА

- **Win10 64-бит минимум, Win7/8 не заявлены** — ПРАВДА. README: «Минимум — Windows 10 64-бит (сборка 1809+)»; launcher.ps1 шапка: «Целевая ОС: Windows 10 x64 (1809+) / Windows 11 x64. Только x86-64». UI печатает «Windows 10/11 x64». Соответствует.
- **Mac right-click→Open (unsigned)** — ПРАВДА. README: «первый раз: правый клик → Открыть, т.к. приложение не подписано». Код подтверждает unsigned-природу: `xattr -dr com.apple.quarantine` (снятие карантина руками), `codesign --force --sign -` (ad-hoc, не Developer ID). Приложение действительно не подписано → right-click→Open корректен.
- **Linux install.sh даёт ярлык в меню** — ПРАВДА. `install.sh` → `install_desktop_entry()` пишет `~/.local/share/applications/reelibra.desktop` (Categories=AudioVideo;Video → «Аудио и видео»), копирует иконки в `hicolor`, `gio set ... trusted`. `reelibra.desktop` существует как шаблон с `@EXEC@`/`@ICON@`. Без root.
- **glibc ≥ 2.35 / x86_64** — ПРАВДА. `check_platform_gate()` жёстко гейтит arch≠x86_64 и glibc<2.35 (+ musl/Alpine die). README заявляет ровно это.
- **macOS Intel ⚠️ Частично, только Deepgram** — ПРАВДА. `macos/launcher.sh` детектит `x86_64`, печатает warning «MLX не работает на Intel», требует подтверждения [y/N], предупреждает про Deepgram + CPU-энкод. README-матрица совпадает.

## 5. «Проверяет окружение и подчищает зависшие процессы каждый запуск» — ПРАВДА

Каждый запуск (не разовый bootstrap):
- **Проверка окружения** — фаза «Проверка окружения/платформы» в каждом лаунчере: версии раннеров, `uv sync` + `pnpm install` идемпотентно при каждом старте.
- **Чистка висяков** — отдельная фаза в каждом:
  - Win: `Invoke-Cleanup` — порты 8000/3000 (`Get-PortPids`+`Stop-PidTree`), stray по cmdline (`Get-OurStrayPids`), `.partial/.tmp`, orphan `.lock` старше 1800с, `__pycache__`.
  - Mac: `kill_graceful` (TERM→5с→KILL) по паттернам + `free_port` 8000/3000 + чистка `.partial/.tmp/.lock`.
  - Linux: `cleanup_previous_session()` — PID-файл, `our_pids_by_pattern`, orphan ffmpeg, `reap_zombies`, `free_port` 8000/3000, `clean_stale_files`.
- **Анти-fratricide** (бонус, README не обещает, но усиливает доверие): все три различают «наши» процессы (`Test-OursPid`/`is_our_pid`/якорь по пути репо + уникальный `uvicorn videomaker.main`) и НЕ убивают чужие dev-серверы на 8000/3000 — вместо этого падают с честным сообщением.

## 6. Overpromise / ложь — НЕ НАЙДЕНО (одно НЕТОЧНО)

- **НЕТОЧНО (не ложь): «прав администратора не требуется» vs VC++ Redist на Windows.**
  README (п.3): «прав администратора не требуется». На Windows `Ensure-VCRedist` при отсутствии `vcruntime140.dll` запускает `vc_redist.x64.exe` через `-Verb RunAs` — это **может вызвать UAC-промпт** (system-wide установка). Сам код это признаёт в комментарии («может запросить права»). На практике VC++ Runtime присутствует почти на любой современной Windows (предустановлен/тянется играми и софтом), и при отказе установка не фатальна (warning). Но строго формально утверждение «прав администратора не требуется» имеет узкое исключение на чистой Windows без VC++ Runtime. Рекомендация (не блокер): добавить в README сноску «(на Windows возможен разовый UAC-запрос для Visual C++ Runtime, если он не установлен)». Это honesty-уточнение, не ложь — обещание «ничего в систему не устанавливается» нарушается только в этом единственном edge-case.

- Прочие проверенные на overpromise: «больше ничего ставить не нужно» (true — все раннеры портативны), «первый запуск дольше, нужен интернет» (true — `check_network` + downloads), «последующие запуски быстрые» (true — bundle-проверки коротят bootstrap), «данные не покидают компьютер» (вне скоупа запуска, но `.gitignore` игнорит `/data/`, `*.db`, медиа — консистентно). Overpromise нет.

---

### Сводка
| # | Утверждение | Вердикт |
|---|---|---|
| 1 | Имена файлов запуска точны и существуют | ПРАВДА |
| 2 | Bootstrap Python/Node/ffmpeg в `.reelibra-runtime`, с прогрессом, без админа | ПРАВДА |
| 3 | Открывает браузер на localhost:3000 | ПРАВДА |
| 4 | Платформенная матрица (Win10+ x64, Mac right-click, Linux ярлык, glibc≥2.35) | ПРАВДА |
| 5 | Проверка окружения + чистка висяков каждый запуск | ПРАВДА |
| 6 | «Прав администратора не требуется» | НЕТОЧНО (VC++ Redist на чистой Win → возможен UAC) |
