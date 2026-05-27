# REFACTR-51 — Новая IA настроек: группы и навигация

> **Этап:** 08 — Фронт: настройки и Cmd+K
> **Шаг:** 52 из 67
> **Зависимости:** REFACTR-02 (инвентаризация), REFACTR-32 (principles).
> **Следующий шаг:** REFACTR-52 (Settings/Subtitles)

**ОБЯЗАТЕЛЬНО:** `frontend-design` skill активен.

---

## Роли

### R-DESIGN-ALCHEMIST
**Soul:** Информационная архитектура — это план города. Пустые улицы ни к чему не ведут, глухие переулки путают. Каждый пункт в меню настроек — должен вести к нужному.

### R-UX-WRITER
**Soul:** Названия групп — на русском, по смыслу. «LLM» — OK (tech-жаргон), «Запись» — лучше, чем «Transcription».

---

## ТРИЗ-принцип

*Принцип объединения.* Старые 8 страниц настроек → 6-7 групп по смыслу. Одинаковые настройки не дублируются.

---

## Оркестрация

**Режим:** Sequential.

---

## Микрозадачи

### 51.1 Финальная IA

(Из REFACTR-02 предварительная, здесь — окончательная)

```
/settings/
    запись/            ← Транскрипция (провайдер, модель, VAD)
    обработка/         ← Silence, filler, multi-pass LLM
    визуал/            ← B-roll, переходы, Ken Burns, color, LUT
    субтитры/          ← Стиль, позиция, font
    llm/               ← Модели (main + fallback) + промпты
    интеграции/        ← API keys (Deepgram, Gemini, Anthropic, OpenAI)
    устройство/        ← темы, expert/simple mode, hotkeys
```

### 51.2 Route structure

`src/routes/settings/` (обновить):

```
settings/
    __root.tsx         → SettingsLayout
    index.tsx          → редирект на /settings/recording
    recording.tsx
    processing.tsx
    visuals.tsx
    subtitles.tsx
    llm.tsx
    integrations.tsx
    device.tsx
```

### 51.3 SettingsLayout

```
┌─────────────────────────────────────────────────┐
│ (TopBar общий)                                  │
├────────────┬────────────────────────────────────┤
│ [sidebar]  │ Active section                     │
│            │                                    │
│ Настройки  │                                    │
│  Запись    │                                    │
│  Обработка │                                    │
│  Визуал    │                                    │
│  Субтитры  │                                    │
│  LLM       │                                    │
│  Интеграции│                                    │
│  Устройство│                                    │
│            │                                    │
└────────────┴────────────────────────────────────┘
```

- **Sidebar вертикальный**, никакой горизонтальной прокрутки.
- Active pill — accent-muted bg.
- Иконка + label.

### 51.4 Редирект старых маршрутов

Чтобы не ломать bookmarks:
- `/settings/brand` → `/settings/visuals`.
- `/settings/models` → `/settings/llm`.
- `/settings/prompts` → `/settings/llm` с anchor.
- `/settings/connections` → `/settings/integrations`.
- `/settings/subtitles` → `/settings/subtitles` (остаётся).
- `/settings/profiles` → `/settings/processing`.
- `/settings/performance` → `/settings/device`.
- `/settings/post-production` → `/settings/processing` и `/settings/visuals` (split по темам).

TanStack Router redirect-route:
```tsx
createFileRoute('/settings/brand')({
  beforeLoad: () => { throw redirect({ to: '/settings/visuals' }); },
});
```

### 51.5 Общий header страницы

Каждая settings-страница начинается с:
- `h1` — название группы.
- Краткое описание (1 строка text-secondary).
- Индикатор «Сохранено» / «Сохраняю…» (REFACTR-15 autosave).

### 51.6 Ширина контента

Settings — одна колонка, max-width 760 px. Формы читаемы, не растягиваются.

### 51.7 Verify frontend-design

- [ ] Sidebar вертикальный, никакой h-scroll.
- [ ] Sections — содержимое читаемо (не сжато).
- [ ] Active section — clear visual.

### 51.8 Commit + Serena

---

## GATE-чекпоинт

- [ ] 7 групп настроек в sidebar.
- [ ] Все старые URL редиректят на новые.
- [ ] Активная секция — visible.
- [ ] Каждая секция открывается.
- [ ] Горизонтальной прокрутки нигде нет (тест на 1280 px).

---

## Артефакт на выходе

SettingsLayout + редирект-роуты + заготовки 7 settings-страниц.
