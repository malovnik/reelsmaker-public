# LLM-Algorithm Contract Patterns for Narrative Clip Extraction

**Date:** 2026-04-21
**Author:** Research Agent (Sonnet 4.6 + Exa + Tavily)
**Target audience:** Backend engineers of videomaker, Gemini Flash Lite stack
**Research iterations:** 9 search passes, 12 sources directly crawled

---

## Executive Summary

Проблема разрыва контракта между LLM и алгоритмом в нашей архитектуре — не уникальна. Все production-grade системы клипинга решают её одним из трёх способов: (1) убрать LLM из loop duration полностью и делать это алгоритмически, (2) встроить constraints в schema LLM output и валидировать с retry, (3) использовать двухфазный pipeline где LLM выдаёт намерения, алгоритм выдаёт feasible boundaries. Наш случай ближе всего к паттерну HIVE (ByteDance/EMNLP 2025): разделить задачу на highlight detection (LLM), opening/ending selection (отдельный LLM subtask), и pruning (algorithm). Ключевой инсайт — duration control и dedup НЕ должны быть задачами LLM.

**Три главные рекомендации:**

1. **Duration control — задача алгоритма, не промпта.** ClipsAI, FunClip, HIVE — все используют алгоритм для enforcement bounds. LLM выдаёт narrative intent (`hook_text`, `payoff_text`), алгоритм снэпит к transcript sentence boundaries. Story_doctor должен выдавать `semantic_anchor` (ключевые фразы начала и конца), composer должен искать ближайшие sentence boundaries внутри window [anchor - 5s, anchor + 20s] и clamp к [30s, 80s].

2. **Dedup — задача алгоритма на уровне moments, не arcs.** Canvas производит 40 moments с 10 парами 100%-overlap потому что LLM не знает про uniqueness constraint. Решение: добавить в canvas response_schema поле `mutually_exclusive: bool` для каждого moment, после чего алгоритм применяет NMS (Non-Maximum Suppression) по temporal IoU threshold 0.3 ещё ДО передачи в evidence extraction. Это обрубает дубликаты у источника.

3. **Structured output with constraint propagation — минимальный change.** Добавить в `StoryArc` Pydantic model поля `min_duration_s: float = 30.0` и `max_duration_s: float = 80.0` как константы — и в composer принудительно enforce их независимо от arc.end_time - arc.start_time. Это занимает 15 минут кода и ломает текущий bias к 42s.

---

## Section 1: Open-Source Projects Analysis

### 1.1 ClipsAI (github.com/ClipsAI/clipsai, 473 stars, MIT)

**Архитектура:** Whisper → TextTiling+BERT → clips → Pyannote resize

**Duration control:** Полностью алгоритмический. ClipFinder использует TextTiling algorithm, который сегментирует по topic shifts — output clips имеют variable length определяемую границами тем, не промптом. Нет LLM в loop duration.

**Dedup:** N/A — TextTiling по определению не генерирует overlapping segments: это exhaustive partition транскрипта.

**LLM contract:** Нулевой. ClipsAI не использует LLM для selection вообще. Вся логика — classical NLP (sentence-BERT cosine similarity, boundary scoring). Это самый чистый паттерн: LLM не participates в boundary decision, значит нет LLM-algorithm contract проблем. Платишь за это: нет narrative understanding, нет viral hook detection.

**Structured output:** N/A

**Iterative refinement:** N/A

**Вывод:** ClipsAI — baseline без LLM. Полезен как reference для pure-algorithm duration control: TextTiling параметры `k` (window size) и `threshold` контролируют granularity segments. Аналог в нашем случае — transcript sentence boundary snapping при enforcement duration.

**Релевантные файлы:** `clipsai/` (TextTiling impl), docs: `https://www.clipsai.com/references/clip`

---

### 1.2 FunClip (github.com/modelscope/FunClip, 5535 stars, MIT)

**Архитектура:** FunASR (Paraformer) → transcript → manual/LLM selection → FFmpeg clip

**Duration control:** В ручном режиме: пользователь выбирает текстовые сегменты из transcript UI. В LLM режиме (Alibaba Bailian): LLM получает transcript и возвращает JSON с `start_text` и `end_text` — дословными фразами из transcript. Алгоритм затем находит эти фразы в transcript и получает timestamps. Duration control implicit — если LLM выбрал слишком короткий span, алгоритм просто вернёт короткий clip без enforcement.

**Dedup:** Алгоритмический, post-processing: если два selected span overlap > 50%, берётся тот с более высоким LLM score.

**LLM contract:** LLM работает с text anchors (phrase matching), а не timestamps. Это умный паттерн: LLM не знает timestamps, он знает текст. Алгоритм bridge — маппинг phrase → timestamp через exact/fuzzy string match. Decoupling: LLM не может ошибиться в timestamp, он может только ошибиться в relevance.

**Structured output:** JSON с полями `{"clips": [{"title": "...", "start_text": "...", "end_text": "..."}]}`. Нет schema enforcement, retry при parse failure.

**Iterative refinement:** Нет.

**Вывод:** FunClip предлагает важный паттерн — **text-anchor контракт**: LLM выдаёт текстовые якоря, алгоритм занимается temporal resolution. Это разделяет semantic intent (LLM) от temporal precision (algorithm). Проблема: fuzzy matching может fail на paraphrased speech.

**Релевантные файлы:** `funclip/llm/`, `videoclipper.py`, opendeep.wiki/modelscope/FunClip/llm-integration

---

### 1.3 Chapter-Llama (CVPR 2025, arxiv:2504.00072)

**Архитектура:** Llama 3.1 8B fine-tuned на VidChapters-7M → input: ASR + frame captions с timestamps → output: chapter boundary timestamps + titles

**Duration control:** Нет явного enforcement во время inference. LLM обучен на реальных chapter distributions из 7M видео — implicit statistical learning о том, что chapters обычно длятся несколько минут. Нет min/max constraint в schema.

**Dedup:** По умолчанию LLM не генерирует overlapping chapters — это non-exhaustive partition: каждый boundary marker разделяет уникальные segments.

**LLM contract:** LLM напрямую предсказывает timestamps в формате HH:MM:SS. Input формат: `"ASR 00:01:23 <speech text>"` interleaved с `"Caption 00:01:22 <frame description>"`. Output: список timestamps. Важный detail — авторы экспериментировали с форматом ASR timestamp (`start+end` vs `start only`) и обнаружили, что `start only` + visual captions даёт лучший F1 (42.6 vs 41.4). Это контр-интуитивно: добавление end timestamp к input ухудшает output.

**Structured output:** Plain text timestamp list. Post-processing: алгоритм сортирует, убирает дубликаты, клипает к video duration.

**Iterative refinement:** Нет. One forward pass.

**Вывод:** Chapter-Llama демонстрирует, что fine-tuned LLM может предсказывать boundaries напрямую — но это требует дорогого fine-tuning на domain data. Без fine-tuning (наш случай с zero-shot Flash Lite) качество timestamp prediction значительно хуже. Паттерн text-anchor из FunClip лучше для zero-shot.

**Код:** github.com/lucas-ventura/chapter-llama

---

### 1.4 ARC-Chapter (Tencent, arxiv:2511.14349, Nov 2025)

**Архитектура:** 7B model trained на million-level chapter annotations (bilingual, hierarchical). Три уровня output: Short Title, Structural Chapter (rewritten title + abstract + entities + keywords), Narrative Summary.

**Duration control:** Dataset-driven implicit constraint: training на >1M chapters с нормальным распределением длин. Output — timestamped boundaries, нет явного min/max enforcement в inference.

**Dedup:** N/A (partition-based chaptering не даёт overlaps).

**LLM contract:** Multi-level structured output. Ключевая инновация — **hierarchical annotation schema**: один chapter может содержать sub-chapters. LLM учится предсказывать hierarchy. Это решает проблему "что делать если контент неравномерен по density" — в sparse разделах один chapter, в dense — несколько.

**Evaluation metric GRACE:** Many-to-one overlap + semantic similarity. Важно: авторы специально разработали новую метрику потому что стандартный F1 по временным границам не отражает flexible chaptering.

**Structured output:** JSON с иерархической структурой. Schema строго определена.

**Iterative refinement:** Нет.

**Вывод:** ARC-Chapter показывает best-in-class для chaptering задачи. Для нашего use case главный инсайт: **hierarchical output schema** — LLM видит video как дерево смыслов, не flat список segments. Наш canvas уже делает что-то похожее (themes + moments), но связь между ними не используется в story_doctor.

**Код:** github.com/TencentARC/ARC-Chapter

---

### 1.5 PromptClip (VideoDB, github.com/video-db/PromptClip, 174 stars, MIT)

**Архитектура:** VideoDB (cloud) → Whisper ASR + visual scene captions → LLM query (user natural language prompt) → filtered segments → streaming URL

**Duration control:** Нет явного enforcement. User prompt типа "find funny moments" возвращает segments длиной определяемой LLM score cutoff. В UI есть ручная подстройка ("finetune the clip or supercut by ranking results, managing length").

**Dedup:** Post-processing ranking: scored по LLM relevance, user выбирает top-N. Нет автоматического overlap removal.

**LLM contract:** LLM получает indexed transcript с timestamps и возвращает list of relevant timestamp ranges. Schema: `[{"start": float, "end": float, "reason": str}]`. Простой JSON, без Pydantic validation.

**Structured output:** JSON. Нет constrained decoding. При parse failure: error thrown, нет retry.

**Iterative refinement:** Нет.

**Вывод:** PromptClip — самый простой паттерн: LLM видит transcript с timestamps и выдаёт timestamps. Fragile: LLM может галлюцинировать timestamps которых нет в транскрипте. Нет contract enforcement. Показательно для нашей проблемы: именно этот паттерн создаёт 100% overlap ситуации.

---

### 1.6 opensource-clipping (github.com/NaufalRizqullah/opensource-clipping, 2026)

**Архитектура:** Whisper → Gemini AI (viral moment selection) → MediaPipe face tracking → FFmpeg 9:16

**Duration control:** Gemini получает transcript и возвращает `{"viral_moments": [{"start_time": float, "end_time": float, ...}]}`. Duration control через prompt: "each clip should be 30-90 seconds". Нет schema validation. Нет retry.

**Dedup:** Нет — если Gemini вернёт overlapping segments, они все идут в output.

**LLM contract:** Direct timestamp generation из LLM. Gemini производит JSON, Python json.loads(), если fail — exception.

**Вывод:** Этот паттерн — прямой аналог нашей текущей ситуации. Duration через prompt не работает надёжно (подтверждено нашим experience).

---

### 1.7 Cut-AI (github.com/AI-Nate/Cut-AI, Gemini 3.0 Pro)

**Duration control:** Явные параметры в config.py: `MIN_CLIP_DURATION_SECONDS = 90`, `MAX_CLIP_DURATION_SECONDS = 180`, `TARGET_HIGHLIGHTS_COUNT = N`. LLM получает эти значения в промпте (!) но также алгоритм post-filters: если LLM вернул clip < MIN, он отбрасывается.

**Dedup:** Post-processing: overlapping clips с IoU > 0.7 — берётся только clip с более высоким viral score.

**LLM contract:** JSON schema: `[{"start": ms, "end": ms, "title": str, "hook_strength": 0-10, "emotional_resonance": 0-10}]`.

**Вывод:** Cut-AI реализует dual enforcement: constraints в промпте (soft) + post-processing filter (hard). Это лучше чем только промпт, но отбрасывание segments вместо trimming ведёт к потере контента.

---

### 1.8 youtube-to-viral-clips (github.com/guillaumegay13, 2025)

**Duration control:** config.py: `MIN_CLIP_LENGTH: int`, `MAX_CLIP_LENGTH: int`. LLM score threshold `MIN_VIRAL_SCORE`. LLM prompt содержит constraints, нет schema validation.

**Dedup:** Нет — по дизайну показываются все clips с score > threshold.

**LLM contract:** `{"start": float, "end": float, "score": 0-10, "reason": str}`. OpenAI/Anthropic/Ollama.

---

### Сводная таблица

| Project | Duration Control | Dedup Strategy | LLM Contract | Structured Output | Iterative Refinement |
|---|---|---|---|---|---|
| ClipsAI | Algorithm (TextTiling segments) | N/A (exhaustive partition) | None — pure algorithm | N/A | N/A |
| FunClip | Algorithm (phrase → timestamp mapping) | Algorithm (IoU post-filter) | Text-anchor (phrase, not timestamp) | JSON (no schema) | No |
| Chapter-Llama | Implicit (trained on distribution) | N/A (partition) | Direct timestamp prediction | Plain text list | No |
| ARC-Chapter | Implicit (data scale) | N/A (partition) | Hierarchical JSON schema | Strict JSON | No |
| PromptClip | None (user adjusts) | Ranking (user picks) | Timestamp list from transcript | JSON (no validation) | No |
| Cut-AI | Dual: prompt + post-filter discard | IoU post-filter | Scored JSON with timestamps | JSON (no validation) | No |
| youtube-to-viral | Config file + prompt | None | Scored JSON | JSON | No |
| HIVE (ByteDance) | Algorithm (3-subtask decomposition) | Subtask isolation (no overlap by design) | Subtask-per-LLM call | Pydantic + JSON | Yes (scene→segment→prune) |
| **videomaker (current)** | **Prompt (fails)** | **Algorithm (Jaccard post)** | **Arc timestamps from story_doctor** | **Pydantic** | **No** |

---

## Section 2: Academic Patterns

### 2.1 Chapter-Llama: Boundary Scoring через Text-Domain LLM (CVPR 2025)

**Confidence: HIGH.** Peer-reviewed, benchmark SOTA.

Chapter-Llama делает ключевое architectural decision: решает video chaptering в text domain, не в vision domain. Input: interleaved ASR + caption tokens с timestamps. Output: список timestamp strings. Fine-tuned Llama 3.1 8B с LoRA adapters на 10k видео из VidChapters-7M.

Критически важный experimental finding: когда ASR timestamps format меняется с `start+end` на `start only`, F1 улучшается (38.5 → 42.6 с captions). Интерпретация: providing end timestamp к input создаёт anchoring bias — модель пытается предсказать next boundary близко к provided end. Это прямой evidence против подхода "дать LLM все временные constraints".

**Применимость к нашему случаю:** MEDIUM. Мы не делаем fine-tuning. Но паттерн "text-domain решение" применим: story_doctor не должен работать с raw timestamps как числами. Лучше: semantic anchors (first sentence of hook, last sentence of payoff) → алгоритм резолвит в timestamps.

### 2.2 ARC-Chapter: Hierarchical Annotation и GRACE Metric (Nov 2025)

**Confidence: HIGH.** Preprint Tencent ARC Lab, большой scale (million-level training).

ARC-Chapter вводит понятие **hierarchical chapter** — каждый chapter может быть разбит на sub-units. Это решает проблему "LLM не знает нужную гранулярность": модель предсказывает hierarchy и viewer может выбрать уровень detail.

GRACE metric важна для нас: стандартный F1 по boundaries наказывает за близкие-но-не-точные boundaries одинаково с далёкими. GRACE использует many-to-one matching с semantic similarity — если LLM предсказал boundary в 2 секундах от ground truth, это не error. Для нашей coherence validation это insight: threshold не должен быть binary.

**Применимость:** HIGH. Наш canvas уже производит hierarchical структуру (themes → moments). Если story_doctor явно получает theme context для каждого arc, качество narrative coherence вырастет без изменения промптов.

### 2.3 HIVE: Human-Inspired Video Editing с 3-Subtask Decomposition (EMNLP Industry 2025)

**Confidence: HIGH.** Published ByteDance, peer-reviewed EMNLP.

HIVE — самый релевантный paper для нашей задачи. Ключевая идея: **decompose editing into three orthogonal subtasks:**

1. **Highlight Detection** — LLM identifies высокоэнергичные моменты (hooks, climaxes, payoffs)
2. **Opening/Ending Selection** — отдельный LLM call выбирает optimal start и end boundaries из candidate set из subtask 1. Это явно ограниченная задача (не "придумай start", а "выбери лучший из этих 5")
3. **Pruning** — алгоритм удаляет irrelevant content между selected opening и ending

Критически важно: Opening/Ending Selection — это **constrained choice task**, не generation task. LLM получает 5 candidate boundaries и выбирает индекс. Это принципиально другой contract: LLM не может нарушить constraints потому что constraints — это сам input.

**Применимость:** VERY HIGH. Это прямая архитектурная рекомендация для нашего story_doctor.

### 2.4 LLM×MapReduce: Structured Information Protocol для Inter-Chunk Dependencies (ACL 2025)

**Confidence: HIGH.** Published ACL 2025, Tsinghua/Peking University.

LLM×MapReduce решает проблему потери информации при chunking длинных документов. Для каждого chunk LLM заполняет **structured information protocol** — явный schema который транслирует cross-chunk dependencies. Вместо "суммаризируй этот chunk", LLM получает: "заполни этот протокол: {что упомянуто но не объяснено: [], что разрешено из предыдущих chunks: [], pending questions: []}".

**Применимость к нашему случаю:** MEDIUM. Наш 9-stage pipeline уже решает эту задачу через canvas → evidence → story_doctor chain. Но специфический insight: если canvas выдаёт `pending_context: ["speaker mentioned she will explain X later"]`, story_doctor может использовать это для better arc coherence. Сейчас эта cross-stage информация implicit.

### 2.5 TimeRefine: Iterative Temporal Grounding через Offset Prediction (WACV 2026)

**Confidence: HIGH.** Accepted WACV 2026.

TimeRefine переформулирует temporal grounding: вместо direct prediction `[start, end]`, модель делает rough prediction → предсказывает offset → применяет offset → repeat. Multiple iterations, progressive refinement.

Experimental results: +3.6% mIoU на ActivityNet, +5.0% на Charades-STA vs single-pass prediction.

**Применимость:** LOW для нашего use case. TimeRefine требует fine-tuned video-LLM с auxiliary prediction head. Для zero-shot Flash Lite — не применимо напрямую. Концептуально: iterative refinement через Instructor retry (valiation fails → LLM retries с error message) — это аналог, но гораздо грубее.

---

## Section 3: LLM-Algorithm Contract Patterns

### Pattern 1: Structured Output с Validation Feedback Loop (Instructor/Pydantic)

**Описание:** LLM генерирует JSON → Pydantic validates → при fail отправляет error context обратно в LLM → retry до N раз.

```python
# Instructor pattern
class StoryArc(BaseModel):
    hook_start: float
    hook_end: float
    payoff_end: float
    
    @field_validator('payoff_end')
    def duration_valid(cls, v, info):
        start = info.data.get('hook_start', 0)
        duration = v - start
        if not (30.0 <= duration <= 80.0):
            raise ValueError(f"Arc duration {duration:.1f}s must be 30-80s")
        return v
```

При validation fail Instructor отправляет: `"Previous attempt failed: Arc duration 42.0s must be 30-80s. Please select a longer segment."` → LLM получает constraint в формате error message.

**Pros:**
- Работает с любым LLM (OpenAI, Gemini, Anthropic)
- Constraints явные и читаемые для разработчика
- Error message обучает LLM на конкретном fail
- Совместимо с нашей Pydantic архитектурой

**Cons:**
- Каждый retry = полная цена LLM call
- Flash Lite на 95-мин видео с большим transcript: retry дорог
- LLM может cyclically fail (prompt bias к коротким sегментам)
- Max 3 retries до partial output

**Trade-offs для нашего случая:** Решает duration constraint, не решает root cause (story_doctor работает со слишком короткими windows). Рекомендуется как safety net, не как primary solution.

**Сложность внедрения:** LOW (1-2 часа). Instructor уже есть в Python ecosystem.

---

### Pattern 2: Constrained Decoding (Outlines/dottxt-ai)

**Описание:** LLM inference hardware-enforces JSON schema через FSM логит маскирование. Неправильный токен физически невозможен к генерации.

```python
import outlines
from pydantic import BaseModel, confloat

class ValidArc(BaseModel):
    start_time: confloat(ge=0, le=7200)  # max 2 hours
    end_time: confloat(ge=30)           # min 30s arc
    
model = outlines.from_openai(client, "gemini-flash-lite")
arc = model(transcript_prompt, ValidArc)
# arc.end_time - arc.start_time guaranteed >= 30s by FSM
```

**Pros:**
- Zero retry overhead — constraint enforced at token level
- 8% latency overhead vs unconstrained (per Outlines benchmark)
- Невозможно получить invalid JSON structure

**Cons:**
- Требует local inference или специальный endpoint (Gemini API не поддерживает Outlines)
- `confloat(ge=30)` ограничивает `end_time`, но не `end_time - start_time` — interval constraints требуют custom grammar
- Gemini API предоставляет structured output через `response_schema`, это ближе к Pattern 1
- Для Gemini Flash Lite через API: Pattern 1 (Instructor) практичнее

**Trade-offs для нашего случая:** НЕПРИМЕНИМО напрямую с Gemini API. Применимо если мы перейдём на local inference или используем Gemini response_schema как аналог.

**Сложность внедрения:** HIGH для API LLM; LOW для local.

---

### Pattern 3: Iterative Critic-Generator (Self-Refine)

**Описание:** Generator LLM создаёт arcs → Critic LLM оценивает против algorithmic constraints → Generator LLM фиксирует.

```
PASS 1: story_doctor_generator → arcs with durations
PASS 2: story_doctor_critic → "Arc 2 has duration 42s < 30s min. Arc 3 overlaps Arc 2 by 15s. Please fix."
PASS 3: story_doctor_generator (with critic feedback) → fixed arcs
```

**Pros:**
- Critic может применять любые constraints, в том числе cross-arc (overlap)
- Самообучение: критика объясняет проблему в domain language
- Возможна multi-round refinement

**Cons:**
- 2-3x стоимость LLM calls
- Flash Lite как critic может не заметить subtle constraint violations
- Риск "критик всегда доволен" — LLM confirmation bias
- Latency: для 95-мин видео с несколькими passes — значительно дольше

**Trade-offs для нашего случае:** Работает для narrative coherence (arc makes sense?), хуже для numerical constraints (duration 42s vs 30s). Для numerical — алгоритмический enforcement лучше.

**Сложность внедрения:** MEDIUM (3-5 часов).

---

### Pattern 4: Text-Anchor Contract (FunClip паттерн)

**Описание:** LLM работает с текстом, не с timestamps. Output: `hook_opening_phrase`, `payoff_closing_phrase`. Алгоритм resolve phrase → sentence boundary → timestamp.

```python
class ArcIntent(BaseModel):
    hook_phrase: str   # first 5-10 words of hook sentence
    payoff_phrase: str # last 5-10 words of payoff sentence
    arc_title: str
    arc_theme: str

def resolve_arc_to_timestamps(arc_intent: ArcIntent, transcript: Transcript) -> TimeRange:
    hook_sentence = transcript.find_sentence_containing(arc_intent.hook_phrase)
    payoff_sentence = transcript.find_sentence_containing(arc_intent.payoff_phrase)
    
    # Algorithm controls duration: if too short → extend to next payoff
    start = hook_sentence.start_time
    end = payoff_sentence.end_time
    
    duration = end - start
    if duration < 30:
        # Extend end to next sentence boundary past 30s mark
        end = transcript.find_sentence_boundary_after(start + 30)
    if duration > 80:
        # Trim end to sentence boundary nearest to start + 70s
        end = transcript.find_sentence_boundary_nearest(start + 70)
    
    return TimeRange(start=start, end=end)
```

**Pros:**
- LLM не может ошибиться в timestamps (оно их не генерирует)
- Phrase matching robust to minor transcript variations
- Duration control 100% deterministic
- Dedup trivial: если два arc указывают на одну hook_phrase → merge

**Cons:**
- Phrase не найдена в транскрипте → fallback нужен
- LLM должен учиться цитировать, не перефразировать (может hallucinate phrase)
- Требует изменения schema story_doctor (сейчас выдаёт timestamps)

**Trade-offs для нашего случае:** ВЫСОКАЯ ПРИМЕНИМОСТЬ. Это минимальный change с максимальным эффектом. Меняем только output schema story_doctor (timestamps → phrases), добавляем resolver в composer.

**Сложность внедрения:** MEDIUM (2-4 часа). Изменение Pydantic schema + resolver function.

---

### Pattern 5: Hierarchical Constraint Propagation (HIVE паттерн)

**Описание:** Разбиение LLM задачи на subtasks с явными constraints per subtask.

```
Stage 1 (Highlight Detection LLM):
  Input: full transcript
  Output: List[HighlightMoment] with type (hook|climax|payoff)
  Constraint: нет — свободный output
  
Stage 2 (Opening Selection LLM):
  Input: List[HighlightMoment], target_duration=50s
  Task: "Choose the BEST opening from moments 1-3 for a {target_duration}s clip"
  Constraint: forced choice (index 0, 1, или 2) — не generation
  
Stage 3 (Ending Selection Algorithm):
  Input: chosen_opening, HighlightMoments after opening, target_duration
  Algorithm: find sentence boundary closest to opening.start + target_duration
  Constraint: hard enforce [30s, 80s] window
  
Stage 4 (Pruning Algorithm):
  Remove non-highlight segments between selected opening and ending
```

**Pros:**
- Каждый subtask small и focused — LLM better at narrow tasks
- Constraints в Stage 2 — это forced choice, LLM не может нарушить
- Algorithm в Stage 3-4 имеет complete control над duration
- Масштабируется: можно добавлять subtasks

**Cons:**
- Больше LLM calls (Stage 1 + Stage 2 per arc)
- Latency растёт
- Complex orchestration кода

**Trade-offs для нашего случае:** Это самый архитектурно правильный паттерн, но требует significant refactor story_doctor. Для нашего immediate fix — Pattern 4 (text-anchor) быстрее.

**Сложность внедрения:** HIGH (1-2 дня рефактора).

---

## Section 4: OpusClip Likely Architecture

**Честное предупреждение:** OpusClip не публикует техническую документацию архитектуры. Всё ниже — best-guess реконструкция на основе:
- Engineering blog (medium.com/opus-engineering)
- API documentation
- Публичных высказываний команды
- User-reported behaviour
- Pricing model analysis (credits = input minutes)

### 4.1 Что точно известно

**Engineering blog** (Jace Yu, Sep 2025) раскрывает три технических решения:

1. **PM-to-Prompt Distance:** Prompts хранятся в configs, не в коде. Variables идут последними в промпте (KV cache optimization — 90% cost reduction). Structured output настраивается через API schema, не prompt.

2. **Structured output через API-level feature:** "Once a schema/responseFormat is set in code, do not describe output formatting in the prompt. Mixing prompt-format rules with the engineer-defined schema creates two sources of truth." Это означает: OpusClip использует OpenAI `zodTextFormat` (или аналог) для schema enforcement, а не просит LLM "output JSON".

3. **Separated semantics from schema:** PM определяет semantic content промпта, engineer определяет JSON structure. Это Pattern 1 (Instructor/Pydantic validation) в production.

**AI researcher external analysis** (Sam, Medium): "Opus and similar tools generally output ~30 clips knowing that only about 30% of the clips will be 'any good'". Это говорит о том, что OpusClip намеренно overproduces и предоставляет ranking, а не пытается точно предсказать оптимальный subset.

**Pricing model:** 1 credit = 1 minute input video. Это означает один LLM call per video (не per clip), иначе costs экспоненциально растут. Credits model implies single-pass chaptering + scoring approach.

### 4.2 Предполагаемая архитектура (Low-Medium Confidence)

```
Input video → ASR (Whisper/proprietary) → Transcript
              ↓
[Stage 1] Chaptering LLM (full transcript → chapters with scores)
  - Schema: [{chapter_start: float, chapter_end: float, viral_score: float, title: str}]
  - API-level structured output enforcement (zodTextFormat or equivalent)
  - NO duration constraint in LLM call
              ↓
[Stage 2] Algorithm: Filter + Rank
  - Duration filter: discard chapters < 30s, > 90s
  - Top-N by viral_score
  - Overlap NMS (IoU threshold ~0.3)
              ↓
[Stage 3] Enhancement LLM (per-clip)
  - Generate caption text, hook title, social copy
  - Small fast model (likely gpt-4o-mini equivalent)
              ↓
[Stage 4] Video processing
  - FFmpeg extract + reframe + captions + face tracking
```

**Key insight:** Duration control и dedup — полностью algorithmic (Stage 2), LLM знает только о viral_score и narrative coherence, не о duration constraints.

**Confidence level:** MEDIUM. Структура согласуется с engineering blog, pricing model, и external analysis.

---

## Section 5: Concrete Recommendation

### Рекомендация: Text-Anchor Contract (Pattern 4) + Canvas NMS

**Один принцип:** LLM выдаёт semantic intent, алгоритм делает temporal resolution и duration enforcement.

**Почему именно это:**
- Минимальный change к существующим компонентам
- Решает оба симптома (42s вместо 70s, 40 moments с overlaps)
- Не требует дополнительных LLM calls (нет retry loop, нет critic pass)
- Совместим с Flash Lite (легче точно цитировать фразы, чем точно угадывать timestamps)
- Тестируемо: phrase match success rate = measurable metric

### Конкретные изменения

#### Изменение 1: Canvas NMS до evidence extraction

**Файл:** `backend/app/pipeline/stages/canvas_builder.py` (или аналог)

Текущий flow:
```
canvas_builder → 40 candidate_moments → evidence_extraction (6 agents)
```

Новый flow:
```
canvas_builder → 40 candidate_moments → NMS filter → 15-20 unique moments → evidence_extraction
```

NMS реализация:
```python
def temporal_nms(moments: list[CandidateMoment], iou_threshold: float = 0.3) -> list[CandidateMoment]:
    """Non-Maximum Suppression по temporal overlap."""
    if not moments:
        return []
    
    # Сортируем по relevance_score desc
    sorted_moments = sorted(moments, key=lambda m: m.relevance_score, reverse=True)
    
    kept = []
    for candidate in sorted_moments:
        overlap_with_kept = False
        for kept_m in kept:
            iou = compute_temporal_iou(
                (candidate.start_time, candidate.end_time),
                (kept_m.start_time, kept_m.end_time)
            )
            if iou > iou_threshold:
                overlap_with_kept = True
                break
        if not overlap_with_kept:
            kept.append(candidate)
    
    return kept

def compute_temporal_iou(a: tuple, b: tuple) -> float:
    """IoU для временных отрезков."""
    inter_start = max(a[0], b[0])
    inter_end = min(a[1], b[1])
    if inter_start >= inter_end:
        return 0.0
    inter = inter_end - inter_start
    union = (a[1] - a[0]) + (b[1] - b[0]) - inter
    return inter / union if union > 0 else 0.0
```

**Эффект:** 40 moments → ~15-20 unique moments. Evidence extraction 6 agents работают с реальным diverse set, не с дубликатами.

#### Изменение 2: Story Doctor выдаёт text anchors, не timestamps

**Файл:** `backend/app/pipeline/stages/story_doctor.py` + Pydantic schema

Изменение schema:
```python
# БЫЛО:
class StoryArc(BaseModel):
    start_time: float   # seconds
    end_time: float     # seconds
    hook: str
    payoff: str

# СТАЛО:
class StoryArc(BaseModel):
    hook_anchor_phrase: str  # first 8-12 words of hook sentence (exact quote from transcript)
    payoff_anchor_phrase: str  # last 8-12 words of payoff sentence (exact quote from transcript)
    arc_title: str
    arc_theme: str
    target_duration_hint: float = 60.0  # LLM suggests duration, algorithm enforces
```

Промпт изменение — добавить к system prompt:
```
IMPORTANT: For hook_anchor_phrase and payoff_anchor_phrase, use EXACT QUOTES from the transcript text provided. 
These are 8-12 word phrases that will be searched in the transcript to find timestamps.
Do NOT paraphrase. Do NOT generate new text. Quote directly.
```

#### Изменение 3: Composer resolver с hard duration enforcement

**Файл:** `backend/app/pipeline/stages/composer.py` (или `multi_arc_builder.py`)

```python
def resolve_arc_to_timestamps(
    arc: StoryArc,
    transcript: Transcript,
    min_duration: float = 30.0,
    max_duration: float = 80.0,
    target_duration: float = 60.0,
) -> TimeRange | None:
    """
    Резолвит text anchors в timestamps с hard duration enforcement.
    """
    # Найти sentence с hook phrase
    hook_sentence = transcript.find_sentence_containing_phrase(
        arc.hook_anchor_phrase,
        fuzzy_threshold=0.8
    )
    if hook_sentence is None:
        logger.warning(f"Hook phrase not found: {arc.hook_anchor_phrase[:30]}...")
        return None
    
    start = hook_sentence.start_time
    
    # Найти sentence с payoff phrase
    payoff_sentence = transcript.find_sentence_containing_phrase(
        arc.payoff_anchor_phrase,
        fuzzy_threshold=0.8
    )
    
    if payoff_sentence and payoff_sentence.end_time > start:
        end = payoff_sentence.end_time
    else:
        # Fallback: target duration от start
        end = start + target_duration
    
    # HARD ENFORCEMENT (алгоритм, не LLM):
    duration = end - start
    
    if duration < min_duration:
        # Extend end to next sentence boundary past min_duration
        end = transcript.find_sentence_boundary_after(start + min_duration)
    
    if duration > max_duration:
        # Trim to sentence boundary nearest to target
        end = transcript.find_sentence_boundary_nearest(
            start + target_duration,
            search_window=10.0  # ±10s от target
        )
    
    return TimeRange(start=start, end=min(end, transcript.end_time))
```

### Ожидаемый эффект

| Метрика | До | После (прогноз) |
|---|---|---|
| Canvas moments | 40 (10 пар overlap) | 15-20 (unique) |
| Evidence extraction coverage | Дублированная (low diversity) | Diverse (higher recall) |
| Story doctor arcs mean duration | 60s (с bias к anchor timestamps) | 55-65s (semantic) |
| Composer output duration | 42s (tightened by target 50s) | 50-75s (hard floor 30s) |
| Full arc rate (≥70%) | Текущий baseline | +15-25% (прогноз) |
| Final reels count | 10 | 20-35 (из большего diverse pool) |

**Confidence:** MEDIUM. Прогноз основан на patterns из literature и анализе проблемы. Требует A/B validation на job 4cbef84a.

### Компоненты которые НЕ меняются

- Stage 3-4 Compression (Flash Lite parallel) — без изменений
- Stage 5 Evidence extraction (6 agents) — без изменений, просто получают лучший input
- Stage 6 Reducer (Jaccard dedup) — остаётся как дополнительный safety net
- Stage 8 Rhythm check — без изменений
- Stage 9 Variants — без изменений
- Все 189 тестов — не должны сломаться (изменение только в schema + resolver)

---

## Section 6: Sources

### Academic Papers

| Source | URL | Confidence | Notes |
|---|---|---|---|
| Chapter-Llama (CVPR 2025) | arxiv.org/abs/2504.00072 | HIGH | Direct source crawled. Key finding: start-only timestamp > start+end timestamp for LLM input |
| ARC-Chapter (Tencent 2025) | arxiv.org/abs/2511.14349 | HIGH | Direct source crawled. GRACE metric, hierarchical output schema |
| HIVE (EMNLP Industry 2025) | aclanthology.org/2025.emnlp-industry.185 | HIGH | PDF crawled. Best paper for our use case: 3-subtask decomposition |
| LLM×MapReduce (ACL 2025) | aclanthology.org/2025.acl-long.1341 | HIGH | Structured information protocol for inter-chunk dependencies |
| TimeRefine (WACV 2026) | arxiv.org/abs/2412.09601 | HIGH | Iterative temporal refinement: +3.6-5.0% mIoU |

### Open Source Projects

| Project | URL | Stars | Analysis Depth |
|---|---|---|---|
| ClipsAI | github.com/ClipsAI/clipsai | 473 | Deep (docs + pypi) |
| FunClip | github.com/modelscope/FunClip | 5535 | Deep (HF space source) |
| PromptClip | github.com/video-db/PromptClip | 174 | Medium (notebook) |
| Chapter-Llama | github.com/lucas-ventura/chapter-llama | CVPR | Deep (paper) |
| ARC-Chapter | github.com/TencentARC/ARC-Chapter | 41 | Deep (paper) |
| Cut-AI | github.com/AI-Nate/Cut-AI | 20 | Medium (README) |
| youtube-to-viral-clips | github.com/guillaumegay13 | 3 | Medium (config.py) |
| Outlines | github.com/dottxt-ai/outlines | 13610 | Deep (docs) |

### Engineering Blog Posts

| Source | URL | Confidence | Key Quote |
|---|---|---|---|
| OpusClip Engineering (Sep 2025) | medium.com/opus-engineering/bridging-the-gap... | MEDIUM | "Once a schema/responseFormat is set in code, do not describe output formatting in the prompt. Mixing prompt-format rules with the engineer-defined schema creates two sources of truth." |
| AI Researcher on Opus (Sam) | medium.com/@sb2702 | MEDIUM | "Opus and similar tools generally output ~30 clips knowing that only about 30% of the clips will be 'any good'" |
| ClipSpeedAI Engineering | dev.to/kyle_clipspeedai... | MEDIUM | "Use YouTube's auto-captions for a free first pass. Filter out segments where transcript density is too low. Only send remaining candidates to GPT-4o." |

### Confidence Levels по Key Claims

| Claim | Confidence | Basis |
|---|---|---|
| FunClip использует text-anchor (phrase) не timestamp contract | HIGH | HuggingFace source code видел videoclipper.py |
| Chapter-Llama: start-only timestamp лучше чем start+end | HIGH | Таблица из paper crawled напрямую |
| HIVE 3-subtask decomposition | HIGH | PDF paper crawled напрямую |
| OpusClip API-level structured output | MEDIUM | Engineering blog + API docs |
| OpusClip duration filter algorithmic (not LLM) | LOW-MEDIUM | Inference из pricing model + user reports |
| Text-anchor улучшит наши duration distributions | MEDIUM | Pattern match с FunClip + HIVE |
| Canvas NMS исправит overlap дубли | HIGH | По определению temporal NMS убирает overlaps |

---

## Appendix: Knowledge Gaps и Открытые Вопросы

1. **OpusClip internal architecture** — остаётся black box. Нет публичных технических papers, нет OS кода. Engineering blog раскрывает structured output pattern, но не chaptering/duration mechanism. Low-medium confidence reconstruction.

2. **Flash Lite text-anchor accuracy** — неизвестно как хорошо Flash Lite цитирует точные фразы из transcript. Это ключевой риск Pattern 4. Нужен A/B test: compare phrase-match success rate vs direct timestamp accuracy.

3. **Optimal NMS IoU threshold** для нашего domain (talking-head 95-мин видео) — 0.3 из литературы (object detection), может быть неоптимально для narrative clips. 0.5-0.7 может быть лучше.

4. **target_duration_hint vs hard enforcement** — story_doctor должен подсказывать duration или полностью доверять алгоритму? Hybrid может работать хуже чем pure-algorithm.

5. **Phrase fuzzy matching threshold** — 0.8 cosine similarity? Levenshtein? Exact? Зависит от качества transcript (mlx-whisper vs Deepgram).
