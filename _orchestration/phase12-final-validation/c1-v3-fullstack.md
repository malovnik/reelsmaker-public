# C1-V3 — Full-Stack & Runtime Validation (цикл 1 из 3)

Дата: 2026-05-27
Роль: Full-Stack & Runtime Validator
Стек (факт): backend FastAPI (uv, `videomaker.main:app`), frontend Vite SPA + React (НЕ Next.js)

## Итог: PASS

Сервис целостен. Все клиентские контракты совпадают с реальными роутами,
сквозной флоу связан без обрывов, бэкенд и фронт поднимаются чисто.

---

## 1. Контракты фронт ↔ бэк

Сверены все 8 клиентских модулей `apps/frontend/src/lib/api/*` против реальных
роутов `apps/backend/src/videomaker/api/routes/*`. **Рассогласований нет.**

Все роутеры включены под `prefix=/api/v1` через `routes/__init__.py`. Каждый
клиентский путь (метод + path) имеет точное соответствие на бэке:

| Клиент | Backend route | Статус |
|---|---|---|
| `jobsApi.*` (24 метода) | `routes/jobs.py` (prefix `/jobs`) | OK |
| `projectsApi.*` | `routes/projects.py` (`/projects` + `jobs_router`) | OK |
| `proxiesApi.*` | `routes/proxies.py` (`/proxies`) | OK |
| `postProductionApi.*` | `routes/post_production.py` | OK |
| `schedulerApi.*` | `routes/scheduler.py` | OK |
| `settingsApi.*` | `routes/settings.py` | OK |
| `subtitleApi.*` | `routes/settings.py` (fonts + subtitle_presets) | OK |
| `coreApi.health` | `routes/health.py` | OK |
| SSE `useJobSse` → `/jobs/{id}/stream` | `jobs.py:1241` | OK |

Особо проверенные новые ручки — все совпадают по методу/пути/параметрам:

- `cancelJob` → `POST /jobs/{id}/cancel` (jobs.py:1102) ✓
- `applyAutoConfig` → `PATCH /jobs/{id}/auto-config` (jobs.py:807); тип
  `AutoConfigPayload` — subset, совместим с backend `AutoConfigApplyPayload` ✓
- `clearAutoConfig` → `DELETE /jobs/{id}/auto-config` (jobs.py:844) ✓
- `exportReel` → `POST /jobs/{id}/reels/{reel_id}/export?preset=` (jobs.py:1461);
  `download_url` собирается как `/api/v1/files/{job_id}/reels/{reel_id}.{preset}.mp4`
  и ведёт на реальный роут `GET /files/{job_id}/{kind}/{name}` (files.py:17) ✓
- `manualPublishOne` → `POST /scheduler/manual/publish-one` (scheduler.py:852) ✓
- `assignJobToProject` → `PATCH /jobs/{id}/project` (projects.jobs_router:155) ✓
- `cancelAssignment` → `POST /scheduler/assignments/{id}/cancel` (scheduler.py:810) ✓
- `proxiesApi` → `GET /proxies`, `DELETE /proxies/cleanup`, `DELETE /proxies/{sha256}`
  (proxies.py:64/79/104) ✓

Замечание (не блокер): backend `/health` отдаёт `version` и `ffmpeg` поверх
типа `HealthResponse` фронта. Это непрорывный superset — клиент игнорирует
лишние поля. Можно при желании добавить поля в тип ради полноты.

---

## 2. Сквозной флоу (UI ↔ реальные ручки)

Цепочка связана без обрывов, все шаги используют реальные эндпоинты:

1. **create + upload** — `useWizardState.ts:359` `api.createJob(form)` (multipart) →
   `POST /jobs`.
2. **process (SSE)** — `useWizardState.ts:259` `useJobSse(jobId)` подключает
   `EventSource /jobs/{id}/stream`; терминирует на статусах done/error/cancelled,
   reconnect-логика с backoff присутствует.
3. **auto-config** (Automatic Mode) — `applyAutoConfig` / `clearAutoConfig`
   (useWizardState.ts:443, AutoConfigSummary.tsx:40).
4. **assign to project** — на `finalStatus=="done"` срабатывает
   `onJobCreated` → `api.assignJobToProject` (useWizardState.ts:262/366).
5. **cancel** — `api.cancelJob` доступен и в wizard (useWizardState.ts:478),
   и на JobDetail (JobDetailClient.tsx:40).
6. **reels / tinder** — `updateArtifactLike` (TinderClient/ReelCard),
   `saveReels` (ReelGrid.tsx:103).
7. **export / publish** — `exportReel` (ExportDialog через ClipDetailClient),
   `manualPublishOne` (ManualPublishButton.tsx:112), плановая публикация через
   scheduler-кампании (CampaignDetailClient + cancel/retry assignment).

Обрывов не найдено.

---

## 3. Runtime-смоук бэкенда — PASS

- `uv sync`: 156 пакетов, ок.
- Запуск: `uv run uvicorn videomaker.main:app --port 8099` (фон).
- Старт чистый, без падений. `.env` не требуется: все `*_api_key` в
  `core/config.py` имеют `default=None`. Publer-воркер сам отключается при
  отсутствии ключа (`publer_worker_disabled_no_api_key`).
- `curl /api/v1/health` → `200 OK`:
  `status:ok, version:0.1.0, llm_providers:[gemini], transcribers:[stable_ts_mlx, mlx_whisper], ffmpeg.available:true (7.1.1, videotoolbox_hevc:true)`.
- На старте сидятся 24 промпта + 4 subtitle-пресета, кэш шрифтов (187 шт).
- Процесс заглушен (`pkill -f uvicorn` — подтверждено dead).

Ничего не блокирует старт бэка. Реальные ключи нужны только для фактической
обработки (LLM/STT/Publer), не для подъёма сервиса.

## 4. Runtime-смоук фронта — PASS

- `pnpm install --frozen-lockfile` ок.
- `pnpm build` — `✓ built in 1.02s`, без ошибок (vite + tsc через build pipeline).
  Code-split по страницам, главный бандл `index` 327 KB (gzip 104 KB).
- `pnpm preview --port 4188`: root отдаёт валидный HTML
  (`<div id="root">`, title «Reelibra…», подключён `/assets/index-*.js`).
  Главный бандл — `HTTP 200`, 327578 байт. Не белый экран на уровне бандла.
- Процесс заглушен (`pkill -f "vite preview"` — подтверждено killed).
- Warning (не блокер): Node 22.11.0, Vite просит 22.12+. Build/preview прошли,
  но стоит обновить Node для устранения предупреждения.

## 5. NO MOCKS в проде — PASS

Скан `apps/backend/src` и `apps/frontend/src` на
`mock|stub|fake|TODO|FIXME|NotImplementedError|placeholder` (исключая тесты):
production-код чист. Единственный хит во фронте — описательный комментарий
в `settings.ts:182` («был hardcoded always-on»), не код-заглушка.

---

## Что блокирует полный запуск

Ничего критичного. Для подъёма сервиса блокеров нет. Для реальной работы
pipeline нужны: `GEMINI_API_KEY` (LLM), при облачном STT — `DEEPGRAM_API_KEY`,
для планировщика — Publer API key. Все опциональны на уровне старта.

Рекомендация (минорно): обновить Node до 22.12+; при желании дополнить
фронтовый `HealthResponse` полями `version`/`ffmpeg`.
