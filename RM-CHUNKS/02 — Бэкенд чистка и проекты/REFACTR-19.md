# REFACTR-19 — Сервис генерации идей рилсов (ReelIdea + Gemini)

> **Этап:** 02
> **Шаг:** 20 из 67
> **Зависимости:** REFACTR-14 (Project), REFACTR-05 (pipeline stages).
> **Следующий шаг:** REFACTR-20 (API approve/reject/regenerate)

---

## Роли

### R-BACKEND-SURGEON
**Soul:** Сервис генерации идей — самостоятельная единица. Не смешиваем с narrative/multi-pass.

### R-PROMPT-ENG — Prompt engineer
**Профессия:** Специалист по LLM-промптингу.
**Soul:** Промпт для генерации идей — это конституция творчества рилса. Должен давать описание, хук, основной текст, таймкоды исходника.

---

## ТРИЗ-принцип

*Принцип предварительного исполнения.* До рендера — массив идей с полной структурой, которые владелец approve/reject. Рендер только для approved. Это экономит 80% вычислительных циклов.

---

## Оркестрация

**Режим:** Sequential.

---

## Микрозадачи

### 19.1 Модель ReelIdea

`models/reel_idea.py`:

```python
class IdeaStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    regenerating = "regenerating"

class ReelIdea(Base):
    id: Mapped[str]
    project_id: Mapped[str]
    
    title: Mapped[str]  # короткое название
    description: Mapped[str]  # что это за рилс и о чём
    hook: Mapped[str]  # первые 3-5 секунд
    script: Mapped[str]  # полный текст рилса (из отобранных фрагментов)
    timecodes: Mapped[list[dict]] = mapped_column(JSON)  # [{start, end, source_start, source_end}]
    
    status: Mapped[IdeaStatus] = mapped_column(default=IdeaStatus.pending)
    regeneration_count: Mapped[int] = mapped_column(default=0)
    parent_idea_id: Mapped[str | None]  # если это regenerate прошлой
    
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    
    # LLM-метаданные
    model_used: Mapped[str]  # "gemini-2.5-flash" и т.п.
    prompt_version: Mapped[int]
```

Alembic-миграция.

### 19.2 Промпт генерации

`services/prompts/reel_ideas_v1.md`:

Структура:
- Роль (копирайтер рилсов, знает paseo YouTube/Instagram).
- Контекст (транскрипция видео с таймкодами).
- Задача (сгенерировать N идей, каждая — полная карточка).
- Формат ответа (JSON schema, валидируется через `json-repair`).
- Примеры (2-3 few-shot).

### 19.3 Сервис

`services/reel_ideas_generator.py`:

```python
async def generate_ideas(
    project_id: str,
    transcript: TranscriptData,
    count: int = 8,
    model: str = "gemini-2.5-flash",
    custom_prompt: str | None = None,
) -> list[ReelIdea]:
    # 1. Build prompt with transcript context
    # 2. Call LLM via unified llm_client
    # 3. Parse JSON response (with json-repair for resilience)
    # 4. Validate via Pydantic ReelIdeaDraft
    # 5. Save to DB with status=pending
    # 6. Return
```

### 19.4 Интеграция в pipeline

В `pipeline_stages/analysis.py`:
- После multi-pass анализа транскрипта → вызов `generate_ideas()`.
- Событие в SSE: `stage=ideas_generated, count=8`.

### 19.5 Тесты

- [ ] Unit: `generate_ideas` с fake-LLM возвращает валидные ReelIdea.
- [ ] E2E smoke: реальный вызов Gemini, получение 3-5 идей (с API-ключом из `.env`).
- [ ] Resilience: LLM возвращает невалидный JSON → json-repair исправляет → парсится.

### 19.6 Commit + Serena

---

## GATE-чекпоинт

- [ ] Модель ReelIdea + миграция.
- [ ] Промпт v1 задокументирован.
- [ ] Сервис работает на реальном Gemini (с тестовым проектом).
- [ ] Идеи сохраняются в БД со статусом pending.
- [ ] Tests зелёные.

---

## Артефакт на выходе

Модель ReelIdea + сервис генерации + интеграция в pipeline + промпт v1.
