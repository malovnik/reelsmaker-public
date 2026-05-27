# ADR-0005 — Темизация (CSS variables + двухсторонний persist + flash-prevention)

- **Статус:** ACCEPTED
- **Дата:** 2026-04-24
- **Авторы:** R-DESIGN-ALCHEMIST, R-ARCHITECT
- **Связанные ADR:** [0001 Frontend Stack](./0001-frontend-stack.md), [0002 Data Storage](./0002-data-storage.md), [0003 Autosave](./0003-autosave.md)
- **Связанный чанк:** REFACTR-11 (Этап 01, шаг 12/67)
- **Реализация:** REFACTR-33 (палитры dark/light + токены + WCAG AA), REFACTR-37 (ThemeProvider + persist + flash-prevention)

---

## Контекст

`task.md §Goals` требует «dark default + light, persist». Текущее состояние (`apps/frontend/src/app/globals.css:11`):

```css
/* Инвариант: одна единственная тёмная тема, без light-mode switcher. */
```

Инвариант устарел — от него отказываемся в пользу двух тем. Но **не перепысываем токены с нуля** — они уже семантически правильные, просто живут в `:root` вместо `[data-theme="dark"]`.

**Инвентаризация существующей палитры** (24 токена, все в OKLCH):

| Группа | Токены |
| --- | --- |
| Surface (4) | `--ink`, `--ink-2`, `--ink-3`, `--ink-4` |
| Paper (2) | `--paper`, `--paper-dim` |
| Border (2) | `--line`, `--line-soft` |
| Mute (2) | `--mute`, `--mute-2` |
| Accent (4) | `--gold`, `--gold-dim`, `--ember`, `--focus` |
| Semantic aliases (11) | `--surface-canvas/raised/sunken/overlay`, `--border-subtle/default/strong`, `--text-primary/secondary/muted/disabled` |
| Interactive (4) | `--accent-primary/hover/subtle/on-primary` |
| Status (4) | `--success`, `--warning`, `--danger`, `--info` |
| Profile (5) | `--profile-talking-head/fashion/travel/screencast/custom` |
| Shadow (4) | `--shadow-xs/sm/md/lg` |
| Radius (3) | `--radius-s/-/-l` |

Основа готова. Задача ADR — формализовать переход от однотемного `:root` к `[data-theme]`-driven двум темам без ломания существующих компонентов.

---

## Движущие критерии решения

1. **Dark — default, инвариант.** Текущая OKLCH ink/paper/gold/ember палитра фиксируется как «canonical dark».
2. **Light — не просто инверсия.** R-DESIGN-ALCHEMIST: «dark ≠ invert of light». У light своя hierarchy (paper-first, ink-text, gold-accent-subtle).
3. **WCAG AA** — минимум 4.5:1 для body-text (L-delta ≥ 0.5 в OKLCH), 3:1 для non-text UI.
4. **Zero flash** — при загрузке страницы не должно быть вспышки чужой темы (FOUC). Inline script в `<head>` до React-монтирования.
5. **Persist двухсторонний** — localStorage (instant) + backend (cross-device / cross-browser). localStorage — источник правды для немедленного применения, backend — backup при первой загрузке в новом окружении.
6. **System-режим работает.** `prefers-color-scheme` media query. При смене OS-темы UI переключается без reload.
7. **Переключение без перерендера.** `documentElement.dataset.theme = "dark" | "light"` — CSS-переменные пересчитываются браузером, React-дерево не дёргается.
8. **Tailwind 4 дружественность.** Tailwind 4 нативно поддерживает `data-*` variant; не нужны JS-классы `class="dark"`.
9. **Не ломает существующие 100+ .tsx компонентов.** Семантические токены остаются те же — только их значения зависят от `[data-theme]`.

---

## Рассмотренные варианты

### Вариант A — JS-класс на `<html>` (`class="dark"`)

**FOR:**
- Классический Tailwind `dark:` variant.
- Примеры в документации Tailwind 3.

**AGAINST:**
- Tailwind 4 предпочитает `data-*` variants (новый синтаксис).
- `classList.add` vs `dataset.theme` — первое триггерит MutationObserver в некоторых devtools-утилитах, второе — data-атрибут, «легче».
- Только bool-состояние (dark/не-dark), нет места для `system` без дополнительного класса.

**VERDICT: ❌ REJECTED.**

---

### Вариант B — `data-theme` атрибут + CSS-variables scoping + localStorage + backend sync

**FOR:**
- `html[data-theme="dark"] { ... }` и `html[data-theme="light"] { ... }` — один source-of-truth в CSS.
- Три значения: `"dark" | "light" | "system"` (последний резолвится в `dark | light` через matchMedia).
- Instant persist через localStorage (inline script до hydration).
- Async sync с backend — eventual consistency, не блокирует UI.
- Нативная поддержка `data-*` variant в Tailwind 4.
- `color-scheme: dark | light` CSS-свойство устанавливается одновременно — корректируются scroll-bar, form-controls, system-UI.

**AGAINST:**
- +1 inline script в `<head>` (~20 строк JS). Анти-slop правило «no inline scripts» — но здесь технически оправдано (FOUC prevention, нельзя делать в React).

**VERDICT: ✅ ACCEPTED.**

---

### Вариант C — Только `prefers-color-scheme`, без ручного override

**FOR:**
- Zero config, уважает OS-setting.

**AGAINST:**
- **Нарушает требование** `task.md §Goals` — «dark default + light, persist». Пользователь должен иметь возможность override OS-setting.
- Нет persist между устройствами.
- Fashion/content-creator часто держат OS в light, но editor в dark — режиссура рабочего пространства.

**VERDICT: ❌ REJECTED.**

---

## Решение

Принимаем **Вариант B** — `html[data-theme]` + 3-значный selector (`dark | light | system`) + localStorage-first persist + async backend sync + inline flash-prevention script.

### Семантические токены (24 — два набора значений)

Токены остаются **теми же** (имена, состав), меняются только значения под `[data-theme="dark"]` vs `[data-theme="light"]`.

#### Backward-compat shim

Переносим из `:root` в `:root, html[data-theme="dark"]` — существующие компоненты работают без правок.

```css
:root,
html[data-theme="dark"] {
  color-scheme: dark;

  /* Surface hierarchy — глубокий ink (canonical) */
  --ink:    oklch(0.14 0.010 260);
  --ink-2:  oklch(0.17 0.012 260);
  --ink-3:  oklch(0.20 0.014 260);
  --ink-4:  oklch(0.24 0.016 260);
  --paper:      oklch(0.97 0.004 80);
  --paper-dim:  oklch(0.88 0.006 80);
  --white:  #ffffff;

  /* Borders */
  --line:       oklch(0.28 0.016 260);
  --line-soft:  oklch(0.22 0.014 260);

  /* Mute text */
  --mute:   oklch(0.58 0.012 260);
  --mute-2: oklch(0.72 0.012 260);

  /* Accents */
  --gold:      oklch(0.82 0.13 88);
  --gold-dim:  oklch(0.62 0.10 88);
  --ember:     oklch(0.70 0.18 40);
  --focus:     oklch(0.82 0.13 88);

  /* Semantic aliases */
  --surface-canvas:  var(--ink);
  --surface-raised:  var(--ink-2);
  --surface-sunken:  var(--ink-3);
  --surface-overlay: oklch(0.16 0.012 260 / 0.88);
  --border-subtle:   var(--line-soft);
  --border-default:  var(--line);
  --border-strong:   var(--paper);
  --text-primary:    var(--paper);
  --text-secondary:  var(--paper-dim);
  --text-muted:      var(--mute-2);
  --text-disabled:   var(--mute);

  /* Interactive */
  --accent-primary:       var(--paper);
  --accent-primary-hover: var(--white);
  --accent-primary-subtle: oklch(0.30 0.014 260);
  --accent-on-primary:    var(--ink);

  /* Status */
  --success: oklch(0.76 0.15 155);
  --warning: oklch(0.78 0.16 75);
  --danger:  oklch(0.70 0.20 25);
  --info:    oklch(0.78 0.14 225);

  /* Shadow — глубокие тёмные тени */
  --shadow-xs: 0 1px 2px rgba(0, 0, 0, 0.25);
  --shadow-sm: 0 2px 6px rgba(0, 0, 0, 0.35);
  --shadow-md: 0 8px 20px rgba(0, 0, 0, 0.45);
  --shadow-lg: 0 24px 48px rgba(0, 0, 0, 0.55);
}
```

#### Light-тема

Не просто инверсия L — новая иерархия: `paper` становится surface, `ink` — text, `gold` — сохраняется как accent, но с повышенной chroma (на светлом фоне золото читается лучше с chroma 0.15-0.18).

```css
html[data-theme="light"] {
  color-scheme: light;

  /* Surface: paper-first (светлые нейтральные) */
  --ink:    oklch(0.98 0.003 80);    /* почти белый с тёплым уклоном */
  --ink-2:  oklch(0.955 0.004 80);   /* surface-raised */
  --ink-3:  oklch(0.925 0.006 80);   /* surface-sunken */
  --ink-4:  oklch(0.89 0.008 80);    /* elevated */
  --paper:      oklch(0.20 0.012 260);    /* text-primary — глубокий ink */
  --paper-dim:  oklch(0.34 0.010 260);    /* text-secondary */
  --white:  #000000;                  /* inversion accent — на light это чёрный */

  /* Borders: делаем темнее на светлом фоне */
  --line:       oklch(0.84 0.008 80);
  --line-soft:  oklch(0.90 0.006 80);

  /* Mute */
  --mute:   oklch(0.56 0.010 260);
  --mute-2: oklch(0.42 0.012 260);

  /* Accents: gold с повышенной chroma */
  --gold:      oklch(0.68 0.16 80);   /* warm gold, темнее L для контраста с paper */
  --gold-dim:  oklch(0.78 0.12 80);
  --ember:     oklch(0.60 0.20 35);   /* ember тёмно-оранжевый */
  --focus:     oklch(0.55 0.22 250);  /* синий focus на light (WCAG 3:1 против paper) */

  /* Semantic aliases — та же семантика, разные значения */
  --surface-canvas:  var(--ink);
  --surface-raised:  var(--ink-2);
  --surface-sunken:  var(--ink-3);
  --surface-overlay: oklch(0.96 0.003 80 / 0.92);
  --border-subtle:   var(--line-soft);
  --border-default:  var(--line);
  --border-strong:   var(--paper);
  --text-primary:    var(--paper);
  --text-secondary:  var(--paper-dim);
  --text-muted:      var(--mute-2);
  --text-disabled:   var(--mute);

  --accent-primary:       var(--paper);
  --accent-primary-hover: var(--white);
  --accent-primary-subtle: oklch(0.95 0.006 80);
  --accent-on-primary:    var(--ink);

  --success: oklch(0.56 0.16 155);
  --warning: oklch(0.62 0.17 75);
  --danger:  oklch(0.55 0.22 25);
  --info:    oklch(0.55 0.18 225);

  /* Shadow — мягкие светлые тени (меньше opacity, бóльший blur) */
  --shadow-xs: 0 1px 2px rgba(20, 20, 40, 0.06);
  --shadow-sm: 0 2px 6px rgba(20, 20, 40, 0.08);
  --shadow-md: 0 8px 20px rgba(20, 20, 40, 0.10);
  --shadow-lg: 0 24px 48px rgba(20, 20, 40, 0.14);
}
```

#### WCAG AA проверка (L-delta)

| Токен | Dark | Light | Min L-delta для AA 4.5:1 |
| --- | --- | --- | --- |
| `--text-primary` on `--surface-canvas` | 0.97 on 0.14 = Δ0.83 | 0.20 on 0.98 = Δ0.78 | ≥0.50 ✅ |
| `--text-secondary` on `--surface-canvas` | 0.88 on 0.14 = Δ0.74 | 0.34 on 0.98 = Δ0.64 | ≥0.50 ✅ |
| `--text-muted` on `--surface-canvas` | 0.72 on 0.14 = Δ0.58 | 0.42 on 0.98 = Δ0.56 | ≥0.50 ✅ |
| `--accent-primary` on `--surface-canvas` | 0.97 on 0.14 = Δ0.83 | 0.20 on 0.98 = Δ0.78 | ≥0.50 ✅ |
| `--focus` (outline) | 0.82 gold on 0.14 ink | 0.55 blue on 0.98 paper | ≥0.30 для UI (3:1) ✅ |
| `--danger` text on surface | 0.70 on 0.14 = Δ0.56 | 0.55 on 0.98 = Δ0.43 ⚠ | 0.43 < 0.50 → увеличить C или L |

**Fix danger light:** `--danger: oklch(0.48 0.24 25);` — L=0.48 даёт Δ0.50 с paper=0.98. Реализовать в REFACTR-33.

Детальная WCAG-проверка всех 24 токенов формализуется в REFACTR-33 через `chroma-js` или `apca-w3` (рекомендуется **APCA** — новый WCAG 3 contrast model, в Chrome DevTools есть нативная поддержка).

### Persist-стратегия (двухсторонняя)

#### Источник правды: `localStorage.videomaker-theme`

Значения: `"dark" | "light" | "system"` (default `"system"` на первом старте — уважает OS).

#### Инициализация (до React hydration)

Встраивается в `index.html` (Vite SPA) между `<head>` и `<body>` первым inline script-ом:

```html
<script>
  (function() {
    try {
      var stored = localStorage.getItem('videomaker-theme') || 'system';
      var resolved = stored;
      if (stored === 'system') {
        resolved = matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
      }
      document.documentElement.dataset.theme = resolved;
      document.documentElement.style.colorScheme = resolved;
    } catch (e) {
      document.documentElement.dataset.theme = 'dark';
      document.documentElement.style.colorScheme = 'dark';
    }
  })();
</script>
```

**Почему в `<head>`:** CSS-variables резолвятся синхронно при parse-time. К моменту, когда браузер начинает красить первый элемент (FCP), `[data-theme]` уже стоит — flash невозможен.

**Почему inline (не отдельный .js):** external script блокирует render до загрузки + парсинга, добавляет RTT. Inline ≈ 400 bytes — дёшево.

**Почему try/catch:** `localStorage` может быть отключён (private browsing → SecurityError в старом Safari). Fallback на `"dark"`.

#### Backend sync (async, eventual consistency)

**GET** `/api/settings/device` (при первой загрузке приложения в новом браузере / после sign-out):

```http
GET /api/settings/device HTTP/1.1

HTTP/1.1 200 OK
{ "theme": "dark" }
```

Если localStorage пуст → записываем в localStorage значение с бэка, применяем к DOM. Если localStorage != backend → **localStorage выигрывает** (владелец только что переключил в этом браузере), бэк обновляется async.

**PUT** `/api/settings/device` (при смене темы в UI):

```http
PUT /api/settings/device HTTP/1.1
Content-Type: application/json

{ "theme": "light" }

HTTP/1.1 204 No Content
```

Неблокирующе (fire-and-forget с `queueMicrotask` + retry 3× с backoff 1s/3s/10s). Если backend down — toast «тема сохранена локально, синхронизация позже» (опционально, не MVP).

#### System-tracking

Если `videomaker-theme === "system"` — подписываемся на `matchMedia('(prefers-color-scheme: dark)').addEventListener('change', ...)` → автоматически перекидываем `data-theme` без reload.

### React-контракт: `<ThemeProvider>` + `useTheme()`

```tsx
// apps/frontend/src/providers/ThemeProvider.tsx

import { createContext, useContext, useEffect, useState } from 'react';
import { api } from '@/lib/api';

type ThemeValue = 'dark' | 'light' | 'system';
type ResolvedTheme = 'dark' | 'light';

interface ThemeContext {
  theme: ThemeValue;
  resolved: ResolvedTheme;
  setTheme: (next: ThemeValue) => void;
}

const Ctx = createContext<ThemeContext | null>(null);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<ThemeValue>(() => {
    try {
      return (localStorage.getItem('videomaker-theme') as ThemeValue) || 'system';
    } catch {
      return 'system';
    }
  });

  const [systemDark, setSystemDark] = useState(() =>
    matchMedia('(prefers-color-scheme: dark)').matches,
  );

  useEffect(() => {
    const mq = matchMedia('(prefers-color-scheme: dark)');
    const listener = (e: MediaQueryListEvent) => setSystemDark(e.matches);
    mq.addEventListener('change', listener);
    return () => mq.removeEventListener('change', listener);
  }, []);

  const resolved: ResolvedTheme = theme === 'system' ? (systemDark ? 'dark' : 'light') : theme;

  useEffect(() => {
    document.documentElement.dataset.theme = resolved;
    document.documentElement.style.colorScheme = resolved;
  }, [resolved]);

  const setTheme = (next: ThemeValue) => {
    setThemeState(next);
    try { localStorage.setItem('videomaker-theme', next); } catch {}
    void api.putDeviceSettings({ theme: next }).catch(() => {});
  };

  useEffect(() => {
    void api.getDeviceSettings().then((remote) => {
      const local = localStorage.getItem('videomaker-theme');
      if (local == null && remote.theme) {
        setThemeState(remote.theme);
        localStorage.setItem('videomaker-theme', remote.theme);
      }
    }).catch(() => {});
  }, []);

  return <Ctx.Provider value={{ theme, resolved, setTheme }}>{children}</Ctx.Provider>;
}

export function useTheme(): ThemeContext {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useTheme must be inside <ThemeProvider>');
  return ctx;
}
```

### Переключатель UI

`<ThemeToggle />` в TopBar справа (рядом с `<SaveStatusBadge />` из ADR-0003):

- `<DropdownMenu>` с 3 опциями: «Система» / «Тёмная» / «Светлая».
- Иконка зависит от `resolved`: moon (dark) / sun (light).
- Клавиатура: `Cmd+Shift+L` (toggle dark↔light), `Cmd+Shift+T` (system).

### API-контракт backend

#### `GET /api/settings/device`

```http
HTTP/1.1 200 OK
{ "theme": "dark" }
```

Источник: `device_settings` — таблица или таблица-синглтон (REFACTR-56). Единственная запись на инсталляцию (single-user локалка, не per-user).

#### `PUT /api/settings/device`

```http
PUT /api/settings/device HTTP/1.1
Content-Type: application/json
{ "theme": "light" }

HTTP/1.1 204 No Content
```

Валидация: `theme in ["dark", "light", "system"]`, иначе 422.

**Расположение в схеме:** отдельная маленькая таблица `device_settings` (1 row, PK = `"default"`), НЕ в `projects.settings_snapshot` — тема глобальна для инсталляции, не per-project.

```python
class DeviceSettings(Base):
    id: Mapped[str] = mapped_column(primary_key=True, default="default")
    theme: Mapped[str] = mapped_column(default="system")  # "dark" | "light" | "system"
    ui_mode: Mapped[str] = mapped_column(default="simple")  # Simple/Expert (REFACTR-56)
    updated_at: Mapped[datetime]
```

Используется в REFACTR-56 (добавятся `ui_mode`, `hotkeys_enabled`).

### Tailwind 4 integration

`tailwind.config.ts` (Vite + Tailwind 4):

```ts
export default {
  darkMode: ['selector', 'html[data-theme="dark"]'],
  // Tailwind 4 @theme директивы указывают на CSS-variables
};
```

В CSS:

```css
@theme {
  --color-bg: var(--surface-canvas);
  --color-text: var(--text-primary);
  --color-accent: var(--accent-primary);
  --color-border: var(--border-default);
  /* ... */
}
```

Компоненты используют Tailwind-классы: `bg-bg`, `text-text`, `border-border`. Значения классов автоматически берутся из CSS-переменных. Переключение `[data-theme]` → новые значения → новый рендер без пересборки.

---

## Последствия

### Положительные

1. **Dark + light + system** — полное требование `task.md §Goals` закрыто.
2. **Zero FOUC** — inline script в `<head>` решает flash навсегда.
3. **Не ломает существующие 100+ .tsx** — токены те же, просто scoped под `[data-theme]`.
4. **Cross-browser persist** — backend sync подтягивает предпочтение при открытии в новом браузере.
5. **System-режим работает live** — OS меняет тему → UI меняется без reload.
6. **WCAG AA gate** — все body-text токены ≥4.5:1, UI-tokens ≥3:1. Danger light требует fix L=0.48.
7. **CSS-variables → O(1) переключение** — нет перерендера React, браузер пересчитывает только значения.
8. **OKLCH палитра** — перцептуально линейна, удобна для алгоритмического сдвига тонов (REFACTR-33 будет использовать `chroma-js oklch`).

### Отрицательные

1. **+ одна таблица** `device_settings` (1 row). Тривиально.
2. **+ один inline script** ~400 bytes в `<head>`. Оправдано (FOUC prevention).
3. **Light-тема требует ревизии 13 компонентов** с hardcoded `bg-red-50 text-red-900` (из `docs/audit/06-ux-pains.md` pain #2) — они читают light-scale Tailwind цвета, на light-теме получат нечитаемый дубль. Решается в REFACTR-33.

### Нейтральные

- **APCA vs WCAG 2** — рекомендуем APCA (новая модель, ближе к восприятию), но fallback на WCAG 2 AA достаточен для MVP.
- **High-contrast mode** (`prefers-contrast: more`) — отложено до REFACTR-56 (accessibility-опции).

---

## Верификация

Gate-критерии (REFACTR-33 + REFACTR-37):

1. `localStorage.getItem('videomaker-theme')` возвращает `"dark" | "light" | "system"`.
2. На первой загрузке без localStorage — `[data-theme]` = OS prefers-color-scheme (`dark` в 90% случаев на macOS).
3. Toggle UI: клик по `<ThemeToggle />` → `[data-theme]` меняется мгновенно, React-дерево не перемонтируется (React DevTools Profiler < 16 ms).
4. **Zero FOUC:** hard refresh (Cmd+Shift+R), замедление CPU throttling 6×, записать Performance — не должно быть frame-а со светлым фоном до dark. Проверяется в Chrome DevTools Performance tab.
5. System-change: в macOS System Settings переключить Appearance — `[data-theme]` меняется без reload (если `localStorage.videomaker-theme === "system"`).
6. Cross-tab: вкладка A → toggle light. `storage` event → вкладка B тоже переключается. (REFACTR-37 listener на `window.addEventListener('storage', ...)`).
7. Backend sync: `curl GET /api/settings/device` возвращает текущую тему. `curl PUT` с невалидным значением → 422.
8. Backend down при PUT → toast «сохранено локально, синхронизация позже»; retry с backoff успешен при восстановлении.
9. WCAG AA: все 24 токена dark + light — contrast ratio ≥4.5 (text) / ≥3 (UI). Через `pnpm test:contrast` (скрипт в REFACTR-33, использует `apca-w3`).
10. Компоненты без hardcoded цветов: `grep -rn "bg-\(white\|black\|red-[0-9]\+0\|stone\|zinc\|slate\|neutral\|gray\)" apps/frontend/src` → 0 matches после REFACTR-33.

---

## Открытые вопросы

1. **Tailwind 4 dark: syntax** — `darkMode: ['selector', 'html[data-theme="dark"]']` или нативный `data-theme="dark":` variant? Ответ: решится в REFACTR-33 на основе Tailwind 4 final docs (RC на момент ADR).
2. **ThemeToggle в TopBar vs Settings** — дублировать или только в одном месте? Ответ: **оба** — быстрый toggle в TopBar (power-user) + полный selector в `/settings/device` (REFACTR-56).
3. **Per-project override** — проект может иметь свою тему? Ответ: **нет** в MVP. Тема device-global, не project-global. Если появится боль (например, «screencast-проекты в light») — отдельный ADR.
4. **Профильные цвета** (`--profile-*`) — меняются между темами? Ответ: **да**, но subtle. Dark: high-chroma OKLCH; light: та же hue, пониженная chroma, повышенная L. Детали в REFACTR-33.

---

## Ссылки

- OKLCH perceptual color model: https://oklch.com
- APCA contrast: https://apcacontrast.com (новый WCAG 3 candidate)
- Tailwind 4 `data-*` variants: https://tailwindcss.com/docs/dark-mode
- `matchMedia` prefers-color-scheme: https://developer.mozilla.org/docs/Web/CSS/@media/prefers-color-scheme
- Vite Flash-prevention pattern: https://vite.dev (шаблон inline script в `index.html`)
- `apps/frontend/src/app/globals.css:1-418` — текущая палитра (dark only, переезжает в `[data-theme="dark"]` scope)
- `docs/audit/06-ux-pains.md` pain #2 — 13 компонентов с hardcoded light-scale → REFACTR-33 очищает
- ADR-0002 `DeviceSettings` table — 1 row, PK `"default"`, поле `theme`
- ADR-0003 `<SaveStatusBadge />` в TopBar — `<ThemeToggle />` рядом
- `task.md §Goals` — «dark default + light, persist»
- `task.md §6.2 REFACTR-33` — палитры + токены + WCAG AA
- `task.md §6.6 REFACTR-37` — ThemeProvider + flash-prevention
- `task.md §9.6 REFACTR-56` — Settings/Device UI + Simple/Expert + hotkeys
