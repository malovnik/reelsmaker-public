# REFACTR-17 — API копирования настроек из проекта Y

> **Этап:** 02
> **Шаг:** 18 из 67
> **Зависимости:** REFACTR-14 (Project модель), REFACTR-15 (PUT settings).
> **Следующий шаг:** REFACTR-18 (Finder-open + delete)

---

## Роли

### R-BACKEND-SURGEON
**Soul:** Копирование настроек — самый запрашиваемый UX-шорткат. Владелец назвал: «быстренько раз нажал, скопировал настроечки сразу».

### R-UX-WRITER
**Soul:** API endpoint — это не только машина, это контракт. Ответ должен содержать `diff` (какие настройки реально скопировались), чтобы UI мог показать «эти 17 настроек применены».

---

## ТРИЗ-принцип

*Принцип изменения окраски.* Старое → новое: одна и та же настройка, но в контексте нового проекта. Исключение: `source_video_path`, `name`, `created_at` — не копируются.

---

## Оркестрация

**Режим:** Sequential.

---

## Микрозадачи

### 17.1 Два сценария

**Сценарий A:** «Скопировать настройки последнего предыдущего проекта» — для нового проекта, когда создаётся.

**Сценарий B:** «Выбрать конкретный проект Y из picker» — явный выбор.

### 17.2 Endpoint

```
POST /api/projects/{project_id}/settings/copy-from
Body: { source_project_id: string }
Response 200: {
  project: ProjectOut,
  etag: string,
  copied_fields_count: int,
  ignored_fields: ["source_video_path", "name", ...]
}
```

Альтернативно, при создании нового проекта — `POST /api/projects` с опциональным `copy_settings_from_project_id` в body.

### 17.3 Service

```python
async def copy_settings(target_id: str, source_id: str) -> CopyResult:
    source = await get_project(source_id)
    target = await get_project(target_id)
    source_snapshot = load_snapshot(source)
    
    # Clone settings, but drop project-specific fields
    new_snapshot = source_snapshot.model_copy(deep=True)
    # нет project-specific полей в ProjectSettingsSnapshot — они все в модели Project,
    # а не в snapshot'е. Но есть исключения:
    new_snapshot.brand.logo_overrides_per_project = None  # если такое есть
    
    await save_snapshot(target, new_snapshot)
    return CopyResult(copied_fields=[...], ignored_fields=[...])
```

### 17.4 UI helper endpoint

Для picker'а:

```
GET /api/projects?for_copy=true&limit=20
Response: [{id, name, last_saved_at, preview_thumb_url}, ...]
```

Сортировка по `last_saved_at DESC`.

### 17.5 Тесты

- [ ] Копирование в чистый проект — все настройки равны источнику.
- [ ] Копирование в проект с существующими настройками — перезаписывает (семантика replace, не merge).
- [ ] Source не существует — 404.

### 17.6 Verification + Commit + Serena

---

## GATE-чекпоинт

- [ ] Endpoint работает в обоих сценариях (A и B).
- [ ] Picker-endpoint возвращает список проектов с превью.
- [ ] Tests зелёные.
- [ ] Копирование идемпотентно (дважды вызвать — тот же результат).

---

## Артефакт на выходе

`POST /api/projects/{id}/settings/copy-from` + `GET /api/projects?for_copy=true` + тесты.
