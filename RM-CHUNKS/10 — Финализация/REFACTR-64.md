# REFACTR-64 — E2E сценарий 3: Перезапуск с шага X

> **Этап:** 10
> **Шаг:** 65 из 67
> **Зависимости:** REFACTR-62, REFACTR-63.
> **Следующий шаг:** REFACTR-65 (Документация)

---

## Роли

### R-QA
**Soul:** Restart — инструмент pro-пользователя. Должен быть бесшовным. Одно ошибочное удаление downstream-артефактов — инцидент.

---

## ТРИЗ-принцип

*Принцип обратной связи.* После restart — проверяем: upstream artifacts сохранены, downstream — удалены, pipeline запустился с нужной стадии.

---

## Оркестрация

**Режим:** Sequential.

---

## Микрозадачи

### 64.1 Сценарий

1. Открыть готовый проект (прошёл полный pipeline, есть рендер).
2. В Workbench timeline → клик на стадию «Генерация идей» → кнопка «Начать заново с этой стадии».
3. ConfirmModal → подтверждаем.
4. Проверяем:
   - Транскрипция — на месте (upstream).
   - Silence-cut artifact — на месте.
   - Ideas — инвалидированы (файл удалён или список очищен).
   - Clips — инвалидированы.
   - Renders — удалены.
5. Pipeline автоматически запускается с стадии ideas.
6. Идеи генерируются заново.
7. Approve → рендер → готово.

### 64.2 Сценарий 2: restart from render

1. Открыть готовый проект.
2. Restart from render (только рендер пересоберётся).
3. Проверяем: ideas сохранены, approved состояние сохранено, только clips/renders пересоздаются.
4. Должно работать быстро (без повторной транскрипции).

### 64.3 Сценарий 3: restart from transcribe (крайний)

1. Открыть проект.
2. Restart from transcribe.
3. ВСЁ удаляется кроме source_video.
4. Pipeline идёт с нуля.

### 64.4 Verification

Через API:

```bash
# До restart
ls data/projects/PROJECT_ID/*.json
ls data/projects/PROJECT_ID/clips/

# POST restart

# После restart
ls data/projects/PROJECT_ID/*.json     # upstream — на месте
ls data/projects/PROJECT_ID/clips/     # пусто (если restart from ideas/render)
```

Проверить через Serena или обычный `ls`.

### 64.5 Commit + Serena

---

## GATE-чекпоинт

- [ ] 3 сценария restart работают.
- [ ] Правильная инвалидация artifacts.
- [ ] Pipeline корректно стартует с нужной стадии.
- [ ] Результаты задокументированы.

---

## Артефакт на выходе

E2E-чеклист + результаты.
