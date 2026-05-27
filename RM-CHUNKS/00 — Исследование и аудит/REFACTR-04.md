# REFACTR-04 — Схема данных (SQLite + файловое хранилище)

> **Этап:** 00 — Исследование и аудит
> **Шаг:** 5 из 67
> **Зависимости:** REFACTR-00, REFACTR-03.
> **Следующий шаг:** REFACTR-05 (Pipeline stages)

---

## Роли

### R-AUDITOR — Аудитор
**Профессия:** Картограф.
**Soul:** Данные — правда системы. Код может врать (dead code), схема — не может. Начинай с неё.

### R-DATA-ARCHITECT (консультативно)
**Профессия:** Data engineer.
**Soul:** Миграции — искусство. Сохранить данные → изменить схему → не потерять ни байта.

---

## ТРИЗ-принцип

*Принцип изменения агрегатного состояния.* Настройки в текущей схеме разбросаны (каждая страница настроек — свой store). Цель Этапа 02 — объединить под project-snapshot. Аудит фиксирует текущее разбросанное состояние.

---

## Оркестрация

**Режим:** Sequential.

---

## Микрозадачи

### 04.1 Прочитать модели SQLAlchemy

- [x] `services/` и `models/`: все файлы `*_store.py` и `*.py` в `models/`.
- [x] Для каждой модели: имя, поля, связи.

Ожидаемые модели:
- Project
- Job
- SubtitleStore / RuntimeSettings / PromptStore / VisionSettings / PerformanceSettings / BrandKit / PostProduction / SchedulerCampaigns / AccountProfiles / ReelPlan

### 04.2 Прочитать миграции Alembic

- [x] `apps/backend/alembic/versions/` — вся история миграций.
- [x] Актуальная ревизия, последовательность, что добавлялось последним.

### 04.3 Содержимое реальной БД

- [x] Путь к БД (скорее всего `data/*.db`).
- [x] `sqlite3 <file> ".schema"` и `.tables`.
- [x] Количество записей в каждой таблице.

### 04.4 Файловое хранилище

- [x] `data/uploads/` — структура, примеры.
- [x] `data/artifacts/` — что хранится (транскрипции, preview, клипы).
- [x] `data/logs/` — текущая ротация (если есть).
- [x] `data/projects/` (если есть) — per-project артефакты.

### 04.5 Схема «где хранится что»

Составить таблицу:

| Сущность | SQLite таблица | JSON-файлы | Binary-файлы | Secrets |
|----------|---------------|------------|--------------|---------|
| Project | projects | - | - | - |
| Video upload | - | - | data/uploads/{id}.mp4 | - |
| Transcript | - | data/artifacts/{job}/transcript.json | - | - |
| Settings (brand) | brand_kit | - | - | - |
| API keys | - | - | - | .env |
| ... | | | | |

### 04.6 Предложить схему project-snapshot

Предварительный дизайн (для ADR-08):
- `Project.settings_snapshot` (JSON column) — полный слепок всех настроек на момент создания проекта.
- `Project.stage_progress` (JSON) — статус каждой стадии pipeline.
- `Project.soft_deleted_at` (timestamp) — soft-delete маркер.
- `Project.last_saved_at` (timestamp) — для автосохранения.

Но это ПРЕДВАРИТЕЛЬНОЕ — финал в ADR-08.

### 04.7 Артефакт

`docs/audit/04-data-schema.md`:
- Модели SQLAlchemy + ER-диаграмма.
- Миграции Alembic (история).
- Файловое хранилище.
- Таблица «где хранится что».
- Предварительный дизайн project-snapshot.

### 04.8 Serena memory

- [x] `write_memory(name="refactr-04-data-schema", content="...")`.

---

## GATE-чекпоинт

- [x] Все модели SQLAlchemy перечислены.
- [x] История Alembic-миграций зафиксирована.
- [x] Количество записей в реальной БД известно (для оценки риска миграции).
- [x] Файловое хранилище описано.
- [x] Предварительный дизайн snapshot предложен.

---

## Артефакт на выходе

`docs/audit/04-data-schema.md` — полная картина хранения данных.
