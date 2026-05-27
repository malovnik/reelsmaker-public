# REFACTR-40 — Контекстное меню карточки

> **Этап:** 06
> **Шаг:** 41 из 67
> **Зависимости:** REFACTR-39 (ProjectCard), REFACTR-18 (backend endpoints).
> **Следующий шаг:** REFACTR-41 (Модалка нового проекта)

**ОБЯЗАТЕЛЬНО:** `frontend-design` skill активен.

---

## Роли

### R-DESIGN-ALCHEMIST
**Soul:** Контекстное меню = концентрация действий. Должно быть очевидно что делает каждый пункт. Группы разделяются subtle border.

### R-UX-WRITER
**Soul:** «Удалить» vs «Удалить навсегда» — слова разные. Первое — soft-delete, второе — hard. Граница ясна, подтверждение обязательно для hard.

---

## ТРИЗ-принцип

*Принцип копирования.* Radix DropdownMenu уже сделал всю работу по a11y/keyboard/positioning. Мы даём ему visual layer.

---

## Оркестрация

**Режим:** Sequential.

---

## Микрозадачи

### 40.1 ProjectCardMenu

`src/features/studio/ProjectCardMenu.tsx`:

Пункты (в порядке):

1. **Открыть** — `navigate('/jobs/{id}')` — дублирует клик по карточке.
2. **Переименовать** — открывает inline-input в названии карточки (или модалка с одним полем).
3. **Открыть в Finder** — `POST /api/projects/{id}/open-in-finder`.
4. — separator —
5. **Скопировать настройки в новый** — открывает «Новый проект» с pre-selected source.
6. — separator —
7. **Убрать из сетки** — soft-delete (`POST /api/projects/{id}/soft-delete`). Toast «Проект скрыт. Восстановить?» с кнопкой Undo.
8. **Удалить навсегда** — danger-вариант. Открывает ConfirmModal.

### 40.2 Триггер

Кнопка-«многоточие» в углу карточки. При hover — появляется. Также работает правый клик на карточку (context menu).

### 40.3 Переименование

Inline-редактирование:
- Клик «Переименовать» → заголовок карточки превращается в Input.
- Enter сохраняет (mutation), Escape отменяет.
- Optimistic update.
- API: `PATCH /api/projects/{id}` (если нет — добавить в REFACTR-14).

### 40.4 Soft-delete с undo

- Мутация → toast с кнопкой «Отменить».
- По клику Undo: `POST /api/projects/{id}/restore`.
- Invalidate `qk.projects()`.

### 40.5 Hard-delete с confirm

```tsx
<ConfirmModal
  title="Удалить навсегда?"
  description="Проект и все его файлы будут удалены. Восстановить невозможно."
  confirmLabel="Удалить"
  confirmVariant="danger"
  onConfirm={() => hardDelete(id)}
/>
```

Mutation: `DELETE /api/projects/{id}?force=true`. Успех → toast «Удалено».

### 40.6 Keyboard

- Пункты меню проходимы стрелками.
- Enter — активация.
- Escape — закрытие.
- Radix из коробки.

### 40.7 Verify frontend-design

- [ ] Danger action выделен цветом.
- [ ] Separator'ы группируют по смыслу.
- [ ] Иконки слева от каждого пункта (опционально).

### 40.8 Commit + Serena

---

## GATE-чекпоинт

- [ ] Меню открывается по клику на «многоточие» и right-click.
- [ ] Все 6 действий работают.
- [ ] Rename: inline или модалка — стабильно.
- [ ] Soft/hard delete — разное поведение.
- [ ] Toast undo работает.

---

## Артефакт на выходе

ProjectCardMenu + ConfirmModal + интеграция с Card.
