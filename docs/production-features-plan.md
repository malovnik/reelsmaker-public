# Production Features Plan — 2026-04-17

Четыре связанные фичи. **Production grade без костылей.** Не пропускать верификацию, не объединять коммиты, не упрощать задачи.

## Мультироли (исполняются попеременно по контексту микрозадачи)

- **Senior Python Backend Architect.** Professional: FastAPI, pydantic v2, ffmpeg pipelines, asyncio, PEP 695. Soul: докапывается до root cause, отказывается «замазать» симптом.
- **Computer Vision Engineer.** Professional: mediapipe face detector, keyframe smoothing (EMA + dead-zone), crop math (scale_factor, anchor clamping). Soul: видит кадр глазами зрителя, не кодера, чувствует когда «лицо уехало».
- **Product Designer.** Professional: shadcn/ui v4 (base-ui-react), Tailwind 4, OKLCH палитра, mobile-first верстка, `next/font/local` для кириллического Inter. Soul: эстетика без клише, строгость без скуки.
- **QA / Test Engineer.** Professional: pytest-asyncio, hypothesis, coverage, integration smoke. Soul: ломает код раньше, чем пользователь заметит.
- **Release Engineer.** Professional: atomic git commits, push, CI-gates, changelog. Soul: каждая фича — одна атомарная история в git log.

Каждую микрозадачу выполняй в контексте 1-2 ролей, не смешивай все сразу.

---

## Стоп-фраза

`FOUR-FEATURE PRODUCTION ROLLOUT COMPLETE`

Выводить **ровно** эту строку только после:
- Все 4 фичи в main с отдельными коммитами.
- Все тесты backend (`uv run pytest`) pass.
- Frontend `pnpm build` без ошибок.
- Serena memories обновлены для каждой фичи.
- `docs/production-features-plan.md` помечен как «исполнено» (раздел Status).

---

## Шаг 1 — Длина рилсов 31-89с

**Зачем:** платформенный формат TikTok/Reels/Shorts. Сейчас `REEL_MIN_DURATION_SEC=10.0` → часто <31s.

### 1.1 Анализ текущего поведения
1.1.1 Прочитать `test_reels_composer.py` — какие кейсы проверяют duration (значения 10, 90).
1.1.2 Пройтись по `_arc_group_to_candidate`, `_candidates_from_singles` — где отбрасывается <min.
1.1.3 Зафиксировать что `_split_arc_into_shorts` только бьёт по overflow, не проверяет min.

### 1.2 Константы
1.2.1 `services/reels_composer.py:53-54`: `REEL_MIN_DURATION_SEC = 31.0`, `REEL_MAX_DURATION_SEC = 89.0`.
1.2.2 `config/export_presets.yaml:68-69`: `min_reel_duration_sec: 31.0`, `max_reel_duration_sec: 89.0`.
1.2.3 Проверить `renderer.py` и `RenderSettings` — использует ли эти границы.

### 1.3 Merge коротких групп arc
1.3.1 Новая функция `_merge_short_groups(groups) -> list[list[StorySegment]]` — если группа <REEL_MIN, присоединять к следующей, при sum<=REEL_MAX. Пост-обработка last.
1.3.2 Вызов в `_candidates_from_base_arc` и `_candidates_from_package_of_shorts` сразу после `_split_arc_into_shorts`.
1.3.3 Инвариант: merged груп ни одна не <REEL_MIN (или <REEL_MIN и dropped — но минимум одна группа сохраняется).

### 1.4 Расширение singles
1.4.1 Новая функция `_extend_evidence_to_min(start, end, source_duration_sec, min_target) -> (start, end)` — симметричное расширение с клампом [0, source_duration].
1.4.2 `_candidates_from_singles(ranked, source_duration_sec)` — принимает длительность, расширяет до min, **не** отбрасывает.
1.4.3 Передать `source_duration_sec` из `compose_reels` уже есть как параметр — прокинуть в singles.

### 1.5 Тесты + commit
1.5.1 Обновить существующие (duration=30 → 35 и т.п., overflow 90 → 89).
1.5.2 Новые кейсы: merge двух коротких, не-merge если сумма > max, extend single симметрично, extend single на границе source.
1.5.3 `uv run pytest` — 0 failures.
1.5.4 `uv run ruff check`, `uv run ruff format --check`.
1.5.5 Commit: `fix(reels): enforce 31-89s reel duration with merge+extend fallback`. Push.

---

## Шаг 2 — Face-aware первичный crop 16:9→9:16

**Зачем:** сейчас `fill_filter: scale=-2:1920,crop=1080:1920:(iw-1080)/2:0` — жёсткий центр. Если спикер снят по правилу третей → лицо уезжает. Нужно учитывать face anchor.

### 2.1 Исследование
2.1.1 `filter_graph_builder.build_filter_graph` Stage A — точка вставки base crop.
2.1.2 `project_graph.py` — модель `ProjectGraph`, поля `export_preset`, `zoom_plan`. Нужно новое поле `base_crop_plan`.
2.1.3 `renderer.py` rendering pipeline — где вызывается `track_faces`, когда.

### 2.2 Архитектура
2.2.1 Решение: вынести crop из yaml. `fill_filter` становится чистым `scale` (ресайз под input). Crop переезжает в Stage A как отдельная ffmpeg chain `crop=CW:CH:x(t):y(t)`.
2.2.2 Новый dataclass `BaseCropPlan` в project_graph (аналог ZoomPlanSpec): `crop_width`, `crop_height`, per-cut `keyframes: tuple[AnchorKeyframe, ...]`.
2.2.3 Fallback: когда face не найден → static center (x=0.5 source frame).
2.2.4 Rule of thirds для X тоже применить опционально (как для Y): допустим, если спикер намеренно у левой трети — не «выправлять» его в центр, но и не отрезать. В первом проходе: anchor_x напрямую из `face.cx`, EMA + clamp.

### 2.3 Модель + zoom_planner reuse
2.3.1 Добавить `BaseCropPlan` в `project_graph.py`.
2.3.2 Новая функция `build_base_crop_plan(cuts, face_track, target_aspect, source_w, source_h) -> BaseCropPlan` в `zoom_planner.py` (или отдельный модуль `base_crop_planner.py` если zoom_planner разрастется).
2.3.3 Расчёт crop_width/crop_height для 9:16 из source 16:9: `crop_h = source_h`, `crop_w = round(source_h * 9/16)`. Для 1080p source: crop_w=608 (чётное).
2.3.4 Keyframes: per-cut window face tracking, EMA smoothing, dead-zone — переиспользовать логику из `_build_anchor_keyframes`.

### 2.4 filter_graph_builder Stage A update
2.4.1 Новая функция `_build_base_crop_expr(plan, cut_idx) -> str` — аналог `_zoom_command_to_crop_expr` но static `crop_w:crop_h`, dynamic `x(t):y(t)`.
2.4.2 per_segment_chain теперь: `trim,setpts,base_crop_expr,scale_to_target,fps,setsar`. Плюс всё cut-specific, поэтому chain-строку собираем в цикле, не константой.
2.4.3 Обратная совместимость: если `base_crop_plan is None` → старое поведение (pure preset.scale_filter).

### 2.5 export_presets.yaml
2.5.1 `fill_filter` для reels_9_16: только scale под высоту (`scale=-2:1920` без crop) — для случая когда base_crop_plan none.
2.5.2 `fit_filter` не трогаем (letterbox).
2.5.3 Подумать: теперь crop 9:16 всегда динамический, fill_filter нужен только как fallback — оставить.

### 2.6 Renderer integration
2.6.1 `renderer.py`: всегда вызывать `track_faces` перед рендером (не только когда zoom_enabled). Cache срабатывает — повторные рендеры того же source не переделывают.
2.6.2 Вычислять `base_crop_plan` для каждого reel через `build_base_crop_plan`.
2.6.3 Передать `base_crop_plan` в `ProjectGraph`.
2.6.4 `pipeline.py:613+` логика «1 раз track_faces» — проверить что работает когда zoom_enabled=False (нужна face keyframes для base crop).

### 2.7 Тесты + smoke
2.7.1 Unit для `build_base_crop_plan` (static center fallback, face-aware anchors, clamp по source границам).
2.7.2 Unit для `_build_base_crop_expr` (1 keyframe → static, N keyframes → piecewise).
2.7.3 Integration: рендер 1 рилса с моком face_track, проверить filter_complex содержит `crop=608:1080:...`.
2.7.4 Manual smoke: запустить на реальном видео где спикер слева от центра — проверить визуально что лицо в финальном кадре по центру.
2.7.5 Commit: `feat(render): face-aware primary 9:16 crop via dynamic anchor keyframes`. Push.

---

## Шаг 3 — UI slider для кол-ва рилсов

**Зачем:** `pending/reel-count-predictability` — пользователь должен контролировать сколько рилсов он хочет получить (5-30), или оставить «авто» (эмпирика OpusClip).

### 3.1 Backend contract
3.1.1 `reels_composer.compose_reels` уже принимает target через `_compute_target_range` — добавить `user_target_count: int | None` параметр, override.
3.1.2 Если override: `target_count = user_target`, `min_count = max(1, user_target - 3)`, `max_count = min(30, user_target + 3)`.
3.1.3 `services/pipeline.py`: прокинуть `user_reel_count` из job / project settings.
3.1.4 Модель `Job` / `Project` — поле `target_reel_count: int | None`.

### 3.2 API endpoint
3.2.1 POST `/projects/{id}/analyze` принимает `target_reel_count: int | None` в body.
3.2.2 Валидация: 5-30 или null.
3.2.3 Передача в pipeline.
3.2.4 SSE stats: `user_requested_reel_count` в `analysis.stats`.

### 3.3 Frontend UI
3.3.1 `UploadDropzone` или новая секция — слайдер 5-30 shadcn `Slider` + чекбокс «Авто».
3.3.2 При `Авто` — передаём null.
3.3.3 Обновить API-клиент в `apps/frontend/src/lib/api.ts`.
3.3.4 Состояние: React form / Zod validation.

### 3.4 Тесты
3.4.1 Backend: test_compose_reels override range.
3.4.2 Backend: test_analyze endpoint validation.
3.4.3 Frontend: smoke через `pnpm dev` — открыть upload, выбрать 15 рилсов, проверить payload.
3.4.4 Commit: `feat(ui): target reel count slider (5-30 или авто)`. Push.

---

## Шаг 4 — Frontend redesign

**Зачем:** `pending/frontend-redesign` — текущий без дизайн-системы. Перенос Hybrid Resonant Brutal из videoeditor.

### 4.1 Инвентарь
4.1.1 `apps/frontend/src/app/**/*.tsx` — список страниц.
4.1.2 `apps/frontend/src/components/**/*.tsx` — список компонентов.
4.1.3 Список UI-примитивов которые нужны (button/input/dialog/card/slider/…).
4.1.4 `apps/videoeditor/frontend/src/components/ui/` — скопировать shadcn компоненты.

### 4.2 Tokens + fonts
4.2.1 `globals.css` с OKLCH палитрой (light 0.99 + brutal black 0.09 accents).
4.2.2 Inter Variable cyrillic через `next/font/local` — WOFF2 файл из videoeditor или fresh download.
4.2.3 `tailwind.config` / Tailwind 4 `@theme` директива с токенами.
4.2.4 Dark theme? — MVP без. Light-first.

### 4.3 shadcn/ui v4 установка
4.3.1 `pnpm add @base-ui-components/react class-variance-authority tailwind-merge lucide-react`.
4.3.2 Настройка `components.json`.
4.3.3 Перенести button, input, dialog, card, slider, label, form, progress, table, tabs, dropdown (11 примитивов).

### 4.4 Страницы
4.4.1 `/` — HomeClient: Upload секция + job list. Карточка загрузки по центру, mobile stack.
4.4.2 `/jobs/[id]` — JobDetailClient: stages progress, reels list, preview thumbnails.
4.4.3 `/settings/prompts` — редактор 12 промптов (tabs по stage).
4.4.4 `/settings/models` — model preferences (tier selector).

### 4.5 Mobile adaptive
4.5.1 Проверить viewport 375 / 768 / 1024 / 1440 для каждой страницы.
4.5.2 Touch-targets >= 44px.

### 4.6 Anti-slop audit
4.6.1 copy-slop: тексты UI — без клише, без эмодзи (BIBLE.md).
4.6.2 visual-slop: без Tailwind utility-spam, без иконок «для декора».

### 4.7 Финал
4.7.1 `pnpm typecheck` — 0 errors.
4.7.2 `pnpm build` — success.
4.7.3 Commit: `feat(frontend): full redesign under Hybrid Resonant Brutal system`. Push.
4.7.4 Обновить Serena `pending/frontend-redesign` → mark done.

---

## Финальный этап

- `/Users/malovnik/Documents/Dev/videomaker/docs/production-features-plan.md` — пометить Status: DONE.
- Serena memory для каждой из 4 фич.
- `last-session-summary.md` — автоген при PreCompact, не трогать.
- Вывести стоп-фразу.

---

## Status

- [x] Шаг 1 — Reel 31-89с (commit c40c598)
- [x] Шаг 2 — Face-aware crop
- [x] Шаг 3 — UI slider
- [ ] Шаг 4 — Frontend redesign
- [ ] Serena memories x4
