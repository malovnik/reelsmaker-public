# ADR-0003 — Автосохранение настроек проекта (debounce + ETag-конфликт-резолюция)

- **Статус:** ACCEPTED
- **Дата:** 2026-04-24
- **Авторы:** R-ARCHITECT, R-UX-WRITER (консультативно)
- **Связанные ADR:** [0001 Frontend Stack](./0001-frontend-stack.md), [0002 Data Storage](./0002-data-storage.md)
- **Связанный чанк:** REFACTR-09 (Этап 01, шаг 10/67)
- **Реализация:** REFACTR-15 (backend API), REFACTR-32..35 (frontend hook + индикатор)

---

## Контекст

`task.md §2.3` требует автосохранение настроек проекта с дебаунсом 10 с, 4-state индикатором в UI и конфликт-резолюцией через ETag.

Почему это критично:

1. **Боль владельца #6** (из `docs/audit/06-ux-pains.md`) — «Нет автосохранения → теряю настройки при закрытии вкладки / вылете Next.js dev-сервера». OOM в Next.js 16 (12 ГБ heap) усугубляет: dev-сервер падает 2-5 раз в день.
2. **Settings — основной редактируемый артефакт** — 7 секций (`runtime`, `brand_kit`, `post_production_preset`, `subtitle_style_preset`, `vision`, `prompts`, `profile_masks`), десятки полей. Ручной «Сохранить» неприемлем.
3. **Контракт с pipeline** — `runs/{run_id}/settings.json` (immutable frozen snapshot из ADR-0002) делается **copy-on-run**, не из автосейва. Это значит автосейв никогда не ломает детерминизм уже стартовавшего run — важная архитектурная граница.

Текущее состояние (pre-REFACTR):
- `apps/frontend` — 0 автосейв-хуков, 0 debounce-утилит (grep verified).
- `apps/backend/app/models/project.py` — минимальная модель `Project` (30 LoC), без `settings_snapshot_path`, без `last_saved_at`.
- `apps/backend/app/api/projects` — только `GET /api/projects`, `POST /api/projects`. Нет `PUT settings`.

---

## Движущие критерии решения

1. **Debounce 10 с** — явное требование владельца (`task.md §2.3`). Не 1 с (как Notion) — локально бэкенд и диск быстрые, нет смысла писать часто; но не 30 с — слишком большое окно потерь при crash.
2. **Никаких CRDT / OT** — single-user локалка не оправдывает Figma/Google Docs-сложность.
3. **Конфликт двух вкладок детектируется** — владелец открывает Studio (грид проектов) в одной вкладке, Workbench (настройки конкретного проекта) в другой; иногда дублирует вкладку с Workbench. Без ETag последняя сохранённая вкладка молча перетирает первую.
4. **Видимый статус** — 4 состояния: «Сохранено», «Изменения…», «Сохраняю…», «Ошибка». Без индикатора автосейв = слепое доверие.
5. **Offline-устойчивость** — backend может упасть (OOM Next.js теперь не при чём, но uvicorn-worker крашится от bug-ов в pipeline). Изменения не должны теряться.
6. **Pipeline не ломается** — мутация settings.json во время run не должна влиять на run. Разделение mutable `settings.json` / immutable `runs/{run_id}/settings.json`.
7. **Ctrl+S / Cmd+S** — power-user ожидает immediate flush (habitual в приложениях настроек).

---

## Рассмотренные варианты

### Вариант A — Наивный debounce без ETag

**FOR:**
- Тривиальная реализация (~20 LoC хук + `fetch`).
- Не нужна колонка `last_saved_at` в БД.

**AGAINST:**
- **Тихая потеря данных** при двух вкладках — последнее PUT перетирает. Реальный сценарий: владелец настроил 6 полей в вкладке А, переключился в Б, случайно изменил 1 поле → PUT из Б затирает 6 полей из А. Никто не поймёт, что произошло.
- Невозможно отследить «откат» — last-write-wins без детекции.
- Нарушает UX-принцип «не потеряешь работу».

**VERDICT: ❌ REJECTED.**

---

### Вариант B — Debounce 10 с + last-write-wins + ETag (RFC 7232)

**FOR:**
- **Детекция конфликта по ETag** — заголовок `If-Match: <last_saved_at>`; при несовпадении 409 Conflict + серверный snapshot в теле → модалка в UI.
- **Стандарт HTTP** — `If-Match` / `ETag` поддерживается всеми HTTP-клиентами, читается в логах, инспектируется DevTools.
- **Простая реализация** — ETag = `W/"{last_saved_at_epoch_ms}"` (weak ETag); сервер сравнивает один int64.
- **Ortogonal к CRDT/OT** — можно в будущем навернуть merge-стратегию, если понадобится.
- **TanStack Query v5** — `useMutation` + `use-debounce` (3 kB). Инфраструктурный долг нулевой.
- **Ctrl+S** — простой `KeyboardEvent` handler, отменяет debounce и триггерит flush немедленно.

**AGAINST:**
- Добавляет колонку `last_saved_at: datetime` в `projects` (уже в ADR-0002 schema).
- Нужна 409-обработка в UI (модалка) — 1 компонент ~60 LoC.
- `navigator.sendBeacon` не поддерживает кастомные headers → beforeunload-flush делается через обычный `fetch` + `keepalive: true` + browser confirm.

**VERDICT: ✅ ACCEPTED.**

---

### Вариант C — Figma/Google Docs-style OT (operational transform)

**FOR:**
- Реальный real-time collaborative — несколько курсоров, block-level granularity.
- Нет конфликтов в принципе.

**AGAINST:**
- **Оверкилл** — single-user локалка, нет multi-user. Владелец явно указал в `task.md §3.1`: «локально, web-интерфейс на localhost:3000».
- OT/CRDT-движок (yjs / automerge) — ~60-150 kB bundle, steep learning curve, сложный debug.
- Требует WebSocket-сервер — ломает простоту HTTP REST API.

**VERDICT: ❌ REJECTED.**

---

### Сравнение с эталонами (Sequential Thinking)

| Приложение | Strategy | Granularity | Conflict | Оправдано здесь? |
| --- | --- | --- | --- | --- |
| **Figma** | WebSocket + OT real-time | per-pixel op | merged | ❌ multi-user, overkill |
| **Notion** | Debounce 1-2 с + server CRDT | per-block | last-write-wins per block | ❌ settings — цельный документ |
| **Google Docs** | OT 2-3 с + версионирование | per-char | merged | ❌ overkill |
| **GitHub web editor** | On-save only + SHA-check | per-file | 409 Conflict | ✅ **наш паттерн** |
| **VSCode settings.json** | Debounce + FS write | per-file | filesystem-level | ✅ **наш паттерн** |

Мы ближе к GitHub web editor + VSCode: cельный документ, сохранение по debounce, 409 при устаревшем ETag.

---

## Решение

**Принимаем Вариант B — Debounce 10 с + ETag (weak, по `last_saved_at`) + 4-state UI + localStorage backup queue.**

### Контракт API

#### `PUT /api/projects/{project_id}/settings`

**Request:**
```http
PUT /api/projects/1a2b3c.../settings HTTP/1.1
Content-Type: application/json
If-Match: W/"1745509740123"

{
  "schema_version": 1,
  "sections": {
    "runtime": { "device": "mps", "concurrency": 2, ... },
    "brand_kit": { ... },
    "post_production_preset": { ... },
    "subtitle_style_preset": { ... },
    "vision": { ... },
    "prompts": { ... },
    "profile_masks": { ... }
  }
}
```

**Response 200 (OK):**
```http
HTTP/1.1 200 OK
ETag: W/"1745509750567"
Content-Type: application/json

{
  "last_saved_at": "2026-04-24T16:09:10.567Z",
  "checksum_sha256": "a3f5..."
}
```

**Response 409 (Conflict):**
```http
HTTP/1.1 409 Conflict
Content-Type: application/json

{
  "error": "conflict",
  "current_etag": "W/\"1745509745000\"",
  "current_snapshot": { "schema_version": 1, "sections": { ... } },
  "current_last_saved_at": "2026-04-24T16:09:05.000Z"
}
```

**Response 404 / 410** — `{project_id}` не найден или soft-deleted.
**Response 422** — Pydantic-валидация не прошла (неполный snapshot, неправильный тип).

#### `GET /api/projects/{project_id}/settings`

**Response 200:**
```http
HTTP/1.1 200 OK
ETag: W/"1745509740123"

{
  "schema_version": 1,
  "sections": { ... },
  "last_saved_at": "2026-04-24T16:09:00.123Z",
  "checksum_sha256": "b7c2..."
}
```

ETag вычисляется как `W/"{int(last_saved_at.timestamp() * 1000)}"` (weak ETag, epoch-ms).

### Контракт backend

```python
# apps/backend/app/api/projects/settings.py

from datetime import UTC, datetime
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project
from app.schemas.project_settings import ProjectSettings
from app.services.settings_io import load_snapshot, write_settings_atomic
from app.db import get_session

router = APIRouter()

def etag_for(ts: datetime) -> str:
    return f'W/"{int(ts.timestamp() * 1000)}"'

@router.put("/api/projects/{project_id}/settings")
async def update_settings(
    project_id: str,
    payload: ProjectSettings,
    if_match: str | None = Header(default=None, alias="If-Match"),
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    if project.soft_deleted_at is not None:
        raise HTTPException(410, "Project deleted")

    current_etag = etag_for(project.last_saved_at)
    if if_match is not None and if_match != current_etag:
        current_snapshot = load_snapshot(project_id)
        return JSONResponse(
            status_code=409,
            content={
                "error": "conflict",
                "current_etag": current_etag,
                "current_last_saved_at": project.last_saved_at.isoformat(),
                "current_snapshot": current_snapshot,
            },
        )

    new_saved_at = datetime.now(UTC)
    checksum = write_settings_atomic(project_id, payload.model_dump(mode="json"))
    project.last_saved_at = new_saved_at
    await session.commit()

    return JSONResponse(
        content={
            "last_saved_at": new_saved_at.isoformat(),
            "checksum_sha256": checksum,
        },
        headers={"ETag": etag_for(new_saved_at)},
    )
```

`write_settings_atomic` (из ADR-0002 §Atomic write):
1. Serialize payload → `settings.json.tmp` (sort_keys, indent=2).
2. `os.fsync` на файл.
3. `Path.replace()` (POSIX atomic rename).
4. Вычислить `sha256` от serialized bytes, записать `settings.meta.json`.
5. Вернуть checksum.

### Контракт frontend

**Хук `useAutosaveSettings(projectId)`** — единая точка, используется в Workbench и settings-страницах.

```tsx
// apps/frontend/src/features/project-settings/useAutosaveSettings.ts

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useDebouncedCallback } from 'use-debounce';
import { useEffect, useRef, useState } from 'react';

import { api, type ProjectSettings, type ConflictError } from '@/lib/api';

export type SaveState =
  | { kind: 'idle'; savedAt: Date }
  | { kind: 'debouncing' }
  | { kind: 'saving' }
  | { kind: 'error'; message: string; retryable: boolean }
  | { kind: 'conflict'; serverSnapshot: ProjectSettings; serverEtag: string };

export function useAutosaveSettings(projectId: string) {
  const qc = useQueryClient();
  const etagRef = useRef<string | null>(null);

  const { data: initial } = useQuery({
    queryKey: ['project', projectId, 'settings'],
    queryFn: async () => {
      const res = await api.getProjectSettings(projectId);
      etagRef.current = res.etag;
      return res.settings;
    },
  });

  const mutation = useMutation({
    mutationFn: async (payload: ProjectSettings) => {
      return api.putProjectSettings(projectId, payload, {
        ifMatch: etagRef.current,
      });
    },
    onSuccess: (res) => {
      etagRef.current = res.etag;
      qc.setQueryData(['project', projectId, 'settings'], res.settings);
      setState({ kind: 'idle', savedAt: new Date(res.lastSavedAt) });
      clearLocalQueue(projectId);
    },
    onError: (err: Error | ConflictError) => {
      if (err instanceof ConflictError) {
        setState({ kind: 'conflict', serverSnapshot: err.currentSnapshot, serverEtag: err.currentEtag });
      } else {
        pushLocalQueue(projectId, latestPayloadRef.current);
        setState({ kind: 'error', message: err.message, retryable: true });
      }
    },
  });

  const [state, setState] = useState<SaveState>({ kind: 'idle', savedAt: new Date() });
  const latestPayloadRef = useRef<ProjectSettings | null>(null);

  const flushNow = () => {
    debouncedFlush.flush();
  };

  const debouncedFlush = useDebouncedCallback(() => {
    if (latestPayloadRef.current) {
      setState({ kind: 'saving' });
      mutation.mutate(latestPayloadRef.current);
    }
  }, 10_000);

  const update = (next: ProjectSettings) => {
    latestPayloadRef.current = next;
    setState({ kind: 'debouncing' });
    debouncedFlush();
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 's') {
        e.preventDefault();
        flushNow();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  useEffect(() => {
    const onUnload = (e: BeforeUnloadEvent) => {
      if (state.kind === 'debouncing' || state.kind === 'saving') {
        e.preventDefault();
        e.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', onUnload);
    return () => window.removeEventListener('beforeunload', onUnload);
  }, [state.kind]);

  return { initial, state, update, flushNow, resolveConflict: (strategy: 'reload' | 'force') => { /* ... */ } };
}
```

### 4 состояния UI-индикатора

Компонент `<SaveStatusBadge state={state} />` — показывается в TopBar справа:

| State | Visual | Label | Tooltip |
| --- | --- | --- | --- |
| `idle` | серая галочка | «Сохранено 5 с назад» (`Intl.RelativeTimeFormat`) | «Последнее сохранение: 2026-04-24 16:09:10» |
| `debouncing` | жёлтый pulse | «Изменения…» | «Автосохранение через Xс. Ctrl+S — сохранить сейчас» |
| `saving` | синий spinner | «Сохраняю…» | «Отправка на сервер» |
| `error` | красный | «Ошибка» | детали ошибки + кнопка «Повторить» |

Пятый (не из 4, но необходимый) — `conflict`: модалка `<ConflictDialog />` с 3 опциями:
1. **Загрузить серверную версию** — перезагрузить snapshot с сервера, локальные изменения теряются.
2. **Принудительно сохранить** — PUT без `If-Match` → перетирает серверный (опасно, серверный snapshot копируется в `data/projects/{id}/.trash/conflict-{timestamp}.json` перед перезаписью, REFACTR-17).
3. **Отмена** — остаёмся в `conflict`-режиме, не сохраняем и не загружаем. Позволяет вручную сравнить поля.

### Offline (backend недоступен)

Локально offline в обычном смысле не бывает — backend на `localhost:8000`. Но crash uvicorn-worker-а возможен (bug в render stage и т. п.).

**Детекция:** mutation.error с `TypeError: Failed to fetch` / `ECONNREFUSED` / 5xx.

**Поведение:**
1. `state = 'error'`, retryable=true.
2. Payload пишется в localStorage: `videomaker.autosave.queue.{project_id}` → `{ payload: ProjectSettings, timestamp: ISO }`. Сохраняется **только последний** payload (last-write-wins — очередь из одного элемента).
3. Background poll: `setInterval(() => fetch('/api/health'), 5_000)`. При 200 — попытка flush.
4. При flush очереди — если PUT успешен, запись из localStorage удаляется. Если снова conflict/error — остаётся в очереди.
5. LocalStorage-очередь также проверяется при старте приложения (page load): `useEffect` → если `queue[project_id]` существует, показать toast «Восстанавливаю несохранённые изменения…» + flush.

**Почему не IndexedDB:** single payload ~50-150 КБ, лимит localStorage 5-10 МБ — с запасом. IndexedDB overkill.

### Pipeline-изоляция

Автосейв пишет в `data/projects/{id}/settings.json` (mutable).

Запуск pipeline (REFACTR-16 `POST /api/projects/{id}/runs`):
1. Backend читает актуальный `settings.json`.
2. Копирует в `data/projects/{id}/runs/{run_id}/settings.json` — **immutable** (ADR-0002 §Disk structure).
3. Pipeline stages читают **только** immutable-копию. Мутации автосейва после старта run — не влияют.

Это отдельный контракт, реализуется в REFACTR-16. Здесь фиксируем как инвариант: **автосейв не видит `runs/`**.

---

## Последствия

### Положительные

1. **Владелец не теряет настройки** — дебаунс 10 с, Ctrl+S, localStorage-fallback.
2. **4-state индикатор** — всегда ясно, где сохранено.
3. **Конфликт двух вкладок** — детектируется и разрешается осознанно.
4. **Pipeline-изоляция** — мутация во время run не ломает детерминизм.
5. **Стандарт RFC 7232** — логи/DevTools читаемы, нет vendor-specific протокола.
6. **+3 kB bundle** (`use-debounce`) — пренебрежимо.

### Отрицательные

1. **+1 колонка** `last_saved_at` в `projects` (уже в ADR-0002).
2. **+1 компонент** `<ConflictDialog />` (~80 LoC).
3. **BeforeUnload-flush не 100% гарантирован** — если пользователь закрыл вкладку через Cmd+Q без confirm, последний payload уходит в localStorage-очередь; при следующем старте восстанавливается.
4. **Merge не делается** — при conflict только «перезагрузить» / «force save», не смешивание полей. Это осознанный компромисс: полу-мержи сложны и часто ломают UX. Если окажется критичным — отдельный ADR для per-section merge.

### Нейтральные

- `If-Match` заголовок требует HTTP client, умеющий custom headers — браузерный `fetch` умеет, `sendBeacon` не умеет (поэтому не используем его для flush). Компенсируется keepalive + beforeunload confirm.

---

## Верификация

Gate-критерии (REFACTR-15 backend + REFACTR-32..35 frontend):

1. `curl PUT /api/projects/{id}/settings` без `If-Match` → 200 + `ETag` в ответе.
2. `curl PUT` с устаревшим `If-Match` → 409 + тело содержит `current_etag`, `current_snapshot`, `current_last_saved_at`.
3. Два параллельных `PUT` в разных shell-ах: один 200, один 409 (race-safe).
4. В UI: измените 20 полей за 8 с → **один** PUT после debounce (debounce работает).
5. Ctrl+S / Cmd+S → немедленный PUT, debounce отменяется.
6. Kill uvicorn-worker (`kill -9 <pid>`) → индикатор `error`, payload в `localStorage['videomaker.autosave.queue.{project_id}']`.
7. Restart uvicorn → toast «Восстанавливаю изменения…» → `idle` после успеха.
8. Открыть проект в 2 вкладках, изменить поле в обеих, flush в 1-й → 2-я получает 409 при своём flush → `ConflictDialog` с 3 опциями.
9. Запустить pipeline → изменить `settings.json` во время run → `runs/{run_id}/settings.json` не изменился (diff empty).
10. `beforeunload` → показать browser confirm если state в `debouncing` / `saving`.

---

## Открытые вопросы

1. **Force save → копия перезаписываемого** — когда пользователь выбирает «Force save» в conflict, надо ли бэкапить текущий серверный snapshot в `.trash/conflict-{timestamp}.json`? Ответ: **Да** (фиксируется в REFACTR-17 как часть hard-delete + trash infrastructure).
2. **Merge per-section** — нужен ли полу-автоматический merge на уровне секций при conflict? Ответ: **Нет** в MVP. Отдельный ADR, если появится реальная боль.
3. **Throttle Ctrl+S спам** — если пользователь жмёт Ctrl+S 10 раз в секунду. Ответ: mutation в `isPending` состоянии блокирует повторные вызовы (TanStack Query).

---

## Ссылки

- RFC 7232 — HTTP Conditional Requests: https://www.rfc-editor.org/rfc/rfc7232
- TanStack Query v5 — Mutations: https://tanstack.com/query/v5/docs/framework/react/guides/mutations
- `use-debounce` — https://github.com/xnimorz/use-debounce
- ADR-0002 — Data Storage (per-run immutable snapshot, atomic write, checksum_sha256)
- `task.md §2.3` — требование «debounce 10 с + ETag + 4 UI-состояния»
- `docs/audit/06-ux-pains.md` — боль #6 «нет автосохранения»
- `RM-CHUNKS/01 — Архитектурные решения/REFACTR-09.md` — исходный чанк
