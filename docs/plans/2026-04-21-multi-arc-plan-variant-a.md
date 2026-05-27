# Variant A: Multi-Arc Architecture — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans или subagent-driven-development.
> **Goal:** переписать flow `canvas → 1 story_doctor arc → composer добирает из evidence singles` на `canvas → N arcs (по одному на candidate_moment) → composer берёт 1 reel per arc`. Каждый финальный рилс получает hook+development+payoff как структурное следствие, не prompt engineering.
>
> **Baseline metrics (до изменений, prod data):**
> - 11-мин видео (c452aadb): 10 reels, 1 (10%) с полным arc, cluster длин 31-40s
> - 95-мин видео (b6b9682e): 48 reels, 2 (4%) с полным arc, 71% в 30-40s
>
> **Target metrics (после):**
> - 11-мин: ≥8 reels, ≥80% с полным arc, длины 30-80s distributed
> - 95-мин: ≥30 reels, ≥80% с полным arc, длины 30-90s distributed

---

## Prerequisites

Этот план **поверх** коммита субагента по model refactoring (в процессе, id a0e44889). Финальный коммит субагента должен:
- Удалить `_FLASH_3` / профили `balanced`, `quality` из `tier_resolver.py`
- Удалить `gemini_pro_model` из `core/config.py`
- Заменить `llm_model=cfg.gemini_pro_model` на `_pro_model_for_messaging(...)` в `analysis.py:464`
- Build gates зелёные

Если субагент вернётся с BLOCKED или DONE_WITH_CONCERNS — **не начинать этот план**, разобраться сначала.

---

## Design decisions (с обоснованиями)

### Decision 1: Где строить N arcs?

**Выбрано:** новый модуль `services/multi_arc_builder.py`. Функция `async def build_arcs_per_moment(canvas, ranked, cfg, pipeline_provider) -> list[StoryScript]`.

**Почему не расширять story_doctor:** `compose_story_script` имеет глобальную семантику «построй лучший нарратив из всего ranked». Менять её на «построй N нарративов» — изменение контракта, ломает существующий fallback. Новый модуль — изолированная новая ответственность.

**Почему не в composer:** composer работает с готовыми candidates, не строит arcs. Добавление build-логики в composer превратит его в god-object.

### Decision 2: Как кормить LLM для каждого arc?

**Выбрано:** reuse существующий `story_doctor.md` prompt (как есть), но подавать ему **отфильтрованный ranked evidence** — только evidence в временном окне вокруг одного canvas moment (±60 сек от центра).

**Почему не новый prompt:** пользовательское ограничение «не решать промптами» — принято. Новый prompt = новая формулировка задачи, высокая вероятность ошибки в неочевидных паттернах (response schema, Lite satisficing bias, и т.д.). Existing prompt уже валидирован на production.

**Почему не чистая алгоритмия:** без LLM нельзя адекватно выбрать между несколькими кандидатами на role=hook с одинаковыми score. LLM сравнивает по контексту. Алгоритмический выбор дал бы топ-по-score что уже и сейчас даёт single-segment reels.

**Фактический change:** story_doctor не модифицируется, меняется **кто** его вызывает и **что** передаёт в `ranked` параметр.

### Decision 3: Сколько arcs строить?

**Выбрано:** N = `min(canvas.candidate_moments_count, max_reel_count)`. Для 11-мин: min(8, 10) = 8 arcs. Для 95-мин: min(40, 71) = 40 arcs.

**Почему не «все moments всегда»:** `PerformanceSettings.max_reel_count` — жёсткий ceiling пользователя. Если он поставил 20 — 40 arcs нет смысла строить (20 выберутся, 20 выбросятся).

**Почему не «всегда max_reel_count»:** если moments=5 а max=20, строить 20 arcs бессмысленно — только 5 реально независимых тем в видео. 5 полных arc'ов лучше 20 мусорных.

### Decision 4: Evidence window для moment

**Выбрано:** для moment с `start_sec=X, end_sec=Y` брать evidence где `start >= X-60 and end <= Y+60`. Дополнительно: если окно даёт <5 evidence — расширить до ±120s. Если и тогда <3 — пропустить moment (canvas нашёл его, но детальных findings нет, arc не собрать).

**Почему ±60:** evidence 2-13s + arc 30-80s → нужен контекст ~120s total для story_doctor. По 60s в каждую сторону от moment центра.

**Почему fallback ±120:** некоторые moments в canvas могут быть summary-узлами без плотности evidence рядом. Давать им шанс найти материал.

### Decision 5: Composer контракт

**Выбрано:** изменить `compose_reels` signature — добавить параметр `per_moment_arcs: list[StoryScript] | None = None`. Если передан не None, composer использует новую стратегию `_candidates_from_per_moment_arcs`, игнорирует `_candidates_from_singles` и `_candidates_from_thematic_clusters` (они были нужны чтобы добрать до max_reel_count из singles — теперь добирать не нужно).

**Почему не убирать старые стратегии:** feature flag позволит A/B. Легаси fallback остаётся доступен при `multi_arc_enabled=false`.

---

## Feature flag

`PerformanceSettings.multi_arc_enabled: bool = False` — default **false**. Это критично:
- Все существующие прогоны на проде не ломаются
- Включается только руками через UI
- После validation и доверия можно переключить default в True отдельным коммитом

---

## File structure

### Create
- `apps/backend/src/videomaker/services/multi_arc_builder.py` — новый модуль, ~200-300 строк
- `apps/backend/src/videomaker/models/multi_arc.py` — Pydantic `MomentArc` (StoryScript + привязка к moment_id, необязательно — может обойтись list[StoryScript])

### Modify
- `apps/backend/src/videomaker/models/runtime_settings.py` — добавить `multi_arc_enabled: bool = False` + `multi_arc_window_sec: float = 60.0`
- `apps/backend/src/videomaker/services/performance_settings_store.py` — сериализация новых полей
- `apps/backend/src/videomaker/services/pipeline_stages/analysis.py` — условная ветка: если flag on → вызвать `build_arcs_per_moment` и передать в `compose_reels`
- `apps/backend/src/videomaker/services/reels_composer.py` — добавить параметр `per_moment_arcs` + функцию `_candidates_from_per_moment_arcs`; условная disable старых source'ов когда flag on
- `apps/frontend/src/components/settings/performance-groups/` — новый toggle UI (один компонент)
- `apps/frontend/src/lib/api/settings.ts` — типизация

### Do NOT modify
- `services/story_doctor.py` — остаётся как есть
- `services/canvas_builder.py` — остаётся как есть
- `services/prompts_data/story_doctor.md` — остаётся как есть (принцип «не промптами»)

---

## Task decomposition

### Task 1: Pydantic models + feature flag (1 commit)

**Files:**
- Modify: `apps/backend/src/videomaker/models/runtime_settings.py`
- Modify: `apps/backend/src/videomaker/services/performance_settings_store.py`

- [ ] **Step 1.1: Add `multi_arc_enabled` + `multi_arc_window_sec` fields**

В `PerformanceSettings` добавить:
```python
multi_arc_enabled: bool = Field(
    default=False,
    description="Включает построение отдельного arc per canvas moment (variant A). Когда выключено — legacy single-arc flow.",
)
multi_arc_window_sec: float = Field(
    default=60.0,
    ge=20.0,
    le=180.0,
    description="Полуокно в секундах вокруг центра candidate_moment для фильтрации evidence.",
)
multi_arc_window_fallback_sec: float = Field(
    default=120.0,
    ge=30.0,
    le=300.0,
    description="Расширенное полуокно если при основном окне найдено меньше multi_arc_min_evidence_per_moment evidence.",
)
multi_arc_min_evidence_per_moment: int = Field(
    default=5,
    ge=2,
    le=30,
    description="Минимум evidence items в окне вокруг moment чтобы строить arc. Меньше — moment пропускается.",
)
```

- [ ] **Step 1.2: Update `performance_settings_store.py`**

Убедиться что новые поля сериализуются в/из БД. Обычно используется `model_dump()` / `model_validate()` Pydantic'а — дополнительные правки не нужны. Проверить через grep.

- [ ] **Step 1.3: Build gates**

```bash
cd apps/backend && uv run ruff check . 
cd apps/backend && uv run pyright src/videomaker/
```

Оба 0 errors.

- [ ] **Step 1.4: Commit**

```bash
git add apps/backend/src/videomaker/models/runtime_settings.py apps/backend/src/videomaker/services/performance_settings_store.py
git commit -m "feat(settings): multi_arc_enabled feature flag + window config (variant A prep)"
```

---

### Task 2: multi_arc_builder core logic (1 commit)

**Files:**
- Create: `apps/backend/src/videomaker/services/multi_arc_builder.py`

- [ ] **Step 2.1: Write module skeleton**

Содержимое:
```python
"""Multi-arc builder — variant A of bottom_up pipeline.

Принимает Canvas.candidate_moments и Ranked evidence, для каждого moment
строит независимый StoryScript через reuse compose_story_script с отфильтрованным
evidence window вокруг moment центра. Возвращает list[StoryScript] для composer.

Feature flag: PerformanceSettings.multi_arc_enabled. При false функция не
вызывается, pipeline работает в legacy mode.
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from videomaker.models.canvas import Canvas, CandidateMoment
from videomaker.models.story_script import StoryScript
from videomaker.services.story_doctor import compose_story_script

if TYPE_CHECKING:
    from videomaker.core.config import Settings
    from videomaker.services.reduce_result import RankedItem

log = logging.getLogger(__name__)


_DEFAULT_PARALLEL_MAX = 10


def _filter_evidence_by_moment(
    ranked: list["RankedItem"],
    moment: CandidateMoment,
    window_sec: float,
) -> list["RankedItem"]:
    """Evidence items с временным пересечением с [moment.start-window, moment.end+window]."""
    left = max(0.0, moment.start_sec - window_sec)
    right = moment.end_sec + window_sec
    return [
        item for item in ranked
        if item.start_sec <= right and item.end_sec >= left
    ]


async def _build_single_arc(
    canvas: Canvas,
    moment: CandidateMoment,
    ranked: list["RankedItem"],
    cfg: "Settings",
    pipeline_provider: str,
    window_sec: float,
    window_fallback_sec: float,
    min_evidence: int,
    semaphore: asyncio.Semaphore,
) -> StoryScript | None:
    """Строит один arc для moment. None если evidence insufficient."""
    async with semaphore:
        nearby = _filter_evidence_by_moment(ranked, moment, window_sec)
        if len(nearby) < min_evidence:
            nearby = _filter_evidence_by_moment(ranked, moment, window_fallback_sec)
        if len(nearby) < min_evidence:
            log.warning(
                "multi_arc_skip_moment",
                extra={
                    "moment_id": moment.id,
                    "evidence_primary": len(_filter_evidence_by_moment(ranked, moment, window_sec)),
                    "evidence_fallback": len(nearby),
                    "threshold": min_evidence,
                },
            )
            return None
        try:
            script = await compose_story_script(
                canvas=canvas,
                ranked_items=nearby,
                cfg=cfg,
                pipeline_provider=pipeline_provider,
            )
        except Exception:
            log.exception("multi_arc_build_failed", extra={"moment_id": moment.id})
            return None
        return script


async def build_arcs_per_moment(
    canvas: Canvas,
    ranked: list["RankedItem"],
    cfg: "Settings",
    pipeline_provider: str,
    window_sec: float = 60.0,
    window_fallback_sec: float = 120.0,
    min_evidence: int = 5,
    max_arcs: int | None = None,
    parallel_max: int = _DEFAULT_PARALLEL_MAX,
) -> list[StoryScript]:
    """Для каждого candidate_moment строит независимый StoryScript через reuse story_doctor.
    
    Возвращает list в том же порядке что canvas.candidate_moments, с пропуском
    moments где недостаточно evidence. Результат используется composer'ом.
    """
    moments = canvas.candidate_moments
    if max_arcs is not None and max_arcs > 0:
        moments = moments[:max_arcs]
    semaphore = asyncio.Semaphore(parallel_max)
    tasks = [
        _build_single_arc(
            canvas=canvas,
            moment=m,
            ranked=ranked,
            cfg=cfg,
            pipeline_provider=pipeline_provider,
            window_sec=window_sec,
            window_fallback_sec=window_fallback_sec,
            min_evidence=min_evidence,
            semaphore=semaphore,
        )
        for m in moments
    ]
    results = await asyncio.gather(*tasks)
    arcs = [r for r in results if r is not None]
    log.info(
        "multi_arc_build_complete",
        extra={
            "moments_count": len(moments),
            "arcs_built": len(arcs),
            "skipped": len(moments) - len(arcs),
        },
    )
    return arcs
```

**CRITICAL**: сигнатура `compose_story_script` может отличаться — СНАЧАЛА прочитать её в `story_doctor.py` через Serena `find_symbol`. Если она не async — этот модуль неверен. Если принимает другие параметры — адаптировать.

- [ ] **Step 2.2: Verify compose_story_script signature match**

```bash
# Read story_doctor.py:compose_story_script via Serena find_symbol
```

Adjust параметры в `_build_single_arc` чтобы совпадали.

- [ ] **Step 2.3: Build gates**

```bash
cd apps/backend && uv run ruff check . 
cd apps/backend && uv run pyright src/videomaker/
```

Оба 0 errors для нового файла.

- [ ] **Step 2.4: Commit**

```bash
git add apps/backend/src/videomaker/services/multi_arc_builder.py
git commit -m "feat(multi_arc): core builder reuses story_doctor per canvas moment"
```

---

### Task 3: Composer integration (1 commit)

**Files:**
- Modify: `apps/backend/src/videomaker/services/reels_composer.py`

- [ ] **Step 3.1: Add `per_moment_arcs` parameter to `compose_reels`**

Signature change:
```python
def compose_reels(
    canvas: Canvas,
    ranked: list[RankedItem],
    story_script: StoryScript,
    variants: list[VariantPlan],
    *,
    source_duration_sec: float,
    llm_model: str = "gemini-2.5-flash-lite",  # ← уже поменяно субагентом
    provider: str = "gemini",
    user_target_count: int | None = None,
    pacing_profile_name: str | None = None,
    cross_context_penalty_enabled: bool = True,
    reel_count_enforce_floor_ceiling: bool = True,
    reel_count_dedup_jaccard_threshold: float = 0.65,
    per_moment_arcs: list[StoryScript] | None = None,  # ← NEW
) -> AnalysisResult:
```

Если `per_moment_arcs is not None and len(per_moment_arcs) > 0`:
- Использовать только новую стратегию `_candidates_from_per_moment_arcs`
- Пропустить `_candidates_from_singles`, `_candidates_from_thematic_clusters`, `_candidates_from_package_of_shorts`, `_candidates_from_punchy_summary`, `_candidates_from_base_arc`
- Остальной flow (greedy uniqueness, enforce_floor_ceiling, dedupe) — оставить

- [ ] **Step 3.2: Write `_candidates_from_per_moment_arcs`**

Каждый arc → 1 кандидат. Использует существующий `_arc_group_to_candidate` (он уже умеет конвертировать arc-segments в ReelCandidate). Параметр `_ARC_NARRATIVE_BOOST` для score multiplier оставить как есть — multi-segment арки должны оставаться приоритетными.

Pseudocode:
```python
def _candidates_from_per_moment_arcs(
    arcs: list[StoryScript],
    canvas: Canvas,
    source_duration_sec: float,
) -> list[_Candidate]:
    candidates = []
    for idx, arc in enumerate(arcs):
        segs = arc.arc or []
        if not segs:
            continue
        cand = _arc_group_to_candidate(
            arc_segments=segs,
            canvas=canvas,
            source_duration_sec=source_duration_sec,
            source_kind="per_moment_arc",
            index=idx,
        )
        if cand is not None:
            candidates.append(cand)
    return candidates
```

**CRITICAL**: прочитать фактическую сигнатуру `_arc_group_to_candidate` в `reels_composer.py`. Приведённая выше — приблизительная. Adjust до реальной.

- [ ] **Step 3.3: Update `_ARC_BOOSTED_SOURCES`**

Добавить `"per_moment_arc"` в set `_ARC_BOOSTED_SOURCES` чтобы narrative boost применялся.

- [ ] **Step 3.4: Disable legacy sources when flag active**

В `compose_reels`:
```python
if per_moment_arcs is not None and per_moment_arcs:
    # variant A mode
    raw_candidates = _candidates_from_per_moment_arcs(
        per_moment_arcs, canvas, source_duration_sec,
    )
else:
    # legacy mode
    raw_candidates = (
        _candidates_from_base_arc(...)
        + _candidates_from_package_of_shorts(...)
        + _candidates_from_punchy_summary(...)
        + _candidates_from_singles(...)
        + _candidates_from_thematic_clusters(...)
    )
```

- [ ] **Step 3.5: Build gates**

```bash
cd apps/backend && uv run ruff check . 
cd apps/backend && uv run pyright src/videomaker/
```

- [ ] **Step 3.6: Commit**

```bash
git add apps/backend/src/videomaker/services/reels_composer.py
git commit -m "feat(composer): per-moment arcs strategy, disables legacy singles when active"
```

---

### Task 4: Pipeline wiring (1 commit)

**Files:**
- Modify: `apps/backend/src/videomaker/services/pipeline_stages/analysis.py`

- [ ] **Step 4.1: Read current `run_analysis_stage` to locate story_doctor call**

Через Serena `find_symbol run_analysis_stage include_body=true`. Найти:
- Место где `story_script = await compose_story_script(...)`
- Место где `analysis = compose_reels(...)` (строка 458-471 на момент плана)
- `perf_for_composer = await get_performance_settings(cfg)` — тут уже читаются settings

- [ ] **Step 4.2: Add multi_arc branch after story_doctor**

После вызова `compose_story_script` (legacy single arc остаётся — он используется как bookend/alternates):
```python
per_moment_arcs: list[StoryScript] | None = None
if perf_for_composer.multi_arc_enabled:
    await _advance(
        service, job_id, JobStage.analyze, 85,
        f"строим arc per moment ({len(canvas.candidate_moments)} штук)",
    )
    from videomaker.services.multi_arc_builder import build_arcs_per_moment
    per_moment_arcs = await build_arcs_per_moment(
        canvas=canvas,
        ranked=reduce_result.ranked,
        cfg=cfg,
        pipeline_provider=pipeline_provider,
        window_sec=perf_for_composer.multi_arc_window_sec,
        window_fallback_sec=perf_for_composer.multi_arc_window_fallback_sec,
        min_evidence=perf_for_composer.multi_arc_min_evidence_per_moment,
        max_arcs=target_reel_count_ceiling,  # use max_reel_count as ceiling
    )
    # Опциональный dump для диагностики
    _dump_per_moment_arcs(per_moment_arcs, art)
```

- [ ] **Step 4.3: Pass `per_moment_arcs` to compose_reels**

В существующем вызове `compose_reels(...)`:
```python
analysis: AnalysisResult = compose_reels(
    canvas,
    reduce_result.ranked,
    story_script,
    variants,
    source_duration_sec=media_info.duration_sec,
    llm_model=_pro_model_for_messaging(cfg, pipeline_provider),  # уже поменяно субагентом
    provider="gemini",
    user_target_count=target_reel_count,
    pacing_profile_name=composer_pacing_profile,
    cross_context_penalty_enabled=True,
    reel_count_enforce_floor_ceiling=perf_for_composer.reel_count_enforce_floor_ceiling,
    reel_count_dedup_jaccard_threshold=perf_for_composer.reel_count_dedup_jaccard_threshold,
    per_moment_arcs=per_moment_arcs,  # ← NEW
)
```

- [ ] **Step 4.4: Write `_dump_per_moment_arcs` helper**

В том же `analysis.py`:
```python
def _dump_per_moment_arcs(arcs: list[StoryScript] | None, art: ArtifactPaths) -> None:
    if not arcs:
        return
    payload = {
        "count": len(arcs),
        "arcs": [arc.model_dump() for arc in arcs],
    }
    (art.text_dir / "per_moment_arcs.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
```

- [ ] **Step 4.5: Build gates**

```bash
cd apps/backend && uv run ruff check . 
cd apps/backend && uv run pyright src/videomaker/
```

- [ ] **Step 4.6: Commit**

```bash
git add apps/backend/src/videomaker/services/pipeline_stages/analysis.py
git commit -m "feat(pipeline): wire multi_arc_builder into analysis stage with dump"
```

---

### Task 5: Frontend toggle (1 commit)

**Files:**
- Modify: `apps/frontend/src/lib/api/settings.ts`
- Create or modify: `apps/frontend/src/components/settings/performance-groups/MultiArcGroup.tsx`
- Modify: `apps/frontend/src/components/settings/performance-groups/index.ts`
- Modify: `apps/frontend/src/components/PerformanceSettingsClient.tsx`

- [ ] **Step 5.1: Type declarations**

В `settings.ts` добавить в `PerformanceSettingsPayload`:
```ts
multi_arc_enabled?: boolean;
multi_arc_window_sec?: number;
multi_arc_window_fallback_sec?: number;
multi_arc_min_evidence_per_moment?: number;
```

- [ ] **Step 5.2: Component MultiArcGroup.tsx**

Простой раздел в Settings: toggle «Multi-arc режим (variant A)» + 3 numeric input (window_sec 20-180, fallback 30-300, min_evidence 2-30) видимые только когда toggle on.

Русский UI:
- «Multi-arc режим — arc per moment»
- «Окно evidence вокруг момента (сек)»
- «Расширенное окно при недоборе evidence (сек)»
- «Минимум evidence items для построения arc»

**DO NOT** использовать эмодзи в UI — правило из CLAUDE.md.

- [ ] **Step 5.3: Export в index.ts + render в PerformanceSettingsClient.tsx**

Следовать существующему pattern NarrativeModeGroup.

- [ ] **Step 5.4: Build gates**

```bash
cd apps/frontend && pnpm tsc --noEmit
cd apps/frontend && pnpm build
```

Оба exit 0.

- [ ] **Step 5.5: Commit**

```bash
git add apps/frontend/
git commit -m "feat(ui): multi_arc toggle + window config in performance settings"
```

---

### Task 6: E2E validation (NO commit — diagnostic only)

**Files:**
- Create: `docs/diagnostics/2026-04-21-multi-arc-validation/results.md`

- [ ] **Step 6.1: Start dev env**

```bash
./run.sh > /tmp/run.log 2>&1 &
sleep 30  # wait backend + frontend health
```

- [ ] **Step 6.2: Enable multi_arc via API**

```bash
curl -X PUT http://127.0.0.1:8000/api/v1/settings/performance \
  -H 'Content-Type: application/json' \
  -d '{"multi_arc_enabled": true}'
```

- [ ] **Step 6.3: Run 11-min baseline video**

Использовать то же видео что в job `c452aadb`. Запустить через API, дождаться `analyze` stage (render можно прервать).

Собрать метрики из `reel_plan.json` + `analysis_summary.json`:
- reel count
- segment counts distribution (все ≥ 3 сегмента ожидаются)
- duration range
- full_arc_count / total (target: ≥80%)

- [ ] **Step 6.4: Run 95-min video**

Использовать то же что в job `b6b9682e`. Те же метрики.

- [ ] **Step 6.5: Compare and record**

Таблица в `results.md`:
```markdown
| Metric | 11-min before (c452aadb) | 11-min after | 95-min before (b6b9682e) | 95-min after |
|---|---|---|---|---|
| reel_count | 10 | <X> | 48 | <Y> |
| full_arc_count | 1 (10%) | <A> | 2 (4%) | <B> |
| median duration | 35.0s | <Z> | 37.3s | <W> |
| duration range | 31-70s | <...> | 30-99s | <...> |
| has_payoff | 2/10 | <P> | 12/48 | <Q> |
```

**Success criteria** для рекомендации «переключить default на multi_arc_enabled=true»:
- ≥80% full_arc на обоих видео
- На 11-min: ≥7 reels (acceptable loss vs 10)
- На 95-min: ≥25 reels (acceptable loss vs 48)
- Нет regression в build gates
- Все reels длиной 30-100s

- [ ] **Step 6.6: If success criteria met — write proposal**

Create next plan: `docs/plans/2026-04-21-multi-arc-default-on.md` — смена default `multi_arc_enabled=true`. Одна строка runtime_settings.py.

- [ ] **Step 6.7: If criteria NOT met — diagnostic**

Определить gap. Возможные причины:
- Canvas moments недобирают → ticket «investigate canvas density»
- story_doctor выдаёт короткие arcs на маленьком evidence window → increase window_sec default
- composer теряет arcs на greedy filter → проверить `_apply_cross_context_penalty` не режет ли over-similar arcs

Записать конкретные gap'ы в `results.md`, НЕ писать fix plan пока user не решит направление.

---

### Task 7: Finalize (1 commit)

**Files:**
- Create: `docs/plans/2026-04-21-multi-arc-plan-variant-a.md` (этот файл, но с финальным статусом)
- Modify: `docs/plans/2026-04-21-multi-arc-plan-variant-a.md` (добавить секцию Post-implementation results)

- [ ] **Step 7.1: Append "Post-implementation" section to this plan**

```markdown
## Post-implementation

**Task completion:** all 6 tasks done. Commits:
- <sha1> feat(settings): multi_arc_enabled
- <sha2> feat(multi_arc): core builder
- <sha3> feat(composer): per-moment arcs strategy
- <sha4> feat(pipeline): wire multi_arc_builder
- <sha5> feat(ui): multi_arc toggle

**Validation results:** see `docs/diagnostics/2026-04-21-multi-arc-validation/results.md`
```

- [ ] **Step 7.2: Commit + push**

```bash
git add docs/
git commit -m "docs(plan): multi-arc variant A — post-implementation status"
git push origin feat/glm-provider
```

---

## Risk register

### Risk 1: compose_story_script на узком evidence window выдаёт пустой arc

**Вероятность:** средняя.
**Симптом:** `_build_single_arc` возвращает StoryScript с `arc=[]`. Composer получает arc без сегментов → 0 reels.
**Mitigation:**
- Step 2.1 проверяет `script.arc` non-empty перед добавлением в results
- Step 3.2 в `_candidates_from_per_moment_arcs` skip'ает arcs с `len(segs) == 0`
**Rollback:** выключить feature flag через UI — мгновенно, никаких миграций.

### Risk 2: LLM rate limit / 429 при N параллельных вызовах

**Вероятность:** низкая при N≤40 и parallel_max=10 (видели на Phase 8 что 10 concurrent ОК для Lite 2.5).
**Симптом:** `compose_story_script` бросает RateLimitError.
**Mitigation:** `_build_single_arc` ловит exception, возвращает None. Pipeline продолжается с меньшим числом arcs.
**Rollback:** уменьшить `parallel_max` в `build_arcs_per_moment` через параметр. Не требует изменения кода.

### Risk 3: story_doctor prompt ожидает весь ranked, не узкое окно

**Вероятность:** средняя.
**Симптом:** на узком evidence window (10-15 items) LLM возвращает вырожденный arc (повтор одного evidence как все 6 ролей) или пустой.
**Mitigation:** Step 6.3/6.4 validation **обязательно** проверяет это. Если обнаружится — ticket для следующего плана: либо увеличить default window_sec до 90-120, либо менять то как сейчас story_doctor получает evidence (последний — нарушит принцип «reuse»).
**Rollback:** flag off.

### Risk 4: Canvas candidate_moments могут быть слабо различимы

**Вероятность:** низкая. Canvas прямо выделяет РАЗНЫЕ моменты (по дизайну).
**Симптом:** 40 arcs выходят overlapping по evidence — dedup в композере оставит только первые 5-8.
**Mitigation:** в composer уже есть `_dedupe_temporal_overlaps` — он сам решит. Если отрезает слишком много — подстраивать `_CROSS_REEL_SEGMENT_OVERLAP_RATIO` отдельным тикетом.
**Rollback:** flag off.

### Risk 5: Signature `compose_story_script` принимает не те параметры что я предположил

**Вероятность:** высокая. Код не читал полностью.
**Симптом:** Step 2.2 показывает mismatch.
**Mitigation:** Step 2.2 — явная verification перед Step 2.3. Если сигнатура другая — adjust `_build_single_arc`.
**Rollback:** тут же, в той же сессии.

### Risk 6: Merge conflict с субагентским коммитом

**Вероятность:** нулевая если Task 1 начинается ПОСЛЕ субагентского DONE.
**Mitigation:** план prerequisite явно это оговаривает.
**Rollback:** `git merge --abort` + resolve manually + повторить.

---

## Honest uncertainties (не скрыто)

1. **Я не знаю точную signature `compose_story_script`.** Task 2 явно требует её прочитать перед написанием кода. Если она sync (не async) или принимает другие именованные аргументы — adjust на месте. Это не стоп-фактор, но нельзя пропустить Step 2.2.

2. **Я не знаю как `_arc_group_to_candidate` обрабатывает source_kind `"per_moment_arc"`.** Возможно потребуется правка `_ROLE_MAP` или `_category_to_role`. Task 3.3 на этот случай добавляет в `_ARC_BOOSTED_SOURCES`. Но если `_arc_group_to_candidate` делает strict validation на известные sources — отдельно это фиксится в том же коммите.

3. **Я не знаю даёт ли canvas.candidate_moments.id уникальные ID** или они могут отсутствовать. Если ID нет — в dump будет использован index. Не критично для runtime.

4. **Я не проверял что PerformanceSettings умеет сериализовать новые поля через существующий store.** Скорее всего умеет (pydantic model_dump), но Step 1.2 явно требует проверить через grep.

5. **Success criteria в Task 6 — эмпирические, не theoretical.** Если на 11-min получится 5 reels вместо 7+ — придётся обсуждать: это fail или acceptable trade-off за 100% narrative completeness. Я заранее не могу выбрать за пользователя.

---

## Non-goals

- **НЕ трогать `story_doctor.py`, `canvas_builder.py`, prompts** — принцип «не промптами».
- **НЕ делать default multi_arc_enabled=true в этом плане** — это отдельный коммит после validation.
- **НЕ удалять legacy composer candidate sources** — они остаются для fallback/legacy mode.
- **НЕ менять closure_validator** — boundary extension это отдельная проблема длины, обсуждается после валидации арок.
- **НЕ расширять canvas density** — если 40 moments недобирают, это отдельный план (обсуждать только если Task 6 покажет это как главный gap).
- **НЕ добавлять новые unit-тесты** — user feedback для этого проекта.

---

## Commit order summary

1. `feat(settings): multi_arc_enabled feature flag + window config`
2. `feat(multi_arc): core builder reuses story_doctor per canvas moment`
3. `feat(composer): per-moment arcs strategy, disables legacy singles when active`
4. `feat(pipeline): wire multi_arc_builder into analysis stage with dump`
5. `feat(ui): multi_arc toggle + window config in performance settings`
6. (no commit) validation run, results → `docs/diagnostics/...`
7. `docs(plan): multi-arc variant A — post-implementation status`

All on `feat/glm-provider`. Push after each if желательно (быстрый feedback), или batch push в конце.

Ориентировочное время на backend subagent: 60-90 минут. Frontend: 20-30 минут. Validation runs: 25-35 минут (11-min и 95-min прогоны + анализ). Total: ~2-2.5 часа wall clock.
