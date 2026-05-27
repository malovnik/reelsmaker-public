# Gap-3 — Capability Alignment (текущее ↔ целевое видение)

> Phase 4, роль: Product Capability Alignment Analyst. Линза — соответствие бэкенд-возможностей продуктовым решениям (00-ROADMAP «Продуктовые решения») и цели 2 режимов («Пошаговый / Эксперт-студия»).
> Вход: [BACKEND-MAP](../phase2-backend-map/BACKEND-MAP.md) (+ section-1/2/3), [FRONTEND-EXPOSURE](../phase3-frontend-exposure/FRONTEND-EXPOSURE.md) (+ A/B/C).
> Каждый разрыв: `GAP-CA-N` · текущее → целевое · приоритет (P0 релиз-блокер / P1 важно / P2 nice) · сложность S/M/L · зависимости от фаз.

Шкала сложности: **S** = локальная правка одного места; **M** = бэк+фронт, 1 поддомен; **L** = многокомпонентная фича или ML/инфра-риск.

---

## 1. Vision / face-tracking opt-in revival

**Продуктовое решение #2:** opt-in revival, не блокируя релиз; чинить hang (таймаут/фолбэк), честный опциональный контрол, дефолт безопасный (center-crop).

**Что есть.** Вся vision-инфра реальна и подключена (Moondream VQA/caption/detect, mediapipe blaze_face, face-tracked zoom/base-crop, visual_validator, cover_selector). Всё за `VisionRuntimeSettings.enabled=False` + per-feature тоглами. `face_tracker_enabled` default False → статичный center-crop. Причина OFF: **mediapipe hang на Apple Silicon** (section-2.7). Эндпоинты уже есть: `GET/PUT /settings/vision`, `GET/PUT/DELETE /settings/profiles/{profile}`, `GET /jobs/{id}/profile/suggestion`, `PATCH /jobs/{id}/profile`. `/settings/vision` имеет lazy health-probe в ответе (`VisionSettingsResponse.health`).

| ID | Разрыв | Текущее | Целевое | Приоритет | Сложн. | Зависимость |
|----|--------|---------|---------|-----------|--------|-------------|
| GAP-CA-01 | mediapipe hang не локализован | face_tracker гасится глобально из-за зависона на Apple Silicon | Воспроизвести и обернуть детект в hard-таймаут (process/thread + `asyncio.wait_for`); при превышении → лог + фолбэк на center-crop, job не падает | **P1** | M | — |
| GAP-CA-02 | Нет честного «безопасного» дефолта при включённом vision | enabled=False тушит всё; включив, юзер рискует hang | center-crop остаётся дефолтом кадрирования даже при vision.enabled=True; face-track — отдельный явный opt-in поверх | **P1** | S | GAP-CA-01 |
| GAP-CA-03 | `/settings/vision` health не выведен в UR честно | поле health есть в ответе, UI не показывает «модель не загружена / медленно» | Бейдж статуса vision в Эксперт-студии (loaded/слишком медленно/выкл), предупреждение про CPU-нагрузку | **P1** | S | Phase 6 (фронт) |
| GAP-CA-04 | `profile/suggestion` без UI-контрола | `GET /jobs/{id}/profile/suggestion` (профиль по face coverage) не вызывается | В Пошаговом — авто-подсказка профиля при загрузке; в Эксперте — кнопка «подобрать профиль» | P2 | S | Phase 6 |
| GAP-CA-05 | Dormant vision-фичи реанимировать НЕ нужно | screencast/deictic zoom, mouth-sound = compute-then-discard (toggle ВКЛ, выход выброшен); B-roll/orphan ~972 LOC мёртвые | Решение #4: режем/прячем, НЕ реанимируем. Здесь только фиксируем границу revival — он касается ТОЛЬКО face-track + базового vision-кадрирования | **P0** (граница скоупа) | — | gap-1 (orphan-削除) |

**Технически нужно для revival:** (1) таймаут-обёртка вокруг mediapipe-детекта с фолбэком (GAP-CA-01) — единственная настоящая инженерная работа, остальное — конфиг и UI. (2) Эндпоинты уже полностью существуют — новых не нужно. (3) Честный контрол = два уровня тогла: `vision.enabled` (включает VQA/validator/cover) и отдельный `face_tracker_enabled` (умное кадрирование). **Сложность revival в целом: M**, риск сконцентрирован в GAP-CA-01 (воспроизводимость hang на конкретном железе).

---

## 2. Publer — единый путь публикации

**Продуктовое решение #3:** Publer единый путь, удалить legacy `/schedule`; связать проекты↔джобы (слать project_id, экран папки).

**Что есть.** Полноценный Publer-стек: `/scheduler/*` (18 ручек), реальный `PublerWorker` в lifespan, CampaignWizard (единственный настоящий 4-шаговый мастер). Параллельно — **второй механизм**: `ScheduleButton` на каждом ReelCard → прямой `POST /api/v1/schedule` + страница `/schedule` (legacy, YouTube/Instagram Graph API). Они не пересекаются (обрыв C#5). `ManualPublishButton` реализован, но нигде не отрендерен (обрыв C#3). `POST /scheduler/assignments/{id}/cancel` — partial stub (флипает локальный статус, не ретрактит Publer-пост).

| ID | Разрыв | Текущее | Целевое | Приоритет | Сложн. | Зависимость |
|----|--------|---------|---------|-----------|--------|-------------|
| GAP-CA-06 | Дублирующий legacy `/schedule` | `ScheduleButton` + `/schedule` страница + прямой `POST /api/v1/schedule` минуют Publer | **Удалить** legacy путь: компонент `ScheduleButton`, роут `/schedule`/`ScheduleClient`, клиентский вызов. Если backend-роут `/schedule` ещё жив (oauth-таблицы дропнуты Publer-миграцией) — удалить и его | **P0** | M | — |
| GAP-CA-07 | `ManualPublishButton` мёртвый | реализован (`manualPublishOne` → `POST /scheduler/manual/publish-one`), не отрендерен | Отрендерить на `ReelCard`/`ClipDetail` как «Опубликовать сейчас» — это и есть замена legacy «быстрой публикации» внутри Publer | **P0** | S | GAP-CA-06 |
| GAP-CA-08 | Проекты ↔ джобы оторваны | `UploadWizard` не шлёт `project_id`; `assignJobToProject` (`PATCH /jobs/{id}/project`) не вызывается ниоткуда | Слать `project_id` опционально из визарда (поле «проект/папка»); кнопка «переместить в проект» в JobDetail | **P0** | M | — |
| GAP-CA-09 | Нет экрана папки/результатов | `POST /jobs/{id}/saved` копирует в `saved/<folder>/`, но UI этой папки нет (обрыв C#8) | Экран проекта (`GET /projects/{id}` уже отдаёт jobs[]) = «папка»; либо отдельный экран saved-рилсов. Связать с liked-артефактами (`GET /jobs/artifacts/liked?project_id`) | **P1** | M | GAP-CA-08 |
| GAP-CA-10 | `assignments/cancel` не ретрактит пост | partial stub — локальный flip, Publer-пост остаётся | Вызвать Publer `DELETE /posts/{id}` для уже-scheduled; для queued — снять с очереди воркера. Иначе UI «отменено» врёт | **P1** | M | — |
| GAP-CA-11 | Viral-score клиентский | `viralScore.ts` считает на клиенте из meta, не из per-reel scoring пайплайна | Отдавать score из пайплайна (он реально считается в bottom_up); фронт читает из артефакта, не пересчитывает | P2 | M | — |

**Консолидация:** единый путь = `/scheduler/*` (кампании) + `manual/publish-one` (быстрая публикация одного). Удаляем `/schedule`. **Связка проект↔джоб** — обязательна для решения, т.к. ReelPicker в кампании уже фильтрует по `project_id`, но фильтр всегда пустой (джобы не привязываются). Это делает «папки» рабочими e2e.

---

## 3. Два режима интерфейса — покрытие 81 ручкой

**Цель Phase 9.** Пошаговый = цепочка «Создай проект → видео» для новичка. Эксперт-студия = все ручки + подсказка у каждого контрола.

### 3.1 Пошаговый режим — линейная цепочка (что из ручек ложится)

Цель: новичок доходит до рилсов без выбора «фикций». Цепочка опирается на уже связный auto-флоу (FRONTEND-EXPOSURE вердикт):

1. **Создать проект** (крупная кнопка) → `POST /projects` → стать активной папкой.
2. **Загрузить видео** → `POST /jobs` (multipart) **с `project_id`** (GAP-CA-08). Минимум полей: файл, вид рилсов (aspect), кол-во (auto/custom).
3. **Профиль** → авто через `GET /jobs/{id}/profile/suggestion` (GAP-CA-04), без ручного выбора.
4. **Авто-конфиг** → `POST /jobs/{id}/auto-analyze` → «Принять» → `PATCH /jobs/{id}/auto-config`. (Скрыть `DELETE auto-config`/«в ручной» — это Эксперт.)
5. **Прогресс** → SSE `GET /jobs/{id}/stream` + кнопка **Отмена** (`DELETE /jobs/{id}` purge=soft или cancel-механизм) — GAP-CA-14.
6. **Просмотр/разметка** → `GET /jobs/{id}/artifacts`, like/dislike, Tinder.
7. **Публикация** → `manual/publish-one` (быстро) или CampaignWizard (расписание).
8. **Папка** → экран проекта (GAP-CA-09).

| ID | Разрыв | Текущее | Целевое | Приоритет | Сложн. | Зависимость |
|----|--------|---------|---------|-----------|--------|-------------|
| GAP-CA-12 | Пошагового режима по сути нет | UploadWizard — псевдо-пошаговый (один скролл), нет принудительной последовательности, нет старта от «создай проект» | Настоящий wizard next/back (как CampaignWizard), цепочка выше, скрытие всех Эксперт-полей | **P0** (цель Phase 9) | L | gap-2 (PRD), Phase 9 |
| GAP-CA-13 | Пошаговый не должен показывать фикции | визард листает chaptered/provider-селекты/tier-тоглы | В Пошаговом — только honest-набор: aspect, count, субтитр-пресет, post-prod-пресет. Никаких tier/provider/chaptered | **P0** | M | gap-1 (honesty), п.4 |
| GAP-CA-14 | Нет кнопки отмены (обрыв C#7) | бэк cancel реально работает (1b-fix), `JobStatus.cancelled` обрабатывается в SSE, кнопки нет | Кнопка «Отменить обработку» в прогрессе обоих режимов | **P1** | S | — |

### 3.2 Эксперт-студия — все ручки + подсказки

Цель: подсказка напротив 100% контролов. Покрывает ВСЕ реальные ручки. Уже почти всё выведено (`/settings/*` 8 экранов, ~25 групп в performance). Задача — не добавить, а **очистить от фикций** и **дорастить tooltip’ы**.

Раскладка 81 ручки (укрупнённо):
- **Пайплайн-параметры** (Эксперт): `GET/PUT /settings/performance` (narrative_mode вкл. рабочие map_reduce/viral_2026, pacing, multi-arc, coherence, ensemble, J/L cuts, cut-snap, filler — все реальные тоглы при OFF-дефолте).
- **Vision** (Эксперт): `GET/PUT /settings/vision`, `/settings/profiles/*` (GAP-CA-01..03).
- **Субтитры/пресеты/пост-прод** (оба режима как пресеты): `/settings/subtitle_presets/*`, `/post_production/*`.
- **Промпты** (Эксперт): `/settings/prompts/*` (12 промптов).
- **Модели** (Эксперт, ПОСЛЕ honesty-фикса): `GET /settings/models`.
- **Шедулер/публикация** (оба): `/scheduler/*`.
- **Прокси-кэш** (Эксперт, сейчас БЕЗ UI): `GET /proxies`, `DELETE /proxies/cleanup`, `DELETE /proxies/{sha256}`.
- **Шрифты** (Эксперт): `POST /settings/fonts/refresh`.

| ID | Разрыв | Текущее | Целевое | Приоритет | Сложн. | Зависимость |
|----|--------|---------|---------|-----------|--------|-------------|
| GAP-CA-15 | proxies-роутер без UI | 3 ручки прокси-кэша не покрыты клиентом | Экран «Кэш прокси» в Эксперте (список/очистка) | P2 | M | Phase 6 |
| GAP-CA-16 | Нет tooltip-системы | подсказок у контролов нет | Tooltip напротив 100% контролов Эксперта (цель Phase 9) | **P1** | M | Phase 9 |
| GAP-CA-17 | `DELETE /jobs/{id}/auto-config` без клиента | half Automatic-Mode флоу без клиента (FRONTEND #7) | «Перейти в ручной» в Эксперте вызывает clear auto-config | P2 | S | Phase 6 |

---

## 4. Честность UI — разведение tier’ов и устранение фикций

**Продуктовое решение #1:** разведение tier’ов на реальные модели где возможно; где невозможно — честно убрать/пометить.

**Факты (section-2.2).** `tier_resolver.py` принудительно сводит **все три tier’а (pro/flash/flash_lite) к Flash-Lite модели** (`gemini-2.5-flash-lite` / `gemini-3.1-flash-lite-preview`). balanced/quality профили удалены, cold-cache коэрсит в `fast` (all-Lite). Это сделано осознанно для cost control. `story_doctor`/`canvas_builder`/`variants` просят `pro`, получают Lite. Zhipu: flat `pro/flash/flash_lite → glm-5.1`. anthropic/openai зарегистрированы и реализованы, но **нет call-site в narrative**. `chaptered` author-marked broken. Export не перекодирует.

### Оценка реалистичности разведения tier’ов

**Реалистично — да, технически тривиально, но это продуктово-стоимостное решение, не инженерное.** Gemini API предоставляет реальные tier-модели (Flash, Pro). `build_llm_for_tier` уже принимает `tier` и резолвит модель — достаточно вернуть в `tier_resolver` реальную карту `pro→gemini-pro`, `flash→gemini-flash`, `flash_lite→flash-lite` и убрать принудительный коэрс в `fast`. Архитектура (registry, rate_limiter, context cache) это уже поддерживает.

**Препятствия — стоимость и латентность, не код:**
- Pro-инференс на `story_doctor` + `canvas_builder` + `variants` × N рилсов = заметный рост стоимости/времени каждого прогона. Коэрс в Lite введён именно для cost control (зафиксировано в коде как осознанный constraint).
- Это противоречит решению пользователя «LLM-стек = только Gemini» только в части моделей — внутри Gemini выбор Flash/Pro допустим.

**Рекомендация (нужно решение пользователя):**

| ID | Разрыв | Текущее | Целевое (вариант) | Приоритет | Сложн. | Зависимость |
|----|--------|---------|-------------------|-----------|--------|-------------|
| GAP-CA-18 | tier-тоггл врёт | pro/flash/lite → всё Flash-Lite | **Вариант A (honest-expose):** развести на реальные Gemini Flash/Pro, tier-тоггл работает, дефолт Lite (cost). **Вариант B (honest-remove):** убрать tier-тоггл совсем, честно «весь анализ на Flash-Lite». A предпочтителен (соответствует #1 «реально рабочее где возможно»), но требует подтверждения по бюджету | **P0** (фикция-блокер) | A=M / B=S | решение юзера |
| GAP-CA-19 | provider-селекты врут | UploadWizard/ModelsPage листают anthropic/openai/deepgram как pipeline-LLM | anthropic/openai — нет call-site → убрать из pipeline-LLM селекта. Оставить только gemini + zhipu (реально подключены). deepgram оставить как транскрайбер (он реален), не как LLM | **P0** | S | — |
| GAP-CA-20 | chaptered broken но выбираем | radio-опция narrative_mode, author-marked broken | Убрать `chaptered` из селекта (оставить bottom_up/map_reduce/viral_2026 — все рабочие) | **P0** | S | — |
| GAP-CA-21 | Export-диалог врёт | TikTok/Reels/Shorts/X пресеты битрейт+LUFS, бэк не перекодирует | Решение #1 «export-transcode → реально рабочее»: реализовать настоящий ffmpeg-transcode по пресету (бэк уже умеет loudnorm/HEVC — переиспользовать render-путь). На Linux/Railway: `videotoolbox→libx264` fallback уже есть | **P1** | M | — |
| GAP-CA-22 | `updateArtifactLike` контракт-расхождение | клиент шлёт tri-state `none\|like\|dislike`, контракт `ArtifactLikeUpdate{liked: bool}` → риск 422 | Сверить Pydantic-модель; привести клиент и контракт к одному типу | **P1** | S | — |

---

## 5. Онбординг / пошаговость, которой нет

**Факт (FRONTEND-EXPOSURE вердикт).** Онбординга нет вообще (только инлайн-подсказка про `GEMINI_API_KEY`). Нет welcome/empty-state, нет «создай первый проект → загрузи», нет туров. Единственный настоящий мастер — CampaignWizard. Главный поток — псевдо-пошаговый.

| ID | Разрыв | Текущее | Целевое | Приоритет | Сложн. | Зависимость |
|----|--------|---------|---------|-----------|--------|-------------|
| GAP-CA-23 | Нет first-run онбординга | пусто; нет проверки готовности окружения | Welcome-экран: проверка `GET /health` (llm_providers, ffmpeg, transcribers), гайд «задай GEMINI_API_KEY», CTA «Создать первый проект» | **P1** | M | Phase 9 |
| GAP-CA-24 | Нет empty-state с действием | разрозненные экраны без «что делать» | Empty-state на `/projects` и `/` → крупная кнопка старта Пошагового режима | **P1** | S | GAP-CA-12 |
| GAP-CA-25 | Переключатель режимов отсутствует | один UI, всё намешано | Глобальный тоггл «Пошаговый / Эксперт-студия» в shell; персист выбора | **P0** (цель Phase 9) | M | Phase 9, gap-2 |
| GAP-CA-26 | `/health` capability-probe не используется в UI | отдаёт ffmpeg/providers/transcribers/videotoolbox | Использовать в онбординге и в Эксперте (бейдж «ffmpeg ok / videotoolbox / vision») | P2 | S | Phase 6 |

---

## Итог

### Что критично для 2 режимов (P0)
1. **Очистка фикций** (GAP-CA-18..20): tier, provider-селекты, chaptered. Без этого ни один режим не может быть честным — Пошаговый не должен их показывать, Эксперт обязан показывать только реальное.
2. **Связка проект↔джоб** (GAP-CA-08): фундамент цепочки Пошагового («Создай проект → …») и рабочих папок/фильтров шедулера.
3. **Единый Publer-путь** (GAP-CA-06/07): удалить legacy `/schedule`, оживить `ManualPublishButton`. Без этого «публикация» в обоих режимах двусмысленна.
4. **Настоящий Пошаговый wizard + переключатель режимов** (GAP-CA-12/25): сама суть Phase 9.
5. **Граница vision-revival** (GAP-CA-05): зафиксировать, что реанимируем только face-track + базовый vision; orphan/dormant режем (не путать с revival).

### Реалистичность разведения tier’ов
**Технически реалистично и недорого в коде** — `build_llm_for_tier`/registry уже поддерживают выбор модели, нужно лишь вернуть реальную карту в `tier_resolver` и снять коэрс в `fast`. **Барьер не инженерный, а стоимостной**: Pro-инференс на нескольких стадиях × N рилсов кратно поднимает цену/время прогона (ради чего коэрс и введён). Внутри Gemini это не нарушает «только Gemini». **Нужно продуктовое решение пользователя**: Вариант A (развести, рабочий тоггл, дефолт Lite) — соответствует решению #1 и предпочтителен; Вариант B (честно убрать тоггл, «весь анализ на Lite») — дешевле и быстрее внедрить. До решения — это единственный пункт п.4, который нельзя закрыть автономно.

### Зависимости между gap-файлами Phase 4
- **gap-1** (orphan/honesty removal): GAP-CA-05, -13, -18..20 опираются на удаление мёртвого кода и фикций.
- **gap-2** (PRD-expose): GAP-CA-12/25 (режимы, wizard) — туда же.
- **Phase 6** (вывод бэка): GAP-CA-03/04/15/17/26 — чисто фронт-экспозиция существующих ручек.
- **Phase 9** (редизайн, 2 режима): GAP-CA-12/16/23/25 — финальная сборка режимов.
