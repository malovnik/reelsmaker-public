# REFACTR-12 — Итоговая архитектурная диаграмма (C4 level 1-2)

> **Этап:** 01
> **Шаг:** 13 из 67
> **Зависимости:** REFACTR-07..11 (все ADR).
> **Следующий шаг:** REFACTR-13 (первый бэкенд-чанк)

---

## Роли

### R-ARCHITECT
**Soul:** Диаграмма — это контракт с будущим собой. Если через 6 месяцев я не пойму, что сделал — значит диаграмма не нужна никому.

### R-DEVIL
**Soul:** Диаграмма не должна быть украшением. Каждая стрелка — проверяемая.

---

## ТРИЗ-принцип

*Принцип универсальности.* Диаграмма C4 — универсальный язык. Level 1 (System Context) — для не-технических читателей. Level 2 (Container) — для разработчиков.

---

## Оркестрация

**Режим:** Sequential.

---

## Микрозадачи

### 12.1 Level 1: System Context

Диаграмма: `videomaker` в центре, вокруг:
- **User** (Никита, владелец, single-user).
- **Gemini API** (LLM-провайдер).
- **Deepgram API** (транскрипция, опционально).
- **Anthropic/OpenAI API** (альтернативные LLM).
- **MacOS Finder** (интеграция «Открыть в Finder»).
- **VideoToolbox** (macOS hardware encoder).

Формат: Mermaid + текстовое описание.

### 12.2 Level 2: Containers

Контейнеры внутри videomaker:
- **Frontend SPA** (Vite + React + TanStack).
- **Backend API** (FastAPI, uvicorn).
- **SQLite database** (`data/app.db`).
- **File storage** (`data/projects/`, `data/uploads/`, `data/artifacts/`).
- **Pipeline workers** (async tasks внутри uvicorn процесса).
- **Rendering engine** (ffmpeg subprocess).
- **Transcription engine** (MLX-Whisper в отдельном процессе / Deepgram HTTP).

Стрелки:
- Frontend → Backend (REST + SSE).
- Backend → SQLite (SQLAlchemy).
- Backend → FileStorage (fs операции).
- Backend → Pipeline (asyncio tasks).
- Pipeline → Rendering (subprocess).
- Pipeline → Transcription (local или HTTP).

### 12.3 Dataflow: «новый проект до рендера»

Отдельная диаграмма: sequence-diagram пути от загрузки видео до готового рилса.

### 12.4 Dataflow: автосохранение

Отдельная sequence-диаграмма.

### 12.5 Написать документ

`docs/architecture/c4-overview.md`:
- Level 1 (Mermaid + описание).
- Level 2 (Mermaid + описание).
- Sequence «new-project-to-reel» (Mermaid).
- Sequence «autosave» (Mermaid).
- Ссылки на все ADR.

### 12.6 Обновить PIPELINE-НАВИГАТОР

- [x] Лог изменений: «Этап 01 ЗАВЕРШЁН. Архитектурная основа зафиксирована.»

### 12.7 Serena memory

- [x] `write_memory(name="refactr-12-architecture", content="...")`.

---

## GATE-чекпоинт

- [x] `docs/architecture/c4-overview.md` создан (≈520 строк, 4 Mermaid-диаграммы + таблицы контейнеров + инварианты + gate).
- [x] Level 1 + Level 2 + 2 sequence — все 4 диаграммы есть (System Context с 7 акторами/сервисами; Containers с 7 контейнерами + 8 протоколов связи; Sequence «new-project-to-reel» с 3 rect-блоками стадий; Sequence «autosave-conflict» с нормальным потоком + 409 + 3 альтернативы разрешения + cross-tab sync).
- [x] Все 5 ADR связаны ссылками (таблица вверху документа + обратные ссылки в Level 2 таблице контейнеров + сводная таблица инвариантов).
- [ ] **Gate с человеком:** владелец подтверждает архитектуру перед началом Этапа 02. (Ожидает владельца — список под-пунктов в документе §Gate-чекпоинт.)

---

## Артефакт на выходе

`docs/architecture/c4-overview.md`.
