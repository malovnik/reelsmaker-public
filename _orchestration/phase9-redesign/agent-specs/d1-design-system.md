# D1 — Дизайн-система ReelsMaker / 色の道

> Спека (не код реализации). Источник истины — брендбук Никиты Малова (самурайская эстетика «латунь на чёрном лаке»).
> Стек: React 19 + Vite + Tailwind 4 (`@theme`). Шрифты self-host через `@fontsource`.
> Один источник токенов: `:root` CSS-переменные → проброс в `@theme` Tailwind. Ни одного хардкода мимо токена.

---

## 0. Принцип системы

Латунная гравировка на чёрном лаке. Тёмная база занимает поле, тёплое золото — акцент, никогда не фон. Чистый белый и чёрный запрещены. Прямые углы везде. Глубина — слоями подложек, не тенями.

**Тёмная-only.** Light — исключение <10% (печать, партнёрские интеграции), вне основного UI. В спеке light описан как опциональный набор токенов, не как переключатель в интерфейсе.

---

## 1. Цветовые токены

### 1.1 Палитра брендбука (raw, immutable)

| Token-имя | Брендбук | HEX | Роль по брендбуку |
|---|---|---|---|
| `--kuro` | Kuro 黒 | `#0A0A0A` | Основной фон (слой 1) |
| `--sumi` | Sumi 墨 | `#1A1A1A` | Подложки, карточки (слой 2) |
| `--hai` | Hai 灰 | `#2A2A2A` | Разделители, бордеры (слой 3) |
| `--kinzoku` | Kinzoku 金属 | `#C9A84C` | Главный акцент: заголовки, CTA |
| `--do` | Dō 銅 | `#B87333` | Вторичный акцент: обводки, линии, иконки |
| `--kogane` | Kogane 黄金 | `#E8C547` | Яркий блик: hover, искры (точечно) |
| `--shiroi` | Shiroi 白い | `#F0E6D2` | Основной текст (тёплый пергамент) |
| `--kasumi` | Kasumi 霞 | `#8A8278` | Мета-текст: подписи, даты, плейсхолдеры |
| `--chi` | Chi 血 | `#8B2500` | Кроваво-красный: ошибка/предупреждение, точечный акцент |

Эти переменные — палитра, не семантика. В компонентах напрямую **не используются** (кроме редких декоративных случаев). Компоненты потребляют только семантический слой ниже.

### 1.2 Семантический слой (то, что используют компоненты)

| Семантический токен | → ссылается на | Назначение |
|---|---|---|
| `--bg` | `--kuro` `#0A0A0A` | Фон страницы, слой 1 |
| `--surface` | `--sumi` `#1A1A1A` | Карточки, панели, модалки, инпуты — слой 2 |
| `--surface-2` | `#202020` | Вложенная подложка (карточка в карточке, hover-фон строки). Между Sumi и Hai |
| `--line` | `--hai` `#2A2A2A` | Разделители, бордеры по умолчанию, тонкие линии |
| `--text` | `--shiroi` `#F0E6D2` | Основной текст |
| `--text-muted` | `--kasumi` `#8A8278` | Мета, подписи, плейсхолдеры, неактивные подписи |
| `--accent` | `--kinzoku` `#C9A84C` | Главный акцент: заголовки-золото, CTA, активные состояния, бордер-hover |
| `--accent-bright` | `--kogane` `#E8C547` | Блик: hover-искры, точечные выделения, активная иконка. Только точечно |
| `--copper` | `--do` `#B87333` | Вторичный акцент: тонкие обводки, decorative-линии, active-state кнопки, теги-рубрики |
| `--danger` | `--chi` `#8B2500` | Ошибки, деструктивные действия, предупреждения |

**Производные (для прозрачностей — не плодить, только нужные):**

| Токен | Значение | Назначение |
|---|---|---|
| `--accent-soft` | `rgb(201 168 76 / 0.10)` | Заливка featured-фона, accent-shadow-замена (тонкое свечение зоны) |
| `--accent-line` | `rgb(201 168 76 / 0.40)` | Полу-видимый акцентный бордер (focus-within, secondary hover) |
| `--grid-line` | `rgb(201 168 76 / 0.04)` | Пиксельная сетка-фон (см. §6) |
| `--danger-soft` | `rgb(139 37 0 / 0.15)` | Фон зоны ошибки/destructive-подтверждения |

### 1.3 Пропорции (контроль на ревью макета)

```
База (bg + surface + surface-2 + line):  ███████████████  65-75%
Текст (text + text-muted):                ████             15-20%
Акценты (accent + copper + accent-bright):███              10-15%  ← accent ≤ 25% площади
Danger:                                    ▏                1-3%   ← ≤ 1 «точка» на экран
```

Правила-инварианты (для аудитора):
- `--accent` как **заливка больших площадей запрещён** (>25% — провал). Это цвет обводки/текста/малых плашек.
- `--copper` никогда не заливка крупных блоков — только линии/обводки/иконки.
- `--accent-bright` — максимум 1-2 элемента на экран.
- `--danger` — не «красный инпут с ошибкой» (слишком тёмный для этого), а одна декоративная точка / лейбл деструктива.
- Фон — всегда `--bg`/`--surface`. `--text` (пергамент) как фон = провал концепции.

### 1.4 Глубина без теней

`box-shadow`/`drop-shadow` **запрещены** (вне эстетики бренда). Глубина строится:
- `--surface` (`#1A1A1A`) поверх `--bg` (`#0A0A0A`) — слои читаются контрастом светлоты, без видимой границы.
- Где нужна граница — `1px solid var(--line)`, hover → `var(--accent)`.
- Вложенность: `--surface-2` поверх `--surface`.
- «Свечение» зоны (замена цветной тени для featured) — `--accent-soft` фоновая заливка или `--accent-line` бордер, не shadow.

### 1.5 Light-исключение (опционально, не в UI-переключателе)

| Семантика | Light-значение |
|---|---|
| `--bg` | `--shiroi` `#F0E6D2` |
| `--text` | `--kuro` `#0A0A0A` |
| `--accent` | `--do` `#B87333` (медь — золото на светлом теряется) |

Применять только в печатных/партнёрских контекстах. В приложении ReelsMaker не реализуем как тему — фиксируем как зарезервированный набор.

---

## 2. Типографика

### 2.1 Шрифты (4 роли, без пересечений) — self-host `@fontsource`

| Роль | Шрифт | `@fontsource` пакет | Веса | CSS-переменная |
|---|---|---|---|---|
| Заголовки / золото | Noto Serif JP | `@fontsource/noto-serif-jp` | 400, 700 | `--font-display` |
| Текст / body | Manrope | `@fontsource-variable/manrope` | 400, 500, 700 | `--font-body` |
| Мета / технический | JetBrains Mono | `@fontsource-variable/jetbrains-mono` | 400, 700 | `--font-mono` |
| Пиксельные микро-теги | Press Start 2P | `@fontsource/press-start-2p` | 400 | `--font-pixel` |

```
--font-display: 'Noto Serif JP', serif;
--font-body:    'Manrope', system-ui, sans-serif;
--font-mono:    'JetBrains Mono', ui-monospace, monospace;
--font-pixel:   'Press Start 2P', monospace;
```

Импорт строго нужных весов в `main.tsx` (не весь набор) — Manrope/JetBrains как variable. Все 4 поддерживают кириллицу.

### 2.2 Шкала размеров (mobile-first, плавная прогрессия)

Маппинг на брендбук-иерархию сайта. Tailwind-классы — mobile base → up.

| Уровень | Шрифт | Вес | Размер (mobile → desktop) | line-height | letter-spacing |
|---|---|---|---|---|---|
| H1 | display | 700 | `text-3xl sm:text-4xl lg:text-5xl` (30→48px) | 1.1 | 0.02em |
| H2 | display | 700 | `text-2xl sm:text-3xl lg:text-4xl` (24→36px) | 1.2 | 0.02em |
| H3 | display | 400 | `text-xl sm:text-2xl lg:text-2xl` (20→24px) | 1.3 | 0.02em |
| Body | body | 400 | `text-base lg:text-lg` (16→18px) | 1.6 | 0 |
| Body-lg | body | 400 | `text-lg lg:text-xl` (18→20px) | 1.7 | 0 |
| Caption / meta | mono | 400 | `text-xs sm:text-sm` (12→14px) | 1.4 | 0.05em |
| Label / eyebrow | mono | 400 | `text-xs` (12px), uppercase | 1.4 | 0.08em |
| Tag (pixel) | pixel | 400 | `text-[9px] sm:text-[10px]`, uppercase | 1.2 | 0.15em |

Инвариант: H1 верхняя граница 48px (брендбук-сайт), 64px+ — только обложки/постеры, не UI.

### 2.3 Правила набора (инварианты для аудита)

- Заголовки display: цвет только `--accent` или `--text`. **Никогда** `--text-muted`/серый.
- Display только для 1-3 строк. Длинный текст (>3 строк) display — провал (это body Manrope).
- Press Start 2P — только 8-14px. Крупнее = провал. Всегда uppercase, всегда `--accent` или `--copper`.
- Mono caps (label/eyebrow) — для рубрик и навигации: uppercase + tracking 0.08em.
- Выравнивание: всё по левому краю. Центр — только hero/обложки. `text-align: justify` и right — запрет.
- Курсив (italic) — запрет во всех 4 шрифтах. Подчёркивание — только ссылки.
- Не более 2 шрифтов на блок (pixel-тег не считается).

### 2.4 Применение по ролям UI

| Элемент UI | Шрифт + токен |
|---|---|
| Заголовок страницы / секции | display, `--accent` (или `--text` для не-hero) |
| Заголовок карточки | display 700, `--text` |
| Body, описания, параграфы | body, `--text` |
| Подписи, даты, размеры файлов, длительности | mono, `--text-muted` |
| Eyebrow над заголовком («// О ПРОЕКТЕ») | mono caps, `--copper` |
| Кнопки | mono, uppercase, tracking 0.1em |
| Теги-рубрики / бейджи статуса | pixel, `--accent` |
| Навигация (NavRail / header) | mono caps, `--text-muted`, hover `--accent` |
| Плейсхолдеры инпутов | body, `--text-muted` |

---

## 3. Геометрия

### 3.1 Углы — нулевые

```
--radius: 0;          /* глобально. border-radius везде 0 */
```
**Инвариант:** любой `border-radius > 0` — провал брендбука. Tailwind: переопределить `--radius-*` в `@theme` в 0, не использовать `rounded-*`.

### 3.2 Сетка и контейнер

| Параметр | Значение | Токен |
|---|---|---|
| Max-width контента | 1200px | `--container-max: 1200px` |
| Колонки (desktop) | 12, gap 24px | `--grid-gap: 1.5rem` |
| Tablet (768-1024px) | 8 колонок | — |
| Mobile (<768px) | 4 колонки, всё в 1 столбец | — |

Контейнер: `mx-auto max-w-[1200px] px-4 sm:px-6 lg:px-8`.

### 3.3 Spacing-система (8px grid)

Все отступы кратны 8px (4px допустим внутри мелких компонентов).

**Section padding (единый по всем секциям):**
```
py-16 md:py-20 lg:py-24      /* вертикальный ритм, без скачков >24px */
```
Брендбук задаёт 120/60px; адаптируем в плавную прогрессию (64→96px) для веб-приложения, сохраняя «много воздуха».

**Card padding:** `p-6 lg:p-8` (24→32px) — собственная система, отдельно от секций.

**Grid-прогрессии:**
```
grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-6 lg:gap-8   /* карточки/галерея рилсов */
grid-cols-2 md:grid-cols-4 gap-4 sm:gap-6                            /* статы/метрики */
```
Инвариант: не смешивать `space-y-*` и `gap-*` в одном компоненте; не делать скачков gap >24px.

### 3.4 Тач-таргеты и focus

- Минимальный интерактивный таргет: 44×44px (аудит отметил текущие 36px как провал).
- Focus-visible на всех интерактивных: `outline: 2px solid var(--accent); outline-offset: 2px` (вместо тени).

---

## 4. Компоненты-примитивы (геометрия + токены)

Базовые правила (детальная вёрстка — отдельная спека UI-примитивов).

### 4.1 Кнопки

| Состояние | Фон | Текст | Бордер |
|---|---|---|---|
| Primary default | прозрачный | `--accent` | `2px solid --accent` |
| Primary hover | `--accent` | `--bg` | `2px solid --accent` |
| Primary active | `--copper` | `--bg` | `2px solid --copper` |
| Secondary default | прозрачный | `--text-muted` | `1px solid --text-muted` |
| Secondary hover | прозрачный | `--text` | `1px solid --text` |
| Destructive | прозрачный | `--danger` | `1px solid --danger` |
| Disabled | прозрачный | `--text-muted` | `1px solid --line` |

Шрифт mono uppercase, tracking 0.1em, padding `12px 24px`, radius 0, заливка-анимация 0.2s.

### 4.2 Карточки

```
background: var(--surface);
border: 1px solid var(--line);
border-radius: 0;
padding: 24px (lg: 32px);
transition: border-color 0.3s;
hover → border-color: var(--accent);
```
Featured-карточка: бордер `--accent` + фон `--accent-soft` (вместо цветной тени) + опциональный мелкий pixel-бейдж `--accent`. Без `scale` (bounce-эстетика запрещена — допустим только статичный визуальный приоритет цветом/бордером).

### 4.3 Инпуты

```
background: var(--surface);
border: 1px solid var(--line);
radius 0; color: var(--text); font: body 16px; padding 14px 18px;
focus → border-color: var(--accent); outline: none (focus-ring через outline для клавиатуры);
placeholder → var(--text-muted);
```

### 4.4 Бейджи / теги

| Тип | Фон | Текст | Бордер |
|---|---|---|---|
| Основной | `--surface` | `--text` | `1px solid --line` |
| Акцентный | `--accent` | `--bg` | нет |
| Тег-рубрика | прозрачный | `--accent` | `1px solid --accent` |
| Статус-ошибка | `--danger-soft` | `--danger` | `1px solid --danger` |

### 4.5 Ссылки / разделители

- Ссылка: `--accent`, `border-bottom: 1px solid transparent` → hover bottom `--accent`, transition 0.2s.
- Разделитель: `1px solid --line`. Акцентный: `2px solid --accent`. Декоративный: пиксельный пунктир `--copper`.

---

## 5. Motion

`transition` — всегда конкретные свойства (`transform`, `border-color`, `background-color`, `opacity`), **никогда `all`**.

### 5.1 Разрешённые

| Элемент | Анимация | Длительность |
|---|---|---|
| Появление секций при скролле | fade-in + `translateY(20px→0)` | 0.6s ease-out, `once: true` |
| Staggered загрузка hero | заголовок → текст → кнопки | 0.3s delay между |
| Hover карточки | `border-color` → `--accent` | 0.3s |
| Hover кнопки | заливка фона | 0.2s |
| Hover ссылки | подчёркивание снизу | 0.2s |
| Точечный глитч (редко) | смещение 2-4px, `--danger` | мгновенно, не цикл |

### 5.2 Запрещённые (инвариант для аудита)

- Параллакс.
- Бесконечная rotation / любой `repeat: Infinity` (особенно на невидимых элементах).
- Bounce / elastic easing.
- Любая анимация >1s.
- Фоновое видео.
- `scale` на hover как основной приём (мягкий, не bounce — допустим точечно, но не «прыжки»).

### 5.3 Доступность

Уважать `prefers-reduced-motion: reduce` — отключать entrance/translate, оставлять только мгновенную смену цвета.

---

## 6. Графические элементы

### 6.1 Пиксельная сетка (фон, слой 1)

Фиксированный фон страницы поверх `--bg`:
```css
background-image:
  linear-gradient(var(--grid-line) 1px, transparent 1px),
  linear-gradient(90deg, var(--grid-line) 1px, transparent 1px);
background-size: 16px 16px;
```
`--grid-line` = `rgb(201 168 76 / 0.04)`. Только поверх плоского фона, не поверх фото/превью. Рендерить **один раз** (аудит VD-01: было дублирование index.html + AppShell — устранить).

### 6.2 Энсо (円相) — фоновый акцент

Незамкнутый пиксельный круг (разрыв 15-20%). SVG или pixel-блоки.
- Hero/крупные пустые зоны: opacity **8%** (брендбук), `--accent`, большой (вне content-flow, absolute, не overflow на mobile).
- Контейнер энсо — responsive (% / vw), сам SVG может иметь фиксированный viewBox.
- Не основной элемент — фоновый слой.

### 6.3 Зернистость (grain)

SVG-noise overlay поверх фонов: opacity 3-7%, `mix-blend-mode: overlay`. Рендерить один раз глобально.

### 6.4 Иероглифы / волны (опционально)

- Кандзи как крупный фоновый слой: 200-600px, opacity 5-10%, `--accent` или `--hai`. Допустимые: 侍 道 心 火 刀. Для ReelsMaker уместен 刀 (катана — инструмент/точность) или 火 (огонь — энергия).
- Волны Seigaiha (пиксельные) — горизонтальный разделитель между секциями, `--copper` opacity 15-30%.

### 6.5 Иконки

Пиксельные, сетка 16×16/24×24, stroke 2px, ступенчатые изгибы. Цвет: `--text-muted` (стандарт), `--accent` (акцент), `--accent-bright` (активный). **Не смешивать** с Lucide/Heroicons — единый пиксельный набор. (Если пиксельный набор недоступен на старте — это явный долг, фиксируем; не подмешивать обычные иконки в эстетику.)

---

## 7. Маппинг на Tailwind 4 `@theme` + CSS-переменные

### 7.1 Слоистая организация (один источник истины)

```
Слой 1: палитра  →  :root { --kuro, --sumi, ..., --chi }          (immutable raw)
Слой 2: семантика →  :root { --bg: var(--kuro); --accent: var(--kinzoku); ... }
Слой 3: @theme    →  проброс семантики в Tailwind-токены           (генерит утилиты)
```

### 7.2 `index.css` (структура спеки)

```css
@import "tailwindcss";

/* @fontsource импортируется в main.tsx, не здесь */

:root {
  /* Слой 1 — палитра брендбука (raw, не использовать в компонентах) */
  --kuro:#0A0A0A; --sumi:#1A1A1A; --hai:#2A2A2A;
  --kinzoku:#C9A84C; --do:#B87333; --kogane:#E8C547;
  --shiroi:#F0E6D2; --kasumi:#8A8278; --chi:#8B2500;

  /* Слой 2 — семантика (потребляют компоненты) */
  --bg: var(--kuro);
  --surface: var(--sumi);
  --surface-2:#202020;
  --line: var(--hai);
  --text: var(--shiroi);
  --text-muted: var(--kasumi);
  --accent: var(--kinzoku);
  --accent-bright: var(--kogane);
  --copper: var(--do);
  --danger: var(--chi);

  /* производные */
  --accent-soft: rgb(201 168 76 / 0.10);
  --accent-line: rgb(201 168 76 / 0.40);
  --grid-line:   rgb(201 168 76 / 0.04);
  --danger-soft: rgb(139 37 0 / 0.15);

  /* шрифты */
  --font-display:'Noto Serif JP',serif;
  --font-body:'Manrope',system-ui,sans-serif;
  --font-mono:'JetBrains Mono',ui-monospace,monospace;
  --font-pixel:'Press Start 2P',monospace;

  /* геометрия */
  --container-max:1200px;
  --grid-gap:1.5rem;
  --radius:0;
}

/* Слой 3 — проброс в Tailwind (генерит bg-*, text-*, border-*, font-*) */
@theme inline {
  --color-bg: var(--bg);
  --color-surface: var(--surface);
  --color-surface-2: var(--surface-2);
  --color-line: var(--line);
  --color-text: var(--text);
  --color-muted: var(--text-muted);
  --color-accent: var(--accent);
  --color-accent-bright: var(--accent-bright);
  --color-copper: var(--copper);
  --color-danger: var(--danger);

  --font-display: var(--font-display);
  --font-body: var(--font-body);
  --font-mono: var(--font-mono);
  --font-pixel: var(--font-pixel);

  /* обнулить все радиусы Tailwind */
  --radius-sm:0; --radius-md:0; --radius-lg:0; --radius-xl:0; --radius-2xl:0; --radius-3xl:0;
}

body {
  background: var(--bg);
  color: var(--text);
  font-family: var(--font-body);
}
```

### 7.3 Правила потребления (для всех компонентов)

- Цвета **только** через семантические утилиты: `bg-surface`, `text-accent`, `border-line`, `bg-bg`. Raw-палитра (`--kuro` и т.д.) и сырые Tailwind-цвета (`stone-*`, `gold-*`, `green-500`) — **запрет**. Это устраняет аудит-проблему U-01 / VD-06 (две конфликтующие системы токенов).
- Шрифты через `font-display` / `font-body` / `font-mono` / `font-pixel`.
- Радиусы — не использовать `rounded-*` (все обнулены, но классы засоряют).
- Тени — не использовать `shadow-*`.
- Прозрачные акценты — через готовые `--accent-soft` / `--accent-line`, не плодить произвольные `/10`, `/20`.

### 7.4 Миграция со старой системы (из аудита)

Существующая OKLCH-система (`--ink/--gold/--paper` тёмная + `--surface/--accent-primary` светлая, хардкод `stone-*`) — **заменяется целиком** этим единым слоем. Сохраняется по аудиту: философия одного акцента, кинематографические слои (grain/энсо вместо vignette), mono-caps навигация, self-host variable-шрифты, focus-ring, `prefers-reduced-motion`, data-слой и бизнес-логика. Меняется: палитра OKLCH → HEX-палитра брендбука, два словаря токенов → один.

---

## Приложение: чек-лист инвариантов (для аудитора редизайна)

- [ ] Фон только `--bg`/`--surface`; пергамент как фон — нет.
- [ ] `--accent` (золото) ≤ 25% площади, не заливка крупных блоков.
- [ ] `--accent-bright` ≤ 2 элементов на экран; `--danger` ≤ 1 точка.
- [ ] Все 4 шрифта на месте, по ролям; display не длиннее 3 строк; pixel ≤ 14px uppercase.
- [ ] `border-radius: 0` везде; ни одного `rounded-*`.
- [ ] Ни одной `box-shadow`; глубина — слои + бордеры.
- [ ] Единый section-padding `py-16 md:py-20 lg:py-24`; нет скачков >24px.
- [ ] Контейнер `max-w-[1200px]`, сетка 12 кол / gap 24px.
- [ ] Цвета только через семантические утилиты; нет `stone-*`/raw-палитры/OKLCH-остатков.
- [ ] Нет `transition: all`, нет `repeat: Infinity`, нет анимаций >1s, нет параллакса/bounce.
- [ ] Пиксельная сетка и grain рендерятся по одному разу (не дублируются).
- [ ] Тач-таргеты ≥44px; focus-visible outline на всех интерактивных.
- [ ] `prefers-reduced-motion` уважается.
```
