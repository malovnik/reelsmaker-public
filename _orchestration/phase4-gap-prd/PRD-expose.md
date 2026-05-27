# PRD — Доработка вывода бэкенда во фронтенд (ReelsMaker)

> Phase 4 артефакт. Основан на [GAP-ANALYSIS.md](GAP-ANALYSIS.md), продуктовых решениях PD1-PD4 (ROADMAP).
> Скоуп: довести «честный рабочий сервис» — починить выведенное-сломанным, вывести упущенное-важное, связать обрывы. НЕ редизайн (это Phase 9).
> Подлежит валидации (Phase 5) перед реализацией (Phase 6).

## Принципы реализации (для всех эпиков)
- Production-ready, NO mocks/TODO/stubs. Serena для правок кода, Context7 для API библиотек.
- Бэк: ruff + pyright зелёные. Фронт: `pnpm build` + tsc зелёные. Новые unit-тесты НЕ пишем (политика проекта), не ломаем существующие.
- **Логирование**: каждое новое действие (cancel, publish, transcode, project-assign) пишет structured log через `core/logging`.
- **Документация**: каждый эпик обновляет соответствующий раздел `BACKEND-MAP`/`FRONTEND-EXPOSURE` по факту изменений + запись в ROADMAP «Лог фаз».
- Каждый PR/коммит атомарен по эпику.

---

## EPIC 1 — Убрать ложь UI (P0/P1, PD1+PD4)
Цель: ни один контрол не обещает того, чего не делает.
- **R1.1** (BR-01) Удалить `/settings/connections` YouTube-OAuth UI и клиентские вызовы `/connections/youtube/*` (роутер дропнут). Навигацию подчистить.
- **R1.2** (BR-04) Убрать `chaptered` из выбора narrative-режима (нет рабочего call-site).
- **R1.3** (BR-05) Убрать мёртвые anthropic/openai/deepgram из pipeline-provider селектов; оставить gemini/zhipu.
- **R1.4** (FL-05) viral-score: честная подпись «клиентская эвристика» либо убрать выдачу за «оценку движка».
**Acceptance:** в UI нет контролов, ведущих к падению/фикции; навигация без битых ссылок; tsc/build зелёные.

## EPIC 2 — Связать обрывы потока (P0, PD3)
- **R2.1** (FL-01/MS-03) Визард шлёт `project_id` в `POST /jobs`; вызывается `assignJobToProject`; проект↔джоб связаны e2e.
- **R2.2** (FL-07) Экран папки `saved/<folder>` — список сохранённых рилсов проекта.
- **R2.3** (FL-02) Удалить legacy `/schedule` + `ScheduleButton` + прямой `POST /api/v1/schedule`. Публикация только через Publer-кампании (PD3).
- **R2.4** (FL-03) Подключить `ManualPublishButton` → `manual/publish-one` («быстрая публикация»).
- **R2.5** (FL-06) После `done` — явный CTA к результату (не мелкая ссылка).
- **R2.6** (BR-06, P0, **добавлено по валидации Phase 5**) assignment cancel должен реально отзывать пост в Publer (`DELETE` соответствующего Publer-поста), а не только флипать локальный статус. Отмена ПУБЛИКАЦИИ ≠ отмена джоба (EPIC 3). Если пост уже опубликован и не отзываем — честно сообщить «нельзя отозвать опубликованное».

**Уточнение R2.1 (по валидации):** `POST /jobs` НЕ принимает `project_id`. Связка проекта: после создания джоба вызвать `PATCH /jobs/{id}/project` (projects.py:155) — клиент `assignJobToProject` уже есть (projects.ts:77). Визард делает assign сразу после успешного `POST /jobs`.
**Acceptance:** новичок проходит create→upload→process→view→publish без тупиков (E2E-проверка кликами); один механизм публикации (grep: нет вызовов legacy `/api/v1/schedule`); папки проектов содержат назначенные джобы; cancel публикации реально отражается в Publer (или честный отказ).

## EPIC 3 — Cancel job (P0, PD-готово на бэке)
- **R3.1** (FL-04/MS-01) Клиент `cancelJob` → `POST /jobs/{id}/cancel` (реализован в 1b-fix). Кнопка отмены на карточке/детали активного джоба. SSE корректно терминирует на `cancelled`.
**Acceptance:** активный джоб реально останавливается из UI, статус `cancelled`, прогресс закрывается.

## EPIC 4 — Automatic Mode целостность (P0, PD1)
- **R4.1** (NX-01/02) Клиентские `applyAutoConfig`/`clearAutoConfig` → `PATCH`+`DELETE /jobs/{id}/auto-config`; UI apply/clear в `AutoConfigSummary`.
- **R4.2** (BR-07, **скорректировано валидацией**) VERIFY-ONLY: премиса 422-риска опровергнута — `liked: str`-enum с обеих сторон (job_dto.py:202 = jobs.ts:191), рассогласования НЕТ. Достаточно подтвердить контракт регресс-проверкой; кодовых правок не требуется, если контракт совпадает.
**Acceptance:** Automatic Mode флоу полный (suggest→apply/clear→start, clear ранее отсутствовал — добавить клиент+UI); лайк работает (контракт подтверждён).

## EPIC 5 — Реальный export-transcode (P0, PD1)
**Уточнение пути (валидация):** реальный ffmpeg render-путь = `pipeline_stages/render.py → ProjectRenderer.render` (project_renderer.py:138) → `build_filter_graph().to_argv()`. Переиспользуемы: encoder-args билдер (filter_graph_builder.py:526), loudnorm (:456). `reels_composer.py` — LLM/planning-слой, ffmpeg в нём НЕТ (не путать).
- **R5.1** (BR-02) `POST /jobs/{id}/reels/{rid}/export` (jobs.py:1383, сейчас stub) реально перекодирует один рилс под выбранный preset (bitrate/LUFS/контейнер) через encoder-args + loudnorm билдеры; `download_url` ведёт на перекодированный файл.
- **R5.2** (🔴 не «бесплатный re-use») Главный render-путь `renderer.py:54` хардкодит `hevc_videotoolbox` → на Linux упадёт. Вынести runtime-детект энкодера (как в media_uploader.py:80-147) в общий хелпер и применить и в export, и в основном рендере: videotoolbox при наличии, иначе libx264.
**Acceptance:** `ffprobe` экспортированного файла показывает реальные параметры preset (битрейт/кодек/LUFS отличаются от исходника); на Linux-окружении export не падает.

## EPIC 6 — Честные LLM-tier'ы (P0, PD1+PD4, Вариант A)
**Уточнение (валидация):** коэрс локализован в `tier_resolver.py` (_tier_profiles:29 мапит все три tier на Lite; _resolve_tier_models:81 коерсит нераспознанное к `fast`). Реальных ID Pro/Flash-моделей в коде нет — взять из конфигурации (`GEMINI_*_MODEL` env / runtime_settings); зафиксировать карту: pro→Gemini Pro, flash→Gemini Flash, flash_lite→Flash-Lite (точные ID — из .env.example/конфига при реализации).
- **R6.1** (BR-03/MS-02) Вернуть реальную карту pro/flash/flash_lite на реальные Gemini-модели; снять принудительный коэрс в профиле `fast`. **Дефолт остаётся Flash-Lite** (cost control), Pro — осознанный opt-in через рабочий тоггл.
- **R6.2** UI: тоггл качества честно меняет модель; подпись с предупреждением о стоимости/времени Pro.
**Acceptance:** в логе/артефакте джоба используемая модель совпадает с выбранным tier (Pro→Pro-модель, не Lite); дефолтный джоб использует Flash-Lite.

## EPIC 7 — Vision/face-tracking opt-in revival (P1, PD2)
**🔴 Уточнение (валидация):** hang в `_detect_faces_in_frames` (face_tracker.py:351) — синхронный mediapipe через `asyncio.to_thread`. `to_thread` НЕПРЕРЫВАЕМ — наивный `asyncio.wait_for` не убьёт зависший поток. Нужна **process-изоляция** (ProcessPoolExecutor / subprocess с kill по таймауту). Существующий фолбэк (render.py:470) ловит exception, но НЕ зависание.
- **R7.1** (VS-01) Вынести mediapipe-детект в отдельный процесс с hard-таймаутом и kill; при таймауте/ошибке — graceful фолбэк на center-crop.
- **R7.2** (VS-02/03) Честный двухуровневый тоггл (`vision.enabled` + `face_tracker_enabled`), дефолт безопасный (OFF→center-crop), UI-пометка «экспериментально/opt-in».
- **R7.3** (NX-03) Вывести триггер `profile/suggestion` в UI.
**Acceptance:** искусственно зависший детект убивается по таймауту, рендер продолжается с center-crop (не виснет); дефолт стабилен; контрол честно помечен.

## EPIC 8 — Доводка экспозиции (P2, PD1)
- **R8.1** (NX-04/05/06) UI управления кэшем прокси (list/cleanup/delete) — в Эксперт-режиме.
- **R8.2** (NX-07) Кнопка `fonts/refresh`.
- **R8.3** (NX-08/09) URL-хелперы для source-thumbnail и assets/thumbnail.
**Acceptance:** ручки доступны из UI; превью грузятся.

## EPIC 9 — Очистка orphan-кода + dormant default (PD4)
**🔴 Уточнение (валидация):** zero-ref подтверждены только **4 модуля**: person_cluster, match_cuts, eye_trace_continuity, transition_chooser. **`object_tracker` НЕ orphan** — живой импорт `ObjectTrack` в zoom_planner.py:47 (zoom_planner в render-пути). B-roll — только self-ссылки + docstring в project_graph.py:18, проверить `BRollSpec` перед удалением.
- **R9.1** Удалить 4 подтверждённых orphan-модуля + B-roll (после verify `BRollSpec`). `object_tracker` НЕ трогать (или сначала расцепить от zoom_planner — отдельная задача, не в этом эпике). Проверять нулевые ссылки на коде ПОСЛЕ EPIC 5/7.
- **R9.2** (H2, dormant default) Выключить дефолт `screencast_cursor_zoom_enabled` → False (жжёт CPU, выход выброшен; UI уже скрыт).
**Acceptance:** ruff/pyright зелёные; pipeline работает; удалён только подтверждённо-мёртвый код; cursor-zoom не запускается по дефолту.

---

## Порядок реализации (Phase 6)
1. EPIC 1 (ложь) → 2. EPIC 3 (cancel, дёшево) → 3. EPIC 4 (auto-config+like) → 4. EPIC 2 (потоки/публикация) → 5. EPIC 6 (tier'ы) → 6. EPIC 5 (export-transcode, L) → 7. EPIC 7 (vision opt-in) → 8. EPIC 8 (доводка) → 9. EPIC 9 (orphan cleanup).

## Метрики приёмки PRD (Phase 7 валидация)
- 0 контролов-фикций (ничего не врёт).
- Главный поток create→reels→publish без обрывов.
- Cancel/auto-config/export/tier/vision — реально работают (не заглушки).
- ruff/pyright/pnpm build зелёные. Существующее не сломано.
- Один механизм публикации (Publer).

## ОТКРЫТЫЕ ЗАВИСИМОСТИ от Phase 9 (редизайн)
Экраны папки (R2.2), переключатель режимов, онбординг — реализуются в редизайне; здесь только бэк-связки и клиентские функции, чтобы Phase 9 строил поверх рабочих данных.
