# Agent C — Narrative Pipeline & LLM Infrastructure

Audit root: `apps/backend/src/videomaker`

Note on scope drift: the task's file list described an older layout. The codebase has since refactored. The narrative pipeline now lives in `services/narrative/` (12 modules) plus a set of standalone `services/*.py` stages; LLM infra split into `services/llm_clients/` (9 files) + `services/llm_providers/` (6 files) behind the `services/llm_client.py` facade. All listed scope files exist; mapping is given below.

---

## LLM-провайдеры и выбор модели

### Зарегистрированные провайдеры
Registry: `services/llm_providers/registry.py` (`PROVIDER_REGISTRY`, `register_llm_provider`, `get_llm_provider`). Регистрация — side-effect импорта `services/llm_providers/__init__.py:26-29`:

| Provider name | Factory | Client | API key | Notes |
|---|---|---|---|---|
| `gemini` | `gemini_factory.py:GeminiProviderFactory` | `llm_clients/gemini.py:GeminiClient` | `gemini_api_key` | Дефолтный. Поддерживает context caching (`create_cache`/`delete_cache`). |
| `anthropic` | `claude_factory.py:ClaudeProviderFactory` | `llm_clients/claude.py:ClaudeClient` | `anthropic_api_key` | Клиент реальный (`complete_json` имплементирован, claude.py:32). **Не используется ни одним pipeline-вызовом** — все стадии идут через `gemini`/`zhipu`. |
| `openai` | `openai_factory.py:OpenAIProviderFactory` | `llm_clients/openai.py:OpenAIClient` | `openai_api_key` | Клиент реальный (openai.py:31). **Также нигде в narrative-пайплайне не выбирается.** |
| `zhipu` | `zhipu_factory.py:ZhipuProviderFactory` | `llm_clients/zhipu.py:GLMClient` | `zhipu_api_key` + `zhipu_base_url` | GLM-5.1 Coding Plan. Hard-switch через UI `PerformanceSettings.pipeline_llm_provider`. Отдельный rate-limiter + concurrency=1 семафор. |

### Два входа в фабрику (`services/llm_client.py`)
- `build_llm(provider, model)` (llm_client.py:37) — прямой выбор провайдера+модели. Использует `translator.py` и `auto_config_llm_fallback.py`.
- `build_llm_for_tier(tier, settings, provider_override)` (llm_client.py:58) — основной путь pipeline. `tier ∈ {pro, flash, flash_lite}`. `provider_override=None → "gemini"`. Делегирует резолв модели фабрике провайдера (`tier_model`).

### Tier matrix (`services/llm_clients/tier_resolver.py`)
Жёсткий constraint: **разрешены только Flash-Lite модели**, профили balanced/quality удалены (tier_resolver.py:8-9). Pro/Flash/Flash-Lite tier — лишь логические метки, физически все три маппятся на Lite.

Для Gemini (`_resolve_tier_models`, tier_resolver.py:55):
- Профиль читается из `PerformanceSettings.llm_tier_profile` + `llm_lite_variant` (`2_5`|`3_1`).
- `fast` профиль: все три tier → выбранный Lite (`gemini-2.5-flash-lite` или `gemini-3.1-flash-lite-preview`).
- `legacy` профиль: все три tier → жёстко `gemini-3.1-flash-lite-preview`.
- **Cold-cache fallback** (runtime_settings ещё не прогреты): → `fast` (all-Lite). Любой нераспознанный профиль тоже коерсится к `fast` — гарантия что pipeline никогда не уйдёт за Lite.

Для Zhipu (`zhipu_factory.py:26`): плоский маппинг `pro/flash/flash_lite → Settings.zhipu_{pro,flash,flash_lite}_model` (по умолчанию все `glm-5.1`).

### Fallback-логика
- **Tier-resolve fallback**: cold cache → fast (см. выше).
- **Retry**: `llm_clients/retry.py` — tenacity wrapper `_retry` + `_is_retryable` на транзиентные ошибки.
- **JSON-repair**: `llm_clients/json_parser.py:parse_json_response` с repair-fallbacks (для verbose Flash-Lite вывода).
- **Per-stage fallback**: почти каждая стадия имеет детерминистический fallback при провале LLM (см. таблицу: `_fallback_chunk`, `_fallback_ranked_evidence`, `_fallback_script`, `_fallback_variants`, `_heuristic_rhythm_report`).
- **Lifecycle**: `build_*` валидируют наличие ключа в фабрике, бросают `LLMError`.

---

## Narrative-конвейер (стадии по порядку, детально)

Полный pipeline: `services/pipeline.py:run_pipeline` → 6 фаз. LLM-«мозг» — в фазе **analyze** (`services/pipeline_stages/analysis.py:run_analysis_stage`). До analyze: ingest (probe → proxy → transcribe → translate → silence_cut).

### Общие preamble-стадии (выполняются во ВСЕХ narrative-режимах)
Перед ветвлением по режиму analysis.py всегда делает:
1. **Chunking** — `services/chunker.py:chunk_transcript` (token-based sliding window, tiktoken) или `services/semantic_chunker.py:semantic_chunk_transcript` (embedding-based boundaries, cosine local minima).
2. **Compression** (`services/compression.py:compress_chunks`, analysis.py:195) — Flash-Lite, **параллельно** (`asyncio.Semaphore(llm_max_concurrency)` + `asyncio.gather`). Промпт `compression`. Fallback `_fallback_chunk`.
3. **Canvas builder** (`services/canvas_builder.py:build_canvas`, analysis.py:203) — один Pro-вызов, промпт `canvas_builder`. Строит ProjectCanvas (themes/motifs/candidate_moments/tone_map/central_theme).
4. **Canvas embedding** (`canvas_embedder.py:embed_canvas_moments`).

Затем dispatch по `PerformanceSettings.narrative_mode` (analysis.py:242, 265).

### Режим A — `bottom_up` (default, legacy 9-stage extraction)
Промпт-конвейер «Манифест живого кадра 2026» (`prompts.py:_OPUSCLIP_MANIFESTO`) вшит в system всех вызовов.

1. **Preference memory** (`preference_memory.py:load_liked_anchors_text`, analysis.py:293) — подтягивает лайкнутые рилсы прошлых job как anchor-примеры (cosine top-k или top_by_date). Не LLM.
2. **Extraction — 6 агентов × N chunks** (`services/agents/orchestrator.py:orchestrate_extraction`, analysis.py:315). **Главный параллелизм.** Flash-Lite. Wave-execution:
   - Wave 1 (reaction): `hook_hunter`, `emotional_peak_finder`, `humor_specialist`.
   - Барьер → детерминистический `build_coverage_summary` между волнами.
   - Wave 2 (meaning): `dramatic_irony_scanner`, `thesis_extractor`, `motif_tracker`.
   - Промпты `hook_hunter`/`emotional_peak_finder`/`humor_specialist`/`dramatic_irony_scanner`/`thesis_extractor`/`motif_tracker`. Per-agent Gemini context cache (TTL 1800s).
3. **Reduce + rank** (`services/reducer.py:reduce_and_rank`, analysis.py:346) — Flash + hybrid dedup (Jaccard + embedding cosine). Промпт `reduce_rank`. Опц. ensemble судей (N параллельных temperatures + median + veto, `_run_ensemble_reduce`). Fallback `_fallback_ranked_evidence`.
4. **Cross-chunk coherence reducer** (`services/cross_chunk_reducer.py:apply_cross_chunk_coherence`, analysis.py:367) — Flash-Lite, вырезает противоречия между chunks. Опц. (`cross_chunk_reducer_enabled`).
5. **Story doctor** (`services/story_doctor.py:compose_story_script`, analysis.py:403) — Pro, строит 3-act arc + book-end symmetry. Промпты `story_doctor` / `story_doctor_travel`. Обёрнут в `_compose_with_rhythm_loop` (critique-loop с rhythm_check).
6. **Rhythm check** (`services/rhythm_check.py:check_rhythm`) — Flash + heuristic middle-sag. Промпт `rhythm_check`. Fallback `_heuristic_rhythm_report`.
7. **Visual validator** (opt-in, Moondream) — только если vision enabled.
8. **Variants generator** (`services/variants_generator.py:generate_variants`, analysis.py:450) — Pro, 4 формата. Промпт `variants_generator`. Fallback `_fallback_variants` если toggle off.
9. **Multi-arc builder** (opt-in, `multi_arc_enabled`, analysis.py:483) — `services/multi_arc_builder.py:build_arcs_per_moment`. Per-candidate-moment arcs, **параллельно** (`Semaphore(parallel_max)` + `gather`). Multi-angle для видео >40мин (window scales 0.7×/1.5×).
10. **Compose reels** (`reels_composer.py:compose_reels`, analysis.py:530) — sync, target N + uniqueness filter.
11. **Coherence validator** (`services/coherence_validator.py:validate_coherence`, analysis.py:557) — Flash-Lite, проверка hook/body/payoff = одна мысль. Режимы off/reject/resort. Промпт `coherence_check`. **Параллельно** (`gather`).
12. **Closure validator** (`services/closure_validator.py:validate_closures`, analysis.py:575) — Flash-Lite, semantic tail check + extension к ASR sentence boundary. Промпт `closure_check`. **Параллельно** (`gather`).
13. **Cover selector** (opt-in, Moondream), **per-reel scoring** (`_populate_reel_scoring` + `trend_lexicons.compute_trend_score`), stats, artifacts.

→ **~13 LLM-стадий** в bottom_up (из них 6 extraction-агентов = одна стадия с массовым параллелизмом).

### Режим B — `chaptered` / `top_down` (`narrative/orchestrator.py:orchestrate_top_down`)
Phase 1-6, помечен автором как «broken per-chapter», сохранён для отката. Skips extraction/reducer/story_doctor/variants/composer/validators. 6 стадий:
1. `chapter_builder.build_chapters` — chaptering (промпт `chapter_boundary_scorer`).
2. `hook_detector.detect_hooks` — **параллельно per chapter** (промпт `hook_detector`).
3. `arc_finder.find_arcs` — Flash per chapter + Pro fallback (промпт `narrative_arc_finder`).
4. `boundary_extender.extend_boundaries` — детерминистический.
5. `cross_chapter_ranker.rank_and_select` — greedy + diversity + novelty (embedding cosine, Jaccard fallback).
6. ReelCandidate → ReelPlan (1-to-1, без padding).

### Режим C — `map_reduce` (`narrative/map_reduce_orchestrator.py:orchestrate_map_reduce`)
Phase 8, OpusClip-parity, production target. 5 стадий:
1. **Global context** (`global_context_builder.build_global_context`) — 1 Flash-Lite вызов (промпт `global_context_builder`). Fallback на canvas.central_theme.
2. **Chunk scoring (MAP)** (`chunk_scorer.score_chunks`) — **массовый параллелизм** (`Semaphore(narrative_chunk_parallel_max)` + `gather`), chunks по `narrative_chunk_size_chars` с overlap. Промпт `chunk_scorer`. Каждый chunk → `RawClipCandidate[]` + `ChunkDiagnostic`.
3. **Reduce (REDUCE)** (`clip_reducer.reduce_and_rank`) — deterministic temporal dedup + Jaccard dedup → 1 LLM curation/rank вызов (промпт `clip_reducer`).
4. `boundary_extender.extend_boundaries` (детерминистический).
5. ExtendedArc → ReelPlan. Density target = duration_min / 2 (если user target=0), cap 3–300.

### Режим D — `viral_2026` (`services/viral_arc_builder.py:build_viral_arcs`, analysis.py:867)
Простой OpusClip-style. Skips extraction/reducer/story_doctor/variants. Стадии:
1. `_build_chunks` (chunking с overlap).
2. **Parallel Flash-Lite** `_score_chunk` per chunk (`Semaphore(_MAX_CONCURRENCY)` + `gather`). Промпт `viral_2026`. Multi-segment рилсы.
3. `_dedupe` (temporal IoU) → ReelPlan, sort by composite_score.

---

## Режимы повествования

`PerformanceSettings.narrative_mode` ∈ **4 значения**:

| Mode | Orchestrator | Стадий | Суть | LLM density |
|---|---|---|---|---|
| `bottom_up` (default) | analysis.py inline | ~13 | Полный Kartoziya: 6 extraction-агентов → reduce → story_doctor 3-act → variants → composer + 2 validator'а. Самый дорогой, самый «режиссёрский». | Десятки вызовов |
| `chaptered` (top_down) | `orchestrate_top_down` | 6 | Per-chapter: chapters → hooks → arcs → rank. Помечен как broken, для отката. | Per-chapter |
| `map_reduce` | `orchestrate_map_reduce` | 5 | OpusClip-parity: global ctx (1) → parallel chunk-score (N) → reducer (1). Production target, density-based count. | 1 + N + 1 |
| `viral_2026` | `build_viral_arcs` | 3 | Простейший: chunk → parallel score → dedup. 1 LLM call / 20K chunk. | N |

Bottom_up и chaptered/map_reduce различаются философией: bottom_up собирает «снизу вверх» через evidence-агентов и режиссирует 3-act arc; map_reduce/viral режут «сверху вниз» целостные клипы из chunks (как OpusClip). Только bottom_up прогоняет coherence_validator + closure_validator.

---

## Сервисы (таблица)

| Сервис | Файл:строка | Назначение | Вход → Выход | Tier/Provider |
|---|---|---|---|---|
| llm_client facade | `llm_client.py:37,58` | `build_llm` / `build_llm_for_tier` | provider/tier → LLMClient | — |
| tier_resolver | `llm_clients/tier_resolver.py:55` | tier→model, all-Lite constraint | Settings → dict[tier,model] | — |
| provider registry | `llm_providers/registry.py` | hot-plug провайдеров | name → factory | — |
| GeminiClient | `llm_clients/gemini.py:35` | Gemini SDK + context caching | system/user → LLMResponse | gemini |
| GLMClient | `llm_clients/zhipu.py` | GLM-5.1 + concurrency gate | — | zhipu |
| ClaudeClient | `llm_clients/claude.py:32` | Anthropic SDK | — | anthropic (НЕ вызывается) |
| OpenAIClient | `llm_clients/openai.py:31` | OpenAI SDK | — | openai (НЕ вызывается) |
| rate_limiter | `rate_limiter.py` | token-bucket RPM, zhipu sem | — | gemini+zhipu |
| chunker | `chunker.py:81` | token sliding-window | transcript → chunks | — |
| semantic_chunker | `semantic_chunker.py:61` | embedding-boundary chunks | transcript → chunks | embeddings |
| compression | `compression.py:61` | per-chunk summary (parallel) | chunks → CompressedChunk[] | flash_lite |
| extraction orchestrator | `agents/orchestrator.py:65` | 6 агентов × N chunks, 2 волны | chunks+canvas → ExtractionResult | flash_lite |
| reducer | `reducer.py:107` | dedup + rank + ensemble | evidence → RankedEvidence | flash |
| cross_chunk_reducer | `cross_chunk_reducer.py:101` | вырезать противоречия | ranked → ranked | flash_lite |
| story_doctor | `story_doctor.py:62` | 3-act arc + book-end | ranked → StoryScript | pro |
| rhythm_check | `rhythm_check.py:42` | pacing/middle-sag | script → RhythmReport | flash |
| variants_generator | `variants_generator.py:48` | 4 формата | script → StoryVariants | pro |
| multi_arc_builder | `multi_arc_builder.py:158` | arc per moment (parallel) | canvas+ranked → StoryScript[] | (per-arc) |
| coherence_validator | `coherence_validator.py:75` | hook↔payoff связность | analysis → analysis | flash_lite |
| closure_validator | `closure_validator.py:98` | semantic tail check | analysis → analysis | flash_lite |
| viral_arc_builder | `viral_arc_builder.py:403` | viral_2026 mode | transcript → ReelPlan[] | flash_lite (Gemini-only, см. находки) |
| punchline_detector | `punchline_detector.py:69` | детект панчлайн-моментов | — | без LLM (sync эвристика) |
| preference_memory | `preference_memory.py:59` | лайкнутые anchors | job history → text | embeddings |
| trend_lexicons | `trend_lexicons.py:75` | lexical trend-score 0-1 | text+profile → float | без LLM |
| auto_config_advisor | `auto_config_advisor.py:119` | heuristic auto-config | AudioProfile → AutoConfig | без LLM |
| auto_config_llm_fallback | `auto_config_llm_fallback.py:92` | LLM narrative advise | payload → overrides | build_llm |
| narrative/orchestrator | `narrative/orchestrator.py:47` | chaptered mode | transcript → AnalysisResult | mixed |
| narrative/map_reduce_orch | `narrative/map_reduce_orchestrator.py:63` | map_reduce mode | transcript → AnalysisResult | flash_lite |
| narrative/chunk_scorer | `narrative/chunk_scorer.py:200` | MAP parallel scoring | transcript+ctx → RawClipCandidate[] | flash_lite |
| narrative/clip_reducer | `narrative/clip_reducer.py:67` | REDUCE dedup+curate | candidates → final | (per impl) |
| narrative/global_context_builder | `narrative/global_context_builder.py:58` | 1-call global ctx | transcript → GlobalContext | flash_lite |
| narrative/chapter_builder | `narrative/chapter_builder.py` | chaptering | transcript → Chapter[] | mixed |
| narrative/hook_detector | `narrative/hook_detector.py` | hooks per chapter (parallel) | chapters → hooks | flash |
| narrative/arc_finder | `narrative/arc_finder.py` | arcs (Flash + Pro fallback) | chapters+hooks → NarrativeArc[] | flash/pro |
| narrative/boundary_extender | `narrative/boundary_extender.py` | extend к natural closure | arcs → ExtendedArc[] | детерминистич. |
| narrative/cross_chapter_ranker | `narrative/cross_chapter_ranker.py` | greedy+diversity+novelty | extended → ReelCandidate[] | embeddings |
| prompts | `prompts.py:40` | PromptKey enum + манифест + builders | — | — |
| prompt_store | `prompt_store.py:50` | versioned seed/upsert в БД | DEFAULT_PROMPTS → DB | — |

---

## Concurrency / rate-limiting

**Rate-limiting** (`rate_limiter.py`):
- `get_gemini_rate_limiter()` — token-bucket, default `gemini_rate_limit_rpm` (60 RPM), shared singleton (`lru_cache`).
- `get_zhipu_rate_limiter()` — отдельный bucket (Coding Plan ~5 RPM).
- `get_zhipu_concurrency_gate()` — `Semaphore(zhipu_max_concurrency)`, для GLM concurrency=1 (иначе 429 code 1302).

**Параллелизм (asyncio.gather + Semaphore)** найден в:
- `agents/orchestrator.py:151,197,214,293,306` — extraction wave1/wave2/legacy/cache create/delete. Sem = `llm_max_concurrency`. **Главная точка нагрузки** (6 агентов × N chunks).
- `compression.py:77,110` — Sem `llm_max_concurrency`.
- `reducer.py:408` — ensemble (N temperatures).
- `coherence_validator.py:133`, `closure_validator.py:169` — per-reel параллельно.
- `narrative/chunk_scorer.py:247,263` — MAP phase, Sem `narrative_chunk_parallel_max`.
- `narrative/hook_detector.py` — per chapter.
- `multi_arc_builder.py:205,220` — per moment, Sem `parallel_max`.
- `viral_arc_builder.py:430,442` — per chunk, Sem `_MAX_CONCURRENCY`.

Все потоки идут через общий Gemini token-bucket → глобальный RPM-кап соблюдается даже при множестве gather.

---

## Подозрения на заглушки

1. **ClaudeClient / OpenAIClient — реализованы, но мёртвый код в pipeline.** `complete_json` имплементирован реально (claude.py:32, openai.py:31), провайдеры зарегистрированы, но ни одна narrative-стадия их не выбирает — все вызовы идут `build_llm_for_tier(..., provider_override ∈ {None→gemini, "zhipu"})`. Anthropic/OpenAI достижимы лишь через прямой `build_llm()` (translator, auto_config_llm_fallback). НЕ заглушка по реализации, но в narrative-мозге не задействованы.
2. **`viral_2026` игнорирует выбор провайдера.** `viral_arc_builder.py:428` вызывает `build_llm_for_tier("flash_lite", settings)` **без `provider_override`** → всегда Gemini, даже если UI переключён на zhipu. Все остальные стадии прокидывают `pipeline_provider`. Похоже на баг/недосмотр, а не заглушку.
3. **Tier matrix — «pro»/«flash» это фикция.** Все три tier физически резолвятся на Flash-Lite (tier_resolver.py). story_doctor/canvas/variants просят `pro`, но получают Lite-модель. Это by-design user-constraint (дешевизна), но «Pro analytics» в docstring'ах вводит в заблуждение — реального Pro-инференса нет.
4. **`narrative_mode="chaptered"` сам автор пометил «broken per-chapter top-down»** (map_reduce_orchestrator.py:18). Код исполняется, но автор не считает его корректным — фактически legacy/dead-ветка, оставленная для отката.
5. **Fallback'ы могут маскировать сбои LLM.** Многие стадии при провале молча отдают детерминистический fallback (`_fallback_chunk`, `_fallback_ranked_evidence`, `_fallback_script`, `_fallback_variants`, `_heuristic_rhythm_report`). Не заглушки, но при тихих провалах LLM качество деградирует без явной ошибки — стоит проверить логирование failure_reason.

Явных return-fake/NotImplementedError/TODO-stub в narrative-сервисах НЕ найдено. `trend_lexicons` (заменил placeholder `trend_pct=70`) и `auto_config_advisor` — полноценные детерминистические реализации.

---

## Открытые вопросы

1. **Какой narrative_mode default в проде?** Код default = `bottom_up`, но docstring map_reduce называет его «production target». Нужно подтвердить значение в БД/runtime_settings.
2. **viral_2026 Gemini-only намеренно?** Если zhipu-провайдер выбран в UI, viral-режим всё равно жжёт Gemini-квоту. Баг или ограничение?
3. **Anthropic/OpenAI провайдеры — наследие или план?** Зарегистрированы и реализованы, но недостижимы из narrative-пайплайна. Удалять или подключать к UI-выбору? (Memory MEMORY.md фиксирует «videomaker LLM-стек = только Gemini» — возможно claude/openai мертвы намеренно.)
4. **chaptered-режим: удалять?** Помечен broken, дублирует map_reduce. Держится только для отката — есть ли он ещё нужен?
5. **Pro-tier naming.** Стоит ли переименовать tier'ы, раз все = Lite, чтобы не вводить в заблуждение будущих читателей?
6. **`semantic_chunker` vs `chunker`** — какой реально используется в каждом режиме? (нужно проверить call-sites — bottom_up берёт один, map_reduce строит свои chunks внутри chunk_scorer.)
