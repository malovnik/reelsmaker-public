# FRONTEND-AUDIT — аудит существующего фронтенда (Phase 8)

> Консолидация 5 сварм-агентов: usability / visual / friendliness / stability / code-health. Вход для редизайна (Phase 9).
> Отчёты: [fa-1 usability](agent-reports/fa-1-usability.md) · [fa-2 visual](agent-reports/fa-2-visual-design.md) · [fa-3 friendliness](agent-reports/fa-3-friendliness.md) · [fa-4 stability](agent-reports/fa-4-stability.md) · [fa-5 code-health](agent-reports/fa-5-code-health.md)

## ГЛАВНЫЙ ВЫВОД (критично для Phase 9)
Визуальный дизайн — **характерный, верхние 10-15%, НЕ AI-slop**: полноценная OKLCH-токен-система (warm-indigo hue 280 + одна gold-amber акцентная точка), кинематографические слои (vignette, SVG-grain, warm тени, conic score-ring), семантическая типографика (Geist + JetBrains mono-caps + Inter, self-hosted), анти-клишейный копирайтинг. **Это работа со вкусом — DNA стоит сохранить.**
Проблема НЕ в эстетике, а в **структуре и UX**: две конфликтующие системы токенов, дублирование навигации, нет 2 режимов, нет онбординга, нет UI-примитивов, нет error boundaries.
→ Редизайн «кардинально другой» правильно читать как: **сохранить визуальную ДНК, радикально переработать архитектуру UX (2 режима, единые токены, примитивы, онбординг, подсказки везде).**

## P0 — блокеры для 2 режимов
| ID | Проблема | Источник |
|----|----------|----------|
| U-01 | Две несовместимые системы токенов (`--ink/--gold/--paper` тёмная vs `--surface/--accent-primary` светлая) смешаны в одном файле; хардкод stone-* | usability |
| U-02 | Навигация дублирована: NavRail выносит 6/8 settings как top-level + SettingsSubNav со всеми 8; нет единой «Настройки»; brand/maintenance недостижимы из рейла | usability |
| U-03 | Главный «визард» — не мастер, а одна длинная форма со всеми опциями сразу (макс. когнитивная нагрузка) | usability |
| FA3-01 | Нет инфраструктуры под Эксперт/Пошаговый: нет `<Tooltip>`, нет `UiModeContext` | friendliness |
| FA4-P0-01 | Ноль React Error Boundary во всём приложении → любой throw = белый экран | stability |
| FA4-P0-02 | lazy ProjectFolderPage в Suspense без error-обработки → rejection чанка = белый экран | stability |

## P1
| ID | Проблема |
|----|----------|
| FA3-02 | Сырые тех-ошибки утекают юзеру (`Ошибка 500: {"detail"...}`, JSON.stringify в 6+ местах) — нужен `humanizeError()` |
| FA3-03 | Нет тост-системы; деструктив через нестилизованный `window.confirm` (13 мест) |
| VD-02 | Галерея рилсов max `sm:grid-cols-2` — на десктопе 1400px+ пустые поля |
| VD-03 | Действия карточек скрыты за `opacity-0 group-hover` → недоступны на тач |
| VD-01 | grain-overlay рендерится дважды (index.html + AppShell) |
| FA4-P1-01 | SSE: нечищеный reconnect-таймер в финальном событии (утечка EventSource) |
| FA5-perf | Бандл 705KB/191KB gzip одним чанком, code-split только ProjectFolderPage |
| code-health | Нет слоя UI-примитивов (Button/Card/Input/Modal) — главный множитель стоимости перевёрстки |

## P2/P3
VD-04 модалки без max-h/overflow · VD-05 162× text-[11px] vs «17px-философия» · VD-06 два словаря токенов · VD-07 контраст --mute близко к AA · FA3-04 машинные имена gemini/zhipu в селектах · U-09 inconsistency кнопок · U-10/FA3 нет онбординга/first-run · touch-таргеты 36px (<44px) · 5 God-компонентов (CampaignDetailClient 878 LOC).

## Состояние по осям
- **Юзабилити:** эксперту почти удобно, новичку нет (первый экран на эксперта). Auto-режим+SSE+done-CTA — зародыш «Пошагового».
- **Дизайн:** характерный, адаптив реально работает (образцовый drawer NavRail). Дыры: hover-only на тач, узкая сетка, мелкий текст.
- **Дружелюбность:** онбординг 6/10 (имплицитный есть, явного нет); подсказки ~70% неравномерно (settings ~100% через обязательный `hint`-проп примитивов; job/reel ~30%; навигация 0%).
- **Стабильность:** нет error boundaries (P0), SSE надёжна кроме 1 утечки, остальное defensive.
- **Код:** готовность к редизайну СРЕДНЕ (ближе к лёгкому). Логика и презентация разделены частично-систематически; бизнес-логика переживёт редизайн нетронутой; работа — в перевёрстке + аддитивная тема + UI-примитивы.

## Сохранить без стыда (вход для Phase 9)
OKLCH-токен-система + философия одного акцента, кинематографические слои, mono-caps навигация, drawer-адаптив, variable-шрифты, анти-slop копирайтинг, focus-ring + prefers-reduced-motion, settings-примитивы с обязательным hint, PipelineTimeline/прогресс, data-слой (loaders + типобезопасный api).

## Фундамент для редизайна (архитектурные предусловия)
1. Единая система токенов (свести U-01/VD-06).
2. Слой `components/ui/` примитивов (Button/Card/Input/Modal/Tooltip).
3. `UiModeContext` (Пошаговый/Эксперт) + переключатель в shell.
4. Error Boundary вокруг Outlet + Suspense-fallback с retry.
5. Тост-система + `humanizeError()`.
6. Route-level `lazy()` split.
7. Онбординг/first-run.
