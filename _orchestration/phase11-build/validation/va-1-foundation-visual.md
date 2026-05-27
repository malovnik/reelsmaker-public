# VA-1 — Design Foundation Validation (色の道)

Валидатор: Design Foundation Validator. Дата: 2026-05-27.
Вход: брендбук 02-color-palette / 10-website-style + спека d1-design-system.
Код: `apps/frontend/src/globals.css`, `src/lib/fonts.ts`, `src/components/ui/*`.

## Итог: PASS с 2 минорными регрессиями (Tooltip box-shadow, Modal OKLCH overlay)

Build: PASS (`✓ built in 988ms`, 0 ошибок). Фундамент верен брендбуку, единый слой токенов, прямые углы, тач ≥44px, a11y на месте. Две точечные дырки в покрытии «ни одного хардкода мимо токена».

---

## 1. Токены globals.css — PASS

- Физический слой 1 = палитра брендбука 1:1: `--kuro #0A0A0A`, `--sumi #1A1A1A`, `--hai #2A2A2A`, `--kinzoku #C9A84C`, `--do #B87333`, `--kogane #E8C547`, `--shiroi #F0E6D2`, `--kasumi #8A8278`, `--chi #8B2500`. Все 9 цветов совпадают с HEX брендбука.
- Семантические имена СОХРАНЕНЫ (не переименованы): `--text-primary/--surface-raised/--accent-primary/--border-default` и т.д. перенаправлены на палитру, JSX 89 файлов не ломается. Дополнительный новый словарь (`--bg/--surface/--accent/--copper`) проброшен в `@theme inline` → утилиты `bg-surface/text-accent/border-line`.
- Производные прозрачности (`--accent-soft/--accent-line/--grid-line/--danger-soft`) совпадают со спекой §1.2.
- Хардкод-hex в globals.css — все легитимны: либо raw-палитра брендбука (слой 1), либо обоснованные межслойные оттенки (`--paper-dim #D8CCB6`, `--line-soft #222222`, `--mute-2 #A39C90`, `--success #7E9B5A` — приглушённый зелёный «в тон»). Мимо палитры ничего не утекло.

## 2. border-radius:0 + box-shadow — PASS с 1 регрессией

- radius обнулены полностью: `@theme { --radius-xs..4xl: 0 }` + `:root { --radius-s/--radius/--radius-l/--radius-xl: 0 }`. Все `rounded-*` → no-op. В ui/* массово используется `rounded-none` (явно, не нарушение).
- Тени отключены: `--shadow-xs..lg: none`, `--shadow-gold` заменён на `0 0 0 1px var(--accent-line)` (свечение через линию, не тень). Глубина — слои Sumi-поверх-Kuro + 1px-бордеры.
- РЕГРЕССИЯ (минор): `Tooltip.tsx:161` — хардкод `shadow-[0_8px_24px_rgba(0,0,0,0.55)]` на floating-карточке. Прямое нарушение запрета box-shadow. Floating-tooltip единственный кандидат на исключение (отрыв от потока), но по букве спеки §1.4 — нарушение. Глубину дать `border` + `--surface-overlay`/`--accent-line`, либо явно задокументировать исключение.

## 3. Шрифты — PASS

- `fonts.ts` грузит все 4 через @fontsource: Noto Serif JP (400/700 + cyrillic), Manrope variable, JetBrains Mono variable, Press Start 2P (400 + cyrillic). Кириллица покрыта.
- Маппинг в globals.css: `--font-display`→Noto Serif JP, `--font-body`→Manrope, `--font-mono`→JetBrains Mono, `--font-pixel`→Press Start 2P. Проброшены в `@theme` (`font-display/body/mono/pixel`). Алиасы `--font-sans/--font-serif` сохранены для legacy.

## 4. Примитивы ui/* — PASS

- Цвета через `var(--*)` / семантические утилиты во всех 15 компонентах. Хардкод-hex не найден (grep чист, кроме комментариев).
- Прямые углы: `rounded-none` везде.
- Тач ≥44px: Button `min-h-11/min-h-12` (44/48px) на всех размерах; icon-кнопки Tooltip/Modal `size-11` (44px). Toast close — `size-8` (32px), допустимо как вторичный dismiss, но строго <44 (минорное замечание, не блокер).
- a11y: focus-visible outline (`outline-2 outline-[var(--gold)]`) на интерактиве; Tooltip — `role=tooltip`, `aria-describedby`, `aria-expanded`, Esc-закрытие, мультимодальность мышь/клавиатура/тач.

## 5. Tooltip — механизм 100%-покрытия — PASS

- `TooltipProps` делает `what` / `effect` / `advise` ОБЯЗАТЕЛЬНЫМИ (не optional). Компилятор заставляет заполнить все 3 слоя подсказки на каждом использовании — типобезопасное 100%-покрытие. badge/inline/side опциональны. Авто-флип позиции + coarse-pointer (тач) рендерит блоком под контролом.

## 6. Грубые регрессии — PASS с 1 регрессией

- indigo / stone-* / gold-[N] / generic-эстетика — НЕ найдено. OKLCH из старой системы вычищен из токенов (упоминается только в комментарии-истории globals.css).
- РЕГРЕССИЯ (минор): `Modal.tsx:115` — overlay `bg-[oklch(0.10_0_0/0.7)]` — единственный остаток OKLCH в рантайм-коде. Есть готовый токен `--surface-overlay: rgb(10 10 10 / 0.92)` — следует использовать его (или новый `--overlay`), а не сырой oklch мимо палитры.

---

## Найденные хардкоды/регрессии (сводка)

| # | Файл:строка | Проблема | Тяжесть |
|---|---|---|---|
| 1 | Tooltip.tsx:161 | `shadow-[0_8px_24px_rgba(0,0,0,0.55)]` — box-shadow при запрете теней | минор |
| 2 | Modal.tsx:115 | `bg-[oklch(0.10_0_0/0.7)]` — сырой OKLCH мимо токена `--surface-overlay` | минор |
| 3 | Toast.tsx:117 | close `size-8` (32px) < 44px тач-таргета | косметика |

Build: PASS. Фундамент корректен; рекомендую закрыть #1 и #2 перед финалом (оба — точечный hardcode мимо токена, противоречат принципу системы).
