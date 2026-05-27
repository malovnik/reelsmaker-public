# Stub-C — Reality-Check HTTP-контрактов API-слоя

Корень: `apps/backend/src/videomaker/api/routes`
Верификация подозрений из `agent-A-api-layer.md` по фактическому коду + `main.py` + `core/artifacts.py` + `services/publer/worker.py`.

---

## Таблица вердиктов

| # | Ручка | Вердикт | Доказательство | Приоритет |
|---|-------|---------|----------------|-----------|
| 1 | POST `/jobs/{id}/reels/{reel_id}/export` | **PARTIAL-stub** (declared transcode = noop) | jobs.py:1317-1347 — нет ffmpeg-вызова; `download_url` указывает на исходный mp4 | P1 |
| 2 | POST `/scheduler/assignments/{id}/cancel` | **PARTIAL-stub** (Publer-side noop) | scheduler.py:720-737 — только flip local status, нет HTTP к Publer | P1 |
| 3 | GET `/post_production/presets/default` | **REAL, контракт расходится** (200+null, не 204) | post_production.py:210-216 | P2 |
| 4 | Весь слой — auth/authz/rate-limit | **MISSING-security** (подтверждено на уровне app factory) | main.py:107-134 — ни одного Depends/middleware кроме CORS | **P0** |
| 5 | GET/PATCH `/files`, `path_for` (`..` блок) | **REAL** — `path_for`/`job_dir` блокируют traversal | artifacts.py:41-60 | — |
| 6 | PATCH/GET `/reels/{reel_id}/subtitles`, `/export` | **VULN** — `reel_id` интерполируется в путь МИМО `path_for` | jobs.py:1263, 1292, 1298(write), 1335 | **P0** |

---

## Детальные вердикты

### 1. POST `/jobs/{id}/reels/{reel_id}/export` — PARTIAL-stub

**Доказательство:** jobs.py:1317-1347. Хендлер:
- валидирует `preset ∈ EXPORT_PRESETS` (400),
- проверяет существование `reels/{reel_id}.mp4` (404),
- возвращает `ExportResponse{preset, bitrate_k, target_lufs, download_url}`.

`bitrate_k`/`target_lufs` берутся из статической таблицы `EXPORT_PRESETS` (jobs.py:1302-1307) и **никогда не применяются к файлу**. `download_url = /api/v1/files/{job_id}/reels/{reel_id}.mp4` — это исходный, неперекодированный рендер. Никакого ffmpeg/loudnorm-вызова в теле нет. Docstring честно признаёт MVP-статус (jobs.py:1326-1328). Это «ложь интерфейсу» в мягкой форме: клиент получает метрики, считая что файл соответствует preset bitrate/LUFS, а он не соответствует.

**План «сделать не для вида»:**
1. Добавить async-функцию `transcode_reel(src, preset_cfg) -> Path` рядом с существующим composer/ffmpeg-кодом (искать `videotoolbox_hevc`/`asyncio.create_subprocess_exec` — инфра уже есть в health.py `_detect_ffmpeg`).
2. ffmpeg: `-c:v` (h264/hevc) `-b:v {bitrate_k}k -maxrate -bufsize`, аудио `-af loudnorm=I={target_lufs}:TP=-1.5:LRA=11`, контейнер mp4 (`+faststart`).
3. Писать в детерминированный путь `reels/{reel_id}.{preset}.mp4` (через `path_for`, не raw-конкатенация).
4. Идемпотентность: если файл существует и mtime ≥ исходника — пропустить транскод.
5. `download_url` → на перекодированный файл. Долгий транскод — либо синхронно (короткие рилсы ≤60с приемлемо), либо отдать job_id события через тот же event bus + `202 Accepted`.
6. Риски: блокировка event-loop (использовать subprocess+await, не sync); рост дискового потребления (нужен cleanup в `delete_job` purge); videotoolbox недоступен на Linux/Railway → fallback на libx264.
- **Размер: M** (синхронный путь) / **L** (async + прогресс).

---

### 2. POST `/scheduler/assignments/{id}/cancel` — PARTIAL-stub (Publer-side)

**Доказательство:** scheduler.py:720-737. Хендлер только `row.status = AssignmentStatus.cancelled.value` + flush. Никакого `PublerClient`-вызова. Docstring (721-725) прямо признаёт: «Удаление на стороне Publer (DELETE /posts/{publer_post_id}) сейчас не реализовано».

**Подтверждение защиты от двойной публикации:** worker.py:102 — `if fresh is None or fresh.status != queued: continue`. Воркер перечитывает свежий статус перед доставкой, так что локально отменённый (cancelled) assignment **не будет доставлен**, ПОКА он в очереди и ещё не ушёл в Publer. Реальная дыра:
- assignment, который **уже** ушёл в Publer (status uploading/posted, есть `publer_post_id`) — cancel его не отзывает; пост опубликуется/останется.
- `retry_assignment` (scheduler.py:743) сбрасывает cancelled→queued — то есть «отмена» обратима кем угодно без защиты (см. P0 ниже).

Вердикт «вернула 200, реально на стороне Publer ничего не отменено» — для уже доставленных постов это **подтверждённая ложь интерфейсу**.

**План:**
1. Если `row.publer_post_id` не пуст — вызвать `PublerClient.delete_post(publer_post_id)` (добавить метод в клиент по образцу list_*).
2. Обрабатывать 404 от Publer (пост уже удалён) как успех; сетевую ошибку → 502, статус НЕ флипать (или флипать в отдельный `cancel_failed`).
3. Только при успехе внешнего DELETE (или отсутствии publer_post_id) ставить local `cancelled`.
4. Риски: Publer rate-limit; идемпотентность повторного cancel; гонка с воркером, который прямо сейчас аплоадит (нужен compare-and-set статуса или короткий lock).
- **Размер: M.**

---

### 3. GET `/post_production/presets/default` — REAL, но контракт расходится

**Доказательство:** post_production.py:210-216. `response_model=PostProductionPresetRead | None`, при отсутствии возвращает `return None` → FastAPI отдаёт **HTTP 200 с телом `null`**. Реальная работа есть (читает БД), это не заглушка. Расхождение: docstring в шапке файла (по отчёту A) обещает 204. Фронт может не ожидать `null` в 200.

**План:** выбрать один контракт. Рекомендую `204 No Content` при отсутствии default — семантически чище, и фронт отличает «нет дефолта» от «дефолт = объект». Заменить на `Response(status_code=204)` при `row is None` (и убрать `| None` из response_model, либо оставить с явной 204-веткой через отдельный Response). **Размер: S.** Риск: сломать существующий фронт, который уже парсит `null` — синхронизировать с фронт-агентом.

---

### 4. Auth/Authz/Rate-limit — MISSING-security (P0, подтверждено на уровне app factory)

**ПОДТВЕРЖДЕНО опровержение гипотезы о middleware уровнем выше.** `create_app()` (main.py:107-134):
- единственный middleware — `CORSMiddleware` (main.py:115-122) с `allow_origins=[settings.frontend_origin]`, `allow_credentials=True`, `allow_methods=["*"]`;
- `app.include_router(api_router)` без глобального `dependencies=[...]`;
- никаких auth-зависимостей, API-key проверок, сессий, rate-limit ни на app, ни на router-уровне (`api/routes/__init__.py` — только prefix `/api/v1`).

**Вывод: весь API-слой полностью открыт.** Любой, кто достучался до порта, выполняет все ручки. CORS не защита (это браузерная политика, не серверная авторизация — `curl` её игнорирует).

Оговорка: продукт спроектирован как **локальный** инструмент (single-user, localhost). Если деплой строго `127.0.0.1` без проброса — фактический риск ниже. Но при любом сетевом/Railway-экспонировании — критично. CORS `allow_credentials=True` + единственный origin указывает на намерение работать в браузере, что повышает требование к auth при публичном доступе.

**Деструктивные ручки, открытые без защиты:**
- `DELETE /jobs/{id}?purge=nuke` (jobs.py:1057) — полная зачистка upload+artifacts+row.
- `DELETE /jobs/{id}?purge=hard` — удаление неотлайканных mp4.
- `DELETE /proxies/cleanup` (proxies.py:79) — LRU-чистка proxy-кэша.
- `DELETE /proxies/{sha256}`, `DELETE /projects/{id}`, `DELETE /post_production/assets|presets/{id}`, `DELETE /scheduler/campaigns/{id}`.
- `POST /scheduler/assignments/{id}/retry` — реактивация отменённого assignment (обходит cancel).
- `POST /scheduler/campaigns/{id}/approve` → ставит assignments в queued → воркер **публикует в реальные соцсети через Publer**. Это самый опасный открытый сайд-эффект: неаутентифицированный POST → реальная публикация.
- `POST /jobs` — запуск pipeline (расход LLM-токенов/CPU, потенциальный DoS/billing-abuse).

**План:**
1. Минимум: статический API-ключ через `Depends`-зависимость на `api_router` (header `X-API-Key` сверять с `settings`). Размер S.
2. Rate-limit: `slowapi`/middleware, агрессивнее на POST `/jobs`, approve, manual/publish-one. Размер M.
3. Жёстко привязать bind к `127.0.0.1` в проде если single-user; явный флаг для сетевого режима, требующий ключа. Размер S.
4. Риски: сломать локальный фронт (передавать ключ из фронт-конфига); ключ в plaintext-конфиге (вынести в env per CLAUDE.md).

---

### 5. Path-traversal в `/files/{job_id}/{kind}/{name}` — REAL (защита работает)

**Доказательство:** artifacts.py:55-60 `path_for`:
- `kind` сверяется с `ALLOWED_KINDS` (whitelist) → ValueError;
- `name`: блок `not name | "/" in name | ".." in name` → ValueError;
- `job_id` через `job_dir` (artifacts.py:41-47): блок `"/" / ".."` + resolve + проверка `root in parents`.

files.py:24-30 ловит ValueError → 400. Двойная защита (string-check + resolve-containment). `..` и абсолютные/escape-пути заблокированы корректно. **Опровергает подозрение о дыре в `/files`.** `resolve_relative` (62-73) тоже containment-проверен.

---

### 6. `reel_id` в subtitles/export — VULN (P0): обход `path_for`

**Доказательство:** jobs.py:1263, 1292, 1335 — путь строится **прямой конкатенацией** `artifacts.job_dir(job_id) / "subs" / f"{reel_id}.ass"`, НЕ через `path_for`. То есть `reel_id` **не проходит** name-валидацию (`..`/`/`-блок применяется только в `path_for`, который здесь не вызывается).

- `job_dir` валидирует только `job_id`, не последующие сегменты.
- FastAPI default path-конвертер не матчит `/` в одном сегменте → `reel_id` со слэшем не пройдёт роутинг. НО Starlette декодирует `%2F` до роутинга в части конфигураций, и одиночный сегмент `..` (без слэша) валиден как значение.
- Суффикс `.ass`/`.mp4` всегда добавляется → цель атаки должна оканчиваться на `.ass`/`.mp4`, что сужает (но не закрывает) вектор.
- **PATCH `/subtitles` (jobs.py:1298) ВЫПОЛНЯЕТ ЗАПИСЬ** `sub_path.write_text(...)` — это write-primitive. Самый опасный из трёх: запись произвольного контента в путь, частично контролируемый через `reel_id`, с ограничением суффикса `.ass`.

Вердикт: реальная брешь в defense-in-depth. Сейчас её прикрывает только default-поведение FastAPI-роутера (не явная санитизация) — хрупко и не должно быть единственным барьером для write-ручки.

**План:**
1. Прогонять `reel_id` через тот же фильтр, что `path_for`: добавить `_safe_segment(reel_id)` (блок `/`, `..`, пустое) ИЛИ ввести `path_for(job_id, "subs", f"{reel_id}.ass")` — но имя содержит суффикс, поэтому проще валидировать `reel_id` отдельной helper-функцией перед конкатенацией.
2. После построения — resolve-containment проверка относительно `job_dir` (как в `resolve_relative`), особенно перед write.
3. Применить к всем трём точкам: 1263 (GET subs), 1292/1298 (PATCH subs write), 1335 (export).
4. Риск: легитимные `reel_id` содержат только `[a-z0-9_]` (формат `v{idx}_r{N}` из памяти проекта) — строгий regex `^[A-Za-z0-9_-]+$` безопасен и ничего не сломает.
- **Размер: S.** Приоритет **P0** из-за write-primitive в PATCH.

---

## P0-список (security, действовать первыми)

1. **`reel_id` path-traversal в PATCH/GET subtitles + export (jobs.py:1263/1292/1298/1335)** — write-primitive с частичным контролем пути. Фикс: regex-валидация `reel_id` + containment-check. Размер S.
2. **Полное отсутствие auth/authz во всём слое (main.py:107-134)** — открыты деструктивные DELETE-ручки и, критичнее, `POST /scheduler/campaigns/{id}/approve` → реальная публикация в соцсети без аутентификации. Фикс: API-key Depends на api_router + bind 127.0.0.1 в single-user. Размер S-M.
3. **Нет rate-limit** на `POST /jobs` (LLM/CPU abuse) и publish-ручках — DoS/billing-abuse вектор. Размер M.

## Подтверждение про auth-middleware

**Опровергнута** гипотеза отчёта A («подтвердить, есть ли middleware уровнем выше»). Проверен `create_app()` в `main.py:107-134`: единственный middleware — CORS; `include_router` без глобальных dependencies; auth/authz/rate-limit отсутствуют на всех уровнях (app, router, route). CORS authorization НЕ обеспечивает — слой полностью открыт для не-браузерных клиентов. Это сквозная находка уровня **P0** при любом сетевом экспонировании; для строго локального single-user деплоя фактический риск ниже, но `approve`-ручка с реальной публикацией делает её значимой даже локально.
