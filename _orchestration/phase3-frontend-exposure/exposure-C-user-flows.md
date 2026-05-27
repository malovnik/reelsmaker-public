# Exposure C — User Flows (как реально работает UI)

> Phase 3, агент User-Flow Analyst. Сквозная трассировка пользовательских сценариев во фронтенде (Vite/React Router, `apps/frontend/src/`) с маппингом на бэкенд-эндпоинты из [BACKEND-MAP](../phase2-backend-map/BACKEND-MAP.md). Цель: где пользователь застрянет, где flow упирается в заглушку, есть ли пошаговость.

Стек фронта: Vite + React Router 6 (data routers, loaders), не Next.js. Карта роутов — `router.tsx`. Навигация — `shell/NavRail.tsx` (9 пунктов: Студия `/`, Проекты, Шедулер, Профили, Модели, Субтитры, Пост-продакшн, Промпты, Производительность).

---

## A. Главный поток: видео → рилсы → экспорт

Это единственный по-настоящему сквозной сценарий, и он **весь живёт на главной странице** (`/`, `HomeClient` → `UploadWizard`). Проекты в нём не участвуют (см. обрыв #1).

### Шаг 1 — Загрузка и настройка (экран `/`, `UploadWizard.tsx` + `useWizardState.ts`)
Один длинный скролл-визард (6 нумерованных «Step» + аккордеон «Дополнительно»), не мастер с next/back:
1. **Профиль видео** (talking_head и т.п.) — `ProfileSelector`, данные из `profileMasks` (loader).
2. **Файл** — drag&drop / picker, до 30 ГБ, валидация расширения.
3. **Формат и количество** — аспект (9:16/1:1/4:5/16:9), reel count auto/custom (3–225).
4. **Субтитры** — выбор пресета (`subtitlePresets`), превью.
5. **Пост-продакшн** — пресет + per-job overrides (интро/аутро/зум/loudnorm/ч-б/split-screen).
6. **Доп-промпт** — `custom_system_prompt` (клеится к system-prompt всех LLM-стадий).
   + аккордеон: транскрайбер, LLM-провайдер, язык, кадрирование, proxy 1080p, рендер из оригинала, force reingest.
   + **Режим монтажа**: «Автоматический» (default) vs «Ручной».
   + Composer strategy.

Сабмит (`actions.submit`) → `POST /api/v1/jobs` (multipart, все поля formData) → возвращает `job.id`, проставляется `jobId`. **Загрузка идёт прямо на главной**, отдельного экрана прогресса аплоада нет.

### Шаг 2 — Auto-режим (если выбран, default)
После создания job: `POST /api/v1/jobs/{id}/auto-analyze` → `AutoConfigSummary` card внизу визарда. Юзер жмёт «Принять» → `PATCH /api/v1/jobs/{id}/auto-config` (15 параметров pacing/zoom/coherence) → пайплайн стартует. Либо «В ручной» → `switchToManual` (берёт настройки из `/settings/performance`).
**Ручной режим стартует пайплайн сразу** (без auto-analyze шага).

### Шаг 3 — Live-прогресс (SSE)
`useJobSse(jobId)` (`lib/sse.ts`): `EventSource` на `GET /api/v1/jobs/{id}/stream`. Парсит JSON-события (`stage/progress/message/transcript_cache/...`), на `status ∈ {done,error,cancelled}` закрывает поток. Реконнект с backoff `[1,2,4,8,15]s`, после исчерпания — «перезагрузи страницу». Прогресс-бар прямо в визарде (стадия + %), на `done` — ссылка «Открыть детали →» на `/jobs/{id}`.
Параллельно `HomeClient` поллит `GET /api/v1/jobs?limit=50` каждые 5с, **пока есть active jobs** (running/pending) — обновляет `JobList`.

### Шаг 4 — Детали джоба (`/jobs/:id`, `JobDetailClient.tsx`)
Loader тянет `getJob` + `listArtifacts`. Если job active — снова `useJobSse` + `PipelineTimeline` (этапы) + `JobHero` (прогресс, transcript cache бейдж). На финализации — рефетч job+artifacts.
Когда есть рилсы (`kind === "reel_output"`):
- **`HeatmapBar`** + **`ReelGrid`** (фильтры all/top/short/long/like/dislike, считаются клиентски через `viralScore.ts`).
- Кнопка «**Режим Tinder**» → `/jobs/:id/tinder`.
- `ReelCard` на каждый рилс: превью, like/dislike (`PATCH artifact like`), delete, **`ScheduleButton`** (см. обрыв #4).
- Bulk-бар при выделении: «**Сохранить в папку**» (`POST saveReels` → копирует в `saved/<folder>/`) и «Удалить».
- `ArtifactsAccordion` — вспомогательные артефакты (transcript/reel_plan и т.п.).

### Шаг 5 — Просмотр клипа (`/jobs/:id/reels/:reelId`, `ClipDetailClient.tsx`)
- `ClipScrubber` (видео) + `WaveformBar` (аудио-скраб, seek).
- `ScoreBlock` — «оценка Reelibra», **считается на клиенте** из meta (`computeViralScore`), не из бэка.
- Like/dislike (`updateArtifactLike`), подпись, **`CaptionsEditor`** (правка ASS-субтитров).
- «**Экспорт**» → `ExportDialog`.
- Навигация prev/next по siblings.

### Шаг 6 — Tinder-выбор (`/jobs/:id/tinder`, `TinderClient.tsx`)
Фуллскрин-оверлей. Стопка рилсов по одному: видео (autoplay/loop), свайпы + хоткеи (→ like, ← dislike, ↓ skip/next, ↑ назад, Space пауза). like/dislike → `PATCH artifact like`, skip ничего не пишет. SpeedSelector 1/1.5/2×, прогресс-бар. В конце — экран «всё просмотрено» со ссылкой назад в галерею.

### Шаг 7 — Экспорт (`ExportDialog.tsx`) — ЗАГЛУШКА
Пресеты TikTok/Reels/Shorts/X (битрейт+LUFS лейблы) → `POST .../export` → `download_url`. **Сам диалог честно пишет: «MVP: возвращает ссылку на существующий MP4 с метаданными пресета. Full transcode по bitrate — в следующей итерации.»** Бэк не перекодирует (BACKEND-MAP 2.7). Битрейт-лейблы декоративны.

---

## B. Настройка параметров обработки

Раздел `/settings/*` (`SettingsLayout` + `SettingsSubNav`), 8 экранов:
- `/settings/performance` — главный экран параметров пайплайна: ~20+ групп (narrative mode, reel count, pacing, multi-arc, coherence, cut-snap, J/L cuts, filler removal, ensemble, LLM tier…). Это «ручной режим» из визарда.
- `/settings/post-production` — пресеты интро/аутро/нормализация/зум/split-screen/ассеты.
- `/settings/subtitles` — ASS-стили + live-превью.
- `/settings/prompts` — редактор 12 промптов LLM-агентов.
- `/settings/models` — провайдеры/модели/транскрайберы.
- `/settings/profiles` — vision-профили (маски кадрирования).
- `/settings/brand`, `/settings/connections` — бренд-кит, ключи интеграций.
Сохранение через `useSettingsSave` + `SaveBar`. Все экраны имеют loader. Поток линейный, без онбординга — это «панель управления», не визард.

---

## C. Планирование публикаций — ДВА ПАРАЛЛЕЛЬНЫХ, НЕСВЯЗАННЫХ МЕХАНИЗМА

### C1 — Publer-шедулер (основной, рабочий)
`/scheduler` (`SchedulerDashboard`) → подэкраны:
- `/scheduler/accounts` — `AccountProfilesDashboard` (профили Publer-аккаунтов, нужны для генерации caption).
- `/scheduler/presets` — `CaptionPresetsDashboard`.
- `/scheduler/new` — **`CampaignWizard`** (настоящий 4-шаговый мастер с next/back/step-indicator):
  1. **Источник** — `ReelPicker`: только **лайкнутые** рилсы, фильтр по проекту/джобу (`listLikedReels({projectId, jobId})`).
  2. **Назначения** — `AccountsPicker` (Publer-аккаунты с профилем).
  3. **Расписание** — `ScheduleTimeline` (per_date / single_day / serial, tz Asia/Ho_Chi_Minh).
  4. **Подтверждение** → `createCampaign` + сразу `approveCampaign` → `/scheduler`.
  Бэк генерит caption (Gemini) и ставит в очередь; `PublerWorker` доставляет (BACKEND-MAP 2.6). При ошибке после create — авто-`deleteCampaign` (хороший rollback).
- `/scheduler/campaigns/:id` — `CampaignDetailClient` (статусы публикаций).

### C2 — «Расписание» (`/schedule`, legacy/parallel) + `ScheduleButton`
Отдельный пункт логики: `ScheduleButton` на каждом `ReelCard` → модалка с платформой YouTube/Instagram, title/desc/tags/visibility → **прямой `fetch POST /api/v1/schedule`** (не через `schedulerApi`, минуя Publer). Страница `/schedule` (`ScheduleClient`) показывает эти запланированные посты, worker «раз в минуту». Instagram-ветка честно предупреждает про Facebook App Review.
**Это второй, отдельный от Publer, механизм публикации** — см. обрыв #5.

---

## ОБРЫВЫ ПОТОКА

1. **Проекты оторваны от создания джобов.** `/projects` позволяет создавать/редактировать/удалять проекты («папки для джобов»), а `ReelPicker` в кампании фильтрует по `project_id`. НО: `UploadWizard` не отправляет `project_id` при `POST /jobs`, и API `assignJobToProject` (`lib/api/projects.ts`) **не вызывается ни из одного компонента**. Пользователь создаёт проект — и не может положить в него ни один джоб. Фича-папки нерабочая end-to-end; фильтр «по проекту» в шедулере всегда пустой по project.

2. **Экспорт — заглушка (декоративный transcode).** `POST .../export` отдаёт ссылку на тот же неперекодированный MP4. UI это признаёт текстом в диалоге, но пресеты TikTok/Reels/Shorts/X с битрейтами создают ложное ожидание разного качества/формата.

3. **`ManualPublishButton` — мёртвый компонент.** Полностью реализован (выбор аккаунта, datetime, custom caption/title, `manualPublishOne`), но **нигде не отрендерен**. Прямой путь «опубликовать один рилс сразу из галереи» в UI недоступен — только через многошаговую кампанию или legacy `ScheduleButton`.

4. **Score «Reelibra» считается на клиенте.** `ClipDetailClient`/`ReelGrid` вычисляют viral-score через `viralScore.ts` из meta, а не из бэкенда. Фильтр «Топ ≥90» и кольцо оценки — клиентская эвристика, не отражает реальный per-reel scoring пайплайна.

5. **Два несвязанных механизма публикации.** Publer-кампании (`/scheduler/*`, `schedulerApi`) и прямой `/api/v1/schedule` + `/schedule` страница (`ScheduleButton`, YouTube/Instagram Graph API). Они не пересекаются: рилс, запланированный через `ScheduleButton`, не виден в `/scheduler`, и наоборот. Пользователь не понимает, какой из двух «правильный». Один из них (legacy `/schedule`) дублирует функцию и сбивает с толку.

6. **Нет навигации к Tinder/деталям до завершения.** Кнопка Tinder и ReelGrid появляются только когда `reels.length > 0`. Пока идёт обработка — только timeline. Это ок, но: на главной после `done` единственный путь дальше — ссылка «Открыть детали», легко пропустить (мелкий текст в прогресс-карточке).

7. **`cancel` джоба не выражен в UI.** Бэк имеет `POST .../cancel` (флипает статус, но не ретрактит Publer-пост), `JobStatus.cancelled` обрабатывается в SSE-хуке, но кнопки «Отменить обработку» в `JobDetail`/`UploadWizard` нет. Запустив длинную нарезку, пользователь не может её остановить из UI.

8. **«Сохранить в папку» (`saved/<folder>/`) ведёт в никуда для пользователя.** Копирует файлы в серверную папку, но в UI нет экрана этой папки — обратной связи кроме toast «Сохранено N файлов» нет, повторно найти их через интерфейс нельзя.

---

## ВЕРДИКТ: пошаговость / онбординг

**Онбординга НЕТ.** Нет welcome/empty-state-гайда, нет «создай первый проект → загрузи → …», нет туров. Единственная подсказка для новичка — инлайн-ошибка «задай `GEMINI_API_KEY`», если нет провайдера.

**Пошаговость — частичная и неравномерная:**
- Главный поток (создать рилсы) **псевдо-пошаговый**: визард пронумерован (Step 1–6), но это один скролл-экран, всё видно сразу, нет принудительной последовательности. Зато сильная сторона — auto-режим (`AutoConfigSummary`) реально ведёт новичка («робот всё решит»), и SSE-прогресс + переход на детали связывают этапы.
- Кампании (`CampaignWizard`) — **единственный настоящий мастер** с next/back/валидацией шагов.
- Остальное (`/settings/*`, `/projects`, `/scheduler` дашборды) — **набор разрозненных экранов** панели управления.

**Итог:** новый пользователь от «ничего» до «готовых рилсов» дойдёт по главной странице за счёт auto-режима и живого прогресса — этот путь связный. Но дальше (организация в проекты, выбор площадки публикации, экспорт под платформу) flow рассыпается на обрывы: проекты не подключить, экспорт фиктивный, два конкурирующих способа публикации, мёртвая кнопка ручной публикации. Цельного «путешествия» от загрузки до опубликованного поста нет — есть рабочее ядро (загрузка→нарезка→просмотр→разметка) и разрозненная, частично нерабочая периферия вокруг публикации.
