# Backend Acceptance Validation — Phase 7 (Exposure)

> Валидатор: Backend Acceptance Validator. Проверка по коду, не по обещаниям.
> Дата: 2026-05-27. База: `apps/backend/src/videomaker`.

## Сводный вердикт

| Эпик | Критерий | Вердикт |
|------|----------|---------|
| EPIC 6 | Честные LLM-tier'ы | **PASS** |
| EPIC 5 | Реальный export-transcode | **PASS** |
| EPIC 7 | Vision/face-tracking process-isolation | **PASS** |
| EPIC 2 R2.6 | Cancel → Publer DELETE | **PASS** |
| EPIC 9 | Orphan cleanup + dormant default | **PASS** |

Гейты: **ruff `All checks passed!`** · **pyright `0 errors, 0 warnings`** (по 8 изменённым файлам).

---

## EPIC 6 — Честные LLM-tier'ы — PASS

Файл: `services/llm_clients/tier_resolver.py`.

- pro/flash маппятся на реальные Gemini-модели из конфигурации:
  - `_tier_profiles` (tier_resolver.py:46-51) → `pro: cfg.gemini_pro_model`, `flash: cfg.gemini_flash_model`, `flash_lite: lite`.
  - `core/config.py:33-34` → `gemini_pro_model = "gemini-2.5-pro"`, `gemini_flash_model = "gemini-2.5-flash"`. Маппинг pro→2.5-pro / flash→2.5-flash подтверждён.
- Дефолт Flash-Lite: профиль `flash_lite` всегда на Lite (`_LITE_2_5`/`_LITE_3_1`, :29-30, :44).
- Принудительный коэрс СНЯТ для распознанных профилей: `_resolve_tier_models` (:85-89) при `profile in profiles` возвращает реальную матрицу без коэрса. All-Lite fallback оставлен ТОЛЬКО для cold-cache (:79-83) и неизвестного профиля из старой БД (:91-95) — это cost-control защита, не коэрс легитимного выбора (соответствует R6.1 «дефолт Flash-Lite, Pro — opt-in»).
- Лог tier-модели: `_log_tier_mapping` (:98-110) пишет `llm_tier_mapping_resolved` с `pro_model`/`flash_model`/`flash_lite_model` через `core/logging`. Acceptance «в логе модель совпадает с tier» выполнено.

Дыр нет.

## EPIC 5 — Реальный export-transcode — PASS

Файлы: `api/routes/jobs.py`, `services/encoder_support.py`, `services/renderer.py`.

- Export НЕ stub: `export_reel_with_preset` (jobs.py:1461-1542) запускает реальный `asyncio.create_subprocess_exec(*argv)` (:1508), ждёт `communicate()`, на rc≠0 удаляет частичный файл и кидает 500 с stderr-tail.
- Параметры preset применяются: `EXPORT_PRESETS` (jobs.py:1379-1382) задаёт `bitrate_k`/`target_lufs`/`container`; `_build_export_argv` (:1392-1458) подставляет bitrate (maxrate=1.4×, bufsize=2×, :1416-1417) и LUFS в `AudioNormalizeSpec` (:1423-1424). Видео-кодирование через реальный `_build_encoder_args` (filter_graph_builder.py:526), аудио через `_build_loudnorm_stage` (filter_graph_builder.py:456) — те же билдеры, что и основной рендер.
- Encoder-детект videotoolbox→libx264: `resolve_video_codec("h264_videotoolbox")` (jobs.py:1407, encoder_support.py:63-75) — если VT нет в `ffmpeg -encoders`, отдаёт `libx264`. На Linux export не упадёт.
- download_url на перекодированный файл: `download_url=f"/api/v1/files/{job_id}/reels/{reel_id}.{preset}.mp4"` (:1541), выход пишется именно туда (`_reel_artifact_path(..., f".{preset}.mp4")`, :1491). Раздаётся через `api/routes/files.py` (`/api/v1/files`, path-validated).
- Главный render-путь расцеплён от хардкода: `renderer.py:55-65` берёт `configured_codec` из defaults, пропускает через `resolve_video_codec`, логирует `render_codec_fallback` при подмене. Хардкод `hevc_videotoolbox` остался лишь как default-строка в `defaults.get(..., "hevc_videotoolbox")`, которая сразу резолвится в доступный кодек — R5.2 выполнено.

Дыр нет.

## EPIC 7 — Vision/face-tracking opt-in — PASS

Файлы: `services/face_tracker.py`, `services/pipeline_stages/render.py`.

- Mediapipe в ОТДЕЛЬНОМ ПРОЦЕССЕ (не to_thread): `_detect_faces_in_subprocess` (face_tracker.py:442-501) использует `mp.get_context("spawn")` + `ctx.Process(target=_detect_faces_worker, daemon=True)` (:460-466). Sync `_detect_faces_in_frames` исполняется ВНУТРИ дочернего процесса (worker :418-434), не в worker-потоке.
- Hard-таймаут + kill: `asyncio.wait_for(asyncio.to_thread(queue.get), timeout=timeout_sec)` (:480-483) — даже при зависшем `queue.get` asyncio выходит по таймауту; `_kill_process` (:469-475) делает `terminate()` → `join(5)` → `kill()` → `join(5)`. `finally` (:494-498) гарантирует очистку процесса/queue в любом исходе. Это закрывает баг «to_thread непрерываем» (job 8a418e9b).
- Фолбэк на center-crop: при таймауте кидается `FaceTrackerError` (:491), который ловит `_prepare_face_tracking` в render.py:471-473 → возвращает `None` (= статичный центр-crop). Сбой/зависание детекта не валит рендер.
- Двухуровневый toggle, дефолт OFF: `face_tracker_enabled` гейтит весь блок (render.py:269), при False — `face_track_skipped` лог и `setup.face_track=None` (:277-281). Дефолт безопасный.

Дыр нет. (UI-пометка «экспериментально» — фронтовая часть R7.2/R7.3, вне backend-скоупа этой валидации.)

## EPIC 2 R2.6 — Cancel → Publer DELETE — PASS

Файлы: `api/routes/scheduler.py`, `services/publer/client.py`.

- Реальный Publer DELETE: `cancel_assignment` (scheduler.py:718-807) при наличии `publer_post_id` и не-published статусе вызывает `PublerClient.delete_posts([row.publer_post_id])` (:760-763). `delete_posts` (client.py:216-235) шлёт реальный `DELETE /posts?post_ids[]=...` через `_request("DELETE", ...)` и парсит `deleted_ids`.
- Честный отказ если опубликовано: статус `published` → `409 "нельзя отозвать опубликованное"` (:749-758), лог `assignment_cancel_refused_published`.
- Честный отказ если не отозвать: запланирован, но `publer_post_id` ещё не сверён (только `publer_job_id`) → `409` «отозвать сейчас нельзя» (:784-796). Сбой Publer DELETE → `502`, локальный статус НЕ меняется (:764-777) — без молчаливого флипа.
- Локальный-only флип только когда отзывать в Publer нечего (нет publer-id, draft/queued) (:797-806). Идемпотентность для уже `cancelled` (:746-747).
- Отмена публикации отделена от отмены джоба (EPIC 3) — это отдельный роут `/assignments/{id}/cancel`.

Дыр нет.

## EPIC 9 — Orphan cleanup + dormant default — PASS

- 4 orphan-модуля удалены: `person_cluster.py`, `match_cuts.py`, `eye_trace_continuity.py`, `transition_chooser.py` — файлы отсутствуют, кодовых ссылок нет (grep по `--include=*.py`).
- B-roll удалён: модуль/`BRollSpec` отсутствуют; единственное упоминание — стейл-docstring в `project_graph.py:18` (комментарий «когда будут разрабатываться»), не код-ссылка. Минорный мусор в комментарии, не блокер.
- `object_tracker` НА МЕСТЕ: `services/object_tracker.py` существует, `ObjectTrack` живо импортируется в `zoom_planner.py:47` (render-путь) — как требовал PRD.
- cursor-zoom default False: `runtime_settings.py:478-479` → `screencast_cursor_zoom_enabled: bool = Field(default=False, ...)`. Гейт в render.py:1115 (`and perf_preview.screencast_cursor_zoom_enabled`) — по дефолту не запускается.

Дыр нет.

---

## Гейты (по изменённым файлам)

```
$ uv run ruff check src/videomaker
All checks passed!

$ uv run pyright <8 changed files>
0 errors, 0 warnings, 0 informations
```

Файлы под pyright: tier_resolver.py, encoder_support.py, renderer.py, api/routes/jobs.py, face_tracker.py, pipeline_stages/render.py, api/routes/scheduler.py, publer/client.py.

## Найденные дыры

Нет блокирующих. Один косметический момент: стейл-упоминание `BRollSpec` в docstring `project_graph.py:18` после удаления B-roll — рекомендуется вычистить комментарий, но это не код-ссылка и не влияет на ruff/pyright/runtime.

## Итог

Все 5 backend-эпиков (6, 5, 7, 2-R2.6, 9) — **PASS** по коду. Реализации реальные (ffmpeg-subprocess, process-isolation, Publer DELETE, real Gemini model IDs), не заглушки. Гейты зелёные.
