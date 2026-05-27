# REFACTR-20 — API approve/reject/regenerate идей (с опциональным prompt)

> **Этап:** 02
> **Шаг:** 21 из 67
> **Зависимости:** REFACTR-19 (сервис идей).
> **Следующий шаг:** REFACTR-21 (VideoToolbox encode)

---

## Роли

### R-BACKEND-SURGEON
**Soul:** API идей — одна ручка на действие, минимум магии.

### R-UX-WRITER
**Soul:** Endpoint-имена должны читаться: `approve`, `reject`, `regenerate` — не `updateStatus` с enum. RESTful, но для единичных действий — action-endpoints.

---

## ТРИЗ-принцип

*Принцип обратной связи.* Каждое действие возвращает обновлённое состояние идеи. Клиент не гадает, сервер — источник правды.

---

## Оркестрация

**Режим:** Sequential.

---

## Микрозадачи

### 20.1 Endpoints

```
GET /api/projects/{pid}/ideas
Response: [ReelIdeaOut, ...]

POST /api/projects/{pid}/ideas/{idea_id}/approve
Response 200: ReelIdeaOut

POST /api/projects/{pid}/ideas/{idea_id}/reject
Response 200: ReelIdeaOut

POST /api/projects/{pid}/ideas/{idea_id}/regenerate
Body: { custom_prompt?: string }
Response 202: { job_id: string, new_idea_id: string }
```

### 20.2 Реализация

`api/routes/ideas.py`:

```python
@router.post("/{pid}/ideas/{idea_id}/approve")
async def approve_idea(pid: str, idea_id: str, service: IdeaService = Depends()):
    idea = await service.approve(pid, idea_id)
    return ReelIdeaOut.from_model(idea)

@router.post("/{pid}/ideas/{idea_id}/regenerate")
async def regenerate_idea(
    pid: str, idea_id: str,
    body: RegenerateRequest,  # { custom_prompt?: str }
    service: IdeaService = Depends(),
):
    # 1. Mark старую идею status=regenerating (для UI indicator)
    # 2. Spawn async task: сгенерировать новую с тем же контекстом транскрипта
    # 3. Новая идея: parent_idea_id = old.id, regeneration_count = old.count + 1
    # 4. Если custom_prompt задан — подставляется в промпт как доп. инструкция
    # 5. Если нет — стандартный промпт v1
    # 6. Return new_idea_id
```

### 20.3 Стандартный промпт для regenerate

`services/prompts/reel_idea_regenerate_v1.md`:
Добавляет в промпт фразу: «Предыдущая версия идеи была отклонена. Сгенерируй альтернативу. {optional custom guidance}».

### 20.4 Тесты

- [ ] Approve: статус меняется, возвращается.
- [ ] Reject: статус меняется.
- [ ] Regenerate без prompt: новая идея создана, parent_idea_id связан.
- [ ] Regenerate с custom prompt: промпт добавлен (проверяется через тест-двойник LLM-клиента).
- [ ] Approve всех → список approved готов к рендеру.

### 20.5 SSE event для regenerate

`stage=idea_regenerating, idea_id, new_idea_id` — фронт обновляет UI сам.

### 20.6 Commit + Serena + лог

### 20.7 Итог Этапа 02

- [ ] В `PIPELINE-НАВИГАТОР.md` Лог: «Этап 02 ЗАВЕРШЁН. Бэкенд проектов готов».

---

## GATE-чекпоинт

- [ ] 4 endpoints работают (GET, approve, reject, regenerate).
- [ ] Regenerate создаёт новую идею с parent-связью.
- [ ] Custom prompt корректно встраивается.
- [ ] SSE-событие передаётся.
- [ ] Tests зелёные.
- [ ] **Этап 02 ЗАВЕРШЁН.**

---

## Артефакт на выходе

4 endpoints + регенерационный промпт + тесты.
