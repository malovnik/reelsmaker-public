# ADR-0002 — Хранение данных: SQLite (мета + hot-state) + JSON (snapshots + артефакты)

- **Статус:** ACCEPTED
- **Дата:** 2026-04-24
- **Авторы:** R-ARCHITECT (ведущий), R-DATA-ARCHITECT
- **Контекст чанка:** `RM-CHUNKS/01 — Архитектурные решения/REFACTR-08.md` (шаг 9/67)
- **Связано с:** ADR-0001 (фронт-стек), ADR-0003 (autosave — следующий REFACTR-09), REFACTR-14 (расширение ProjectRow), REFACTR-16 (restart-from-stage), REFACTR-43 (copy-from-project).

---

## Контекст

`videomaker` — локальное single-user приложение на MacBook Pro M5 (24 GB RAM). Хранилище уже существует в виде SQLite (`data/videomaker.db`) + файлового дерева `data/{uploads,proxies,artifacts,transcripts,thumbnails,...}`.

Ключевые факты из `docs/audit/04-data-schema.md` и прямой проверки (`sqlite3` на 2026-04-24):

- **12 прикладных таблиц** + `alembic_version`, HEAD `eb6d1b814c95`, линейная add-only Alembic-цепочка.
- **`projects = 0` записей**. **`jobs` с `project_id IS NOT NULL` = 0**. Все 50 существующих jobs (31 done + 19 error) исторические, без привязки к проекту.
- **11 таблиц настроек** (EAV + preset-паттерн): `runtime_settings` (87 строк, EAV), `brand_kit`, `post_production_presets`, `subtitle_style_presets`, `vision_settings`, `prompts`, `profile_masks`, `scheduler_campaigns`, `account_profiles`, `caption_presets`, `schedule_assignments`.
- **Файловое хранилище 36 ГБ**: uploads 15 ГБ, proxies 9.7 ГБ, artifacts 6.9 ГБ, models 3.5 ГБ, thumbnails/caches 345 МБ.
- Папка `data/projects/` **отсутствует** (будет создана этим решением).

Требования, накопленные в этапах 00 и 01:

1. **Autosave** настроек проекта каждые 10 с (task.md §2.6, REFACTR-09). → Write-частота: до 6 ops/min на один активный проект.
2. **Restart-from-stage X** должен быть детерминированным (UX-боль #8, REFACTR-16). → Настройки на момент старта pipeline-run должны быть immutable.
3. **Copy-from-another-project** (task.md §2.4, REFACTR-43). → Нужен parent_project_id и надёжный import snapshot.
4. **Soft-delete / Hard-delete** проектов (task.md §2.4). → `soft_deleted_at` timestamp + физическое удаление по запросу.
5. **Инспектируемость snapshot** — владелец должен иметь возможность открыть файл и посмотреть настройки проекта.
6. **Git-friendly backup** — snapshot можно закоммитить в личный backup-repo.
7. **Portability** — перенос проекта на другую машину должен быть tarball-ом папки `data/projects/{id}/`.

---

## Decision Drivers

1. **Асимметрия частоты изменения данных.** Stage-progress обновляется каждые 1–10 с при рендере; settings при autosave каждые 10 с при активной работе; snapshot в per-run копии создаётся один раз на job-запуск. Разные режимы требуют разного storage.
2. **Детерминизм restart.** Frozen immutable snapshot per run — обязательное условие.
3. **БД остаётся маленькой.** SQLite на 36 ГБ диска — ≤50 МБ включая все метаданные, чтобы `VACUUM` / backup / migration оставались быстрыми.
4. **Transaction safety при write-heavy autosave.** SQLite single-writer blocks concurrent writes; частый autosave (10 с) не должен блокировать SSE-polling читатели.
5. **Простота инспекции и backup.** JSON открывается `cat`, diff'ится `git diff`, архивируется `tar czf`.
6. **Совместимость со всеми 11 таблицами настроек.** Снапшот должен сериализовать их все единообразно.

---

## Рассмотренные варианты

### Вариант A — Всё в SQLite (JSON blob-колонка + таблица ProjectSnapshot для версий)

**Схема:**
```python
class Project(Base):
    id: Mapped[str] = mapped_column(primary_key=True)
    settings_snapshot: Mapped[dict] = mapped_column(JSON)  # blob
    stage_progress: Mapped[dict] = mapped_column(JSON)

class ProjectSnapshot(Base):  # версии
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[str]
    run_id: Mapped[str]
    snapshot_data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime]
```

**FOR:**
- Транзакционность: atomic commit settings + stage_progress в одной транзакции.
- JOIN-friendly: `SELECT p.*, s.snapshot_data FROM projects p JOIN snapshots s`.
- Alembic покрывает миграции схемы.

**AGAINST:**
- **БД раздувается.** 100 проектов × 10 run-snapshot'ов × 100 КБ = 100 МБ в БД. SQLite `VACUUM` не запускается автоматически; свободное место накапливается. Backup БД становится медленным.
- **Блокировки autosave.** SQLite — single-writer. Если pipeline пишет stage_progress и параллельно UI сохраняет settings — writer-блокировка создаёт латентность. WAL-mode смягчает, но не устраняет.
- **JSON-blob неинспектируем.** Чтобы посмотреть settings проекта, нужен `sqlite3 -cmd ".mode line" db "SELECT ..."` → снижает DX при отладке.
- **Git-unfriendly.** Backup БД = один бинарный файл; diff между snapshot-версиями невозможен.
- **Portability.** Перенос проекта требует dump строк в SQL-скрипт; tarball папки невозможен.

**VERDICT:** отклонён. БД становится свалкой, теряется инспектируемость и portability.

---

### Вариант B — SQLite (мета + hot-state) + JSON на диске (current + per-run frozen snapshots + артефакты)

**Схема БД (Project row):**
```python
class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(primary_key=True)  # UUID
    name: Mapped[str]
    description: Mapped[str | None]
    color: Mapped[str | None]

    # --- Расширение ADR-0002 (REFACTR-14) ---
    source_video_path: Mapped[str | None]       # data/uploads/{...}.mp4
    settings_snapshot_path: Mapped[str]          # "settings.json" (rel. к data/projects/{id}/)
    stage_progress: Mapped[dict] = mapped_column(JSON, default=dict)  # hot, per-stage
    last_saved_at: Mapped[datetime | None]
    soft_deleted_at: Mapped[datetime | None]
    parent_project_id: Mapped[str | None]        # FK -> projects.id ON DELETE SET NULL
    profile_id: Mapped[str]                      # "viral_2026" | "chaptered"

    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
```

**Структура диска:**
```
data/projects/{project_id}/
├── settings.json                  # current (mutable, autosave 10 с)
├── settings.meta.json             # { schema_version: 1, updated_at, checksum }
├── runs/
│   └── {run_id}/                  # frozen per run, IMMUTABLE после creation
│       ├── settings.json          # snapshot на момент старта pipeline
│       ├── settings.meta.json
│       ├── transcript.json        # артефакт transcribe
│       ├── cleaned_segments.json  # артефакт silence_cut
│       ├── reel_plan.json         # артефакт analysis
│       ├── stage_durations.json   # измерения
│       └── manifest.json          # финальный артефакт render
├── clips/                         # готовые фрагменты (shared между runs через content-hash)
├── renders/                       # финальные MP4 per run → symlinks из runs/{run_id}/
└── thumbnails/                    # превью
```

**FOR:**
- **БД остаётся маленькой**: Project row ~1 КБ × 100 проектов = 100 КБ. `stage_progress` JSON ~5 КБ × 100 = 500 КБ. Итого ≤10 МБ на всю БД при 100 проектах.
- **Детерминизм restart**: `runs/{run_id}/settings.json` — immutable snapshot на момент запуска. REFACTR-16 читает ИМЕННО ЕГО, а не текущий `settings.json`. Restart from stage X даёт те же параметры, что были в момент оригинального run.
- **Read/write concurrency**: autosave пишет в `settings.json.tmp` → `Path.replace()` (atomic POSIX rename); БД пишет в `stage_progress` (JSON column, быстрый UPDATE). Два независимых источника, нет взаимных блокировок.
- **Инспектируемость**: `cat data/projects/{id}/settings.json | jq` — читаемо.
- **Git-friendly backup**: `git -C ~/backup/videomaker-projects add projects/{id}/` закомитит текстовый snapshot с diff-history.
- **Portability**: `tar czf project-{id}.tar.gz data/projects/{id}/` + один INSERT-row из БД = полный перенос.
- **Schema-versioning**: `settings.meta.json` содержит `schema_version`; migration-функция в `settings_snapshot_service.py` при чтении старой версии.

**AGAINST:**
- **Два источника правды.** Mitigation: строгое правило «диск = truth для settings; БД = truth для метаданных и hot-state». Никаких дублирований настроек в БД.
- **Atomic write сложнее одной SQL-транзакции.** Mitigation: `tempfile.NamedTemporaryFile(dir=project_dir)` → `Path.replace()` — POSIX atomic, не прерывается прогноcтически при сбое питания.
- **Orphan директории** при hard-delete если БД-строка удалена, а директория осталась. Mitigation: hard-delete сервис делает сначала `shutil.rmtree(path)`, затем `session.delete(project)` в одной try/except. При сбое middle — периодический GC-скрипт (`services/projects_store.py::cleanup_orphans()`).

**VERDICT:** принят. Решает все 7 требований без компромиссов.

---

### Вариант C — Plain-JSON files + SQLite index (минимальная БД)

**Схема:** только `projects_index` таблица `(id, path, name, created_at, soft_deleted_at)`, всё остальное в файлах.

**FOR:**
- Максимум portability (почти весь state в файлах).
- БД минимальна (~десятки КБ).

**AGAINST:**
- **Hot-state (stage_progress) в JSON-файле на диске** требует частых atomic-write при каждом progress-event (10+ раз за стадию). Tempfile+rename на 6 GB+ диске тратит inode-ы и fsync-лaтентность. Хуже, чем `UPDATE projects SET stage_progress = ? WHERE id = ?` в WAL-режиме SQLite.
- **List/filter проектов** (soft-deleted, by date, by profile) без SQL требует `os.scandir()` + JSON-parse каждого → O(N) на UI-рефреш.
- **Alembic больше не управляет всей схемой** — возникает split-brain: БД мигрируется одним механизмом, файлы — другим.
- **JOIN с таблицей `jobs`** невозможен (foreign key в SQL даёт ON DELETE SET NULL cascading из коробки).

**VERDICT:** отклонён. Переусложняет hot-path для маргинальной выгоды в portability, которую Вариант B уже даёт через tar+SQL INSERT.

---

## Decision Outcome

**Выбран Вариант B: SQLite мета + hot-state JSON-column + плоские JSON-файлы settings/artifacts с per-run immutable snapshots.**

### Поля Project (финальная схема)

| Поле | Тип | Nullable | Описание |
|------|-----|----------|----------|
| `id` | `VARCHAR(36)` PK | no | UUID v4 |
| `name` | `VARCHAR` | no | Пользовательское имя |
| `description` | `VARCHAR` | yes | Опциональное описание |
| `color` | `VARCHAR` | yes | Accent-цвет для UI |
| `source_video_path` | `VARCHAR` | yes | Относительный путь от `data/uploads/` |
| `settings_snapshot_path` | `VARCHAR` | no | Относительный путь от `data/projects/{id}/`, по умолчанию `"settings.json"` |
| `stage_progress` | `JSON` | no | Hot: `{stage: {status, progress, started_at, finished_at, run_id?}}` |
| `last_saved_at` | `TIMESTAMP` | yes | Последний успешный autosave |
| `soft_deleted_at` | `TIMESTAMP` | yes | `NULL` → активный; `NOT NULL` → скрыт |
| `parent_project_id` | `VARCHAR(36)` FK | yes | `ON DELETE SET NULL` |
| `profile_id` | `VARCHAR` | no | `"viral_2026"` (default) или `"chaptered"` |
| `created_at`, `updated_at` | `TIMESTAMP` | no | Управляются ORM |

**Jobs расширение:** поле `run_id: VARCHAR(36)` (UUID per pipeline-запуск) добавляется в таблицу `jobs`. Job ссылается одновременно на project (через `project_id`) и на конкретный frozen snapshot (через `run_id` → папка `data/projects/{project_id}/runs/{run_id}/`).

### Структура диска (финальная)

```
data/projects/{project_id}/
├── settings.json                 # current (autosave 10s, mutable)
├── settings.meta.json            # { schema_version: 1, updated_at, checksum_sha256 }
├── runs/
│   └── {run_id}/
│       ├── settings.json         # frozen копия на момент start; read-only
│       ├── settings.meta.json
│       ├── ingest/
│       │   ├── probe.json
│       │   └── transcript.json   # ref или copy из content-addressed cache
│       ├── analysis/
│       │   ├── reel_plan.json
│       │   └── stage_durations.json
│       ├── render/
│       │   └── manifest.json
│       └── logs/
│           └── pipeline.log
├── clips/                        # общие клипы (content-addressed, shared между runs)
├── renders/                      # финальные MP4 per run (hard-links из runs/)
├── thumbnails/
└── .metadata/
    ├── created_at
    └── last_accessed_at
```

### Формат `settings.json`

```json
{
  "schema_version": 1,
  "project_id": "a1b2c3d4-...",
  "profile_id": "viral_2026",
  "sections": {
    "runtime": { ... },
    "brand_kit": { ... },
    "post_production_preset": { ... },
    "subtitle_style_preset": { ... },
    "vision": { ... },
    "prompts": { ... },
    "profile_masks": [ ... ]
  },
  "exported_at": "2026-04-24T16:42:00Z"
}
```

Каждый section — JSON-представление одноимённой таблицы настроек. Сериализатор живёт в `services/project_snapshot_service.py` (создаётся в REFACTR-14).

### Atomic write алгоритм

```python
def save_settings_atomic(project_id: str, payload: dict) -> None:
    project_dir = _project_dir(project_id)
    target = project_dir / "settings.json"
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.fsync(tmp.open("rb").fileno())  # durability
    tmp.replace(target)                # POSIX atomic rename
    _write_meta(project_dir, payload)
```

`Path.replace()` на POSIX — atomic rename: либо `settings.json` остаётся старым, либо полностью заменён новым. Частичная запись невозможна.

### Миграция существующих данных

**Greenfield-сценарий (текущий):** `projects = 0` → Alembic revision `add_project_extended_columns`:
1. `ALTER TABLE projects ADD COLUMN source_video_path VARCHAR`.
2. `ALTER TABLE projects ADD COLUMN settings_snapshot_path VARCHAR NOT NULL DEFAULT 'settings.json'`.
3. `ALTER TABLE projects ADD COLUMN stage_progress JSON NOT NULL DEFAULT '{}'`.
4. `ALTER TABLE projects ADD COLUMN last_saved_at TIMESTAMP NULL`.
5. `ALTER TABLE projects ADD COLUMN soft_deleted_at TIMESTAMP NULL`.
6. `ALTER TABLE projects ADD COLUMN parent_project_id VARCHAR(36) NULL REFERENCES projects(id) ON DELETE SET NULL`.
7. `ALTER TABLE projects ADD COLUMN profile_id VARCHAR NOT NULL DEFAULT 'viral_2026'`.
8. `ALTER TABLE jobs ADD COLUMN run_id VARCHAR(36) NULL`.
9. `CREATE INDEX ix_projects_soft_deleted_at ON projects(soft_deleted_at)`.

Существующие 50 jobs остаются с `project_id IS NULL` и `run_id IS NULL` — legacy-слой, UI-фильтр `/` прячет их за чекбоксом «показать legacy-jobs».

**Hypothetical future (есть проекты в проде):** Downgrade-сценарий задокументирован в revision-файле, но не автоматизирован — ручной backup БД перед `alembic upgrade`.

### Hard-delete алгоритм

```python
def hard_delete_project(project_id: str, session: Session) -> None:
    project_dir = _project_dir(project_id)
    if project_dir.exists():
        shutil.rmtree(project_dir)  # сначала файлы
    session.execute(
        delete(Project).where(Project.id == project_id)
    )
    session.commit()
```

При сбое между `rmtree` и `commit` — строка БД ссылается на несуществующую папку. Mitigation: периодический `cleanup_orphans()` (REFACTR-17), который:
1. Сравнивает список `projects.id` в БД с именами папок в `data/projects/`.
2. Удаляет папки без БД-строки старше 7 дней.
3. Помечает БД-строки без папки как `orphan_at = now()` и показывает в admin-UI для ручного решения.

### Copy-from-project алгоритм (REFACTR-43)

```python
def copy_project(source_id: str, new_name: str, session: Session) -> Project:
    new_id = str(uuid.uuid4())
    new_dir = _project_dir(new_id)
    source_dir = _project_dir(source_id)

    new_dir.mkdir(parents=True, exist_ok=False)
    shutil.copy2(source_dir / "settings.json", new_dir / "settings.json")
    shutil.copy2(source_dir / "settings.meta.json", new_dir / "settings.meta.json")
    # runs/, clips/, renders/, thumbnails/ НЕ копируются — у нового проекта своя история

    source = session.get(Project, source_id)
    new_project = Project(
        id=new_id,
        name=new_name,
        description=source.description,
        color=source.color,
        settings_snapshot_path="settings.json",
        stage_progress={},
        profile_id=source.profile_id,
        parent_project_id=source_id,
    )
    session.add(new_project)
    session.commit()
    return new_project
```

Унаследуются только настройки (settings.json); история запусков и готовые клипы — нет. Ссылка на источник сохраняется в `parent_project_id` для UI-графа «основан на».

---

## Consequences

### Положительные

1. **Детерминизм restart-from-stage.** Благодаря per-run immutable snapshot REFACTR-16 станет прямолинейным: читаем `runs/{run_id}/settings.json`, пропускаем стадии, где `stage_progress[{run_id}][stage] == done`, запускаем from X.
2. **БД остаётся ≤10 МБ** при 100 активных проектах — быстрые backup, migration, VACUUM.
3. **Инспектируемость**: `cat data/projects/*/settings.json | jq '.sections.runtime.narrative_mode'` — анализ настроек без кода.
4. **Git-friendly backup**: пользователь может `git init ~/backup/videomaker-projects` и коммитить settings.json с history.
5. **Portability**: полный перенос проекта — `tar czf` папки + один `INSERT` в БД (ADR формализует CLI-команду `videomaker project export/import` в REFACTR-20).
6. **Autosave не блокирует SSE**: file-write и JSON-column update независимы.
7. **Content-addressed cache сохраняется**: транскрипция и proxy по-прежнему в `data/transcripts/{sha}/` и `data/proxies/` — дедупликация между проектами работает.

### Отрицательные

1. Два источника правды (БД + диск). **Правило:** диск = truth для settings (полный snapshot); БД = truth для метаданных и hot-state. Сервис `project_snapshot_service.py` — единственная граница.
2. Возможны orphan-директории при сбое между `rmtree` и `session.commit()`. **Mitigation:** `cleanup_orphans()` GC раз в день (REFACTR-17).
3. Settings schema изменения требуют двух согласованных действий: новая Alembic revision (для мета-полей) + bump `schema_version` в `settings.meta.json` + migration-функция. **Mitigation:** единый CHANGELOG в `services/project_snapshot_service.py::SCHEMA_MIGRATIONS`.

### Нейтральные

- Существующие 50 legacy-jobs без `project_id` остаются. Frontend REFACTR-39 показывает их отдельной вкладкой «Нарезки без проекта» (legacy) и даёт кнопку «Создать проект из этой нарезки».
- `data/artifacts/{job_id}/` остаётся для legacy-jobs; новые pipeline-runs пишут в `data/projects/{project_id}/runs/{run_id}/`.

---

## Верификация (gate критерии после REFACTR-14 + REFACTR-16 + REFACTR-17)

1. `alembic upgrade head` проходит без ошибок на пустой и на тестовой БД.
2. `python -c "from videomaker.services.project_snapshot_service import save_settings_atomic; ..."` создаёт `data/projects/{id}/settings.json` + `.meta.json` с корректным checksum.
3. Pipeline-run создаёт `runs/{run_id}/settings.json` перед началом первой стадии (проверяется в REFACTR-16).
4. Restart-from-stage X с существующим `run_id` использует frozen snapshot, а не current — проверяется в REFACTR-16 integration-тестом.
5. Hard-delete проекта оставляет БД и файловую систему согласованными.
6. `cleanup_orphans()` помечает и/или удаляет рассинхронизации.
7. Copy-from-project создаёт новый UUID, копирует settings.json, НЕ копирует runs/.

---

## References

- `docs/audit/04-data-schema.md` — инвентарь текущей схемы, row counts (`projects = 0`, `jobs = 50`, все legacy).
- `docs/audit/05-pipeline-stages.md §3` — checkpoint-анализ, потребность immutable snapshot per run.
- `docs/audit/06-ux-pains.md §2` (#7 autosave) и (#8 restart-from-stage).
- `RM-CHUNKS/task.md §2.4, §2.6, §2.8` — требования автосейв/restart/copy-from/ProjectRow snapshot.
- SQLite docs: [WAL journaling mode](https://sqlite.org/wal.html), [atomic commit](https://sqlite.org/atomiccommit.html).
- POSIX `rename(2)` — atomic guarantee.
