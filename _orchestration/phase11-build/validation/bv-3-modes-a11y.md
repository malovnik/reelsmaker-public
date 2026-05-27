# BV-3 — Валидация двух режимов, подсказок и доступности

Роль: Two-Mode UX & Accessibility Validator. Источники: d2-mode-stepwise.md (R1), d3-mode-expert.md (R5), UI-IMPL-PRD R1/R2/R5.
Код: `apps/frontend/src` — `contexts/`, `components/upload/`, `components/settings-shared/`, `components/ui/Tooltip.tsx`.

---

## Итоговый вердикт

| Критерий | Статус |
|---|---|
| Пошаговый (R1) — реальная пошаговая машина | PASS (с замечаниями) |
| Эксперт (R5) — 100% подсказок на upload-форме | FAIL (студия D3 не реализована в upload-режиме) |
| Lossless switch (R2) | PASS |
| a11y / тач | PASS (с дырами) |
| `pnpm build` | PASS (✓ built in ~1s, 0 ошибок) |

Главный вывод: R1 и R2 закрыты добротно. **R5 закрыт частично**: tooltip-система с реестром `controlHints` + обязательным `hintKey` реально существует и используется на страницах `/settings/*` (performance-groups, post-production, vision, maintenance), но **режим «Эксперт» в форме загрузки — это не студия D3, а legacy `UploadWizard.tsx` форма-всё-сразу** без `controlHints`/`Tooltip`. Заявленное «100% подсказок механически» относится к settings-страницам, не к upload-Эксперту.

---

## 1. Пошаговый режим (R1) — PASS

`components/upload/guided/GuidedFlow.tsx` + `guided/StepChrome.tsx`.

Реальная пошаговая машина: локальный `screen` стейт `"start" | 1..6 | "summary" | "progress"`, навигация `setScreen()`, не форма-всё-сразу. Подтверждено:

- **Старт-кнопка крупная**: `btn btn-primary px-10 py-4 text-base`, по центру (GuidedFlow:218-224).
- **Прогресс**: `SetupProgress` — полоса заполнения + «Шаг N / 6» + кликабельные метки пройденных шагов (`onJump`, прыжок назад). На S1–S6.
- **Дефолты (Auto)**: `narrativeMode=bottom_up` по умолчанию (бейдж «Рекомендуем»), STT локальный, Gemini, авто-имя проекта при пустом поле (leaveProjectStep:144-156). Новичок проходит на «Далее».
- **S2 единственный обязательный**: «Далее» блокируется без файла (`nextDisabled={!state.file}` + `nextHint`).
- **S7 сводка** с «измен.» → прыжок на шаг; крупная «▶ Запустить нарезку».
- **S8 прогресс** SSE % + стадия + «✕ Отменить нарезку» с confirm-модалкой (cancelJob:172-183), `done` → CTA «Смотреть рилсы».

Замечания (не блокеры):
- **Спека просит S1–S11**, реализованы только **S1–S8**. S9 (галерея), S10 (Tinder), S11 (экспорт) живут отдельными роутами (`/jobs/:id`, JobTinderPage), а пошаговый ведёт к ним ссылкой «Смотреть рилсы →» вместо встроенной цепочки. Линейная цепочка S9–S11 «внутри визарда» из спеки D2 §1 — не реализована (осознанный компромисс: результат вынесен на страницу джоба).
- S6: добавлен контрол «Кадрирование» (fit_mode), которого в спеке D2 S6 не было; слайдер «Эконом—Макс» из спеки заменён на статичный warning-блок «все режимы качества работают одинаково» (честнее, но слайдера-ощущения контроля нет — это ок).

## 2. Lossless switch (R2) — PASS

`contexts/WizardStateProvider.tsx` + `HomeClient.tsx`.

- `WizardStateProvider` вызывает `useWizardState` **один раз** и раздаёт через контекст (WizardStateProvider:34-45).
- В `HomeClient.tsx:101-114` провайдер смонтирован **НАД** `StudioSwitch`, который рендерит `GuidedFlow` ИЛИ `UploadWizard` по `useUiMode()`. Переключение режима меняет только дочернее поддерево — провайдер не размонтируется.
- Оба режима читают `useWizardStateContext()` (GuidedFlow:109, UploadWizard:98), **локального стейта данных нет**. `GuidedFlow` держит локально только UI-эфемерное (`screen`, `projectName`, `isDragging`) — это не теряемые при свитче данные.
- `File`, `project_id`, опции, SSE — всё в общем сторе → при guided↔expert не теряются. Контракт верен.
- `UiModeContext` персистит режим в localStorage с синхронным no-flash чтением.

## 3. Tooltip 100% (R5) — FAIL для upload-Эксперта, PASS для settings

### Что реализовано хорошо (settings-страницы)
- `components/ui/Tooltip.tsx` — полноценный компонент: required `what/effect/advise`, `badge`, двухслойность (inline + full-tooltip), мультимодальность hover(150ms)/focus/tap-`(i)` 44px, авто-флип, portal, Esc, `aria-describedby`, coarse-pointer → accordion-блок. Соответствует D3 §2.
- `settings-shared/controlHints.ts` — реестр **~60 ключей** со всеми 8 группами D3, honesty-бейджи (broken/decorative/dormant/off-default/opt-in/cpu-heavy/partial/destructive). Типобезопасный `ControlHintKey`.
- `hintAdornment.resolveHint` + примитивы `SwitchRow/SelectRow/SliderRow/NumberRow/ActionButton`: `hintKey?` подтягивает триплет, `hint?` — fallback-строка. Используются в 30+ performance-groups, post-production, vision, maintenance.

### Где провал
**Реальный gate отсутствует.** D3 §2.4 обещает: «собрать контрол без подсказки нельзя типобезопасно» + «gate-валидатор сборки падает». По факту:
- `hintKey` — **опциональный** проп (`hintKey?`), рядом живёт `hint?: string` fallback. Контрол можно отрендерить вообще без подсказки (оба undefined → `inline: ""`, `adornment: null`). Это не инвариант, а дисциплина.
- Никакого build-gate-валидатора в проекте нет (build = чистый `tsc + vite`, без проверки покрытия).

**Upload-«Эксперт» — не студия D3.** `UploadWizard.tsx` — старая форма с примитивами `Step/Field/Select/ToggleRow` из `WizardSteps.tsx`, не использует `controlHints`/`Tooltip`/`settings-shared`. Покрытие подсказками здесь:

| | контролов | с подсказкой |
|---|---|---|
| UploadWizard (Эксперт upload) | ~14 групп контролов | ~5 (hint=/help=) |

- `ToggleRow` (WizardSteps) делает `hint: string` **обязательным** — 3 тоггла (use_proxy / use_source / force_reingest) покрыты.
- `ComposerStrategyBlock` — 4 radio с hint каждый. `<textarea>` custom_prompt — `help=`.
- **Без подсказки**: profile selector, project select, aspect-сегмент (4 кнопки), reel-count auto/custom + слайдер + number, subtitle select, post-production select + 5 override-чекбоксов, split-screen 3-way, transcriber/provider/lang/fit селекты (в `<details>`), pipeline_mode radio.

**Реальное покрытие подсказками upper-bound оценка:**
- Upload-Эксперт (то, что юзер реально видит как «Эксперт»): **~35–40%** контролов имеют какую-либо подсказку, **0%** через `hintKey`/реестр/full-tooltip.
- Settings-страницы (где студия D3 реально живёт): **~95%+** через `hintKey` (full-triplet + badge), остальное — fallback `hint`.
- Объединённо «Эксперт-поверхность» (если считать settings частью эксперт-режима): доминируют settings-контролы с реестром → **~85% с full-tooltip-триплетом**, но критичная upload-точка входа провалена.

## 4. a11y / тач — PASS с дырами

Хорошо:
- Глобально `:focus-visible { outline: 2px gold }` (globals.css:261) + `@media (prefers-reduced-motion: reduce)` глушит анимации (globals.css:761).
- Tooltip-`(i)` тач-кнопки `size-11` = 44×44px (Tooltip:202,220). Drop-зоны `role=button tabIndex=0` + Enter/Space (GuidedFlow:339-348, UploadWizard:218-223). `aria-pressed` на radio-картах, `role=switch aria-checked` на тоглах, `role=tablist/tab aria-selected` на свитче режимов, `role=alert` на ошибках, `aria-live=polite` на счётчике символов.
- Тач: действия не hover-only — tap-`(i)` через coarse-pointer ветку.

Дыры:
- **Тач-таргеты <44px на главных интерактивных элементах.** Тоглы guided/expert — `h-6 w-11` (24×44px, высота 24px < 44). Radio-карты navrative — клик по всей карте (ок), но radio-dot декоративен. Subtitle-чекбокс `size-4` (16px), override-чекбоксы `size-3.5` (14px), reel-count number `w-16 py-1`. Сегмент-контролы aspect `py-2` (~32px высоты). Метки прогресса `text-[0.625rem]` — мелкие кликабельные цели <44px. На тач это ниже WCAG 2.5.5 / чеклиста ≥44px.
- **Хардкод светлой темы в тёмном бренде.** `WizardSteps.tsx` `ComposerStrategyBlock`: `bg-white`, `text-stone-900/700/500` (строки 223,230,241,244,251); тогл-ручка `bg-white` (171). `AutoConfigSummary.tsx` сплошь `text-stone-*`. На Kuro-фоне это белые карточки — ломает брендбук и контраст-ожидания, выглядит как чужой компонент в Эксперт-форме.
- **Модалки max-h**: не проверено по этому скоупу (ConfirmDialog/Modal в ui/), но Tooltip `max-width:280` есть; для модалок отдельная проверка вне B-V-3.
- Слайдер reel-count `type=range` имеет `aria-label`, но без `aria-valuetext`/связанного описания — приемлемо.

## 5. Build

```
pnpm build → ✓ built in ~1s, 0 ошибок типов/сборки.
```
Артефакты: HomePage 90.76kB, PerformanceSettingsPage 58.65kB, hintAdornment 31.77kB (отдельный чанк — реестр подсказок). TSC чист.

---

## Рекомендации (приоритет)

1. **R5 критично**: либо подключить студию D3 (`settings-shared`-примитивы + `controlHints`) к upload-«Эксперту», либо честно задокументировать, что «Эксперт upload» = упрощённая форма, а полная студия = `/settings/*`. Сейчас точка входа «Эксперт» не отражает обещание 100% подсказок.
2. Сделать `hintKey` **обязательным** (убрать `hint?` fallback или ввести build-time проверку покрытия) — иначе инвариант R5 = дисциплина, а не гарантия.
3. Поднять тач-высоту тоглов и чекбоксов до 44px (или увеличить кликабельную область wrapper'ом).
4. Заменить `bg-white`/`text-stone-*` в `WizardSteps.ComposerStrategyBlock` и `AutoConfigSummary` на токены тёмной темы (`--ink-2`, `--paper`, `--mute`).
5. Довести пошаговую цепочку S9–S11 либо оставить осознанный редирект на `/jobs/:id` (задокументировать как принятое решение).
