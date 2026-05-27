# Top-Down E2E Validation Guide — Phase 7

> **Созд:** 2026-04-21
> **Backend build gates:** ✅ (ruff, pyright 0 new errors)
> **Frontend build gates:** ✅ (tsc exit 0, pnpm build compiled successfully)

## Infrastructure Status

### Что уже готово (Phase 0-6)

- [x] Pydantic models (`models/narrative.py`): Chapter, HookCandidate, NarrativeArc, ExtendedArc, ReelCandidate
- [x] 20+ констант в `services/narrative/constants.py` (MIN=28, TARGET=42, MAX=75, MAX_CLOSURE_EXTENSION=35, ...)
- [x] `services/narrative/chapter_builder.py` — hybrid semantic+LLM chaptering
- [x] `services/narrative/hook_detector.py` — per-chapter asyncio.gather hooks
- [x] `services/narrative/arc_finder.py` — Flash→Pro fallback arc discovery
- [x] `services/narrative/boundary_extender.py` — deterministic closure markers
- [x] `services/narrative/cross_chapter_ranker.py` — two-pass greedy с diversity
- [x] `services/narrative/orchestrator.py` — координатор 6 stages
- [x] `pipeline_stages/analysis.py` — branching на `narrative_mode`, early return `_run_top_down_branch`
- [x] Frontend UI: `NarrativeModeGroup.tsx` в `/settings/performance`
- [x] API: `PUT /api/v1/settings/performance` принимает `narrative_mode` field

### Prompts (registered)

- `chapter_boundary_scorer.md` — 4-layer decision (lexical/discourse/rhetorical/narrative)
- `hook_detector.md` — 6 hook_kind categories, anti-confirmation bias
- `narrative_arc_finder.md` — 6 closure_type enum, composite arc_score formula

## Runtime Validation Steps

### Шаг 1: Переключить narrative_mode

Открыть `/settings/performance` в UI → секция "Архитектура сборки рилсов" →
выбрать **"Top-down (OpusClip-style, 2026-04-21)"** → Save.

Альтернатива через API:
```bash
curl -X PUT http://localhost:8000/api/v1/settings/performance \
  -H "Content-Type: application/json" \
  -d '{"narrative_mode": "top_down", ...all_other_fields}'
```

### Шаг 2: Запустить тестовое видео

Использовать test видео из предыдущих сессий:
```
/Users/malovnik/Downloads/4K Video Downloader+/Сделай ЭТО для своей женщины прямо сейчас!...mp4
```

Upload через UI → выбрать profile (talking_head) → target_reel_count (можно оставить default 15) → Run.

### Шаг 3: Проверка прогресса

В SSE-progress stream должны появиться сообщения:
- "top-down narrative: chaptering → hooks → arcs (gemini-...)"
- "выбор thumbnail обложек (Moondream)" (если vision enabled)
- "top-down план готов: N рилсов"

Если pipeline упадёт — смотреть logs:
- `top_down_chapters_built` — сколько глав найдено
- `top_down_hooks_detected` — сколько hook'ов в сумме, сколько глав без hook'ов
- `top_down_arcs_found` — сколько arcs от find_arcs
- `top_down_boundaries_extended` — stats по 3 стратегиям
- `cross_chapter_ranker_done` — итог ранкинга

### Шаг 4: Проверить artifacts

В `/data/artifacts/<job_id>/`:
```
chapters.json           # ≥ 3 глав, durations в 60-300s
narrative_hooks.json    # hooks_by_chapter — ≥ 1 hook на большинстве глав
narrative_arcs.json     # ≥ 3 ExtendedArc
reel_candidates.json    # ≥ 3 ReelCandidate
reel_plan.json          # ≥ 3 ReelPlan (для render)
analysis_summary.json   # narrative_mode="top_down", median_duration_sec в stats
reels/reel_001.mp4      # ≥ 3 mp4
```

### Шаг 5: Ключевые метрики (acceptance criteria)

Из `analysis_summary.json` в `stats`:

| Метрика | Acceptance | Почему |
|---|---|---|
| `chapter_count` | ≥ 3 (для 15+min видео) | Меньше — chaptering не работает |
| `reel_candidates` | ≥ 3 | Если 0-2 — нет narrative closure |
| `median_duration_sec` | 40-60s | Если < 40 — arcs короткие; если > 60 — arcs плывут |
| `min_duration_sec` | ≥ 28 | Hard cutoff — reject ниже MIN |
| `max_duration_sec` | ≤ 75 | Hard cutoff — reject выше MAX |
| `closure_distribution` | ≥ 2 разных closure_type | Если все conclusion — мало diversity |

### Шаг 6: Manual watch-test

Открыть 3-5 рилсов в dashboard:
- Hook ясно выделен в первых 2-8 секундах? ✅/❌
- Зритель получает payoff (завершённую мысль) в конце? ✅/❌
- Фраза не обрывается на mid-sentence? ✅/❌
- Рилс ощущается как единое целое, не куски? ✅/❌

Если все 4 ✅ на ≥ 3/5 рилсов → Phase 7 PASSED.

## Tuning Levers (если acceptance fails)

### Peak длительности < 45s

Значит arcs слишком короткие. Варианты:
1. В `services/narrative/constants.py`: `MIN_CHAPTER_DURATION_SEC = 60 → 90`. Более длинные главы = больше места для development.
2. В `prompts_data/narrative_arc_finder.md`: усилить constraint "minimum 2 development_sentences".
3. `ARC_DEVELOPMENT_MIN_SENTENCES = 1 → 2` в constants.

### Peak длительности > 60s

Arcs плывут. Варианты:
1. `REEL_MAX_DURATION_SEC = 75 → 65` в constants (hard cutoff).
2. В arc_finder prompt: "предпочитать earlier payoff при выборе между двумя closure points".
3. duration_fit penalty круче на large duration.

### Low chapter_count (< 3 для 15+min)

Chaptering слишком conservative. Варианты:
1. `CHAPTER_BUILDER_SIMILARITY_THRESHOLD = 0.35 → 0.45` — больше candidate boundaries.
2. `MIN_CHAPTER_DURATION_SEC = 60 → 45` — разрешить более короткие главы.

### Many arcs == null

Arc_finder слишком строгий или hooks не прошли. Варианты:
1. `ARC_COHERENCE_MIN = 0.5 → 0.4` в constants.
2. `FLASH_RETRY_WITH_PRO_COHERENCE_THRESHOLD = 0.55 → 0.45`.
3. В hook_detector: snap HOOK_MIN_SCORE 0.5 → 0.4.

### All reels same closure_type

Diversity constraint не работает. Варианты:
1. `CLOSURE_TYPE_MAX_PER_RANK = 2 → 1` (жёстче) — но это скорее ухудшит fill-rate.
2. Skip closure_type constraint в первом pass'e.

## Rollback

Если top-down работает хуже bottom-up для конкретного контента:
1. `/settings/performance` → narrative_mode → **bottom_up** → Save.
2. Pipeline немедленно переключается на legacy flow (zero restart нужен).
3. Все артефакты narrative_*.json останутся в старых jobs для debug.

## Completion Criteria

Phase 7 PASSED когда:
- [ ] Runtime test на test видео запущен
- [ ] ≥ 3 рилсов в `reel_plan.json`
- [ ] Median duration 40-60s
- [ ] Manual watch-test: ≥ 3/5 рилсов с closed narrative
- [ ] Build gates зелёные (уже ✅)

## Что НЕ проверяется в этой phase

- Cost comparison bottom-up vs top-down (отдельный анализ)
- Stress-test на 2+ часовом видео (отдельная итерация)
- A/B тест метрик (отдельный проект)
- Render correctness (render stage не менялся — совместим)
