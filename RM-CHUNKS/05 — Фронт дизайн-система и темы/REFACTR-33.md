# REFACTR-33 — Палитры: dark (основная) + light, токены

> **Этап:** 05
> **Шаг:** 34 из 67
> **Зависимости:** REFACTR-32 (manifest), REFACTR-11 (ADR theming).
> **Следующий шаг:** REFACTR-34 (Типографика)

**ОБЯЗАТЕЛЬНО:** `frontend-design` skill активен.

---

## Роли

### R-DESIGN-ALCHEMIST
**Soul:** Палитра — не список hex. Это система. Токены связаны друг с другом, контраст рассчитан, accent — выбран.

---

## ТРИЗ-принцип

*Принцип асимметрии.* Dark — основная, проработана до последнего оттенка. Light — корректная альтернатива, но не её копия «инвертированная». Асимметричное внимание.

---

## Оркестрация

**Режим:** Sequential + `frontend-design` Phase 2 «Color must pop».

---

## Микрозадачи

### 33.1 Выбор accent-цвета

Владелец назвал референсы YouTube/Instagram. Варианты accent:
- Красный YouTube (`#FF0000`) — но это слишком прямая референция, украдено.
- Электрик-синий (Instagram blue `#5851DB` или `#405DE6`) — то же.
- Свой выбор: **кислотно-зелёный `#9BFF00`** (киноплёнка, «rec»-маркер), или **янтарный `#FFB020`** (warmth + энергия), или **электрик-фиолетовый `#A855F7`** (медиа-app 2026).

Провести Sequential Thinking (FOR/AGAINST) по трём кандидатам. Критерий выбора:
- Контраст с dark background: AAA по WCAG.
- Индивидуальность (не украли у YouTube/Instagram).
- Узнаваемость на видео-миниатюрах (не сливается с контентом).

**Записать выбор в manifest.** Для дальнейших чанков — фикс.

### 33.2 Dark палитра — semantic tokens

`src/design/tokens/colors.ts`:

```ts
export const darkTokens = {
  // Backgrounds
  bgPrimary: '#0B0B0D',        // глубокий, но не чистый чёрный
  bgSecondary: '#141418',
  bgTertiary: '#1C1C22',
  bgElevated: '#22222A',       // cards, modals
  bgHover: '#2A2A33',
  
  // Text
  textPrimary: '#F5F5F7',
  textSecondary: '#B0B0BA',
  textMuted: '#70707A',
  textOnAccent: '#0B0B0D',     // на кислотно-зелёном — чёрный
  
  // Borders
  borderSubtle: 'rgba(255, 255, 255, 0.06)',
  borderDefault: 'rgba(255, 255, 255, 0.1)',
  borderStrong: 'rgba(255, 255, 255, 0.18)',
  
  // Accent (пример — кислотно-зелёный)
  accentPrimary: '#9BFF00',
  accentHover: '#AFFF33',
  accentMuted: 'rgba(155, 255, 0, 0.14)',
  
  // Semantic
  success: '#34D399',
  warning: '#FBBF24',
  danger: '#F87171',
  info: '#60A5FA',
  
  // Shadows (dark-adapted)
  shadowSm: '0 1px 2px rgba(0, 0, 0, 0.4)',
  shadowMd: '0 4px 12px rgba(0, 0, 0, 0.5)',
  shadowLg: '0 12px 40px rgba(0, 0, 0, 0.6)',
  
  // Overlays
  overlayBackdrop: 'rgba(0, 0, 0, 0.6)',
};
```

### 33.3 Light палитра

```ts
export const lightTokens = {
  bgPrimary: '#FAFAFB',
  bgSecondary: '#F3F3F5',
  bgTertiary: '#E8E8ED',
  bgElevated: '#FFFFFF',
  bgHover: '#EEEEF1',
  
  textPrimary: '#0B0B0D',
  textSecondary: '#4A4A54',
  textMuted: '#7A7A85',
  textOnAccent: '#0B0B0D',
  
  borderSubtle: 'rgba(0, 0, 0, 0.06)',
  borderDefault: 'rgba(0, 0, 0, 0.1)',
  borderStrong: 'rgba(0, 0, 0, 0.18)',
  
  accentPrimary: '#4AD400',    // чуть приглушённый вариант того же accent
  accentHover: '#5BE515',
  accentMuted: 'rgba(74, 212, 0, 0.14)',
  
  success: '#059669',
  warning: '#D97706',
  danger: '#DC2626',
  info: '#2563EB',
  
  shadowSm: '0 1px 2px rgba(10, 10, 15, 0.06)',
  shadowMd: '0 4px 12px rgba(10, 10, 15, 0.1)',
  shadowLg: '0 12px 40px rgba(10, 10, 15, 0.18)',
  
  overlayBackdrop: 'rgba(20, 20, 28, 0.4)',
};
```

### 33.4 CSS variables

`src/design/themes.css`:

```css
:root[data-theme="dark"] {
  --bg-primary: #0B0B0D;
  --bg-secondary: #141418;
  /* ... вся dark палитра ... */
}

:root[data-theme="light"] {
  --bg-primary: #FAFAFB;
  /* ... вся light палитра ... */
}
```

### 33.5 Tailwind 4 интеграция

В Tailwind 4 CSS variables сразу используются в arbitrary values:

```html
<div class="bg-[var(--bg-primary)] text-[var(--text-primary)]">
```

Альтернатива: настроить Tailwind theme через `@theme` директиву (Tailwind 4 syntax):

```css
@theme {
  --color-bg-primary: var(--bg-primary);
  --color-bg-secondary: var(--bg-secondary);
  /* ... */
}
```

→ позволяет использовать `bg-bg-primary` в Tailwind-классах.

### 33.6 Contrast check

- [ ] Text на каждом bg: проверить WCAG AA (4.5:1 для текста, 3:1 для крупного/UI).
- [ ] Accent на bg-primary: проверить AAA (7:1 для CTA).
- [ ] Автоматизировать через `tailwind-contrast-checker` или ручные проверки в Figma.

### 33.7 Demo route

Создать `/design-preview` route для живого просмотра всех токенов (swatch-стенд + типичные компоненты).

### 33.8 Commit + Serena

---

## GATE-чекпоинт

- [ ] Accent-цвет выбран и зафиксирован в manifest.
- [ ] Dark tokens: минимум 20 переменных.
- [ ] Light tokens: минимум 20 переменных.
- [ ] CSS themes.css подключены.
- [ ] Tailwind интеграция работает.
- [ ] Contrast WCAG AA пройден на всех комбинациях.
- [ ] `/design-preview` показывает палитру.

---

## Артефакт на выходе

`src/design/tokens/colors.ts` + `src/design/themes.css` + Tailwind theme bridge + preview route.
