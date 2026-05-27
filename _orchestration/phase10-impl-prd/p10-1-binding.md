# P10-1 — Data-Binding: спека ↔ бэкенд ↔ клиент

> Роль: Frontend-Backend Binding Analyst. Сверка UI-REDESIGN-SPEC (Phase 9: d2 Пошаговый S1-S11, d3 Эксперт 8 групп, d5 7 экранов) с реальными бэкенд-ручками (BACKEND-MAP, section-1, 81 эндпоинт) и текущим клиентом `apps/frontend/src/lib/api`.
> Вопрос на каждую строку: контрол спеки → какая ручка его обслуживает → есть ли клиентская функция?

## TL;DR
- **Data-binding готовность: ~92%.** Почти каждый контрол спеки имеет реальную ручку И клиентскую функцию. Клиент `lib/api` покрывает все 8 роутеров.
- **Пробелов «спека-без-бэка»: 3** (все — клиентские вычисления/UX, не дыры API): клиентский скор рилса, heatmap, ETA/density-оценка. Спека уже честно их маркирует.
- **Ручек-не-в-UI: 4** (мелкие): `getDefaultPostProductionPreset`, `getSubtitlePreset/{id}` (single-get дублирует list), `getVisionProfile/{p}` (single), `assignJobToProject` частично.
- **Расхождение карты: 82 ≠ 81.** `POST /jobs/{id}/cancel` есть в коде (jobs.py:1102) и в клиенте (`cancelJob`), но section-1 его НЕ перечислила в таблице 24 jobs-ручек. Реальный счёт — 82.
- **Honesty-фикции (tier/export/chaptered/cancel-assignment) поданы честно** и в спеке, и подтверждены в клиенте (export-тип содержит декларативные bitrate/lufs — UI обязан подавать сноску «как есть»).

---

## 1. Data-binding таблица — Пошаговый (S1-S11)

| Шаг / контрол | Бэкенд-ручка | Клиентская функция | Статус |
|---|---|---|---|
| СТАРТ «Создать проект» | — (навигация) | — | UI-only ✅ |
| S1 поле «Название» + создать | `POST /projects` | `projectsApi.createProject` | ✅ |
| S1 карты существующих | `GET /projects` | `projectsApi.listProjects` | ✅ |
| S1 → привязка project_id к job | `POST /jobs` form `project_id`* / `PATCH /jobs/{id}/project` | `jobsApi.createJob(form)` / `projectsApi.assignJobToProject` | ⚠ см. прим. |
| S2 drag&drop файла + probe | `POST /jobs` (multipart `file`) | `jobsApi.createJob(form)` | ✅ |
| S2 валидация размера (30 ГБ) | 413 от `POST /jobs` | `ApiError` 413 | ✅ |
| S3 Режиссёрский/Сбаланс./Быстрый | `narrative_mode` (perf) bottom_up/map_reduce/viral_2026 | `settingsApi.updatePerformanceSettings` | ✅ |
| S3 chaptered (скрыт) | `narrative_mode=chaptered` (broken) | поле есть в типе, в S3 не рендерится | ✅ честно скрыт |
| S4 пресеты субтитров + превью | `GET /settings/subtitle_presets` | `subtitleApi.listSubtitlePresets` | ✅ |
| S4 «без субтитров» | `subtitle_style_inline`/опуск в `POST /jobs` | `createJob(form)` | ✅ |
| S5 «убрать паузы/паразиты» | `filler_removal_enabled`, `pause_compression_enabled` (perf) или per-job overrides | `updatePerformanceSettings` / form | ✅ |
| S5 «приближение на акцентах» | `punch_in_zoom_enabled` (perf) | `updatePerformanceSettings` | ✅ |
| S5 «выровнять громкость» (lock ON) | loudnorm в render (всегда ON) | — (декларативно ON) | ✅ честно lock |
| S5 «интро/аутро» | `post_production_preset_id` в `POST /jobs` | `postProductionApi.list...Presets` + form | ✅ |
| S6 STT Mac/Deepgram | `transcriber` в `POST /jobs` (каталог `GET /settings/models`) | `createJob` + `settingsApi.models` | ✅ |
| S6 LLM Gemini/Zhipu | `pipeline_llm_provider`(perf) / `llm_provider`(form) | `updatePerformanceSettings`/`createJob` | ✅ |
| S6 слайдер качества (tier) + warn | `llm_tier_profile`/`llm_lite_variant` (perf) | `updatePerformanceSettings` | ✅ **DECORATIVE** — warn обязателен |
| S7 сводка + «измен.» | агрегат state, не ручка | — | UI-only ✅ |
| S7 «Запустить» (Auto-цепочка) | `POST /jobs` → `POST /jobs/{id}/auto-analyze` → `PATCH /jobs/{id}/auto-config` | `createJob` → `autoAnalyzeJob` → `applyAutoConfig` | ✅ цепочка полная |
| S8 live SSE + стадии | `GET /jobs/{id}/stream` | (raw EventSource/fetch, не в `lib/api`)** | ✅ контракт есть |
| S8 «Отменить нарезку» | `POST /jobs/{id}/cancel` | `jobsApi.cancelJob` | ✅ (карта забыла ручку) |
| S9 ReelGrid превью | `GET /jobs/{id}/artifacts` + `/jobs/{id}/thumbnail` | `jobsApi.listArtifacts` / `jobThumbnailUrl` | ✅ |
| S9 Heatmap | — (клиентский расчёт из reel_plan/score) | — | ⚠ спека-без-бэка |
| S9 оценка/кольцо | — (клиентская эвристика) | `avg_composite_score` на job есть, per-reel — клиент | ⚠ спека-без-бэка (честно) |
| S9 фильтры all/top/short/long | клиентская фильтрация artifacts | `listArtifacts` | ✅ |
| S10 Tinder like/dislike | `PATCH /jobs/{id}/artifacts/{aid}/like` | `jobsApi.updateArtifactLike` | ✅ |
| S10 скорость 1/1.5/2× | — (player) | — | UI-only ✅ |
| S11 «Скачать выбранные» | `POST /jobs/{id}/reels/{rid}/export` + `/files/...` | `jobsApi.exportReel` | ✅ **PARTIAL** — «как есть» |
| S11 «Создать кампанию» | `POST /scheduler/campaigns` (мастер) | `schedulerApi.createCampaign` | ✅ |

\* `project_id` в форме `POST /jobs`: section-1 «POST /jobs Form fields» project_id **не перечисляет** явно. Спека S1/S7 утверждает «шлёт project_id в POST /jobs». **Требует верификации в Phase 11**: либо поле есть в форме (карта неполна), либо привязка через `PATCH /jobs/{id}/project` пост-фактум (ручка существует, клиент `assignJobToProject` есть). Безопасный путь — `assignJobToProject` сразу после `createJob`.

\** SSE-стрим (`GET /jobs/{id}/stream`) обслуживается хуком `useJobSse` (вне `lib/api`, т.к. EventSource, не `request<T>`). Контракт SSE в section-1 §3 полный. Клиентский хук — отдельная проверка Phase 11.

---

## 2. Data-binding — Эксперт (8 групп P3)

| Группа · контрол | Бэкенд-ручка | Клиент | Статус |
|---|---|---|---|
| **G1 Narrative** режим/число/стратегия/промпт | perf + `POST /jobs` form | `updatePerformanceSettings`/`createJob` | ✅ |
| G1 reducer ensemble / cross-chunk / multi-arc / chunking / coherence | perf поля (все присутствуют в `PerformanceSettings`) | `updatePerformanceSettings` | ✅ |
| G1 редактор 12 промптов | `GET/PUT /settings/prompts/{key}`, `GET /settings/prompts` | `listPrompts/getPrompt/upsertPrompt` | ✅ |
| **G2 Vision** мастер-тумблер | `GET/PUT /settings/vision` | `getVisionSettings/updateVisionSettings` | ✅ **OPT-IN** |
| G2 профиль кадра | `vision_profile` form / `PATCH /jobs/{id}/profile` | `createJob`/`updateJobProfile` | ✅ |
| G2 переопределить маску | `PUT /settings/profiles/{p}`, list/reset | `listVisionProfiles/updateVisionProfile/resetVisionProfile` | ✅ |
| G2 face-tracking | `face_tracker_enabled` (perf) | `updatePerformanceSettings` | ✅ **CPU-HEAVY/OFF** |
| G2 split-screen | `split_screen_enabled` form / `SplitScreenConfig` в post-prod | `createJob` / `postProductionApi` | ✅ **OPT-IN** |
| G2 visual-валидатор / cover-selector | vision-флаги (perf/vision) | `updatePerformanceSettings` | ✅ OPT-IN |
| G2 подсказка профиля по лицам | `GET /jobs/{id}/profile/suggestion` | `jobsApi.getProfileSuggestion` | ✅ |
| **G3 Audio/DSP** loudnorm/cut-snap | render-флаги (perf) `cut_snap_enabled` | `updatePerformanceSettings` | ✅ |
| G3 pause/filler/breath/leveller/jl/snap | perf поля (все в `PerformanceSettings`) | `updatePerformanceSettings` | ✅ |
| G3 mouth-sound removal | `mouth_sound_removal_enabled` (perf) | `updatePerformanceSettings` | ✅ **DORMANT** |
| G3 анализ аудио | `POST /jobs/{id}/auto-analyze` | `jobsApi.autoAnalyzeJob` | ✅ |
| **G4 Субтитры** пресет CRUD | `/settings/subtitle_presets` (5 ручек) | `subtitleApi.*SubtitlePreset` | ✅ |
| G4 инлайн-стиль | `subtitle_style_inline` form (`SubtitleStyleConfig`) | `createJob` + тип `SubtitleStyleConfig` | ✅ |
| G4 шрифт + пересканировать | `GET /settings/fonts`, `POST /settings/fonts/refresh` | `subtitleApi.listFonts/refreshFonts` | ✅ |
| G4 редактор .ass рилса | `GET/PATCH /jobs/{id}/reels/{rid}/subtitles` | `getReelSubtitles/updateReelSubtitles` | ✅ |
| **G5 Post-prod** пресеты CRUD | `/post_production/presets` (5) | `postProductionApi.*Preset` | ✅ |
| G5 загрузка интро/аутро | `POST /post_production/assets` (413) | `postProductionApi.importAsset` | ✅ |
| G5 ассеты + превью-кадр | `/assets`, `/assets/{id}/thumbnail` | `listAssets/getAsset/assetThumbnailUrl` | ✅ |
| G5 zoom/Ken Burns | `PostProductionConfig.zoom_*` | `postProductionApi` (config) | ✅ |
| G5 per-job overrides | `post_production_overrides_json` form | `createJob` + `PostProductionOverrides` | ✅ |
| **G6 Модели/Tier** провайдер/модель/транскрайбер | `GET /settings/models` + form | `settingsApi.models` + `createJob` | ✅ |
| G6 Tier pro/flash | tier (perf) | `updatePerformanceSettings` | ✅ **DECORATIVE** |
| G6 язык/aspect/fit/proxy | form-поля `POST /jobs` | `createJob` | ✅ |
| G6 проба возможностей | `GET /health` | `coreApi.health` | ✅ |
| **G7 Публикация** статус Publer | `GET /scheduler/connection/status` | `getConnectionStatus` | ✅ |
| G7 аккаунты + профили | `/scheduler/accounts`, `/accounts/profiles` (CRUD) | `listPublerAccounts/listProfiles/upsertProfile/deleteProfile` | ✅ |
| G7 пресеты подписей | `/scheduler/presets` (CRUD) | `list/create/update/deletePreset` | ✅ |
| G7 кампании | `/scheduler/campaigns` (CRUD+approve) | `list/create/get/approve/deleteCampaign` | ✅ |
| G7 назначения + edit | `/scheduler/assignments` (list/patch) | `listAssignments/updateAssignment` | ✅ |
| G7 одиночная публикация | `POST /scheduler/manual/publish-one` | `manualPublishOne` | ✅ |
| G7 отменить назначение | `POST /scheduler/assignments/{id}/cancel` | `cancelAssignment` | ✅ **PARTIAL** |
| G7 retry | `POST /scheduler/assignments/{id}/retry` | `retryAssignment` | ✅ |
| **G8 Прокси/Сервис** кэш/cleanup/delete | `/proxies` (3) | `proxiesApi.listProxies/cleanupProxies/deleteProxy` | ✅ |
| G8 force re-ingest | `force_reingest` form | `createJob` | ✅ |
| G8 purge soft/hard/nuke | `DELETE /jobs?purge=` | `jobsApi.deleteJob(purge)` | ✅ **DESTRUCTIVE** |

---

## 3. Data-binding — d5 экраны (доп. контролы, не покрытые S/G выше)

| Экран · контрол | Бэкенд-ручка | Клиент | Статус |
|---|---|---|---|
| 1 Dashboard список джобов | `GET /jobs?limit` | `jobsApi.listJobs` | ✅ |
| 1 job-card thumb 16:9 | `GET /jobs/{id}/thumbnail` | `jobThumbnailUrl` | ✅ |
| 1 ⋯ переименовать | `PATCH /jobs/{id}/rename` | `jobsApi.renameJob` | ✅ |
| 1 ⋯ в проект | `PATCH /jobs/{id}/project` | `assignJobToProject` | ✅ |
| 1 ⋯ удалить | `DELETE /jobs?purge=` | `deleteJob` | ✅ |
| 2 PipelineTimeline | `GET /jobs/{id}/stream` + `GET /jobs/{id}` | SSE-хук + `getJob` | ✅ |
| 2 like/save рилса | `PATCH .../like`, `POST /jobs/{id}/saved` | `updateArtifactLike`/`saveReels` | ✅ |
| 2 удалить рилс | `DELETE /jobs/{id}/artifacts/{aid}` | `deleteArtifact` | ✅ |
| 2 сменить vision-профиль | `PATCH /jobs/{id}/profile` | `updateJobProfile` | ✅ |
| 3 плеер + экспорт | `/files/...` + `POST .../export` | `exportReel` | ✅ PARTIAL |
| 3 правка .ass | `GET/PATCH .../subtitles` | `get/updateReelSubtitles` | ✅ |
| 4 Tinder like/undo | `PATCH .../like` | `updateArtifactLike` | ✅ |
| 5 пул лайкнутых рилсов (источник кампании) | `GET /jobs/artifacts/liked` | `schedulerApi.listLikedReels` | ✅ |
| 5 dashboard кампаний | `GET /scheduler/campaigns` | `listCampaigns` | ✅ |
| 5 «Снять» назначение | `POST .../assignments/{id}/cancel` | `cancelAssignment` | ✅ PARTIAL |
| 5 неподключённая площадка «Добавить в Publer ↗» | external link (нет dead OAuth) | — | ✅ честно |
| 6 проекты CRUD | `/projects` (6) | `projectsApi.*` | ✅ |
| 6 деталь проекта + джобы | `GET /projects/{id}` (ProjectDetail) | `getProject` | ✅ |
| 7 настройки sub-nav | все `/settings/*` | `settingsApi/subtitleApi/postProductionApi` | ✅ |

---

## 4. Пробелы: спека обещает то, чего нет в бэке

Все три — **клиентские/UX-конструкции**, не дыры API. Спека уже подаёт их честно — претензий нет, но Phase 11 должна реализовать строго в клиенте.

1. **Per-reel «оценка/скор»** (S9 кольцо, S10/d5-3 «честная эвристика»). Бэк отдаёт только `avg_composite_score` на job (`JobRead`) + meta артефакта. Per-reel число для кольца **считается клиентом** из reel_plan/meta. Спека d5-2/d5-3 прямо предписывает подавать как «эвристику, не прогноз виральности» — выполнено честно.
2. **Heatmap силы моментов** (S9). Нет ручки `/heatmap`. Источник — клиентский расчёт по плотности/скорам артефактов. Реализуемо из `listArtifacts` meta, но это вычисление фронта.
3. **Оценка «~40 рилсов · ~6-10 мин»** (S7 сводка). Density-эвристика режима, не ручка. Клиентский расчёт.

Граничный случай (не пробел, но проверить):
4. **`project_id` в `POST /jobs`** — см. прим.* в §1. Если поле отсутствует в форме — Пошаговый S7 «шлёт project_id в POST /jobs» некорректен; страховка `assignJobToProject` после создания (ручка+клиент есть). **Верифицировать форму в Phase 11.**

---

## 5. Ручки, не выведенные ни в один режим

Малозначимы — в основном single-GET дубли коллекций или редко нужные. Не блокеры.

| Ручка | Клиент есть? | Почему не в UI | Рекомендация |
|---|---|---|---|
| `GET /post_production/presets/default` | `getDefaultPostProductionPreset` ✅ | не привязана к экрану; контракт-quirk (200+`null`) | использовать для авто-выбора дефолт-пресета в S5/G5; клиент уже обрабатывает null |
| `GET /settings/subtitle_presets/{id}` | `getSubtitlePreset` ✅ | list покрывает превью S4/G4 | оставить для деталь-редактора пресета (G4 CRUD) |
| `GET /settings/profiles/{profile}` | `getVisionProfile` ✅ | list+update покрывают G2 | оставить для редактора одной маски |
| `GET /post_production/assets/{id}` | `getAsset` ✅ | list+thumbnail покрывают G5 | оставить для деталь-вью ассета |
| `GET /scheduler/assignments` фильтр по status | `listAssignments(status)` ✅ | d5-5 показывает все статусы карточками | использовать фильтр-табы на деталь-кампании |
| `GET /jobs/{id}/source-thumbnail` | `sourceThumbnailUrl` ✅ | d3-P2 «превью кадра» упоминает, но не в S-шагах | вывести в Эксперт P2 превью |

**Вывод:** «осиротевших» ручек без клиента — 0. Все 82 ручки имеют клиентскую обёртку. Часть single-GET просто не нужна основным экранам (list-варианты покрывают), что нормально.

---

## 6. Honesty-система — сверка фикций с подачей

| Фикция (BACKEND-MAP §6) | Реальность | Подача в спеке | Клиент-сигнал | Вердикт |
|---|---|---|---|---|
| **tier «pro»** | физически Flash-Lite | Пошаговый S6: warn медным `#B87333` «Макс = Эконом». Эксперт G6: бейдж **DECORATIVE** | `llm_tier_profile` поле есть, семантики качества нет | ✅ честно |
| **export** | отдаёт MP4 как есть (PARTIAL STUB; Phase 6 утверждает «реально перекодирует», section-1 §6 — «не применяет bitrate/lufs») | Пошаговый S11 + d5-3: сноска «отдаём MP4 как есть, перекодирование в планах». Эксперт: **PARTIAL** | `exportReel` тип содержит `bitrate_k/target_lufs` (декларативные!) | ⚠ **противоречие источников** — см. ниже |
| **chaptered** | broken на монологах | Пошаговый S3: **скрыт**. Эксперт/d5-7: показан с ⚠ «ненадёжно» + бейдж **BROKEN** | поле `narrative_mode` включает `chaptered` | ✅ честно |
| **cancel-назначения** | local status flip, не отзывает Publer | d5-5: «в очереди — снимем; опубликовано — только Открыть пост». Эксперт G7: **PARTIAL** | `cancelAssignment` | ✅ честно |
| **cancel-job** | реальный (Task.cancel + mark_cancelled), сохраняет частичный результат | S8/d5-2: ConfirmDialog «готовые рилсы сохранятся» | `cancelJob` | ✅ честно |
| **YouTube OAuth** | мёртвый, таблицы удалены | d5-5: нет страницы connections, «Добавить в Publer ↗» | — (нет dead-ручки) | ✅ честно |
| **dormant zoom/mouth-sound** | жгут CPU, выход выброшен | Пошаговый: скрыт. Эксперт G3: бейдж **DORMANT/CPU-HEAVY** | perf-флаги есть | ✅ честно |

**⚠ Противоречие для Phase 11 (export):** BACKEND-MAP §«Обновление после Phase 6» утверждает «export реально перекодирует (ffmpeg)», но section-1 §6 (более детальный контракт) держит **PARTIAL STUB**: bitrate/lufs декларативны, файл не перекодируется. Клиентский тип `exportReel` возвращает `bitrate_k/target_lufs` — если они не применяются, UI обязан НЕ показывать их как реальные параметры (спека d5-3 это уже требует: «без косметических цифр битрейта»). **Действие Phase 11:** верифицировать по коду `export`-роута, какое утверждение верно; подать UI по факту.

---

## 7. Готовность data-binding: итог

| Срез | Готовность |
|---|---|
| Пошаговый S1-S11 | ~95% (минус: per-reel скор, heatmap, ETA — клиентские; project_id в form — verify) |
| Эксперт 8 групп | ~98% (все ~82 ручки имеют клиент; honesty-бейджи маппятся) |
| d5 7 экранов | ~95% |
| Клиент `lib/api` ↔ бэкенд | 100% покрытие ручек обёртками; 0 осиротевших ручек |
| Honesty-подача | ✅ все 7 фикций честны в спеке; 1 требует верификации (export) |
| **Совокупно** | **~92%** |

**Блокеры для Phase 11 (импл-PRD):**
1. Верифицировать `project_id` в форме `POST /jobs` (иначе страховать `assignJobToProject`).
2. Разрешить противоречие export (перекодирует / stub) — подать UI по факту кода.
3. Реализовать клиентские: per-reel эвристика-скор, heatmap, density-ETA (честно, как предписывает спека).
4. SSE-хук `useJobSse` — вне `lib/api`, отдельная проверка контракта §3.
5. Поправить BACKEND-MAP: `POST /jobs/{id}/cancel` отсутствует в section-1 — реальный счёт 82, не 81.
