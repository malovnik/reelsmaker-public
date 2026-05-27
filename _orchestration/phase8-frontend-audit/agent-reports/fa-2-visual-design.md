# FA-2 — Аудит визуального дизайна (Reelibra frontend)

Область: `apps/frontend/src` + `globals.css` + `index.html`.
Стек: React 19 + Vite + Tailwind 4. Шрифты: Inter Variable / Geist Variable / JetBrains Mono (self-hosted через `@fontsource-variable`).
Дизайн-система: "Refined Cinema Dark" (Phase 10, 2026-04-28). Dark-only.

---

## Вердикт: generic vs характерный

**Характерный, верхние 10–15% AI-генерируемых фронтов.** Это НЕ slop. Признаки авторского вкуса:

- Полноценная токен-система на **OKLCH** (а не дефолтный slate/zinc Tailwind), единый warm-indigo hue 280 для поверхностей + одна сатурированная gold-amber акцентная точка (hue 75). Дисциплина "один акцент".
- Кинематографические детали с замыслом: radial-gradient vignette на фоне (`body`), SVG-grain overlay (opacity 0.025, mix-blend overlay), inner-highlight на карточках (`inset 0 1px 0 oklch(1 0 0 / .04)`), warm-tinted тени `rgba(20,16,12,...)` вместо чёрных.
- Семантическая типографика: display (Geist) для чисел/заголовков с `tnum`, mono (JetBrains) для service-caps/кодов навигации (DSH/PRJ/SCH), sans (Inter) для тела. Шкала через `clamp()`.
- Копирайтинг без клише: приветствие дашборда "Ночь — а ты ещё режешь" вместо банкоматного "Доброй ночи" — в коде явный комментарий-намерение против generic.
- Системные утилиты-обёртки: `.page-shell` с прогрессивным padding-scale под sticky NavRail, `.surface-card/.stamp/.divider/.score-ring` — переиспользуемый словарь.

Что тянет к generic (мелочи): toggle-switch (`h-6 w-11` pill + белый круг) — стандартный shadcn-силуэт; ring-2 ring-offset на выбранной карточке — дефолтный Tailwind-паттерн. Не критично.

---

## Состояние дизайн-системы (токены)

Зрелая. CSS custom properties в `:root`: surface hierarchy (`--ink`..`--ink-4`), text tiers (`--paper/--paper-dim/--mute/--mute-2`), borders (`--line/--line-soft`), акценты + семантические алиасы (`--text-primary`, `--accent-primary`, `--success/--warning/--danger/--info`), profile-accents, тени, radii (8/12/18/24). Компоненты ссылаются через `text-[color:var(--...)]` / `bg-[color:var(--...)]` — консистентно по всей базе (121 компонент).

Минусы: **два параллельных словаря токенов** — сырые (`--paper`, `--mute-2`, `--gold`) и семантические алиасы (`--text-primary`, `--text-muted`, `--accent-primary`). Компоненты используют то одно, то другое (NavRail → `--paper/--mute-2/--gold`; SwitchRow/ReelCard → `--text-primary/--accent-primary`). Работает, но повышает порог входа и риск дрейфа.

---

## Топ-10 проблем

| ID | Sev | Где | Проблема | Рекомендация |
|----|-----|-----|----------|--------------|
| **VD-01** | High | `index.html:10` + `AppShell.tsx:36` | Grain-overlay рендерится **дважды**: `<body class="grain">` и `<div className="grain">`. Оба `position:fixed; inset:0; z-index:100`. Двойной шум + два full-viewport mix-blend слоя = лишний repaint и удвоенная плотность зерна. | Убрать один. Оставить только `index.html` (грузится раньше, без FOUC) либо только AppShell. |
| **VD-02** | High | `job/ReelGrid.tsx:275` | Галерея рилсов максимум `sm:grid-cols-2` — на десктопе 1400px+ всего 2 колонки 9:16, огромные пустые поля по бокам. Главный экран продукта (нарезки) недоиспользует ширину. | `sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5`. |
| **VD-03** | High | `ReelCard.tsx:237,289,340`, `dashboard/JobCard.tsx`, `ProfileSelector.tsx` | Действия (like/dislike, delete, select) скрыты за `opacity-0 group-hover:opacity-100`. На тач-устройствах hover отсутствует → кнопки **недоступны** на мобайле/планшете. `group-focus-within` спасает только при клавиатуре. | На `<lg` показывать действия всегда (`opacity-100 lg:opacity-0 lg:group-hover:opacity-100`) или вынести в видимую панель. |
| **VD-04** | Med | `projects/ProjectFormModal.tsx:89-93` | Модалка `fixed inset-0 flex items-center justify-center p-4` без `max-h`/`overflow-y-auto` на контейнере. Высокая форма на коротком экране (мобайл landscape) обрежется, нет скролла. | Добавить `max-h-[90dvh] overflow-y-auto` на панель, проверить остальные модалки (CaptionPresetFormModal и др.). |
| **VD-05** | Med | вся база | Массовое использование микро-текста: **162×** `text-[11px]`, **107×** `text-[10px]`. Многие — не бейджи, а вторичный контент (метаданные карточек, подписи). На мобайле и для целевой аудитории (предприниматели, не разработчики) 10px нечитаемо; противоречит заявленной в шапке `globals.css` цели "комфорт чтения, 17px база". | Поднять вторичный текст до 12–13px; 10–11px оставить только `.mono`-caps/`.stamp`/`.micro`. |
| **VD-06** | Med | `globals.css:23-123` | Дублирующиеся токен-словари (сырой `--paper/--mute-2/--gold` vs семантический `--text-*/--accent-*`), компоненты миксуют оба. Нет single source of truth. | Зафиксировать семантический слой как канон, сырые токены — только как его сырьё; постепенно мигрировать прямые ссылки. |
| **VD-07** | Med | `ReelCard.tsx:113`, `113 px[11px]` + comment text | Контраст: `--mute` = `oklch(0.66 0.012 280)` на `--ink-2` (`oklch 0.185`) для текста 11px (comment рилса) — близко к нижней границе WCAG AA для мелкого шрифта. `--mute` объявлен как самый тёмный тир. | Для контента (не decorative) использовать `--mute-2`/`--text-secondary`; `--mute` оставить декоративным меткам крупнее/жирнее. |
| **VD-08** | Low | `NavRail.tsx:62` / `globals.css:591-611` | NavRail desktop ширина `232px` зашита в Tailwind-классе `lg:w-[232px]`, а `.page-shell` padding-логика ("рядом NavRail 232px") описана отдельно в CSS-комментарии. Магическое число живёт в двух местах без связи. | Вынести в токен `--nav-rail-w` и использовать в обоих местах. |
| **VD-09** | Low | `globals.css` | Заявлен `color-scheme: dark` — light-темы нет вовсе. Если это сознательное решение (cinema dark) — ок. Но нет даже `prefers-color-scheme` fallback-намёка; пользователи в светлом окружении получат только тёмный. | Подтвердить, что dark-only — продуктовое решение. Если да — оставить, не gold-plate'ить вторую тему. |
| **VD-10** | Low | `BrandKitClient.tsx`, `ProjectFormModal.tsx:12`, `ProjectsList.tsx:11` | Hardcoded hex дефолты бренд-цветов (`#6366f1` Tailwind-indigo, `#b79b5b`, `#2f2b26`). `#6366f1` — дефолтный indigo-500, выбивается из warm-gold палитры системы как fallback-цвет проектов. | Заменить fallback на токен `--gold-dim` или нейтраль из палитры, чтобы дефолтные проекты не выглядели "чужими". |

(Hardcoded hex в `WaveformBar`, `ReelCard` score-ramp `#4ade80`→`#f87171`, canvas `#fff/#000` — легитимны: canvas fillStyle и data-viz градиент. Не правка.)

---

## Типографика, иерархия, ритм, spacing

- **Иерархия — сильная.** `.page-h1` clamp(1.75→2.5rem), DashboardHero clamp(2→4rem) с `text-wrap:balance`, метрики display+tnum. Mono-caps (`.micro`, `.divider`, `.stamp`) дают чёткий второй регистр для служебных меток. Letter-spacing продуман (display −0.022em, caps +0.08em).
- **Ритм** опирается на стандартную Tailwind-шкалу spacing + кастомный `.page-shell`. Консистентно.
- **Проблема ритма** — VD-05: переизбыток 10–11px ломает заявленную "17px-комфорт" философию.

## Цвет / контраст

- Палитра OKLCH когерентна, один акцент, теплая. Семантические статусы заданы.
- Контраст в основном хорош (`--paper` 0.97 на `--ink` 0.155). Риск — VD-07 (`--mute` на мелком тексте).
- Dark-only (VD-09).

## Мобильный / адаптив

**Реально отзывчив, не декоративно.** NavRail — полноценный drawer-паттерн: `translate-x-full` → `translate-x-0`, затемнение `bg-black/60 backdrop-blur`, закрытие по route-change/Esc/overlay-клику, burger в TopBar `lg:hidden`. Брейкпойнты осмысленные (sm 33×, md 15×, lg 29×). `.page-shell` прогрессивно масштабирует padding 640→1920px. Crumbs скроллятся горизонтально.

Проблемы адаптива: **VD-03 (hover-only действия недоступны на тач)** — самая серьёзная; VD-04 (модалка без скролла); VD-02 (не масштабируется вверх); VD-05 (мелкий текст на мобайле). Touch-таргеты иконок-кнопок в основном `size-9` (36px) — приемлемо, чуть ниже рекомендованных 44px.

## Что НЕ стыдно сохранить

- Всю OKLCH токен-систему и философию "один warm-gold акцент".
- Кинематографические слои (vignette, warm shadows, inner-highlight, score-ring conic-gradient) — это и есть характер.
- Mono-caps навигационные коды + `.stamp/.divider/.micro` словарь.
- Drawer-навигацию (образцовая реализация).
- Self-hosted variable-шрифты + `font-feature-settings` (ss01/cv11/tnum/zero).
- Анти-slop копирайтинг (greeting по времени суток).
- Focus-ring и `prefers-reduced-motion` — accessibility основа на месте.
