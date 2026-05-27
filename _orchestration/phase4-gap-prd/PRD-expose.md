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
**Acceptance:** новичок проходит create→upload→process→view→publish без тупиков; один механизм публикации; папки проектов рабочие.

## EPIC 3 — Cancel job (P0, PD-готово на бэке)
- **R3.1** (FL-04/MS-01) Клиент `cancelJob` → `POST /jobs/{id}/cancel` (реализован в 1b-fix). Кнопка отмены на карточке/детали активного джоба. SSE корректно терминирует на `cancelled`.
**Acceptance:** активный джоб реально останавливается из UI, статус `cancelled`, прогресс закрывается.

## EPIC 4 — Automatic Mode целостность (P0, PD1)
- **R4.1** (NX-01/02) Клиентские `applyAutoConfig`/`clearAutoConfig` → `PATCH`+`DELETE /jobs/{id}/auto-config`; UI apply/clear в `AutoConfigSummary`.
- **R4.2** (BR-07) Согласовать `updateArtifactLike`: клиент tri-state vs Pydantic boolean — привести к одному контракту (проверить модель, выбрать целевой), убрать 422-риск.
**Acceptance:** Automatic Mode флоу полный (suggest→apply/clear→start); лайк не падает 422.

## EPIC 5 — Реальный export-transcode (P0, PD1)
- **R5.1** (BR-02) `POST /jobs/{id}/reels/{rid}/export` реально перекодирует через существующий ffmpeg render-путь под выбранный preset (bitrate/LUFS/контейнер); `download_url` ведёт на перекодированный файл.
- **R5.2** Портируемость: использовать libx264-фолбэк (как в 1b-fix media_uploader) на не-macOS.
**Acceptance:** экспорт отдаёт файл с реальными параметрами preset; пресеты больше не косметика.

## EPIC 6 — Честные LLM-tier'ы (P0, PD1+PD4, Вариант A)
- **R6.1** (BR-03/MS-02) В `tier_resolver.py` вернуть реальную карту pro/flash/flash_lite на реальные Gemini-модели; снять принудительный коэрс в Flash-Lite в профиле `fast`. **Дефолт остаётся Flash-Lite** (cost control), Pro — осознанный opt-in через рабочий тоггл.
- **R6.2** UI: тоггл качества честно меняет модель; подпись с предупреждением о стоимости/времени Pro.
**Acceptance:** выбор tier реально меняет используемую модель (видно в артефакте/логе); дефолт дешёвый.

## EPIC 7 — Vision/face-tracking opt-in revival (P1, PD2)
- **R7.1** (VS-01) Hard-таймаут вокруг mediapipe-детекта + graceful фолбэк на center-crop (устранить hang на Apple Silicon).
- **R7.2** (VS-02/03) Честный двухуровневый тоггл (`vision.enabled` + `face_tracker_enabled`), дефолт безопасный (OFF→center-crop), UI-пометка «экспериментально/opt-in».
- **R7.3** (NX-03) Вывести триггер `profile/suggestion` в UI.
**Acceptance:** включение face-tracking не вешает рендер (таймаут срабатывает); дефолт стабилен; контрол честно помечен.

## EPIC 8 — Доводка экспозиции (P2, PD1)
- **R8.1** (NX-04/05/06) UI управления кэшем прокси (list/cleanup/delete) — в Эксперт-режиме.
- **R8.2** (NX-07) Кнопка `fonts/refresh`.
- **R8.3** (NX-08/09) URL-хелперы для source-thumbnail и assets/thumbnail.
**Acceptance:** ручки доступны из UI; превью грузятся.

## EPIC 9 — Очистка orphan-кода (PD4)
- **R9.1** Удалить ~972 LOC orphan-модулей (B-roll, object_tracker, person_cluster, match_cuts, eye_trace_continuity, transition_chooser) — после подтверждения нулевых ссылок. Подчистить импорты.
**Acceptance:** ruff/pyright зелёные; pipeline работает; мёртвый код удалён.

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
