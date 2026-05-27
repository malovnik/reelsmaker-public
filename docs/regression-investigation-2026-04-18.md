# Регрессия нарезки — расследование 2026-04-18

**Жалобы:** 
1. `44b8eb62` — попросил 110 рилсов (2.5 ч видео), получил 61.
2. `437cb524` — два рилса (r1, r2) с дублем одной фразы подряд.

## Симптом 1 — хард-кап на ранжирование (bug для всех видео длиннее 30 мин)

**Файл:** `apps/backend/src/videomaker/services/reducer.py:52`

```python
MAX_RANKED_ITEMS = 60          # жёсткий потолок, без scaling
LLM_RANK_INPUT_CAP = 80        # сколько evidence LLM ranker видит на входе
```

Эти константы **hardcoded** и не растут с длительностью.

### Что произошло в job 44b8eb62 (2.5 ч видео)

```
evidence_pre_dedup: 353         ← 6 text-агентов нашли много 
evidence_post_dedup: 257        ← reduce схлопнул дубли
  ↓
LLM_RANK_INPUT_CAP = 80          ← ranker видит top-80 по strength
  ↓
MAX_RANKED_ITEMS = 60            ← output обрезается до 60
  ↓
ranked_evidence_count: 60        ← всё, дальше пайплайн работает с 60 item
  ↓
candidates_total: 64             ← 60 singles + 4 variants
  ↓
uniqueness filter max_count=121  ← target 110 + tolerance 11
  ↓
actual_reel_count: 61            ← всё что смог, физически нет больше
```

Target 110 недостижим **потому что кандидатов просто нет**. Фильтр не виноват — виноват верхний потолок reducer.

### Fix — масштабирование по длительности

Предлагаемые формулы:

```python
# reducer.py
def _compute_rank_caps(source_duration_sec: float) -> tuple[int, int]:
    duration_min = source_duration_sec / 60.0
    # База для 30-мин видео: 60 ranked, 80 input. Растём линейно до cap.
    ranked_cap = min(300, max(60, round(duration_min * 2.0)))   # 150 мин → 300
    input_cap = min(400, max(80, round(duration_min * 2.5)))    # 150 мин → 400
    return ranked_cap, input_cap
```

- 10 мин: 60 ranked / 80 input (прежнее поведение, без регрессии)
- 30 мин: 60 / 80 (прежнее)
- 60 мин: 120 / 150
- 150 мин: 300 / 375
- 300 мин: 300 / 400 (cap)

`LLM_RANK_INPUT_CAP` — именно top-80-по-strength; сейчас LLM **не видит** 180+ потенциально хороших evidence на длинных видео. Он видит только 80 «сильных» — а сильными часто оказываются те что в начале видео.

### Побочный эффект

Разрешение reducer-cap'а косвенно даёт 110+ кандидатов в composer, но **не гарантирует 110 accepted**: если Jaccard-фильтр (0.65) косит как «дубли» — снова недобор. Смотрим отдельно.

---

## Симптом 2 — дубль фразы (overlap сегментов внутри рилса)

**Файл:** `apps/backend/src/videomaker/services/reels_composer.py:_pull_closure_from_arc` (Task #28) + отсутствие dedup по времени внутри группы.

### Что произошло в job 437cb524 (reel r1)

```
segments:
  [0] 439.1 – 461.4 (22.3s)  role=hook     ← основной кусок речи
  [1] 444.9 – 457.4 (12.5s)  role=peak     ← ПОЛНОСТЬЮ внутри hook!
  [2] 554.2 – 571.4 (17.2s)  role=payoff
```

ffmpeg concatенирует их подряд — зритель слышит:
- 439.1 → 461.4 (hook, внутри которого **звучит фраза из 444.9-457.4**)
- 444.9 → 457.4 (peak, **ровно та же фраза снова**)
- 554.2 → 571.4 (payoff)

То же в reel r2: сегменты [455.5-461.4] (хвост hook) и [444.9-457.4] (peak) перекрываются на 1.9 с.

### Как это оказалось в одном рилсе

Stage 7 Story Doctor составляет arc из segments. На один кусок источника могут указать **два разных агента** (например, `hook_hunter` и `emotional_peak_finder`). Оба попадают в arc как отдельные StorySegment с разными `evidence_id`, **но перекрывающимися** `source_start_sec / source_end_sec`. 

Composer's `_arc_group_to_candidate` не делает temporal-dedup — просто конвертирует StorySegment → ReelSegment в исходном порядке. Плюс `_pull_closure_from_arc` (Task #28) может ещё и **добавить четвёртый сегмент**, если в группе нет payoff — но его guard `(evidence_id, source_start_sec)` не ловит temporal overlap.

### Fix — временной dedup сегментов внутри рилса

Добавить в `_arc_group_to_candidate` (или непосредственно в `_renumber_and_finalize`) шаг:

```python
def _dedupe_temporal_overlaps(segments: list[ReelSegment]) -> list[ReelSegment]:
    """Убирает сегменты, чей временной диапазон полностью содержится в
    предыдущем принятом, либо перекрывается с ним >= 60%.
    
    Сохраняет порядок принятия (hook первый), но отбрасывает 'дубли вживую'.
    """
    accepted: list[ReelSegment] = []
    for seg in segments:
        overlap = False
        for prev in accepted:
            inter_start = max(seg.source_start, prev.source_start)
            inter_end = min(seg.source_end, prev.source_end)
            inter = max(0.0, inter_end - inter_start)
            seg_len = max(0.001, seg.source_end - seg.source_start)
            if inter / seg_len >= 0.6:  # 60%+ перекрытие = дубль
                overlap = True
                break
        if not overlap:
            accepted.append(seg)
    return accepted
```

Применять в `_arc_group_to_candidate` после конвертации StorySegment→ReelSegment, перед возвратом кандидата. И в `_renumber_and_finalize` как safety.

---

## Почему именно сейчас это проявилось

- **110 → 61** всегда было на длинных видео, но ты до этого не тестировал с target > 60. До Task #31 (5-часовое масштабирование) UI не давал поставить > 30. Теперь слайдер идёт до 225, а reducer-cap остался старый.
- **Дубль фразы** — функциональный риск появился с **Task #28** (cross-group pull), когда `_pull_closure_from_arc` стал добавлять сегменты не по порядку времени. До этого segments всегда шли монотонно по арке. Реально проявляется когда Story Doctor помещает два **разных evidence_id** на один кусок источника.

---

## Ничто из этого не связано с сегодняшним коммитом `cedf8a3`

- `reducer.py:52` — не трогал.
- `reels_composer.py` — не трогал.
- `_pull_closure_from_arc` — существует с коммита `151ec24` (Task #28).

Override профилей в БД (story_weight=0.75) **усиливает** проблему через `apply_profile_weights`, но не создаёт её.

---

## Предлагаемый хотфикс — один коммит, два файла

1. `reducer.py`: заменить константы `MAX_RANKED_ITEMS=60` / `LLM_RANK_INPUT_CAP=80` на функцию `_compute_rank_caps(duration_sec)`. ~15 строк.
2. `reels_composer.py`: добавить `_dedupe_temporal_overlaps()` + вызов в `_arc_group_to_candidate`. ~25 строк.
3. Смысловая проверка: сбросить override профилей (`DELETE FROM runtime_settings WHERE key LIKE 'vision_profile_override_%'`), запустить тот же job. Не пишем unit-тесты (user rule).

~40 строк кода + 1 DB-cleanup. ~30 мин работы.

## После фикса — ожидания

- Job 44b8eb62-стиль (2.5 ч, 110 target) → ~90–110 рилсов (зависит от Jaccard-фильтра; если снова недобор — смотрим uniqueness threshold adaptive).
- Job 437cb524-стиль (дубль фразы) → сегмент peak [444.9-457.4] отфильтруется как overlap hook [439.1-461.4]. Reel r1 станет 2-сегментным (hook + payoff).

`rhythm_pacing: рваный` в обоих job — следствие проблемы с overlap (рывки timeline), после fix должно выравняться.
