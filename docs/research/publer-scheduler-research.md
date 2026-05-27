# Publer Scheduler — Research & Подготовка

> **Дата:** 2026-04-23
> **Автор:** Claude (Opus 4.7)
> **Статус:** исследование, до написания кода требуется апрув архитектуры

---

## 1. Что просит user (парсинг запроса)

1. **Шедулер через API Publer** (`https://publer.com/docs`) — не OAuth-to-platform напрямую, а через агрегатор.
2. **Модуль уникальных описаний** — для каждого аккаунта, куда публикуется рилс, описание (caption) генерится отдельно (язык/стиль/аудитория/хештеги этого аккаунта).
3. **Публикация лайкнутых рилсов** — из «кабинета» (UI job detail), где уже работает `PATCH /artifacts/{id}/like`.
4. **Выбор проектов-папок** — из каких job-артефактов брать пул рилсов (current видео, прошлые видео, подборка).
5. **Единое время публикации в разные даты** — паттерн «время T в датах [D1, D2, …]» + «единый batch по нескольким аккаунтам».

---

## 2. Publer API — ключевые факты

### 2.1 Доступность и лимиты

- **План:** Business / Enterprise only. Обычная подписка не даёт ключа. Нужно проверить, какой тариф у user'а.
- **Rate limit:** 100 req / 2 мин / пользователь.
- **Base URL:** `https://app.publer.com/api/v1`.
- **Auth:** `Authorization: Bearer-API <API_KEY>` + `Publer-Workspace-Id: <WS_ID>` (кастомная схема, НЕ стандартный Bearer).

Ключ создаётся в Settings → Access & Login → API Keys.

### 2.2 Полный эндпоинт-каталог, нужный нам

| Назначение | HTTP | Path |
|---|---|---|
| Мои workspace'ы | GET | `/workspaces` |
| Социальные аккаунты workspace'а | GET | `/accounts` |
| Upload файла (≤200 MB) | POST (multipart) | `/media` |
| Upload по URL (async, для >200 MB) | POST | `/media/from-url` |
| Создать batch постов (schedule/draft) | POST | `/posts/schedule` |
| Создать и опубликовать сразу | POST | `/posts/schedule/publish` |
| Опрос async-джоба | GET | `/job_status/{job_id}` |
| Список существующих постов | GET | `/posts?state=scheduled` |
| Удалить пост | DELETE | `/posts/{post_id}` |

### 2.3 Схема создания поста (bulk)

```json
{
  "bulk": {
    "state": "scheduled",
    "posts": [
      {
        "networks": {
          "instagram": {
            "type": "video",
            "text": "Caption для инсты",
            "media": [{
              "id": "<media_id_from_publer>",
              "path": "https://cdn.publer.com/videos/xxx.mp4",
              "type": "video",
              "thumbnails": [{
                "id": "<thumb_id>",
                "small": "...",
                "real": "..."
              }],
              "default_thumbnail": 0
            }],
            "details": {
              "type": "reel",
              "feed": false,
              "trial_reel": "MANUAL"
            }
          }
        },
        "accounts": [
          {
            "id": "<account_id>",
            "scheduled_at": "2026-04-28T19:00:00+03:00",
            "labels": ["videomaker-auto"]
          }
        ]
      }
    ]
  }
}
```

**Важно для нашего кейса:**

- `networks.<net>.text` — **один** текст на пост, шарится между всеми аккаунтами в `accounts[]` одного `post`. Чтобы получить **разный caption per account**, нужно слать **отдельный `post` в `posts[]`** для каждого аккаунта, даже если видео то же. В one bulk можно запихать пачку.
- `accounts[].scheduled_at` может быть разным — можно один пост запланировать на разные даты на разных аккаунтах.
- `labels[]` — наш маркер «это из videomaker» для последующего аудита в UI Publer.

### 2.4 Reels / Shorts / Stories — ограничения

| Формат | Длительность | Аспект | Макс. размер | Платформы |
|---|---|---|---|---|
| Reel | 3–90 сек | 9:16 | 1 GB | Instagram, Facebook |
| Short | ≤60 сек | 9:16 | 2 GB | YouTube |
| Story | ≤15 сек | 9:16 | 1 GB | Instagram, Facebook |
| ⚠️ TikTok | **не поддерживается через Publer API** |

Наши рилсы (default 45–60 сек, max 90) попадают в Reel + возможно Short (если длина ≤60).

### 2.5 Async workflow

1. POST → ответ `{success, data: {job_id}}`.
2. GET `/job_status/{job_id}` цикл пока `status ∈ {working}`.
3. `status = complete` → успех, `failed` → `result.payload.failures` с ошибками.

### 2.6 Upload media

- ≤200 MB: multipart → сразу `media_id`. Наши 9:16 HEVC рендеры 45-60 сек обычно 20-80 MB — влезаем.
- >200 MB: `media/from-url` → job_id → ждать complete → media_id. Нужен публичный URL (наш backend должен отдавать signed URL рилса).

---

## 3. Что уже есть в videomaker (НЕ ломать, но учесть)

### 3.1 Legacy scheduler (direct OAuth)

```
apps/backend/src/videomaker/
├── models/scheduler.py                  # OAuthConnectionRow + ScheduledPostRow
├── services/scheduler_worker.py         # фоновый worker, poll scheduled_posts
├── services/scheduled_posts_store.py    # CRUD очереди
└── services/connections_store.py        # YouTube/IG OAuth токены
```

Модель `ScheduledPostRow`:
- `platform ∈ {youtube, instagram}` (StrEnum), `publish_at`, `status ∈ {pending, uploading, done, error, cancelled}`, `attempts`, `external_video_id/url`.
- Reel_id + job_id → задача: «возьми рилс X из джоба Y и загрузи в YouTube/IG».
- **Worker сейчас сам льёт в YouTube Data API / Instagram Graph API** — конкурирует с Publer подходом.

**Решение (требует апрува user'а):**
- **Вариант A:** Отключить старый worker, перевести `ScheduledPostRow` на Publer backend (оставить таблицу, сменить выполнение). Плюс: минимальные изменения схемы. Минус: старый код гниёт в репо.
- **Вариант B:** Новый параллельный модуль `publer_scheduler` + новая таблица `publer_scheduled_posts`. Плюс: чистая архитектура, легко сравнить. Минус: дубль store + worker.
- **Вариант C:** Snapshot того что есть, удалить legacy (не запущен в prod), делать один модуль `scheduler` на Publer. Плюс: нет legacy. Минус: нужно коммитить удаление.

Рекомендация: **вариант C**, если legacy не использовался в реальных публикациях. Нужно спросить user'а.

### 3.2 Лайки рилсов — уже работает

- `PATCH /api/v1/jobs/{job_id}/artifacts/{artifact_id}/like` с `{liked: "none"|"like"|"dislike"}`.
- Хранится в `Artifact.meta['liked']` (не отдельная колонка).
- На `like` считается 256-dim Gemini embedding хука → `Artifact.embedding_json`. Используется preference-memory.
- UI уже показывает лайки в job detail.

**Для шедулера:** нужен запрос «все артефакты где `meta->>'liked' = 'like'` и `kind = 'reel'` + optional filter по job_ids / date range». Добавить `GET /api/v1/artifacts/liked?project_ids=...&limit=...` — одна новая роут-функция, таблицы новые не нужны.

### 3.3 «Проекты-папки»

Текущая модель: **1 видео = 1 `Job` = 1 папка `data/artifacts/<uuid>/`**. Отдельной сущности «project / folder» как логической группы джобов нет.

Варианты реализации «выбор из проектов-папок»:

1. **Плоский:** user выбирает N джобов из списка → pool их лайкнутых рилсов. Без схемы.
2. **Project как label:** добавить `Job.project_label: str | None` и тэгировать при upload. Schema-light.
3. **Полная модель Project:** новая таблица `projects` + FK `jobs.project_id`. Больше кода, но позволяет UI «папки».

Рекомендация: **вариант 2** (label) — минимальный shift, покрывает сценарий, не ломает текущий flat-view. Миграция тривиальная.

---

## 4. Модуль уникальных описаний per account

### 4.1 Что нужно знать про каждый аккаунт

Чтобы Gemini делал разный caption для `@accountA` vs `@accountB`, нам нужен **профиль аккаунта** (новая сущность `account_profile`):

- `publer_account_id` (PK mapping на Publer)
- `display_name` / handle
- `network` (instagram/youtube/...)
- `language` (ru/en/...)
- `audience` — короткое описание ЦА (фрилансеры / маркетологи / SMB)
- `tone` — стиль (агрессивный/дружелюбный/экспертный)
- `hashtags_default: list[str]` — базовые теги аккаунта
- `banned_words: list[str]` — что не писать
- `signature: str | None` — добавляется в конец (ссылка / CTA)
- `cta_style` — «подписка», «в био ссылка», «комменты», etc.
- `max_caption_length: int` — по network ограничение (IG 2200, YT 5000, TikTok 2200)

### 4.2 Caption generation workflow

На каждый (reel × account) вызов Flash Lite с системным промптом:
- in: hook/segments/target_audience рилса (из `ReelPlan`) + профиль аккаунта + оригинальный транскрипт (excerpt).
- out: `{caption: str, hashtags: list[str]}`.

Стоимость: N_reels × M_accounts Flash Lite вызовов. Для 20 рилсов × 3 аккаунта = 60 calls, ~копейки.

Кеш: первый раз посчитали → хранить в `scheduled_post_drafts` (новая таблица) до финального апрува.

### 4.3 Превью и редактирование

User должен видеть caption перед публикацией и иметь возможность править руками. UI-flow:
1. Выбрал pool рилсов + pool аккаунтов + расписание.
2. Backend генерит drafts (N×M caption'ов).
3. UI показывает grid: рилс × аккаунт → каждую ячейку можно edit.
4. Apply → bulk POST в Publer.

---

## 5. Паттерн расписания «единое время × разные даты»

### 5.1 Use case

User: «Хочу запланировать 5 лайкнутых рилсов. На @accountA — даты 28, 29, 30 апреля. На @accountB — 1, 3, 5 мая. Время публикации у всех 19:00 MSK».

### 5.2 Data model

`ScheduleTemplate` (новая):
- `time_of_day: time` — 19:00
- `timezone: str` — `"Europe/Moscow"`
- `dates: list[date]` — [2026-04-28, 2026-04-29, ...]
- `spacing_min_gap_hours: int = 0` — опциональный jitter между аккаунтами в один день

`ScheduleAssignment`:
- template_id
- reel_id
- account_id
- scheduled_at (computed: `combine(date, time_of_day) в tz`)
- caption (из модуля 4) + hashtags
- publer_job_id (после POST)
- publer_post_id (после complete)
- status: draft/queued/published/failed

### 5.3 UI flow для «единого времени»

Wizard 3 шага:
1. **Source:** выбрать лайкнутые рилсы (по проектам/датам/вручную).
2. **Destination:** выбрать аккаунты + дефолт caption-стратегию.
3. **Schedule:** единое время + список дат ИЛИ генератор «каждый день с D1 по D2» ИЛИ «по дням недели».

Publer принимает `accounts[].scheduled_at` → все наши assignments один bulk.

---

## 6. Secrets & config

- `PUBLER_API_KEY` — в `.env` backend'а. НЕ коммитить.
- `PUBLER_WORKSPACE_ID` — либо в `.env`, либо хранить per-user в UI settings (если workspace'ов несколько).
- Retry policy: max 3, exponential backoff. Rate-limit aware (sleep 120s при 429).

---

## 7. Гипотетический модульный breakdown (для обсуждения, НЕ implementation plan)

```
apps/backend/src/videomaker/services/publer/
├── client.py                # HTTPX async client + auth + rate limit
├── schemas.py               # Pydantic для request/response Publer
├── media_uploader.py        # upload file OR from-url + poll job_status
├── post_builder.py          # сборка bulk payload (networks/accounts/media)
├── caption_generator.py     # Gemini Flash Lite на ReelPlan + AccountProfile
├── scheduler_service.py     # главный фасад: create_campaign() / publish_now()
├── worker.py                # poll queue, delivers pending → Publer
└── models.py                # AccountProfile, ScheduleTemplate, ScheduleAssignment
```

Frontend:
```
apps/frontend/src/app/scheduler/
├── page.tsx                 # список campaigns + календарь
├── new/page.tsx             # wizard (source → destinations → schedule)
└── ...
apps/frontend/src/components/scheduler/
├── AccountProfilesEditor.tsx
├── ReelPicker.tsx           # лайкнутые, фильтры
├── CaptionPreviewGrid.tsx   # reel×account grid с edit
└── ScheduleTimeline.tsx     # визуализация по датам
```

---

## 8. Открытые вопросы (требуют ответа user'а)

1. **Publer ключ:** есть ли уже активный Business/Enterprise ключ или нужно купить тариф?
2. **Legacy scheduler (YouTube/IG OAuth):** что с ним? A) адаптировать под Publer, B) рядом, C) удалить. Подтверди.
3. **Проекты-папки:** устроит `Job.project_label` (вариант 2 в §3.3) или нужна полная Project-модель?
4. **Caption per account:** храним профиль аккаунта где? (новая таблица `account_profiles`, per workspace). Какие поля обязательные, какие опциональные?
5. **Время публикации:** фиксированное 1 timezone на user'а, или per-account timezone (IG US → ET, IG RU → MSK)?
6. **TikTok:** Publer API его НЕ поддерживает. Если TikTok нужен — нужен параллельный модуль через TikTok API / ручная выгрузка. Подтверди что TikTok НЕ в scope.
7. **Trial reels:** дефолт `MANUAL` (не публикуется пока user не подтвердит в IG) или `SS_PERFORMANCE` (автошара если зашёл)?
8. **Cover/thumbnail:** используем `cover_path` из `ReelPlan` (vision cover_selector уже выбирает) или отдельный UI-выбор на шедулер-шаге?
9. **Размер рилсов:** нам хватит 200 MB multipart upload или нужен URL-flow (и сразу public serving рилсов через signed URL в backend'е)?
10. **Workspace:** один на user'а или несколько (нужен UI-селектор workspace'а)?

---

## 9. Что я пока НЕ делаю

- НЕ пишу код
- НЕ создаю таблицы / миграции
- НЕ трогаю legacy scheduler модули
- НЕ коммичу ничего

Жду ответов на §8 → тогда формирую implementation plan через `writing-plans` skill.

---

## Sources

- [Publer API Overview](https://publer.com/docs)
- [Publer API Quickstart](https://publer.com/docs/getting-started/quickstart)
- [Publer API Authentication](https://publer.com/docs/getting-started/authentication)
- [Publer Creating Posts](https://publer.com/docs/posting/create-posts)
- [Publer Media Handling](https://publer.com/docs/posting/create-posts/media-handling)
- [Publer Video Posts](https://publer.com/docs/posting/create-posts/content-types/video-posts)
- [Publer Reels/Shorts/Stories](https://publer.com/docs/posting/create-posts/content-types/platform-specific-formats/reels-shorts-and-stories)
- [Publer API Reference Intro](https://publer.com/docs/api-reference/introduction)
