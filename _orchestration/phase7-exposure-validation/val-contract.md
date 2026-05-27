# Phase 7 — Frontend↔Backend Contract Validation

Роль: Frontend↔Backend Contract Validator. Сверка клиентских вызовов (`apps/frontend/src/lib/api`) с реальными FastAPI-эндпоинтами (`apps/backend/src/videomaker/api/routes`). Эталон-контракт: `_orchestration/phase2-backend-map/section-1-api-data.md`.

## Итог

| # | Контракт | Вердикт |
|---|---|---|
| 1 | cancelJob → POST /jobs/{id}/cancel | СОГЛАСОВАН |
| 2 | applyAutoConfig (PATCH) / clearAutoConfig (DELETE) /jobs/{id}/auto-config | СОГЛАСОВАН |
| 3 | export → POST /jobs/{id}/reels/{rid}/export | СОГЛАСОВАН (контракт-doc устарел) |
| 4 | assignJobToProject → PATCH /jobs/{id}/project | СОГЛАСОВАН |
| 5 | manualPublishOne / listLikedReels | СОГЛАСОВАН |
| 6 | proxiesApi (list/cleanup/delete) → /proxies/* | СОГЛАСОВАН |
| 7 | tier-выбор (fast/legacy + 3_1/2_5) | СОГЛАСОВАН |
| 8 | cancelAssignment — обработка 409/502 на фронте | РАССОГЛАСОВАН (минорный UX) |

Критичных рассогласований уровня "метод/путь/тело не совпадает" — НЕТ. Один минорный UX-разрыв (#8) и одна устаревшая запись в эталон-документе (#3).

---

## Доказательства

### 1. cancelJob — СОГЛАСОВАН
- Фронт: `lib/api/jobs.ts:222-226` — `POST /api/v1/jobs/${id}/cancel`, без тела.
- Бэк: `routes/jobs.py:1102-1128` — `@router.post("/{job_id}/cancel", status_code=200)`.
- Ответ: фронт ждёт `{job_id, status, cancelled}` (jobs.ts:223) ↔ бэк возвращает ровно `{"job_id", "status", "cancelled"}` (jobs.py:1122, 1128). Совпадает метод/путь/тело/ответ.

### 2. applyAutoConfig / clearAutoConfig — СОГЛАСОВАН
- PATCH: фронт `jobs.ts:228-233` шлёт JSON `AutoConfigPayload` ↔ бэк `jobs.py:807-841` принимает `AutoConfigApplyPayload` (jobs.py:774-798).
  - Все 17 полей фронта (`AutoConfigPayload`, jobs.ts:165-183) — подмножество/совпадение с Pydantic-моделью, включая `onset_snap_max_shift_sec` (фронт:182 ↔ бэк:798). Все опциональны (`| null` ↔ `| None`). `extra` в модели не запрещён, лишних полей фронт не шлёт.
  - Ответ `AutoConfigApplyResponse{job_id, pipeline_mode, applied_keys}` (фронт jobs.ts:185-189 ↔ бэк jobs.py:801-804). Совпадает.
- DELETE: фронт `jobs.ts:235-239` `DELETE /auto-config`, ждёт `{job_id, pipeline_mode}` ↔ бэк `jobs.py:844-856` возвращает `{job_id, pipeline_mode:"manual"}` со статусом 200. Совпадает.

### 3. export — СОГЛАСОВАН (эталон-документ устарел)
- Фронт: `jobs.ts:314-323` — `POST /api/v1/jobs/{id}/reels/{rid}/export?preset=...`, ждёт `{preset, bitrate_k, target_lufs, download_url}`.
- Бэк: `jobs.py:1461-1542` — `@router.post(".../export", response_model=ExportResponse)`; `ExportResponse{preset, bitrate_k, target_lufs, download_url}` (jobs.py:1385-1389). Тело/ответ совпадают.
- **Расхождение с эталон-документом (не с кодом):** `section-1-api-data.md:148,290` помечает эндпоинт как "PARTIAL STUB" и утверждает, что возвращается ссылка на нетранскоженный `/files/{job_id}/reels/{reel_id}.mp4`, а `bitrate_k`/`target_lufs` декларативны. Фактический код (jobs.py:1493-1542) делает реальный ffmpeg-транскод (`_build_export_argv`, jobs.py:1392) и возвращает `download_url` на транскоженный файл `.{preset}.mp4` (jobs.py:1541). Фронт-контракт согласован с реальным кодом; устарела фаза-2 карта.

### 4. assignJobToProject — СОГЛАСОВАН
- Фронт: `projects.ts:77-82` — `PATCH /api/v1/jobs/${jobId}/project`, тело `{project_id: number|null}`.
- Бэк: `projects.py:155-159` (`jobs_router.patch("/{job_id}/project")`) + модель `JobProjectAssign{project_id: int|None}` (projects.py:67-70, `extra="forbid"`).
- Ответ `JobProjectAssignResponse{job_id, project_id}` (фронт projects.ts:49-52 ↔ бэк projects.py:73-75). Путь/тело/ответ совпадают. `extra="forbid"` не нарушается — фронт шлёт только `project_id`.

### 5. manualPublishOne / listLikedReels — СОГЛАСОВАН
- manualPublishOne: фронт `scheduler.ts:339-344` — `POST /api/v1/scheduler/manual/publish-one`, тело `ManualPublishRequest{reel_artifact_id, job_id, publer_account_id, scheduled_at_utc, custom_caption?, custom_title?}` (scheduler.ts:190-197) ↔ бэк `scheduler.py:853-858` модель `ManualPublishRequest` (scheduler.py:261-269) с теми же 6 полями, `extra="forbid"`. Совпадает.
- listLikedReels: фронт `scheduler.ts:347-358` — `GET /api/v1/jobs/artifacts/liked` с query `project_id?`, `job_id?`, `limit?`. Путь под `/jobs`-префиксом (не `/scheduler`) — корректно, совпадает с эталоном (section-1 §2.7, строка 130). Параметры совпадают.

### 6. proxiesApi — СОГЛАСОВАН
- list: `proxies.ts:36` `GET /api/v1/proxies` ↔ `proxies.py:64`. Ответ `ProxyListResponse{items,total_count,total_size_bytes,total_size_mb}` совпадает (proxies.ts:21-26 ↔ proxies.py:50).
- cleanup: `proxies.ts:37-41` `DELETE /api/v1/proxies/cleanup?max_gb=` ↔ `proxies.py:79-87` (query `max_gb: float = -1.0`). Фронт опускает параметр, когда `undefined` → бэк применяет default. Совпадает.
- delete: `proxies.ts:42-45` `DELETE /api/v1/proxies/{sha256}` (encodeURIComponent) ↔ `proxies.py:104-114` (валидация ≥8 символов → 400, 0 удалено → 404). Метод/путь совпадают.

### 7. tier-выбор — СОГЛАСОВАН
- Фронт `components/settings/performance-groups/LLMGroup.tsx`:
  - `llm_tier_profile` ∈ `{fast, legacy}` (строки 27-30).
  - `llm_lite_variant` ∈ `{3_1, 2_5}` (строки 45-46).
  - `pipeline_llm_provider` ∈ `{gemini, zhipu}` (строки 14-15).
- Бэк `services/llm_clients/tier_resolver.py`:
  - `_tier_profiles` обрабатывает ключи `"fast"` и `"legacy"` (строки 46, 52).
  - `lite_variant` сравнивается с `"2_5"`, иначе fallback на `3_1` (строка 44, 66) — оба фронт-значения распознаются.
  - default при отсутствии: `"3_1"` (строки 127, 131).
- Значения, которые шлёт фронт, бэк-резолвер понимает 1:1. Совпадает.

### 8. cancelAssignment — РАССОГЛАСОВАН (минорный, UX-уровень)
- Бэк `scheduler.py:720-807` реализует богатый flow (НЕ stub, в отличие от того что section-1 §6 строка 291 называет "PARTIAL STUB"):
  - `published` → 409 "нельзя отозвать опубликованное" (scheduler.py:749-758).
  - `publer_post_id` есть → реальный `DELETE /posts` в Publer; при `PublerClientError` → 502 (scheduler.py:760-777).
  - `publer_job_id` без `post_id` → 409 "id ещё не сверён" (scheduler.py:784-796).
  - иначе локальный флип в `cancelled` → 200 `AssignmentRead`.
- Фронт `components/scheduler/CampaignDetailClient.tsx:526-546`:
  - На успех корректно подменяет assignment в state (строки 532-538).
  - На ошибку — только `setError(err.message)` (строки 539-540), показывает `detail` бэка как есть.
- **Разрыв:** фронт НЕ различает 409 (опубликовано / не сверён — действие невозможно, не повторять) и 502 (ошибка retract в Publer — можно повторить). Оба попадают в одну строку ошибки. `ApiError` несёт `status` (см. `lib/api/core.ts`), но компонент его не читает — нет ветвления по коду, нет подсказки "повторите" для 502 vs "необратимо" для 409. Контракт по методу/пути/телу/ответу СОГЛАСОВАН; рассогласована только обработка новых статус-кодов на клиенте.
- Доп. наблюдение: эталон-документ (section-1 §2.8 строка 175, §6 строка 291) описывает cancel как "PARTIAL STUB — local status flip only / не зовёт Publer DELETE". Реальный код это уже опровергает (зовёт `client.delete_posts`, scheduler.py:763). Карта фазы-2 устарела и здесь.

---

## Критичные рассогласования
Нет. Все 8 контрактов совпадают по методу / пути / телу запроса / форме ответа.

## К исправлению (приоритет)
1. **#8 (UX, low):** `CampaignDetailClient.handleCancel` — ветвить по `ApiError.status`: 409 → "необратимо/уже опубликовано", 502 → "ошибка Publer, повторите". Сейчас оба показываются одинаково.
2. **Документ (не код):** обновить `_orchestration/phase2-backend-map/section-1-api-data.md` §6 — `export` и `assignments/{id}/cancel` больше не PARTIAL STUB (Phase 6 реализовала реальный транскод и реальный Publer-retract). Фронт уже согласован с новым поведением.
