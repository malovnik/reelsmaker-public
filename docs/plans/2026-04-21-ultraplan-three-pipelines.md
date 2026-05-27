# Ultraplan: Three Pipelines Restoration

> **Дата:** 2026-04-21
> **Контекст:** [viral-clipper-research-2026-04-21.md](../viral-clipper-research-2026-04-21.md) + [top-down-architecture-roadmap.md](../top-down-architecture-roadmap.md) + memory `videomaker-pipeline-reanimation-2026-04-21`
> **Цель:** все три pipeline работают (bottom_up, chaptered, map_reduce), distribution длин 30-89s, narrative closure для каждого рилса

---

## Диагноз

Три pipeline уже в коде (feature flag `narrative_mode`), но качество выдачи деградирует по-разному:

| Режим | Статус | Root cause |
|---|---|---|
| `bottom_up` (default) | Работает, но клипы кучкуются вокруг 40-50s и обрываются на payoff | `story_doctor` → один 45-55s arc; `closure_validator` смотрит только +8s — не видит payoff в 20-40s дальше |
| `chaptered` | 1 chapter → 1 reel на 95-мин монологе | Cosine similarity между окнами монолога всегда >0.5 — embedding chaptering не находит boundaries |
| `map_reduce` | Не валидирован после fix4 (relative timestamps) | Ожидание 30-50 рилсов на 2h; требуется runtime test |

Жалоба пользователя про OpusClip — распределённая длина 30-89s с завершённой темой — требует:
- **boundary_extender** как post-processor для каждого рилса (discourse markers + silence + LLM fallback)
- **duration diversifier** на этапе композиции (target slots 35/45/55/70s вместо единого 45s)
- **русские discourse markers** (итак, таким образом, вот почему, значит, поэтому, в итоге)

---

## Phase A: Pipeline #1 `bottom_up` — приоритет

**Цель:** distribution 30-89s + narrative closure без переписывания архитектуры.
**Выбранная стратегия:** инъекция `boundary_extender` + `duration_diversifier` (per AskUserQuestion ответ).

### A.1: Расширение discourse markers для русского

**Файл:** `apps/backend/src/videomaker/services/narrative/boundary_extender.py`

Текущие markers в файле ориентированы на английский. Добавить русскоязычный набор из research:

```python
CLOSURE_MARKERS_RU = [
    r"\bитак\b",
    r"\bтаким образом\b",
    r"\bвот почему\b",
    r"\bзначит\b",
    r"\bпоэтому\b",
    r"\bв итоге\b",
    r"\bсмысл в том\b",
    r"\bсуть в том\b",
    r"\bподводя итог\b",
    r"\bглавное\b",
    r"\bв конечном счёте\b",
    r"\bименно поэтому\b",
]
```

**Gate:** regex smoke-test на русском транскрипте из `/tmp/fixtures/` — пересечение >= 3 markers per 1000 слов.

### A.2: Интеграция boundary_extender как universal post-processor

**Файл:** новый `apps/backend/src/videomaker/services/pipeline_stages/boundary_extension.py`

Stage между `reels_composer` и `render` для ВСЕХ трёх mode. Контракт:

```python
async def apply_boundary_extension(
    reel_candidates: list[ReelCandidate],
    cleaned_transcript: CleanedTranscript,
    mode: Literal["off", "extend_only", "full"] = "full",
) -> list[ReelCandidate]:
    """
    Post-process reel candidates: extend each clip_end до natural closure point.
    - off: no-op (для A/B)
    - extend_only: только расширение, не сокращение
    - full: расширение + trim до sentence boundary
    """
```

Feature flag: `boundary_extension_mode: Literal["off", "extend_only", "full"] = "full"` в `PerformanceSettings`.

**Gate:** ruff 0 errors, pyright 0 errors, smoke test на existing 11-мин видео — все рилсы НЕ обрезаны на mid-sentence.

### A.3: Duration Diversifier

**Файл:** новый `apps/backend/src/videomaker/services/duration_diversifier.py`

Принимает список reel candidates из composer и target slots. Для каждого slot находит NEAREST natural closure в range [target-10, target+15]:

```python
TARGET_SLOTS = [35.0, 45.0, 55.0, 70.0]  # seconds

def diversify_durations(
    base_candidates: list[ReelCandidate],
    transcript: CleanedTranscript,
    target_slots: list[float] = TARGET_SLOTS,
) -> list[ReelCandidate]:
    """
    Для каждого candidate: найти closure marker ближайший к каждому target.
    Если в пределах slot существует natural closure → variant с этой длиной.
    Это даёт распределение [35, 45, 55, 70] вместо монотонного 45s.
    """
```

Интеграция: вызывается ПОСЛЕ composer, ДО boundary_extension. Итог в render идут N вариантов разной длины.

**Gate:** синтетический тест на одном arc 90s — output = 4 варианта (35/45/55/70 ± 10s), все завершаются на discourse marker или sentence boundary.

### A.4: Disable `_apply_arc_narrative_boost` при diversifier ON

Текущий `reels_composer.py` усиливает multi-segment arcs через `_apply_arc_narrative_boost` (score × 1.25). При активном diversifier это создаёт дубли (один arc → 4 варианта → каждый boost'нут). Добавить условие:

```python
if settings.duration_diversifier_enabled:
    # diversifier already produces multi-variant output, skip boost
    return candidates
```

### A.5: E2E валидация A

1. 11-мин baseline (`/tmp/videos/test-11min.mp4` или существующий из job logs):
   - narrative_mode = bottom_up
   - boundary_extension_mode = full
   - duration_diversifier_enabled = true
   - **Gate:** 4+ рилсов с distribution min 30s, max 89s, без обрывов payoff
2. 95-мин real video:
   - Те же settings
   - **Gate:** 15+ рилсов, median 40-55s, percentile 90 <= 80s, все завершённые темы

### A.6: Commit

`feat(bottom_up): universal boundary_extension + duration_diversifier for distribution 30-89s`

---

## Phase B: Pipeline #3 `map_reduce` — валидация + дошлифовка

**Цель:** подтвердить 30-50 рилсов на 2h видео, применить тот же boundary_extender что в Phase A.

### B.1: Runtime validation на 95-мин видео

Preconditions: `narrative_mode = map_reduce`, chunk_size 20000, overlap 2000, parallel 10.

**Checkpoint артефакты:**
- `global_context.json` — central_theme специфична, не "общий monologue"
- `map_raw_candidates.json` — от 3 chunks минимум 30 raw candidates (>=10 per chunk)
- `reduce_final_candidates.json` — 25-50 final clips после dedup
- `reel_plan.json` — итог для render
- `analysis_summary.json` → stats.density_clips_per_min в диапазоне 0.3-0.5

### B.2: Если reel count < 20 на 95-мин → fix B.2.a

Реализовать **retry loop** в `chunk_scorer.py`:

```python
async def score_chunk_with_retry(chunk, target_min, client):
    result = await score_chunk(chunk, target_min, client)
    valid_count = len([c for c in result if c.is_valid])
    if valid_count < max(3, target_min // 2):
        # second pass с explicit hint
        hint = f"Первый вызов вернул {valid_count} клипов. Найди ОСТАВШИЕСЯ моменты которые ты пропустил. НЕ дублируй."
        retry_result = await score_chunk(chunk, target_min, client, extra_hint=hint)
        # merge + dedup
        return dedup_candidates(result + retry_result)
    return result
```

### B.3: Применить universal boundary_extension к map_reduce output

Тот же pipeline_stages/boundary_extension.py из Phase A — map_reduce orchestrator возвращает `list[ReelCandidate]`, post-processor применяется одинаково.

### B.4: E2E валидация B

- 11-мин baseline с map_reduce → ожидание 4-8 рилсов
- 95-мин real → ожидание 30-50 рилсов, distribution 30-89s, все с closure

### B.5: Commit

`fix(map_reduce): runtime validation + retry loop + shared boundary_extension`

---

## Phase C: Pipeline #2 `chaptered` — replace embedding chaptering

**Цель:** работа на монологах (без topic shifts).

### C.1: Replace embedding-based chapter_builder

Корневой диагноз из research 2026-04-21:
> Embedding cosine similarity between consecutive 45-second windows of a monologue stays above 0.5 almost everywhere. The approach was designed for topic-switched dialogues.

**Замена:** LLM-based discourse segmentation на Gemini Flash Lite.

**Файл:** `apps/backend/src/videomaker/services/narrative/chapter_builder.py`

Добавить новый метод `build_chapters_llm_based`:

```python
async def build_chapters_llm_based(
    transcript: CleanedTranscript,
    client: GeminiClient,
    min_duration: float = 60.0,
    max_duration: float = 300.0,
) -> list[Chapter]:
    """
    LLM-based discourse segmentation для монологов.
    Промпт: 'Разбей транскрипт на 5-15 тематических частей.
    Границы — discourse markers (итак, таким образом, вот почему) или topic drift.'
    Русские discourse markers как explicit signal в промпте.
    """
```

Feature flag: `chapter_detection_mode: Literal["embedding", "llm_discourse", "hybrid"] = "hybrid"`.

Hybrid = embedding first; если <3 chapters → fallback на llm_discourse.

### C.2: Forced split fallback

Если даже LLM возвращает 1 chapter на 95-мин → forced split на `ceil(duration_min / 10)` equal chunks с 10% overlap. Это safety net.

### C.3: E2E валидация C

- 95-мин monologue → ожидание 5-10 chapters, 5-10 рилсов, distribution 30-89s

### C.4: Commit

`fix(chaptered): LLM-based discourse segmentation for monologue content`

---

## Phase D: Унификация + Side-by-side benchmark

**Цель:** все три pipeline через единый контракт + бенчмарк на одном видео.

### D.1: Unified downstream

Все три orchestrator выдают `list[ReelCandidate]`. Единый downstream:

```
orchestrator_{mode} → list[ReelCandidate]
   → duration_diversifier (optional)
   → boundary_extension (all modes)
   → render
```

### D.2: Benchmark harness

Новая команда `pnpm run benchmark:all-pipelines <video_path>`:

1. Запускает три jobs параллельно (или sequential если GPU занят)
2. Собирает метрики в `benchmarks/YYYY-MM-DD-<video>/`:
   - `bottom_up.json`: reel_count, duration distribution, cost, time
   - `chaptered.json`: тоже самое
   - `map_reduce.json`: тоже самое
3. Генерирует `comparison.md` с таблицей

### D.3: Default recommendation

После benchmark на 95-мин video — выбираем default:
- Если map_reduce даёт 30+ рилсов с median 45s и closure rate >= 80% → default = map_reduce
- Иначе bottom_up с diversifier остаётся default
- chaptered — всегда как manual choice (не default)

### D.4: Commit

`feat(pipelines): unified downstream + benchmark harness + default selection`

---

## Constraints

- **No mocks/stubs/TODO/FIXME** — production-ready код
- **Новые unit-тесты НЕ писать** (feedback `no_extra_tests`)
- **Build gates после каждой phase:** `cd apps/backend && uv run ruff check . && uv run pyright src/videomaker/` + `cd apps/frontend && pnpm tsc --noEmit && pnpm build`
- **Только Gemini LLM** (feedback `videomaker_gemini_only`)
- **Russian UI** — все новые UI-элементы на русском
- **Commits** после каждой Phase с push в `feat/glm-provider`
- **ONE phase per iteration + STOP** — ждать подтверждения user (max focus protocol)

---

## Sequence

1. **Phase A** (3-5 iterations Ralph Loop) — bottom_up: duration diversifier + boundary extension + ru markers + E2E
2. **Phase B** (2-3 iterations) — map_reduce: runtime validation + possible retry loop + shared post-processor
3. **Phase C** (2-3 iterations) — chaptered: LLM-based discourse + forced split fallback
4. **Phase D** (1-2 iterations) — unification + benchmark + default recommendation

Total: 8-13 Ralph Loop iterations, 1 phase per iteration.

---

## Risk / rollback

- Все изменения за feature flags (`boundary_extension_mode`, `duration_diversifier_enabled`, `chapter_detection_mode`) — legacy bottom_up режим всегда доступен через UI toggle
- Каждая Phase — отдельный commit, можно rollback через `git revert`
- E2E валидация на 11-мин baseline перед 95-мин — быстрый canary test

---

## Success criteria (финал)

- [ ] 11-мин baseline: все три mode дают 4+ рилсов с distribution 30-89s
- [ ] 95-мин real: map_reduce даёт 30+ рилсов, bottom_up 15+, chaptered 5+
- [ ] Все рилсы имеют natural closure (manual watch-test 5 random samples per mode)
- [ ] Peak duration distribution = 45-55s (не 32-43s)
- [ ] Median distance между clip durations >= 10s (не монотонно 40s)
- [ ] Build gates все зелёные (ruff, pyright, pnpm build)
- [ ] Benchmark harness генерирует comparison.md с 3 mode × 1 video
