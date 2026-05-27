# REFACTR-49 — Approve/Reject/Regenerate UI (+ модалка prompt)

> **Этап:** 07
> **Шаг:** 50 из 67
> **Зависимости:** REFACTR-48 (карточка), REFACTR-20 (API).
> **Следующий шаг:** REFACTR-50 (Прогресс рендера + экспорт)

**ОБЯЗАТЕЛЬНО:** `frontend-design` skill активен.

---

## Роли

### R-DESIGN-ALCHEMIST
**Soul:** Три действия = три chara. Approve — зелёный жест, Reject — красный, Regenerate — нейтральный но мотивирующий.

### R-UX-WRITER
**Soul:** Модалка regenerate должна подсказать, что улучшить — но не принуждать. Prompt — опционален.

---

## ТРИЗ-принцип

*Принцип обратной связи.* Optimistic updates — UI реагирует мгновенно. Если ошибка — rollback + toast.

---

## Оркестрация

**Режим:** Sequential.

---

## Микрозадачи

### 49.1 Mutations

Уже описаны в REFACTR-29. Использовать:
- `useApproveIdea(pid, ideaId)`.
- `useRejectIdea(pid, ideaId)`.
- `useRegenerateIdea(pid, ideaId)` — принимает `{ custom_prompt?: string }`.

### 49.2 Кнопки в IdeaCard

- **Approve** — primary (accent) вариант. Клик → mutation → optimistic. Иконка checkmark.
- **Reject** — danger ghost вариант. Клик → mutation → optimistic. Иконка x.
- **Regenerate** — secondary. Клик → открывает RegenerateModal.

### 49.3 RegenerateModal

```
┌─────────────────────────────────────────┐
│ Регенерировать идею                   ✕ │
├─────────────────────────────────────────┤
│ Что улучшить? (опционально)              │
│ ┌─────────────────────────────────────┐  │
│ │                                     │  │
│ │  Оставь пустым для стандартной      │  │
│ │  альтернативы.                      │  │
│ │                                     │  │
│ └─────────────────────────────────────┘  │
│                                          │
│ Примеры:                                  │
│ • сделай жёстче                          │
│ • убери лирику, оставь факты              │
│ • начни с вопроса                         │
├─────────────────────────────────────────┤
│              [ Отмена ] [ Регенерировать ]│
└─────────────────────────────────────────┘
```

- Textarea (не input) на 3-5 строк.
- Примеры под ним — кликабельны (вставляют текст в textarea).
- Кнопка «Регенерировать» — primary.

### 49.4 Mutation regenerate

```tsx
const m = useRegenerateIdea(projectId, ideaId);
// в submit:
m.mutate({ custom_prompt: promptText || undefined });
```

Backend (REFACTR-20) принимает `{ custom_prompt?: string }`.

### 49.5 Оптимистичное поведение

- При старте regenerate: карточка меняет статус на `regenerating`, показывает spinner.
- После ответа: новая идея добавляется (с `parent_idea_id`), старая — статус `rejected` auto.
- Если `regeneration_count > 3` — warning: «Обычно после 3 попыток пора менять prompt радикально.»

### 49.6 Keyboard shortcuts

- В focused карточке: `A` — approve, `R` — reject, `G` — regenerate.
- `Cmd+A` — approve all pending.

### 49.7 Verify frontend-design

- [ ] 3 кнопки визуально различимы.
- [ ] Модалка regenerate не пугает пустым textarea.
- [ ] Shortcuts подсвечены в tooltips (подсказка «A» на Approve-кнопке).

### 49.8 Commit + Serena

---

## GATE-чекпоинт

- [ ] Approve / Reject работают, optimistic updates.
- [ ] Regenerate без prompt — стандартная регенерация.
- [ ] Regenerate с prompt — использует custom.
- [ ] Keyboard shortcuts работают.
- [ ] Новая идея появляется в grid, связь parent отображается.

---

## Артефакт на выходе

Approve/Reject/Regenerate buttons + RegenerateModal + shortcuts.
