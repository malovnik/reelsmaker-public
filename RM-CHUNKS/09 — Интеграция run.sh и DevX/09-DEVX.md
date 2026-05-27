# Этап 09: Интеграция — run.sh и DevX

> Статус: ⬜ Не начат
> Родитель: [[PIPELINE-НАВИГАТОР]]
> Проект: **videomaker-рефакторинг**

## Суть этапа

Запуск-скрипт `run.sh` — единственная точка входа. Владелец сказал: «Запуск должен остаться по `run.sh` с проверкой всех зависимостей и установкой если надо и очищением всех процессов при завершении».

Текущий `run.sh` уже неплохо справляется с preflight-cleanup, но заточен под Next.js. Нужно:

1. Переключить на Vite-dev-server (порт остаётся 3000).
2. Добавить автоматическую проверку/установку зависимостей (`uv sync`, `pnpm install`).
3. Ужесточить orphan-guard: все `vite`, `node`, `uvicorn`, `ffmpeg`-дети должны умирать на SIGINT.
4. Логи проекта унифицировать в `data/logs/` с ротацией.
5. `.env` guard: при отсутствии ключей (GEMINI/DEEPGRAM) — warning, а не silent-fallback.

**Режим работы:** Sequential.

## Подэтапы (REFACTR-58..REFACTR-61)

- **REFACTR-58** — run.sh preflight: uv sync + pnpm install + ffmpeg/open/lsof checks ⬜
- **REFACTR-59** — run.sh startup: Vite-dev (не Next), uvicorn reload, trap SIGINT/TERM/EXIT ⬜
- **REFACTR-60** — Унифицированные логи: structlog backend + pino/custom frontend → `data/logs/` ⬜
- **REFACTR-61** — .env guard + стартовый health-check (API-ключи валидны, VideoToolbox доступен) ⬜

## Вход

- Текущий `run.sh`.
- Backend и frontend после миграции (этапы 02, 03, 04).

## Выход

- Обновлённый `run.sh`.
- `scripts/health-check.sh` для проверки окружения.
- `data/logs/` с ротацией (7 дней, 100 МБ на файл).

## GATE-чекпоинт этапа

- [ ] `./run.sh` с нуля на чистой системе: detects missing deps → подсказывает установку → не падает silently.
- [ ] Ctrl+C убивает ВСЁ дерево процессов (проверено `ps aux | grep` через 5 с после Ctrl+C).
- [ ] Логи backend и frontend попадают в `data/logs/{backend,frontend}.log`.
- [ ] `.env` без `GEMINI_API_KEY` → warning в терминал + health-endpoint возвращает 503.
- [ ] Скрипт идемпотентен: повторный запуск не конфликтует с предыдущим.
