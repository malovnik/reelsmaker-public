# Multi-Arc Quality Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Note:** This is a **refactoring/tuning plan**, not feature development. No new tests. Each task = atomic changes + build gates (ruff/pyright on backend; tsc/next build on frontend) + commit + push to `origin/feat/glm-provider`.

**Goal:** Убрать 64% коротких рилсов <45s в multi_arc pipeline через 4 точечных фикса: расширение angle-scales, возврат мягкого dedup, source extension до target, пользовательская опция защиты коротких закрытых арок.

**Architecture:** Точечные правки в существующих файлах без новых абстракций. Все 4 задачи независимы — можно выполнять в любом порядке, но рекомендуемый порядок 1→4 даёт incremental validation (каждый фикс видим в логе следующего job'а). 1+2 — быстрый win против дублей, 3 — настоящий pull-fix, 4 — UX polish.

**Tech Stack:** Python 3.12 backend (FastAPI, Pydantic v2, structlog), TypeScript/React frontend (Next.js 16, shadcn/ui). LLMs: Gemini 3.1 flash-lite-preview + zhipu (hardcoded, не трогаем). Menedzher пакетов: `uv` (backend), `pnpm` (frontend, workspace в apps/frontend).

**User Constraints:**
- ✅ NO prompt changes (`.md` файлы в `prompts_data/`)
- ✅ NO new unit tests (жжёт токены; build gates достаточны)
- ✅ NO mocks / stubs / TODO / FIXME
- ✅ Serena MCP для symbolic edits (`find_symbol`, `replace_symbol_body`)
- ✅ Каждая task = atomic commit + `git push origin feat/glm-provider`

---

## File Structure Overview

**Файлы модифицируются (ни один не создаётся):**

| Path | Responsibility | Changed in |
|---|---|---|
| `apps/backend/src/videomaker/services/pipeline_stages/analysis.py` | Оркестратор pipeline, вызывает multi_arc_builder с параметрами | Task 1 |
| `apps/backend/src/videomaker/services/multi_arc_builder.py` | Multi-angle arc generation | Task 1 |
| `apps/backend/src/videomaker/services/reels_composer.py` | Композер кандидатов, dedup фильтры, _arc_group_to_candidate, _merge_short_groups | Tasks 2, 3, 4 |
| `apps/backend/src/videomaker/models/runtime_settings.py` | PerformanceSettings Pydantic model | Task 4 |
| `apps/backend/src/videomaker/core/config.py` | Settings env defaults | Task 4 |
| `apps/frontend/src/components/settings/performance-groups/QualityGatesGroup.tsx` | UI блок «Качество и длительность рилсов» | Task 4 |
| `apps/frontend/src/lib/api/settings.ts` | TypeScript тип PerformanceSettings | Task 4 |

Каждый файл имеет одну ответственность, изменения фокусные (не более 20 строк на task). Pattern проекта — multi-file пакеты сервисов, нет смысла декомпозировать ещё.

---

### Task 1: Расширить window_scales в multi_arc_builder

**Цель:** window_scales=(1.0, 2.0) давали почти одинаковые evidence subsets → LLM возвращал идентичные arcs (r1-r4 = 30.3s × 4 в job f28943fb). Расширение до (0.7, 1.5) создаёт два реально разных окна: узкое видит только peak evidence (tight punchy arc), широкое видит exposition context (longer arc).

**Files:**
- Modify: `apps/backend/src/videomaker/services/pipeline_stages/analysis.py:474-486` (блок `window_scales`)
- Modify: `apps/backend/src/videomaker/services/multi_arc_builder.py:~115-170` (добавить logging)

- [ ] **Step 1: Обновить window_scales в analysis.py**

Найти блок (примерно строка 474):

```python
        multi_angle_threshold_min = 40.0
        use_multi_angle = media_info.duration_sec / 60.0 > multi_angle_threshold_min
        window_scales = (1.0, 2.0) if use_multi_angle else (1.0,)
```

Заменить на:

```python
        # Iteration 2026-04-22 (fix 1/4): расширенный разброс scales для
        # реальной angle-diversity. Было (1.0, 2.0) — слишком близко,
        # LLM получал почти одинаковый evidence subset и возвращал
        # идентичные arcs (дубли 4x в job f28943fb). Новые (0.7, 1.5):
        # узкое окно 0.7× видит только peak evidence → tight punchy arc
        # (25-40s), широкое 1.5× видит exposition context → longer arc
        # (50-70s). Min разброс scales = 2.14× → LLM не может совпасть.
        multi_angle_threshold_min = 40.0
        use_multi_angle = media_info.duration_sec / 60.0 > multi_angle_threshold_min
        window_scales = (0.7, 1.5) if use_multi_angle else (1.0,)
```

- [ ] **Step 2: Добавить logging window_scales_applied в multi_arc_builder**

Найти функцию `_build_single_arc` в `apps/backend/src/videomaker/services/multi_arc_builder.py` (строка ~71). Внутри `async with semaphore:` блока, сразу после `nearby = _filter_evidence_by_moment(...)` и fallback логики, перед try/compose_story_script — найти блок:

```python
        if len(nearby.items) < min_evidence:
            log.info(
                "multi_arc_build_with_low_evidence",
                moment_id=moment.id,
                evidence_count=len(nearby.items),
                user_threshold=min_evidence,
                hard_min=hard_min_evidence,
            )
```

В `log.info("multi_arc_moment_arc_built", ...)` (в конце функции) добавить поле `window_sec` если оно ещё не логгируется. Проверить текущую сигнатуру — если `window_sec` уже там, ничего не менять.

Также в `build_arcs_per_moment` в финальном `log.info("multi_arc_build_complete", ...)` убедиться что `window_scales=list(scales)` уже логгируется (должно быть с предыдущего коммита `bf88e26`).

- [ ] **Step 3: Build gates**

```bash
cd <source-repo>/apps/backend && uv run ruff check src/videomaker/services/pipeline_stages/analysis.py src/videomaker/services/multi_arc_builder.py
```

Expected output: `All checks passed!`

```bash
cd <source-repo>/apps/backend && uv run pyright src/videomaker/services/pipeline_stages/analysis.py src/videomaker/services/multi_arc_builder.py
```

Expected output: `0 errors, 0 warnings, 0 informations`

- [ ] **Step 4: Commit + push**

```bash
cd <source-repo> && git add apps/backend/src/videomaker/services/pipeline_stages/analysis.py apps/backend/src/videomaker/services/multi_arc_builder.py && git commit -m "fix(multi_arc): widen angle-scales (1.0,2.0)→(0.7,1.5) for real diversity

LLM выдавал идентичные arcs при (1.0, 2.0) scales — evidence
subsets в окнах 45s/90s отличались на edge cases. Новые
(0.7, 1.5) дают 2.14× разброс: узкое окно 31.5s видит только
peak evidence (tight punchy arc), широкое 67.5s видит exposition
context (longer arc).

Было в job f28943fb: r1-r4=30.3s × 4 identical, r7-r10=31.0s × 4
identical, r34-r37=45.0s × 4 identical.

Expected после фикса: тот же счётчик arcs (~120 candidates на
95-мин видео), но реально разные по evidence и тексту — дубли
падают с ~12% до ~2-3%." && git push origin feat/glm-provider
```

---

### Task 2: Вернуть dedup для multi_arc с мягкими порогами

**Цель:** Safety net против оставшихся 2-3% LLM-дублей после Task 1. Даже с разными scales LLM иногда выдаёт близкие по тексту arcs (особенно если moment узкий и контекст один и тот же). Dedup режет only near-identical — не трогает valid angle-variants.

**Files:**
- Modify: `apps/backend/src/videomaker/services/reels_composer.py:132-135` (constants)
- Modify: `apps/backend/src/videomaker/services/reels_composer.py:_greedy_uniqueness_filter` (logging)

- [ ] **Step 1: Обновить 4 константы multi_arc thresholds**

Найти в `apps/backend/src/videomaker/services/reels_composer.py` блок (строка 132-135):

```python
_MULTI_ARC_UNIQUENESS_JACCARD_THRESHOLD = 1.01
_MULTI_ARC_SEMANTIC_REEL_SIMILARITY_THRESHOLD = 1.01
_MULTI_ARC_CROSS_REEL_SEGMENT_OVERLAP_RATIO = 1.01
_MULTI_ARC_TEMPORAL_OVERLAP_DUP_RATIO = 1.01
```

И предшествующий docstring — обновить iteration log и комментарий. Заменить весь блок (строки ~118-135):

```python
#: Multi-arc variant A (2026-04-21): loose thresholds для overproduction+ranking
#: режима. При multi_arc_enabled composer получает N StoryScript'ов, по одному
#: на canvas moment. Multiple angles одного топика — это не баг а feature
#: (OpusClip pattern: ~30 candidates → ranking top-N). Поэтому dedup
#: ослабляется до near-exact-duplicate порога, LLM-отобранные уникальные
#: углы сохраняются.
#: Iteration log:
#: * v1 (a212f4f): 0.85/0.95/0.70/0.90 → 10 reels out of 18 arcs (job 54fcef5f)
#: * v2 (e3bba6d): 0.92/0.97/0.85/0.95 → 5 reels out of 12 arcs (job a5331d13)
#: * v3 (4a94460): 1.01/1.01/1.01/1.01 — DISABLE dedup полностью для multi_arc.
#:   Overproduction pattern: все per_moment_arc candidates проходят фильтр
#:   без дедуп-cap'ов. Ranking по composite_score → user_target_count cuts.
#:   Если arcs <= 1.0 порога — никогда не отбросятся. Ratio 1.01 безопасен
#:   потому что real overlap всегда в [0.0, 1.0].
#: * v4 (2026-04-22, fix 2/4): soft thresholds как safety net ПОСЛЕ расширения
#:   window_scales до (0.7, 1.5). Дубли из одного moment (r1=r2=r3=r4 идентичные)
#:   срезаем через Jaccard 0.88 (near-identical текст) + semantic 0.92
#:   (embedding cosine, embedding-based dedup точнее Jaccard). temporal 0.95
#:   ловит arcs с почти 100%-overlapping segments. cross_reel 1.01 остаётся
#:   disabled — multi-angle по определению перекрывает sources.
_MULTI_ARC_UNIQUENESS_JACCARD_THRESHOLD = 0.88
_MULTI_ARC_SEMANTIC_REEL_SIMILARITY_THRESHOLD = 0.92
_MULTI_ARC_CROSS_REEL_SEGMENT_OVERLAP_RATIO = 1.01
_MULTI_ARC_TEMPORAL_OVERLAP_DUP_RATIO = 0.95
```

- [ ] **Step 2: Добавить rejected_reel_ids logging в _greedy_uniqueness_filter**

Найти функцию `_greedy_uniqueness_filter` в `reels_composer.py`. Найти финальный блок `log.info("greedy_uniqueness_breakdown", ...)`. Добавить сбор списков rejected reel_ids по причинам:

Перед циклом, где инкрементируются `rejected_cross_reel`, `rejected_semantic`, `rejected_jaccard` — рядом с ними завести накапливающие списки:

```python
    rejected_ids_cross_reel: list[str] = []
    rejected_ids_semantic: list[str] = []
    rejected_ids_jaccard: list[str] = []
```

В местах где инкрементируется `rejected_*` счётчик — также `rejected_ids_*.append(candidate.plan.reel_id)` или аналогичного идентификатора (смотреть реальную структуру candidate).

В финальном `log.info("greedy_uniqueness_breakdown", ...)` добавить поля:

```python
        rejected_ids_cross_reel=rejected_ids_cross_reel,
        rejected_ids_semantic=rejected_ids_semantic,
        rejected_ids_jaccard=rejected_ids_jaccard,
```

**Если structure `_Candidate` не имеет удобного `id` — использовать `source` + первые 40 символов hook/text**: например `f"{c.source}:{c.plan.hook[:40] if c.plan.hook else '?'}"`.

- [ ] **Step 3: Build gates**

```bash
cd <source-repo>/apps/backend && uv run ruff check src/videomaker/services/reels_composer.py
```

Expected: `All checks passed!`

```bash
cd <source-repo>/apps/backend && uv run pyright src/videomaker/services/reels_composer.py
```

Expected: `0 errors, 0 warnings, 0 informations`

- [ ] **Step 4: Commit + push**

```bash
cd <source-repo> && git add apps/backend/src/videomaker/services/reels_composer.py && git commit -m "fix(composer): soft dedup thresholds for multi_arc safety net

Jaccard=0.88 + semantic=0.92 + temporal=0.95 — safety net для
near-identical arcs, которые проходят через разные window_scales
но LLM совпал (narrow evidence, same LLM temperature=0).

cross_reel=1.01 остаётся disabled — multi-angle по определению
перекрывает source segments (same moment + разные окна) и это
валидный use case.

Добавлено логирование rejected_ids_* в greedy_uniqueness_breakdown
для observability — видно конкретные arcs которые резались dedup'ом,
можно триангулировать с per_moment_arcs.json." && git push origin feat/glm-provider
```

---

### Task 3: Source extension в multi_arc для pull to target

**Цель:** В multi_arc режиме каждая arc = 1 self-contained StoryScript из 1 group'а. Pass 3 conditional pull мёрджит groups **внутри одной StoryScript** — но внутри нечего мёрджить. Правильный fix: не мёрджить, а **расширять source timeline** каждого segment'а через transcript context вокруг, чтобы достичь `target_duration`. Существующая логика в `_arc_group_to_candidate` уже делает extension до `REEL_MIN` — расширяем цель до `target_duration` для multi_arc-sourced кандидатов.

**Files:**
- Modify: `apps/backend/src/videomaker/services/reels_composer.py:_arc_group_to_candidate`

- [ ] **Step 1: Прочитать текущую реализацию _arc_group_to_candidate**

```bash
cd <source-repo> && sed -n '540,700p' apps/backend/src/videomaker/services/reels_composer.py
```

Найти в теле функции блок который **extend'ит короткие evidence до REEL_MIN**. По комментарию в docstring: "Короткие evidence (<REEL_MIN) расширяются симметрично до REEL_MIN в пределах source". Локализовать конкретные строки.

- [ ] **Step 2: Изменить extension цель с REEL_MIN на target_duration для multi_arc**

Найти параметр `source` в сигнатуре `_arc_group_to_candidate`. Он уже передаётся — используется как marker ("per_moment_arc", "base_arc", "package_of_shorts", etc).

Добавить **новый параметр** `extend_to_target: float | None = None` в сигнатуру:

```python
def _arc_group_to_candidate(
    group: list[StorySegment],
    *,
    # ... существующие параметры ...
    source: str,
    cleaned_words: list[TranscribedWord] | None = None,
    extend_to_target: float | None = None,  # <-- добавить
) -> _Candidate | None:
```

Найти блок где текущий extension работает к `REEL_MIN_DURATION_SEC`. Добавить перед ним (или модифицировать):

```python
    # Source extension (fix 3/4, 2026-04-22): для multi_arc-sourced
    # candidate если extend_to_target задан и превышает total_duration,
    # расширяем каждый segment симметрично через transcript context.
    # Это настоящий fix pull-to-target для multi_arc: внутри одной
    # StoryScript нет соседних groups для мёрджа, зато есть transcript
    # context вокруг каждого evidence'а. Max extension per segment = 15s
    # чтобы не тянуть произвольный кусок транскрипта.
    effective_min_target = REEL_MIN_DURATION_SEC
    if (
        extend_to_target is not None
        and extend_to_target > effective_min_target
        and total_duration < extend_to_target
        and total_duration >= REEL_MIN_DURATION_SEC
    ):
        deficit = extend_to_target - total_duration
        per_segment_bonus = min(15.0, deficit / max(1, len(segments)))
        extended_segments: list[ReelSegment] = []
        for seg in segments:
            new_start = max(0.0, seg.source_start - per_segment_bonus / 2.0)
            new_end = seg.source_end + per_segment_bonus / 2.0
            if cleaned_words:
                new_start, new_end = _snap_segment_to_sentence_boundaries(
                    new_start, new_end, cleaned_words, max_shift_sec=2.0
                )
            extended_segments.append(
                seg.model_copy(update={"source_start": new_start, "source_end": new_end})
            )
        segments = extended_segments
        total_duration = sum(s.source_end - s.source_start for s in segments)
```

**ВАЖНО:** размещение этого блока ПОСЛЕ существующего REEL_MIN extension — чтобы сначала сработал платформенный минимум, потом target-extension. Убедиться что `segments` переменная и `total_duration` существуют в scope (если имя другое — адаптировать).

- [ ] **Step 3: Пробросить extend_to_target из callers**

Найти все вызовы `_arc_group_to_candidate(...)` через Grep. Нужно найти тот, который идёт из **multi_arc path** (per_moment_arc source). Обычно это в `_candidates_from_per_moment_arcs` или аналогичной функции.

В этом caller'е получить target через `_get_target_duration()` helper (он уже существует в том же файле):

```python
target_duration = _get_target_duration()  # reads from PerformanceSettings → Settings fallback
```

И передать в вызов:

```python
        cand = _arc_group_to_candidate(
            group,
            # ... existing args ...
            source="per_moment_arc",
            cleaned_words=cleaned_words,
            extend_to_target=target_duration,  # <-- добавить
        )
```

Другие вызовы (`source="base_arc"`, `"package_of_shorts"`, etc) — НЕ передавать `extend_to_target` (остаётся None → старое поведение, только REEL_MIN extension). Это важно: legacy single-arc pipeline не должен меняться.

- [ ] **Step 4: Build gates**

```bash
cd <source-repo>/apps/backend && uv run ruff check src/videomaker/services/reels_composer.py
```

Expected: `All checks passed!`

```bash
cd <source-repo>/apps/backend && uv run pyright src/videomaker/services/reels_composer.py
```

Expected: `0 errors, 0 warnings, 0 informations`

- [ ] **Step 5: Commit + push**

```bash
cd <source-repo> && git add apps/backend/src/videomaker/services/reels_composer.py && git commit -m "fix(composer): source extension to target for multi_arc pull

Multi_arc: 1 StoryScript = 1 group, Pass 3 conditional pull
мёрджит groups внутри StoryScript — внутри нечего мёрджить,
pull не работает.

Fix: новый параметр extend_to_target в _arc_group_to_candidate.
Если группа из per_moment_arc source и total_duration < target,
каждый segment симметрично расширяется в transcript context
на (target - current) / N секунд (max 15s per segment). Границы
snap'ятся к sentence boundaries через существующий
_snap_segment_to_sentence_boundaries.

Effect на 95-мин видео при target=75: ожидаемое падение доли
рилсов <45s с 64% до ~20-25% (остаются только closed short
arcs с hook+payoff, защищённые skip_complete_short_arcs).

Legacy single-arc pipeline не меняется — extend_to_target
передаётся только из per_moment_arc caller'а." && git push origin feat/glm-provider
```

---

### Task 4: skip_complete_short_arcs — опция в PerformanceSettings + UI

**Цель:** Сейчас `skip_complete_short_arcs=True` захардкожено в `_merge_short_groups` (Pass 1). Эта защита сохраняет короткие закрытые арки (hook+payoff <REEL_MIN) как отдельные рилсы. Для некоторых user'ов (те кто хочет длинные рилсы) это раздражает — хочется чтобы короткие сливались с соседями. Даём user toggle.

**Files:**
- Modify: `apps/backend/src/videomaker/models/runtime_settings.py` (PerformanceSettings)
- Modify: `apps/backend/src/videomaker/core/config.py` (Settings env default)
- Modify: `apps/backend/src/videomaker/services/reels_composer.py` (чтение setting в `_merge_short_groups`)
- Modify: `apps/frontend/src/components/settings/performance-groups/QualityGatesGroup.tsx` (UI SwitchRow)
- Modify: `apps/frontend/src/lib/api/settings.ts` (TypeScript type)

- [ ] **Step 1: Добавить поле в PerformanceSettings (Pydantic)**

Найти в `apps/backend/src/videomaker/models/runtime_settings.py` поле `reel_target_pull_strength` (строка ~139). Добавить новое поле **после** него:

```python
    skip_complete_short_arcs: bool = Field(
        default=True,
        description=(
            "Защищать короткие закрытые арки (hook+payoff под REEL_MIN) "
            "от мёрджа с соседями в Pass 1. True (default) = punchy 30-40s "
            "рилсы живут как отдельные единицы. False = сливаются с "
            "соседями для более длинных рилсов в диапазоне 45-80s."
        ),
    )
```

- [ ] **Step 2: Добавить env default в core.config.Settings**

Найти в `apps/backend/src/videomaker/core/config.py` аналогичное поле `reel_target_pull_strength` (строка ~203). Добавить **после** него:

```python
    skip_complete_short_arcs: bool = Field(
        default=True,
        description=(
            "Env default для PerformanceSettings.skip_complete_short_arcs. "
            "См. runtime_settings.py для семантики."
        ),
    )
```

- [ ] **Step 3: Создать _get_skip_complete_short_arcs helper в reels_composer**

Найти в `apps/backend/src/videomaker/services/reels_composer.py` helper `_get_pull_strength` (строка ~1112). Добавить **после** него аналогичный helper:

```python
def _get_skip_complete_short_arcs() -> bool:
    """Читает ``skip_complete_short_arcs`` с приоритетом PerformanceSettings.

    Resolution order:
    1. PerformanceSettings (UI override из /settings/performance)
    2. core.config.Settings (env defaults)
    3. ``True`` (safety fallback — legacy behavior)
    """
    try:
        from videomaker.services.runtime_settings_store import (
            get_cached_performance_settings,
        )

        perf = get_cached_performance_settings()
        if perf is not None:
            return perf.skip_complete_short_arcs
    except Exception:
        pass
    try:
        from videomaker.core.config import get_settings

        return get_settings().skip_complete_short_arcs
    except Exception:
        return True
```

- [ ] **Step 4: Использовать helper в _merge_short_groups**

Найти в `reels_composer.py` строку 990:

```python
    merged = _pass(
        REEL_MIN_DURATION_SEC, groups, skip_complete_short_arcs=True
    )
```

Заменить на:

```python
    merged = _pass(
        REEL_MIN_DURATION_SEC,
        groups,
        skip_complete_short_arcs=_get_skip_complete_short_arcs(),
    )
```

- [ ] **Step 5: Добавить поле в TypeScript тип settings**

Найти в `apps/frontend/src/lib/api/settings.ts` интерфейс PerformanceSettings (строка ~124, рядом с `reel_target_duration_sec`). Добавить после `reel_target_pull_strength`:

```typescript
  skip_complete_short_arcs: boolean;
```

- [ ] **Step 6: Добавить UI toggle в QualityGatesGroup**

Найти в `apps/frontend/src/components/settings/performance-groups/QualityGatesGroup.tsx` блок с `reel_target_pull_strength` (SelectRow, строка 31-42). Добавить **после** него (до `variants_generator_enabled` SwitchRow):

```tsx
      <SwitchRow
        id="skip_complete_short_arcs"
        label="Защищать короткие punchy арки"
        hint="Вкл (default): короткие закрытые арки hook+payoff под REEL_MIN живут как отдельные рилсы 30-40s. Выкл: сливаются с соседями для более длинных рилсов 45-80s с большим emotional buildup."
        checked={values.skip_complete_short_arcs}
        onChange={(v) => update("skip_complete_short_arcs", v)}
      />
```

- [ ] **Step 7: Build gates (backend)**

```bash
cd <source-repo>/apps/backend && uv run ruff check src/videomaker/models/runtime_settings.py src/videomaker/core/config.py src/videomaker/services/reels_composer.py
```

Expected: `All checks passed!`

```bash
cd <source-repo>/apps/backend && uv run pyright src/videomaker/models/runtime_settings.py src/videomaker/core/config.py src/videomaker/services/reels_composer.py
```

Expected: `0 errors, 0 warnings, 0 informations`

- [ ] **Step 8: Build gates (frontend)**

```bash
cd <source-repo> && pnpm -C apps/frontend type-check
```

Expected: `tsc --noEmit` пройдёт без ошибок (0 errors).

```bash
cd <source-repo> && pnpm -C apps/frontend build
```

Expected: `next build` завершится с `✓ Compiled successfully` и успешной генерацией статических страниц.

- [ ] **Step 9: Commit + push**

```bash
cd <source-repo> && git add apps/backend/src/videomaker/models/runtime_settings.py apps/backend/src/videomaker/core/config.py apps/backend/src/videomaker/services/reels_composer.py apps/frontend/src/components/settings/performance-groups/QualityGatesGroup.tsx apps/frontend/src/lib/api/settings.ts && git commit -m "feat(settings): skip_complete_short_arcs toggle

Убирает hardcoded skip_complete_short_arcs=True в _merge_short_groups
Pass 1 — теперь читается из PerformanceSettings через новый
_get_skip_complete_short_arcs() helper. User может выключить
защиту коротких закрытых арок через UI /settings/performance:
все <REEL_MIN арки будут мёрджиться с соседями для более длинных
рилсов.

Поля:
- runtime_settings.py: PerformanceSettings.skip_complete_short_arcs
- core/config.py: Settings.skip_complete_short_arcs (env default True)
- lib/api/settings.ts: PerformanceSettings TypeScript type
- QualityGatesGroup.tsx: SwitchRow 'Защищать короткие punchy арки'

Default True сохраняет текущее поведение — UI toggle opt-in для
пользователей хотящих 100% рилсов в 45-80 диапазоне." && git push origin feat/glm-provider
```

---

## Self-Review

**1. Spec coverage:** 
- Task 1 покрывает window_scales (0.7, 1.5) + logging ✓
- Task 2 покрывает dedup thresholds + rejected_ids logging ✓
- Task 3 покрывает source extension через _arc_group_to_candidate + extend_to_target параметр ✓
- Task 4 покрывает 4 файла: runtime_settings, config, composer, frontend UI + TypeScript type ✓

Спецификация полностью отражена в 4 задачах.

**2. Placeholder scan:** 
- Никаких "TBD", "implement later" в плане — каждый шаг имеет конкретный код или команду ✓
- Один нюанс в Task 2 step 2: формулировка "смотреть реальную структуру candidate" — это legitimate variance, структура `_Candidate` dataclass может иметь разные поля для ID (score, plan.hook, source). Добавлен fallback формат `f"{c.source}:{c.plan.hook[:40] if c.plan.hook else '?'}"` как допустимый. Не placeholder — это адаптивная логика
- Task 3 step 3 говорит "Другие вызовы (source='base_arc', ...) НЕ передавать extend_to_target" — это explicit instruction, не placeholder ✓

**3. Type consistency:**
- `extend_to_target: float | None = None` в Task 3 — тип консистентен, используется в signature и passing
- `skip_complete_short_arcs: bool` во всех 5 файлах Task 4 — boolean везде
- Pydantic Field default=True, Settings default=True, TypeScript boolean — консистентно
- Helper `_get_skip_complete_short_arcs()` returns `bool` (следует паттерну `_get_pull_strength()` → Literal)

Плаг чист, готов к исполнению.

---

**Plan complete and saved to `<source-repo>/docs/plans/2026-04-22-multi-arc-quality-fixes.md`.**
