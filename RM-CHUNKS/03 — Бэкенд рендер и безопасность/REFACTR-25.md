# REFACTR-25 — Command injection + path traversal

> **Этап:** 03
> **Шаг:** 26 из 67
> **Зависимости:** REFACTR-18 (Finder-open уже защищён), REFACTR-21 (ffmpeg).
> **Следующий шаг:** REFACTR-26 (rate-limit + чистка debug-кода)

---

## Роли

### R-SECURITY
**Soul:** Command injection и path traversal — два самых частых класса уязвимостей в сервисах, которые спавнят дочерние процессы или читают файлы по пользовательскому вводу. Оба покрываются дисциплиной: argv-only + resolve-and-check.

---

## ТРИЗ-принцип

*Принцип универсальности.* Один стандартный защитный паттерн (resolve + root-check) применяется везде, где есть пользовательский path. Один стандартный паттерн argv-only — везде, где backend запускает внешний процесс.

---

## Оркестрация

**Режим:** Sequential.

---

## Микрозадачи

### 25.1 Инвентаризация вызовов внешних процессов

Через Serena:
- [ ] `search_for_pattern` по `subprocess\\.|asyncio\\.create_subprocess` — все места запуска дочерних процессов.
- [ ] Проверить отсутствие устаревших системных вызовов (должно быть 0 во всём backend).
- [ ] Для каждого найденного вызова: аргументы формируются через argv-массив или через shell-строку?

Ожидаемые места:
- `renderer.py` / `project_renderer.py` — ffmpeg.
- `silence_cutter.py` — ffmpeg для silence-detect.
- `proxy.py` — ffmpeg для preview.
- `services/transcribers/mlx_whisper_backend.py` — если спавнит отдельный процесс.
- `REFACTR-18 Finder-open` — уже argv-only.

### 25.2 Правило: argv-only

Для каждого места:
- [ ] Аргументы — список строк (argv).
- [ ] Параметр `shell` — False (по умолчанию).
- [ ] Никаких `" ".join(...)` в командной строке.
- [ ] Все пользовательские значения проходят через валидацию (запрет `\0`, `\n`, `\r`).

### 25.3 Инвентаризация path-вводов

API endpoints, которые принимают path-like input:
- Upload видео (имя файла от клиента).
- Finder-open.
- Чтение артефактов (`GET /api/projects/{id}/artifacts/{filename}`).
- Download клипов.

### 25.4 Правило: resolve + root-check

Стандартный helper `services/paths.py`:

- Функция `safe_path(root: Path, user_input: str) -> Path`.
- Реализация: склеить `root / user_input`, вызвать `resolve(strict=False)`, проверить `relative_to(root_resolved)` — если выбрасывает `ValueError`, значит был traversal → `raise ValueError("path_traversal_blocked")`.
- Применить во всех API endpoints, принимающих path.

### 25.5 Semgrep правила

- [ ] Skill `static-analysis:semgrep` — important-only scan.
- [ ] Правила должны поймать: shell-режим запуска процесса, string-конкатенацию в argv, отсутствие `safe_path` в uploads.

### 25.6 Verification

- [ ] Ручной тест: `curl .../api/projects/../etc/passwd/open-in-finder` → 400.
- [ ] Ручной тест: загрузить файл с именем `test.mp4; rm -rf /` → принимается как строковое имя, не выполняется.
- [ ] Semgrep-отчёт — 0 high/critical.

### 25.7 Документ

Создать/обновить `docs/security/local-hardening.md`:
- Таблица «источник пользовательского ввода → какая защита применяется».
- Правила argv-only + safe_path.
- Примеры атак, которые заблокированы.

### 25.8 Commit + Serena memory

---

## GATE-чекпоинт

- [ ] Все внешние процессы запускаются через argv-массив.
- [ ] Все path-вводы проходят через `safe_path`.
- [ ] Semgrep 0 high/critical findings.
- [ ] Ручной pentest на 3 сценария пройден.
- [ ] Документ security-harden обновлён.

---

## Артефакт на выходе

Hardened backend + semgrep-отчёт + документ по local-hardening.
