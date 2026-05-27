# REFACTR-38 — Motion: микро-транзиции + правила анимаций

> **Этап:** 05
> **Шаг:** 39 из 67
> **Зависимости:** REFACTR-35, REFACTR-36.
> **Следующий шаг:** REFACTR-39 (Grid проектов)

**ОБЯЗАТЕЛЬНО:** `frontend-design` skill активен.

---

## Роли

### R-MOTION — Моушн-дизайнер
**Профессия:** Специалист по Framer Motion и CSS-анимациям.
**Soul:** Движение — язык. Говорит «это кликнулось», «что-то появилось», «это перетаскивается». Без языка — мёртвый интерфейс. С переизбытком — шумный.

### R-A11Y-ENG
**Soul:** `prefers-reduced-motion` — уважать. Для a11y-users — ставим все durations в 0.

---

## ТРИЗ-принцип

*Принцип динамизации.* Каждая анимация имеет причину. Нет анимации ради анимации.

---

## Оркестрация

**Режим:** Sequential.

---

## Микрозадачи

### 38.1 Motion tokens

`src/design/tokens/motion.ts`:

```ts
export const motion = {
  duration: {
    instant: '50ms',
    fast: '100ms',
    moderate: '150ms',   // default для hover/focus
    medium: '250ms',     // default для overlay (modal, popover)
    slow: '400ms',       // для больших переходов (route)
  },
  easing: {
    standard: 'cubic-bezier(0.2, 0, 0.2, 1)',      // default
    enter: 'cubic-bezier(0, 0, 0.2, 1)',           // вход
    exit: 'cubic-bezier(0.4, 0, 1, 1)',            // выход
    bounce: 'cubic-bezier(0.4, 0, 0.2, 1.4)',      // редко, для подчёркивания
  },
};
```

### 38.2 Правила

`docs/design/MOTION.md`:

- **Hover/focus**: 100-150 ms, standard easing.
- **Modal/popover open**: 200-250 ms, enter easing.
- **Modal/popover close**: 150 ms, exit easing.
- **Route change**: fade 200-300 ms.
- **List reorder / add / remove**: 200 ms.
- **Progress indicators**: бесконечная, linear.
- **Skeleton loading**: pulse 1.5 s.
- **Toast enter/exit**: slide + fade 250 ms.

Запрет:
- Более 300 ms на интерактивные переходы.
- Spring-animations для всего подряд (только для drag-реакций).
- Парallax / scroll-driven animations (нет смысла в инструменте).

### 38.3 Библиотека

Выбор: Framer Motion (v11) или CSS transitions.
- Для простых — CSS `transition`.
- Для состояний (exit animation, layout shift) — Framer Motion.

Установить `framer-motion` (Context7 актуальная версия).

### 38.4 Утилиты

`src/design/motion.ts`:

```ts
export const fadeIn = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  exit: { opacity: 0 },
  transition: { duration: 0.15 },
};

export const slideUp = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -4 },
  transition: { duration: 0.2, ease: [0.2, 0, 0.2, 1] },
};
```

### 38.5 prefers-reduced-motion

В глобальной CSS:

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

### 38.6 Применить к уже созданным компонентам

Ретрофит:
- Button hover — transition 150ms.
- Modal open — AnimatePresence + slideUp.
- Toast — slideUp.
- Dropdown/Popover — fadeIn с масштабом 0.98→1.

### 38.7 Preview

Обновить `/design-preview`:
- Секция «Motion»: триггеры для всех анимаций.

### 38.8 Commit + Serena + лог

### 38.9 Итог Этапа 05

- [ ] В `PIPELINE-НАВИГАТОР.md` Лог: «Этап 05 ЗАВЕРШЁН. Дизайн-система готова. Этапы 06-08 пишут UI поверх неё.»

---

## GATE-чекпоинт

- [ ] Motion tokens в коде.
- [ ] Правила в docs.
- [ ] Ретрофит на существующие компоненты применён.
- [ ] `prefers-reduced-motion` уважается.
- [ ] Preview с motion-демо.
- [ ] **Этап 05 ЗАВЕРШЁН.**

---

## Артефакт на выходе

Motion tokens + utils + reduced-motion respect + ретрофит компонентов.
