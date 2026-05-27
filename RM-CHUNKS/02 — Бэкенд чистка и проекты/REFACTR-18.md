# REFACTR-18 — API Finder-open + soft/hard delete

> **Этап:** 02
> **Шаг:** 19 из 67
> **Зависимости:** REFACTR-14 (Project модель).
> **Следующий шаг:** REFACTR-19 (Идеи: модель + Gemini)

---

## Роли

### R-BACKEND-SURGEON
**Soul:** «Открыть в Finder» — нативная интеграция. Субпроцесс `open`, но без shell=True и без конкатенации строк. Only exec with argv.

### R-SECURITY
**Soul:** Это единственный endpoint, который спавнит нативный процесс macOS. Path traversal и command injection — приоритет номер один.

### R-DEVIL
**Soul:** Hard delete = неотменимое действие. Уверен ли пользователь? UI должен подтверждать. Но backend доверяет запросу — дополнительного confirmation здесь нет.

---

## ТРИЗ-принцип

*Принцип вложенной матрёшки.* Soft-delete (удаление из сетки) — отметка `soft_deleted_at`. Hard-delete (навсегда) — удаление записи + файлов. Две операции на одной сущности, но разные ручки.

---

## Оркестрация

**Режим:** Sequential.

---

## Микрозадачи

### 18.1 Endpoints

```
POST /api/projects/{id}/open-in-finder
Response 200: { opened: true }
Response 400: { error: "path_missing_or_invalid" }
Response 503: { error: "finder_unavailable" }  # не macOS

POST /api/projects/{id}/soft-delete
Response 200: { soft_deleted_at: ISO8601 }

POST /api/projects/{id}/restore
Response 200: { soft_deleted_at: null }

DELETE /api/projects/{id}  # hard delete
Query: ?force=true  (без этого — 409 если not soft-deleted)
Response 204
```

### 18.2 Finder-open — безопасная реализация

```python
import subprocess, os

async def open_in_finder(project_id: str) -> None:
    project = await get_project(project_id)
    if not project:
        raise HTTPException(404)
    
    folder = Path("data/projects") / project_id
    folder = folder.resolve(strict=True)
    
    # Защита от path traversal: folder должен быть внутри data/projects
    data_root = Path("data/projects").resolve()
    if not str(folder).startswith(str(data_root) + "/"):
        raise HTTPException(400, "path_invalid")
    
    if sys.platform != "darwin":
        raise HTTPException(503, "finder_unavailable")
    
    # argv без shell=True
    subprocess.Popen(["/usr/bin/open", str(folder)])
```

### 18.3 Soft-delete

```python
async def soft_delete(project_id: str):
    await update(Project).where(Project.id == project_id).values(soft_deleted_at=datetime.utcnow())
```

Видимость в `list_projects()`: по умолчанию `include_deleted=False`.

### 18.4 Hard-delete

```python
async def hard_delete(project_id: str, force: bool = False):
    project = await get_project(project_id, include_deleted=True)
    if not project:
        raise HTTPException(404)
    
    if not project.soft_deleted_at and not force:
        raise HTTPException(409, "must_soft_delete_first")
    
    # Удаляем файлы
    folder = Path("data/projects") / project_id
    if folder.exists():
        shutil.rmtree(folder)
    
    # Удаляем запись
    await db.delete(project)
```

### 18.5 Тесты

- [ ] `open-in-finder`: валидный проект → успех. Path traversal (`../etc/passwd`) → 400.
- [ ] Soft-delete → проект не виден в `list_projects()` по умолчанию.
- [ ] Restore → виден снова.
- [ ] Hard-delete без soft → 409. C soft → удалено. Файлы удалены.

### 18.6 Security-аудит этого endpoint отдельно

- [ ] Semgrep на `subprocess.*` и `os.path.*`.
- [ ] Ручная ревью: никаких `shell=True`, никакой конкатенации строк в argv.

### 18.7 Commit + Serena

---

## GATE-чекпоинт

- [ ] Все 4 endpoint работают.
- [ ] Path traversal заблокирован.
- [ ] Soft/hard разграничение работает.
- [ ] Tests зелёные.
- [ ] Semgrep по этим endpoints — 0 important findings.

---

## Артефакт на выходе

4 endpoints + тесты + security-аудит этого небольшого участка.
