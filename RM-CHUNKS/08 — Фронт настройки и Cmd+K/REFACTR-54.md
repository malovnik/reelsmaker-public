# REFACTR-54 — Settings/LLM + Prompts (единый редактор с версионностью)

> **Этап:** 08
> **Шаг:** 55 из 67
> **Зависимости:** REFACTR-51.
> **Следующий шаг:** REFACTR-55 (Visuals + Integrations)

**ОБЯЗАТЕЛЬНО:** `frontend-design` skill активен.

---

## Роли

### R-DESIGN-ALCHEMIST
**Soul:** LLM + Prompts — близнецы. Одна страница, две вкладки. Не изобретаем новую страницу «Models».

### R-UX-WRITER
**Soul:** Модели показываются «по-человечески» (Gemini 2.5 Flash), не id-кодами (`gemini-2.5-flash-preview-0120`).

---

## ТРИЗ-принцип

*Принцип копирования.* Промпт = текст + метаданные. Версионируем через immutable-записи в БД (каждый save — новая version), UI показывает последнюю + history.

---

## Оркестрация

**Режим:** Sequential.

---

## Микрозадачи

### 54.1 Layout

```
/settings/llm

Tabs: [ Модели ] [ Промпты ]

--- Модели ---
Главная модель
 [ Gemini 2.5 Flash  ▾ ]  ← default
 Список: Gemini 2.5 Flash / Pro / Claude Sonnet 4.5 / Opus / GPT-5
 
Модель для регенерации идей
 [ Та же, что главная  ▾ ]
 
Температура
 [──●──────]  0.7
 
Max tokens
 [ 8192 ]
 
--- Промпты ---
Каждая стадия pipeline имеет промпт:
  • Multi-pass analysis (проход 1, 2, 3)
  • Generate ideas
  • Regenerate idea (default)
  • Subtitle fix
  • B-roll generation

Клик на название → редактор справа.

┌────────────────────┬─────────────────────────┐
│ Multi-pass pass 1  │ # system                │
│ Multi-pass pass 2  │ Ты — ...                 │
│ Multi-pass pass 3  │                          │
│ Generate ideas     │ # user                   │
│ Regenerate idea    │ {{transcript}}           │
│ Subtitle fix       │                          │
│ B-roll generation  │ # output                 │
│                    │ JSON schema: ...         │
│                    │                          │
│                    │ [ Сохранить v3 → ]      │
│                    │ История: v3 (сейчас),    │
│                    │   v2 (10 ч назад), v1    │
└────────────────────┴─────────────────────────┘
```

### 54.2 Редактор промпта

- Textarea с моноширинным шрифтом.
- Подсветка синтаксиса (простая): `{{placeholders}}` — accent, комментарии `#` — muted.
- Optionally: Monaco editor (если не тяжело для bundle).

### 54.3 Версионность

- При save → backend создаёт новую запись с `version = prev + 1`.
- UI показывает «v3» после save.
- История: click → показывает diff.
- Rollback: кнопка «Откатить к v1».

### 54.4 Verify frontend-design

- [ ] Не перегружено.
- [ ] Diff понятен (side-by-side или unified с highlight).
- [ ] Подсветка синтаксиса работает.

### 54.5 Commit + Serena

---

## GATE-чекпоинт

- [ ] Вкладки Модели/Промпты работают.
- [ ] Редактор промптов — редактирует и сохраняет.
- [ ] История версий видна, rollback работает.
- [ ] Модели в human-readable names.

---

## Артефакт на выходе

Settings/LLM страница с двумя вкладками + редактор промптов.
