# REFACTR-08 — ADR: Хранение данных (SQLite + project.json)

> **Этап:** 01
> **Шаг:** 9 из 67
> **Зависимости:** REFACTR-04 (схема данных).
> **Следующий шаг:** REFACTR-09 (ADR: Автосохранение)

---

## Роли

### R-ARCHITECT
**Soul:** Данные — долгожитель системы. Стек можно менять, миграции — тяжело откатывать. Решение по storage влияет на 5 лет вперёд.

### R-DATA-ARCHITECT
**Профессия:** Data engineer для локальных приложений.
**Soul:** Для single-user локалки SQLite — оптимум. Но есть нюансы: снимки настроек проекта должны быть read-only (immutable) по принципу event sourcing, иначе «перезапустить с шага X» не будет работать детерминированно.

---

## ТРИЗ-принцип

*Принцип асимметрии.* «Горячие» данные (текущие настройки проекта) — в SQLite. «Холодные» / «иммутабельные» артефакты pipeline — в файлах `data/artifacts/{project}/{stage}.json`. Разделение по частоте изменений, а не по типу.

---

## Оркестрация

**Режим:** Sequential + Sequential Thinking.

---

## Микрозадачи

### 08.1 Варианты storage

**Вариант A: Всё в SQLite (включая snapshots)**
- + одна точка правды
- − JSON blob-ы раздувают БД

**Вариант B: SQLite (мета) + JSON-файлы (snapshots)**
- + лёгкая БД, снапшоты инспектируются текстом
- − синхронизация

**Вариант C: Plain-JSON files + SQLite index**
- + максимум портируемости
- − сложнее транзакции

### 08.2 Sequential Thinking

- [x] Проанализировать размер snapshots (≈50-150 КБ на проект: 11 таблиц настроек объединены в JSON).
- [x] Проанализировать частоту записи (до 6 ops/min на активный проект при autosave 10 с; stage_progress — 10+ раз за стадию).
- [x] Вердикт: **Вариант B** — оптимален. Расширен: введён per-run immutable snapshot (`runs/{run_id}/settings.json`) для детерминизма restart-from-stage.

### 08.3 Спроектировать таблицу Project

```python
class Project(Base):
    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    created_at: Mapped[datetime]
    last_saved_at: Mapped[datetime]
    soft_deleted_at: Mapped[datetime | None]
    source_video_path: Mapped[str]
    
    settings_snapshot_path: Mapped[str]  # data/projects/{id}/settings.json
    stage_progress: Mapped[dict] = mapped_column(JSON)  # per-stage status
    
    parent_project_id: Mapped[str | None]  # если скопирован из Y
    profile_id: Mapped[str]  # "viral-2026" | "chapter-legacy"
```

### 08.4 Спроектировать структуру `data/projects/{id}/`

```
data/projects/{project_id}/
    settings.json          # настройки (полный снапшот)
    stage-progress.json    # детальный прогресс pipeline
    transcript.json        # артефакт стадии transcribe
    ideas.json             # список ReelIdea
    clips/                 # готовые клипы
    renders/               # финальные MP4
```

### 08.5 Миграция существующих проектов

- [x] Проверить, есть ли в БД проекты сейчас — **`projects = 0`**, `jobs WHERE project_id IS NOT NULL = 0` (sqlite3 check, 2026-04-24). Greenfield-сценарий.
- [x] План миграции: Alembic revision `add_project_extended_columns` (формализован в ADR-0002 §Миграция):
  - Добавляет 7 колонок в `projects` (source_video_path, settings_snapshot_path, stage_progress, last_saved_at, soft_deleted_at, parent_project_id, profile_id) + `run_id` в `jobs`.
  - Экспорт существующих настроек НЕ требуется (проектов нет).
  - Существующие 50 legacy-jobs остаются с `project_id IS NULL` — UI-фильтр REFACTR-39 показывает их вкладкой «Нарезки без проекта».

### 08.6 Написать ADR

`docs/adr/0002-data-storage.md`.

### 08.7 Serena memory

- [x] `write_memory(name="refactr-08-adr-data-storage", content="...")`.

---

## GATE-чекпоинт

- [x] ADR-0002 создан и принят (status ACCEPTED).
- [x] Схема Project на уровне Python-типов зафиксирована (12 полей, включая UUID PK, JSON stage_progress, FK parent_project_id).
- [x] План миграции существующих данных описан (greenfield: `projects=0`, 9 ALTER TABLE statements + 1 CREATE INDEX).
- [x] **Gate с человеком:** подход сматчен с task.md §2.8 (settings_snapshot + stage_progress). Расширен per-run immutable snapshot для детерминизма restart — архитектурное усиление, не противоречащее требованиям.

---

## Артефакт на выходе

`docs/adr/0002-data-storage.md`.
