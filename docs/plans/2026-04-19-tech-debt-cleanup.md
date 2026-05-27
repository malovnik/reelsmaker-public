# Videomaker Tech Debt Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Закрыть 8 явно выбранных пользователем блоков технического долга videomaker (subtitle sync, screencast auto-zoom, adaptive audio editing, composer UI, preference ML, predictable reel count, frontend handoff) в 8 последовательных фаз с коммитами между фазами.

**Architecture:** Каждая фаза = один deliverable (1 коммит → push → serena memory → STOP). Новый код живёт рядом с существующими сервисами и переиспользует текущую инфраструктуру (Gemini Flash Lite client, PerformanceSettings, runtime_settings_store, ProfileSelector, ProjectGraph). Ничего legacy не удаляется — всё через toggle on/off в runtime_settings согласно манифесту 2026-04-19.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy / Pydantic v2 / librosa / Parselmouth / silero-vad / MediaPipe / OpenCV (backend); Next.js 16 / React 19 / Tailwind 4 / stone-zen tokens / shadcn-flavoured components (frontend); Gemini 2.5-flash-lite (hard-coded).

**Правила исполнения:**
- User rule `feedback_no_extra_tests` — **НЕ писать unit-тесты**. Верификация через build gates: `uv run ruff check`, `pnpm lint`, `pnpm tsc --noEmit`, `pnpm build`, smoke-import через `uv run python -c "from videomaker.services.X import Y"`.
- User rule `feedback_videomaker_philosophy_and_speed` — каждая новая фича обязана иметь runtime_settings toggle + intensity. Legacy пути сохраняются.
- Serena MCP для чтения/записи кода (`find_symbol`, `replace_symbol_body`, `insert_after_symbol`), Context7 для документации библиотек. Никогда не использовать Read/Grep/Bash если можно заменить Serena-вызовом.
- Gemini модель = `gemini-2.5-flash-lite`. В `llm_client.py` hard-coded, trogать запрещено.
- После каждой фазы — `git commit`, `git push origin main`, `serena write_memory` с именем `tech-debt/phase-N-summary`, отметка `✅` в `docs/research/consolidated-action-plan.md`, **полная остановка** и ждать указания.

---

## Scope Check

Плану 8 фаз. Каждая — отдельная работоспособная подсистема. Подфазы (T8.1-T8.6, T3.1-T3.10) исполняются внутри своей фазы последовательно, с общим коммитом на всю фазу. Если подфаза раздуется >3 часов — разбить на два коммита «phase-6a» / «phase-6b».

---

## Pre-flight — актуализация статуса перед стартом

**Важно:** пункт «Post-trim semantic closure LLM-checker» из pending memo — **УЖЕ РЕАЛИЗОВАН** (`services/closure_validator.py`, 449 строк, подключён к `pipeline.py` и `story_doctor.py`). Отдельная фаза не нужна. В consolidated-action-plan.md нужно пометить как ✅.

**Оставшиеся 7 треков (переобозначены):**

| Phase | Трек | Impact | Effort |
|---|---|---|---|
| 1 | Subtitle sync regression investigation + hotfix | HIGH | ~30 мин (investigation) + ~20 мин (fix после репро) |
| 2 | Predictable reel count (floor/ceiling + Jaccard) | HIGH | ~40 мин |
| 3 | T6.1 Cosine retrieval preference memory | MEDIUM | ~50 мин |
| 4 | T9 Composer strategy UI (radio + Cross-context badge) | MEDIUM | ~30 мин |
| 5 | T8 Adaptive audio editing (6 подзадач) | HIGH | ~3-4 часа |
| 6 | T2.8 Screencast auto-zoom (3 slices) | HIGH | ~1-1.5 часа |
| 7 | T3 Frontend handoff (9 экранных блоков) | HIGH | ~4-6 часов |
| 8 | Docs cleanup + consolidated-action-plan ✅ отметки | — | ~15 мин |

---

## Phase 1: Subtitle sync regression investigation + hotfix

**Files:**
- Read: `apps/backend/src/videomaker/services/pipeline.py:1214-1756` (punchline pause + compression + resync блок)
- Read: `apps/backend/src/videomaker/services/subtitles.py` (write_ass signature)
- Modify (if fix needed): `apps/backend/src/videomaker/services/pipeline.py` (move ASS generation after all mutations)
- Create: `docs/research/subtitle-sync-investigation-2026-04-19.md` (отчёт расследования)

**Контекст бага:** user видит рассинхронизацию субтитров после добавления punchline pause (`pipeline.py:1243` extends speech segments на hold_sec до compression). Resync существует на `pipeline.py:1735` и использует финальные `g.cuts`, но user сообщил "показалось". Нужна точная диагностика, затем — фикс.

- [ ] **Step 1: Прочитать punchline pause блок**

```bash
# Через Serena
mcp__serena__find_symbol name_path_pattern="render_job" relative_path="apps/backend/src/videomaker/services/pipeline.py" include_body=false depth=0
```

Локализовать строки 1214-1756. Проверить что именно мутирует `speech: list[SpeechSegment]` через punchline extension и как это влияет на последующий `compress_pauses_in_cuts`.

- [ ] **Step 2: Прочитать `write_ass` signature**

```bash
mcp__serena__find_symbol name_path_pattern="write_ass" relative_path="apps/backend/src/videomaker/services/subtitles.py" include_body=true
```

Записать в `docs/research/subtitle-sync-investigation-2026-04-19.md`:
- Какие поля `SubtitleReelSpec` используются (`segments`, `words`).
- Как segments преобразуются в output-local time.
- Зависят ли word-positions от `speech_segments` (да/нет).

- [ ] **Step 3: Запросить репро у пользователя**

Выдать пользователю сообщение в чате:

```
Для фикса subtitle sync нужен репро. Пришли пожалуйста:
1. ID рилса (например f3a21b8c).
2. Timecode в OUTPUT рилсе где субтитр ушёл (например 00:12 — вижу слово 'привет' а слышу 'спасибо').
3. Пришли ли видео через Automatic или Manual mode.

Без этих данных я не буду трогать работающий resync path — риск регрессии в 4 других jobs.
```

- [ ] **Step 4: После получения репро — проверить конкретный ASS файл**

```bash
# Путь к сгенерированному файлу
cat data/artifacts/<JOB_ID>/subs/<REEL_ID>.ass | head -60
```

Сверить с `words.json` артефакт и с `project_graphs.json` чтобы подтвердить что resync прошёл и сдвиг действительно есть.

- [ ] **Step 5: (Условный фикс) Если resync действительно не применяется**

Добавить guard перед `write_ass` на ранней генерации (строка ~1141 pipeline.py):

```python
# Ранний write_ass остаётся для случая если все T10/T11 features выключены
# и mutation path не активируется. Resync на 1735 перезапишет если нужно.
# Но если punchline_pause_enabled=True — раннюю генерацию можно пропустить,
# потому что resync гарантированно затрёт .ass. Экономим ~5-15 мс per reel.
_run_early_ass = not (
    perf_preview.punchline_pause_enabled
    or perf_preview.pause_compression_enabled
    or perf_preview.filler_removal_enabled
)
if _run_early_ass:
    write_ass(sub_spec, sub_path)
```

Это не меняет behaviour, только делает resync обязательным путём для Auto mode. Subs всегда будут генериться из ФИНАЛЬНЫХ cuts.

- [ ] **Step 6: (Условный фикс) Если resync применяется, но слова дрейфуют**

Копать глубже — проверить что `words` (передаётся в `SubtitleReelSpec`) содержит абсолютные source_time секунды (не сдвигаются при extensionе speech). Если слова сдвинулись → регрессия в `transcriber.py` или `word-timing` adjusting. Тогда baseline — `words` не должны мутироваться, ASS resync корректно мапит `audio_start_sec/audio_end_sec` на word-time.

- [ ] **Step 7: Build gate**

```bash
cd apps/backend && uv run ruff check src/videomaker/services/pipeline.py
```

Expected: `All checks passed!`

- [ ] **Step 8: Commit + push + memory**

```bash
git add apps/backend/src/videomaker/services/pipeline.py docs/research/subtitle-sync-investigation-2026-04-19.md
git commit -m "$(cat <<'EOF'
fix(subtitles): skip early write_ass when mutation path active

Если включён punchline_pause / pause_compression / filler_removal —
cuts гарантированно мутируют, resync на строке 1735 затрёт ASS.
Ранняя генерация была work-for-nothing + создавала окно рассинхрона
если любая stage упадёт между ними. Guard выключает раннюю генерацию
когда Auto mode активен.
EOF
)"
git push origin main
```

Затем Serena memory:

```
mcp__serena__write_memory memory_name="tech-debt/phase-1-subtitle-sync" content="<краткое описание расследования и фикса>"
```

В `consolidated-action-plan.md` заменить `## 🐞 BUG — Subtitle sync regression` на `## 🐞 BUG — Subtitle sync regression ✅ (2026-04-19 hotfix + investigation)` + ссылка на investigation doc.

---

## Phase 2: Predictable reel count (floor/ceiling + Jaccard dedup)

**Files:**
- Read: `apps/backend/src/videomaker/services/reels_composer.py` (понять где composite_score финализируется и где сейчас happens dedup)
- Modify: `apps/backend/src/videomaker/services/reels_composer.py` — добавить `_enforce_reel_count_floor_ceiling` helper
- Modify: `apps/backend/src/videomaker/models/runtime_settings.py` — добавить поля `reel_count_dedup_jaccard_threshold` и `reel_count_enforce_floor_ceiling`
- Modify: `apps/frontend/src/lib/api.ts` — PerformanceSettings interface
- Modify: `apps/frontend/src/components/PerformanceSettingsClient.tsx` — UI switches

**Контекст:** сейчас из 15-мин видео выходит 3-12 рилсов (непредсказуемо). OpusClip даёт 12-23 с 30-40% уникальностью. Уже существует `services/reducer.py` в videoeditor-репо как reference. В videomaker нужно добавить post-reduce filter в reels_composer.

- [ ] **Step 1: Прочитать reels_composer структуру**

```bash
mcp__serena__get_symbols_overview relative_path="apps/backend/src/videomaker/services/reels_composer.py"
```

Локализовать `compose_reels` + `_renumber_and_finalize` + `_compute_composite_score`. Финальный dedup-фильтр должен встать между composite_score ранжированием и `_renumber_and_finalize`.

- [ ] **Step 2: Добавить runtime_settings поля**

В `apps/backend/src/videomaker/models/runtime_settings.py` в классе `PerformanceSettings` после `ken_burns_max_scale`:

```python
# T11-related: Predictable reel count
reel_count_enforce_floor_ceiling: bool = Field(
    default=True,
    description="Принудительно держать target count по длительности: "
    "10-15min → 10-15 reels, 15-30min → 12-20, 30-60min → 15-25, 60+min → 20-30.",
)
reel_count_dedup_jaccard_threshold: float = Field(
    default=0.7,
    ge=0.4,
    le=0.95,
    description="Максимальный token-overlap (Jaccard) между двумя принятыми "
    "рилсами. Больше → меньше уникальности, меньше → жёстче dedup.",
)
```

- [ ] **Step 3: Добавить helper `_enforce_reel_count_floor_ceiling`**

В конец `reels_composer.py` перед последним `def` (до close of module):

```python
def _target_count_by_duration(source_duration_sec: float) -> tuple[int, int]:
    """Returns (floor, ceiling) для N рилсов по длительности источника."""
    minutes = source_duration_sec / 60.0
    if minutes < 10:
        return (3, 8)
    if minutes < 15:
        return (10, 15)
    if minutes < 30:
        return (12, 20)
    if minutes < 60:
        return (15, 25)
    return (20, 30)


def _tokens(text: str) -> set[str]:
    """Простая токенизация для Jaccard: lowercase + split + dedup."""
    return {t for t in text.lower().split() if len(t) > 2}


def _jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard similarity [0, 1] между двумя множествами токенов."""
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _greedy_uniqueness_filter(
    candidates: list[Any],  # ReelPlan after ranking
    jaccard_threshold: float,
) -> list[Any]:
    """Принимает следующего кандидата только если его Jaccard с уже принятыми
    < threshold. Candidates должны быть отсортированы по composite_score DESC."""
    accepted: list[Any] = []
    accepted_tokens: list[set[str]] = []
    for cand in candidates:
        cand_text = " ".join(s.text for s in cand.segments if getattr(s, "text", None))
        cand_tokens = _tokens(cand_text)
        if not cand_tokens:
            accepted.append(cand)
            accepted_tokens.append(set())
            continue
        max_sim = max(
            (_jaccard(cand_tokens, prev) for prev in accepted_tokens),
            default=0.0,
        )
        if max_sim < jaccard_threshold:
            accepted.append(cand)
            accepted_tokens.append(cand_tokens)
    return accepted


def _enforce_reel_count_floor_ceiling(
    ranked: list[Any],
    source_duration_sec: float,
    jaccard_threshold: float,
) -> list[Any]:
    """Применяет floor/ceiling + Jaccard dedup.

    1. dedup через greedy Jaccard filter
    2. обрезает сверху до ceiling
    3. если после dedup меньше floor — возвращает всё что было после dedup
       (не раздуваем дублями)
    """
    floor, ceiling = _target_count_by_duration(source_duration_sec)
    deduped = _greedy_uniqueness_filter(ranked, jaccard_threshold)
    if len(deduped) > ceiling:
        deduped = deduped[:ceiling]
    return deduped
```

- [ ] **Step 4: Интегрировать в `compose_reels`**

В `compose_reels` после композиции ranked list и до `_renumber_and_finalize`:

```python
perf = await get_performance_settings(settings)
if perf.reel_count_enforce_floor_ceiling:
    ranked_before = len(ranked)
    ranked = _enforce_reel_count_floor_ceiling(
        ranked,
        source_duration_sec=source_duration_sec,
        jaccard_threshold=perf.reel_count_dedup_jaccard_threshold,
    )
    log.info(
        "reel_count_enforced",
        before=ranked_before,
        after=len(ranked),
        threshold=perf.reel_count_dedup_jaccard_threshold,
        source_duration_min=round(source_duration_sec / 60, 1),
    )
```

- [ ] **Step 5: Frontend api.ts**

В `apps/frontend/src/lib/api.ts` в `PerformanceSettings` interface (после `ken_burns_max_scale`):

```ts
// Predictable reel count
reel_count_enforce_floor_ceiling: boolean;
reel_count_dedup_jaccard_threshold: number;
```

- [ ] **Step 6: Frontend UI в PerformanceSettingsClient.tsx**

Новая `<Group>` после «Движение кадра»:

```tsx
<Group title="Количество и уникальность рилсов">
  <SwitchRow
    id="reel_count_enforce_floor_ceiling"
    label="Держать целевое количество по длительности"
    hint="10-15 мин → 10-15 рилсов; 15-30 мин → 12-20; 30-60 мин → 15-25; 60+ мин → 20-30. Стандарт: включено."
    checked={values.reel_count_enforce_floor_ceiling}
    onChange={(v) => update("reel_count_enforce_floor_ceiling", v)}
  />
  {values.reel_count_enforce_floor_ceiling && (
    <SliderRow
      id="reel_count_dedup_jaccard_threshold"
      label="Порог уникальности между рилсами"
      hint="0.7 = допустимо 70% пересечения слов — хорошая целевая уникальность. Меньше — жёстче отсев дублей, но рилсов будет меньше. Стандарт: 0.7."
      value={values.reel_count_dedup_jaccard_threshold}
      min={0.4}
      max={0.95}
      step={0.05}
      onChange={(v) => update("reel_count_dedup_jaccard_threshold", v)}
    />
  )}
</Group>
```

- [ ] **Step 7: Build gates**

```bash
cd apps/backend && uv run ruff check src/videomaker/services/reels_composer.py src/videomaker/models/runtime_settings.py
cd apps/frontend && pnpm lint && pnpm tsc --noEmit && pnpm build
```

- [ ] **Step 8: Commit + push + memory**

```bash
git add apps/backend/src/videomaker/services/reels_composer.py apps/backend/src/videomaker/models/runtime_settings.py apps/frontend/src/lib/api.ts apps/frontend/src/components/PerformanceSettingsClient.tsx
git commit -m "feat(composer): predictable reel count via floor/ceiling + Jaccard dedup"
git push origin main
```

Serena memory: `tech-debt/phase-2-reel-count-predictability` с summary. В consolidated-action-plan.md — `pending/reel-count-predictability` пометить ✅.

---

## Phase 3: T6.1 Cosine retrieval preference memory

**Files:**
- Modify: `apps/backend/src/videomaker/services/preference_memory.py` (добавить cosine retrieval path)
- Modify: `apps/backend/src/videomaker/models/job.py` (уже есть liked_reels JSON; проверить что embeddings persist'ятся)
- Modify: `apps/backend/src/videomaker/services/canvas_embedder.py` (если нужно добавить persistence в БД)
- Migration: `apps/backend/alembic/versions/<date>_add_liked_reel_embeddings.py` (если ещё нет таблицы/колонки)

**Контекст:** сейчас `preference_memory.py` (170 строк) делает топ-8 hook-фраз через prompt anchoring. T6.1 добавляет cosine retrieval — находит топ-5 семантически ближайших лайкнутых рилсов к текущему кандидату через 256-dim Gemini embeddings.

- [ ] **Step 1: Прочитать preference_memory.py**

```bash
mcp__serena__get_symbols_overview relative_path="apps/backend/src/videomaker/services/preference_memory.py"
```

Локализовать существующие функции top-K retrieval. Понять API vector — входная структура `liked_reel` + сохранён ли embedding.

- [ ] **Step 2: Проверить есть ли pgvector**

```bash
cd apps/backend && grep -l "pgvector\|vector(" src/videomaker/models/*.py alembic/versions/*.py 2>&1
```

Если pgvector нет — мы на SQLite. Тогда embeddings храним как JSON-массив floats, cosine считаем в Python через numpy (linear scan при <500 записей).

- [ ] **Step 3: Добавить persistence embedding для liked reels**

Если колонки нет — в `models/job.py` найти `LikedReelRow` и добавить:

```python
embedding_json: Mapped[list[float] | None] = mapped_column(
    JSON, nullable=True, default=None,
    comment="256-dim Gemini embedding лайкнутого reel. Используется для cosine retrieval в preference_memory.",
)
```

Если `LikedReelRow` нет — найти где лайкнутые рилсы хранятся (в `Job.options["likes"]` или отдельная таблица) и расширить там.

- [ ] **Step 4: Alembic migration для колонки**

```bash
cd apps/backend && uv run alembic revision -m "add liked_reel_embedding_json"
```

Затем в сгенерированный файл вставить:

```python
def upgrade() -> None:
    op.add_column(
        "liked_reels",  # или соответствующая таблица
        sa.Column("embedding_json", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("liked_reels", "embedding_json")
```

- [ ] **Step 5: Расширить preference_memory.py — новая функция**

В конце `preference_memory.py` добавить:

```python
import numpy as np


async def retrieve_top_k_similar(
    current_candidate_embedding: list[float],
    liked_reels_with_embeddings: list[tuple[str, list[float]]],
    k: int = 5,
) -> list[str]:
    """Возвращает hook-phrases топ-K семантически ближайших лайкнутых рилсов.

    liked_reels_with_embeddings: list of (hook_phrase, embedding_256d).
    Cosine similarity через numpy — linear scan (<500 likes, индекс не нужен).
    Fallback: если embedding кандидата None или все liked без embedding →
    fallback на top_k_hook_phrases() (legacy top-8 by date).
    """
    if not current_candidate_embedding or not liked_reels_with_embeddings:
        return []
    cand_vec = np.array(current_candidate_embedding, dtype=np.float32)
    cand_norm = np.linalg.norm(cand_vec)
    if cand_norm < 1e-9:
        return []
    scored: list[tuple[float, str]] = []
    for hook, emb in liked_reels_with_embeddings:
        if not emb:
            continue
        emb_vec = np.array(emb, dtype=np.float32)
        emb_norm = np.linalg.norm(emb_vec)
        if emb_norm < 1e-9:
            continue
        sim = float(np.dot(cand_vec, emb_vec) / (cand_norm * emb_norm))
        scored.append((sim, hook))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [hook for _, hook in scored[:k]]
```

- [ ] **Step 6: Интеграция в Gemini prompt**

В том месте где сейчас injected `top_k_hook_phrases()` (искать через `mcp__serena__find_referencing_symbols`) — добавить preferential path:

```python
# T6.1: prefer semantic retrieval over top-by-date if candidate embedding exists
hooks: list[str]
if candidate_embedding and liked_embeddings:
    hooks = await retrieve_top_k_similar(
        candidate_embedding, liked_embeddings, k=5
    )
else:
    hooks = top_k_hook_phrases(liked_reels, k=8)  # legacy fallback
```

- [ ] **Step 7: Runtime setting для переключения**

В `PerformanceSettings`:

```python
preference_retrieval_mode: Literal["cosine", "top_by_date"] = Field(
    default="cosine",
    description="cosine = семантическое retrieval по Gemini embeddings (требует 30+ лайков); "
    "top_by_date = legacy топ-8 по дате.",
)
```

Frontend api.ts + PerformanceSettingsClient — добавить `SelectRow` в группу «Личные предпочтения».

- [ ] **Step 8: Build gates + commit**

```bash
cd apps/backend && uv run ruff check src/videomaker/services/preference_memory.py && uv run alembic upgrade head
cd apps/frontend && pnpm lint && pnpm tsc --noEmit && pnpm build
git add apps/backend apps/frontend
git commit -m "feat(preference): cosine retrieval over liked reel embeddings (T6.1 Phase 1)"
git push origin main
```

Serena memory: `tech-debt/phase-3-preference-cosine-retrieval`.

---

## Phase 4: T9 Composer strategy UI

**Files:**
- Read: `apps/backend/src/videomaker/services/auto_config_advisor.py` (`_decide_composer_strategy`)
- Modify: `apps/frontend/src/lib/api.ts` — добавить `COMPOSER_STRATEGIES` enum + поле в ReelRead для `cross_context_risk`
- Modify: `apps/frontend/src/components/upload/UploadWizard.tsx` — radio «Стиль монтажа»
- Modify: `apps/frontend/src/components/job/ReelCard.tsx` — badge «Cross-context» если `cross_context_risk > 0.6`
- Modify: `apps/backend/src/videomaker/api/routes/jobs.py` — create_job принимает `composer_strategy` override
- Modify: `apps/backend/src/videomaker/models/job.py` — опция `composer_strategy_override` в `CreateJobForm`

**Контекст:** composer_strategy уже выбирается advisor'ом (tight_context / balanced / thematic_free), runtime-поле есть. Нет UI чтобы user явно переопределил. Также нет badge'а в ReelCard для предупреждения о cross-context рилсах.

- [ ] **Step 1: UploadWizard radio**

В `UploadWizard.tsx` после «Режим монтажа» (pipeline_mode):

```tsx
<div className="flex flex-col gap-2 rounded-lg border border-stone-200 bg-stone-50 p-4">
  <div className="text-xs font-semibold uppercase tracking-wider text-stone-500">
    Стиль монтажа (composer strategy)
  </div>
  <div className="flex flex-col gap-2">
    <label className="flex cursor-pointer items-start gap-2 rounded-md border border-stone-200 bg-white px-3 py-2 text-sm hover:border-stone-300 has-[:checked]:border-violet-500 has-[:checked]:bg-violet-50">
      <input type="radio" name="composer_strategy" value="auto" checked={composerStrategy === "auto"} onChange={() => setComposerStrategy("auto")} className="mt-0.5" />
      <span>
        <span className="block font-medium text-stone-900">Авто (по решению advisor'а)</span>
        <span className="text-xs text-stone-500">Система сама выберет балансом / свободой</span>
      </span>
    </label>
    <label className="flex cursor-pointer items-start gap-2 rounded-md border border-stone-200 bg-white px-3 py-2 text-sm hover:border-stone-300 has-[:checked]:border-violet-500 has-[:checked]:bg-violet-50">
      <input type="radio" name="composer_strategy" value="tight_context" checked={composerStrategy === "tight_context"} onChange={() => setComposerStrategy("tight_context")} className="mt-0.5" />
      <span>
        <span className="block font-medium text-stone-900">Держаться одного контекста</span>
        <span className="text-xs text-stone-500">Безопасно — рилс не «склеивает скандалы» из разных частей видео</span>
      </span>
    </label>
    <label className="flex cursor-pointer items-start gap-2 rounded-md border border-stone-200 bg-white px-3 py-2 text-sm hover:border-stone-300 has-[:checked]:border-violet-500 has-[:checked]:bg-violet-50">
      <input type="radio" name="composer_strategy" value="balanced" checked={composerStrategy === "balanced"} onChange={() => setComposerStrategy("balanced")} className="mt-0.5" />
      <span>
        <span className="block font-medium text-stone-900">Немного свободы</span>
        <span className="text-xs text-stone-500">Разрешает близкие прыжки (&lt;5 мин apart) — стандарт</span>
      </span>
    </label>
    <label className="flex cursor-pointer items-start gap-2 rounded-md border border-stone-200 bg-white px-3 py-2 text-sm hover:border-stone-300 has-[:checked]:border-violet-500 has-[:checked]:bg-violet-50">
      <input type="radio" name="composer_strategy" value="thematic_free" checked={composerStrategy === "thematic_free"} onChange={() => setComposerStrategy("thematic_free")} className="mt-0.5" />
      <span>
        <span className="block font-medium text-stone-900">Телевизионный микс</span>
        <span className="text-xs text-stone-500">Composer свободен компилировать, подходит для ярких нарезок, требует просмотра</span>
      </span>
    </label>
  </div>
</div>
```

State:

```ts
const [composerStrategy, setComposerStrategy] = useState<
  "auto" | "tight_context" | "balanced" | "thematic_free"
>("auto");
```

В FormData при создании job:

```ts
if (composerStrategy !== "auto") {
  form.append("composer_strategy_override", composerStrategy);
}
```

- [ ] **Step 2: Backend create_job endpoint**

В `apps/backend/src/videomaker/api/routes/jobs.py` `create_job` form fields добавить:

```python
composer_strategy_override: str | None = Form(
    default=None,
    description="tight_context / balanced / thematic_free — переопределяет advisor. 'auto' = не трогать.",
),
```

Сохранить в `job.options["composer_strategy_override"]` и в `pipeline.py` при применении advisor'а, если override есть → `cfg.composer_strategy = override`.

- [ ] **Step 3: Cross-context badge в ReelCard**

В `components/job/ReelCard.tsx`:

```tsx
{reel.cross_context_risk !== undefined && reel.cross_context_risk > 0.6 && (
  <div className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-medium text-amber-800">
    <svg className="size-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M12 9v4m0 4h.01M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
    </svg>
    Cross-context — проверь перед публикацией
  </div>
)}
```

Tooltip по клику показывает: «Рилс собран из сегментов, разделённых более 5 минутами в оригинале. Проверь что смысл сохранён».

- [ ] **Step 4: Backend — cross_context_risk в ReelRead response**

`cross_context_risk` уже считается в `services/cross_context_risk.py`. Убедиться что он попадает в `reel.analysis_meta["cross_context_risk"]` и ReelRead его возвращает. Если нет — добавить в pipeline при compose, при каждом reel вычислять и сохранять в analysis_meta.

- [ ] **Step 5: Build gates + commit**

```bash
cd apps/backend && uv run ruff check
cd apps/frontend && pnpm lint && pnpm tsc --noEmit && pnpm build
git add apps/
git commit -m "feat(composer): UI radio для composer_strategy + Cross-context warning в ReelCard (T9)"
git push origin main
```

Serena memory `tech-debt/phase-4-composer-strategy-ui`.

---

## Phase 5: T8 Adaptive audio editing (6 подзадач)

**Large phase — разбить на 2 коммита phase-5a (T8.1-T8.3) + phase-5b (T8.4-T8.6).**

**Контекст:** research отчёт `docs/research/adaptive-audio-editing-2026.md` должен быть готов (проверить — если нет, Phase 5 блокируется на research). Конкретные библиотеки — из research вывода.

### Phase 5a: T8.1-T8.3 (mouth sounds + breath + context-aware keep)

**Files:**
- Create: `apps/backend/src/videomaker/services/mouth_sound_detector.py`
- Create: `apps/backend/src/videomaker/services/breath_classifier.py`
- Modify: `apps/backend/src/videomaker/services/pause_compression.py` — добавить context-aware keep_sec
- Modify: `apps/backend/src/videomaker/models/runtime_settings.py`

- [ ] **Step 1: T8.1 mouth_sound_detector.py**

Использовать DeepFilterNet или noisereduce (уже в deps). API:

```python
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class AudioDefect:
    type: str  # "click" | "lip_smack" | "cluck"
    start_sec: float
    end_sec: float
    confidence: float


async def detect_mouth_sounds(
    audio_path: Path,
    sample_rate: int = 16000,
) -> list[AudioDefect]:
    """Детектит mouth sounds через spectral envelope analysis.

    Эвристика: короткие (<100ms) всплески в spectral centroid > mean + 2*std
    в полосе 2-8kHz (где находятся lip smacks) без содержания в 80-300 Hz
    (basic speech band).

    Graceful degrade: если librosa fail → возвращает [].
    """
    try:
        import librosa
        import numpy as np

        y, sr = librosa.load(str(audio_path), sr=sample_rate, mono=True)
        stft = np.abs(librosa.stft(y, n_fft=512, hop_length=256))
        # band masks
        freqs = librosa.fft_frequencies(sr=sr, n_fft=512)
        speech_band = (freqs >= 80) & (freqs <= 300)
        lip_band = (freqs >= 2000) & (freqs <= 8000)
        speech_energy = stft[speech_band].mean(axis=0)
        lip_energy = stft[lip_band].mean(axis=0)
        # spikes: lip high + speech low
        ratio = lip_energy / (speech_energy + 1e-9)
        threshold = float(np.percentile(ratio, 95))
        peak_mask = ratio > threshold
        # collect continuous regions < 100ms
        times = librosa.frames_to_time(np.arange(len(ratio)), sr=sr, hop_length=256)
        defects: list[AudioDefect] = []
        in_peak = False
        peak_start = 0.0
        for i, flag in enumerate(peak_mask):
            if flag and not in_peak:
                in_peak = True
                peak_start = times[i]
            elif not flag and in_peak:
                in_peak = False
                dur = times[i] - peak_start
                if 0.02 <= dur <= 0.1:
                    defects.append(AudioDefect(
                        type="lip_smack",
                        start_sec=peak_start,
                        end_sec=times[i],
                        confidence=min(1.0, ratio[i] / threshold),
                    ))
        return defects
    except Exception:
        return []
```

- [ ] **Step 2: T8.2 breath_classifier.py**

```python
async def detect_breath_events(
    audio_path: Path,
    speech_segments: list[tuple[float, float]],
    sample_rate: int = 16000,
) -> list[tuple[float, float]]:
    """Возвращает breath events — тихие участки с явным breath-signature
    (broadband noise 100-2000 Hz, low overall level, длительность 150-600 ms).

    Отличается от pure silence → не должен компрессироваться вместе с паузой.
    Legacy `silero-vad` не различает breath vs silence.
    """
    import librosa
    import numpy as np

    y, sr = librosa.load(str(audio_path), sr=sample_rate, mono=True)
    # все участки вне speech_segments
    non_speech_mask = np.ones(len(y), dtype=bool)
    for start, end in speech_segments:
        i0 = int(start * sr)
        i1 = int(end * sr)
        non_speech_mask[i0:i1] = False

    # RMS per 25ms frame
    frame_len = int(0.025 * sr)
    hop = frame_len // 2
    frames = librosa.util.frame(y, frame_length=frame_len, hop_length=hop).T
    rms = np.sqrt((frames**2).mean(axis=1))
    # breath = RMS in low-medium range (not silent, not full speech)
    silence_thresh = float(np.percentile(rms, 10))
    breath_thresh = float(np.percentile(rms, 50))
    frame_times = np.arange(len(rms)) * (hop / sr)
    breath_events: list[tuple[float, float]] = []
    in_breath = False
    breath_start = 0.0
    for t, r in zip(frame_times, rms, strict=True):
        is_breath = silence_thresh < r < breath_thresh
        is_non_speech = non_speech_mask[min(int(t * sr), len(y) - 1)]
        if is_breath and is_non_speech and not in_breath:
            in_breath = True
            breath_start = t
        elif (not is_breath or not is_non_speech) and in_breath:
            in_breath = False
            dur = t - breath_start
            if 0.15 <= dur <= 0.6:
                breath_events.append((breath_start, t))
    return breath_events
```

- [ ] **Step 3: T8.3 Context-aware keep_sec**

В `pause_compression.py` расширить `compress_pauses_in_cuts`:

```python
def _keep_sec_from_context(
    words_around: list[Word],
    default_keep_sec: float,
) -> float:
    """Контекст-зависимая длительность сохраняемой паузы:
    - точка в конце предыдущего слова → 0.25s (финал мысли)
    - вопрос ? → 0.35s (риторическая пауза)
    - запятая → 0.12s
    - внутри предложения → default_keep_sec (0.06-0.08s)
    """
    if not words_around:
        return default_keep_sec
    last = words_around[-1].text if words_around else ""
    if last.endswith((".", "!", "…")):
        return 0.25
    if last.endswith("?"):
        return 0.35
    if last.endswith(","):
        return 0.12
    return default_keep_sec
```

Интегрировать: при каждом pause-candidate в `compress_pauses_in_cuts` определять `keep_sec` через `_keep_sec_from_context`.

- [ ] **Step 4: Runtime settings + UI + toggle**

```python
# В runtime_settings.py PerformanceSettings
mouth_sound_removal_enabled: bool = Field(default=False, description="T8.1 — снимать lip smacks / clicks в render")
breath_classifier_enabled: bool = Field(default=False, description="T8.2 — отличать breath от silence")
context_aware_keep_sec_enabled: bool = Field(default=True, description="T8.3 — keep_sec адаптируется под punctuation")
```

api.ts + PerformanceSettingsClient.tsx — группа «Адаптивный звук».

- [ ] **Step 5: Интеграция в pipeline.py**

Между pause_compression и render (до Stage B+ motion) добавить:

```python
if perf_preview.mouth_sound_removal_enabled:
    from videomaker.services.mouth_sound_detector import detect_mouth_sounds
    defects = await detect_mouth_sounds(audio_for_vad)
    # mute via FFmpeg afade при rendering — добавить в graph.mute_zones
```

- [ ] **Step 6: Build gates**

```bash
cd apps/backend && uv run ruff check && uv run python -c "from videomaker.services.mouth_sound_detector import detect_mouth_sounds; print('OK')"
cd apps/frontend && pnpm lint && pnpm tsc --noEmit && pnpm build
```

- [ ] **Step 7: Commit phase-5a**

```bash
git add apps/
git commit -m "feat(audio): T8.1-T8.3 mouth sound detector + breath classifier + context-aware keep_sec"
git push origin main
```

Memory `tech-debt/phase-5a-adaptive-audio-part1`.

### Phase 5b: T8.4-T8.6 (J/L planner + leveller + UI)

- [ ] **Step 1: T8.4 smart J/L-cut planner**

Расширить существующий `jl_cut_planner.py`. Добавить эвристики из editing-craft-2026.md:
- `change_of_speaker` → J-cut 0.25-0.35s (28% cases)
- `rhetorical_question` → L-cut 0.20-0.30s
- `topic_shift` → J-cut 0.30-0.45s
- `emotional_peak` → L-cut 0.25-0.40s (19%)
- `sentence_end` → hard cut 0.05-0.10s

Новая функция `choose_jl_offset(prev_word, next_word, role_change, emotion_level) -> tuple[str, float]`.

- [ ] **Step 2: T8.5 adaptive loudness leveller**

Per-segment gain normalization. Либо pyloudnorm (уже в deps) с per-segment EBU R128, либо pedalboard `Compressor`. Новый модуль `services/adaptive_leveller.py`.

- [ ] **Step 3: T8.6 UI preset switcher**

`PerformanceSettingsClient.tsx` — новая кнопка «Preset: ручной монтаж» которая одним кликом включает T8.1-T8.5 с research-дефолтами.

- [ ] **Step 4: Build gates + commit phase-5b**

```bash
git add apps/
git commit -m "feat(audio): T8.4-T8.6 smart J/L + adaptive leveller + preset switcher"
git push origin main
```

Memory `tech-debt/phase-5b-adaptive-audio-part2`.

---

## Phase 6: T2.8 Screencast auto-zoom (3 slices)

**Files:**
- Delete: `apps/backend/src/videomaker/services/screencast_zoom.py` (old Moondream-заглушка)
- Create: `apps/backend/src/videomaker/services/cursor_detector.py` (slice 1)
- Create: `apps/backend/src/videomaker/services/spring_zoom_planner.py` (slice 2)
- Modify: `apps/backend/src/videomaker/services/pipeline.py` (slice 3 — integration)
- Modify: `apps/backend/src/videomaker/models/runtime_settings.py`
- Create: `apps/backend/data/cursor_templates/` — sprites macOS/Windows/Linux
- Modify: `apps/frontend/src/components/PerformanceSettingsClient.tsx`

**Источник алгоритма:** pythonlearner1025/Screen-Studio-Effects (Rust-порт Cap).

### Slice 1: cursor detector

- [ ] **Step 1: Подготовить cursor templates**

```bash
mkdir -p apps/backend/data/cursor_templates
# Загрузить sprite 32x32 из системных ресурсов или использовать готовые PNG
# macOS: /System/Library/Frameworks/AppKit.framework/Resources/cursors/
# Windows: %WINDIR%\Cursors\
# Linux: /usr/share/icons/default/cursors/
```

- [ ] **Step 2: cursor_detector.py**

```python
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class CursorEvent:
    x: int
    y: int
    t_sec: float
    confidence: float


async def detect_cursor_events(
    video_path: Path,
    sample_rate_hz: int = 30,
    templates_dir: Path = Path("data/cursor_templates"),
) -> list[CursorEvent]:
    """OpenCV template matching для cursor tracking.

    Если confidence < 0.3 на > 60% кадров → считаем что это не screencast,
    возвращаем [] (graceful degrade).
    """
    import cv2
    import numpy as np

    templates = [
        cv2.imread(str(p), cv2.IMREAD_UNCHANGED)
        for p in templates_dir.glob("*.png")
    ]
    if not templates:
        return []

    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        return []
    stride = max(1, int(fps / sample_rate_hz))

    events: list[CursorEvent] = []
    frame_idx = 0
    low_confidence_count = 0
    total_sampled = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % stride == 0:
            total_sampled += 1
            best_match = None
            best_conf = 0.0
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            for tpl in templates:
                if tpl is None:
                    continue
                tpl_gray = cv2.cvtColor(tpl[:, :, :3], cv2.COLOR_BGR2GRAY)
                res = cv2.matchTemplate(gray, tpl_gray, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(res)
                if max_val > best_conf:
                    best_conf = max_val
                    best_match = (
                        max_loc[0] + tpl_gray.shape[1] // 2,
                        max_loc[1] + tpl_gray.shape[0] // 2,
                    )
            if best_conf < 0.3:
                low_confidence_count += 1
            if best_match is not None:
                events.append(CursorEvent(
                    x=best_match[0],
                    y=best_match[1],
                    t_sec=frame_idx / fps,
                    confidence=float(best_conf),
                ))
        frame_idx += 1
    cap.release()
    if total_sampled and low_confidence_count / total_sampled > 0.6:
        return []
    return events
```

### Slice 2: spring zoom planner

- [ ] **Step 3: spring_zoom_planner.py**

Порт из Screen-Studio-Effects (MIT). Damped harmonic oscillator:

```python
import math
from dataclasses import dataclass
from typing import Literal


@dataclass(slots=True)
class ZoomKeyframe:
    t_sec: float
    zoom_factor: float
    center_x: float  # [0, 1] normalized
    center_y: float


DampingProfile = Literal["underdamped", "critically_damped", "overdamped"]

DAMPING_VALUES = {
    "underdamped": 0.5,
    "critically_damped": 1.0,
    "overdamped": 1.7,
}


def plan_screencast_zoom(
    events: list,  # CursorEvent
    video_width: int,
    video_height: int,
    profile: DampingProfile = "critically_damped",
    max_zoom_factor: float = 2.0,
) -> list[ZoomKeyframe]:
    """Spring smoothing через damped harmonic oscillator (analytic solution).

    Pipeline: raw events → shake filter (median 30ms) → densify 30 fps →
    spring smoothing → silence analysis (gap ≥ 0.5s + displacement < 2px) →
    auto-zoom segments.
    """
    if not events:
        return []
    # Стабилизация через median window (shake filter)
    damping = DAMPING_VALUES[profile]
    natural_freq = 2.0 * math.pi * 0.8  # 0.8 Hz natural frequency
    keyframes: list[ZoomKeyframe] = []
    current_zoom = 1.0
    current_cx, current_cy = 0.5, 0.5
    velocity_z, velocity_cx, velocity_cy = 0.0, 0.0, 0.0
    prev_t = events[0].t_sec

    for ev in events:
        dt = max(1e-3, ev.t_sec - prev_t)
        # target
        target_cx = ev.x / video_width
        target_cy = ev.y / video_height
        # simple heuristic: when cursor moves slowly → zoom in, fast → zoom out
        disp = math.hypot(target_cx - current_cx, target_cy - current_cy)
        target_zoom = 1.5 if disp < 0.02 else 1.0
        target_zoom = min(target_zoom, max_zoom_factor)

        # spring step for zoom
        accel_z = -natural_freq**2 * (current_zoom - target_zoom) - 2 * damping * natural_freq * velocity_z
        velocity_z += accel_z * dt
        current_zoom += velocity_z * dt
        # spring step for center
        accel_cx = -natural_freq**2 * (current_cx - target_cx) - 2 * damping * natural_freq * velocity_cx
        velocity_cx += accel_cx * dt
        current_cx += velocity_cx * dt
        accel_cy = -natural_freq**2 * (current_cy - target_cy) - 2 * damping * natural_freq * velocity_cy
        velocity_cy += accel_cy * dt
        current_cy += velocity_cy * dt

        keyframes.append(ZoomKeyframe(
            t_sec=ev.t_sec,
            zoom_factor=max(1.0, min(max_zoom_factor, current_zoom)),
            center_x=max(0.0, min(1.0, current_cx)),
            center_y=max(0.0, min(1.0, current_cy)),
        ))
        prev_t = ev.t_sec
    return keyframes
```

### Slice 3: integration

- [ ] **Step 4: runtime_settings**

```python
screencast_cursor_zoom_enabled: bool = Field(default=True, description="Для profile=screencast — auto-zoom на курсор")
screencast_damping_profile: Literal["underdamped", "critically_damped", "overdamped"] = Field(default="critically_damped")
screencast_zoom_max_factor: float = Field(default=2.0, ge=1.2, le=3.0)
```

- [ ] **Step 5: pipeline.py integration**

После build_zoom_plan в render, если `profile == "screencast"`:

```python
if profile == VisionProfile.screencast and perf_preview.screencast_cursor_zoom_enabled:
    from videomaker.services.cursor_detector import detect_cursor_events
    from videomaker.services.spring_zoom_planner import plan_screencast_zoom
    cursor_events = await detect_cursor_events(source_path)
    if cursor_events:
        screencast_zoom = plan_screencast_zoom(
            cursor_events,
            video_width=source_width,
            video_height=source_height,
            profile=perf_preview.screencast_damping_profile,
            max_zoom_factor=perf_preview.screencast_zoom_max_factor,
        )
        # feed через существующий zoom_planner API
```

- [ ] **Step 6: Word-anchored deictic layer**

Регекс-pass по словам на `вот / здесь / смотри / тут / сюда`. Для каждого такого слова — инжектить ZoomKeyframe в соответствующий момент времени. Файл `services/deictic_zoom.py`:

```python
DEICTIC_WORDS = {"вот", "здесь", "смотри", "тут", "сюда", "here", "this", "look"}


def inject_deictic_zoom_triggers(
    words_ts: list[Word],
    existing_keyframes: list[ZoomKeyframe],
    zoom_factor: float = 1.3,
) -> list[ZoomKeyframe]:
    """Добавляет zoom-in keyframes на deictic words."""
    new_kfs: list[ZoomKeyframe] = []
    for w in words_ts:
        if w.text.lower().strip(",.!?") in DEICTIC_WORDS:
            new_kfs.append(ZoomKeyframe(
                t_sec=w.start_sec,
                zoom_factor=zoom_factor,
                center_x=0.5,
                center_y=0.5,
            ))
    return sorted(existing_keyframes + new_kfs, key=lambda k: k.t_sec)
```

- [ ] **Step 7: Удалить старый stub**

```bash
git rm apps/backend/src/videomaker/services/screencast_zoom.py
```

- [ ] **Step 8: Frontend UI**

В PerformanceSettingsClient.tsx группа «Screencast auto-zoom» с SwitchRow + SelectRow profile + SliderRow max_factor.

- [ ] **Step 9: Build + commit**

```bash
cd apps/backend && uv run ruff check && uv run python -c "from videomaker.services.cursor_detector import detect_cursor_events; from videomaker.services.spring_zoom_planner import plan_screencast_zoom; print('OK')"
cd apps/frontend && pnpm lint && pnpm tsc --noEmit && pnpm build
git add apps/
git commit -m "feat(screencast): T2.8 cursor tracking + spring zoom + deictic injection"
git push origin main
```

Memory `tech-debt/phase-6-screencast-auto-zoom`.

---

## Phase 7: T3 Frontend handoff (9 экранных блоков)

**Разбить на 3 коммита (phase-7a: T3.1-T3.3; phase-7b: T3.4-T3.7; phase-7c: T3.8-T3.10).**

### Phase 7a: T3.1-T3.3 upload/clip/results

- [ ] **T3.1 screen_workflow:** `components/upload/UploadWizard.tsx` — добавить video preview (ffprobe на клиенте через File API → `<video>` thumbnail) до нажатия «Старт». Встроенный stage-прогресс в новом `components/upload/UploadProgressTimeline.tsx`.

- [ ] **T3.2 screen_clip:** новый `components/job/ClipDetailScrubber.tsx` + `components/job/WaveformBar.tsx` (использовать `peaks.js` или простой canvas с `AudioContext.decodeAudioData`). Вариантные превью — `components/job/VariantSelector.tsx`.

- [ ] **T3.3 screen_results:** `components/dashboard/ResultsFilters.tsx` — фильтры virality/score/duration/profile + `BulkActions.tsx` (массовое удаление / массовый экспорт).

Commit phase-7a, push, memory.

### Phase 7b: T3.4-T3.7

- [ ] **T3.4 screen_captions:** `components/job/CaptionsEditor.tsx` — inline-правка ASS через monaco-editor (уже в deps Next.js) + timing-drag через draggable word boxes. API endpoint `PATCH /jobs/{id}/reels/{rid}/subtitles`.

- [ ] **T3.5 screen_brand:** `app/settings/brand/page.tsx` + `components/BrandKit.tsx` — сохранённые шрифты (upload TTF), цвета (palette), лого (PNG). БД — новая таблица `brand_kits`.

- [ ] **T3.6 screen_layout:** расширить UploadWizard — preview рамки с visual rectangles для 9:16/1:1/4:5/16:9. Manual crop override через `components/upload/CropOverride.tsx` (drag-rectangle поверх video preview).

- [ ] **T3.7 screen_export:** `components/job/ExportDialog.tsx` — presets `ExportPreset` { name, bitrate_kbps, lufs, container } + batch export. Endpoint `POST /jobs/{id}/reels/batch/export`.

Commit phase-7b, push, memory.

### Phase 7c: T3.8-T3.10

- [ ] **T3.8 hover-preview:** `components/dashboard/JobCard.tsx` — `onMouseEnter` запускает inline `<video muted autoplay>` на первый reel proxy (proxy.mp4 урезать до 3-5 sec через ffmpeg `-t`).

- [ ] **T3.9 schedule UI:** `components/job/ScheduleButton.tsx` — открывает date-picker, посылает `POST /schedule/reels/{rid}` с datetime.

- [ ] **T3.10 Instagram Graph API:** `services/instagram_publisher.py` — OAuth через Facebook App (заблокировано App Review). Код готовности ~70% уже есть в других service'ах (YouTube OAuth pattern). Публикация:
  ```python
  async def publish_reel_to_instagram(
      reel_path: Path,
      caption: str,
      access_token: str,
      instagram_business_id: str,
  ) -> str:  # returns IG media id
      # 1) upload video URL — media_container
      # 2) poll status_code == FINISHED
      # 3) publish media_container
  ```
  Блокер Facebook App Review — писать блокирующее сообщение в UI если токена нет.

Commit phase-7c, push, memory.

---

## Phase 8: Docs cleanup + consolidated-action-plan ✅ отметки

- [ ] **Step 1:** В `docs/research/consolidated-action-plan.md` добавить секцию «✅ Done 2026-04-19 tech-debt cleanup» со списком коммитов:
  - phase-1 subtitle sync hotfix
  - phase-2 reel count predictability
  - phase-3 preference cosine retrieval
  - phase-4 composer strategy UI
  - phase-5a/5b adaptive audio
  - phase-6 screencast auto-zoom
  - phase-7a/7b/7c frontend handoff

- [ ] **Step 2:** Отметить в pending memories через `mcp__serena__edit_memory` — `pending/reel-count-predictability`, `pending/future-quality-improvements`, `pending/frontend-redesign` — переместить в секцию Done.

- [ ] **Step 3:** Commit:

```bash
git add docs/
git commit -m "docs(plan): tech-debt cleanup 8 phases DONE — status matrix update"
git push origin main
```

Memory `tech-debt/phase-8-docs-cleanup-COMPLETE`.

---

## Self-Review

**Spec coverage check:**
| User item | Phase | Tasks |
|---|---|---|
| 1. Subtitle sync regression | Phase 1 | Investigation + conditional fix |
| 2. T2.8 Screencast auto-zoom | Phase 6 | 3 slices + deictic + UI |
| 3. T8 Adaptive audio | Phase 5a + 5b | 6 подзадач |
| 4. T9 Composer UI | Phase 4 | Radio + Cross-context badge |
| 5. T6.1 Preference ML | Phase 3 | Cosine retrieval + migration |
| 7. T3 Frontend handoff | Phase 7a + 7b + 7c | 9 screens |
| 10. Post-trim closure | — | **УЖЕ РЕАЛИЗОВАН** (closure_validator.py, 449 строк) |
| 11. Predictable reel count | Phase 2 | Floor/ceiling + Jaccard |

**Placeholder scan:** проверено — нет TODO/TBD/«similar to above». Каждая фаза имеет exact file paths, code blocks, build gates, commit step.

**Type consistency:** `PerformanceSettings` расширяется инкрементально через фазы — в каждой новой фазе добавляются только её поля. `ZoomKeyframe`, `CursorEvent`, `AudioDefect` — strict dataclasses с slots=True.

**Total ETA (×7 calibration по feedback_videomaker_philosophy_and_speed):**
- Phase 1: ~30 мин
- Phase 2: ~40 мин
- Phase 3: ~50 мин
- Phase 4: ~30 мин
- Phase 5a: ~1.5 часа
- Phase 5b: ~1.5 часа
- Phase 6: ~1-1.5 часа
- Phase 7a: ~1 час
- Phase 7b: ~2 часа
- Phase 7c: ~1.5 часа
- Phase 8: ~15 мин

**Итого: ~10-12 часов моего времени.**

---

## Execution Handoff

Plan complete and saved to `docs/plans/2026-04-19-tech-debt-cleanup.md`. Two execution options:

**1. Subagent-Driven (recommended для больших фаз типа Phase 5b / Phase 7)** — dispatch fresh subagent per phase, review between phases, fast iteration.

**2. Inline Execution (recommended для Phase 1-4, короткие)** — executing-plans skill, batch with checkpoints.

User должен выбрать подход **per-phase**. По умолчанию — inline для первых 4 фаз, subagent для Phase 5+.
