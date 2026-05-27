# Val-2 — Technical Feasibility Audit (PRD-expose)

> Phase 5 артефакт. Каждое требование PRD проверено против реального кода.
> Вердикты: РЕАЛИЗУЕМО как написано / ТРЕБУЕТ УТОЧНЕНИЯ / РИСК.
> Все ссылки — `файл:строка` относительно `apps/backend/src` и `apps/frontend/src`.

---

## EPIC 5 — export-transcode (R5.1, R5.2)

### Вердикт: РЕАЛИЗУЕМО, но PRD неверно называет render-путь + РИСК по портируемости.

**Текущее состояние (косметика подтверждена):**
`api/routes/jobs.py:1383-1414` `export_reel_with_preset` — чистый stub. Валидирует
preset + наличие mp4, возвращает metadata (`bitrate_k`, `target_lufs`) и
`download_url`, который указывает на **уже существующий** файл
(`/api/v1/files/{job_id}/reels/{reel_id}.mp4`). Никакого ffmpeg-вызова. Docstring
честно пишет «Full transcode по preset bitrate — следующая итерация». `target_lufs`
из `EXPORT_PRESETS` (jobs.py:1368-1373) сейчас не применяется вообще.

**Render-путь реально переиспользуем — но НЕ те модули, что названы в PRD.**
PRD говорит «renderer.py/reels_composer/filter_graph_builder». На деле:
- `services/reels_composer.py` — это LLM/planning слой (compose_reels, candidates,
  ranking). **Ffmpeg в нём нет вообще.** Включать в render-путь ошибочно.
- `services/renderer.py` — только presets/segments (`load_presets`, `select_preset`,
  `coerce_segments`). Не спавнит ffmpeg.
- Реальная цепочка финального рендера:
  `pipeline_stages/render.py` → `ProjectRenderer.render(graph)`
  (`services/project_renderer.py:115-138`) →
  `build_filter_graph(graph).to_argv()` (`services/filter_graph_builder.py:75`,
  `:48 to_argv`) → `asyncio.create_subprocess_exec(*argv)`
  (`project_renderer.py:138`).

**Что конкретно вызвать для перекодирования одного рилса под preset:**
Нужен `ProjectGraph` с переопределённым `ExportPresetSpec` (bitrate/codec/lufs).
`filter_graph_builder._build_encoder_args` (`:526-576`) уже компилирует `-b:v`,
`-maxrate`, `-bufsize` из `preset.video_bitrate/maxrate/bufsize`, а loudnorm —
`_build_loudnorm_stage` (`:456-490`, читает `graph.audio_normalize.target_lufs`).
То есть инфраструктура для bitrate+LUFS+контейнера **есть**. Но это рендер из
исходных сегментов, а не «перекодирование готового mp4». Два варианта:
1. **Простой transcode** готового рилса: отдельный лёгкий ffmpeg-вызов
   (`-i reel.mp4 -c:v <codec> -b:v ... loudnorm ...`) — НЕ переиспользует
   `ProjectGraph`/`build_filter_graph` (те заточены под сегменты+crop+zoom).
   Это минимальный честный путь под R5.1.
2. **Полный ре-рендер** из ProjectGraph под новый preset — дороже, требует
   сохранённого graph/plan на момент экспорта (его сейчас НЕ персистят рядом с
   рилсом — есть только reel_plan.json hooks).

**🔴 Уточнение для PRD:** выбрать вариант. Вариант 1 (transcode готового файла)
реалистичнее и дешевле, но НЕ «через существующий render-путь» — это новый
маленький ffmpeg-helper. Формулировку «через существующий ffmpeg render-путь»
надо смягчить до «через ffmpeg (переиспользуя encoder-args билдер
`_build_encoder_args` + loudnorm-фильтр)».

**🔴 РИСК R5.2 (портируемость) — реальный и НЕ покрыт «как в media_uploader».**
Default codec render-пути — `hevc_videotoolbox` (hardcoded fallback
`renderer.py:54`, и в `post_production.py:104` колонка codec). Runtime-детект
энкодера (`_has_videotoolbox_h264`, `_ffmpeg_encoders`) существует **только** в
`services/publer/media_uploader.py:80-147`. Главный render-путь его НЕ использует —
кодек берётся статически из presets.yaml/defaults. На Linux/Railway без
videotoolbox export-transcode упадёт, если переиспользовать дефолтный codec.
Под R5.2 надо вынести детект энкодера media_uploader в общий helper и применить
в export-эндпоинте (libx264-фолбэк). Это доп. работа, не «бесплатный re-use».

---

## EPIC 6 — LLM-tier'ы (R6.1, R6.2)

### Вердикт: РЕАЛИЗУЕМО, коэрс локализован в одном модуле.

`services/llm_clients/tier_resolver.py` — карта tier→model **намеренно схлопнута в
Lite**:
- `_tier_profiles` (`:29-52`): и `fast`, и `legacy` профили мапят все три tier
  (`pro`/`flash`/`flash_lite`) на Lite-модели (`_LITE_3_1` / `_LITE_2_5`,
  `:25-26`). Pro/Flash физически не резолвятся.
- `_resolve_tier_models` (`:55-81`): любой нераспознанный профиль коерсится к
  `fast` (`:81`), cold-cache → `fast` (`:74`). Docstring `:7-9` прямо декларирует
  «разрешены только Flash-Lite варианты… профили balanced/quality удалены».

**Где коэрс снять:** добавить реальную Pro-модель в `_tier_profiles` (новый профиль,
напр. `quality`: `pro→gemini-3-pro`, `flash→gemini-flash`, `flash_lite→lite`) и
убрать «нераспознанный → fast» fallback ТОЛЬКО для валидных новых ключей (cold-cache
fallback на Lite оставить — он cost-control, соответствует «дефолт дешёвый»).
`_try_read_tier_profile` (`:84-102`) уже читает `llm_tier_profile` +
`llm_lite_variant` из runtime_settings — расширяемо без структурных изменений.

**🟡 Уточнение для PRD:** R6.1 говорит «вернуть реальную карту pro/flash/flash_lite
на реальные Gemini-модели». Нужно зафиксировать **точные ID моделей** для Pro/Flash
(в коде сейчас только Lite-константы; реальные Pro/Flash ID не заданы нигде). Без
этого реализатор гадает. Также: `PerformanceSettings.llm_tier_profile` — проверить,
что enum/validation в runtime_settings допустит новый профиль (не в скоупе этого
файла, но блокер для R6.2 UI-тоггла).

---

## EPIC 4 — Automatic Mode + like (R4.1, R4.2)

### R4.1 — Вердикт: РЕАЛИЗУЕМО. Бэк-эндпоинты СУЩЕСТВУЮТ, клиентских функций нет.

Бэк полностью готов:
- `PATCH /jobs/{id}/auto-config` — `jobs.py:798-832` `apply_auto_config`. Принимает
  `AutoConfigApplyPayload` (`:765-789`) — subset полей, все `Optional`,
  `exclude_none`. Пустой payload → 400 (`:819-823`). Пишет
  `job.options["auto_config"]` + `pipeline_mode=automatic`.
- `DELETE /jobs/{id}/auto-config` — `jobs.py:835-848` `clear_auto_config`. Ставит
  `auto_config=None` → manual mode.

Фронт (Vite/pages app):
- **apply** уже вызывается, но НЕ через клиент-функцию: `acceptAutoConfig` в
  `components/upload/useWizardState.ts:331` делает прямой `fetch(...PATCH /auto-config)`.
- **clear** (`DELETE`) — отсутствует целиком (grep `auto-config` + DELETE = 0).
- Клиентских `applyAutoConfig`/`clearAutoConfig` в `lib/api/jobs.ts` нет (grep = 0).

R4.1 «клиентские applyAutoConfig/clearAutoConfig» — реализуемо: завернуть
существующий fetch в типизированные функции + добавить DELETE. UI apply есть в
wizard; UI clear в `AutoConfigSummary` — новый.

### R4.2 (BR-07) — Вердикт: ТРЕБУЕТ УТОЧНЕНИЯ — премиса PRD устарела.

PRD утверждает «клиент tri-state vs Pydantic boolean → 422-риск». **На текущем коде
рассогласования НЕТ:**
- Pydantic: `models/job_dto.py:197-202` `ArtifactLikeUpdate.liked: str`,
  `pattern="^(none|like|dislike)$"`, `extra="forbid"`. Это **tri-state строка, НЕ
  boolean.**
- Клиент: `lib/api/jobs.ts:188-201` `updateArtifactLike` шлёт
  `{ liked: "none"|"like"|"dislike" }` — **точно совпадает.**
- Других call-site с boolean `liked` нет (grep по lib/components/app = только этот
  путь + UI-стейт `LikeState` none/like/dislike в `ReelCard.tsx:233`).

**🔴 Уточнение для PRD:** BR-07 либо уже закрыт (возможно в 1b-fix), либо был
ложной тревогой. 422-риска в текущем коде не видно. R4.2 → либо снять, либо
переформулировать в «verify-only» (подтвердить отсутствие регрессии, не менять
контракт). НЕ привязывать к этому работу.

---

## EPIC 3 — Cancel (R3.1)

### Вердикт: РЕАЛИЗУЕМО. Бэк готов (1b-fix подтверждён), клиента нет.

- `POST /jobs/{id}/cancel` — `jobs.py:1093-1119` `cancel_job`. Реализован:
  идемпотентен (done/error/cancelled → `cancelled:false`, `:1112-1113`), находит
  asyncio-task по имени `pipeline:{job_id}` (`_find_pipeline_task` `:1435-1441`,
  task spawn с именем `:1488`), шлёт `task.cancel()` + `service.mark_cancelled`.
- SSE терминирует на `cancelled` корректно: `stream_job_progress` обрабатывает
  `cancelled` в снапшоте (`:1256`) и в event-loop (`:1266`).

Фронт: `cancelJob` в `lib/api/jobs.ts` отсутствует (grep = 0). Кнопки отмены нет.

**Замечание (риск, не блокер):** `_pipeline_tasks` — in-memory set в модуле
(`:1432`). При multi-worker деплое (несколько uvicorn-процессов) cancel найдёт
task только если запрос попал в тот же процесс, что запустил pipeline. Для single
-worker (текущий MVP) ОК; для Railway-масштабирования — отметить ограничение.
Статус всё равно проставится `cancelled` в БД даже если task не найден.

---

## EPIC 7 — Vision/face-tracking (R7.1, R7.2, R7.3)

### R7.1 — Вердикт: РИСК. Hard-таймаут вокруг mediapipe НЕ сработает как наивно написано.

Где hang: `face_tracker.py:351-407` `_detect_faces_in_frames` — **синхронный
блокирующий цикл** по кадрам через mediapipe FaceDetector. Запускается через
`asyncio.to_thread(_detect_faces_in_frames, ...)` (`:276-282`).

**🔴 КЛЮЧЕВОЙ РИСК:** обернуть `asyncio.wait_for(asyncio.to_thread(...))` таймаутом
НЕ убьёт зависший mediapipe-вызов. `to_thread` использует thread-pool executor;
Python-поток нельзя прервать извне — `wait_for` отвалится по таймауту, но поток
mediapipe продолжит висеть и держать worker thread (на Apple Silicon именно это
вешает рендер). Реальный hard-таймаут требует ProcessPoolExecutor (отдельный
процесс, который можно killнуть) или subprocess-изоляции mediapipe. Это
значительно дороже, чем «обернуть таймаутом».

**Фолбэк на center-crop УЖЕ есть** (частично): `_prepare_face_tracking`
(`render.py:439-472`) ловит `FaceTrackerError` → возвращает `None` → центр-crop.
НО: hang — это не exception, а зависание, которое try/except не перехватит.
Фолбэк работает на «детект упал», не на «детект завис».

**🟡 Уточнение для PRD:** R7.1 надо переформулировать с учётом ограничения
`to_thread`. Варианты: (а) ProcessPoolExecutor + timeout + terminate;
(б) timeout как «мягкий» — отметить hang в логе, отдать частичный результат, но
это не гарантирует освобождение потока. Наивный `wait_for` не закроет VS-01.

### R7.2 — Вердикт: РЕАЛИЗУЕМО. Двухуровневый тоггл уже есть на бэке.

`render.py:447-451` подтверждает: face tracking выполняется только при
`PerformanceSettings.face_tracker_enabled=True`, default False (opt-in). Второй
уровень `vision.enabled` — модели `models/vision_settings.py` существуют. UI-пометка
«экспериментально» — фронт-работа, реализуема.

### R7.3 — Вердикт: РЕАЛИЗУЕМО. Эндпоинт есть.

`GET /jobs/{id}/profile/suggestion` — `jobs.py:560-600` `get_profile_suggestion`.
Возвращает `ProfileSuggestion`, 409 если транскрипт не готов. Клиент уже есть:
`lib/api/jobs.ts` — `request<ProfileSuggestion>(.../profile/suggestion)`. Нужен
только UI-триггер.

---

## EPIC 2 — Publer/projects (R2.1–R2.5)

### R2.1 — Вердикт: ТРЕБУЕТ УТОЧНЕНИЯ. project_id в POST /jobs НЕ существует.

**Важно:** `POST /jobs` (`create_job`, `jobs.py:83-309`) **не принимает project_id**
ни в одном Form-поле. Wizard FormData (`useWizardState.ts:229-`) тоже его не
добавляет. Связывание идёт через **отдельный** эндпоинт:
- `PATCH /jobs/{id}/project` — `projects.py:155-180` `assign_job_to_project_endpoint`.
  Принимает `{project_id: int|null}`, валидирует существование проекта (404),
  вызывает `projects_store.assign_job_to_project`. **Полностью рабочий.**
- Клиент есть: `lib/api/projects.ts:77-81` `assignJobToProject(jobId, projectId)` →
  `PATCH .../project`, body `{project_id}`.

**🔴 Уточнение для PRD:** R2.1 говорит «визард шлёт project_id в POST /jobs». Этого
поля в `POST /jobs` нет, и добавлять его в multipart-форму — лишняя работа.
Правильный путь: после `createJob` вызвать существующий `assignJobToProject`
(PATCH /project). Переформулировать R2.1 на «визард после создания job вызывает
`assignJobToProject(jobId, projectId)`». E2e-связка реализуема без изменений бэка.

### R2.3/R2.4 — Вердикт: РЕАЛИЗУЕМО.
- Legacy `/schedule`: `components/schedule/ScheduleClient.tsx:49,75` (прямой
  fetch `/api/v1/schedule`) + `components/job/ScheduleButton.tsx:61` (POST
  `/api/v1/schedule`), смонтирован в `ReelCard.tsx:10,145`. Удаление реализуемо
  (нужно проверить бэк-роутер `/schedule` — он в `api/routes/scheduler.py`,
  отдельно от Publer-кампаний).
- `ManualPublishButton` (`components/scheduler/ManualPublishButton.tsx`)
  **определён, но нигде не смонтирован** (grep import = 0). R2.4 «подключить» —
  реализуемо, нужен только site-call + проверка эндпоинта `manual/publish-one`
  в scheduler-роутере.

### R2.2/R2.5 — фронт-работа (папки saved, CTA). Реализуемо; saved-эндпоинт
`POST /jobs/{id}/saved` (`jobs.py:1122-1155`) существует.

---

## EPIC 1 — Ложь UI (R1.1–R1.4)
Не в фокусе аудита (чистый фронт-cleanup), но затронуто: `viralScore`
(`lib/viralScore.ts`) — клиентская эвристика (`computeViralScore`,
`readBackendCompositeScore`), R1.4 о честной подписи реализуем. R1.3 провайдеры:
`POST /jobs` валидирует `llm_provider` против `settings.available_llm_providers`
(`jobs.py:191`) — убирать мёртвые из UI-селектов безопасно.

---

## EPIC 9 — Orphan cleanup (R9.1)

### Вердикт: ЧАСТИЧНО реализуемо. 2 из 6 модулей НЕ orphan — нулевых ссылок нет.

Проверка ссылок (grep по всему `videomaker/`, исключая сам модуль):

| Модуль | Внешних ссылок | Статус |
|--------|----------------|--------|
| `services/person_cluster.py` | 0 | ✅ orphan, удаляемо |
| `services/match_cuts.py` | 0 | ✅ orphan, удаляемо |
| `services/eye_trace_continuity.py` | 0 | ✅ orphan, удаляемо |
| `services/transition_chooser.py` | 0 | ✅ orphan, удаляемо |
| `services/object_tracker.py` | **1 (живая)** | 🔴 НЕ orphan |
| B-roll (`services/broll/*`) | self-only + 1 docstring | 🟡 условно |

**🔴 `object_tracker.py` НЕ удаляем как есть.** `services/zoom_planner.py:47`
импортирует `ObjectTrack` и использует его в сигнатурах
(`zoom_planner.py:217,354,572` — параметр `object_track: ObjectTrack | None = None`).
`zoom_planner` — живой модуль render-пути (referenced из `pipeline_stages/render.py`,
`project_graph.py`, `face_tracker.py`, `config.py`, `deictic_zoom.py`). Удаление
`object_tracker` сломает импорт zoom_planner → pyright/ruff красные → pipeline
падает. Если `object_track` нигде не передаётся не-None (всегда default None) —
надо сперва вычистить параметр из zoom_planner, потом удалять модуль. Это доп.
рефакторинг, не «подчистить импорты».

**🟡 B-roll:** `services/broll/{inserter,retriever,__init__}.py` ссылаются только
друг на друга. `project_graph.py:18` — лишь **комментарий-докстринг** про
`BRollSpec` (не код). Если `BRollSpec` не определён/не используется как тип в
project_graph — broll-кластер удаляем. Проверить, что `BRollSpec` не импортируется
реально (в данном аудите — только docstring-упоминание).

**🔴 Уточнение для PRD:** «~972 LOC, нулевые ссылки» неточно. Подтверждённо
zero-ref: person_cluster, match_cuts, eye_trace_continuity, transition_chooser.
object_tracker требует предварительной зачистки zoom_planner. R9.1 разбить на:
(а) удалить 4 чистых orphan; (б) отдельная под-задача — расцепить
zoom_planner↔object_tracker, затем удалить; (в) проверить BRollSpec перед
удалением broll-кластера.

---

## Сводка красных флагов (приоритет для уточнения PRD)

1. **EPIC 5**: render-путь назван неверно (reels_composer — LLM-слой, ffmpeg нет).
   Решить transcode-готового-файла vs ре-рендер. R5.2 портируемость — реальная
   доп. работа (детект энкодера только в media_uploader, не в render-пути).
2. **EPIC 7 R7.1**: наивный таймаут вокруг `to_thread(mediapipe)` НЕ убьёт hang.
   Нужен ProcessPool/subprocess. Существующий фолбэк ловит exception, не зависание.
3. **EPIC 9**: object_tracker НЕ orphan (живая ссылка zoom_planner.py:47).
   Только 4 модуля zero-ref. B-roll проверить на BRollSpec.
4. **EPIC 2 R2.1**: project_id в POST /jobs не существует — использовать
   `PATCH /jobs/{id}/project` (assignJobToProject уже в клиенте).
5. **EPIC 4 R4.2**: tri-state/boolean mismatch в текущем коде ОТСУТСТВУЕТ —
   контракт совпадает (str enum обе стороны). Премиса BR-07 устарела.

## Сводка «реализуемо как написано» (бэк готов, нужен только клиент/UI)
- EPIC 3 cancel: `POST /jobs/{id}/cancel` готов; добавить `cancelJob` + кнопку.
- EPIC 4 R4.1: PATCH/DELETE /auto-config готовы; apply есть (inline fetch),
  добавить clear + типизированные функции.
- EPIC 6: коэрс в одном модуле (tier_resolver), расширяемо; зафиксировать ID
  Pro/Flash моделей.
- EPIC 7 R7.2/R7.3: тоггл + suggestion-эндпоинт + клиент готовы; нужен UI.
- EPIC 2 R2.3/R2.4: удаление /schedule + монтаж ManualPublishButton реализуемы.
