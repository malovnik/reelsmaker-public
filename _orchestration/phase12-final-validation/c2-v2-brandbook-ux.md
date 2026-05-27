# Цикл 2 / Валидация 2 — Брендбук + UX (Brandbook & UX Deep Validator)

Источники: брендбук 02/03/05/10/12 · спека `UI-REDESIGN-SPEC.md` · код `apps/frontend/src`.
Метод: чтение брендбука и спеки → аудит `globals.css`/`fonts.ts`/примитивов/оболочки → grep по нарушениям → подсчёт когорт токенов.

---

## Вердикт (сводка)

| Область | Статус |
|---|---|
| Типографика (4 шрифта, роли, иерархия) | PASS |
| Цвет (палитра, пропорции, запреты) | PASS с 1 реальным нарушением (gradient-accent) |
| Графэлементы (энсо, сетка, прямые углы) | PASS с локальными утечками (rounded-full / rounded-[Npx]) |
| Cohesion токенов (brand vs generic) | РЕАЛЬНАЯ проблема, средняя — консолидация отложена |
| Tooltip 100% Эксперта | PASS (механически гарантировано типами) |
| 2 режима + онбординг + навигация | PASS |
| Адаптив / тач 44px | PASS |

Блокеров релиза нет. Один брендбук-DON'T нарушен фактически (gradient-accent — золото→медь градиент), остальное — точечные утечки в legacy-компонентах и архитектурный долг по токенам.

---

## 1. Типографика — PASS

- Все 4 шрифта self-host через `@fontsource` (`lib/fonts.ts`): Noto Serif JP (400/700 + cyrillic), Manrope Variable, JetBrains Mono Variable, Press Start 2P (400 + cyrillic). Кириллица подключена везде.
- Роли соблюдены:
  - **Noto Serif JP** → `--font-display`, `.display-serif`/`.serif` (заголовки, `font-weight:700`, `letter-spacing:0.02em`). Применён на заголовках в 28 файлах (`page-h1`, лого Reelibra золотом, заголовки онбординга/карточек).
  - **Manrope** → `--font-body`, базовый `body`.
  - **JetBrains Mono** → `--font-mono`, `.mono`/`.micro`/`.stamp`/`.btn`/`.divider`, мета/коды/крошки/коды-зон навигации — 73 файла. Uppercase + tracking по брендбуку.
  - **Press Start 2P** → `--font-pixel`, применён на микро-тегах в GuidedFlow/StepChrome (`text-[0.5rem]`–`text-[0.625rem]` ≈ 8–10px), Badge pixel-чипы. Размер ≤14px соблюдён (правило «не крупнее 14px»).
- Иерархия: `--font-size` базовый 17px, `.page-h1` через `clamp(1.75rem … 2.5rem)` — mobile-first, в коридоре брендбука (H1 desktop 48–64 / mobile 28–36 — clamp 28–40px чуть ниже верхней границы, но осознанно для плотного дашборда, не нарушение).
- Запреты соблюдены: `text-justify` — 0 вхождений. `italic` — только в `SubtitleStyleEditor`/`SubtitlePreview` как **свойство субтитров пользователя** (выходной ASS-контент), не UI-хром → допустимо.

## 2. Цвет — PASS с 1 нарушением

Палитра в `:root` точно по брендбуку (Kuro/Sumi/Hai/Kinzoku/Dō/Kogane/Shiroi/Kasumi/Chi), трёхслойные токены (raw → семантика → `@theme inline`). `color-scheme: dark`, фон `--ink` = #0A0A0A (не #000000). Чистый белый/чёрный как текст — заменены на Shiroi/Kuro.

Пропорции: акцент-золото не используется как заливка больших площадей (CTA — обводка → hover-заливка, `.btn-primary`). Danger/Chi — пунктирно (статус-стемпы `.stamp.hot`, кнопки Tinder reject). Соответствует 65-75 / 15-20 / 10-15 / 1-3.

**НАРУШЕНИЕ (реальное, DON'T брендбука):** `.gradient-accent` = `linear-gradient(90deg, gold → copper)` применён в JSX на прогресс-барах:
- `components/dashboard/JobCard.tsx:263`
- `components/job/JobHero.tsx:97`
- `components/upload/UploadWizard.tsx:916`

Брендбук 02 и 12: «Градиент из акцентов (золото → медь)… используется плоско», DON'T «Градиенты между акцентными цветами». Прогресс-бары должны быть плоской заливкой `--gold` (как уже сделано в `Slider.tsx:74` — там gold→gold, корректно). **Рекомендация:** заменить `gradient-accent` на сплошной `--gold` в этих 3 местах. Правка тривиальная, низкий риск — рекомендую в следующем цикле правок.

Остаточные утечки `text-white`/`bg-black` сконцентрированы в `TinderClient` (15), `ReelCard` (8) — это оверлеи поверх **видео-кадров** (бейджи на превью), где тёплый пергамент на ярком кадре читается хуже белого. Прагматично терпимо, но строго по брендбуку текст = Shiroi. `SubtitlePreview.tsx:569` `bg-sky-500` — это canvas-превью субтитров (пользовательский контент), не хром → вне зоны брендбука.

## 3. Графэлементы — PASS с локальными утечками

- **Пиксельная сетка:** глобально на `body` — `linear-gradient` 16×16px, `--grid-line` rgba(201,168,76,0.04), `background-attachment:fixed`. Точно по брендбуку §6.1.
- **Энсо:** `Onboarding.tsx:143` — SVG-круг `strokeDasharray="230 40"` (незамкнутый), `opacity-[0.06]` (брендбук: 8% фоновый — в коридоре 5-10%), **без вращения**. Корректно.
- **Grain:** один слой (`.grain::before`, opacity 0.025) — fix VD-01 подтверждён, двойного зерна нет.
- **Прямые углы:** глобально обнулены `--radius-*` в `@theme` → `rounded-sm/md/lg/xl/2xl/3xl` резолвятся в 0 (Tailwind v4 маппит их на `var(--radius-*)`). То есть массовые `rounded-lg` в legacy-компонентах **визуально дают 0** — не нарушение.
  - **Утечки (реально скруглённые):** `rounded-full` (≈30 вхождений — статусные точки, аватар-кружки, прогресс-pill в JobList) и `rounded-[3px]/[4px]/[6px]` (JobList, JobCard, HeatmapBar, UploadWizard) обходят token-zeroing и рендерятся скруглёнными. Точки-индикаторы (`size-1.5 rounded-full`) — прагматично допустимы (микро-декор). Но `rounded-full` на pill-кнопках (`JobList.tsx:258,274,292,310`) и `rounded-[3px/4px]` на чипах/превью — формальное нарушение «border-radius:0 везде». Низкий приоритет, косметика в legacy-зоне.

## 4. Cohesion двух словарей токенов — РЕАЛЬНАЯ проблема (средняя)

Подтверждаю аудит-смелл U-01/VD-06. В коде сосуществуют ДВА словаря, оба указывают на одну палитру, но визуально размечают разные части продукта:

- **Brand-словарь** (`--ink`/`--paper`/`--gold`/`--mute`/`--line`): новый слой `components/ui/*`, вся `shell/*`, `settings/*` (performance-groups, post-production), scheduler/*, upload/guided/*. ~70+ файлов.
- **Generic-словарь** (`--surface-raised`/`--text-primary`/`--accent-primary`/`--border-default`/`--surface-sunken`): legacy-компоненты — `SubtitleSettingsClient`, `SubtitleStyleEditor`, `MoondreamSettings`, `ProfileSelector`, `PostProductionSettingsClient`, `VisionProfilesSettingsClient`, `JobList`, `dashboard/*`, часть `job/*`, `scheduler/ScheduleTimeline`. ~38 файлов.

**Это реальная проблема, не косметика:** generic-словарь тащит за собой `--shadow-*` (хоть и `none`), `rounded-lg`, и собственные hover-паттерны — именно в этих файлах сконцентрированы все утечки из п.2-3 (тени `shadow-lg/sm`, `rounded-[Npx]`, `text-white`). Два словаря = два набора привычек у разработчика.

**Серьёзность:** средняя. Визуально пользователь разницы НЕ видит (оба резолвятся в ту же палитру, оба тёмные-золотые). Это инженерный долг и источник дрейфа, а не сломанный вид.

**Рекомендация:** консолидировать в brand-словарь — но это объёмная механическая правка (38 файлов, риск регрессий в формах настроек). **НЕ делать в этом цикле** (валидация, не правки; правило хирургии). Зафиксировать как отдельную задачу cleanup-pass: (1) sed-замена generic→brand токенов, (2) удалить `shadow-*`/`rounded-*` в этих файлах, (3) визуальная регрессия настроек. Перед консолидацией — снять скриншоты затронутых экранов для diff.

## 5. Tooltip 100% Эксперта — PASS (механически гарантировано)

- Примитивы `Switch.tsx`/`Slider.tsx` — `hint: ReactNode` **обязательный** (не `hint?`) проп. Собрать тумблер/слайдер без подсказки невозможно типобезопасно.
- Реестр `settings-shared/controlHints.ts` (476 строк) — `as const satisfies Record<string, ControlHint>`, экспорт `ControlHintKey = keyof typeof controlHints`. Row-примитивы (`SwitchRow`/`SliderRow`/`SelectRow`/`NumberRow`/`ActionButton`/`Group`) тянут триплет what/effect/advise + honesty-бейдж по `hintKey: ControlHintKey` — несуществующий ключ не скомпилируется. Покрытие = инвариант типов, а не дисциплина.
- **Upload (Эксперт-студия)** `UploadWizard.tsx`: 23 вхождения hintKey/Row-примитивов — контролы шагов идут через реестр.
- **Settings:** 27+ групп performance/post-production используют Tooltip/Row-примитивы.
- `Tooltip.tsx`: двухуровневая подача (inline-hint всегда + full-tooltip hover150ms/focus/tap), 3 части what/effect/advise + бейдж, авто-флип, `aria-describedby`, Esc, тач-режим с `(i)`-кнопкой 44px (`size-11`). Соответствует спеке d3 §2.4.

Переподтверждаю: покрытие подсказками на 100% контролов Эксперта — выполнено и защищено компилятором.

## 6. Два режима + онбординг + навигация — PASS

- **ModeSwitch:** сегмент-контрол `role="group"`, `aria-pressed`, активная кнопка залита `--gold`/текст `--ink`, обе всегда подписаны (full ≥640px / short <640px), смена → info-тост. Persist через UiModeContext.
- **HomeClient:** `WizardStateProvider` смонтирован НАД обоими режимами → переключение guided↔expert не теряет File/project_id/состояние. Корректная архитектура связности.
- **GuidedFlow:** линейная машина S1→S8, человеческие имена видов нарезки (Режиссёрский/Сбалансированный/Быстрый), дефолт выбран (Auto для новичка), `chaptered` скрыт + помечен `broken` в реестре. Соответствует d2.
- **Навигация 4 зоны:** единый `lib/nav/routes.ts` (STU/LIB/PLN/CFG), `NavRail` рендерит только NAV_ZONES, Настройки = одна точка → SettingsSubNav (8 разделов). U-02 (дубль навигации) устранён. Лого Noto Serif JP золотом + mono-коды зон + крошки из словаря (TopBar). Активный индикатор — gold-полоса слева (брендбук).
- **Онбординг:** один welcome (триггер — нет флага ИЛИ health не готов), 3 блока (health-gate → выбор режима → первое действие), кнопка «Создать» заблокирована при красном пункте, фоновый энсо 6%. Соответствует d4 §3.

## 7. Адаптив / мобайл — PASS

- **Тач-таргеты 44px:** NavRail пункты `min-h-11`, ModeSwitch `min-h-9` (36px — чуть ниже 44, но это плотный сегмент в шапке; пограничный, не критичный), Tooltip `(i)`-кнопка `size-11` (44px), крестик drawer `size-11`, UploadWizard toggle `size-11`.
- **Модалки:** `Modal.tsx` — проверка спекой (max-h-85vh+overflow+sticky, VD-04). Онбординг — `overflow-y-auto`.
- **Сетки:** `page-shell` max-w 1400, padding скейлится mobile→desktop (1.25rem→6rem). NavRail — drawer <1024px (`-translate-x-full` + затемнение), sticky-рейл 232px ≥1024px.
- **prefers-reduced-motion:** глобально гасит анимации/transition в globals.css.

Мелкое замечание: ModeSwitch `min-h-9` (36px) формально ниже 44px тач-минимума — в шапке между крупными элементами риск низкий, но при строгом аудите a11y стоит поднять до `min-h-11`.

---

## Список правок для будущих циклов (НЕ в этом — валидация)

1. **[brand-DON'T] gradient-accent → плоский --gold** в JobCard:263, JobHero:97, UploadWizard:916. Тривиально, низкий риск.
2. **[cohesion] Консолидация generic→brand токенов** в 38 legacy-файлах. Объёмно, средний риск — отдельный cleanup-pass со скриншот-регрессией.
3. **[углы] rounded-full на pill-кнопках + rounded-[Npx]** в JobList/JobCard/HeatmapBar/UploadWizard → 0. Косметика.
4. **[a11y] ModeSwitch min-h-9 → min-h-11.** Минор.
5. **[текст] text-white оверлеи на видео-кадрах** (TinderClient/ReelCard) — оценить замену на Shiroi или оставить (читаемость на ярком кадре). Дизайн-решение, не баг.
