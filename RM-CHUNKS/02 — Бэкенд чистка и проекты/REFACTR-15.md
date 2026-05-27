# REFACTR-15 — API автосохранения настроек проекта

> **Этап:** 02
> **Шаг:** 16 из 67
> **Зависимости:** REFACTR-09 (ADR autosave), REFACTR-14 (модель Project).
> **Следующий шаг:** REFACTR-16 (API перезапуска с шага)

---

## Роли

### R-BACKEND-SURGEON
**Soul:** API — договор с клиентом. Ни одного лишнего поля, ни одного отсутствующего. HTTP-коды по делу.

### R-SECURITY (консультативно)
**Soul:** Автосейв принимает весь snapshot целиком. Валидация Pydantic не должна позволить инъекцию через обход схемы.

---

## ТРИЗ-принцип

*Принцип «сделай наоборот».* Вместо PATCH (слияние по полям) используем PUT (полный snapshot). Это устраняет классы багов «устаревшее поле в merge» и упрощает ETag-версионирование.

---

## Оркестрация

**Режим:** Sequential.

---

## Микрозадачи

### 15.1 Endpoint спецификация

```
PUT /api/projects/{project_id}/settings
Headers:
  If-Match: <last_saved_at ISO8601>  (optional, для conflict detection)
Body: ProjectSettingsSnapshot (Pydantic)
Response 200: { project: ProjectOut, etag: <new last_saved_at> }
Response 409: { error: "conflict", current: ProjectSettingsSnapshot, etag }
Response 422: { error: "validation", details: [...] }
```

### 15.2 Реализация handler

`api/routes/projects.py`:

```python
@router.put("/{project_id}/settings")
async def update_settings(
    project_id: str,
    payload: ProjectSettingsSnapshot,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
    service: ProjectService = Depends(),
):
    project = await service.get_project(project_id)
    if not project:
        raise HTTPException(404)
    
    if if_match and project.last_saved_at.isoformat() != if_match:
        return JSONResponse(
            status_code=409,
            content={"error": "conflict", "current": current_snapshot, "etag": project.last_saved_at.isoformat()},
        )
    
    updated = await service.update_settings(project_id, payload)
    return {"project": ProjectOut.from_model(updated), "etag": updated.last_saved_at.isoformat()}
```

### 15.3 GET для снятия snapshot

```
GET /api/projects/{project_id}/settings
Response 200: { settings: ProjectSettingsSnapshot, etag }
```

### 15.4 Тесты

- [ ] Happy path: создать проект → PUT snapshot → GET → получен тот же snapshot.
- [ ] Conflict: PUT с устаревшим If-Match → 409.
- [ ] Validation: PUT с невалидной схемой → 422 с деталями.
- [ ] Ratelimit: убедиться что API не падает при 100 PUT/сек (для автосейв).

### 15.5 Verification

- [ ] `curl -X PUT ...` с JSON — работает.
- [ ] Логи backend показывают сохранение + обновление `last_saved_at`.

### 15.6 Commit + лог

### 15.7 Serena memory

---

## GATE-чекпоинт

- [ ] Endpoint работает: PUT/GET проверены `curl`-ом.
- [ ] Conflict detection работает (верифицирован тестом).
- [ ] Валидация Pydantic отсекает мусор.
- [ ] Tests зелёные.

---

## Артефакт на выходе

`PUT /api/projects/{id}/settings` + `GET /api/projects/{id}/settings` + тесты.
