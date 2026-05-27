# 02 — Инвентаризация настроек (/settings/*)

> **Артефакт REFACTR-02.** Зона охвата: 8 страниц `/settings/*` + backend-зеркала (`models/runtime_settings.py`, `models/vision_settings.py`, `subtitle_store`, `prompt_store`, `post_production_store`).
> **Дата:** 2026-04-24.
> **Автор:** R-AUDITOR + R-UX-WRITER (консультативно).
> **Назначение:** дать Этапу 08 (REFACTR-51…57) полный список настроек с file:line и предварительную IA-группировку.

---

## 1. Состав 8 страниц

| # | URL | Главный клиент | LoC клиента | Вспомогательные компоненты | Источник данных |
|---|-----|----------------|------------:|----------------------------|------------------|
| 1 | `/settings/brand` | `components/settings/BrandKitClient.tsx` | 219 | — | **localStorage** (`videomaker.brand_kit`), НЕ backend |
| 2 | `/settings/models` | `components/MoondreamSettings.tsx` + inline `Block` в `app/settings/models/page.tsx` | 253 | `ProfileSelector.tsx` (235) | `GET /api/v1/models`, `GET /api/v1/settings/vision` (Moondream) |
| 3 | `/settings/connections` | `components/ConnectionsSettings.tsx` | 167 | — | `GET /api/v1/connections/youtube/status`, OAuth flow |
| 4 | `/settings/prompts` | `components/PromptsEditorClient.tsx` | 159 | — | `GET /api/v1/settings/prompts`, `PUT /api/v1/settings/prompts/{key}` |
| 5 | `/settings/profiles` | `components/VisionProfilesSettingsClient.tsx` | 498 | — | `GET/PUT /api/v1/settings/profiles` (4 маски) |
| 6 | `/settings/performance` | `components/PerformanceSettingsClient.tsx` | 309 | **29 файлов** в `performance-groups/` | `GET/PUT /api/v1/settings/performance` |
| 7 | `/settings/post-production` | `components/PostProductionSettingsClient.tsx` | 429 | **9 файлов** в `settings/post-production/` | `GET/PUT /api/v1/post-production/presets` |
| 8 | `/settings/subtitles` | `components/SubtitleSettingsClient.tsx` | 458 | `SubtitleStyleEditor.tsx` (653), `SubtitlePreview.tsx` (~600) | `GET/PUT /api/v1/settings/subtitles`, `GET /api/v1/settings/fonts` |

**Всего client LoC:** 219+253+167+159+498+309+429+458+653+600 ≈ **3745 строк** только на главные клиенты, без учёта 29 perf-групп и 9 post-prod секций.

---

## 2. Полный список полей по страницам

### 2.1. `/settings/brand` (4 поля, **localStorage only**)

Определение в `BrandKitClient.tsx:6-11, 23-42`:

| Поле | Тип | Default | Хранение | Использование |
|------|-----|---------|----------|---------------|
| `primary_color` | color (hex) | `#b79b5b` | localStorage `videomaker.brand_kit` | **Задумано** для субтитров и post-prod — по факту нигде не читается |
| `secondary_color` | color (hex) | `#2f2b26` | localStorage | — |
| `text_color` | color (hex) | `#f5f1ea` | localStorage | — |
| `font_family` | text | `"Inter"` | localStorage | — |
| `logo_data_url` | file (base64, max 1.5 MB) | null | localStorage | — |

**🔴 Проблема:** страница существует, но поля не передаются ни в render, ни в subtitle_styles. Декларация владельца в `app/settings/brand/page.tsx:11-14`: «потом их можно будет подключить». **Feature stub** — либо реализовать на Этапе 08 (REFACTR-55), либо удалить.

### 2.2. `/settings/models` (read-only + Moondream 2 поля)

**Read-only (`app/settings/models/page.tsx`):**

| Поле | Источник | Назначение |
|------|----------|-----------|
| `defaults.gemini` | `GET /api/v1/models` | Модель Gemini по умолчанию |
| `defaults.anthropic` | там же | Claude |
| `defaults.openai` | там же | OpenAI |
| `defaults.zhipu` | там же | GLM |
| `defaults.mlx_whisper` | там же | MLX Whisper |
| `defaults.deepgram` | там же | Deepgram |
| `available_providers` | там же | boolean-маска (есть ключ или нет) |
| `available_transcribers` | там же | boolean-маска |

**Moondream (editable, `MoondreamSettings.tsx:28-32`):**

| Поле | Тип | Default | API |
|------|-----|---------|-----|
| `enabled` | bool | `false` | `PUT /api/v1/settings/vision` |
| `frame_sample_rate_sec` | float (0.5..60.0, step 0.5) | зависит от backend | там же |

**⚠️ Пересечение:** API-ключи LLM **не управляются через UI** — только через `.env`. Документировано в шапке страницы (`page.tsx:28-30`). При миграции IA (REFACTR-55) — переместить read-only display в «Интеграции».

### 2.3. `/settings/connections` (YouTube OAuth, 0 form-полей)

**Компонент — control flow без полей:**

| Действие | API | Источник |
|----------|-----|----------|
| Connect YouTube | `POST /api/v1/connections/youtube/connect` | `ConnectionsSettings.tsx:40-61` |
| Disconnect YouTube | `DELETE /api/v1/connections/youtube` | строки 63-79 |
| Status polling | `GET /api/v1/connections/youtube/status` | строки 18-34 |
| Instagram Reels | **placeholder** — «в следующей фазе» | строки 152-158 |

**Read-only display fields:** `platform`, `external_account_name`, `external_account_id`, `expires_at`.

**🔴 Проблема:** Instagram блок — **явный placeholder** (стр. 152-158). По task.md §6.4 — «запрещены TODO/FIXME/mocks в production». Либо реализовать на Этапе 08, либо убрать блок до явной фичи.

### 2.4. `/settings/prompts` (динамический список, ~20 ключей)

**Схема:** ключ-значение из backend. Ключи генерируются `services/prompts.py::PromptKey` (см. REFACTR-00 §5.1).

| Поле | Тип | Источник |
|------|-----|----------|
| `key` | enum string (immutable на UI) | backend `PromptKey`: `hook_hunter_system`, `emotional_peak_finder_system`, `humor_specialist_system`, `dramatic_irony_scanner_system`, `thesis_extractor_system`, `motif_tracker_system`, `reduce_rank_system`, `story_doctor_system`, `story_doctor_travel_system`, `rhythm_check_system`, `variants_generator_system`, `closure_check_system`, `coherence_check_system`, `chapter_boundary_scorer_system`, `hook_detector_system`, `narrative_arc_finder_system`, `chunk_scorer_system`, `global_context_builder_system`, `clip_reducer_system`, `viral_2026_system`, `publer_caption_system` |
| `content` | textarea (multi-line) | `PromptsEditorClient.tsx:46-52` |

**Ожидается ~21 промпт** (по `prompts.py:40-64`).

**⚠️ Нет:** versioning UI, diff, rollback (**Решение REFACTR-54**).

### 2.5. `/settings/profiles` (4 vision-профиля × 6 полей = 24)

**Профили из backend (`VisionProfilesSettingsClient.tsx:AGENT_NAMES` + `ProfileMaskRead`):**
- `talking_head` — говорящая голова
- `fashion` — фэшн
- `screencast` — скринкаст
- `travel` — путешествия

**Поля на каждый профиль (`VisionProfilesSettingsClient.tsx:83-94`):**

| Поле | Тип | Назначение |
|------|-----|-----------|
| `enabled_agents` | multi-checkbox (AGENT_NAMES) | Какие агенты анализа включены |
| `story_weight` | slider 0.0-1.0 (round 0.001) | Вес story vs visual |
| `visual_weight` | derived (`1 - story_weight`) | — |
| `dead_zone_norm` | slider | Мёртвая зона компоновки |
| `ema_alpha` | slider | Плавность следования |
| `rule_of_thirds_y_shift` | slider | Сдвиг по правилу третей |

**⚠️ Пересечение:** имя `profile` столкнётся с Publer `account_profiles` (scheduler). В task.md §7.3 REFACTR-00 — задокументировано как риск.

### 2.6. `/settings/performance` (**29 групп, ~97 полей**)

Источник — `models/runtime_settings.py::PerformanceSettings` (500+ строк, ~50 Pydantic полей). UI в 29 файлах `performance-groups/` (REFACTR-01 §4.7). Подробный список полей:

| Группа файла | LoC | Field count (в UI) | Backend ключевые поля |
|--------------|----:|-------------------:|------------------------|
| `RenderConcurrencyGroup` | 21 | 1 | `render_concurrency` |
| `LLMGroup` | 48 | 9 | `llm_tier_profile`, `llm_lite_variant`, `pipeline_llm_provider`, + Gemini defaults |
| `NarrativeModeGroup` | 122 | 9 | `narrative_mode`, `narrative_chunk_size_chars`, `narrative_chunk_overlap_chars`, `narrative_clips_per_chunk_target`, `narrative_chunk_parallel_max` + режимы |
| `CoherenceGroup` | 149 | 6 | `coherence_mode`, `coherence_threshold` |
| `CrossChunkGroup` | 33 | 4 | `cross_chunk_reducer_enabled`, `cross_chunk_reducer_strictness` |
| `EnsembleGroup` | 33 | 2 | `reducer_ensemble_size`, `reducer_ensemble_veto` |
| `SemanticChunkingGroup` | 59 | 4 | `semantic_chunking_enabled`, `semantic_chunk_target_duration_sec`, `semantic_chunk_min_duration_sec`, `semantic_chunk_similarity_threshold` |
| `PreferenceGroup` | 33 | 3 | `preference_retrieval_mode` |
| `ReelCountGroup` | 41 | 2 | `reel_count_enforce_floor_ceiling`, `reel_count_dedup_jaccard_threshold` |
| `QualityGatesGroup` | 65 | 8 | `variants_generator_enabled`, `rhythm_critique_loop_enabled`, `skip_complete_short_arcs` + reel_target_* |
| `AutoModeGroup` | 37 | 3 | `pipeline_mode` (manual/automatic) |
| `PacingGroup` | 60 | 11 | `pacing_profile`, punchline/emphasis |
| `MultiArcGroup` | 69 | 4 | `multi_arc_enabled`, `multi_arc_window_sec`, `multi_arc_window_fallback_sec`, `multi_arc_min_evidence_per_moment` |
| `PauseCompressionGroup` | 77 | 6 | `pause_compression_*`, `breath_compression_*` |
| `CutSnapGroup` | 30 | 2 | `cut_snap_enabled`, `cut_snap_window_sec` |
| `RhythmCutsGroup` | 30 | 2 | `rhythm_aware_cuts_enabled`, `rhythm_aware_max_shift_sec` |
| `FillerRemovalGroup` | 51 | 4 | `filler_removal_*` |
| `JLCutGroup` | 50 | 5 | `jl_cut_enabled`, `jl_cut_mode`, `jl_cut_max_offset_sec` |
| `PunchlineGroup` | 53 | 3 | `punchline_pause_enabled`, `punchline_pitch_drop_hz`, `punchline_hold_after_sec` |
| `AdaptiveAudioGroup` | 54 | 4 | `mouth_sound_removal_enabled`, `breath_classifier_enabled`, `context_aware_keep_sec_enabled`, `smart_jl_chooser_enabled`, `adaptive_leveller_enabled` (**🔴 mapping на мёртвый сервис, REFACTR-00 §6**) |
| `MotionGroup` | 107 | 8 | `snap_strategy`, `onset_snap_max_shift_sec`, `punch_in_zoom_*`, `ken_burns_*` |
| `ProxyGroup` | 75 | 7 | `proxy_enabled`, `proxy_max_dim`, `proxy_video_crf`, `proxy_video_maxrate_kbps`, `proxy_audio_bitrate_kbps` |
| `ProxyCacheGroup` | 36 | 2 | `proxy_cache_max_gb`, `proxy_lock_timeout_sec` |
| `ProxySkipGroup` | 48 | 3 | `proxy_skip_height_le`, `proxy_skip_duration_lt_sec`, `proxy_skip_bitrate_lt_kbps` |
| `DefaultsGroup` | 18 | 1 | `default_use_source_for_render` |
| `ManualEditingPresetCard` | 32 | 0 | (shortcut-card, без полей) |
| `SaveBar` | 76 | 0 | (управление сохранением) |

**Итого ≈ 97 UI-полей** в performance. Главная проблема — **страница на один скролл** (все 29 групп рендерятся одновременно `PerformanceSettingsClient.tsx`). Без accordion / navigation — **boundary condition для UX**.

### 2.7. `/settings/post-production` (6 секций, ~47 label)

Источник — `models/post_production.py::PostProductionConfig` + `post_production_store`. UI-части:

| Секция (файл) | Поля |
|---------------|------|
| `PresetIdentitySection.tsx` | `name`, `description`, `is_default`, `applies_to_profile` (talking_head/fashion/…) |
| `IntroOutroSection.tsx` | `intro_video`, `intro_duration`, `outro_video`, `outro_duration`, `fade_config` |
| `AudioNormalizationSection.tsx` | `loudnorm_enabled`, `target_lufs`, `true_peak`, `loudness_range`, `two_pass_enabled` |
| `ZoomSection.tsx` | `zoom_mode`, `zoom_intensity`, Ken Burns controls |
| `VideoEffectsSection.tsx` | B&W enable, effect registry (из `services/video_effects/registry.py`) |
| `SplitScreenSection.tsx` | layout (vertical/horizontal), aspect, padding — **🔴 `overflow-x-auto` на строке 181** (REFACTR-01 §6.2) |
| `AssetsColumn.tsx` | список загруженных assets (intro/outro/logo/B-roll) |
| `PresetListColumn.tsx` | список preset'ов + create/duplicate/delete |

**🔴 Проблема группировки (`PostProductionSettingsClient.tsx:374-414`):** все 6 секций рендерятся подряд в одной колонке без accordion. task.md §2.6 — «5 подгрупп в accordion (Silence, Audio, Color/LUT, Transitions, Effects)».

### 2.8. `/settings/subtitles` (**20+ основных полей**)

Источник — `models/job.py::SubtitleStyleConfig` + `subtitle_store` + `subtitle_styles`. UI — `SubtitleStyleEditor.tsx` (653 LoC).

**Основные поля (`SubtitleStyleEditor.tsx` labels):**

| Категория | Поле | Тип | Default |
|-----------|------|-----|---------|
| Формат | `aspect_ratio` | select (9:16 / 1:1 / 16:9) | 9:16 (строка 71) |
| Формат | `fit_mode` | select (fill / fit) | fill (строка 78) |
| Позиция | `position_mode` | select | manual / auto (строка 93) |
| Позиция | `anchor` | select | — (строка 106) |
| Позиция | `position_x_pct` | slider | — (строка 149) |
| Позиция | `position_y_pct` | slider | — (строка 160) |
| Позиция | `instagram_safe_zones` | checkbox | — (строка 170) |
| Текст | `wrap_mode` | select | — (строка 188) |
| Текст | `max_lines_per_subtitle` | number | — (строка 199) |
| Шрифт | `font_family` | font picker | — (строка 229) |
| Шрифт | `size` | number (пикс) | — (строка 239) |
| Шрифт | `weight` | segmented (100-900) | — (строка 248) |
| Цвет текста | `color` | color picker | — (строка 273) |
| Обводка | `outline_width` | slider (пикс) | — (строка 284) |
| Обводка | `outline_color` | color picker | — (строка 293) |
| Тень | `shadow_width` | slider | — (строка 302) |
| Тень | `color + opacity` | ColorWithOpacity | — (строка 311) |
| Подложка (box) | `box.color + opacity` | ColorWithOpacity | — (строка 335) |
| Нижний box | offset ranges | — | — (`getOffsetRange:372`) |
| Preset meta | `name`, `is_default` | — | — (в `SubtitleSettingsClient`) |

**Итого: ~20 основных полей** (плюс подполя shadow/box). Редактор — самый плотный в приложении.

**Супер-критично (🔴 task.md §1):** **h-scroll на `/settings/subtitles`** — корень в `SubtitleSettingsClient.tsx:239` (`grid grid-cols-1 gap-6 lg:grid-cols-[240px_1fr_auto]`) — 3-колоночный grid в main area ≤1020px (settings/layout.tsx 7xl - 240px sidebar). Editor + preview не помещаются параллельно.

---

## 3. Сводная таблица (агрегат)

| Страница | Field count | Хранилище | Группировка | Проблемы (уровень) |
|----------|------------:|-----------|-------------|----|
| `/settings/brand` | 5 | localStorage | — | 🔴 поля не применяются нигде (feature stub) |
| `/settings/models` | 10 (8 read-only + 2 editable) | .env + DB | grid 2col | 🟡 API-ключи только в .env |
| `/settings/connections` | 0 form + OAuth | DB | 2 section | 🟡 Instagram блок — placeholder |
| `/settings/prompts` | ~21 | DB (`prompt_settings`) | list | 🟡 нет версионности UI |
| `/settings/profiles` | 24 (4 × 6) | DB (`profile_masks`) | accordion per profile | 🟡 имя `profile` конфликтует с Publer account_profiles |
| `/settings/performance` | ~97 (29 групп) | DB (`runtime_settings`) | линейный список | 🔴 монолит-скролл, один из флагов → мёртвый сервис (`adaptive_leveller`) |
| `/settings/post-production` | ~47 (6 секций) | DB (`post_production_presets`) | секции без accordion | 🔴 нет группировки, `SplitScreenSection:181` h-scroll |
| `/settings/subtitles` | ~20 | DB (`subtitle_style_presets`) | 3-col grid | 🔴🔴🔴 **h-scroll** (task.md «омерзительно-омерзительно-омерзительно») |
| **Итого** | **≈224** | смесь | смесь | — |

**224 настройки на 8 страницах** — подтверждает оценку task.md: «настройки разбросаны по историческим страницам».

---

## 4. Пересечения и конфликты

### 4.1. Имена «profile»

Найдено три несовместимых концепта (REFACTR-00 §9.3):
1. **Vision profile** (talking_head / fashion / screencast / travel) — `/settings/profiles`, `ProfileMaskRead`, `models/vision_settings.py`.
2. **Publer account profile** (presets публикации в соцсетях) — `scheduler_campaigns_store`, `account_profiles_store`.
3. **Narrative profile (PRO)** — `narrative_mode` в PerformanceSettings, UI в `NarrativeModeGroup.tsx`.

**Решение REFACTR-03/13:** переименование не требуется (риск регрессии высок), но вводится чёткая терминология в документации.

### 4.2. Moondream настройки в `/settings/models`

Moondream-фича — visual analysis, логически ближе к `/settings/profiles` (vision-профили), чем к `/settings/models` (LLM-модели). UI смешивает слои.

**Решение REFACTR-51:** Moondream-блок — в группу «Запись» / «Визуал» вместе с vision-профилями.

### 4.3. API-ключи — два источника

- `/settings/models` отображает наличие ключей (`info.available_providers`) из backend `GET /api/v1/models`.
- `/settings/connections` отображает YouTube OAuth статус.
- `.env` — единственный источник LLM-ключей.

Нет страницы «API keys management» — пользователь должен знать про `.env`. **Решение REFACTR-55:** «Интеграции» объединяет LLM-ключи (read-only с инструкцией) + OAuth + Publer token (в `scheduler`).

### 4.4. Настройки с мёртвыми модулями

- `adaptive_leveller_enabled` в `AdaptiveAudioGroup.tsx` → бэкенд-сервис `adaptive_leveller.py` 🔴 мёртвый (REFACTR-00 §6).

**Решение:** либо ампутировать флаг на Этапе 02 (REFACTR-13 после удаления бэкенд-сервиса), либо имплементировать сервис.

### 4.5. Настройки с дублирующимися эффектами

- `rhythm_aware_cuts_enabled` (T2.5, RhythmCutsGroup) + `snap_strategy="beat"` (MotionGroup) — оба включают beat-snapping. `snap_strategy="both"` явно дублирует T2.5.
- `breath_compression_enabled` и `breath_classifier_enabled` — разные, но названия близкие (первый обрабатывает аудио между фразами, второй — классифицирует breath vs silence).

**Решение REFACTR-53:** UX-writer (R-UX-WRITER) переименует в однозначные термины, объединит в одну группу «Аудио».

---

## 5. Horizontal scroll hunt — сводка (детали из REFACTR-01 §6.2)

| Место | file:line | Pattern | Тип |
|-------|-----------|---------|-----|
| **Субтитры** (корень) | `components/SubtitleSettingsClient.tsx:239` | `grid grid-cols-1 gap-6 lg:grid-cols-[240px_1fr_auto]` в main area ≤1020px | Architectural layout |
| Post-production main | `components/PostProductionSettingsClient.tsx:315` | `lg:grid-cols-[260px_260px_1fr]` | Architectural layout |
| Post-production split | `components/settings/post-production/SplitScreenSection.tsx:181` | `<div className="overflow-x-auto">` | Explicit scroll |
| SubtitleStyleEditor внутренние 2-col | `components/SubtitleStyleEditor.tsx:70, 238` | `grid grid-cols-2 gap-3` + `grid grid-cols-[auto_1fr]` (586) | Тесные в парной ячейке |

**🔴 Корневая боль**: трёхколоночный grid на 1024/1280/1920 viewport × subnav 240px + settings max-w-7xl = main area 1020px. Subtitle editor (богатый) + preview (360-400px) не помещаются параллельно. 

**Решение REFACTR-52**: breakpoint-aware layout:
- `1024–1280px` — 2 колонки (list + editor), preview снизу sticky или в таб.
- `1280–1920px` — 2 колонки (list + editor-tab-preview) или 3 адаптивные.
- `>1920px` — 3 колонки комфортно.

---

## 6. Предварительная IA-группировка (гипотеза для Этапа 08)

Task.md §2.6 называет «7 смысловых групп». Предлагаю следующую карту:

| Группа | Текущие страницы/компоненты → куда | Поля (count) |
|--------|-------------------------------------|--------------|
| **1. Запись / Профили** | `/settings/profiles` (4 профиля × 6) + Moondream из `/settings/models` | 26 |
| **2. Обработка / Нарезка** | `/settings/performance` (29 групп → 5 accordion-подгрупп): Narrative, Audio, Motion, Quality, Proxy | ~97 |
| **3. Визуал** | `/settings/post-production` (→ 5 accordion: Silence/Audio/Color/Transitions/Effects) + `/settings/brand` | ~47 + 5 |
| **4. Субтитры** | `/settings/subtitles` (адаптивный редактор) | ~20 |
| **5. LLM / Промпты** | `/settings/prompts` (+ tab «Модели» из `/settings/models` read-only) | ~21 + 8 read-only |
| **6. Интеграции** | `/settings/connections` (YouTube/Instagram) + Publer API (из scheduler admin) + LLM API-keys (→ read-only из .env) | YouTube OAuth + placeholder |
| **7. Устройство** | тема (dark/light), режим UI (Simple/Expert), hotkeys | новая секция, REFACTR-56 |

**Итого:** ~230 полей → 7 групп с правильной иерархией + Simple/Expert фильтр.

---

## 7. Риски и рекомендации для Этапа 08

### 7.1. Performance group split (REFACTR-53)

29 групп слишком много для плоского списка. Гипотеза split:
- **Narrative** (LLM, NarrativeMode, Coherence, CrossChunk, Ensemble, SemanticChunking, Preference, ReelCount, QualityGates, AutoMode) — 10 групп.
- **Audio** (PauseCompression, FillerRemoval, RhythmCuts, Punchline, AdaptiveAudio) — 5 групп.
- **Motion / Cuts** (CutSnap, JLCut, Motion, MultiArc, Pacing) — 5 групп.
- **Proxy / System** (Proxy, ProxyCache, ProxySkip, Defaults, RenderConcurrency) — 5 групп.
- **Shortcuts** (ManualEditingPresetCard) — 1.

### 7.2. Subtitles редактор (REFACTR-52)

Приоритет №1 — адаптивный layout. Рекомендация: поместить preview в `<Tabs>`:
- Tab «Редактор» (full editor, 100% ширины).
- Tab «Превью» (full preview на 9:16 / 1:1 / 16:9 с toggle).
- Tab «Список пресетов» (list column).

На >1440 viewport — 2 колонки (editor + preview), список сворачивается в sidebar.

### 7.3. Brand kit (REFACTR-55)

**Решение**: реализовать применение кита (brand primary → subtitle accent, brand secondary → post-prod overlay). Либо удалить страницу. **STOP-2 — вопрос владельцу на этапе 08**, если приоритет неясен.

### 7.4. Connections Instagram (REFACTR-55)

Убрать placeholder-блок до момента реализации (по task.md §6.4). Либо оставить с явной меткой «скоро» — но чётко.

### 7.5. Prompts versioning (REFACTR-54)

Добавить:
- История версий prompt'а (БД уже поддерживает через `prompt_store`).
- Diff previous vs current.
- Rollback button.
- Tab-split: модели (read-only) + промпты (editable).

### 7.6. Simple vs Expert режим (REFACTR-56)

**Эталон:** каждая настройка получает `complexity` атрибут (simple / expert). Simple mode показывает только ~20% полей — самые важные (тема, темп, субтитры, основная нарезка). Остальные — под Expert toggle.

---

## 8. Ключевые находки (TL;DR)

1. **8 страниц, ~224 настройки**, LoC главных клиентов = **3745**.
2. **Performance page — 97 полей в 29 группах** рендерится как монолит-скролл. Требует accordion + sub-nav (REFACTR-53).
3. **Subtitles 3-col grid в 1020px main area** — корень h-scroll. Architectural layout, не overflow-bug (REFACTR-52).
4. **Brand kit в localStorage**, не применяется никуда — feature stub. Решение — либо реализовать, либо удалить.
5. **Instagram в connections — открытый placeholder**, нарушает no-stub требование task.md §6.4.
6. **3 разных «profile»** (vision / Publer account / narrative) — терминологический конфликт, документирован для REFACTR-13.
7. **Флаг `adaptive_leveller_enabled` в UI, но backend-сервис мёртвый** (REFACTR-00 §6). Ампутируется на Этапе 02 (REFACTR-13).
8. **API-ключи LLM — только `.env`**, UI отражает статус (read-only). При миграции IA в «Интеграции».
9. **Дубликаты флагов**: `rhythm_aware_cuts_enabled` vs `snap_strategy="beat"` включают одинаковый beat-snap. UX-редактор (R-UX-WRITER) на Этапе 08 переименует/объединит.
10. **Prompts без versioning UI** — история есть в БД, но пользователь не видит (REFACTR-54).

---

**Артефакт записан:** `docs/audit/02-settings-inventory.md`
**Serena memory:** `refactr-02-settings-inventory`
**Следующий чанк:** REFACTR-03 — Профили и PRO-код (детальная ампутационная карта `narrative_mode`).
