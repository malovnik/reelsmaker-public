# Top-Down Architecture Refactor — Roadmap

> **Создан:** 2026-04-21
> **Цель:** Замена bottom-up сборки на OpusClip-style top-down: Chaptering → Hook → Narrative Arc → Boundary Extension → Stitching
> **Research basis:** `docs/viral-clipper-research-2026-04-21.md`

---

## Проблема (one-liner)

Текущий pipeline собирает рилс из 2-13s evidence fragments и padding'ом доводит до MIN. Narrative closure структурно невозможен — evidence это highlights, не narrative units. Результат: клипы 32-43s без payoff, как у OpusClip 0.x до 2023.

## Решение (one-liner)

Сначала находим **естественные главы** (chaptering) в транскрипте, затем внутри каждой главы ищем **hook + body + payoff** как единый arc. Длительность — следствие arc'а, не цель padding'а.

---

## Architecture diff

### Before (bottom-up)

```
compression → canvas → 6 extraction agents → reducer (rank) →
  story_doctor (склеить evidence в arc) → rhythm → variants →
  composer (padding до MIN) → closure_validator (+8s syntactic)
```

### After (top-down)

```
compression → canvas → chapter_builder (TreeSeg-style) →
  per-chapter parallel:
    hook_detector (Flash Lite 1 call/chapter) →
    narrative_arc_finder (Flash Lite 1 call/chapter) →
    boundary_extender (regex → silence → LLM fallback) →
  cross_chapter_ranker (coherence + uniqueness) →
  story_polish (optional variants) →
  renderer (no padding — natural length)
```

---

## Phase breakdown

### Phase 0: Foundation (1 итерация)

Создать skeleton новых модулей, не ломая existing. Старый pipeline работает as-is параллельно через feature flag `pipeline_mode: "bottom_up" | "top_down"`.

**Deliverables:**
- `services/narrative/__init__.py` — namespace
- `services/narrative/chapter_builder.py` — skeleton + types
- `services/narrative/hook_detector.py` — skeleton
- `services/narrative/arc_finder.py` — skeleton
- `services/narrative/boundary_extender.py` — skeleton (regex markers)
- `schemas/narrative.py` — Chapter, HookCandidate, NarrativeArc, ExtendedArc Pydantic models
- `config/constants.py` или аналог — MIN=28, TARGET=42, MAX=75, MAX_CLOSURE_EXTENSION=35

**Gate:** ruff/pyright зелёные. Никаких изменений в analysis.py.

### Phase 1: Chapter Builder (1-2 итерации)

Hybrid semantic + LLM chaptering. Reuse existing `semantic_chunker.py` как embedding basis, добавляем LLM boundary scoring для topic shifts.

**Алгоритм:**
1. Получить embedding similarities между smogvinnet (10-30s) windows (уже есть в semantic_chunker)
2. Найти local minima → candidate boundaries
3. LLM pass (Flash Lite batch): для каждого candidate — prev 90s + next 90s → `is_chapter_boundary: bool + topic_label: str`
4. Merge глав < MIN_CHAPTER_DURATION (60s), split глав > MAX_CHAPTER_DURATION (5min)
5. Output: `list[Chapter]` с `start_sec, end_sec, topic_label, key_claims: list[str], confidence`

**Gate:** Синтетический транскрипт 15мин → 3-5 chapters с meaningful topics. Нет глав < 45s или > 7min.

### Phase 2: Hook Detector (1 итерация)

1 LLM call на главу (parallel). На вход — полный текст главы + position in video. На выход — top-3 hook candidates.

**Prompt pattern (cache-friendly):**
```
Глава из лекции (topic: {topic_label}):
{chapter_text}

Найди 3 потенциальных hook'а — 2-8s cлайса которые заставят зрителя остановить скролл.
Критерии: контр-интуитивно / вопрос / bold claim / эмоциональный триггер.
Return: [{"hook_start": sec, "hook_end": sec, "text": str, "score": 0..1, "why": str}]
```

**Gate:** На 3 тестовых главах — top-1 hook всегда в первой трети главы, score distribution 0.3-0.9.

### Phase 3: Narrative Arc Finder (1-2 итерации)

Принимает главу + hook → находит natural ending (earliest point after hook where payoff).

**Prompt:**
```
Глава: {chapter_text}
Hook начинается в {hook_start}s: "{hook_text}"
Найди arc: hook → development (1-3 sentences setup) → payoff (resolution).
Payoff = момент когда mental model зрителя "закрывается".
Return: {clip_start, clip_end, closure_type: "conclusion"|"punchline"|"revelation"|"callback", development_sentences: list[str]}
```

Anti-confirmation: "если payoff не находится внутри главы — return null, не fabricate"

**Gate:** 80% arc'ов 30-75s, closure_type distribution не monotonic.

### Phase 4: Boundary Extender (1 итерация)

Trim/extend arc до natural boundaries:
1. **Tail trim**: если clip_end попадает в mid-sentence → найти ближайший sentence end
2. **Silence boundary**: если < 0.5s после sentence end → silence > 0.8s → extend to silence
3. **Discourse marker fallback**: regex на `CLOSURE_MARKERS` в forward 15s

Reuse `closure_validator.py` logic, но без LLM call (детерминизм + regex only).

**Gate:** Все arc'и начинаются на word boundary, заканчиваются на sentence boundary.

### Phase 5: Cross-Chapter Ranker (1 итерация)

Из N chapters получили N arcs. Выбрать top-K для финальных рилсов:
1. Score = hook_score × arc_coherence × novelty (1 - max cosine with selected)
2. Greedy selection с diversity constraint (разные closure_types, разные topics)
3. Output: `list[ReelCandidate]` совместимый с существующим render stage

**Gate:** Distribution topic_labels разнообразная, нет 3+ arcs с одинаковым closure_type в топе.

### Phase 6: Pipeline Integration (1-2 итерации)

Подключить новый flow в `pipeline_stages/analysis.py` через feature flag.

**Ключевые решения:**
- `narrative_mode` setting в runtime_settings (default=top_down после verification)
- Existing extraction agents → deprecated но не удаляем (legacy mode)
- Story_doctor → optional post-processor для arc polishing (не primary)
- Composer → simplified: arc → reel (1:1 mapping), без padding logic
- Closure_validator → final sanity check, не primary closure mechanism

**Gate:** E2E test на 15мин видео: 3+ рилсов, distribution 35-70s, все с finished stories.

### Phase 7: Validation & Tuning (1-2 итерации)

Запустить на тестовом видео `Сделай ЭТО для своей женщины...` → проверить:
- Distribution длин (peak должен быть 40-55s, не 32-43)
- Narrative closure всех reels
- No ffmpeg errors, no frontend crashes
- Artifacts: chapters.json, arcs.json, reels/*.mp4

**Tuning levers** (если peak всё ещё низкий):
- MIN_CHAPTER_DURATION ↑
- Arc finder prompt: "payoff должен быть минимум 2 sentences"
- Cross-chapter ranker: duration_fit_score booster на 45-60s

---

## Legacy compat

- НЕ удаляем: reducer.py, story_doctor.py, reels_composer.py, closure_validator.py
- Feature flag `narrative_mode: "bottom_up" (legacy) | "top_down" (new)`
- Default: top_down после Phase 7 verification
- Прежний bottom_up режим доступен через UI toggle для A/B

---

## Budget / LLM cost

Top-down = меньше LLM calls чем bottom-up:
- Chaptering: 1 batch call (10-15 boundaries × 1 context = 1 prompt)
- Hook detector: N calls parallel (N = chapters, обычно 5-10)
- Arc finder: N calls parallel
- Boundary extender: 0 LLM (regex only)
- Cross-chapter ranker: 0 LLM (scoring only)

vs existing: 6 extraction agents + reducer + story_doctor + rhythm + variants + closure = 10+ LLM calls на весь транскрипт.

**Expected:** 2-3x cheaper + 2-3x faster (parallel vs sequential).

---

## Gemini tier strategy

- Chaptering: **Flash Lite** (batch, cache-friendly prompts)
- Hook detector: **Flash Lite** (parallel, 5-10 calls)
- Arc finder: **Flash** (нужна более сильная model для narrative reasoning)
- Fallback для Arc: **Pro** если Flash возвращает null/low quality

Gemini 2.5 tier resolver уже есть — используем existing `tier_matrix`.

---

## Risk mitigations

1. **Chaptering находит слишком много boundaries** → MIN_CHAPTER_DURATION=60s merges aggressive
2. **Arc finder returns short arcs (< MIN)** → extend до MIN через boundary_extender forward search (no padding)
3. **Hook detector misses** → fallback = start of chapter (первые 5s)
4. **LLM hallucinates closure_type** → enum constraint в schema + validation retry
5. **Cost regression** → compare 10 jobs A/B: old vs new, если new > 2x cost → abort

---

## Success criteria (Phase 7)

Вход: 20-min видео с 3-4 topical chapters.

- [ ] Chaptering → 4-6 chapters, все 90-300s
- [ ] ≥3 рилсов на выходе
- [ ] Distribution длин: median 45-55s, peak 40-60s (not 32-43s!)
- [ ] Все рилсы имеют finished narrative (manual watch-test)
- [ ] Все рилсы имеют coherent topic (не mix of unrelated claims)
- [ ] Cost: LLM spend в пределах 2x от bottom_up
- [ ] Time: pipeline runtime в пределах 1.5x от bottom_up
- [ ] Build gates: ruff 0 errors, pyright 0 errors, pnpm build succeeds
