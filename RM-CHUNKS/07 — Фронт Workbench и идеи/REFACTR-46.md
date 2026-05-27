# REFACTR-46 — Pipeline timeline + кнопка «Начать заново с шага»

> **Этап:** 07
> **Шаг:** 47 из 67
> **Зависимости:** REFACTR-45 (layout), REFACTR-16 (restart API), SSE-events.
> **Следующий шаг:** REFACTR-47 (Режимы авто/пошагово)

**ОБЯЗАТЕЛЬНО:** `frontend-design` skill активен.

---

## Роли

### R-DESIGN-ALCHEMIST
**Soul:** Timeline стадий = нерв Workbench. По нему пользователь читает «где я и что сейчас происходит». Визуально должно быть сразу ясно.

### R-FRONTEND-ARCHITECT
**Soul:** Состояние стадий — через SSE. Каждое событие обновляет Query. Никаких polls, никаких setInterval.

---

## ТРИЗ-принцип

*Принцип обратной связи.* Каждая стадия имеет статус (pending/running/done/error). Пользователь видит в любой момент.

---

## Оркестрация

**Режим:** Sequential.

---

## Микрозадачи

### 46.1 PipelineTimeline компонент

`src/features/workbench/PipelineTimeline.tsx`:

Список стадий (из REFACTR-05, точный список стадий):
- Транскрипция
- Удаление тишины и филлеров
- Анализ смыслов (LLM)
- Генерация идей
- Склейка рилсов
- Цвет + субтитры + B-roll
- Финальный рендер

Каждая стадия — row в sidebar:

```
  ● Транскрипция                      ✓ done
  ◐ Удаление тишины                   running 34%
  ○ Анализ смыслов                    pending
  ○ Генерация идей                    pending
  ○ Склейка                           pending
  ○ Рендер                            pending
```

Индикаторы:
- ✓ done — зелёная точка.
- ◐ running — accent-цвет, крутящийся spinner + процент.
- ○ pending — серая рамка.
- ! error — красный треугольник.

### 46.2 Источник данных

- `useProject(id)` → `project.stage_progress` — начальное состояние.
- `useEventSource('/api/jobs/{id}/events')` → SSE-события `{stage, status, progress}` обновляют Query через `queryClient.setQueryData`.

### 46.3 Клик по стадии

При клике на строку-стадию:
- Если стадия уже done → кнопка «Начать заново с этой стадии».
- Если running → disabled (ждём завершения).
- Если pending → disabled.

Подтверждение через ConfirmModal: «Перезапустить с шага X? Все результаты дальнейших шагов будут удалены.»

По подтверждению: `useRestartFromStage()` mutation → `POST /api/projects/{id}/restart` с `{from_stage: "transcribe"}`. На успех — invalidate всё и показать toast.

### 46.4 Контекстное меню стадии

Альтернатива клику: «многоточие» в row:
- Начать заново с этой стадии.
- Пропустить (если возможно).
- Открыть логи (modal с логом именно этой стадии).

### 46.5 Хранение истории

Каждый restart — event. Сохраняем историю в `project.stage_progress.history` (бэк уже хранит в REFACTR-14). Фронт может показать «Перезапускалось 2 раза».

### 46.6 Verify frontend-design

- [ ] Timeline читается с одного взгляда (какая стадия активна — ясно).
- [ ] Accent-цвет только у running-стадии.
- [ ] Нет generic spinners.

### 46.7 Commit + Serena

---

## GATE-чекпоинт

- [ ] Timeline отрисован с правильными статусами.
- [ ] SSE обновляет статусы live.
- [ ] «Начать заново» работает, downstream артефакты инвалидированы.
- [ ] History просматривается.

---

## Артефакт на выходе

PipelineTimeline + ConfirmModal для restart + logs modal (опционально).
