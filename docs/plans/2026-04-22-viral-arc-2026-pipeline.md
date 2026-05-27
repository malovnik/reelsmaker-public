# Viral Arc 2026 Pipeline + Face Track Fix — Implementation Plan

> **Status (2026-04-22): ✅ ЗАВЕРШЕНО**. 8 tasks выполнены, pushed в origin/feat/glm-provider.
> E2E smoke: job `e5615cc8` на 95-мин видео → **18 рилсов** avg score 83.1, narrative_mode=viral_2026.
> Face tracker conditional: default OFF, job `0d77cc65` подтвердил `face_track_skipped`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use `ralph-loop-local:ralph-loop` для автономного исполнения (user preference). Каждая Task — atomic commit + push.

**Goal:** Добавить простой OpusClip-style pipeline параллельно существующему Kartoziya (toggle через existing `narrative_mode` enum), плюс убрать хардкод always-on face_tracker в render stage.

**Architecture:** Единственный LLM-call per chunk 20К знаков → модель возвращает готовые `{hook, segments[], save_value, viral_score}` по manifest'у Живого Кадра 2026. Chunks обрабатываются параллельно через Flash Lite, cross-chunk dedup по temporal overlap >70%. Весь output нормализуется в `ReelPlan` список для downstream `render_stage`. Legacy pipeline сохраняется за дефолтом `narrative_mode="bottom_up"`.

**Tech Stack:** Python 3.12 + FastAPI + Pydantic v2, Gemini Flash Lite только, async/asyncio.Semaphore. Frontend Next.js 16 + React 19 + Tailwind 4 — `NarrativeModeGroup.tsx` уже существует, расширяется одним option.

---

## File Structure

### Backend create
- `apps/backend/src/videomaker/services/prompts_data/viral_2026.md` — system prompt с manifest + JSON schema (~8К знаков)
- `apps/backend/src/videomaker/services/viral_arc_builder.py` — chunking + parallel LLM + dedup (~350 LOC)

### Backend modify
- `apps/backend/src/videomaker/services/prompts.py` — +`PromptKey.viral_2026`, +`VIRAL_2026_PROMPT`, entry в `DEFAULT_PROMPTS`
- `apps/backend/src/videomaker/models/runtime_settings.py:55` — `NarrativeMode` расширяется `"viral_2026"`; описание в `Field.description`; `face_tracker_enabled` новое поле
- `apps/backend/src/videomaker/services/pipeline_stages/analysis.py:234-255` — branching: `viral_2026` → новая функция `_run_viral_2026_branch`
- `apps/backend/src/videomaker/services/pipeline_stages/render.py:425-456` + `262-267` — conditional face_tracking по флагу из runtime settings

### Frontend modify
- `apps/frontend/src/components/settings/performance-groups/NarrativeModeGroup.tsx` — +option `viral_2026` в meta map
- `apps/frontend/src/components/settings/performance-groups/DefaultsGroup.tsx` (или отдельный MotionGroup) — toggle `face_tracker_enabled`
- `apps/frontend/src/lib/api/settings.ts` — тип `narrative_mode` расширяется; добавить `face_tracker_enabled`

---

## Task 1: Prompt file (manifest + JSON schema)

**Files:**
- Create: `apps/backend/src/videomaker/services/prompts_data/viral_2026.md`

- [ ] **Step 1: Создать prompt-файл**

Write `apps/backend/src/videomaker/services/prompts_data/viral_2026.md`:

```markdown
# IDENTITY

Ты — монтажёр вирусных рилсов 2026. Задача: найти в транскрипте talking-head видео готовые рилсы по структуре 5 блоков и Манифесту Живого Кадра.

Возвращай JSON согласно OUTPUT SCHEMA в конце.

# STRUCTURE (5 блоков, оптимум 45-60 сек)

## Блок 1. Hook — 0:00–0:02
Pattern interrupt, визуал + текст-дубль. Типы:
- Contrarian: «Все делают X. Это убивает охват»
- Curiosity gap: открытая петля, отложить разгадку
- Result-first: «Собрал 200k просмотров за ночь. Вот что сработало»
- Identity hook: адресная реплика «если тебе 35+ и ты ведёшь канал...»
- Pain point: конкретная боль зрителя вслух

## Блок 2. Context/Counter — 0:02–0:08
Не отдавай ответ сразу. Контекст, история, или counter «я это уже знаю».

## Блок 3. Payoff/Core — 0:08–0:35
ОДНА мысль. Не список из пяти. Смена плана 2-4 сек. Равномерная ценность (не frontload, не backload). Темп речи +20% от обычного.

## Блок 4. Re-hook/Twist — 0:35–0:45
Замыкание петли, неожиданный поворот, дожим инсайта другой формулировкой. Второй пик.

## Блок 5. CTA/Loop — 0:45–0:55
Одна конкретная команда ИЛИ loop-концовка (финал замыкается на первый кадр).

# HOOK-FIRST FLASH-FORWARD (ПРИОРИТЕТ)

Самая провокативная фраза ролика → в первые 3 секунды (даже если в оригинале она была в середине/конце). Потом разгрузка контекста → развитие → кульминация закрывает петлю.

Возвращай MULTI-SEGMENT рилс с role полем:
- `flashforward_hook` — провокация сначала
- `context_development` — контекст и развитие
- `payoff_closure` — закрытие петли

Сегменты склеиваются в порядке массива.

# МАНИФЕСТ ЖИВОГО КАДРА 2026

**I. Замкнутая дуга.** Вход (шок/вопрос/Разрыв шаблона) → Развитие (опыт) → Катарсис (финальный гвоздь). Если зритель не может пересказать мораль одной фразой — в корзину.

**II. Алгоритмические трюки:**
- Адский хуяк: 1.5 сек, шок без прелюдий
- Контрапункт: предпринимательская жесткость × философское дно
- Save-value: алгоритм/афоризм/тактика, которые захочется сохранить

**III. Стилистическая хирургия:**
- Стерилизация канцелярита: «в контексте вышеупомянутых событий» — в морг. Только глаголы и «грязная» живая речь
- Ритм Кардиограмма: шепот перед важным, мат от восторга
- Антагонизм: видео против посредственности, успешного успеха, скуки

**IV. Ударный финал.** Последняя фраза = точка в шахматной партии. Нервный смешок или 5 секунд тишины. Среднего не дано.

# РЕЖЬ БЕЗЖАЛОСТНО

На входе: приветствия («добрый день», «всем привет»), проверки звука, оргмоменты («кто подключился»), представление участников без контента, артефакты транскрипции.

В середине: упоминания чатов/курсов/клубов/подписок, связки «ну, собственно»/«в общем-то», повторы одной мысли, переходы между спикерами без контента, технические паузы.

В финале: «спасибо за внимание», «был рад пообщаться», вопросы «есть ли вопросы?», переход к следующим темам. Ролик закрывается НА ПИКЕ.

# LENGTH TACTICS

| Длина | Для чего | Риск |
|-------|----------|------|
| 7-15 сек | Один хук + один payoff | Мало места |
| 20-35 сек | Talking head с инсайтом | Нужен плотный монтаж |
| **45-60 сек** | Сторителлинг, кейс, разбор | Средний risk drop-off |
| 60+ сек | Авторитет и лояльная ЦА | Completion обрушивается |

Формула: самая короткая длина, на которой мысль доносится полностью.

# OUTPUT SCHEMA

Возвращай ТОЛЬКО JSON (без markdown fence, без комментариев). Формат:

```json
{
  "reels": [
    {
      "reel_id": "r1",
      "title": "Короткий провокативный заголовок",
      "hook_type": "contrarian",
      "segments": [
        {"start": 45.2, "end": 48.0, "role": "flashforward_hook", "reason": "..."},
        {"start": 10.5, "end": 35.0, "role": "context_development", "reason": "..."},
        {"start": 48.0, "end": 52.0, "role": "payoff_closure", "reason": "..."}
      ],
      "target_duration_sec": 48.2,
      "save_value": "Что человек захочет сохранить (афоризм или алгоритм)",
      "viral_score": 78
    }
  ]
}
```

Правила:
- `hook_type` одно из: `contrarian`, `curiosity`, `result`, `identity`, `pain`
- `role` одно из: `flashforward_hook`, `context_development`, `payoff_closure`, `hook`, `development`, `payoff`
- `viral_score` integer 0..100 (твоя честная оценка потенциала, не раздувай)
- `start`/`end` — seconds от начала ВИДЕО (не чанка), округление до 0.01
- Минимум 1 сегмент, максимум 5 сегментов в рилсе
- `target_duration_sec` должен ≈ равняться сумме длительностей сегментов

Возвращай МАКСИМУМ столько рилсов, сколько реально вирусных моментов в чанке. Не раздувай — лучше 2 сильных, чем 10 средних. Нет вирусных моментов → `{"reels": []}`.
```

- [ ] **Step 2: Commit**

```bash
git -C /Users/malovnik/Documents/Dev/videomaker add apps/backend/src/videomaker/services/prompts_data/viral_2026.md
git -C /Users/malovnik/Documents/Dev/videomaker commit -m "feat(viral_2026): system prompt с manifest и JSON schema

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
git -C /Users/malovnik/Documents/Dev/videomaker push origin feat/glm-provider
```

---

## Task 2: PromptKey enum + DEFAULT_PROMPTS registration

**Files:**
- Modify: `apps/backend/src/videomaker/services/prompts.py`

- [ ] **Step 1: Добавить enum value**

В `PromptKey` class после `clip_reducer = "clip_reducer_system"` добавить:

```python
    viral_2026 = "viral_2026_system"
```

- [ ] **Step 2: Загрузить файл + DEFAULT_PROMPTS**

Найти где загружаются prompts через `files(...)` pattern. Скорее всего есть секция с loading block. Добавить строку:

```python
VIRAL_2026_PROMPT = (files(_PROMPTS_PKG) / "viral_2026.md").read_text(encoding="utf-8")
```

(Имя `_PROMPTS_PKG` — проверить существующие строки, оно может быть `videomaker.services.prompts_data` или подобное. Копировать exact pattern от `STORY_DOCTOR_PROMPT` / `CLIP_REDUCER_PROMPT`.)

В `DEFAULT_PROMPTS` dict добавить entry:

```python
    PromptKey.viral_2026: VIRAL_2026_PROMPT,
```

- [ ] **Step 3: Build gates**

Run:
```bash
cd /Users/malovnik/Documents/Dev/videomaker/apps/backend && uv run ruff check src/videomaker/services/prompts.py && uv run pyright src/videomaker/services/prompts.py
```
Expected: `All checks passed` + `0 errors, 0 warnings, 0 informations`

- [ ] **Step 4: Smoke test import**

```bash
cd /Users/malovnik/Documents/Dev/videomaker/apps/backend && uv run python -c "from videomaker.services.prompts import PromptKey, DEFAULT_PROMPTS; assert PromptKey.viral_2026 in DEFAULT_PROMPTS; print('OK len=', len(DEFAULT_PROMPTS[PromptKey.viral_2026]))"
```
Expected: `OK len= <число >5000>`

- [ ] **Step 5: Commit**

```bash
git -C /Users/malovnik/Documents/Dev/videomaker add apps/backend/src/videomaker/services/prompts.py
git -C /Users/malovnik/Documents/Dev/videomaker commit -m "feat(viral_2026): PromptKey enum + DEFAULT_PROMPTS registration

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
git -C /Users/malovnik/Documents/Dev/videomaker push origin feat/glm-provider
```

---

## Task 3: NarrativeMode enum + face_tracker_enabled field

**Files:**
- Modify: `apps/backend/src/videomaker/models/runtime_settings.py:55`, `apps/backend/src/videomaker/models/runtime_settings.py` (PerformanceSettings block)

- [ ] **Step 1: Расширить enum**

Line 55:
```python
NarrativeMode = Literal["bottom_up", "chaptered", "map_reduce", "viral_2026"]
```

- [ ] **Step 2: Обновить description у narrative_mode field**

Найти `narrative_mode: NarrativeMode = Field(` (line ~269) и в `description` добавить:

```
"viral_2026 (OpusClip-parity simple) — один LLM call per chunk 20К знаков "
"эмиттит готовые рилсы по структуре 5 блоков Hook→Context→Payoff→Re-hook→CTA "
"и манифесту Живого Кадра. ~10-15 LLM calls на 90 мин видео вместо 80-120."
```

- [ ] **Step 3: Добавить face_tracker_enabled field**

Найти в `PerformanceSettings` класс подходящее место (после motion/auto-mode полей). Добавить:

```python
    face_tracker_enabled: bool = Field(
        default=False,
        description=(
            "Включает MediaPipe face tracking для face-centered base crop "
            "(fit_mode=fill). По умолчанию OFF — для 95% случаев не нужен: "
            "letterbox / manual / split с main_transform работают без face-keyframes. "
            "Включай только когда fit_mode=fill и важна композиция по лицу спикера. "
            "Риск зависания на больших видео (mediapipe на M-series Apple Silicon)."
        ),
    )
```

- [ ] **Step 4: Build gates**

```bash
cd /Users/malovnik/Documents/Dev/videomaker/apps/backend && uv run ruff check src/videomaker/models/runtime_settings.py && uv run pyright src/videomaker/models/runtime_settings.py
```

- [ ] **Step 5: Commit**

```bash
git -C /Users/malovnik/Documents/Dev/videomaker add apps/backend/src/videomaker/models/runtime_settings.py
git -C /Users/malovnik/Documents/Dev/videomaker commit -m "feat(runtime): narrative_mode=viral_2026 + face_tracker_enabled toggle

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
git -C /Users/malovnik/Documents/Dev/videomaker push origin feat/glm-provider
```

---

## Task 4: viral_arc_builder.py — chunking + parallel LLM + dedup

**Files:**
- Create: `apps/backend/src/videomaker/services/viral_arc_builder.py`

- [ ] **Step 1: Reference existing patterns**

Прочитать как другие services делают LLM parallel calls:
- `apps/backend/src/videomaker/services/narrative/chunk_scorer.py` — chunking + parallel scoring (похожая задача, изучить структуру)
- `apps/backend/src/videomaker/services/extraction_agents.py` или `analyzers/*` — parallel LLM через asyncio.Semaphore

Понять:
- Как получается `client` и `rate_limiter`
- Как делается `generate_json` на Flash Lite
- Как вытаскивается `CleanedTranscript.segments` с timestamps для чанкинга
- Как вызывается `llm_call` с prompt_key

- [ ] **Step 2: Написать viral_arc_builder.py**

Create `apps/backend/src/videomaker/services/viral_arc_builder.py`:

```python
"""Viral Arc 2026 pipeline — параллельный simple OpusClip-style builder.

Архитектура: транскрипт нарезается на chunks 20К знаков с overlap 2К,
каждый chunk отправляется в Flash Lite с system prompt manifest, LLM
возвращает готовые ``{hook, segments, save_value, viral_score}`` по
структуре 5 блоков. Chunks обрабатываются параллельно (asyncio.gather с
Semaphore), cross-chunk deduplication по temporal overlap >70%.

Контракт: `build_viral_arcs(transcript, *, cfg) -> list[ReelPlan]` — совместим
с downstream `pipeline_stages/render.py` как legacy bottom_up output.

Feature flag: `PerformanceSettings.narrative_mode == "viral_2026"`. Когда
другой mode — функция не вызывается, pipeline работает как раньше.
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from dataclasses import dataclass

from pydantic import BaseModel, Field, ValidationError

from videomaker.core.config import Settings
from videomaker.core.logging import get_logger
from videomaker.models.reel_plan import ReelPlan, ReelSegment
from videomaker.models.transcription import CleanedTranscript
from videomaker.services.llm_client import get_llm_client
from videomaker.services.prompt_store import get_prompt
from videomaker.services.prompts import PromptKey
from videomaker.services.rate_limiter import get_rate_limiter
from videomaker.services.tier_resolver import resolve_tier

log = get_logger(__name__)

_CHUNK_SIZE_CHARS = 20_000
_CHUNK_OVERLAP_CHARS = 2_500
_MAX_CONCURRENCY = 10
_DEDUP_OVERLAP_RATIO = 0.70
_MIN_SEGMENT_DURATION_SEC = 0.5
_MAX_SEGMENTS_PER_REEL = 5


class _LLMSegment(BaseModel):
    start: float = Field(ge=0.0)
    end: float = Field(ge=0.0)
    role: str = "development"
    reason: str = ""


class _LLMReel(BaseModel):
    reel_id: str = Field(min_length=1, max_length=32)
    title: str = ""
    hook_type: str = "curiosity"
    segments: list[_LLMSegment] = Field(min_length=1, max_length=_MAX_SEGMENTS_PER_REEL)
    target_duration_sec: float = Field(ge=5.0, le=120.0)
    save_value: str = ""
    viral_score: int = Field(ge=0, le=100)


class _LLMOutput(BaseModel):
    reels: list[_LLMReel] = Field(default_factory=list)


@dataclass(slots=True, frozen=True)
class _Chunk:
    index: int
    text: str
    start_sec: float
    end_sec: float


def _format_chunk_user_message(chunk: _Chunk) -> str:
    """User-сообщение: таймкодированный транскрипт + инструкция."""
    return (
        f"Chunk #{chunk.index} транскрипта. Временной window: "
        f"[{chunk.start_sec:.2f}, {chunk.end_sec:.2f}] сек от начала видео.\n\n"
        "Таймкоды в транскрипте (секунды от начала видео) — используй их в "
        "segments.start / segments.end.\n\n"
        "--- TRANSCRIPT START ---\n"
        f"{chunk.text}\n"
        "--- TRANSCRIPT END ---\n\n"
        "Верни JSON согласно OUTPUT SCHEMA. Никакого текста вне JSON."
    )


def _build_chunks(transcript: CleanedTranscript) -> list[_Chunk]:
    """Режет транскрипт на chunks 20К знаков с overlap 2.5К.

    Формат одной строки: `[SS.ss-EE.ee] текст\\n`. Timestamp позволяет LLM
    привязываться к реальным секундам, а не к абстрактному offset в чанке.
    """
    lines: list[tuple[float, float, str]] = []
    for seg in transcript.segments:
        lines.append((seg.start, seg.end, f"[{seg.start:.2f}-{seg.end:.2f}] {seg.text}"))

    chunks: list[_Chunk] = []
    current_lines: list[tuple[float, float, str]] = []
    current_chars = 0
    chunk_idx = 0

    i = 0
    while i < len(lines):
        start_sec, end_sec, line = lines[i]
        line_len = len(line) + 1

        if current_chars + line_len > _CHUNK_SIZE_CHARS and current_lines:
            chunk_text = "\n".join(l[2] for l in current_lines)
            chunks.append(
                _Chunk(
                    index=chunk_idx,
                    text=chunk_text,
                    start_sec=current_lines[0][0],
                    end_sec=current_lines[-1][1],
                )
            )
            chunk_idx += 1

            overlap_chars = 0
            overlap_lines: list[tuple[float, float, str]] = []
            for l in reversed(current_lines):
                if overlap_chars + len(l[2]) > _CHUNK_OVERLAP_CHARS:
                    break
                overlap_lines.insert(0, l)
                overlap_chars += len(l[2]) + 1
            current_lines = overlap_lines
            current_chars = overlap_chars

        current_lines.append((start_sec, end_sec, line))
        current_chars += line_len
        i += 1

    if current_lines:
        chunk_text = "\n".join(l[2] for l in current_lines)
        chunks.append(
            _Chunk(
                index=chunk_idx,
                text=chunk_text,
                start_sec=current_lines[0][0],
                end_sec=current_lines[-1][1],
            )
        )

    return chunks


def _strip_json_fence(raw: str) -> str:
    """LLM иногда оборачивает в ```json ... ```. Снимаем, чтобы парсер работал."""
    cleaned = raw.strip()
    fence_match = re.match(r"^```(?:json)?\s*\n(.*)\n```\s*$", cleaned, re.DOTALL)
    if fence_match:
        return fence_match.group(1).strip()
    return cleaned


async def _call_llm_for_chunk(
    chunk: _Chunk,
    *,
    system_prompt: str,
    cfg: Settings,
    semaphore: asyncio.Semaphore,
) -> list[_LLMReel]:
    """Один LLM call на chunk. Возвращает parsed reels или [] при ошибке."""
    async with semaphore:
        tier = resolve_tier("viral_arc_2026", cfg)
        client = await get_llm_client(tier=tier, cfg=cfg)
        rate_limiter = get_rate_limiter(tier.provider)
        user_message = _format_chunk_user_message(chunk)

        try:
            async with rate_limiter:
                raw_response = await client.generate_json(
                    system_prompt=system_prompt,
                    user_prompt=user_message,
                    model=tier.model,
                )
        except Exception:
            log.exception("viral_arc_chunk_llm_failed", chunk_index=chunk.index)
            return []

        try:
            parsed = _LLMOutput.model_validate_json(_strip_json_fence(raw_response))
        except (ValidationError, json.JSONDecodeError) as exc:
            log.warning(
                "viral_arc_chunk_parse_failed",
                chunk_index=chunk.index,
                error=str(exc)[:200],
            )
            return []

        log.info(
            "viral_arc_chunk_done",
            chunk_index=chunk.index,
            reel_count=len(parsed.reels),
        )
        return parsed.reels


def _time_overlap_ratio(a: _LLMReel, b: _LLMReel) -> float:
    """IoU по временному покрытию двух рилсов (union сегментов).

    Возвращает ratio [0..1]. >0.7 → считаем дубликатами.
    """
    def _cover(reel: _LLMReel) -> list[tuple[float, float]]:
        return sorted((s.start, s.end) for s in reel.segments if s.end > s.start)

    a_cover = _cover(a)
    b_cover = _cover(b)
    if not a_cover or not b_cover:
        return 0.0

    a_dur = sum(e - s for s, e in a_cover)
    b_dur = sum(e - s for s, e in b_cover)
    if a_dur <= 0 or b_dur <= 0:
        return 0.0

    intersection = 0.0
    for a_s, a_e in a_cover:
        for b_s, b_e in b_cover:
            lo = max(a_s, b_s)
            hi = min(a_e, b_e)
            if hi > lo:
                intersection += hi - lo

    union = a_dur + b_dur - intersection
    return intersection / union if union > 0 else 0.0


def _dedupe_reels(reels: list[_LLMReel]) -> list[_LLMReel]:
    """Greedy dedup: sort по viral_score desc, отбрасываем дубликаты (IoU>0.7)."""
    sorted_reels = sorted(reels, key=lambda r: r.viral_score, reverse=True)
    kept: list[_LLMReel] = []
    for candidate in sorted_reels:
        is_dup = any(
            _time_overlap_ratio(candidate, k) >= _DEDUP_OVERLAP_RATIO for k in kept
        )
        if not is_dup:
            kept.append(candidate)
    return kept


def _to_reel_plan(llm_reel: _LLMReel) -> ReelPlan | None:
    """Конвертер LLM output → legacy ReelPlan.

    Returns None если LLM reel невалиден (пустые segments, overlap, длина 0).
    """
    normalized_segments: list[ReelSegment] = []
    for seg in llm_reel.segments:
        if seg.end - seg.start < _MIN_SEGMENT_DURATION_SEC:
            continue
        role_map = {
            "flashforward_hook": "hook",
            "hook": "hook",
            "context_development": "development",
            "development": "development",
            "payoff_closure": "payoff",
            "payoff": "payoff",
            "peak": "peak",
        }
        order_role = role_map.get(seg.role, "development")
        normalized_segments.append(
            ReelSegment(
                source_start=round(seg.start, 3),
                source_end=round(seg.end, 3),
                reasoning=f"viral_2026 {seg.role}: {seg.reason}"[:500],
                order_role=order_role,  # type: ignore[arg-type]
            )
        )

    if not normalized_segments:
        return None

    predicted_duration = sum(s.source_end - s.source_start for s in normalized_segments)
    safe_reel_id = re.sub(r"[^A-Za-z0-9_-]", "_", llm_reel.reel_id)[:32]
    if not safe_reel_id:
        safe_reel_id = f"v_{uuid.uuid4().hex[:8]}"

    return ReelPlan(
        reel_id=safe_reel_id,
        hook=llm_reel.title or llm_reel.save_value[:120],
        predicted_duration_sec=round(predicted_duration, 2),
        target_audience="",
        segments=normalized_segments,
        composite_score=float(llm_reel.viral_score),
    )


async def build_viral_arcs(
    transcript: CleanedTranscript,
    *,
    cfg: Settings,
) -> list[ReelPlan]:
    """Entry-point для viral_2026 narrative mode.

    Конвертирует transcript в list[ReelPlan]. Pipeline:
    1. Chunking 20К знаков с overlap 2.5К.
    2. Parallel LLM call per chunk (Flash Lite) с Semaphore(10).
    3. Validate JSON output через Pydantic.
    4. Cross-chunk dedup по temporal IoU > 0.70.
    5. Конвертер → ReelPlan формат.

    Returns:
        list[ReelPlan], отсортированный по viral_score desc.
    """
    chunks = _build_chunks(transcript)
    if not chunks:
        log.warning("viral_arc_empty_transcript")
        return []

    system_prompt = await get_prompt(PromptKey.viral_2026)
    log.info(
        "viral_arc_build_start",
        chunk_count=len(chunks),
        chunk_size_chars=_CHUNK_SIZE_CHARS,
        overlap_chars=_CHUNK_OVERLAP_CHARS,
    )

    semaphore = asyncio.Semaphore(_MAX_CONCURRENCY)
    tasks = [
        _call_llm_for_chunk(chunk, system_prompt=system_prompt, cfg=cfg, semaphore=semaphore)
        for chunk in chunks
    ]
    per_chunk_results = await asyncio.gather(*tasks)
    all_llm_reels = [reel for chunk_reels in per_chunk_results for reel in chunk_reels]

    if not all_llm_reels:
        log.warning("viral_arc_no_reels")
        return []

    deduped = _dedupe_reels(all_llm_reels)
    log.info(
        "viral_arc_dedup_done",
        raw_count=len(all_llm_reels),
        kept=len(deduped),
        rejected=len(all_llm_reels) - len(deduped),
    )

    reel_plans: list[ReelPlan] = []
    for llm_reel in deduped:
        plan = _to_reel_plan(llm_reel)
        if plan is not None:
            reel_plans.append(plan)

    log.info(
        "viral_arc_build_complete",
        final_reel_count=len(reel_plans),
    )
    return reel_plans
```

- [ ] **Step 3: Проверить что `llm_client` / `tier_resolver` / `rate_limiter` API существует**

```bash
grep -n "async def generate_json\|def resolve_tier\|def get_rate_limiter\|def get_llm_client" /Users/malovnik/Documents/Dev/videomaker/apps/backend/src/videomaker/services/*.py | head -10
```

Если сигнатуры различаются — адаптировать код под реальные. Например если `generate_json` называется иначе или принимает другие параметры, либо если resolve_tier возвращает object другой формы — поправить. Не изобретать — ОБЯЗАТЕЛЬНО смотреть как делают existing services (напр. `narrative/chunk_scorer.py`).

- [ ] **Step 4: Build gates**

```bash
cd /Users/malovnik/Documents/Dev/videomaker/apps/backend && uv run ruff check src/videomaker/services/viral_arc_builder.py && uv run pyright src/videomaker/services/viral_arc_builder.py
```

- [ ] **Step 5: Commit**

```bash
git -C /Users/malovnik/Documents/Dev/videomaker add apps/backend/src/videomaker/services/viral_arc_builder.py
git -C /Users/malovnik/Documents/Dev/videomaker commit -m "feat(viral_2026): chunked LLM builder — parallel 20K chunks + IoU dedup

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
git -C /Users/malovnik/Documents/Dev/videomaker push origin feat/glm-provider
```

---

## Task 5: analysis.py branching (viral_2026 → build_viral_arcs)

**Files:**
- Modify: `apps/backend/src/videomaker/services/pipeline_stages/analysis.py`

- [ ] **Step 1: Расширить branching**

Найти block line 241-255 (`perf_narrative = await get_performance_settings(cfg)` → `if perf_narrative.narrative_mode in {"chaptered", "map_reduce"}`). Добавить перед этим блоком (или отдельной ветвью):

```python
    # Phase 9 (2026-04-22) — Viral 2026 simple pipeline. Один LLM call per
    # chunk 20К знаков → готовые рилсы по 5-block структуре + манифест
    # Живого Кадра. Параллельно Kartoziya pipeline; default bottom_up.
    if perf_narrative.narrative_mode == "viral_2026":
        return await _run_viral_2026_branch(
            ctx=ctx,
            cleaned_transcript=cleaned_transcript,
            cfg=cfg,
        )
```

- [ ] **Step 2: Написать _run_viral_2026_branch**

В конец файла или рядом с `_run_top_down_branch` (посмотреть signature для образца) добавить:

```python
async def _run_viral_2026_branch(
    *,
    ctx: PipelineContext,
    cleaned_transcript: CleanedTranscript,
    cfg: Settings,
) -> PipelineContext:
    """Viral 2026 branch: chunked LLM pipeline, bypass Kartoziya 9-stage.

    Вызывает ``build_viral_arcs`` и упаковывает результат в ``AnalysisResult``,
    совместимый с downstream ``render_stage``. Запись artifact
    ``analysis_summary.json`` с meta.narrative_mode=viral_2026.
    """
    from videomaker.models.reel_plan import AnalysisResult
    from videomaker.services.viral_arc_builder import build_viral_arcs

    job_id = ctx.job_id
    service = ctx.service
    art = ctx.artifact_store

    await _advance(service, job_id, JobStage.analyze, 30, "viral 2026: chunked LLM build")

    reels = await build_viral_arcs(cleaned_transcript, cfg=cfg)

    analysis = AnalysisResult(
        reels=reels,
        llm_model="gemini-flash-lite",
        provider="gemini",
        stats={
            "narrative_mode": "viral_2026",
            "reel_count": len(reels),
        },
    )

    art.write_json(
        job_id,
        "text/analysis_summary.json",
        {
            "narrative_mode": "viral_2026",
            "reel_count": len(reels),
            "avg_composite_score": (
                sum(r.composite_score or 0 for r in reels) / len(reels)
                if reels
                else None
            ),
        },
    )
    art.write_json(
        job_id,
        "text/reel_plan.json",
        {"reels": [r.model_dump() for r in reels]},
    )

    await _advance(
        service, job_id, JobStage.analyze, 95,
        f"viral 2026: готово {len(reels)} рилсов",
    )

    ctx.analysis = analysis
    return ctx
```

Поправить, если сигнатуры `_advance`, `ctx.artifact_store`, `ctx.service` другие — посмотреть как это делает `_run_top_down_branch`.

- [ ] **Step 3: Build gates**

```bash
cd /Users/malovnik/Documents/Dev/videomaker/apps/backend && uv run ruff check src/videomaker/services/pipeline_stages/analysis.py && uv run pyright src/videomaker/services/pipeline_stages/analysis.py
```

- [ ] **Step 4: Commit**

```bash
git -C /Users/malovnik/Documents/Dev/videomaker add apps/backend/src/videomaker/services/pipeline_stages/analysis.py
git -C /Users/malovnik/Documents/Dev/videomaker commit -m "feat(viral_2026): analysis.py branching — bypass Kartoziya 9-stage

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
git -C /Users/malovnik/Documents/Dev/videomaker push origin feat/glm-provider
```

---

## Task 6: Face_track hardcode fix (conditional через face_tracker_enabled)

**Files:**
- Modify: `apps/backend/src/videomaker/services/pipeline_stages/render.py:263-267`, `425-456`

- [ ] **Step 1: Поменять _prepare_face_tracking на conditional**

Найти вызов `setup.face_track = await _prepare_face_tracking(...)` (~line 263). Обернуть в conditional:

```python
    perf = await get_performance_settings(cfg)
    if perf.face_tracker_enabled:
        setup.face_track = await _prepare_face_tracking(
            job_id=job_id,
            face_track_source_path=face_track_source_path,
            settings=settings,
        )
    else:
        log.info(
            "face_track_skipped",
            job_id=job_id,
            reason="face_tracker_enabled=False в PerformanceSettings",
        )
        setup.face_track = None
```

Проверить что `cfg` и `get_performance_settings` импортированы в файле. Если нет — добавить импорт:

```python
from videomaker.services.runtime_settings_store import get_performance_settings
```

- [ ] **Step 2: Обновить docstring _prepare_face_tracking**

В функции `_prepare_face_tracking` (line ~425) исправить docstring с "выполняется ВСЕГДА" на "выполняется только при perf.face_tracker_enabled=True; иначе base_crop использует статичный center-crop".

- [ ] **Step 3: Build gates**

```bash
cd /Users/malovnik/Documents/Dev/videomaker/apps/backend && uv run ruff check src/videomaker/services/pipeline_stages/render.py && uv run pyright src/videomaker/services/pipeline_stages/render.py
```

- [ ] **Step 4: Commit**

```bash
git -C /Users/malovnik/Documents/Dev/videomaker add apps/backend/src/videomaker/services/pipeline_stages/render.py
git -C /Users/malovnik/Documents/Dev/videomaker commit -m "fix(face_track): conditional через face_tracker_enabled (default OFF)

Hardcode 'v0.7 всегда' заменён на opt-in toggle. Mediapipe на M-series
может зависать (наблюдалось в jobs 8a418e9b). Default OFF — для 95%
случаев face-keyframes не нужны: letterbox / manual / split с main_transform
работают без них.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
git -C /Users/malovnik/Documents/Dev/videomaker push origin feat/glm-provider
```

---

## Task 7: Frontend — NarrativeModeGroup + face_tracker toggle

**Files:**
- Modify: `apps/frontend/src/components/settings/performance-groups/NarrativeModeGroup.tsx`
- Modify: `apps/frontend/src/lib/api/settings.ts`
- Modify: один из `performance-groups/*Group.tsx` (MotionGroup.tsx — face-tracker логически там)

- [ ] **Step 1: Расширить NarrativeModeGroup**

В `NarrativeModeGroup.tsx`:

1. Сменить тип `NarrativeMode`:
```typescript
type NarrativeMode = "bottom_up" | "chaptered" | "map_reduce" | "viral_2026";
```

2. Добавить entry в `NARRATIVE_MODE_META`:
```typescript
  viral_2026: {
    label: "Viral 2026 (OpusClip-parity, самый быстрый)",
    hint: "Транскрипт → chunks 20К → один LLM call per chunk эмиттит готовые рилсы по структуре 5 блоков (Hook/Context/Payoff/Re-hook/CTA) + манифест Живого Кадра. ~10-15 LLM calls на 90 мин видео. Рекомендовано для talking-head.",
  },
```

- [ ] **Step 2: Обновить settings API типы**

В `apps/frontend/src/lib/api/settings.ts` найти narrative_mode определение и добавить `"viral_2026"` в union type. Добавить поле `face_tracker_enabled: boolean` в соответствующий interface (скорее всего `PerformanceSettings`).

Если точное имя поля / структуру не ясно — открыть файл и добавить аккуратно с учётом существующих полей.

- [ ] **Step 3: Добавить face_tracker toggle**

В `apps/frontend/src/components/settings/performance-groups/MotionGroup.tsx` (или где логично — зум/моушн контролы) добавить checkbox toggle под существующими полями:

```tsx
<CheckboxRow
  label="Face tracker (только для fit=fill с face-centered crop)"
  description="Включает MediaPipe face detection. Default OFF — ресурсоёмкий, может зависать на больших видео (Apple Silicon + mediapipe)."
  checked={values.face_tracker_enabled ?? false}
  onChange={(v) => update("face_tracker_enabled", v)}
/>
```

Если `CheckboxRow` называется иначе — посмотреть как другие groups используют toggles (напр. `CoherenceGroup.tsx`, `CutSnapGroup.tsx`).

- [ ] **Step 4: Build gates**

```bash
cd /Users/malovnik/Documents/Dev/videomaker/apps/frontend && npx tsc --noEmit -p tsconfig.json 2>&1 | tail -15
```
Expected: 0 errors.

- [ ] **Step 5: Commit**

```bash
git -C /Users/malovnik/Documents/Dev/videomaker add apps/frontend/src/components/settings/performance-groups/NarrativeModeGroup.tsx apps/frontend/src/components/settings/performance-groups/MotionGroup.tsx apps/frontend/src/lib/api/settings.ts
git -C /Users/malovnik/Documents/Dev/videomaker commit -m "feat(ui): viral_2026 narrative mode + face_tracker toggle

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
git -C /Users/malovnik/Documents/Dev/videomaker push origin feat/glm-provider
```

---

## Task 8: End-to-end smoke validation

**Files:**
- None (только тесты через API)

- [ ] **Step 1: Backend health check**

```bash
curl -sS http://127.0.0.1:8000/api/v1/health 2>/dev/null | head -3
```

Если отдаёт 404/connection refused → запустить:
```bash
cd /Users/malovnik/Documents/Dev/videomaker && ./run.sh >/tmp/run-ralph.log 2>&1 &
```
Подождать 45 сек. Повторить health check до успеха.

- [ ] **Step 2: Выбрать короткое тестовое видео**

```bash
for d in /Users/malovnik/Documents/Dev/videomaker/data/artifacts/*/text/cleaned_transcript.json; do
  JOB_ID=$(basename $(dirname $(dirname $d)))
  UPLOAD_DIR=/Users/malovnik/Documents/Dev/videomaker/data/uploads/$JOB_ID
  if [ -d "$UPLOAD_DIR" ]; then
    SOURCE=$(ls $UPLOAD_DIR/*.mp4 2>/dev/null | head -1)
    if [ -n "$SOURCE" ]; then
      DURATION=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$SOURCE" 2>/dev/null)
      echo "$DURATION $JOB_ID $SOURCE"
    fi
  fi
done | sort -n | head -5
```

Выбрать первый (самое короткое) job_id с транскриптом.

- [ ] **Step 3: Выставить viral_2026 через API**

```bash
curl -sS -X PUT http://127.0.0.1:8000/api/v1/settings/performance \
  -H 'Content-Type: application/json' \
  -d '{"narrative_mode": "viral_2026"}' | head -10
```

- [ ] **Step 4: Запустить новый job**

Через API:
```bash
# (уточнить exact endpoint — grep apps/backend/src/videomaker/api/routes/jobs.py на POST upload)
```

Использовать тот же source файл что выбран в step 2.

- [ ] **Step 5: Poll до analyze-complete**

```bash
for i in $(seq 1 60); do
  STATUS=$(curl -sS http://127.0.0.1:8000/api/v1/jobs/$NEW_JOB_ID 2>/dev/null | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('status'),d.get('progress'))")
  echo "$i $STATUS"
  if [[ "$STATUS" == *"running 95"* ]] || [[ "$STATUS" == *"succeeded"* ]]; then
    break
  fi
  sleep 10
done
```

- [ ] **Step 6: Проверить reel_plan.json**

```bash
cat /Users/malovnik/Documents/Dev/videomaker/data/artifacts/$NEW_JOB_ID/text/analysis_summary.json | python3 -m json.tool
cat /Users/malovnik/Documents/Dev/videomaker/data/artifacts/$NEW_JOB_ID/text/reel_plan.json | python3 -c "import json,sys;d=json.load(sys.stdin);print('reel_count:', len(d['reels']));print('sample:', d['reels'][0] if d['reels'] else None)"
```

Expected: `narrative_mode: "viral_2026"` в analysis_summary; `reel_count >= 5`; sample reel содержит `hook`, `segments` с `source_start`/`source_end`.

- [ ] **Step 7: Cancel render (save time)**

```bash
curl -sS -X POST http://127.0.0.1:8000/api/v1/jobs/$NEW_JOB_ID/cancel
```

- [ ] **Step 8: Frontend smoke**

```bash
curl -sS http://127.0.0.1:3000 2>/dev/null | head -20
```

Expected: HTML output — frontend поднят и отдаёт.

- [ ] **Step 9: Final commit (документация результата)**

Обновить этот план — отметить все tasks checkbox'ами `[x]`. Commit:

```bash
git -C /Users/malovnik/Documents/Dev/videomaker add docs/plans/2026-04-22-viral-arc-2026-pipeline.md
git -C /Users/malovnik/Documents/Dev/videomaker commit -m "docs(viral_2026): plan checked off — e2e smoke успешен

- Reel count: <N>
- Avg composite_score: <X>
- Frontend toggle: OK
- Face_track conditional: confirmed

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
git -C /Users/malovnik/Documents/Dev/videomaker push origin feat/glm-provider
```

---

## Completion Criteria (для ralph-loop promise)

Промис `ViralArc2026PipelineReady` выставляется когда:

1. File `apps/backend/src/videomaker/services/prompts_data/viral_2026.md` существует
2. `grep -q "viral_2026" apps/backend/src/videomaker/services/prompts.py` — PromptKey + DEFAULT_PROMPTS
3. `grep -q "viral_2026" apps/backend/src/videomaker/models/runtime_settings.py` — NarrativeMode Literal
4. File `apps/backend/src/videomaker/services/viral_arc_builder.py` существует + `build_viral_arcs` function
5. `grep -q "viral_2026" apps/backend/src/videomaker/services/pipeline_stages/analysis.py` — branching
6. `grep -q "face_tracker_enabled" apps/backend/src/videomaker/services/pipeline_stages/render.py` — conditional
7. `grep -q "viral_2026" apps/frontend/src/components/settings/performance-groups/NarrativeModeGroup.tsx` — UI option
8. `grep -q "face_tracker_enabled" apps/frontend/src/lib/api/settings.ts` — API type
9. Backend build gates pass (ruff + pyright 0 errors)
10. Frontend build gates pass (tsc 0 errors)
11. End-to-end smoke: новый job с `narrative_mode=viral_2026` → reel_plan.json с ≥5 reels, analysis_summary содержит `"narrative_mode": "viral_2026"`

Все 11 критериев TRUE → `<promise>ViralArc2026PipelineReady</promise>`.

Любой невыполнен → НЕ выводить promise, продолжать loop, найти незавершённый критерий через state check и сделать соответствующую Task.

---

## Execution Handoff

Plan сохранён. Юзер запросил автономное исполнение через `ralph-loop-local:ralph-loop` (не subagent-driven, не inline). Макс итераций 18.
