# REFACTR-55 — Settings/Visuals + Integrations

> **Этап:** 08
> **Шаг:** 56 из 67
> **Зависимости:** REFACTR-51.
> **Следующий шаг:** REFACTR-56 (Device + expert mode)

**ОБЯЗАТЕЛЬНО:** `frontend-design` skill активен.

---

## Роли

### R-DESIGN-ALCHEMIST
**Soul:** Visuals — это Brand + B-roll + шаблоны плашек. Один настроечный center, не раскиданный.

### R-SECURITY (консультативно)
**Soul:** Integrations = API keys. Ключ никогда не возвращается в response. Ввод через password-input, после save — маска (`****`).

---

## ТРИЗ-принцип

*Принцип перехода в другое измерение.* Settings/Visuals — не только тексты-цвета, а всё визуальное. Settings/Integrations — отдельная страница, потому что семантически API-keys ≠ визуалка.

---

## Оркестрация

**Режим:** Sequential.

---

## Микрозадачи

### 55.1 Settings/Visuals

Подгруппы (accordion):

**Brand kit**
- Логотип (upload).
- Цвета бренда (color-pickers, 3-5 цветов).
- Шрифты для плашек.

**Плашки «Подписаться»**
- Шаблон (список пресетов).
- Позиция на кадре.
- Timing (когда появляется, сколько висит).
- Custom text.

**B-roll**
- Источник: Gemini nano banana / DALL-E / OpenAI Image / Flux.
- Разрешение: 1024×1024 / 1024×576 / 576×1024 (для вертикали).
- Частота: каждые N секунд (slider).

### 55.2 Settings/Integrations

```
API-ключи

┌────────────────────────────────────────┐
│ Gemini (Google)                        │
│ [ ●●●●●●●● установлен ]  [ Обновить ]   │
│ Статус: ✓ рабочий (проверено 5 мин назад)│
├────────────────────────────────────────┤
│ Deepgram (транскрипция)                 │
│ [ не установлен ]         [ Добавить ]   │
│ Опционально. Альтернатива — MLX-Whisper │
├────────────────────────────────────────┤
│ Anthropic Claude                       │
│ [ ●●●●●●●● установлен ]  [ Обновить ]   │
├────────────────────────────────────────┤
│ OpenAI                                 │
│ [ не установлен ]         [ Добавить ]   │
└────────────────────────────────────────┘

Пути к папкам

Выходные клипы:  data/projects/{id}/renders (default)
 [ Изменить ]

Uploads:         data/uploads (default)
 [ Изменить ]
```

### 55.3 API key UX

- Backend отдаёт только `has_key: bool` + `last_used_at`.
- Input type="password".
- После save — placeholder `●●●●●●●●` + кнопка «Обновить».
- Health-check: кнопка «Проверить» → backend делает тестовый запрос → возвращает статус.

### 55.4 Verify frontend-design

- [ ] Password-fields не утекают (инспектор браузера не видит значение после save).
- [ ] Health-status читается с первого взгляда.
- [ ] Папки выглядят как действительно пути (моноширинный шрифт).

### 55.5 Commit + Serena

---

## GATE-чекпоинт

- [ ] 2 страницы реализованы (Visuals + Integrations).
- [ ] Brand kit работает.
- [ ] B-roll настройки сохраняются.
- [ ] API-keys — защищены, health-check работает.
- [ ] Пути к папкам меняются.

---

## Артефакт на выходе

Settings/Visuals + Settings/Integrations.
