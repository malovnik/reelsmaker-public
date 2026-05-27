# REFACTR-35 — Атомы: Button, Input, Select, Chip, Badge, Avatar, Icon

> **Этап:** 05
> **Шаг:** 36 из 67
> **Зависимости:** REFACTR-33, REFACTR-34.
> **Следующий шаг:** REFACTR-36 (Молекулы)

**ОБЯЗАТЕЛЬНО:** `frontend-design` skill активен.

---

## Роли

### R-DESIGN-ALCHEMIST
**Soul:** Атом — единица. Не «shadcn Button как есть», а Button videomaker'а: знает про accent, про dark/light, про состояния, про мотор (hover/active/disabled/loading).

### R-A11Y-ENG (консультативно)
**Soul:** Каждый атом a11y: focus-visible, ARIA, keyboard nav.

---

## ТРИЗ-принцип

*Принцип универсальности.* Один атом — много сценариев через вариации (variant, size, tone). Не множим компоненты, а расширяем API.

---

## Оркестрация

**Режим:** Sequential. Атомы пишутся последовательно в одном чанке.

---

## Микрозадачи

### 35.1 Button

`src/design/components/Button.tsx`:

- Variants: `primary` (accent), `secondary` (muted surface), `ghost` (transparent + hover), `danger` (red).
- Sizes: `xs | sm | md | lg`.
- States: default, hover, active, disabled, loading.
- Props: `asChild` (через `@radix-ui/react-slot` — для Link-обёртки), `leading/trailing` иконки, `loading` spinner.

Визуально:
- Primary: bg accent, text on-accent, shadow-sm, hover+brightness.
- Secondary: bg elevated, text primary, border subtle.
- Ghost: transparent, hover bg hover.
- Radius md (8 px).
- Transition 150 ms.

### 35.2 Input

Text input:
- Sizes: sm/md/lg (padding + text-size).
- States: default, focus (accent ring), error (danger border), disabled.
- Иконка leading/trailing.
- Clear button (optional).

### 35.3 Select

Radix `Select`:
- Триггер — как Input.
- Dropdown — bg elevated, shadow-md, radius lg.
- Items — hover bg hover, active bg accent-muted.
- Keyboard navigation, a11y.

### 35.4 Chip

Small pill:
- Variants: default (subtle border), accent (accent-muted), success/warning/danger.
- Onclick + onDismiss props.
- Sizes: xs/sm.

### 35.5 Badge

Для статусов (approved, pending, rejected):
- Цветной dot + label.
- 4 варианта: accent, success, warning, danger.

### 35.6 Avatar

- Fallback: инициалы или иконка.
- Sizes: xs/sm/md/lg.
- Можем не нужен (одно-юзерное приложение) — сделать минимально, использовать для профиля-создателя сессии.

### 35.7 Icon

Обёртка над lucide-react:
- `<Icon name="video" size="md" />`.
- Размеры через токены (xs 12 / sm 14 / md 16 / lg 20 / xl 24).

### 35.8 Storybook-like preview

Расширить `/design-preview`:
- Все variants × sizes × states.
- Dark + Light.
- Живые для проверки.

### 35.9 Верификация frontend-design

Пройти раздел «Anti-AI-slop» skill'а:
- [ ] Нет generic «modern» кнопок.
- [ ] Primary CTA — accent-цвет, контраст отчётливый.
- [ ] Нет фальшивого glassmorphism на кнопках.
- [ ] Нет эмодзи.
- [ ] Тексты — на русском, проверены UX-writer-ом.

### 35.10 Commit + Serena

---

## GATE-чекпоинт

- [ ] 7 атомов реализованы.
- [ ] Все работают в dark + light.
- [ ] `/design-preview` показывает все варианты.
- [ ] A11y: tab navigation, focus-visible, ARIA.
- [ ] Anti-slop чеклист пройден.

---

## Артефакт на выходе

`src/design/components/` — 7 атомов + preview.
