# UI-REDESIGN-SPEC — спецификация редизайна (Phase 9)

> Консолидация 5 дизайн-агентов (frontend-design skill активирован, брендбук-источник). Визуальный язык — самурайский «латунь на чёрном лаке».
> Это СПЕКА для реализации (Phase 11), не код. Секции: [d1 система](agent-specs/d1-design-system.md) · [d2 Пошаговый](agent-specs/d2-mode-stepwise.md) · [d3 Эксперт](agent-specs/d3-mode-expert.md) · [d4 оболочка](agent-specs/d4-shell-system.md) · [d5 экраны](agent-specs/d5-screens.md)

## Нейминг
Внутренний продукт в коде — **Reelibra** (репо `reelsmaker-public`). Код НЕ переименовываем (overreach). Брендбук даёт визуальные правила, не нейминг.

## 1. Дизайн-система (канон — d1)
**Токены (3 слоя: raw палитра → семантика → @theme Tailwind 4):**
- `--bg`=Kuro #0A0A0A · `--surface`=Sumi #1A1A1A · `--surface-2` #202020 · `--line`=Hai #2A2A2A
- `--text`=Shiroi #F0E6D2 · `--text-muted`=Kasumi #8A8278
- `--accent`=Kinzoku #C9A84C · `--accent-bright`=Kogane #E8C547 · `--copper`=Dō #B87333 · `--danger`=Chi #8B2500
- Производные: `--accent-soft`(.10), `--accent-line`(.40), `--grid-line`(.04), `--danger-soft`(.15)
- Пропорции: база 65-75% / текст 15-20% / акцент 10-15% (золото ≤25-30%, не заливка) / danger 1-3%
- **Глубина — слоями подложек, `box-shadow` запрещён.** Тёмная-only (light зарезервирован, не переключатель UI).

**Типографика (self-host @fontsource):** `--font-display` Noto Serif JP (заголовки/золото) · `--font-body` Manrope · `--font-mono` JetBrains Mono (мета/теги uppercase) · `--font-pixel` Press Start 2P (микро-теги ≤14px). Mobile-first шкала. Запрет italic/justify.

**Геометрия:** `border-radius: 0` глобально (обнулить Tailwind `--radius-*`, ноль `rounded-*`). max-w 1200→1400px, 12 колонок/gap 24, mobile 4 колонки. 8px-grid, тач-таргеты ≥44px, focus через `outline`.

**Motion:** разрешено — fade-in+translate-y 0.6s, border-hover 0.3s→#C9A84C, заливка кнопки 0.2s, staggered. Запрещено — параллакс, bounce, >1s, infinite-rotation, фон-видео.

**Графика:** пиксельная сетка 16px (.04 opacity), энсо 8% (без вращения), grain 3-7% (ОДИН слой — fix VD-01), пиксельные иконки.

## 2. Архитектурные предусловия (новый слой `components/ui/`)
Перед перевёрсткой создать: **UI-примитивы** (Button/Card/Input/Select/Switch/Slider/Modal/Tooltip — с обязательным `hint`-пропом), `UiModeContext` (guided|expert, persist localStorage), двухуровневый **Error Boundary** (root + route-lazy), **тост-система** (aria-live), `humanizeError()`, `ConfirmDialog`/`useConfirm` (вместо 13× window.confirm), скелетоны, route-level `lazy()` split. Единый `lib/nav/routes.ts`.

## 3. Два режима (ядро редизайна)
**Переключатель:** сегмент-контрол в sticky-шапке справа, глобальный, `aria-pressed`, persist. Меняет ТОЛЬКО степень раскрытия сложности — не функции, не роуты.

### Режим «Пошаговый» (guided, default) — d2
Линейная цепочка, один экран = один шаг, крупные элементы, сквозной прогресс, дефолт уже выбран:
СТАРТ (крупная кнопка «Создать проект») → S1 Проект (шлёт project_id!) → S2 Видео (drag&drop, единств. обязательный) → S3 Вид рилсов (Режиссёрский/Сбалансированный/Быстрый — человеч. имена, chaptered скрыт) → S4 Субтитры (пресеты+превью) → S5 Обработка (тумблеры, loudnorm залочен ON) → S6 Модели (STT локально/облако, LLM Gemini/Zhipu, слайдер качества с честным предупреждением) → S7 Запуск (сводка) → S8 Прогресс (SSE+отмена) → S9 Результаты (Heatmap+ReelGrid) → S10 Разметка (Tinder) → S11 Экспорт/публикация (честно: download as-is vs Publer-кампания).
**Auto для новичка:** видимые дефолты + скрытый auto-config (15 параметров молча) + сложность за ссылкой «продвинутые настройки →».

### Режим «Эксперт-студия» (expert) — d3
4-панельный «студийный пульт»: P1 навигатор-якоря (sticky) · P2 источник+таймлайн+SSE · P3 аккордеон 8 групп со всеми ~81 ручкой · P4 лента рилсов. Адаптив: P1→иконки, P3→drawer.
**Tooltip на 100% контролов** — механически гарантировано: обязательные required-пропы примитивов (нельзя собрать контрол без подсказки), единый реестр `controlHints`, gate-валидатор сборки. Подача двухуровневая: inline-hint (всегда) + full-tooltip (hover/focus/tap-`(i)` 44px) из 3 частей (что/эффект/рекомендация). 8 групп: narrative/vision(opt-in)/audio-DSP/субтитры/post-production/модели-tier/публикация/прокси.

## 4. Оболочка и система (d4)
- **Навигация:** 4 зоны (Студия/Проекты/Планировщик/Настройки) из `lib/nav/routes.ts`. Устраняет U-02 (дублирование). Настройки — одна точка (SettingsSubNav единственный источник 8 разделов). Шапка по брендбуку (лого Noto Serif JP золото + mono-крошки, sticky 64px), drawer-адаптив сохранён.
- **Онбординг:** один welcome (триггер — нет флага ИЛИ `/health` не готов: пустой llm_providers=нет GEMINI_API_KEY, ffmpeg). 3 блока: health-gate, выбор режима, первое действие. «Создать» заблокирована при красном пункте.
- **Системные паттерны** (самурайский стиль): Error Boundary («Клинок затупился»), пустые состояния с CTA+оценкой времени, тосты success/error/info, humanizeError(), ConfirmDialog (фокус-трап, alertdialog), скелетоны (prefers-reduced-motion).

## 5. Основные экраны (d5)
Dashboard · Деталь джоба (PipelineTimeline SSE + видимая отмена + **широкая галерея xl:5/2xl:6, max-w 1400**) · Деталь рилса (плеер, честный скор, правка ASS, экспорт) · Tinder (свайп + 3 явные кнопки + клавиши) · Scheduler/Publer (кампании, 4-шаг мастер, честные статусы) · Проекты+папка · Настройки (единая sub-nav, режимы, Tooltip везде).

## 6. Решённые проблемы аудита (трассировка)
- U-01/VD-06 (двойные токены) → единая система (раздел 1). U-02 (нав-дубль) → 4 зоны + одна точка настроек. U-03 (форма-всё-сразу) → Пошаговый мастер.
- VD-02 (узкая сетка) → xl:5/2xl:6, 1400px. VD-03 (hover-only тач) → primary-действия всегда видимы, 44px панель на coarse-pointer. VD-04 (модалки) → max-h-85vh+overflow+sticky. VD-05 (мелкий текст) → 15-17px. VD-01 (двойной grain) → один слой.
- FA3-01 (нет инфры режимов) → UiModeContext+Tooltip. FA3-02 (сырые ошибки) → humanizeError. FA3-03 (нет тостов/confirm) → тост-система+ConfirmDialog.
- FA4-P0-01/02 (нет error boundaries) → двухуровневый ErrorBoundary. FA5 (бандл) → route lazy().

## 7. Система честности (вплетена в дизайн)
Honesty-бейджи (decorative/dormant/broken/partial/destructive) на фикции: tier-качество честно про скорость/модель, export «отдаём MP4 как есть», cancel-джоб сохраняет частичный результат, cancel-назначения не ретрактит опубликованное (см. 409/502), мёртвый YouTube-OAuth удалён, chaptered скрыт. Пошаговый прячет фикции, Эксперт показывает правду.

## Вход для Phase 10
Эту спеку + BACKEND-MAP (81 ручка) + FRONTEND-EXPOSURE сверяют 3 агента с frontend-скиллом → UI-IMPL-PRD (реализационный PRD).
