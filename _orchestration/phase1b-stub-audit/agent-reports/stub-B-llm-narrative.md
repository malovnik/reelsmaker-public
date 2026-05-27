# Stub-B — LLM Narrative Infrastructure Reality-Check

Audit root: `apps/backend/src/videomaker`
Method: трассировка call-sites (grep + чтение реализаций), сверка декларации в коде/UI с фактическим рантайм-резолвом.

---

## Таблица вердиктов

| # | Объект | Вердикт | Доказательство | Реко |
|---|--------|---------|----------------|------|
| 1 | Tier matrix pro/flash/flash_lite | **FICTION-always-same** (by-design, но врёт в docstrings/UI) | `tier_resolver.py:37-52` — оба профиля `fast`/`legacy` мапят все три tier на Lite | ИСПРАВИТЬ (честный naming + опц. развести) |
| 2 | ClaudeClient / OpenAIClient в narrative | **DEAD-code** (для pipeline) | Используются только в `translator.py:61` и `auto_config_llm_fallback.py:112` через `build_llm()`, и то с захардкоженным `gemini` | ОСТАВИТЬ translator-путь, УДАЛИТЬ из narrative-фасада / признать dead |
| 3 | viral_2026 игнорирует provider | **BUG-ignores-config** | `viral_arc_builder.py:428` `build_llm_for_tier("flash_lite", settings)` без `provider_override`; `analysis.py:867` зовёт `build_viral_arcs(... cfg=cfg)` без провайдера | ИСПРАВИТЬ (S) |
| 4 | chaptered / top_down | **LEGACY-broken** (исполняется, автор пометил broken) | `map_reduce_orchestrator.py:18` "мой broken per-chapter top-down"; достижим из UI через `analysis.py:242` | ИСПРАВИТЬ (скрыть из UI) или УДАЛИТЬ |
| 5 | Per-stage fallback | **SILENT-FALLBACK-masks-error** | `reducer/_fallback_ranked_evidence`, `compression/_fallback_chunk`, `variants/_fallback_variants`, `rhythm/_heuristic_rhythm_report`, `story_doctor/_fallback_script` | ИСПРАВИТЬ (surface failure_reason в stats/UI) |

---

## Детально

### 1. Tier matrix — FICTION-always-same (намеренно, но вводит в заблуждение)

**Трассировка.** `tier_resolver.py:_tier_profiles` (строки 37-52): оба профиля возвращают `lite` (или `_LITE_3_1`) для всех трёх ключей `pro`/`flash`/`flash_lite`. `_resolve_tier_models` (55-81) при любом неизвестном профиле и при cold-cache коерсит к `fast` → тоже all-Lite. Нет ни одной ветки, резолвящей реальную Flash или Pro модель.

**Это намеренно.** Docstring модуля (7-9) явно: "разрешены только Flash-Lite варианты... профили balanced/quality удалены". Совпадает с MEMORY: videomaker LLM-стек дешёвый, Gemini-only.

**Где врёт.** `build_llm_for_tier` docstring (llm_client.py:65-68) описывает `pro = тяжёлая аналитика (Canvas, Story Doctor, Variants)`, `flash = средние`. `analysis.py:120` логирует `build_llm_for_tier("pro", ...).model` как "Pro analytics". Стадии `canvas_builder/story_doctor/variants` зовут `"pro"` (canvas_builder.py:140, story_doctor.py:98, variants_generator.py:62) — но физически получают Lite. **Реального Pro-инференса в пайплайне нет.** Любой текст в UI/доке про "Pro-режиссуру 3-act arc" — это Lite, выдающий себя за Pro.

**План «не для вида».**
- **S:** Переименовать docstrings + лог-метки: убрать "Pro analytics", писать фактическую модель. Риск: ноль.
- **M:** Развести тиры реально — добавить в `_tier_profiles` ветку, где `pro→gemini-2.5-flash`/`flash→...`, прокинуть через `PerformanceSettings.llm_tier_profile` новый профиль `quality`. Риск: рост стоимости/латентности; story_doctor/canvas качество вырастет (это и есть смысл Pro). Нужен бюджетный gate.
- **L:** A/B Lite-vs-Flash на canvas/story_doctor, измерить прирост связности рилсов — иначе развод тиров спекулятивен.

**Реко: ИСПРАВИТЬ** (минимум naming, чтобы перестать врать; развод тиров — отдельным решением user про бюджет).

---

### 2. ClaudeClient / OpenAIClient — DEAD-code в narrative

**Трассировка.** Клиенты реальны (`complete_json` имплементирован). Но единственные `build_llm()` call-sites:
- `translator.py:61` — `build_llm(config.llm_provider, config.llm_model, ...)` — провайдер из конфига перевода (может быть не-gemini, это живой путь).
- `auto_config_llm_fallback.py:112` — `build_llm(_LLM_PROVIDER, _LLM_MODEL)` где `_LLM_PROVIDER="gemini"`, `_LLM_MODEL="gemini-2.5-flash-lite"` захардкожены (строки 45-46).

В narrative-мозге (analysis.py и все services/narrative/*) — **только `build_llm_for_tier`**, а он резолвит `provider_override or "gemini"` либо `"zhipu"`. Anthropic/OpenAI недостижимы из пайплайна вообще.

**Реко:**
- translator-путь **ОСТАВИТЬ** (реально может выбрать провайдера).
- Регистрацию `claude_factory`/`openai_factory` и реэкспорт `ClaudeClient/OpenAIClient` из `llm_client.py` — признать dead для narrative. Если стратегия Gemini-only зафиксирована (MEMORY: да), **УДАЛИТЬ** факторки + реэкспорты, чтобы не создавать иллюзию мультипровайдерности. Риск удаления: S (никто в pipeline не зовёт). Если планируется подключить к UI — оставить, но пометить честно.

---

### 3. viral_2026 игнорирует выбор провайдера — BUG-ignores-config (ПОДТВЕРЖДЁН)

**Трассировка, два уровня дефекта:**
1. `viral_arc_builder.py:428`: `llm = build_llm_for_tier("flash_lite", settings)` — **нет** `provider_override`. Для сравнения, ВСЕ 15+ остальных call-site передают `provider_override=pipeline_provider` (compression.py:75, reducer.py:168, story_doctor.py:98, canvas_builder.py:140, coherence/closure/cross_chunk/rhythm, chunk_scorer, hook_detector, arc_finder, clip_reducer, global_context). viral — единственное исключение. → всегда Gemini.
2. `analysis.py:867`: `build_viral_arcs(cleaned_transcript, cfg=cfg)` — провайдер даже не передаётся в функцию (нет параметра). А `_run_viral_2026_branch` ниже **хардкодит** `AnalysisResult(llm_model="gemini-flash-lite", provider="gemini")` (строки 871-872) и при этом **отдельно** пишет `analysis.stats["user_requested_llm"] = f"{llm_provider}:{llm_model}"` (898).

**Это и есть прямая ложь пользователю.** Если в UI выбран Zhipu/GLM, viral-режим: (а) жжёт Gemini-квоту вопреки выбору, (б) в `analysis_summary.json` пишет `provider: gemini`, но в stats `user_requested_llm: zhipu:...` — рассинхрон, скрывающий что выбор проигнорирован.

**План «не для вида».**
- **S:** Добавить параметр `provider_override` в `build_viral_arcs`, прокинуть из `_run_viral_2026_branch` (`llm_provider` уже доступен в сигнатуре, строка 839), внутри `viral_arc_builder.py:428` передать в `build_llm_for_tier`. Заменить хардкод `provider="gemini"` на фактический. Риск: GLM concurrency=1 семафор — `_MAX_CONCURRENCY` в viral надо гейтить через `get_zhipu_concurrency_gate()` при zhipu, иначе 429 (code 1302). Иначе фикс провайдера = новый баг параллелизма.
- **M:** Юнит smoke — viral с zhipu override резолвит GLM client (build gate, без новых тестов по feedback).

**Реко: ИСПРАВИТЬ** (S+гейт concurrency).

---

### 4. chaptered / top_down — LEGACY-broken

**Трассировка.** `map_reduce_orchestrator.py:18` — авторская метка: `"chaptered" — мой broken per-chapter top-down (Phase 1-6)`. Но он **исполняется**: `analysis.py:242` `if perf_narrative.narrative_mode in {"chaptered", "map_reduce"}: return await _run_top_down_branch(...)`, внутри (`analysis.py:747`) `orchestrate_top_down` вызывается когда `narrative_mode != "map_reduce"`. Значение приходит из `PerformanceSettings.narrative_mode` — т.е. **доступно из UI**. Пользователь может выбрать режим, помеченный автором как сломанный, и получить деградированный результат без предупреждения.

**План.**
- **S:** Убрать `chaptered` из списка валидных значений UI-селектора narrative_mode (или дизейблить с подписью "legacy/broken"). Оставить код для отката за флагом.
- **M:** Если map_reduce полностью покрывает кейс — **УДАЛИТЬ** `orchestrate_top_down` + ветку. Риск: теряется fallback, но дублируется map_reduce.

**Реко: ИСПРАВИТЬ** (скрыть из UI немедленно) → потом решение про УДАЛИТЬ.

---

### 5. Per-stage fallback — SILENT-FALLBACK-masks-error

**Трассировка.** Почти каждая стадия при LLM-провале молча отдаёт детерминистический результат: `_fallback_chunk` (compression), `_fallback_ranked_evidence` (reducer), `_fallback_script` (story_doctor), `_fallback_variants` (variants), `_heuristic_rhythm_report` (rhythm). Это не заглушки — это деградация качества. Опасность: при тихом провале LLM (rate-limit, JSON-parse fail после repair, провайдер недоступен) рилсы строятся эвристикой, а пользователь видит "успех" без индикации, что "режиссёрский мозг" не отработал.

**План «не для вида».**
- **S:** Каждый fallback инкрементит счётчик в `analysis.stats` (`fallback_count`, `failed_stages: [...]`) с `failure_reason`. Surface в UI/analysis_summary.json как warning-бейдж "N стадий деградировали".
- **M:** Порог: если >X% стадий упали в fallback — помечать job как `degraded`, не `success`. Душа: тихое ухудшение надо называть.

**Реко: ИСПРАВИТЬ** (логирование + surface, без удаления fallback — он защищает от полного краха).

---

## ТОП-3 фикции, которые врут пользователю в UI

1. **viral_2026 «уважает выбор провайдера» — ложь.** Выбрал Zhipu в UI → пайплайн молча жжёт Gemini (`viral_arc_builder.py:428` без override), а в артефакте пишет `provider: gemini` при `user_requested_llm: zhipu`. Прямой рассинхрон выбор↔исполнение (`analysis.py:867,871-872,898`).

2. **«Pro analytics / 3-act режиссура на Pro-модели» — ложь.** Tier `pro` для canvas/story_doctor/variants физически = Flash-Lite (`tier_resolver.py:37-52`). UI/доки обещают тяжёлую модель — рантайм всегда отдаёт cheapest Lite. Качество "режиссуры" — это Lite под вывеской Pro.

3. **«narrative_mode: chaptered» выбираемый в UI — broken-ветка.** Автор сам пометил её broken (`map_reduce_orchestrator.py:18`), но она исполняется при выборе из UI (`analysis.py:242`). Пользователь получает деградированный результат, считая это рабочим режимом.

**Бонус (скрытая деградация):** Per-stage fallback'ы превращают тихий LLM-сбой в "успешный" job на эвристике — пользователь не знает, что мозг пайплайна не отработал.
