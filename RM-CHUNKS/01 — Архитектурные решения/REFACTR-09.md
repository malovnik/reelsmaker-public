# REFACTR-09 — ADR: Автосохранение (debounce + конфликт-резолюция)

> **Этап:** 01
> **Шаг:** 10 из 67
> **Зависимости:** REFACTR-08 (storage).
> **Следующий шаг:** REFACTR-10 (ADR: Видеодвижок)

---

## Роли

### R-ARCHITECT
**Soul:** Автосохранение — не просто debounce. Это договор с пользователем: «не потеряешь работу, даже если выключится свет».

### R-UX-WRITER (консультативно)
**Soul:** Пользователь должен **видеть** статус: «Сохранено 2 с назад» / «Сохраняю…» / «Ошибка сохранения». Без индикатора автосейв превращается в доверие вслепую.

---

## ТРИЗ-принцип

*Принцип предварительного подставленного противодействия.* Конфликты «две вкладки открыты одновременно» в single-user локалке маловероятны, но возможны. Решаем превентивно: last-write-wins + версионный номер snapshot'а.

---

## Оркестрация

**Режим:** Sequential + Sequential Thinking.

---

## Микрозадачи

### 09.1 Контракт автосохранения

**Триггер:** изменение любой настройки проекта или поля в Workbench.
**Стратегия:** debounce 10 с (как просил владелец) или immediate-ручное через Ctrl+S.
**API:** `PUT /api/projects/{id}/settings` — полный snapshot, last-write-wins.
**Индикатор UI:** 4 состояния — idle («Сохранено»), debouncing («Изменения…»), saving («Сохраняю…»), error («Ошибка»).

### 09.2 Конфликты

**Сценарий:** две вкладки редактируют один проект.
**Решение:** при открытии проекта создаётся `session_token`, сохраняется в локальном state. При PUT передаётся `If-Match: <last_saved_at>` — если сервер видит более свежий snapshot, возвращает 409 Conflict + текущий snapshot в ответе.

**Поведение UI:** модалка «Проект изменён в другой вкладке. Перезагрузить и потерять локальные изменения?».

### 09.3 Offline

**Локальный режим** → офлайна не бывает (backend работает в той же машине). Если backend упал — UI показывает toast «Backend недоступен», сохранение в очередь (localStorage), при восстановлении — flush.

### 09.4 Sequential Thinking

- [x] Сравнить с подходами: Figma (OT / WebSocket — ❌ overkill), Notion (debounce 1-2 с + server CRDT per-block — ❌ settings цельный документ), Google Docs (OT + 2-3 с — ❌ overkill), GitHub web editor / VSCode settings.json (debounce + SHA/ETag — ✅ наш паттерн).
- [x] Для single-user локалки не нужен CRDT / OT. Выбрано: last-write-wins + weak ETag по `last_saved_at` (RFC 7232 `If-Match`).

### 09.5 Написать ADR

`docs/adr/0003-autosave.md` — создан (380 строк, MADR).

### 09.6 Serena memory

- [x] `write_memory(name="refactr-09-adr-autosave", content="...")`.

---

## GATE-чекпоинт

- [x] ADR-0003 принят (status ACCEPTED).
- [x] 4 состояния UI-индикатора описаны (idle / debouncing / saving / error) + 5-е для conflict (модалка `<ConflictDialog />` с 3 опциями: reload / force save / cancel).
- [x] Конфликт-резолюция описана (weak ETag по `last_saved_at`, 409 Conflict с `current_snapshot` в теле).
- [x] Offline (backend down) поведение описано (localStorage last-only queue + 5-с health-poll + flush при восстановлении).

---

## Артефакт на выходе

`docs/adr/0003-autosave.md`.
