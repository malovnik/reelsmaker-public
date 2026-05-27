# 03 — PRO Removal Plan: ампутационная карта narrative_mode

> **Чанк:** REFACTR-03 (4 из 67). **Этап:** 00 — Исследование и аудит.
> **Дата:** 2026-04-24. **Роль:** R-AUDITOR + R-BACKEND-SURGEON (консультативно).
> **Зависимости:** REFACTR-00 (backend map), REFACTR-01 (frontend map), REFACTR-02 (settings inventory).
> **Следующий шаг:** REFACTR-04 (схема данных).

---

## 0. Дизамбигуация: три разных «profile»

Словарь владельца task.md путает три независимых концепта. В кодовой базе они не связаны и трогать их надо раздельно.

| Концепт | Где лежит | Что это | Нужна ли ампутация? |
|---------|-----------|---------|---------------------|
| **`narrative_mode`** (он же «PRO») | `models/runtime_settings.py:55` — Literal из 4 значений | Переключатель pipeline: какой алгоритм собирает рилсы из транскрипта | **ДА.** Удалить `bottom_up` + `map_reduce`. Оставить `viral_2026` (default) + `chaptered` (legacy fallback) |
| `vision_profile` | `models/job.py::VisionProfile` (enum), `services/profile_detector.py`, `services/profile_masks.py` | Тип контента: talking_head / fashion / screencast / etc. Выбирает маску vision-анализа | **НЕТ.** Отдельный домен, нейтрален к narrative-ампутации |
| `account_profile` | `services/account_profiles_store.py`, `models/account_profile.py` | Пресеты Publer-публикации (Instagram-аккаунт, caption-style) | **НЕТ.** Отдельный домен |

Далее в этом документе под «PRO» понимается **только `narrative_mode`**.

---

## 1. Текущее состояние `narrative_mode`

### 1.1. Определения литерала (ДУБЛЬ — критично)

В коде живут **два конкурирующих определения** с разными значениями:

| Файл | Строка | Литерал |
|------|--------|---------|
| `apps/backend/src/videomaker/models/runtime_settings.py` | 55 | `NarrativeMode = Literal["bottom_up", "chaptered", "map_reduce", "viral_2026"]` — 4 значения, используется Pydantic-моделью `PerformanceSettings` |
| `apps/backend/src/videomaker/models/narrative.py` | 41 | `NarrativeMode = Literal["bottom_up", "top_down"]` — 2 значения, **legacy docstring-литерал**, не импортируется нигде |

Решение: `models/narrative.py:41` — мёртвый литерал, подлежит удалению (только docstring). `runtime_settings.py:55` — канонический, после ампутации стянется до `Literal["chaptered", "viral_2026"]`.

### 1.2. Значение по умолчанию

`apps/backend/src/videomaker/models/runtime_settings.py:269-284`:

```python
narrative_mode: NarrativeMode = Field(
    default="bottom_up",
    description="Архитектура сборки рилсов. bottom_up (legacy) ... Default bottom_up — zero regression. Для тестов map_reduce/viral_2026."
)
```

После ампутации: `default="viral_2026"`, description — переписать без упоминания legacy.

### 1.3. Состояние storage (БД `data/videomaker.db`)

SQLite, таблица `runtime_settings` (key-value с JSON-value). Текущие ключи, связанные с narrative-ампутацией:

| Ключ | Значение | Updated | Привязан к |
|------|----------|---------|------------|
| `narrative_mode` | **`"viral_2026"`** | 2026-04-21 | — (оставить, default→viral_2026) |
| `narrative_chunk_size_chars` | `20000` | 2026-04-21 | map_reduce (удалить) |
| `narrative_chunk_overlap_chars` | `2000` | 2026-04-21 | map_reduce (удалить) |
| `narrative_clips_per_chunk_target` | `15` | 2026-04-21 | map_reduce (удалить) |
| `narrative_chunk_parallel_max` | `10` | 2026-04-21 | map_reduce (удалить) |
| `multi_arc_enabled` | `true` | 2026-04-21 | bottom_up (удалить) |
| `multi_arc_window_sec`, `multi_arc_window_fallback_sec`, `multi_arc_min_evidence_per_moment` | (default-значения) | — | bottom_up (удалить) |
| `coherence_mode` | `"resort"` | 2026-04-17 | bottom_up — coherence_validator (удалить) |
| `reducer_ensemble_size` | `1` | 2026-04-18 | bottom_up — reducer ensemble judge (удалить) |
| `cross_chunk_reducer_enabled` | `false` | 2026-04-18 | bottom_up — cross_chunk_reducer (удалить) |
| `variants_generator_enabled` | `true` | 2026-04-20 | bottom_up — variants_generator (удалить) |
| `rhythm_critique_loop_enabled` | `true` | 2026-04-20 | bottom_up — rhythm critique (удалить) |
| `semantic_chunking_enabled` | `true` | 2026-04-18 | bottom_up / chaptered preamble (зависит — см. §5) |
| `skip_complete_short_arcs` | `true` | 2026-04-22 | bottom_up (удалить) |
| `pacing_profile` | `"documentary"` | 2026-04-19 | bottom_up — composer bias (удалить) |
| `preference_retrieval_mode` | `"cosine"` | 2026-04-19 | bottom_up — preference_memory (удалить) |

**КРИТИЧЕСКИ ВАЖНЫЙ ВЫВОД:** владелец уже перешёл на `viral_2026` в продакшне (2026-04-21). Default `bottom_up` не отражает реальное использование. Ампутация *декларирует в коде то, что уже свершилось в данных*.

### 1.4. Распределение jobs по narrative_mode

Из таблицы `jobs` и `artifacts.meta`:

| Метрика | Значение |
|---------|----------|
| Всего jobs в БД | 50 |
| Артефактов `reel_plan` с меткой `narrative_mode` в meta | 2 (оба `viral_2026`) |
| Артефактов `reel_plan` без метки (bottom_up era, pre-2026-04-22) | ~41 |

Миграция данных **не требуется**: исторические `reel_plan.json` файлы остаются на диске в `data/artifacts/<job_id>/`, они валидны как артефакты прошедших рендеров. Удаление кода `bottom_up` не делает эти артефакты невалидными — они уже финализированы.

---

## 2. Таблица упоминаний PRO в коде

### 2.1. Backend Python (`apps/backend/src/videomaker/`)

| Файл | Строка | Контекст | Действие |
|------|--------|----------|----------|
| `models/runtime_settings.py` | 50-56 | Docstring + `NarrativeMode` литерал | Переписать: оставить только `chaptered` + `viral_2026` |
| `models/runtime_settings.py` | 259-284 | Поле `narrative_mode` + default=`bottom_up` | `default="viral_2026"`, description переписать |
| `models/runtime_settings.py` | 286-328 | Поля `narrative_chunk_size_chars`, `narrative_chunk_overlap_chars`, `narrative_clips_per_chunk_target`, `narrative_chunk_parallel_max` | Удалить — применяются только к map_reduce |
| `models/runtime_settings.py` | 330-368 | Поля `multi_arc_*` (4 шт.) | Удалить — bottom_up-only |
| `models/runtime_settings.py` | 91-123, 445-449, и др. | Поля `variants_generator_enabled`, `rhythm_critique_loop_enabled`, `coherence_mode`, `coherence_threshold`, `preference_retrieval_mode`, `pacing_profile`, `reducer_ensemble_size`, `reducer_ensemble_veto`, `cross_chunk_reducer_enabled`, `cross_chunk_reducer_strictness`, `skip_complete_short_arcs`, `semantic_chunk_*` (3 поля) | Удалить — bottom_up-only (см. §3 граф) |
| `models/narrative.py` | 13, 41-48 | Legacy `NarrativeMode = Literal["bottom_up", "top_down"]` + docstring | Удалить литерал, переписать docstring |
| `services/pipeline_stages/analysis.py` | 38-99 | Импорты `orchestrate_extraction`, `reduce_and_rank`, `compose_reels`, `compose_story_script`, `generate_variants`, `check_rhythm`, `validate_coherence`, `validate_closures`, `apply_cross_chunk_coherence`, `orchestrate_map_reduce`, `semantic_chunk_transcript`, `load_liked_anchors_text`, `mean_embedding`, `run_visual_evidence_agent`, `validate_arc`, `compute_trend_score` | Удалить импорты, relevant только bottom_up/map_reduce |
| `services/pipeline_stages/analysis.py` | 235-274 | Branch-switch `narrative_mode` | Упростить: `if == "chaptered"` → top_down, else → viral_2026 |
| `services/pipeline_stages/analysis.py` | 276-676 | Весь bottom_up flow (preference → extraction → reducer → cross_chunk → story_doctor → rhythm loop → variants → composer → coherence → closure) | Удалить целиком (~400 строк) |
| `services/pipeline_stages/analysis.py` | 678-830 | `_run_top_down_branch` — обслуживает chaptered + map_reduce | Сузить: только chaptered, выкинуть ветку `if narrative_mode == "map_reduce"` |
| `services/pipeline_stages/analysis.py` | 717-745 | `if narrative_mode == "map_reduce":` + `orchestrate_map_reduce(...)` | Удалить целиком |
| `services/pipeline_stages/analysis.py` | 804, 817 | `"narrative_mode": "top_down"` в analysis_summary.meta | Переписать на `"chaptered"` |
| `services/pipeline_stages/analysis.py` | 833-940 | `_run_viral_2026_branch` | Оставить без изменений (production default) |
| `services/pipeline_stages/analysis.py` | ≈970-1400 | Helper'ы bottom_up: `_run_extraction_with_retry`, `_compose_with_rhythm_loop`, `_critique_text_for_rhythm`, `_build_visual_evidence_tool`, `_apply_visual_validator` | Удалить (все зависят от удаляемых модулей) |
| `services/viral_arc_builder.py` | 18, 408 | Docstring referencing `narrative_mode == "viral_2026"` | Оставить — этот модуль ядро Viral 2026 |
| `services/performance_settings_store.py` | 91-98 | Legacy migration: `if narrative_mode == "top_down": → "chaptered"` | Оставить (safety migration для старых JSON-дампов из пользовательских БД) |
| `services/narrative/__init__.py` | 9 | Docstring: `narrative_mode = "top_down"` | Переписать на `"chaptered"` |
| `services/narrative/orchestrator.py` | 102, 125, 143, 172, 325 | Literals `"narrative_mode": "top_down"` в stats | Переписать на `"chaptered"` |
| `services/narrative/map_reduce_orchestrator.py` | 1-485 | Весь файл | **Удалить целиком** (485 строк) |
| `services/narrative/chunk_scorer.py` | 1-? | Зависимый от map_reduce_orchestrator | **Удалить целиком** |
| `services/narrative/clip_reducer.py` | 1-? | Зависимый от map_reduce_orchestrator | **Удалить целиком** |
| `services/narrative/global_context_builder.py` | 1-? | Зависимый от map_reduce_orchestrator | **Удалить целиком** |

### 2.2. Frontend TypeScript (`apps/frontend/src/`)

| Файл | Строка | Контекст | Действие |
|------|--------|----------|----------|
| `lib/api/settings.ts` | 158 | `narrative_mode: "bottom_up" \| "chaptered" \| "map_reduce" \| "viral_2026"` в PerformanceSettings type | Сузить до `"chaptered" \| "viral_2026"` |
| `components/settings/performance-groups/NarrativeModeGroup.tsx` | 6 | Тип `NarrativeMode = "bottom_up" \| "chaptered" \| "map_reduce" \| "viral_2026"` | Сузить |
| `components/settings/performance-groups/NarrativeModeGroup.tsx` | 8-28 | `NARRATIVE_MODE_META` — meta-описания всех 4 режимов | Удалить записи `bottom_up` и `map_reduce`, переписать описания `chaptered`/`viral_2026` под новый UX |
| `components/settings/performance-groups/NarrativeModeGroup.tsx` | 31 | `(values.narrative_mode ?? "bottom_up")` — fallback | `?? "viral_2026"` |
| `components/settings/performance-groups/NarrativeModeGroup.tsx` | 37 | `"Default bottom_up — не меняет существующий pipeline. Для тестов OpusClip-quality переключайся на map_reduce."` | Переписать текст |
| `components/settings/performance-groups/NarrativeModeGroup.tsx` | 72-119 | Conditional UI для `narrative_chunk_*` когда `current === "map_reduce"` | Удалить целиком (47 строк) |

**Замечание:** на Этапе 08 (REFACTR-51..57) settings UI пересоздаётся в IA-группах. Этот компонент всё равно будет реструктурирован — достаточно очистить типы и не ломать компиляцию при ампутации на Этапе 02.

---

## 3. Граф зависимостей: кто от кого зависит

### 3.1. Bottom-up (target ампутации A)

ASCII-дерево (стрелка = `import`):

```
pipeline_stages/analysis.py::run_analysis_stage  (bottom_up ветка, строки 276-676)
├── services.agents.orchestrator::orchestrate_extraction
│   └── services.agents.base::AgentResult
│       └── (также импортируется extraction_coverage.py:28 — удалить этот файл тоже)
├── services.reducer::reduce_and_rank
│   └── services.agents.orchestrator::ExtractionResult (возвращает)
├── services.cross_chunk_reducer::apply_cross_chunk_coherence
│   └── services.reducer::reduce_and_rank (внутренний вызов)
├── services.story_doctor::compose_story_script
│   └── (вызывается также services.multi_arc_builder::build_arcs_per_moment
│        — оба удаляются)
├── services.rhythm_check::check_rhythm
├── services.variants_generator::generate_variants
├── services.reels_composer::compose_reels  (2198 LoC — крупнейший файл)
│   └── (читает PerformanceSettings: pacing_profile, reel_target_*,
│        reel_count_*, multi_arc_*)
├── services.coherence_validator::validate_coherence
├── services.closure_validator::validate_closures
├── services.preference_memory::load_liked_anchors_text
│   └── services.preference_memory::mean_embedding
├── services.trend_lexicons::compute_trend_score
├── services.visual_evidence_agent::run_visual_evidence_agent
│   └── ТАКЖЕ импортируется services.broll.index.py:20 — НЕ удалять модуль
│     полностью. На Этапе 02 — решить: вынести общую часть либо оставить
│     visual_evidence_agent как shared.
├── services.visual_validator::validate_arc
│   └── (используется только в _apply_visual_validator внутри analysis.py)
├── services.multi_arc_builder::build_arcs_per_moment  (локальный import)
│   └── services.story_doctor::compose_story_script (внутренний вызов)
└── services.semantic_chunker::semantic_chunk_transcript
    └── (также вызывается в shared-преамбуле analysis.py:171 —
        используется chaptered + viral_2026 тоже; НЕ удалять целиком,
        но можно упростить после ампутации — см. §5)
```

### 3.2. Map-Reduce (target ампутации B)

```
pipeline_stages/analysis.py::_run_top_down_branch  (строки 717-745, map_reduce ветка)
└── services.narrative.map_reduce_orchestrator::orchestrate_map_reduce
    ├── services.narrative.global_context_builder::build_global_context
    │   └── services.narrative.chunk_scorer::GlobalContext (type)
    ├── services.narrative.chunk_scorer::score_chunks, ChunkDiagnostic,
    │   GlobalContext, RawClipCandidate
    ├── services.narrative.clip_reducer::reduce_and_rank
    │   └── services.narrative.chunk_scorer::GlobalContext, RawClipCandidate
    └── services.narrative.boundary_extender::extend_boundaries
        └── ТАКЖЕ импортируется services.narrative.orchestrator.py:38 —
          НЕ удалять (нужен chaptered).
```

### 3.3. Chaptered (ОСТАЁТСЯ)

```
pipeline_stages/analysis.py::_run_top_down_branch  (строки 746-757, chaptered ветка)
└── services.narrative.orchestrator::orchestrate_top_down
    ├── services.narrative.chapter_builder::build_chapters  (1073 LoC)
    ├── services.narrative.hook_detector::detect_hooks  (478 LoC)
    ├── services.narrative.arc_finder::find_arcs  (537 LoC)
    ├── services.narrative.boundary_extender::extend_boundaries  (391 LoC)
    └── services.narrative.cross_chapter_ranker::rank_and_select  (424 LoC)
Всего chaptered-only модулей: 5 файлов, ~2903 LoC.
```

### 3.4. Viral 2026 (ОСТАЁТСЯ, production default)

```
pipeline_stages/analysis.py::_run_viral_2026_branch  (строки 833-940)
└── services.viral_arc_builder::build_viral_arcs  (474 LoC)
    ├── services.llm_client::build_llm_for_tier
    ├── services.prompts::VIRAL_2026_PROMPT
    ├── services.rate_limiter::RateLimiter, get_gemini_rate_limiter
    └── services.transcribers.base::TranscribedSegment, TranscriptResult
Внешних зависимостей нет. Виральный билдер самодостаточен.
```

---

## 4. Итоговый список модулей к удалению на Этапе 02 (REFACTR-13)

### 4.1. Полное удаление (файлы целиком)

| Путь | LoC | Причина |
|------|-----|---------|
| `services/agents/__init__.py` | ? | bottom_up only |
| `services/agents/base.py` | ? | bottom_up only |
| `services/agents/orchestrator.py` | ? | bottom_up — ExtractionResult + orchestrate_extraction |
| `services/extraction_coverage.py` | 229 | Использует `agents.base::AgentResult` — только bottom_up |
| `services/reducer.py` | 673 | bottom_up only |
| `services/cross_chunk_reducer.py` | 256 | Использует reducer — bottom_up only |
| `services/story_doctor.py` | 443 | bottom_up only |
| `services/rhythm_check.py` | 201 | bottom_up only |
| `services/coherence_validator.py` | 447 | bottom_up only |
| `services/closure_validator.py` | 486 | bottom_up only |
| `services/variants_generator.py` | 215 | bottom_up only |
| `services/reels_composer.py` | **2198** | bottom_up only — крупнейший файл репозитория |
| `services/multi_arc_builder.py` | 236 | Использует `story_doctor::compose_story_script` — bottom_up only |
| `services/preference_memory.py` | 353 | Использует canvas embeddings — только bottom_up читает `load_liked_anchors_text` |
| `services/trend_lexicons.py` | 116 | Используется только в bottom_up ветке analysis.py:1271 |
| `services/narrative/map_reduce_orchestrator.py` | 485 | map_reduce only |
| `services/narrative/chunk_scorer.py` | ? | Импортируется только из map_reduce_orchestrator + clip_reducer + global_context_builder |
| `services/narrative/clip_reducer.py` | ? | map_reduce only |
| `services/narrative/global_context_builder.py` | ? | map_reduce only |

**Итого:** 19 файлов, **≥7 067 LoC** (без `agents/*` — ещё +300-500 LoC оценочно).

### 4.2. Частичное удаление (трогать код внутри файла)

| Файл | Удалить | Оставить |
|------|---------|----------|
| `models/runtime_settings.py` | поля: `narrative_chunk_*` (4), `multi_arc_*` (4), `variants_generator_enabled`, `rhythm_critique_loop_enabled`, `coherence_mode/threshold`, `preference_retrieval_mode`, `pacing_profile`, `reducer_ensemble_*` (2), `cross_chunk_reducer_*` (2), `skip_complete_short_arcs`, `semantic_chunk_*` (3) — итого **≈20 полей**. Сузить `NarrativeMode` литерал до 2 значений, default=`viral_2026`. | Всё, не связанное с narrative (render/proxy/vision/punchline/zoom/face/ken_burns/breath/audio/snap/screencast/filler settings) |
| `models/narrative.py` | `NarrativeMode = Literal["bottom_up", "top_down"]` (строка 41) + docstring переработать | Pydantic-модели `Chapter`, `HookCandidate`, `NarrativeArc`, `ExtendedArc`, `ReelCandidate` |
| `services/pipeline_stages/analysis.py` | импорты 38-99 (bottom_up + map_reduce), весь bottom_up flow (строки 276-676), map_reduce ветка `_run_top_down_branch` (строки 717-745), все helper'ы bottom_up (≈970-1400) | Preamble (chunker/compression/canvas), `_run_top_down_branch` для chaptered, `_run_viral_2026_branch`, `_apply_cover_selector` |
| `services/pipeline.py` | docstring строки 10-17 (упоминание 6-этапов bottom_up) | `run_pipeline_safe`, `_advance`, логика диспетчера |
| `services/narrative/__init__.py` | docstring line 9: `"top_down"` → `"chaptered"` | остальное |
| `services/narrative/orchestrator.py` | строки 102, 125, 143, 172, 325: `"top_down"` → `"chaptered"` | основная логика |
| `services/performance_settings_store.py` | **ОСТАВИТЬ** migration `top_down → chaptered` (91-98) как safety для старых JSON-дампов. Добавить migration `bottom_up|map_reduce → viral_2026` | — |
| `services/semantic_chunker.py` | Решить на REFACTR-13: удалять целиком (viral_2026 не использует) либо оставить для chaptered. Chaptered использует свой `chapter_builder`, не `semantic_chunker`. Vuдалить. | — |
| `lib/api/settings.ts` (frontend) | поля `narrative_chunk_*` (4), `multi_arc_*` (4), прочие bottom_up-поля в `PerformanceSettings` type | остальное |
| `components/settings/performance-groups/NarrativeModeGroup.tsx` | строки 12-15 (bottom_up meta), 20-23 (map_reduce meta), 31 fallback, 34-38 текст, 72-119 map_reduce chunk-settings UI | оболочка Group + chaptered/viral_2026 записи |

---

## 5. Тонкие места / риски

### 5.1. Shared модули preamble

Preamble в `analysis.py:160-232` выполняется для ВСЕХ `narrative_mode` (включая viral_2026):

| Модуль | LoC | Зачем нужен viral_2026? |
|--------|-----|-------------------------|
| `chunker.py` | 257 | Fallback когда `semantic_chunking_enabled=False`. viral_arc_builder использует свой chunker (20K chars). Для viral_2026 preamble-chunks **не используются downstream**. |
| `semantic_chunker.py` | 258 | Тот же случай: для viral_2026 результат выбрасывается. |
| `compression.py` | 191 | compression → canvas. viral_2026 канву использует только для analysis_summary.json метадаты, но canvas.central_theme / themes / motifs эффективно не нужны. |
| `canvas_builder.py` | 603 | То же самое — canvas для viral_2026 — декоративная метадата. |
| `canvas_embedder.py` | 243 | embeddings на candidate_moments. viral_2026 не использует (preference_memory удаляется). **После ампутации — удалить целиком.** |

**РЕШЕНИЕ для REFACTR-13:**
- `canvas_embedder.py` — удалить целиком (223 LoC).
- `chunker.py` / `semantic_chunker.py` / `compression.py` / `canvas_builder.py` — оставить как есть, но на REFACTR-21 (перфоманс) рассмотреть skip'анье preamble для `viral_2026` (экономия ~30-60 сек на 60-мин видео).
- Либо, как более чистое решение, — переместить preamble внутрь веток (chaptered_branch, viral_2026_branch) и там решать что нужно.

### 5.2. Хранилище `runtime_settings` — миграция значений

После удаления полей из Pydantic-модели `PerformanceSettings` они начнут вызывать `ValidationError` (модель имеет `extra="forbid"` на `apps/backend/src/videomaker/models/runtime_settings.py:61`) **на старте приложения**, потому что `performance_settings_store` читает 80+ ключей из `runtime_settings` table и конструирует `PerformanceSettings`.

Migration-план (REFACTR-14):
1. Alembic-миграция: `DELETE FROM runtime_settings WHERE key IN (...)` для всех 20 удалённых полей. Обратимая migration — downgrade: re-insert defaults (но нам не нужно).
2. В `performance_settings_store.py::load_performance_settings` добавить `migrated_keys` на конструирование: известные устаревшие ключи игнорировать до рестарта миграции. **Либо**, если миграция выполнится на startup через Alembic — в `load_performance_settings` защиту не нужно.
3. Migration для `narrative_mode`: если value IN (`bottom_up`, `map_reduce`) → `UPDATE SET value='viral_2026'`. (На сейчас в БД уже `viral_2026`, но для другой инсталляции / бэкапа `data/videomaker.db.bak-20260423-192330` этот случай возможен.)

### 5.3. Historical artifacts

На диске `data/artifacts/<job_id>/reel_plan.json` — исторические файлы. Они содержат поля, которые не меняются. **Оставить как есть.** Никаких preferences из них больше не читается (preference_memory удаляется).

Артефакты типа `reducer_candidates.json`, `story_script.json`, `rhythm_report.json`, `variants.json`, `coherence_report.json`, `closure_report.json` — становятся orphan'ами (никто их не создаёт и не читает). Для чистоты Этапа 10 (REFACTR-62-66) стоит не удалять их принудительно — пользовательские данные неприкосновенны.

### 5.4. Функциональная регрессия Viral 2026 vs bottom_up

**Это ключевой риск, достойный ADR (Этап 01).** Viral 2026 значительно беднее по инструментам:

| Функция | bottom_up | chaptered | viral_2026 |
|---------|-----------|-----------|------------|
| Preference memory (few-shot из лайков) | ✅ | ❌ | ❌ |
| Trend lexicons boost | ✅ | ❌ | ❌ |
| Multi-variant output (4 формата рилса) | ✅ | ❌ | ❌ |
| Rhythm critique loop (3 итерации) | ✅ | ❌ | ❌ |
| Coherence validator (arc resort) | ✅ | ❌ | ❌ |
| Closure validator | ✅ | ❌ | ❌ |
| Reducer ensemble judge (5x voting) | ✅ | ❌ | ❌ |
| Cross-chunk coherence | ✅ | ❌ | ❌ |
| Visual validator (vision score) | ✅ | ❌ | ❌ |
| Multi-arc per moment | ✅ | ❌ | ❌ |
| Padding до MIN | ✅ | ❌ | ❌ |
| Density-aware (OpusClip-style) | ❌ | ❌ (фиксированный target) | ✅ (chunk-per-chunk) |
| Natural arc length (без padding) | ❌ | ✅ | ✅ |
| Зависит от Pro-tier модели | да | да | нет (только Flash Lite) |
| LLM calls на 90-мин видео | 80-120 | ≈20-30 | 10-15 |

**Оценка:** осознанный compromise владельца. `viral_2026` = дёшево (Flash Lite, 10-15 calls) + быстро + production-tested. Теряется качество scoring-а (нет ensemble), нет лайк-адаптации, нет вариантов форматов.

**СТОП-2 НЕ срабатывает**, потому что:
- Владелец явно задал direction в task.md §8 («PRO — удалить»).
- Владелец уже использует `viral_2026` в БД (2026-04-21 — 3 дня перед этим аудитом).
- Chaptered остаётся как fallback для сложных случаев.

**Что требует ADR (REFACTR-07..12):**
- Принятие регрессии функциональности как осознанное архитектурное решение.
- Документирование того, что Viral 2026 + Chaptered Legacy — это **новая архитектурная парадигма**, а не частичный downgrade.
- Решение по возврату preference_memory / variants / coherence_validator в будущем (если понадобятся) — новой реализацией поверх viral_arc_builder, а не воскрешением bottom_up.

### 5.5. Performance_settings_store migration safety

`performance_settings_store.py:91-98`:
```python
# Phase 8 migration (2026-04-21): legacy narrative_mode values.
if merged.get("narrative_mode") == "top_down":
    merged["narrative_mode"] = "chaptered"
```

Это safety-net для старых user-БД. Расширить:
```python
if merged.get("narrative_mode") in ("top_down", "bottom_up", "map_reduce"):
    merged["narrative_mode"] = "viral_2026"
```

Важно для случая: пользователь восстанавливает `data/videomaker.db.bak-20260423-192330` или аналогичный бэкап — приложение должно не упасть, а мигрировать в разумный default.

### 5.6. Порядок ампутации (fail-safe)

На REFACTR-13 выполнять в таком порядке, чтобы ни в какой момент не поломать compilation + pipeline:

1. **Сперва** сузить Pydantic-модель: убрать 20 полей, сузить literal.
2. **Alembic migration**: очистка `runtime_settings` keys, update `narrative_mode` value.
3. **Удаление импортов** в `analysis.py`: сначала только импорты, pipeline продолжает работать для `viral_2026` и `chaptered` (bottom_up branch выбросит dev-only ImportError, но юзер уже не использует).
4. **Удаление bottom_up веточки** в `run_analysis_stage`.
5. **Удаление bottom_up helper'ов** (`_run_extraction_with_retry`, `_compose_with_rhythm_loop`, и т.д.).
6. **Удаление map_reduce веточки** в `_run_top_down_branch`. После этого `_run_top_down_branch` становится `_run_chaptered_branch` с упрощённым телом.
7. **Удаление файлов**: `reels_composer`, `story_doctor`, `variants_generator`, etc. — в последнюю очередь, когда импорты уже не ссылаются.
8. **Frontend**: сузить type в `lib/api/settings.ts`, переписать `NarrativeModeGroup.tsx`.

Между каждыми шагами — `uv run pytest` (хотя тестов нет) + `uv run python -c "from videomaker.main import app"` (smoke import) + `curl http://localhost:8000/api/v1/settings/performance` (runtime smoke).

---

## 6. GATE-чекпоинт (REFACTR-03)

- [x] Все упоминания PRO выписаны: **~40 code-refs** в backend + **6 refs** в frontend + **20 runtime_settings полей** в БД.
- [x] Зависимости построены, критичные точки выделены.
- [x] Состояние storage зафиксировано: `narrative_mode="viral_2026"` + 15 bottom_up/map_reduce-specific ключей с фактическими значениями.
- [x] Viral 2026 и Chapter Legacy подтверждены как работающие (branch'и в analysis.py отдельны, не зависят от удаляемых модулей).
- [x] Риски ампутации описаны: **СТОП-2 НЕ срабатывает**, но требуется ADR на Этапе 01 для документирования функциональной регрессии.

---

## 7. Следующий чанк

**REFACTR-04** — Схема данных: Alembic-миграция для Project (settings_snapshot_path, stage_progress, soft_deleted_at, parent_project_id), новая таблица ReelIdea (для approve/reject/regenerate флоу).

Ампутация PRO-кода — REFACTR-13 (Этап 02). Там выполняются п.4 + п.5.6 (migration safety + порядок удаления).
