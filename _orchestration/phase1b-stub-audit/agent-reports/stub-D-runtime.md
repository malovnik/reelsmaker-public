# Stub-D — Runtime Correctness & Persistence Reality-Check

Root: `apps/backend/src/videomaker/`. Engine: SQLite (`sqlite+aiosqlite`, single file `data/videomaker.db`), async SQLAlchemy 2.0. Single-process FastAPI app, pipelines run as in-process `asyncio` tasks.

## Таблица вердиктов

| # | Тема | Вердикт | Доказательство | Приоритет |
|---|---|---|---|---|
| 1 | `JobStatus.cancelled` без обработчика | **DEAD-enum-value** | `job_constants.py:38` (объявлен) · читается только в SSE-терминаторе `api/routes/jobs.py:1226,1236` · НИГДЕ не пишется (`grep status=JobStatus` → только pending/done/error/running) · нет cancel-роута для job · нет `mark_cancelled` в `services/jobs.py` | P2 |
| 2 | `JobEventBus` + perf/vision TTL-кэши привязаны к процессу | **SCALING-stub (acceptable for single-instance)** | `job_event_bus.py:20` docstring «один процесс, без Redis»; `maxsize=256` молчаливый дроп `job_event_bus.py:46`; module-global `_perf_cache`/`_vision_cache` (30с TTL) | P3 |
| 3 | SQLite «database is locked» при параллельных флашах | **RACE-RISK (низкая вероятность, не нулевая)** | нет `PRAGMA journal_mode=WAL`, нет `busy_timeout` PRAGMA (`core/db.py` целиком) — только `connect_args={"timeout":30}` (db.py:49); `render_many` параллельит N ffmpeg с `Semaphore` (`project_renderer.py:220-227`), каждый пишет artifact-row; несколько job-task'ов одновременно (`_schedule_pipeline` → `asyncio.create_task`, `api/routes/jobs.py:1390`) | P2 |
| 4 | `h264_videotoolbox` в media_uploader | **PORTABILITY-BREAK** | хардкод без platform-guard и без fallback `services/publer/media_uploader.py:104`; для сравнения proxy.py использует портируемый `libx264` (`proxy.py:291`) | P1 (если деплой Linux) |
| 5 | `jobs.options` schema-less JSON | **SCHEMA-RISK (контролируемый техдолг)** | `options: Mapped[dict] = mapped_column(JSON)` `job_orm.py:106`; несёт `hidden`/`hidden_purge`/`hidden_at` (jobs.py:679-682), `stage_durations`/`total_generation_sec` (`_store_timings` jobs.py:906), `auto_config`, `composer_strategy_override`; фильтр `hidden` — Python-side (jobs.py:284) | P3 |

---

## 1. Cancel-функционал — статус: НЕ РАБОТАЕТ (мёртвое значение enum)

Трассировка полная:

- **Объявление:** `JobStatus.cancelled = "cancelled"` (`job_constants.py:38`).
- **Запись статуса:** единственные места, где пишется `job.status` — `JobStatus.pending` (create, jobs.py:144), `running` (mark_stage буфер, jobs.py:307), `done` (mark_done, jobs.py:336), `error` (mark_error jobs.py:369 + reset_stale jobs.py:892). **`cancelled` не присваивается нигде.**
- **Чтение:** только в SSE-стриме как терминальный признак — `if job.status in (done, error, cancelled)` (jobs.py:1226) и `event.get("status") in {"done","error","cancelled"}` (jobs.py:1236). То есть код *готов* принять cancelled от стрима, но источник его не производит.
- **DELETE-роут** (`api/routes/jobs.py:1057` → `service.delete_job`) делает soft/hard/nuke — это удаление записи/файлов, НЕ отмена выполнения. Running-job он не останавливает (pipeline-task продолжит писать в удалённую/скрытую job).
- **Task-реестр:** `_pipeline_tasks: set[asyncio.Task]` (jobs.py:1365) наполняется (`add` jobs.py:1414), но **никогда не итерируется для `.cancel()`** — единственный `.cancel()` в проекте это `fonts_warmup_task.cancel()` (main.py:99). Нет ни роута, ни сервис-метода, отменяющего pipeline.

**Вывод:** пользователь не может отменить запущенную обработку. `cancelled` — мёртвая ветка enum. Аналогичный enum `AssignmentStatus.cancelled` (scheduler) — это ДРУГОЙ домен и он рабочий (`api/routes/scheduler.py:734`); не путать.

**План фикса (M):**
1. Добавить `JobService.mark_cancelled(job_id)` рядом с mark_error: флаш буфера, `status=cancelled`, `finished_at=now`, `bus.publish status=cancelled`. (S)
2. Хранить `asyncio.Task` per-job в dict `{job_id: task}` вместо анонимного set (правка `_schedule_pipeline`). (S)
3. Роут `POST /{job_id}/cancel`: `task.cancel()` → дождаться `CancelledError` → `mark_cancelled`. В `run_pipeline_safe` поймать `CancelledError` отдельно от `Exception`, чтобы не маппить отмену в `error`. (M)
4. `reset_stale_running_jobs` оставить как есть (рестарт ≠ отмена).
- Риск: ffmpeg-subprocess не убивается автоматически при `task.cancel()` — нужно явно `proc.kill()` в except-ветках renderer'а. Без этого останутся зомби-процессы. Альтернатива (S, если cancel не нужен): удалить `cancelled` из enum и из SSE-чеков, чтобы не вводить в заблуждение.

---

## 2. Process-bound шина и кэши — SCALING-stub, приемлемо для single-instance

Осознанный дизайн (docstring явный), не недоделка. Корректно ровно при одном процессе:
- `JobEventBus` — RAM dict очередей. >1 воркера → SSE-подписчик на воркере A не увидит события из воркера B.
- perf/vision TTL-кэши (30с) — PUT на воркере A не инвалидирует кэш воркера B (до 30с рассинхрон).
- Доп. риск той же природы: `reset_stale_running_jobs` на старте помечает ВСЕ `running → error` — при multi-instance рестарт одного воркера убьёт активные job'ы других.

**План (L, только если планируется горизонтальное масштабирование):** вынести шину в Redis pub/sub, кэши — в Redis с pub/sub-инвалидацией, `reset_stale` ограничить по owner-id воркера. Для Railway-1-контейнер деплоя — **не трогать**, это over-engineering. Требует подтверждения целевого деплоя.

---

## 3. SQLite database-is-locked — RACE-RISK, воспроизводимо при нагрузке

Реально ли: **да, но вероятность низкая** благодаря `timeout=30` (sqlite3 busy-timeout: писатель ждёт до 30с снятия блокировки вместо мгновенного `SQLITE_BUSY`). Однако:
- Нет WAL-режима → один писатель блокирует БД целиком (в rollback-journal даже читатели конфликтуют с писателем).
- Параллелизм реальный: `render_many` гонит N ffmpeg одновременно (`project_renderer.py:220`), по завершении каждый рендер регистрирует artifact (write); плюс `mark_stage` флашит прогресс раз/3с; плюс несколько job'ов могут идти параллельно (никакого global-семафора на число одновременных job нет — `_schedule_pipeline` просто создаёт task).
- Сценарий лока: 2+ одновременных job на финализации (burst artifact-INSERT) + флаш прогресса. При >30с суммарного ожидания → `OperationalError: database is locked`, который НИГДЕ не ловится (нет `OperationalError` в коде) → пробьётся в `run_pipeline_safe` как generic Exception → job в `error`.

**План фикса (S, рекомендуется):**
1. В `core/db.py` `_enable_sqlite_foreign_keys` (он уже навешан на каждый connect) добавить `PRAGMA journal_mode=WAL` + `PRAGMA busy_timeout=30000` + `PRAGMA synchronous=NORMAL`. WAL даёт конкурентные читатели + один писатель без взаимоблокировки читателей. (S)
- Риск: WAL создаёт `-wal`/`-shm` файлы рядом с БД (учесть в бэкапах/volume); на сетевых ФС WAL ненадёжен (Railway volume — локальный, ОК).
2. (Опционально M) При реальной нагрузке — миграция на Postgres. Блокер: `set_performance_settings` использует `sqlite_insert.on_conflict` (SQLite-специфика) — потребует ветку на `pg_insert`.

---

## 4. h264_videotoolbox — PORTABILITY-BREAK на не-macOS

**Что сломается на Linux/Railway:** ветка re-encode в `media_uploader.py:_reencode_to_h264` (вызывается только когда рилс >180 MB перед загрузкой в Publer). На Linux ffmpeg собран без `h264_videotoolbox` (это macOS VideoToolbox API) → `ffmpeg ... rc!=0` → `ValueError` (media_uploader.py:124-128) → доставка рилса в Publer падает. Остальной pipeline НЕ затронут: proxy и финальный рендер используют `libx264` (`proxy.py:291`), который кроссплатформенный.

Граница риска: триггерится **только** для рилсов >180 MB. Для типичных ≤90с 9:16 рилсов размер обычно <180 MB → ветка не вызывается, и на Linux всё работает. Но это «бомба замедленного действия»: первый тяжёлый экспорт на проде упадёт.

**План фикса (S):**
1. Заменить хардкод на runtime-выбор кодека: попытаться `h264_videotoolbox`, при недоступности (или сразу по `sys.platform != "darwin"`) — `libx264 -preset veryfast -crf`-эквивалент target-bitrate. (S)
2. Чище: вынести имя видеокодека в Settings (`app_publer_reencode_vcodec`, default авто-детект через `ffmpeg -encoders` один раз при старте). (M)
- Риск: `libx264` с фиксированным `-b:v` без two-pass даёт менее предсказуемый размер — добавить `-maxrate`/`-bufsize` или CRF+проверку размера.
- **Требует подтверждения целевого деплоя.** Если деплой остаётся macOS (локальный сервис на Apple Silicon, как и заявлено в видении videomaker) — приоритет падает до P3 «задокументировать ограничение».

---

## 5. jobs.options schema-less — SCHEMA-RISK, контролируемый техдолг

`options` — нетипизированный `JSON`-словарь (job_orm.py:106), де-факто свалка разнородных полей: `hidden`/`hidden_purge`/`hidden_at`, `stage_durations`, `total_generation_sec`, `auto_config`, `composer_strategy_override`. Риски:
- Нет валидации ключей/типов на запись → опечатка в ключе тихо создаст «фантомное» поле, чтение вернёт `None`/дефолт без ошибки.
- Фильтр `hidden` идёт Python-side после выборки всех job'ов (jobs.py:284) — не масштабируется (комментарий автора: пересмотреть при >1000 job).
- Невозможно индексировать/фильтровать в SQL по этим полям без JSON-функций.

**Не баг сейчас, но точка роста.** План (M, по необходимости): вынести стабильные поля (`hidden`, `total_generation_sec`) в типизированные колонки с индексом на `hidden`; оставить в `options` только «свободную» телеметрию; ввести Pydantic-модель `JobOptions` для валидации на границе записи. Риск: миграция Alembic + бэкфилл существующих job'ов.

---

## Что сломается на не-macOS (сводка)

| Компонент | На Linux | Серьёзность |
|---|---|---|
| `media_uploader._reencode_to_h264` (`h264_videotoolbox`) | **Падает** при рилсе >180 MB → Publer-доставка fails | Условный break (только тяжёлые рилсы) |
| proxy.py (`libx264`) | Работает | — |
| Финальный рендер (`libx264` в render/filter_graph) | Работает | — |
| Аудио DSP, Publer HTTP, SQLite, scheduler | Платформо-независимы | — |

Единственная macOS-зависимость в рантайме — re-encode-ветка Publer-аплоадера. Всё остальное портируемо.

## Статус cancel-функционала (для координатора)

**ОТМЕНА JOB НЕ РЕАЛИЗОВАНА.** `JobStatus.cancelled` — мёртвое enum-значение: объявлено, читается в SSE-терминаторе, но никогда не пишется. Нет cancel-роута, нет `mark_cancelled`, реестр `_pipeline_tasks` не используется для `.cancel()`. DELETE-роут удаляет/скрывает запись, но не останавливает выполнение. (Не путать с рабочим `AssignmentStatus.cancelled` в scheduler-домене — это другая сущность.)
