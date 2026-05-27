# REFACTR-14 — Миграция модели Project (settings_snapshot, stage_progress)

> **Этап:** 02
> **Шаг:** 15 из 67
> **Зависимости:** REFACTR-08 (ADR storage), REFACTR-13 (PRO удалён).
> **Следующий шаг:** REFACTR-15 (API автосохранения)

---

## Роли

### R-BACKEND-SURGEON
**Soul:** Структура Project меняется один раз. Делаем правильно, потом не трогаем.

### R-DATA-ARCHITECT
**Soul:** JSON-поля — гибкость. Но их схема должна валидироваться Pydantic-ом на API-границе. Иначе JSON-blob превращается в помойку за 3 месяца.

---

## ТРИЗ-принцип

*Принцип разделения противоречия во времени.* БД хранит метаданные (id, timestamps, связи), JSON-файл хранит изменяющиеся настройки. Разделение повышает перфоманс БД и делает настройки инспектируемыми.

---

## Оркестрация

**Режим:** Sequential.

---

## Микрозадачи

### 14.1 Определить Pydantic-схемы

Создать `models/project_settings_schema.py`:

```python
class TranscriptionSettings(BaseModel):
    provider: Literal["mlx-whisper", "deepgram"] = "mlx-whisper"
    model: str = "large-v3"
    word_timestamps: bool = True

class ProcessingSettings(BaseModel):
    remove_silence: bool = True
    filler_words: list[str] = [...]
    # ...

class ProjectSettingsSnapshot(BaseModel):
    version: int = 1
    transcription: TranscriptionSettings
    processing: ProcessingSettings
    visuals: VisualsSettings
    subtitles: SubtitlesSettings
    llm: LLMSettings
    brand: BrandSettings
    profile_id: str  # "viral-2026" | "chapter-legacy"
```

### 14.2 Модель Project

Обновить SQLAlchemy:

```python
class Project(Base):
    id: Mapped[str]
    name: Mapped[str]
    created_at: Mapped[datetime]
    last_saved_at: Mapped[datetime]
    soft_deleted_at: Mapped[datetime | None]
    source_video_path: Mapped[str]
    
    settings_snapshot_path: Mapped[str]  # path к data/projects/{id}/settings.json
    stage_progress: Mapped[dict] = mapped_column(JSON, default=dict)
    
    parent_project_id: Mapped[str | None]
```

### 14.3 Alembic миграция

- [ ] `alembic revision --autogenerate -m "project snapshot model"`.
- [ ] Редактировать миграцию:
  - Добавить новые поля с defaults.
  - Backfill: для существующих проектов сгенерировать `settings.json` из всех связанных stores (brand, subtitles, prompts и т.п.).
  - Прописать downgrade.

### 14.4 Service layer

`services/project.py` (или новый файл):

- `create_project(name, video_path, profile_id) -> Project`
- `get_project(id) -> Project | None`
- `list_projects(include_deleted=False) -> list[Project]`
- `update_settings(id, settings: ProjectSettingsSnapshot) -> Project`
- `soft_delete(id) -> None`
- `hard_delete(id) -> None`
- `restore(id) -> Project`

Под капотом: SQLAlchemy для БД + файловые операции для `settings.json`.

### 14.5 Тесты

- [ ] `test_project_crud.py`: CRUD + snapshot roundtrip.
- [ ] `test_project_migration.py`: миграция с существующими проектами — ни один не потерян.

### 14.6 Verification

- [ ] `alembic upgrade head` без ошибок.
- [ ] Существующие проекты продолжают открываться.
- [ ] Новый проект создаётся и `data/projects/{id}/settings.json` появляется.

### 14.7 Commit + лог

### 14.8 Serena memory

---

## GATE-чекпоинт

- [ ] Pydantic-схемы описаны и проходят mypy.
- [ ] Миграция применяется и откатывается.
- [ ] Все существующие проекты мигрированы (количество совпадает до/после).
- [ ] Tests зелёные.
- [ ] Новый проект создаёт корректную структуру на диске.

---

## Артефакт на выходе

Обновлённая модель Project + Alembic migration + schema-файл + service.
