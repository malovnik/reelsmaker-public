# REFACTR-36 — Молекулы: Card, Modal, Toast, Tooltip, Popover, Tabs

> **Этап:** 05
> **Шаг:** 37 из 67
> **Зависимости:** REFACTR-35 (атомы).
> **Следующий шаг:** REFACTR-37 (ThemeProvider)

**ОБЯЗАТЕЛЬНО:** `frontend-design` skill активен.

---

## Роли

### R-DESIGN-ALCHEMIST
**Soul:** Молекула = композиция атомов. Модалка — Card + Overlay + Button'ы. Не изобретаем примитивы внутри — используем готовые атомы.

### R-A11Y-ENG
**Soul:** Модалки — focus trap. Tooltips — delayed. Tabs — ARIA roles.

---

## ТРИЗ-принцип

*Принцип копирования.* Radix UI уже решил a11y для dialog/popover/tooltip. Мы накладываем свой visual layer, не переизобретая поведение.

---

## Оркестрация

**Режим:** Sequential.

---

## Микрозадачи

### 36.1 Card

- Простая карточка: bg elevated, border subtle, radius md, padding md.
- Variants: default, interactive (hover scale 1.01 + shadow-lift), outline-only.
- Композиция: `Card.Header`, `Card.Body`, `Card.Footer`.

### 36.2 Modal (Dialog)

Radix `Dialog`:
- Backdrop: bg overlay-backdrop.
- Content: bg elevated, radius lg, shadow-lg, max-w 560 px (default).
- Header с close icon.
- Footer с actions.
- Animation: fade + scale 0.98 → 1.
- Focus trap.

### 36.3 Toast

`sonner` библиотека (Context7 подтвердить актуальность) или свой компонент:
- 4 варианта: success, warning, danger, info.
- Position: bottom-right по умолчанию.
- Auto-dismiss 5 с, swipe-to-dismiss.
- Actions (опционально).

### 36.4 Tooltip

Radix `Tooltip`:
- Delay 400 ms.
- Content: bg primary (инвертированный), text secondary, radius sm, padding xs sm.
- Arrow.

### 36.5 Popover

Radix `Popover`:
- Content как у модалки, но меньше.
- Arrow — опционально.

### 36.6 Tabs

Radix `Tabs`:
- Horizontal — под-навигация внутри страницы (settings-like).
- Vertical — редко, но доступно.
- Active indicator — линия accent-цвета.

### 36.7 Dropdown Menu

Radix `DropdownMenu`:
- Используется в контекстных меню (REFACTR-40).
- Item hover bg hover.
- Separator, Group, Label.

### 36.8 Preview

`/design-preview` — живые примеры каждой молекулы в dark + light.

### 36.9 Verify frontend-design

- [ ] Anti-slop чеклист.
- [ ] Никаких generic shadcn/ui outline как в tutorial-ах.
- [ ] Motion: 150-250 ms, cubic-bezier(0.2, 0, 0.2, 1).

### 36.10 Commit + Serena

---

## GATE-чекпоинт

- [ ] 7 молекул реализованы.
- [ ] Dark + light работают.
- [ ] A11y: focus trap в модалке, ARIA в tabs, keyboard в dropdown.
- [ ] Preview обновлён.

---

## Артефакт на выходе

7 молекул в `src/design/components/` + preview.
