# REFACTR-53 — Settings/Processing: структурированные группы

> **Этап:** 08
> **Шаг:** 54 из 67
> **Зависимости:** REFACTR-51.
> **Следующий шаг:** REFACTR-54 (LLM + Prompts)

**ОБЯЗАТЕЛЬНО:** `frontend-design` skill активен.

---

## Роли

### R-DESIGN-ALCHEMIST
**Soul:** «Post-production как свалка» — другая боль владельца. Структурируем по подгруппам: звук / цвет / переходы / эффекты.

### R-UX-WRITER
**Soul:** Параметры post-production — это тонкие настройки. Лейблы описательные, не коды-переменных.

---

## ТРИЗ-принцип

*Принцип вложенной матрёшки.* Группа Processing содержит подгруппы (Audio, Color, Transitions, Effects). Каждая — Accordion, collapsible. Экспертный режим — показывает все, простой — только главные.

---

## Оркестрация

**Режим:** Sequential.

---

## Микрозадачи

### 53.1 Подгруппы

`/settings/processing`:

**1. Удаление тишины и филлеров**
- Включено ли (toggle).
- Порог тишины (dB, slider).
- Минимальная длина паузы для удаления (сек).
- Список филлеров (chip-list editor).

**2. Звук (аудио-обработка)**
- Нормализация громкости (LUFS target, slider).
- Шумоподавление (off / light / aggressive).
- De-esser (toggle).
- Compressor (ratio, threshold).

**3. Цвет и LUT**
- Пресет (Natural / Cinema / Vivid / Muted).
- LUT file upload (.cube).
- Saturation / contrast / brightness (slider-ы для ручной подстройки).

**4. Переходы**
- Стиль между фрагментами (cut / fade / zoom / slide).
- Ken Burns (toggle + intensity).
- Продолжительность перехода (мс).

**5. Эффекты**
- Глобальные фильтры (film grain, chromatic abberation).
- B-roll генерация (toggle + источник: nano banana / DALL-E).
- Всплывающие плашки «Подписаться» (toggle + позиция + timing).

### 53.2 UI: Accordion

Каждая подгруппа — collapsible. По умолчанию все свёрнуты, кроме первой.

Иконки слева: waveform / speaker / palette / arrow-right / sparkle.

### 53.3 Форма

Все поля autosave.

### 53.4 Экспертный / простой

REFACTR-56 добавит toggle. Здесь — пометка:
- Каждое поле имеет `complexity: 'basic' | 'advanced' | 'expert'`.
- В Simple режиме показываются только `basic`.
- В Expert режиме — все.

### 53.5 Verify frontend-design

- [ ] Accordion не прыгает при expand/collapse.
- [ ] Параметры сгруппированы по смыслу.
- [ ] Нет свалки.

### 53.6 Commit + Serena

---

## GATE-чекпоинт

- [ ] 5 подгрупп реализованы.
- [ ] Accordion работает, сохраняет expand-state в localStorage.
- [ ] Autosave работает.
- [ ] Никакой horizontal scroll.

---

## Артефакт на выходе

Settings/Processing страница.
