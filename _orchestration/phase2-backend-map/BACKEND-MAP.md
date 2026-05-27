# BACKEND-MAP — Карта софта ReelsMaker (бэкенд)

> Готовый документ бэкенда (Phase 2). Консолидация аудита Phase 1 + 1b, написана 3 агентами-документаторами, принята оркестратором.
> Состоит из 3 разделов (отдельные файлы) + эта сводка.

## Разделы
1. **[API Contract & Data Model](section-1-api-data.md)** — 81 эндпоинт (8 роутеров под `/api/v1`), SSE-контракт, 12 таблиц БД, 13 stores.
2. **[Processing Pipeline](section-2-pipeline.md)** — сквозной поток, narrative-мозг (4 режима), vision/video/ffmpeg, audio DSP, транскрипция, Publer.
3. **[System Architecture & Operations](section-3-architecture-ops.md)** — слои, зависимости, конфигурация, запуск, техдолг.

## Сводка для быстрого старта

**Что это.** Локальный сервис: длинное видео → набор вертикальных рилсов 9:16 через LLM-управляемый многостадийный анализ транскрипта (фреймворк драматургии Картозии) + ffmpeg-рендер + опциональная публикация в соцсети через Publer.

**Стек.** Монорепо: `apps/backend` (FastAPI, Python, async, SQLite через aiosqlite) + `apps/frontend` (Vite — НЕ Next.js, README устарел). Точка входа `main.py` с lifespan (2 фоновых воркера: fonts-warmup + PublerWorker; pipeline = fire-and-forget `create_task`).

**Поток (дефолтный прогон, ~22 исполняемые стадии).**
`upload → job → ingest (probe→proxy→STT stable-ts MLX→translate если не RU→silence_cut) → analyze [bottom_up: chunking→compression→canvas→6 extraction-агентов→reduce→story_doctor 3-act→rhythm→variants→compose→coherence+closure валидаторы, всё Gemini Flash-Lite] → render (ffmpeg HEVC: center-crop→cut_snap→burn ASS-субтитров→loudnorm −14 LUFS) → finalize`. Публикация в Publer — отдельный ручной флоу.

**Обязательные внешние зависимости: 3** — ffmpeg/ffprobe, Gemini API, локальный MLX-STT. Опционально: Zhipu/GLM, Deepgram, Anthropic/OpenAI (мёртвый код в narrative), Publer, Moondream, mediapipe.

**Истина состояния.** SQLite (`data/videomaker.db`, теперь WAL): job-статусы, проекты, ассеты, настройки, scheduler. Артефакты pipeline (transcript/reel_plan/reels) — файлы на диске, в БД относительные пути. SSE-прогресс — параллельный in-memory поток.

## Статус «реально vs декоративно» (критично для фронтенд-фаз)
- 🟢 **Живое ядро:** ingest, narrative bottom_up, ffmpeg-рендер, аудио-DSP, SSE, Publer, персистентность.
- 🟡 **Выключено на дефолте:** vision-слой (kill-switch), face-tracking (flagship «smart reframing» тёмный → статичный center-crop), multi_arc, post-production, большинство DSP-трансформов.
- 🟡 **Dormant (жгут CPU, выход выброшен):** screencast cursor zoom (toggle ВКЛ!), deictic zoom, mouth-sound removal.
- 🔴 **Фикции в UI:** tier «pro»=Flash-Lite; chaptered-режим broken но выбираем; export не перекодирует.
- 🔴 **Orphan (~972 LOC мёртвого кода, ещё НЕ удалён):** B-roll, object_tracker, person_cluster, match_cuts, eye_trace_continuity, transition_chooser.

## Обновление после Phase 6 (вывод бэка во фронт)
Ранее «PARTIAL STUB» в section-1 БОЛЬШЕ НЕ актуальны: export реально перекодирует (ffmpeg), assignment cancel реально отзывает пост в Publer. Tier'ы разведены на реальные модели (дефолт Flash-Lite). Orphan ~972 LOC удалены (object_tracker оставлен). Face-tracking — process-isolation с kill по таймауту.

## Что уже починено (1b-fix, проверено по коду)
path-traversal `reel_id` · реальный cancel job · viral_2026 уважает провайдера · videotoolbox→libx264 fallback · SQLite WAL+busy_timeout.

## Отложено в PRD (Phase 4)
Удаление orphan-кода · revival/honesty фиксы (tier-лейблы, dormant) · face-tracking fix · real export transcode · persistent job queue · решение по auth (по умолчанию НЕ добавляем — локальный single-user инструмент).

## Полный список 81 эндпоинта — в [section-1](section-1-api-data.md). Это база для Phase 3 (что выведено во фронтенд) и Phase 4 (gap-анализ).
