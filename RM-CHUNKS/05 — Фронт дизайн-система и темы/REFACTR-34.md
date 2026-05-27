# REFACTR-34 — Типографика и spacing scale

> **Этап:** 05
> **Шаг:** 35 из 67
> **Зависимости:** REFACTR-33 (палитры).
> **Следующий шаг:** REFACTR-35 (Атомы)

**ОБЯЗАТЕЛЬНО:** `frontend-design` skill активен.

---

## Роли

### R-DESIGN-ALCHEMIST
**Soul:** Типографика — 60% воспринимаемого качества UI. Шрифты не случайные, scale математический, weight-ы осмысленные.

---

## ТРИЗ-принцип

*Принцип гармонии.* Шкалы (typo, spacing, radius) связаны модульным коэффициентом (1.2x — minor third). Это даёт визуальную гармонию без «на глаз».

---

## Оркестрация

**Режим:** Sequential.

---

## Микрозадачи

### 34.1 Шрифты

- **Основной sans-serif:** Inter Variable (веса 100-700, opsz поддержка).
- **Monospace (для кодов, IDs, таймкодов):** JetBrains Mono Variable или SF Mono-alternative (Geist Mono).

Self-host через `@fontsource-variable/inter` + `@fontsource-variable/jetbrains-mono` (из npm) — никакого Google Fonts CDN.

### 34.2 Type scale

Модульная шкала 1.2× от base 14 px:

| Token | Size | Line-height | Weight | Usage |
|-------|------|-------------|--------|-------|
| `text-xs` | 11 px | 14 px | 500 | микро-лейблы |
| `text-sm` | 13 px | 18 px | 400 | вторичный текст |
| `text-base` | 14 px | 20 px | 400 | body |
| `text-md` | 15 px | 22 px | 500 | акцентированный body |
| `text-lg` | 18 px | 26 px | 600 | section title |
| `text-xl` | 22 px | 30 px | 600 | page subtitle |
| `text-2xl` | 28 px | 36 px | 600 | page title |
| `text-3xl` | 36 px | 44 px | 700 | hero |
| `text-4xl` | 48 px | 56 px | 700 | hero big |

Monospace идёт своей параллельной шкалой с теми же размерами.

### 34.3 Weights и стили

- 400 Regular — body.
- 500 Medium — лейблы, акценты.
- 600 Semibold — заголовки.
- 700 Bold — hero.

Italic — **не используем** в UI (только цитаты в документации).

### 34.4 Spacing scale

Base 4 px, шкала 4-based:

```
0 → 0
0.5 → 2px
1 → 4px
2 → 8px
3 → 12px
4 → 16px
5 → 20px
6 → 24px
8 → 32px
10 → 40px
12 → 48px
16 → 64px
20 → 80px
24 → 96px
```

Tailwind по умолчанию 4-based, значит ничего не переопределяем.

### 34.5 Radius

```
radius-xs → 4px
radius-sm → 6px
radius-md → 8px
radius-lg → 12px
radius-xl → 16px
radius-full → 9999px
```

Правило: dense UI (buttons, inputs) — md-lg. Карточки — md. Модалки — lg-xl. Нет «bubble» (не 24px+).

### 34.6 Конфиг в коде

`src/design/tokens/typography.ts`:
```ts
export const typography = {
  sizes: { xs: '11px', sm: '13px', ... },
  lineHeights: { xs: '14px', ... },
  weights: { regular: 400, medium: 500, semibold: 600, bold: 700 },
  fontFamily: {
    sans: '"Inter Variable", system-ui, sans-serif',
    mono: '"JetBrains Mono Variable", ui-monospace, monospace',
  },
};

export const spacing = { /* ... */ };
export const radius = { /* ... */ };
```

### 34.7 Tailwind theme

Через Tailwind 4 `@theme`:
```css
@theme {
  --font-sans: "Inter Variable", ...;
  --font-mono: "JetBrains Mono Variable", ...;
  --text-xs: 11px; --text-xs--line-height: 14px;
  /* ... */
}
```

### 34.8 Подключить шрифты

`src/main.tsx` (или index.css):
```ts
import '@fontsource-variable/inter';
import '@fontsource-variable/jetbrains-mono';
```

В `styles.css`:
```css
body {
  font-family: var(--font-sans);
  font-feature-settings: "cv01", "cv11", "ss03"; /* Inter stylistic sets */
}
```

### 34.9 Demo

Обновить `/design-preview`:
- Все text-size + weight комбинации.
- Mono-версия.
- Spacing scale визуально.
- Radius scale.

### 34.10 Commit + Serena

---

## GATE-чекпоинт

- [ ] Inter Variable + JetBrains Mono self-hosted, не через CDN.
- [ ] Type scale 9 размеров в токенах + Tailwind.
- [ ] Spacing и radius описаны.
- [ ] `/design-preview` показывает всю типографику.
- [ ] В коде только токены, нет raw `16px`/`20px` в компонентах.

---

## Артефакт на выходе

`src/design/tokens/typography.ts` + подключение шрифтов + Tailwind bridge + обновлённый preview.
