# REFACTR-56 — Settings/Device + режимы Simple/Expert

> **Этап:** 08
> **Шаг:** 57 из 67
> **Зависимости:** REFACTR-51..55.
> **Следующий шаг:** REFACTR-57 (Cmd+K)

**ОБЯЗАТЕЛЬНО:** `frontend-design` skill активен.

---

## Роли

### R-DESIGN-ALCHEMIST
**Soul:** Simple mode = пустая стена с нужными кнопками. Expert mode = pro-инструмент. Пользователь сам решает.

### R-UX-WRITER
**Soul:** «Простой» и «Экспертный» — владелец назвал «мальчиковый и экспертный». В UI — нейтральные «Простой» / «Экспертный».

---

## ТРИЗ-принцип

*Принцип копирования.* Каждое поле настроек уже имеет complexity (REFACTR-53). Глобальный toggle «режим» переключает видимость.

---

## Оркестрация

**Режим:** Sequential.

---

## Микрозадачи

### 56.1 Settings/Device

Секции:

**Тема**
- System / Dark / Light (Radio или Segmented).
- (Уже реализовано в REFACTR-37 как ThemeSwitcher — здесь вторая точка доступа).

**Режим интерфейса**
- Простой (показываются ключевые настройки).
- Экспертный (все настройки).
- Toggle + описание разницы.

**Горячие клавиши**
- Список текущих shortcuts (read-only в v1, custom bindings — future).
- Cmd+K открыть command palette.
- N новый проект.
- / фокус поиск.
- A/R/G в grid идей.

**Язык интерфейса**
- Только «Русский» (v1).
- Placeholder для future (English).

**Логи**
- Уровень: info / debug.
- Расположение: `data/logs/`.

### 56.2 Complexity attribute

В `ProjectSettingsSnapshot` и runtime-settings — для каждого поля:
```ts
fieldMeta: {
  pipelineMode: { complexity: 'basic' },
  compressor.ratio: { complexity: 'advanced' },
  videotoolbox.qv: { complexity: 'expert' },
}
```

В UI — фильтр по этому атрибуту:
- Simple: показываем `basic`.
- Expert: показываем все.

### 56.3 Persist

Выбор режима → localStorage `videomaker-ui-mode` + backend sync.

### 56.4 Toggle

В Settings/Device:
```
Режим интерфейса
┌────────────────────────────────────┐
│ [ Простой ] [ Экспертный ]          │
│ Экспертный показывает все параметры │
│ pipeline и кодека.                  │
└────────────────────────────────────┘
```

### 56.5 Verify frontend-design

- [ ] Переключение не скрывает primary CTA ни в одной странице.
- [ ] Expert-режим не пугает плотностью — всё так же читаемо.

### 56.6 Commit + Serena

---

## GATE-чекпоинт

- [ ] Settings/Device работает.
- [ ] Toggle Simple/Expert реально меняет видимость полей (проверено на Processing и Visuals).
- [ ] Persist работает.
- [ ] Hotkeys лист отображается.

---

## Артефакт на выходе

Settings/Device + UI-mode глобальный + complexity-attribute система.
