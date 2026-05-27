# REFACTR-60 — Унифицированные логи (structlog + frontend logger)

> **Этап:** 09
> **Шаг:** 61 из 67
> **Зависимости:** REFACTR-26 (чистка debug-кода).
> **Следующий шаг:** REFACTR-61 (.env guard + health-check)

---

## Роли

### R-DEVOPS
**Soul:** Один формат логов, одно место хранения. Иначе debugging — угадайка.

### R-BACKEND-SURGEON
**Soul:** Бэкенд — structlog с JSON. Для чтения — `jq`. В dev — pretty-printed.

---

## ТРИЗ-принцип

*Принцип объединения.* Backend и frontend пишут в одну папку `data/logs/`, один формат (JSON), одни метки (event, timestamp, level, context).

---

## Оркестрация

**Режим:** Sequential.

---

## Микрозадачи

### 60.1 Backend structlog

- [ ] Проверить `models/logging.py` — уже есть structlog конфиг.
- [ ] Финализировать:
  - Output: stdout (для dev) + `data/logs/backend.jsonl` (rotated).
  - Processors: mask_secrets (REFACTR-24), add timestamp, add level, render as JSON.
  - Dev: pretty renderer.

### 60.2 Ротация backend

Через `logging.handlers.TimedRotatingFileHandler` или `structlog.processors.FileRotator`:
- По дням.
- Храним 7 файлов.
- Max 100 МБ на файл (по size тоже).

### 60.3 Frontend logger

`src/lib/logger.ts`:

```ts
interface LogEvent {
  event: string;
  level: 'info' | 'warn' | 'error' | 'debug';
  [key: string]: unknown;
}

export function log(event: LogEvent) {
  if (import.meta.env.DEV) {
    console[event.level]?.(event);
  }
  // Для production логов (если когда-то нужны) — POST в backend /api/logs/frontend.
  // Сейчас — только dev console.
}
```

Использование: `log({ event: 'project_create_click', level: 'info', projectId: id })`.

### 60.4 Frontend error boundary

`src/components/ErrorBoundary.tsx`:
- Поймать React-ошибки.
- Показать fallback UI.
- Отправить в logger + POST `/api/logs/frontend` с деталями.

### 60.5 Backend endpoint для frontend-логов

```python
@router.post("/logs/frontend")
async def frontend_log(payload: FrontendLogEntry):
    logger.info("frontend", **payload.model_dump())
```

### 60.6 Документ

`docs/ops/LOGS.md`:
- Где лежат логи.
- Как читать (`tail -f data/logs/backend.jsonl | jq`).
- Формат событий.
- Где искать что.

### 60.7 Smoke

- [ ] Запустить приложение → логи появляются в `data/logs/backend.jsonl`.
- [ ] Вызвать фронт-событие → появляется запись.
- [ ] Маски секретов работают (нет ключей в логах).

### 60.8 Commit + Serena

---

## GATE-чекпоинт

- [ ] Backend логи в `data/logs/backend.jsonl` + ротация.
- [ ] Frontend логирование работает (dev console + опционально backend POST).
- [ ] Error boundary фронта ловит и логирует.
- [ ] Маски секретов (проверено тестом).
- [ ] Документ LOGS.md создан.

---

## Артефакт на выходе

Унифицированная система логов + ErrorBoundary + LOGS.md.
